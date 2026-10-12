"""
Rédaction V2 × lecture intégrale du dossier du marché : l'atelier lit le dossier EN ENTIER.

 • le moteur de l'atelier reçoit TOUS les règlements et TOUS les cadres de réponse en entier (bien
   au-delà des anciens plafonds de 24 000 / 30 000 / 80 000 caractères), en tête et dans un bloc
   mis en cache de prompt identique d'une partie à l'autre, PLUS, pour chaque partie, les passages
   pertinents de toutes les autres pièces (recherche sans IA) — jamais une pièce entière hors sujet ;
 • « Pièces du dossier de l'acheteur lues par Adjugo » dit la couverture honnête : lue en entier,
   en partie, non lue et pourquoi, et ce qui est remis à l'IA ; une ancienne lecture le dit et dit
   comment obtenir la lecture intégrale (« Ré-analyser »), qui est alors prise sans reconstruire le plan ;
 • le dossier de l'acheteur ne prouve jamais rien sur l'entreprise, même par ses passages ;
 • la mesure « fichier de réponse imposé » est posée aussi quand l'analyse se fait en tâche de fond ;
 • les exigences du moteur du savoir-faire (mémoire de groupement) passent par la lecture intégrale ;
 • retouches vues dans le navigateur : texte écrit par l'utilisateur, fenêtres de confirmation de
   l'application, échec gardé dans la partie, bulle (i) du compteur jamais seule à 375 px.
Aucun appel réseau : l'IA est simulée.
"""
import io
import random
import time
import zipfile

import pytest

from app.services import atelier as at
from app.services import llm
from tests.test_redaction_socle0 import NOMS, _company, _db, _user_id, fake_llm  # noqa: F401
from tests.test_redaction_v2_atelier import CADRE, RC, _analysis, _attendre, _creer, _etat, _projet

FILLER = ("alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar papa "
          "quebec romeo sierra tango uniform victor whiskey xray yankee zulu").split()


def _filler(chars: int, seed: int) -> str:
    rnd = random.Random(seed)
    out, n, i = [], 0, 0
    while n < chars:
        i += 1
        ln = f"Paragraphe {i}. " + " ".join(rnd.choice(FILLER) for _ in range(14)) + "."
        out.append(ln)
        n += len(ln) + 1
        if i % 5 == 0:
            out.append("")
    return "\n".join(out)


RC_FIN = "RC-FIN-MARQUEUR : les variantes ne sont pas autorisées."
CADRE_FIN = "CADRE-FIN-MARQUEUR : répondre dans l'ordre des questions."
DECHETS = "DECHETS-MARQUEUR : la gestion des déchets impose 4 bennes de tri sur le site."
HORS_SUJET = "HORSSUJET-MARQUEUR : la peinture de la clôture du stade est reprise en teinte verte."
CCTP_FIN = "CCTPFIN-MARQUEUR"


def _dossier() -> bytes:
    rc = RC + _filler(40000, 1) + "\n" + RC_FIN
    cadre = CADRE + _filler(6000, 2) + "\n" + CADRE_FIN
    cctp = ("CAHIER DES CLAUSES TECHNIQUES PARTICULIERES\n" + _filler(80000, 3) + "\n" + DECHETS + "\n"
            + _filler(40000, 4) + "\n" + HORS_SUJET + "\n" + _filler(40000, 5) + "\n" + CCTP_FIN)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("01_Reglement_de_la_consultation.txt", rc)
        z.writestr("02_Cadre_de_reponse_technique.txt", cadre)
        z.writestr("03_CCTP.txt", cctp)
        z.writestr("04_BPU.doc", b"\xd0\xcf\x11\xe0 ancien format")
    return buf.getvalue()


@pytest.fixture
def analyse_simulee(monkeypatch):
    from app.services import analysis as an

    def fake(text, company=None, criteria=None, lang_name=None, pieces=None, **_lecture):
        return _analysis(text, pieces)
    monkeypatch.setattr(an, "analyze_dce_text", fake)


