"""
Réorganisation de l'interface — vague 2a, chantier A3 : entreprise, documents, confirmations, vocabulaire.
Contrat : docs/REORGANISATION_V2A.md, section A3 ; étude « organisation du logiciel », § 5.3, 7.1, 7.3, 8, 9 ;
décisions 10 (« partie (lot n) ») et 8, 9 (comme en vague 1).

  1. Mon entreprise en 4 onglets : Identité · Ce que je cherche · Mes preuves · Tarifs ; le « montant que je porte
     seul », vide par défaut, jamais déduit d'un autre champ, utilisé nulle part (l'étude ne s'en sert qu'avec
     l'innovation A du moteur, derrière un interrupteur) ;
  2. Mes documents : catégorie et date de fin visibles et modifiables dans la liste ; un seul calcul de la fin
     (liste, pastille « pièces à renouveler », courriel), au jour de Paris ; une date changée a ses propres alertes ;
  3. plus aucun confirm() ni prompt() du navigateur : la fenêtre de confirmation de l'application (dialogue modal,
     focus gardé, clavier, 375 px) ;
  4. « lot » devient « partie (lot n) » dans les textes lus à l'écran ; les fichiers exportés, les données et les
     citations du règlement gardent « lot ».

Sans navigateur ni réseau ; les fonctions pures et la fenêtre sous Node.
"""
import ast
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from datetime import date, timedelta

import pytest

