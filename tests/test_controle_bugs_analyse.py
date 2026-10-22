"""Contrôle des bugs d'octobre 2026, groupe « analyse » : chaque test échouait sur cfe04e1.

1. État de la lecture après une analyse pendant la requête : l'état d'une ancienne lecture en tâche de fond
   (en erreur, ou restée « en cours » après la mort de sa tâche) ne survit plus sous « termine » ; GET /lecture
   ne dit plus « La lecture ou l'analyse du dossier a échoué. Réessayez : votre analyse n'a pas été débitée. »
   d'une analyse qui a réussi et qui a été débitée.
2. Tableur dont les cellules n'ont pas d'adresse (« r », facultative dans le format) : chaque cellule est lue à
   sa place ; avant, elles s'écrasaient toutes dans la première colonne et la pièce était dite « lue en entier ».
3. Tableur : une cellule au format date est écrite en date lisible (« 15/12/2026 »), et non comme le nombre de
   jours que le tableur enregistre (« 46371 »).
4. Lieu d'exécution sur plusieurs départements (« Rennes (35) et Brest (29) », « Région Bretagne (22, 29, 35,
   56) ») : dans la zone dès que l'un d'eux l'est ; avant, seul le premier était lu (« hors zone » pour une
   entreprise du 29) ou aucun (« Lieu d'exécution non précisé »).
5. Carte d'analyse de « Trouver des marchés » : la pastille « Seul » dit le verdict seul, jamais « Bon potentiel
   en groupement » à côté de « À plusieurs Y % ».
6. En-tête d'un marché créé à la main puis analysé depuis un dossier importé : aucun lien « · réf » vide.
"""
import io
import json
import os
import re
import shutil
import subprocess
import zipfile

import pytest

from tests.test_lecture_integrale import _petit_dossier, _project, fake_ia  # noqa: F401
from tests.test_redaction_socle0 import _db, _user_id

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = open(os.path.join(ROOT, "app", "static", "app.js"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "app", "static", "app.html"), encoding="utf-8").read()
NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'


def _methode(nom):
    from tests.test_reorganisation_v2b_espace_partenaire import _methode as m
    return m(nom)