def _importer(client, h, contenu=None):
    r = client.post("/api/projects/", headers=h, json={"name": "Toiture du groupe scolaire", "client": "Ville de Lorient"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    r = client.post("/api/sourcing/analyze-upload", headers=h, data={"project_id": str(pid)},
                    files={"file": ("DCE.zip", contenu or _dossier(), "application/zip")})
    assert r.status_code == 200, r.text
    return pid


def _appels_rediger(fake):
    return [k for k in fake.calls if "Tu rédiges UNE partie" in llm._flatten_content(k.get("system"))]


def _user(k):
    return llm._flatten_content(k["messages"][0]["content"])


# ═══ 1. Le moteur lit le dossier en entier, et les passages utiles de chaque pièce ═══════════════

def test_l_atelier_lit_reglement_et_cadre_en_entier_et_les_passages_de_toutes_les_pieces(
        client, auth, fake_llm, analyse_simulee):
    h = auth["headers"]
    _company(client, h)
    pid = _importer(client, h)
    st = _creer(client, h, pid)
    assert st["dossier"]["plan_source"] == "cadre" and len(st["sections"]) == 4

    tenants = []

    def ans(kw):
        tenants.append(llm._CURRENT_TENANT.get())
        user = _user(kw)
        if "PARTIE À RÉDIGER : Démarche environnementale" in user:
            return "Nous mettrons en place 4 bennes de tri sur le site.", "end_turn"
        return "Notre organisation suit le chantier au quotidien.", "end_turn"
    fake = fake_llm(ans)
    r = client.post(f"/api/atelier/{pid}/rediger", headers=h, json={})
    assert r.status_code == 202, r.text
    assert _attendre(client, h, pid, r.json()["tache"]["id"])["status"] == "done"
    appels = _appels_rediger(fake)
    assert len(appels) == 4
    owner = _user_id(auth["email"])
    premiers = set()
    for k in appels:
        user = _user(k)
        # Règlement et cadre EN ENTIER (au-delà des anciens plafonds de 24 000, 30 000, 80 000 caractères).
        assert RC_FIN in user and CADRE_FIN in user and "Les entreprises devront être certifiées ISO 14001" in user
        # Jamais le CCTP entier : seulement ses passages utiles à la partie.
        assert CCTP_FIN not in user and HORS_SUJET not in user
        # Note PROPRE à l'atelier (son texte va à l'acheteur) : ce qui est remis en entier (2 pièces), le
        # reste par passages, les pièces non lues pour l'IA seulement ; jamais « dossier lu en entier »
        # ni « écris qu'elle n'a pas été trouvée dans les pièces lues ».
        assert "Ci-dessous, remis à chaque fois : 2 pièces du dossier du marché" in user
        assert "L'autre pièce lue n'est remise que par passages choisis pour chaque partie." in user
        assert "N'affirme jamais qu'une exigence est absente du dossier" in user
        assert "n'y écris jamais de remarque sur la lecture du dossier" in user
        assert "pour toi seulement, à ne jamais mentionner dans le texte" in user and "04_BPU.doc" in user
        assert "[Dossier lu en entier" not in user and "pas été trouvée dans les pièces lues" not in user
        # Le dossier commun vient en tête, marqué pour le cache de prompt, identique d'une partie à l'autre.
        blocs = k["messages"][0]["content"]
        assert isinstance(blocs, list) and blocs[0].get("cache_control") == {"type": "ephemeral"}
        assert blocs[0]["text"].startswith("DOSSIER DE L'ACHETEUR (ne prouve RIEN sur l'entreprise)")
        assert "PARTIE À RÉDIGER" not in blocs[0]["text"]
        premiers.add(blocs[0]["text"])
        for nom in NOMS:
            assert nom not in llm._flatten_content(k.get("system")) + user, f"« {nom} » est parti à l'IA"
    assert len(premiers) == 1
    env = next(_user(k) for k in appels if "PARTIE À RÉDIGER : Démarche environnementale" in _user(k))
    assert DECHETS in env and "Pièce « 03_CCTP.txt »" in env
    assert "PASSAGES DES AUTRES PIÈCES DU DOSSIER DE L'ACHETEUR LES PLUS PROCHES DE CETTE PARTIE" in env
    autre = next(_user(k) for k in appels if "PARTIE À RÉDIGER : Encadrement du chantier" in _user(k))
    assert DECHETS not in autre                                   # la recherche suit la partie
    # Le dossier de l'acheteur ne prouve rien sur l'entreprise, même par ses passages : « 4 bennes » est à relire.
    st = _etat(client, h, pid)
    s = next(x for x in st["sections"] if x["intitule"] == "Démarche environnementale")
    assert any("4" in f["fait"] and f["statut"] == "a_relire" for f in s["version_courante"]["faits"])
    # Le texte intégral n'est pas recopié dans la base du dossier (il reste dans le stockage du marché).
    from app.models import DossierPresentation
    db = _db()
    try:
        d = db.query(DossierPresentation).filter(DossierPresentation.project_id == pid).first()
        assert d.dce_lu["integral"] is True and d.dce_lu["texte"] == "" and RC_FIN not in str(d.dce_lu)
        # Ni le texte du cadre de réponse : seul « le cadre se découpe en questions » est gardé.
        assert d.dce_lu["cadre"] == "" and CADRE_FIN not in str(d.dce_lu) and d.dce_lu["cadre_decoupable"] is True
        # Le coût mesuré compte à part ce qui passe par le cache de prompt (écrit, relu).
        assert {"tokens_cache_ecrits", "tokens_cache_lus"} <= set(d.cout_ia)
    finally:
        db.close()
    assert tenants and all(t == owner for t in tenants)        # espace facturé reposé dans chaque fil


def test_pieces_lues_par_adjugo_couverture_honnete(client, auth, analyse_simulee):
    h = auth["headers"]
    pid = _importer(client, h)
    st = _creer(client, h, pid)
    da = st["dossier_acheteur"]
    assert da["present"] is True and da["integral"] is True and da["message_lecture"] == ""
    assert da["couverture"]["complet"] is False and da["couverture"]["message"].startswith("Dossier lu en partie")
    by = {p["nom"]: p for p in da["pieces"]}
    assert set(by) == {"01_Reglement_de_la_consultation.txt", "02_Cadre_de_reponse_technique.txt", "03_CCTP.txt",
                       "04_BPU.doc"}
    rc, cadre, cctp, doc = (by["01_Reglement_de_la_consultation.txt"], by["02_Cadre_de_reponse_technique.txt"],
                            by["03_CCTP.txt"], by["04_BPU.doc"])
    for p in (rc, cadre):
        assert p["statut"] == "lu_en_entier" and p["lu_en_entier"] is True and p["remise"] == "entiere"
        assert p["remise_libelle"] == "remise en entier à chaque partie" and p["raison"] == ""
    assert cctp["statut"] == "lu_en_entier" and cctp["remise"] == "passages"
    assert cctp["remise_libelle"] == "passages choisis pour chaque partie"
    assert doc["statut"] == "non_lu" and doc["lu_en_entier"] is False and "ancien format Word" in doc["raison"]
    assert doc["remise"] == "" and doc["remise_libelle"] == ""
    # Le même état, relu (GET) : stable, sans relecture du fichier.
    st2 = _etat(client, h, pid)
    assert st2["dossier_acheteur"] == da


def test_reglement_trop_long_remis_en_partie_et_le_reste_cherche():
    from app.services import dce_texte
    payload = {"pieces": [
        {"nom": "RC.txt", "type": "reglement", "texte": "A" * 5000},
        {"nom": "RC modificatif.txt", "type": "reglement", "texte": "B" * 3000},
        {"nom": "Cadre.txt", "type": "cadre", "texte": "C" * 9000},
        {"nom": "CCTP.txt", "type": "cctp", "texte": "D" * 9000}]}
    r = dce_texte.pieces_remises(payload, 12000)
    noms = [(x["nom"], x["entier"]) for x in r["pieces"]]
    # Le modificatif d'abord, puis le RC, en entier ; le cadre n'y tient qu'en partie (son début).
    assert noms == [("RC modificatif.txt", True), ("RC.txt", True), ("Cadre.txt", False)]
    assert r["entiers"] == {0, 1}                       # le cadre coupé reste cherché comme les autres pièces
    assert "Début de la pièce seulement : ses 4000 premiers caractères." in r["texte"]
    assert r["texte"].index("=== RC modificatif.txt ===") < r["texte"].index("=== RC.txt ===")
    assert dce_texte.pieces_remises(payload, 2000)["pieces"] == []      # moins de 4 000 caractères : rien de coupé


# ═══ 2. Ancienne lecture : dite, puis complétée par « Ré-analyser » ══════════════════════════

def test_ancienne_lecture_dite_puis_lecture_integrale_apres_reanalyse(client, auth, fake_llm, analyse_simulee):
    h = auth["headers"]
    pid = _projet(client, h)                       # analysé avant la lecture intégrale (rien de rangé)
    st = _creer(client, h, pid)
    da = st["dossier_acheteur"]
    assert da["integral"] is False and da["message_lecture"] == at.MSG_LECTURE_ANCIENNE
    assert "Ré-analyser" in da["message_lecture"] and da["couverture"] is None
    assert all(p.get("statut") in ("lu_en_entier", "lu_en_partie") for p in da["pieces"])
    r = client.post("/api/sourcing/reanalyze", headers=h, data={"project_id": str(pid)})
    assert r.status_code == 200, r.text
    da = _etat(client, h, pid)["dossier_acheteur"]
    assert da["integral"] is True and da["message_lecture"] == "" and da["a_change"] is False
    assert da["couverture"]["complet"] is True and da["couverture"]["message"].startswith("Dossier lu en entier")
    fake = fake_llm(lambda kw: ("Texte de la partie.", "end_turn"))
    r = client.post(f"/api/atelier/{pid}/sections/{st['sections'][0]['id']}/rediger", headers=h, json={})
    assert _attendre(client, h, pid, r.json()["tache"]["id"])["status"] == "done"
    user = _user(_appels_rediger(fake)[0])
    assert "Ci-dessous, remis à chaque fois : 2 pièces" in user and "=== 01_Reglement_de_la_consultation.txt ===" in user
    assert "[Dossier lu en entier" not in user


def test_lecture_en_cours_dite_honnetement(client, auth):
    from app.models import Job, Project
    from app.services.jobs import create_job
    h = auth["headers"]
    pid = _projet(client, h)
    db = _db()
    try:
        p = db.get(Project, pid)
        j = create_job(db, p.user_id, "lecture_dossier", "Lecture du dossier du marché")
        j.status = "running"
        p.workflow = {"lecture": {"etat": "en_cours", "job_id": j.id}}
        db.commit()
        jid = j.id
    finally:
        db.close()
    st = _creer(client, h, pid)
    assert st["dossier_acheteur"]["message_lecture"] == at.MSG_LECTURE_EN_COURS
    # La lecture échoue (rien n'est rangé) : l'écran ne dit plus « en cours », il dit comment la relancer.
    db = _db()
    try:
        p = db.get(Project, pid)
        p.workflow = {"lecture": {"etat": "erreur", "job_id": jid}}
        db.get(Job, jid).status = "error"
        db.commit()
    finally:
        db.close()
    assert _etat(client, h, pid)["dossier_acheteur"]["message_lecture"] == at.MSG_LECTURE_ANCIENNE


# ═══ 3. Mesure « fichier imposé » aussi en tâche de fond ════════════════════════════════════

def test_mesure_fichier_impose_posee_quand_l_analyse_se_fait_en_tache_de_fond(client, auth, monkeypatch,
                                                                              analyse_simulee):
    from app.models import Project
    from app.routers import sourcing
    monkeypatch.setattr(sourcing, "_needs_background", lambda *a, **k: True)
    h = auth["headers"]
    r = client.post("/api/projects/", headers=h, json={"name": "Gros dossier", "client": "Ville"})
    pid = r.json()["id"]
    r = client.post("/api/sourcing/analyze-upload", headers=h, data={"project_id": str(pid)},
                    files={"file": ("DCE.zip", _dossier(), "application/zip")})
    assert r.status_code == 202 and r.json()["en_cours"] is True, r.text
    t0 = time.time()
    while time.time() - t0 < 60:
        etat = client.get(f"/api/sourcing/lecture/{pid}", headers=h).json()["etat"]
        if etat in ("termine", "erreur"):
            break
        time.sleep(0.1)
    assert etat == "termine"
    db = _db()
    try:
        p = db.get(Project, pid)
        assert p.dce_importe_le is not None and p.dce_fichier_impose is True and p.dce_file_key
    finally:
        db.close()


# ═══ 4. Le moteur du savoir-faire (exigences) passe par la lecture intégrale ══════════════════

def test_exigences_lues_par_la_lecture_integrale_et_plus_coupees_a_24000(client, auth, fake_llm, analyse_simulee):
    from app.models import Project
    from app.services.agents import memoire
    h = auth["headers"]
    pid = _importer(client, h)
    fake = fake_llm(lambda kw: ('{"objet": "Toiture", "criteres_attribution": [], "exigences": []}', "end_turn"))
    db = _db()
    try:
        p = db.get(Project, pid)
        memoire.extract_requirements("", project=p)
    finally:
        db.close()
    user = _user(fake.calls[-1])
    assert RC_FIN in user and CADRE_FIN in user and "jamais qu'elle n'existe pas" in user
    assert CCTP_FIN not in user
    # Sans lecture rangée : le texte fourni, règlement et cadre en tête, le reste partagé (plus de coupe à 24 000).
    texte = "=== CCTP.txt ===\n" + "x " * 30000 + "\n=== RC.txt ===\nREGLEMENT DE LA CONSULTATION\n" + RC_FIN
    out = memoire.texte_pour_exigences(texte)
    assert RC_FIN in out and out.index("=== RC.txt ===") < out.index("=== CCTP.txt ===")


# ═══ 5. Écrans : retouches vues dans le navigateur ════════════════════════════════════════════

def test_ecrans_texte_ecrit_par_vous_confirmations_echec_garde_et_bulle_du_compteur():
    from tests.test_redaction_v2_ecrans import ATELIER, JS_METH, _sans_commentaires_html
    a = _sans_commentaires_html(ATELIER)
    # (a) Texte écrit par l'utilisateur : ses faits sont ses déclarations, jamais « aucun fait signalé ».
    phrase = "Texte écrit par vous : vos chiffres et noms sont vos déclarations. Adjugo signale les faits ajoutés par l'IA."
    assert phrase in a
    i = a.index(phrase)
    assert "atlSec().version_courante.origine === 'utilisateur'" in a[i - 300:i]
    assert a.index(phrase) < a.index("Aucun fait signalé dans ce texte")
    # (b) Aucune confirmation native dans l'atelier : la fenêtre de l'application (comme « Marquer déposé »).
    assert "confirm(" not in JS_METH
    for fn in ("atlRetirerPartie(s) {", "atlEditCancel() {", "atlValider() {", "atlRestaurer(v) {",
               "_atlAvantLancer(title, ok, lines, go) {"):
        corps = JS_METH[JS_METH.index(fn):JS_METH.index(fn) + 900]
        assert "this._convAsk(" in corps, fn
    # (c) Échec d'une rédaction : gardé DANS la partie jusqu'à la prochaine action sur elle.
    # (avec la même marge que le verrou de rédaction placé au même endroit : jamais collé au-dessus).
    assert 'v-else-if="atlEchec(atlSec())" class="conv-err atl-mt12" role="alert"' in a
    assert "this._atlEchecNoter(j.pid, j.ids, msg)" in JS_METH and "this._atlEchecNoter(j.pid, ko," in JS_METH
    for fn in ("_atlLancer(path, body, action) {", "atlEdit() {", "atlSave() {", "_atlValider(s, v) {", "atlRelu() {",
               "atlFait(f, statut) {", "_atlRestaurer(s, v) {", "_atlRetirer(s) {"):
        corps = JS_METH[JS_METH.index(fn):JS_METH.index(fn) + 700]
        assert "_atlEchecOublier(" in corps, fn
    # (d) Bulle (i) du compteur : collée au dernier mot, jamais seule sur sa ligne.
    assert ('<span class="atl-nowrap">{{ atlNum(atl.st.compteur.total.pages) }} page{{ atl.st.compteur.total.pages > 1 '
            "? 's' : '' }}<button v-if=\"atl.st.compteur.message\" type=\"button\" class=\"tip\">") in a
    assert a.count("Comment c'est compté") == 1
    # Couverture de la lecture : statut, raison, ce qui est remis à l'IA, et ce qui manque hors de la liste.
    assert "atlPieceLecture(p)" in a and "p.raison" in a and "p.remise_libelle" in a
    assert "atlCouvertureManque(atl.st)" in a
    assert "les passages des autres pièces du dossier les plus proches de la partie" in a


def test_lecture_d_une_piece_et_ce_qui_manque_sous_node():
    from tests.test_redaction_v2_ecrans import _node
    r = _node("console.log(JSON.stringify({"
              "e: atlLecturePiece({statut: 'lu_en_entier', pages: 12}), e1: atlLecturePiece({statut: 'lu_en_entier', pages: 1}),"
              "p: atlLecturePiece({statut: 'lu_en_partie'}), n: atlLecturePiece({statut: 'non_lu'}),"
              "ancien: atlLecturePiece({lu_en_entier: true}), rien: atlLecturePiece(null),"
              "m1: atlManqueLecture({present: true, message_lecture: 'Ancienne lecture.'}),"
              "m2: atlManqueLecture({present: true, couverture: {complet: false, message: 'Dossier lu en partie.'}}),"
              "m3: atlManqueLecture({present: true, couverture: {complet: true, message: 'Dossier lu en entier.'}}),"
              "m4: atlManqueLecture({present: false, message_lecture: 'x'})}));")
    assert r == {"e": "lue en entier (12 pages)", "e1": "lue en entier (1 page)", "p": "lue en partie",
                 "n": "non lue", "ancien": "lue en entier", "rien": "", "m1": "Ancienne lecture.",
                 "m2": "Dossier lu en partie.", "m3": "", "m4": ""}