from tests.textes_visibles import _ATTR_TECHNIQUES, _CLE, _regex_possible, textes_courriels, textes_html, textes_js
from tests.zones import zone

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
HTML = (STATIC / "app.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "styles.css").read_text(encoding="utf-8")


def _lire(nom):
    return (STATIC / nom).read_text(encoding="utf-8")


def _node(script, *args):
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    r = subprocess.run([node, "-e", script] + list(args), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _fonction(src, nom):
    i = src.index(f"function {nom}(")
    return src[i:src.index("\n}\n", i) + 3]


def _accolade_fermante(src, i):
    """Indice juste après l'accolade qui ferme celle ouverte en `i` (chaînes, gabarits et commentaires sautés)."""
    prof, j, n = 0, i, len(src)
    while j < n:
        c = src[j]
        if src.startswith("//", j):
            j = src.find("\n", j)
            continue
        if src.startswith("/*", j):
            j = src.index("*/", j) + 2
            continue
        if c == "/" and _regex_possible(src, j):          # expression régulière : /[&<>"]/g
            k, classe = j + 1, False
            while k < n and src[k] != "\n":
                if src[k] == "\\":
                    k += 2
                    continue
                if src[k] == "[":
                    classe = True
                elif src[k] == "]":
                    classe = False
                elif src[k] == "/" and not classe:
                    break
                k += 1
            j = k + 1
            continue
        if c in "\"'`":
            k = j + 1
            while k < n and src[k] != c:
                k += 2 if src[k] == "\\" else 1
            j = k + 1
            continue
        if c == "{":
            prof += 1
        elif c == "}":
            prof -= 1
            if prof == 0:
                return j + 1
        j += 1
    raise AssertionError("accolade non fermée")


def _methode(nom):
    """Le texte d'une méthode Vue de app.js (« nom(…) { … } » ou « async nom(…) { … } »), sans la virgule."""
    m = re.search(r"\n    (async )?" + re.escape(nom) + r"\(", JS)
    assert m, nom
    i = JS.index("{", m.end())
    return JS[m.start() + 1:_accolade_fermante(JS, i)].strip()


def _ent(*noms):
    return "const o = {\n" + ",\n".join(_methode(n) for n in noms) + "\n};\n"


# ═══ 1. Mon entreprise en 4 onglets ═════════════════════════════════════════════════════════════════

def test_mon_entreprise_en_quatre_onglets_dans_l_ordre_de_l_etude():
    i = JS.index("const RUBRIQUES = [")
    rub = _node(JS[i:JS.index("\n];\n", i) + 4] + "\nconsole.log(JSON.stringify(RUBRIQUES.find(r => r.k === 'entreprise')));")
    assert rub["vues"] == ["company", "criteria", "preuves", "tarifs"]
    assert [(t["view"], t["label"], t["ic"]) for t in rub["onglets"]] == [
        ("company", "Identité", "building-2"), ("criteria", "Ce que je cherche", "sliders-horizontal"),
        ("preuves", "Mes preuves", "award"), ("tarifs", "Tarifs", "calculator")]
    assert rub["onglets"][1]["ancien"] == "Mes critères"                 # bulle de transition (anciens comptes)
    assert rub["onglets"][3]["avant"] == "Vos tarifs étaient dans l'onglet « Identité »."
    assert 'criteria: "Ce que je cherche", tarifs: "Tarifs",' in JS     # titres des vues
    # La mesure d'usage compte le nouvel onglet (une vue).
    from app.services.mesure_usage import ECRANS
    assert "tarifs" in ECRANS


def test_tarifs_sortis_d_identite_avec_leur_propre_bouton():
    ident, tarifs = zone(HTML, "vue-company"), zone(HTML, "vue-tarifs")
    for champ in ("company.day_rates", "company.distance_threshold_km", "company.distance_surcharge_pct"):
        assert champ in tarifs and champ not in ident, champ
    assert '@click="saveCompany(\'tarifs\')"' in tarifs and '@click="saveCompany()"' in ident
    assert "go('tarifs')" in ident                                       # renvoi depuis Identité
    assert "Estimer mon prix" in tarifs                                  # dit à quoi servent les tarifs (vrai : chiffrage.py)
    # Une seule fiche, deux boutons : le message dit l'onglet concerné.
    s = _methode("saveCompany")
    assert "Tarifs enregistrés" in s and "dans l'onglet « Identité »" in s


def test_ce_que_je_cherche_metiers_zone_montants_puis_seuils():
    v = zone(HTML, "vue-criteria")
    ordre = [v.index(x) for x in ("Mes métiers", "Ma zone", "Montants", "Montant que je porte seul", "Seuils de recommandation")]
    assert ordre == sorted(ordre)
    # Chaque champ a son libellé lié (accessibilité de base).
    for i in ("crit-spec", "crit-cpv", "crit-qual", "crit-excl", "crit-km", "crit-dep", "crit-bmin", "crit-bmax",
              "crit-seul", "crit-go", "crit-nogo"):
        assert f'<label for="{i}"' in v and f'id="{i}"' in v, i
    assert 'v-model.number="criteria.montant_porte_seul" placeholder="Non renseigné"' in v
    # La bulle dit ce que fait (et ne fait pas) le champ, sans annoncer de fonction qui n'est pas en ligne.
    bulle = v[v.index("Montant que je porte seul"):]
    bulle = bulle[:bulle.index("</label>")]
    assert "Il ne masque aucun marché et ne change aucune note" in bulle and "ne le déduit d'aucun autre champ" in bulle
    assert "bientôt" not in bulle.lower() and "pas encore" not in bulle.lower()


def test_montant_porte_seul_vide_par_defaut_enregistre_garde_et_efface(client, auth):
    h = auth["headers"]
    d = client.get("/api/criteria/", headers=h).json()
    assert d["montant_porte_seul"] is None and d["budget_max"] == 500000      # jamais déduit de budget_max
    body = dict(d, specialites="Couverture", montant_porte_seul=300000)
    r = client.put("/api/criteria/", headers=h, json=body)
    assert r.status_code == 200 and r.json()["montant_porte_seul"] == 300000
    # Une page plus ancienne qui n'envoie pas le champ ne l'efface pas.
    sans = {k: v for k, v in body.items() if k != "montant_porte_seul"}
    assert client.put("/api/criteria/", headers=h, json=sans).json()["montant_porte_seul"] == 300000
    # Vidé dans le formulaire (null ou "") : effacé.
    assert client.put("/api/criteria/", headers=h, json=dict(body, montant_porte_seul="")).json()["montant_porte_seul"] is None
    client.put("/api/criteria/", headers=h, json=body)
    assert client.put("/api/criteria/", headers=h, json=dict(body, montant_porte_seul=None)).json()["montant_porte_seul"] is None
    # Un montant négatif ou absurde est refusé, avec une phrase.
    for v in (-1, 2e10):
        r = client.put("/api/criteria/", headers=h, json=dict(body, montant_porte_seul=v))
        assert r.status_code == 400 and "montant positif" in r.json()["detail"]
    # Mes données (RGPD) : exporté avec ce que la page enregistre vraiment (les critères étendus).
    client.put("/api/criteria/", headers=h, json=body)
    ex = client.get("/api/rgpd/export", headers=h).json()
    assert ex["criteres"]["montant_porte_seul"] == 300000 and ex["criteres"]["specialites"] == "Couverture"


def test_montant_porte_seul_n_entre_dans_aucun_calcul():
    """Utilisé seulement là où l'étude le prévoit : l'innovation A du moteur (derrière un interrupteur), pas encore
    construite. Aucun module ne le lit en dehors de sa route, de l'export RGPD et de sa migration ; le classement
    d'un marché ne change pas quand il est rempli."""
    lecteurs = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "app").rglob("*.py")
                      if "montant_porte_seul" in p.read_text(encoding="utf-8"))
    assert lecteurs == ["app/routers/criteria_v2.py"], lecteurs       # rgpd.py le lit par CriteriaUpdate
    from app.sourcing.scoring import score_tender
    from app.sourcing.schemas import NormalizedTender, Provenance
    t = NormalizedTender(objet="Réfection de toiture", acheteur="Ville", departements=["29"], montant_estime=900000.0,
                         provenance=Provenance(source="BOAMP", source_url="https://www.boamp.fr/x"))
    crit = {"specialites": "Couverture", "departements": "29", "budget_min": 0, "budget_max": 500000}
    a = score_tender(t, {"name": "Toits"}, crit)
    b = score_tender(t, {"name": "Toits"}, dict(crit, montant_porte_seul=100000))
    assert a.model_dump() == b.model_dump()