def _node(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _objet_vue(*noms):
    """Les méthodes nommées de l'application, dans un objet JavaScript (« ({ m1(…) {…}, m2(…) {…}, }) »)."""
    return "({\n" + "\n".join(_methode(n) for n in noms) + "\n})"


# ═══ 1. État de la lecture après une analyse pendant la requête ═════════════════════════════════════════════

def _poser_lecture(pid, uid, etat, erreur):
    """Pose sur le marché l'état laissé par une lecture en tâche de fond dont la tâche a échoué."""
    from sqlalchemy.orm.attributes import flag_modified
    from app.models import Job, Project
    from app.services import lecture_taches
    db = _db()
    try:
        j = Job(user_id=uid, kind=lecture_taches.KIND, status="error", label="Lecture du dossier du marché",
                error=erreur)
        db.add(j)
        db.commit()
        p = db.get(Project, pid)
        st = {"etat": etat, "job_id": j.id, "source": "GROS.zip"}
        if etat == "erreur":
            st["erreur"] = erreur
        p.workflow = dict(p.workflow or {}, lecture=st)
        flag_modified(p, "workflow")
        db.commit()
        return j.id
    finally:
        db.close()


def test_c1_analyse_pendant_la_requete_apres_une_lecture_de_fond_en_echec(client, auth, fake_ia):
    from tests.test_lecture_integrale import _used
    fake_ia()
    h = auth["headers"]
    pid = _project(client, h, "Etat d'une ancienne lecture")
    uid = _user_id(auth["email"])
    echec = "La lecture ou l'analyse du dossier a échoué. Réessayez : votre analyse n'a pas été débitée."
    jid = _poser_lecture(pid, uid, "erreur", echec)
    st = client.get(f"/api/sourcing/lecture/{pid}", headers=h).json()
    assert st["etat"] == "erreur"                    # l'ancienne lecture a bien échoué
    avant = _used(auth["email"])
    # Petit dossier : analysé pendant la requête, réussi, débité.
    r = client.post("/api/sourcing/analyze-upload", headers=h, data={"project_id": str(pid)},
                    files={"file": ("DCE.zip", _petit_dossier(), "application/zip")})
    assert r.status_code == 200, r.text
    assert _used(auth["email"]) == avant + 1
    st = client.get(f"/api/sourcing/lecture/{pid}", headers=h).json()
    assert st["etat"] == "termine" and st["erreur"] == "", st
    wf = client.get(f"/api/projects/{pid}", headers=h).json()["workflow"]["lecture"]
    assert wf["etat"] == "termine" and "erreur" not in wf and wf.get("job_id") != jid, wf

    # Lecture restée « en cours » dont la tâche est morte (redémarrage du serveur) : « Ré-analyser » est permis
    # (aucune tâche ne tourne), l'analyse réussit pendant la requête, l'état repart de zéro.
    _poser_lecture(pid, uid, "en_cours", "Interrompu par un redémarrage du serveur.")
    rr = client.post("/api/sourcing/reanalyze", headers=h, data={"project_id": str(pid)})
    assert rr.status_code == 200, rr.text
    st = client.get(f"/api/sourcing/lecture/{pid}", headers=h).json()
    assert st["etat"] == "termine" and st["erreur"] == "", st


# ═══ 2. Tableur : cellules sans adresse ═════════════════════════════════════════════════════════════════════

def _xlsx(sheet_xml, styles=None, workbook=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        if workbook is not None:
            z.writestr("xl/workbook.xml", workbook)
        if styles is not None:
            z.writestr("xl/styles.xml", styles)
        z.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return buf.getvalue()


def _feuille_sans_adresse(rows):
    xml = f"<worksheet {NS}><sheetData>"
    for i, row in enumerate(rows, 1):
        xml += f'<row r="{i}">' + "".join(f'<c t="inlineStr"><is><t>{v}</t></is></c>' for v in row) + "</row>"
    return xml + "</sheetData></worksheet>"


def test_c2_tableur_cellules_sans_adresse_lues_a_leur_place():
    from app.services.analysis import extract_xlsx
    from app.services.dce_lecture import LU, lire_dossier
    rows = [["Poste", "Designation", "Prix unitaire HT"], ["1", "Fourniture et pose de bordure T2", "37 EUR"],
            ["2", "Reprise de chaussee", "120 EUR"]]
    data = _xlsx(_feuille_sans_adresse(rows))
    assert extract_xlsx(data) == ("Poste | Designation | Prix unitaire HT\n"
                                  "1 | Fourniture et pose de bordure T2 | 37 EUR\n2 | Reprise de chaussee | 120 EUR")
    p = lire_dossier("BPU.xlsx", data, mode="direct")["pieces"][0]
    assert p["statut"] == LU and "1 | Fourniture et pose de bordure T2 | 37 EUR" in p["texte"]
    # Adresses et absences mêlées : une cellule sans adresse suit la précédente (B1, -, E1, -).
    xml = (f'<worksheet {NS}><sheetData><row r="1"><c r="B1" t="inlineStr"><is><t>b</t></is></c>'
           '<c t="inlineStr"><is><t>c</t></is></c><c r="E1" t="inlineStr"><is><t>e</t></is></c>'
           '<c t="inlineStr"><is><t>f</t></is></c></row></sheetData></worksheet>')
    assert extract_xlsx(_xlsx(xml)) == "b | c | e | f"
    # Avec adresses partout : inchangé (une cellule vide entre deux reste un trou, sans colonne fantôme).
    xml = (f'<worksheet {NS}><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>a</t></is></c>'
           '<c r="C1" t="inlineStr"><is><t>c</t></is></c><c r="B1" t="inlineStr"><is><t>b</t></is></c>'
           '</row></sheetData></worksheet>')
    assert extract_xlsx(_xlsx(xml)) == "a | b | c"


# ═══ 3. Tableur : dates lisibles ════════════════════════════════════════════════════════════════════════════

_STYLES = (f'<styleSheet {NS}><numFmts count="5">'
           '<numFmt numFmtId="164" formatCode="dd/mm/yyyy\\ hh:mm"/>'
           '<numFmt numFmtId="165" formatCode="#,##0.00\\ &quot;€&quot;"/>'
           '<numFmt numFmtId="166" formatCode="hh:mm"/>'
           '<numFmt numFmtId="167" formatCode="[h]:mm"/>'
           '<numFmt numFmtId="168" formatCode="[$-40C]dddd\\ d\\ mmmm\\ yyyy"/>'
           '</numFmts><cellXfs count="8"><xf numFmtId="0"/><xf numFmtId="14"/><xf numFmtId="164"/>'
           '<xf numFmtId="165"/><xf numFmtId="20"/><xf numFmtId="166"/><xf numFmtId="167"/><xf numFmtId="168"/>'
           '</cellXfs></styleSheet>')


def _classeur_dates(cellules, avec_styles=True, date1904=False):
    pr = '<workbookPr date1904="1"/>' if date1904 else "<workbookPr/>"
    wb = f"<workbook {NS}>{pr}<sheets/></workbook>"
    sheet = f'<worksheet {NS}><sheetData><row r="1">{cellules}</row></sheetData></worksheet>'
    return _xlsx(sheet, styles=_STYLES if avec_styles else None, workbook=wb)


def test_c3_tableur_dates_lisibles_et_non_nombre_de_jours():
    from app.services.analysis import extract_xlsx
    cel = ('<c r="A1" t="inlineStr"><is><t>Date limite</t></is></c><c r="B1" s="1"><v>46371</v></c>'
           '<c r="C1" s="2"><v>46371.395833</v></c><c r="D1" s="3"><v>1234.5</v></c><c r="E1" s="4"><v>0.5</v></c>'
           '<c r="F1"><v>46371</v></c><c r="G1" s="5"><v>0.395833</v></c><c r="H1" s="7"><v>46371</v></c>')
    # Date, date et heure, montant (inchangé), heure (format intégré), nombre sans style (inchangé), heure
    # (format personnalisé « hh:mm », sans jour fictif), date longue (format personnalisé avec langue).
    assert extract_xlsx(_classeur_dates(cel)) == (
        "Date limite | 15/12/2026 | 15/12/2026 09:30 | 1234.5 | 12:00 | 46371 | 09:30 | 15/12/2026")
    # Sans styles lisibles, les nombres restent des nombres.
    assert extract_xlsx(_classeur_dates(cel, avec_styles=False)) == (
        "Date limite | 46371 | 46371.395833 | 1234.5 | 0.5 | 46371 | 0.395833 | 46371")
    # Base 1904 du classeur.
    assert extract_xlsx(_classeur_dates('<c r="A1" s="1"><v>46371</v></c>', date1904=True)) == "16/12/2030"
    # Durée cumulée (« [h]:mm », 36 heures) : jamais réduite à une heure du jour ; le nombre reste.
    assert extract_xlsx(_classeur_dates('<c r="A1" s="6"><v>1.5</v></c>')) == "1.5"
    # Une valeur nulle dans une colonne de dates n'invente pas une date de 1899.
    assert extract_xlsx(_classeur_dates('<c r="A1" s="1"><v>0</v></c>')) == "0"
    # Une cellule texte au style de date reste du texte.
    assert extract_xlsx(_classeur_dates('<c r="A1" s="1" t="inlineStr"><is><t>à préciser</t></is></c>')) == (
        "à préciser")


# ═══ 4. Lieu d'exécution sur plusieurs départements ═════════════════════════════════════════════════════════

def test_c4_lieu_sur_plusieurs_departements_dans_la_zone_des_que_l_un_y_est():
    from app.services.dce_scoring import _dept, score_dce
    base = {"intitule_marche": "Travaux de voirie", "date_limite": "15/12/2099"}
    crit = {"departements": ["29"], "specialites": "voirie"}

    def zone(lieu):
        r = score_dce(dict(base, lieu_execution=lieu), {"postal_code": "29000"}, crit)
        return next(c for c in r["breakdown"] if c["key"] == "zone")
    for lieu in ("Rennes (35) et Brest (29)", "Région Bretagne (22, 29, 35, 56)"):
        z = zone(lieu)
        assert (z["status"], z["points"], z["detail"]) == ("ok", 20, "Lieu d'exécution dans votre zone (29)"), (lieu, z)
    z = zone("Rennes (35) et Nantes (44)")
    assert (z["status"], z["points"], z["detail"]) == ("partiel", 5, "Hors zone d'intervention (dépt 35, 44)")
    z = zone("Lille (59)")
    assert (z["status"], z["detail"]) == ("partiel", "Hors zone d'intervention (dépt 59)")
    z = zone("Quimper (29)")
    assert (z["status"], z["detail"]) == ("ok", "Lieu d'exécution dans votre zone (29)")
    # Un seul département, un code postal : _dept inchangé pour tous ses appelants (le premier d'une liste).
    for s, d in (("Quimper (29)", "29"), ("29000", "29"), ("20100", "2A"), ("20200", "2B"), ("97400", "974"),
                 ("Saint-Denis (974)", "974"), ("", ""), ("Rennes (35) et Brest (29)", "35")):
        assert _dept(s) == d, (s, _dept(s))

    from app.services.dce_scoring import _depts
    assert _depts("Rennes (35) et Brest (29)") == ["35", "29"]
    assert _depts("Région Bretagne (22, 29, 35, 56)") == ["22", "29", "35", "56"]
    assert _depts("Brest (29200) et Lorient (56100)") == ["29", "56"]
    assert _depts("Ajaccio (2A) et Bastia (2B)") == ["2A", "2B"]
    # Ni un numéro d'article, ni une année, ni des numéros de lots, ni un décimal.
    assert _depts("Lille (59) (voir article 3.2)") == ["59"]
    assert _depts("Lorient (56), tranche 2 (2027)") == ["56"]
    assert _depts("Marché en 3 lots (lot 12 et lot 13)") == []


def test_c4_groupement_zone_sur_plusieurs_departements():
    """Chef de file du 44, marché à Rennes (35) et Brest (29) : le manque nomme les deux départements, et un
    partenaire du 29 le comble."""
    from app.services import groupement_scoring as gs
    details = {"intitule_marche": "Travaux de voirie", "lieu_execution": "Rennes (35) et Brest (29)",
               "date_limite": "15/12/2099", "budget_estime": "200 000 EUR HT"}
    lead = {"name": "Chef", "postal_code": "44000", "ca_n1": 500000}
    crit = {"departements": ["44"], "specialites": "voirie"}
    z = next(g for g in gs.gaps_for(details, lead, crit) if g["key"] == "zone")
    assert z["required"] == "départements 35, 29 (Rennes (35) et Brest (29))", z
    partner = {"name": "Brestois", "kind": "annuaire", "departements": ["29"], "specialites": "voirie"}
    res = gs.score_groupement(details, lead, crit, [partner])
    assert not any(g["key"] == "zone" for g in res["gaps"]), res["gaps"]
    assert any(g["key"] == "zone" and "Brestois" in (g.get("apporte_par") or []) for g in res["gaps_combles"])
    # Un seul département : le manque garde sa forme.
    z = next(g for g in gs.gaps_for(dict(details, lieu_execution="Brest (29)"), lead, crit) if g["key"] == "zone")
    assert z["required"] == "département 29 (Brest (29))", z


# ═══ 5. Carte de « Trouver des marchés » : le verdict SEUL ══════════════════════════════════════════════════

def test_c5_carte_trouver_dit_le_verdict_seul_jamais_celui_du_groupement(client, auth, monkeypatch):
    from tests.test_groupement_routes import DETAILS, _add_partner, _seed_project
    from app.services import llm
    h = auth["headers"]
    pid, seul, verdict_seul = _seed_project(client, h)
    _add_partner(client, h)
    llm._CB.update(fails=0, open_until=0.0)
    llm._TENANT_CB.clear()
    payload = json.dumps({"match_score": 50, "go_decision": "a_etudier", "summary": "Analyse simulée.",
                          "details": DETAILS})

    class _Resp:
        usage = type("U", (), {"input_tokens": 10, "output_tokens": 20})()
        content = [type("B", (), {"text": payload})()]
    monkeypatch.setattr(llm, "_use_mistral", lambda: False)
    monkeypatch.setattr(llm, "client", lambda: type("C", (), {
        "messages": type("M", (), {"create": staticmethod(lambda **kw: _Resp())})}))
    dce = ("Règlement de la consultation : rénovation thermique et étanchéité du groupe scolaire. "
           "Chiffre d'affaires minimum 300 000 EUR. Qualification Qualibat 1512 exigée. " * 4).encode("utf-8")
    r = client.post("/api/sourcing/analyze-upload", headers=h, data={"project_id": str(pid)},
                    files={"file": ("dce.txt", dce, "text/plain")})
    assert r.status_code == 200, r.text
    j = r.json()
    # « decision » est le verdict posé sur le marché (de groupement ici) ; le verdict seul est dit à part.
    assert j["decision"] == "go_groupement" and j["score"] == seul
    assert j["decision_seul"] == verdict_seul == "a_etudier"
    llm._CB.update(fails=0, open_until=0.0)

    # L'écran : la pastille « Seul » lit le verdict seul.
    carte = HTML[HTML.index("Décision 8 : après le dossier, le couple"):]
    carte = carte[:carte.index("</div>\n            </div>")]
    assert "decLabel(src.analysis.decision)" not in carte and "src.analysis.decision||" not in carte
    assert "decLabel(srcSeulDecision(src.analysis))" in carte and "srcSeulDecision(src.analysis)||'neutral'" in carte
    vu = _node("const app = " + _objet_vue("srcSeulDecision", "decLabel") + ";"
               "app.criteria = {go_threshold: 75, nogo_threshold: 40};"
               "const f = a => app.decLabel(app.srcSeulDecision(a));"
               "console.log(JSON.stringify(["
               "f({decision: 'go_groupement', decision_seul: 'a_etudier', score: 50}),"
               "f({decision: 'go_groupement', score: 80}),"        # ancienne réponse sans decision_seul : seuils
               "f({decision: 'go_groupement', score: 20}),"
               "f({decision: 'no_go', score: 20}),"
               "f({decision: 'go', decision_seul: 'go', score: 90})]));")
    assert vu == ["À étudier", "Bon potentiel", "Peu adapté", "Peu adapté", "Bon potentiel"], vu


# ═══ 6. En-tête du marché : aucun lien « · réf » vide sans avis ═════════════════════════════════════════════

def test_c6_marche_sans_avis_sans_lien_ref_vide(client, auth, fake_ia):
    fake_ia()
    h = auth["headers"]
    pid = _project(client, h, "Créé à la main")
    r = client.post("/api/sourcing/analyze-upload", headers=h, data={"project_id": str(pid)},
                    files={"file": ("DCE.zip", _petit_dossier(), "application/zip")})
    assert r.status_code == 200, r.text
    # Ce que l'écran reçoit : un bloc « source » vide (aucun avis derrière ce marché).
    assert client.get(f"/api/projects/{pid}", headers=h).json()["ai_analysis"]["source"] == {}
    # L'en-tête n'affiche le lien que si aoSource() renvoie un bloc (v-if="aoSource()").
    assert re.search(r'<a v-if="aoSource\(\)" :href="safeUrl\(aoSource\(\)\.source_url\)"', HTML)
    vu = _node("const app = " + _objet_vue("aoSource") + ";"
               "const s = x => { app.ao = {project: {ai_analysis: x === undefined ? {} : {source: x}}};"
               " return app.aoSource(); };"
               "console.log(JSON.stringify([s({}), s(undefined), s(null),"
               " s({source: 'BOAMP', official_ref: '26-1', source_url: 'https://www.boamp.fr/avis/1'})]));")
    assert vu == [None, None, None, {"source": "BOAMP", "official_ref": "26-1",
                                     "source_url": "https://www.boamp.fr/avis/1"}], vu