def test_demo_n_invente_aucun_montant_porte_seul(client):
    r = client.post("/api/auth/demo")
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/criteria/", headers=h).json()["montant_porte_seul"] is None


def test_migration_montant_porte_seul_aller_retour_idempotente(tmp_path):
    import sqlalchemy as sa
    dbfile = tmp_path / "seul.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{dbfile}"}

    def run(*args):
        r = subprocess.run([sys.executable, "-m", "alembic"] + list(args), cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stdout + r.stderr

    def colonnes():
        eng = sa.create_engine(f"sqlite:///{dbfile}")
        try:
            return {c["name"] for c in sa.inspect(eng).get_columns("matching_criteria_ext")}
        finally:
            eng.dispose()

    run("upgrade", "head")
    assert "montant_porte_seul" in colonnes()
    run("downgrade", "b3mesureecrans")
    assert "montant_porte_seul" not in colonnes() and "budget_max" in colonnes()
    run("upgrade", "head")
    run("stamp", "b3mesureecrans")
    run("upgrade", "head")                                               # rejeu : idempotent
    assert "montant_porte_seul" in colonnes()


# ═══ 2. Mes documents : catégorie, date de fin, alertes cohérentes ═════════════════════════════════

def test_etat_fin_un_seul_calcul():
    from app.services.pieces_fin import ALERTE_JOURS, etat_fin
    j = date(2026, 10, 20)
    assert etat_fin(None, j) is None
    assert etat_fin(j - timedelta(days=3), j) == {"jours": -3, "a_renouveler": True, "code": "expiree",
                                                   "libelle": "Expirée le 17/10/2026"}
    assert etat_fin(j, j)["libelle"] == "Expire aujourd'hui"
    assert etat_fin(j + timedelta(days=1), j)["libelle"] == "Expire demain"
    assert etat_fin(j + timedelta(days=12), j)["libelle"] == "Expire dans 12 jours"
    assert etat_fin(j + timedelta(days=ALERTE_JOURS), j)["a_renouveler"] is True
    assert etat_fin(j + timedelta(days=ALERTE_JOURS + 1), j) == {"jours": 31, "a_renouveler": False, "code": "valide",
                                                                  "libelle": ""}


def test_jour_de_paris():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.services.pieces_fin import jour_paris
    assert jour_paris() == datetime.now(ZoneInfo("Europe/Paris")).date()


def _doc(client, h, nom="Attestation URSSAF.pdf"):
    r = client.post("/api/documents/", headers=h, files={"file": (nom, b"%PDF-1.4 test", "application/pdf")},
                    data={"name": nom, "category": "autre"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_categorie_et_date_de_fin_modifiables_et_coherentes_avec_la_pastille(client, auth):
    from app.services.pieces_fin import jour_paris
    h = auth["headers"]
    did = _doc(client, h)
    fin = (jour_paris() + timedelta(days=12)).isoformat()
    r = client.patch(f"/api/documents/{did}", headers=h, json={"category": "fiscal", "expiration_date": fin})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["category"] == "fiscal" and d["expiration_date"] == fin
    assert d["fin"] == {"jours": 12, "a_renouveler": True, "code": "bientot", "libelle": "Expire dans 12 jours"}
    liste = {x["id"]: x for x in client.get("/api/documents/", headers=h).json()}
    assert liste[did]["fin"] == d["fin"] and liste[did]["name"] == "Attestation URSSAF.pdf"
    # La pastille compte exactement les pièces que la liste dit « à renouveler ».
    exp = {x["id"]: x for x in client.get("/api/documents/expiring", headers=h).json()}
    assert set(exp) == {i for i, x in liste.items() if x["fin"] and x["fin"]["a_renouveler"]}
    assert exp[did]["fin"] == d["fin"]
    # Valable au-delà de 30 jours : la date suffit, la pièce ne compte pas.
    loin = (jour_paris() + timedelta(days=200)).isoformat()
    d2 = client.patch(f"/api/documents/{did}", headers=h, json={"expiration_date": loin}).json()
    assert d2["fin"]["a_renouveler"] is False and d2["fin"]["libelle"] == ""
    assert did not in {x["id"] for x in client.get("/api/documents/expiring", headers=h).json()}
    # Date retirée : plus rien n'est dit.
    d3 = client.patch(f"/api/documents/{did}", headers=h, json={"expiration_date": ""}).json()
    assert d3["expiration_date"] is None and d3["fin"] is None and d3["category"] == "fiscal"
    # Refus avec une phrase.
    for corps, mot in (({"category": "pizza"}, "Catégorie inconnue"), ({"expiration_date": "32/13/2026"}, "illisible"),
                       ({"expiration_date": "0202-01-01"}, "improbable"), ({}, "Rien à modifier"), ({"name": "  "}, "vide")):
        r = client.patch(f"/api/documents/{did}", headers=h, json=corps)
        assert r.status_code == 400 and mot in r.json()["detail"], (corps, r.text)


def test_une_date_changee_a_ses_propres_alertes(client, auth, monkeypatch):
    from app.core.database import SessionLocal
    from app.models import Document
    from app.services.pieces_fin import jour_paris
    import app.services.alerts as alerts_mod
    envoyes = []
    monkeypatch.setattr(alerts_mod, "send_email", lambda to, subject, text, html=None: envoyes.append((to, subject, text)) or True)
    h = auth["headers"]
    did = _doc(client, h, "Kbis.pdf")
    client.patch(f"/api/documents/{did}", headers=h, json={"expiration_date": (jour_paris() + timedelta(days=5)).isoformat()})
    alerts_mod.run_document_expiry_alerts(SessionLocal())
    a_moi = [x for x in envoyes if x[0] == auth["email"]]
    assert len(a_moi) == 1
    to, sujet, texte = a_moi[0]
    assert sujet == "Adjugo — 1 pièce à renouveler"
    assert "• Kbis.pdf : expire dans 5 jours (date de fin : " in texte      # le libellé de la liste
    assert "Mes documents" in texte and "coffre-fort" not in texte
    # Même date : pas de second envoi. Date renouvelée puis de nouveau proche : de nouvelles alertes.
    alerts_mod.run_document_expiry_alerts(SessionLocal())
    assert len([x for x in envoyes if x[0] == auth["email"]]) == 1
    db = SessionLocal()
    try:
        assert db.query(Document).get(did).alert_7_sent is True
    finally:
        db.close()
    client.patch(f"/api/documents/{did}", headers=h, json={"expiration_date": (jour_paris() + timedelta(days=3)).isoformat()})
    db = SessionLocal()
    try:
        doc = db.query(Document).get(did)
        assert (doc.alert_30_sent, doc.alert_7_sent, doc.alert_day_sent) == (False, False, False)
    finally:
        db.close()
    alerts_mod.run_document_expiry_alerts(SessionLocal())
    assert len([x for x in envoyes if x[0] == auth["email"]]) == 2
    # Ne changer que la catégorie ne relance rien.
    client.patch(f"/api/documents/{did}", headers=h, json={"category": "administratif"})
    db = SessionLocal()
    try:
        assert db.query(Document).get(did).alert_7_sent is True
    finally:
        db.close()


def test_demo_ne_modifie_aucun_document(client):
    r = client.post("/api/auth/demo")
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    docs = client.get("/api/documents/", headers=h).json()
    assert docs and all("fin" in d for d in docs)
    r = client.patch(f"/api/documents/{docs[0]['id']}", headers=h, json={"category": "fiscal"})
    assert r.status_code == 403


def test_liste_des_pieces_categorie_et_date_de_fin_modifiables():
    v = zone(HTML, "vue-documents")
    assert '<th>Date de fin</th>' in v and "Expiration" not in v
    assert '@change="docModifier(d, { category: $event.target.value })"' in v
    assert 'type="date" :value="d.expiration_date || \'\'" @change="docModifier(d, { expiration_date: $event.target.value })"' in v
    assert '{{ d.fin.libelle }}' in v and ':class="d.fin.code"' in v
    assert "Ajoutez vos attestations avec leur date de fin : Adjugo vous prévient avant qu'elles expirent." in v  # étude, § 7.3
    for x in ("aria-label=\"'Catégorie de ' + d.name\"", ":aria-label=\"'Date de fin de ' + d.name\"",
              ":aria-label=\"'Supprimer ' + d.name\""):
        assert x in v, x
    # Les catégories de l'écran sont exactement celles du serveur.
    from app.models import DocCategory
    i = JS.index("const CATEGORIES_DOC = [")
    cats = _node(JS[i:JS.index("];", i) + 2] + "\nconsole.log(JSON.stringify(CATEGORIES_DOC.map(c => c.k)));")
    assert cats == [c.value for c in DocCategory]
    m = _methode("docModifier")
    assert 'this.api("PATCH", "/api/documents/" + d.id, patch)' in m and "this.loadExpiring()" in m
    assert "await this.loadDocuments()" in m                              # refus : l'ancienne valeur revient
    assert "this.loadExpiring()" in _methode("delDoc") and "this.loadExpiring()" in _methode("restoreDoc")
    # Sur téléphone : une pièce par bloc, sans défilement de côté.
    assert ".t-wrap table.doc-table { min-width:0; }" in CSS and ".doc-table thead { display:none; }" in CSS


# ═══ 3. La fenêtre de confirmation de l'application ════════════════════════════════════════════════

FRONT = ("app.js", "app.html", "invite.html", "redaction-partenaire.js", "carnet-notes.js", "sources-publiques.js",
         "cotraitance-crypto.js")


def _code_sans_commentaires(src):
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(l for l in src.split("\n") if not l.strip().startswith("//"))


def test_plus_aucun_confirm_ni_prompt_du_navigateur():
    rx = re.compile(r"(?:^|[^\w.$])(?:window\.)?(confirm|prompt|alert)\s*\(")
    fautes = [f"{f} : {m.group(0)!r}" for f in FRONT for m in rx.finditer(_code_sans_commentaires(_lire(f)))]
    assert not fautes, fautes
    # Les 19 appels de la production passent tous par la fenêtre de l'application.
    for nom in ("rgpdDelete", "orgRemove", "orgTransfer", "convertInvoice", "gateCriteria", "sharedLostCode",
                "sharedEnsureVerified", "sharedDecline", "aoRevokeInvite", "aoGrpCancelPlan",
                "aoUnfreezeOffer", "delProject", "delCotraitant", "delContact", "renameDoc", "srcDelAlert", "kbDelete"):
        m = _methode(nom)
        assert "this.confirmer(" in m or "this.demander(" in m, nom
    # Réunion A2 × A3 : un seul « Figer l'offre » (A2), dans « Convention et accords » ; le second, avec son confirm(),
    # n'existe plus (la route reste, sans bouton).
    assert "    async aoFreezeOffer() {" not in JS and "aoConvAskGenerate(" in JS
    # « caduque » ne revient pas par la porte de la fenêtre (vague 1 : « à revalider », avec la raison).
    assert "sera à revalider : les accords déjà enregistrés ne comptent plus" in _methode("aoUnfreezeOffer")


def test_fenetre_accessible_clavier_et_375_px():
    f = zone(HTML, "fenetre-confirmation")
    for x in ('@keydown.esc="cdlgClose()"', '@keydown.tab="cdlgTab($event)"', 'ref="cdlgBox"',
              ":role=\"cdlg.fields.length ? 'dialog' : 'alertdialog'\"", 'aria-modal="true"', 'aria-labelledby="cdlg-t"',
              ":aria-describedby=\"cdlg.lines.length ? 'cdlg-d' : null\"", ':type="fl.type || \'text\'"',
              '@keydown.enter.prevent="cdlgRun()"', ':disabled="!cdlgValide()"', "{{ cdlg.annuler }}",
              '@click="cdlgAutre()"', ":class=\"cdlg.danger ? 'danger' : 'primary'\"", 'ref="cdlgCancel"'):
        assert x in f, x
    assert "@media (max-width:480px) {\n  .cdlg .modal-f { flex-direction:column-reverse; align-items:stretch; }" in CSS
    # La passe d'accessibilité globale (role="dialog" sur chaque .modal) n'écrase pas une confirmation sans champ :
    # vu dans un vrai navigateur, elle remettait « dialog » sur l'« alertdialog ».
    assert 'if (m.getAttribute("role") !== "alertdialog") m.setAttribute("role", "dialog");' in JS
    t = _methode("cdlgTab")
    assert "e.preventDefault(); last.focus();" in t and "e.preventDefault(); first.focus();" in t


def test_champs_valides_sous_node():
    r = _node(_fonction(JS, "champsValides") + """
console.log(JSON.stringify([
  champsValides([]), champsValides([{ requis: true, value: "  " }]), champsValides([{ requis: true, value: "x" }]),
  champsValides([{ attendu: "SUPPRIMER", value: " supprimer " }]), champsValides([{ attendu: "SUPPRIMER", value: "supprimé" }]),
  champsValides([{ motif: "^\\\\d{6}$", value: "12345" }]), champsValides([{ motif: "^\\\\d{6}$", value: "123456" }]),
  champsValides([{ motif: "^\\\\d{6}$", value: "" }])]));""")
    assert r == [True, False, True, True, False, False, True, True]


def test_la_fenetre_rend_une_promesse_sous_node():
    noms = ("_convAsk", "demander", "confirmer", "_cdlgOuvrir", "_cdlgFermer", "cdlgClose", "cdlgValide", "cdlgRun",
            "cdlgAutre")
    script = (_fonction(JS, "champsValides")
              + "global.document = { activeElement: null, getElementById: () => null, body: { contains: () => false } };\n"
              + _ent(*noms) + """
Object.assign(o, { cdlg: null, _cdlgFocus: null, $refs: {}, $nextTick(f) { if (f) f(); } });
(async () => {
  const r = {};
  let p = o.demander({ title: "T", fields: [{ key: "pw", type: "password", requis: true }, { key: "cf", attendu: "SUPPRIMER" }] });
  o.cdlg.fields[0].value = " mot de passe "; o.cdlg.fields[1].value = "supprimé";
  r.v1 = o.cdlgValide(); await o.cdlgRun(); r.ouvert = !!o.cdlg;
  o.cdlg.fields[1].value = " supprimer "; r.v2 = o.cdlgValide(); await o.cdlgRun();
  r.vals = await p; r.ferme = o.cdlg === null;
  p = o.confirmer({ title: "X" }); r.lignes = o.cdlg.lines; r.ok = o.cdlg.ok; r.ann = o.cdlg.annuler; o.cdlgClose(); r.annule = await p;
  p = o.confirmer({ title: "Y", lines: ["a", { t: "b", warn: true }, ""] }); r.lignes2 = o.cdlg.lines; await o.cdlgRun(); r.confirme = await p;
  p = o.demander({ title: "Z", autre: "Analyser quand même" }); o.cdlgAutre(); r.autre = await p;
  p = o.confirmer({ title: "Z2", autre: "Autre" }); o.cdlgAutre(); r.autreConfirme = await p;
  const p1 = o.demander({ title: "A" }), p2 = o.demander({ title: "B" });
  r.premier = await p1; r.titre = o.cdlg.title; o.cdlgClose(); r.second = await p2;
  let recu = null; o._convAsk({ title: "C", fields: [{ key: "n", value: " x " }], run: v => { recu = v; } });
  await o.cdlgRun(); r.run = recu;
  console.log(JSON.stringify(r));
})();""")
    r = _node(script)
    assert r["v1"] is False and r["ouvert"] is True and r["v2"] is True
    assert r["vals"] == {"pw": " mot de passe ", "cf": "supprimer"} and r["ferme"] is True   # mot de passe tel quel
    assert r["lignes"] == [] and r["ok"] == "Confirmer" and r["ann"] == "Annuler" and r["annule"] is False
    assert r["lignes2"] == [{"t": "a"}, {"t": "b", "warn": True}] and r["confirme"] is True
    assert r["autre"] == {"autre": True} and r["autreConfirme"] is False
    assert r["premier"] is None and r["titre"] == "B" and r["second"] is None   # une seule fenêtre à la fois
    assert r["run"] == {"n": "x"}                                                # les fenêtres de la convention


def test_avant_une_analyse_echap_n_analyse_pas_sous_node():
    """« Dire d'abord ce que vous cherchez ? » : une analyse coûte un crédit, elle ne part jamais sur Échap."""
    script = _ent("gateCriteria", "criteriaEmpty") + """
(async () => {
  const out = [];
  for (const rep of [null, { autre: true }, {}]) {
    const vu = [];
    Object.assign(o, { criteria: {}, go: v => vu.push(v), demander: async () => rep });
    out.push([await o.gateCriteria(), vu]);
  }
  Object.assign(o, { criteria: { specialites: "Couverture" }, demander: async () => { throw new Error("jamais"); } });
  out.push([await o.gateCriteria(), []]);
  console.log(JSON.stringify(out));
})();"""
    assert _node(script) == [[False, []], [True, []], [False, ["criteria"]], [True, []]]
    assert JS.count("if (!(await this.gateCriteria())) return;") == 3 and "this.gateCriteria()) return" not in JS.replace(
        "(await this.gateCriteria())) return", "")


# ═══ 4. « lot » devient « partie (lot n) » (décision 10) ═══════════════════════════════════════════

def test_partie_lot_meme_fonction_partout_sous_node():
    sources = {"app.js": JS, "carnet-notes.js": _lire("carnet-notes.js"), "redaction-partenaire.js": _lire("redaction-partenaire.js")}
    textes = {n: re.sub(r"\s+", " ", _fonction(s.replace("\n  function partieLot", "\nfunction partieLot")
                                                .replace("\n  }\n", "\n}\n"), "partieLot")) for n, s in sources.items()}
    assert len(set(textes.values())) == 1, textes
    r = _node(_fonction(JS, "partieLot") + """
console.log(JSON.stringify([partieLot("2"), partieLot("Lot 2 — Couverture"), partieLot("lot n° 03 : Étanchéité"),
  partieLot("2", "Couverture"), partieLot("Lot 3", true), partieLot("Lot 2 — Couverture", true), partieLot("Démolition"),
  partieLot("Lot unique"), partieLot(""), partieLot(null), partieLot(4)]));""")
    assert r == ["Partie (lot 2)", "Partie (lot 2) — Couverture", "Partie (lot 3) — Étanchéité", "Partie (lot 2) — Couverture",
                 "partie (lot 3)", "partie (lot 2) — Couverture", "Démolition", "Lot unique", "", "", "Partie (lot 4)"]
    assert "partieLot," in _lire("carnet-notes.js") and "partieLot," in _lire("redaction-partenaire.js")


# Un « lot » lu à l'écran est toujours entre parenthèses : « partie (lot 2) », « parties (lots) », « (lot unique) ».
# Une citation du règlement, entre guillemets « … », garde son mot.
LOT_NU = re.compile(r"(?<![\w.\-(])lots?(?![\w\-])", re.I)
# Gardés, avec leur raison (contrat, section A3).
LOT_GARDES = {
    "DPGF du lot - prix de vente HT": "en-tête du fichier remis au chef de file puis à l'acheteur : son vocabulaire",
    "Lot ": "valeur proposée pour la « Part » d'un invité (pmLotPart) : une donnée reprise dans la convention et les "
            "formulaires officiels remis au client, qui gardent le mot du règlement",
}


def _nu(t):
    t = re.sub(r"«[^»]*»", " ", _ATTR_TECHNIQUES.sub(" ", t))
    return bool(LOT_NU.search(t))


def test_aucun_lot_nu_dans_les_textes_lus_a_l_ecran():
    fautes = []
    for f in ("app.html", "invite.html", "landing.html", "demo.html", "demande-acces.html"):
        fautes += [f"{f}:{ln}: {t.strip()[:140]}" for ln, t in textes_html(_lire(f)) if _nu(t) and t.strip() not in LOT_GARDES]
    for f in ("app.js", "redaction-partenaire.js", "carnet-notes.js", "sources-publiques.js", "cotraitance-crypto.js"):
        fautes += [f"{f}:{ln}: {t.strip()[:140]}" for ln, t in textes_js(_lire(f)) if _nu(t) and t not in LOT_GARDES]
    assert not fautes, "\n".join(fautes)


# Espace acheteur (collectivités) : l'acheteur écrit son règlement, « lot » est son mot (allotissement, art. L2113-10).
# Fichiers exportés (remis au client ou au chef de file) : le mot du règlement. Consignes de l'IA : jamais lues.
HORS_ECRAN = ("app/routers/acheteur.py", "app/routers/dce.py", "app/services/dce_", "app/services/infructuosite_scoring.py",
              "app/services/acheteur_demo_seed.py", "app/services/agents/", "app/services/consortium_report.py",
              "app/services/atelier_export.py", "app/services/memoire_export.py", "app/routers/export_dossier.py",
              "app/services/atelier_preparation.py", "app/services/i18n_data.py", "app/services/demo_", "app/routers/cospace.py")


def _messages_serveur(src):
    """Chaînes montrées à l'écran : erreurs (HTTPException, AtelierError, LotsInvalides, CarnetError, ValueError des
    validateurs), valeurs des clés message / detail / label / libelle / titre, constantes MSG_*."""
    arbre = ast.parse(src)
    out = []

    def chaines(n):
        return [(c.lineno, c.value) for c in ast.walk(n) if isinstance(c, ast.Constant) and isinstance(c.value, str)
                and not _CLE.fullmatch(c.value)]
    for n in ast.walk(arbre):
        if isinstance(n, ast.Call):
            f = n.func
            nom = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
            if nom in ("HTTPException", "AtelierError", "LotsInvalides", "CarnetError", "ValueError"):
                for a in list(n.args) + [k.value for k in n.keywords]:
                    out += chaines(a)
        elif isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values):
                if isinstance(k, ast.Constant) and k.value in ("message", "detail", "label", "libelle", "titre"):
                    out += chaines(v)
        elif isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id.startswith(("MSG_", "CRITERIA_LABELS",
                                                                                              "EXPLICATION"))
                                               for t in n.targets):
            out += chaines(n.value)
    return out + textes_courriels(src)


def test_aucun_lot_nu_dans_les_messages_du_serveur():
    fautes = []
    for p in sorted((ROOT / "app").rglob("*.py")):
        rel = str(p.relative_to(ROOT))
        if rel.startswith(HORS_ECRAN):
            continue
        for ln, t in _messages_serveur(p.read_text(encoding="utf-8")):
            if _nu(t):
                fautes.append(f"{rel}:{ln}: {t.strip()[:140]}")
    assert not fautes, "\n".join(fautes)


def test_les_fichiers_exportes_et_les_donnees_gardent_le_mot_du_reglement():
    from app.services import atelier_lots as al
    nom = al.nom_du_lot({"numero": "2", "intitule": "Couverture"}, "Mémoire technique")
    assert nom["stem"] == "Mémoire technique - Lot 2 - Couverture"
    regle = al.nom_du_lot({"numero": "2", "intitule": "C"}, "M", "Ent", {"modele": "Mémoire technique - Nom du candidat"})
    assert regle["stem"] == "Mémoire technique - Ent - Lot 2"                            # le fichier : « Lot 2 »
    assert "Le numéro de la partie (lot) est ajouté au nom : un fichier par partie du marché." in regle["message"]
    # Le libellé d'un lot du dossier reste une donnée (« Lot 2 — … ») : l'écran le dit « Partie (lot 2) — … ».
    assert "pmLotPart(l) { return l && l.num ? \"Lot \" + l.num + \" — \" + l.label" in JS
    assert "partieLot(l.libelle)" in HTML and "partieLot(x.numero, x.intitule)" in HTML
    # L'en-tête du tableau de prix exporté par le partenaire, la ligne « Lot » du fichier.
    crypto = _lire("cotraitance-crypto.js")
    assert '[["DPGF du lot - prix de vente HT"]]' in crypto and 'rows.push(["Lot", csvText(o.lot)])' in crypto


def test_textes_de_la_demo_a_la_voix_d_adjugo_disent_partie():
    """Les analyses de la démo (résumé, recommandation, points d'attention) parlent comme l'écran ; le dossier fictif
    de l'acheteur (règlement, CCTP, tableau de prix) et le fait lu « allotissement » gardent ses mots."""
    fautes = []
    for f in ("demo_search.py", "demo_seed.py", "demo_lots.py"):
        src = (ROOT / "app" / "services" / f).read_text(encoding="utf-8")
        for n in ast.walk(ast.parse(src)):
            vals = []
            if isinstance(n, ast.Dict):
                vals = [v for k, v in zip(n.keys, n.values)
                        if isinstance(k, ast.Constant) and k.value in ("recommandation", "summary", "points_attention",
                                                                        "pourquoi", "levier_negociation")]
            elif isinstance(n, ast.Call):
                f_ = n.func
                nom = f_.attr if isinstance(f_, ast.Attribute) else (f_.id if isinstance(f_, ast.Name) else "")
                vals = [k.value for k in n.keywords if k.arg == "summary"] + (n.args[1:2] if nom == "_analysis" else [])
            for v in vals:
                for c in ast.walk(v):
                    if isinstance(c, ast.Constant) and isinstance(c.value, str) and _nu(c.value):
                        fautes.append(f"{f}:{c.lineno}: {c.value[:120]}")
    assert not fautes, "\n".join(fautes)


# ═══ Traductions (décision 16) ══════════════════════════════════════════════════════════════════════

def test_traductions_des_nouveaux_libelles():
    r = _node("global.window={}; require(process.argv[1]); console.log(JSON.stringify(window.ADJUGO_I18N))",
              str(STATIC / "i18n.js"))
    cles = ["Ce que je cherche", "Tarifs", "Anciennement « Mes critères ».", "Vos tarifs étaient dans l'onglet « Identité ».",
            "Mes métiers", "Ma zone", "Montants", "Montant que je porte seul (€ HT)", "Mes prix de journée",
            "Frais de déplacement", "Date de fin", "Fiscal et social", "Confirmer",
            "Marché en une seule partie (lot unique), ou découpage non précisé : pas de répartition.",
            "Parties couvertes", "Parties (lots)", "Chercher pour cette partie",
            "Ajoutez vos attestations avec leur date de fin : Adjugo vous prévient avant qu'elles expirent."]
    manque = [k for k in cles if not (r["nl"].get(k) and r["es"].get(k))]
    assert not manque, manque
