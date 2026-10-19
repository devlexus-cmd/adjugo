"""
Rédaction, vague 4 — documents privés déposés par le lien (décision 5 a) : contre-relecture (contrat
docs/REDACTION_V4_GROUPEMENT.md § 21.14). Chaque test reproduit une remarque des relectures ; tous échouaient sur
1a9f2f4.

 • ce que les brouillons ont recopié d'un document (nom réel, passage exact) part avec lui : purge automatique,
   réinitialisation, retrait (aucun reste dans aucune table, aucun fichier) ;
 • courses : l'espace réinitialisé pendant l'aide de l'IA ne reçoit pas le brouillon ; réinitialisé pendant la lecture
   d'un dépôt, il ne reçoit pas le document ; un document supprimé pendant l'aide n'y laisse ni son nom ni son passage ;
 • le journal du marché (lu par le chef de file) ne donne pas le rang des dépôts ;
 • noms de personnes des documents déposés (sans équipe connue) masqués avant l'IA dans les tournures courantes,
   et l'écran ne promet plus un masquage complet ;
 • un CV sans le mot « CV » (nom, puis « EXPÉRIENCE », « FORMATION », « COMPÉTENCES »…) est refusé ; un CV inséré
   dans un mémoire en est retiré ; une plaquette n'est pas prise pour un CV ;
 • l'écran dit que réinitialiser efface aussi les documents, et combien de temps ils sont gardés (expiration du
   lien comprise) ; de nouvelles conditions publiées pendant que la page est ouverte font apparaître les cases.
Aucun appel réseau : le client IA est simulé.
"""
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.services import atelier_groupement as ag
from app.services import depot_lien as dl
from app.services import fiches_import as fi
from tests.test_redaction_socle0 import _db, fake_llm  # noqa: F401
from tests.test_redaction_v4_depot_lien import _deposer, _deposer_ok, _docx, _pdf, _sans_expiration
from tests.test_redaction_v4_groupement import P, _aide, _groupement, _part_a, _reponse_partenaire

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXTE_IA = "Nous trions les déchets amiantés dans 6 big-bags étanches [S1]. [À compléter : planning des évacuations]"


def _memoire(secret: str) -> str:
    return ("Mémoire technique : désamiantage du collège Brizeux (2024)\n\n"
            "Démarche environnementale et gestion des déchets du chantier : nous trions les déchets amiantés dans "
            f"6 big-bags étanches, évacués vers une installation de stockage agréée. {secret}\n\n"
            "Conductrice de travaux : Anne Le Floch.\n")


def _secret() -> str:
    return "SEC" + uuid.uuid4().hex[:10].upper()


def _partout(*secrets) -> list:
    """Chaque table où l'un des secrets apparaît encore : [(table, secret)]."""
    from app.core.database import Base, engine
    out = set()
    with engine.connect() as cx:
        for t in Base.metadata.sorted_tables:
            try:
                rows = cx.execute(select(t)).fetchall()
            except Exception:       # noqa: BLE001 — table absente de cette base
                continue
            for r in rows:
                s = repr(tuple(r))
                for x in secrets:
                    if x in s:
                        out.add((t.name, x))
    return sorted(out)


def _fichiers(invite_id) -> list:
    from app.services.storage import UPLOAD_DIR
    d = os.path.join(UPLOAD_DIR, "invitations", str(invite_id), "depots")
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


def _attendre_tache(jid):
    from app.models import Job
    for _ in range(400):
        db = _db()
        try:
            j = db.get(Job, jid)
            if j.status in ("done", "error"):
                return j.status, dict(j.result or {})
        finally:
            db.close()
        time.sleep(0.05)
    raise AssertionError("tâche jamais terminée")


def _brouillons(invite_id) -> list:
    from app.models import DossierPartBrouillon
    db = _db()
    try:
        return [{"sources": b.sources, "faits": b.faits, "texte": b.texte}
                for b in db.query(DossierPartBrouillon).filter(DossierPartBrouillon.invite_id == invite_id)]
    finally:
        db.close()


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


# ═══ 1. Ce que les brouillons ont recopié part avec le document (purge, réinitialisation, retrait) ═══

def test_purge_6_mois_efface_aussi_ce_que_les_brouillons_ont_recopie(client, auth, fake_llm, monkeypatch):
    monkeypatch.setenv("ATELIER_LIBELLES_SOURCES", "1")
    h = auth["headers"]
    secret = _secret()
    nom = f"Memoire-{secret}.txt"
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    fake_llm(_reponse_partenaire(TEXTE_IA)[0])
    sid = _part_a(vue)["section_id"]
    _sans_expiration(a["id"])                      # lien sans expiration : seule la règle des 6 mois joue
    pa = P(client, a["token"])
    _deposer_ok(pa, nom, _memoire(secret))
    assert _aide(pa, sid)[0]["status"] == "done"
    avant = json.dumps(_brouillons(a["id"]), ensure_ascii=False)
    assert nom in avant and secret in avant        # contrôle : le brouillon cite bien le document et son passage
    assert client.put(f"/api/projects/{pid}", headers=h, json={"status": "perdu"}).status_code == 200
    from app.models import DepotLienEspace
    db = _db()
    try:
        dl.purger(db, datetime.now(timezone.utc))
        resultat = db.query(DepotLienEspace).filter(DepotLienEspace.invite_id == a["id"]).one().resultat_le
        res = dl.purger(db, dl.plus_mois(resultat, 6) + timedelta(hours=1))
    finally:
        db.close()
    assert res["documents_partenaires_effaces"] >= 1
    assert _partout(secret) == [] and _fichiers(a["id"]) == []
    bro = _brouillons(a["id"])
    assert bro and nom not in json.dumps(bro, ensure_ascii=False)
    faits = [f for x in bro for f in (x["faits"] or []) if str(f.get("fait", "")).startswith("6")]
    assert faits and all(f["statut"] != "avec_source" and not f.get("source") for f in faits)
    # L'écran du partenaire : ni le nom, ni le passage, le fait est « à relire ».
    v = pa.get(f"/sections/{sid}")
    assert v.status_code == 200 and nom not in v.text and secret not in v.text


def test_reinitialisation_et_retrait_ne_laissent_rien_non_plus(client, auth, fake_llm, monkeypatch):
    monkeypatch.setenv("ATELIER_LIBELLES_SOURCES", "1")
    for mode in ("reinit", "retrait"):
        secret = _secret()
        pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
        fake_llm(_reponse_partenaire(TEXTE_IA)[0])
        sid = _part_a(vue)["section_id"]
        pa = P(client, a["token"])
        _deposer_ok(pa, f"Memoire-{secret}.txt", _memoire(secret))
        assert _aide(pa, sid)[0]["status"] == "done" and _partout(secret)
        if mode == "reinit":
            assert client.post(f"/api/invite/{a['token']}/redaction/espace", json={"reinitialiser": True}).status_code == 200
        else:
            assert client.delete(f"/api/projects/{pid}/invites/{a['id']}", headers=auth["headers"]).status_code == 200
        assert _partout(secret) == [] and _fichiers(a["id"]) == [], mode


# ═══ 2. Courses ═══════════════════════════════════════════════════════════════════════

def test_reinitialisation_pendant_l_aide_ne_range_rien_dans_le_nouvel_espace(client, auth, fake_llm, monkeypatch):
    """Celui qui détient le lien (le chef de file, par exemple) réinitialise l'espace pendant l'appel à l'IA : il ne
    lit ni le brouillon, ni le nom du document, ni son passage, avec sa nouvelle clé."""
    monkeypatch.setenv("ATELIER_LIBELLES_SOURCES", "1")
    secret = _secret()
    nom = f"Memoire-{secret}.txt"
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])
    _deposer_ok(pa, nom, _memoire(secret))
    chef = {}

    def ans(kw):
        if not chef:
            r = client.post(f"/api/invite/{a['token']}/redaction/espace", json={"reinitialiser": True})
            assert r.status_code == 200, r.text
            chef.update(cle=r.json()["cle"], docs=r.json()["documents_effaces"])
        return TEXTE_IA, "end_turn"
    fake = fake_llm(ans)
    r = pa.post(f"/sections/{sid}/aide", {})
    assert r.status_code == 202, r.text
    statut, res = _attendre_tache(r.json()["tache"]["id"])
    assert len(fake.calls) == 1 and chef["docs"] == 1
    assert statut == "done" and res["sections"][0]["ok"] is False
    assert res["message"] == ag.MSG_AIDE_ESPACE_REINITIALISE
    hc = {ag.ENTETE_CLE: chef["cle"]}
    s = client.get(f"/api/invite/{a['token']}/redaction/sections/{sid}", headers=hc)
    assert s.status_code == 200 and s.json().get("brouillon") is None
    assert nom not in s.text and secret not in s.text
    ex = client.get(f"/api/invite/{a['token']}/redaction/export", headers=hc)
    assert ex.status_code == 200 and nom not in ex.text and secret not in ex.text
    assert _partout(secret) == [] and _brouillons(a["id"]) == []
    # La partie est libérée : le nouvel espace peut relancer l'aide.
    v = client.get(f"/api/invite/{a['token']}/redaction", headers=hc).json()
    assert all(not (p.get("aide") or {}).get("en_cours") for p in v["parties"])


def test_rouvrir_avec_le_code_pendant_l_aide_garde_le_brouillon(client, auth, fake_llm, monkeypatch):
    """Rouvrir son espace sur un autre appareil avec le code reçu par email (brouillons gardés) n'est pas une
    réinitialisation : le brouillon de l'aide en cours est rangé, et se lit avec la nouvelle clé."""
    import app.routers.invites as invites
    from app.models import ProjectInvite
    secret = _secret()
    nom = f"Memoire-{secret}.txt"
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])
    _deposer_ok(pa, nom, _memoire(secret))
    autre = {}

    def ans(kw):
        if not autre:
            db = _db()
            try:
                inv = db.get(ProjectInvite, a["id"])
                inv.otp_hash = invites._hash_otp("123456")
                inv.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
                inv.otp_attempts = 0
                db.commit()
            finally:
                db.close()
            monkeypatch.setattr(invites, "_binding_required", lambda inv: True)
            r = client.post(f"/api/invite/{a['token']}/redaction/espace", json={"code": "123456"})
            assert r.status_code == 200 and r.json()["brouillons_effaces"] == 0, r.text
            autre["cle"] = r.json()["cle"]
        return TEXTE_IA, "end_turn"
    fake_llm(ans)
    r = pa.post(f"/sections/{sid}/aide", {})
    assert r.status_code == 202, r.text
    statut, res = _attendre_tache(r.json()["tache"]["id"])
    assert statut == "done" and res["sections"][0]["ok"] is True, res
    s = client.get(f"/api/invite/{a['token']}/redaction/sections/{sid}", headers={ag.ENTETE_CLE: autre["cle"]})
    br = s.json()["brouillon"]
    assert br is not None and any(x.get("doc_name") == nom for x in br["sources"])


def test_reinitialisation_avant_le_debut_de_l_aide_rend_tout(client, auth, fake_llm, monkeypatch):
    """La tâche n'a pas encore démarré quand l'espace est réinitialisé : l'IA n'est jamais appelée, l'aide est rendue
    et rien n'est débité."""
    import app.services.jobs as jobs
    from tests.test_redaction_v4_groupement import _dossier_db, _trial
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])
    _deposer_ok(pa, "Memoire.txt", _memoire(_secret()))
    fake = fake_llm(_reponse_partenaire(TEXTE_IA)[0])
    t0 = _trial(auth["email"])
    vrai, gardee = jobs.run_in_thread, {}
    monkeypatch.setattr(jobs, "run_in_thread", lambda *a_, **k: gardee.update(a=a_, k=k))
    r = pa.post(f"/sections/{sid}/aide", {})
    assert r.status_code == 202, r.text
    rr = client.post(f"/api/invite/{a['token']}/redaction/espace", json={"reinitialiser": True})
    assert rr.status_code == 200
    vrai(*gardee["a"], **gardee["k"])
    statut, _res = _attendre_tache(r.json()["tache"]["id"])
    assert statut == "error" and fake.calls == []
    assert _trial(auth["email"]) == t0 and _dossier_db(pid)["analyse_debitee"] is False
    v = client.get(f"/api/invite/{a['token']}/redaction/sections/{sid}", headers={ag.ENTETE_CLE: rr.json()["cle"]}).json()
    assert v["aide"]["utilisees"] == 0 and v["brouillon"] is None and not v["aide"].get("en_cours")


def test_reinitialisation_pendant_un_depot_ne_garde_rien(client, auth, monkeypatch):
    secret = _secret()
    nom = f"Memoire-LENT-{secret}.txt"
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    pa = P(client, a["token"])
    lire = dl.lire
    chef = {}

    def lente(n, contenu, ext):
        out = lire(n, contenu, ext)
        if "LENT" in n and not chef:
            # Pendant la lecture (un scan peut durer), qui détient le lien réinitialise l'espace.
            from app.models import ProjectInvite
            db = _db()
            try:
                chef["cle"] = ag.ouvrir_espace(db, db.get(ProjectInvite, a["id"]), reinitialiser=True)["cle"]
            finally:
                db.close()
        return out
    monkeypatch.setattr(dl, "lire", lente)
    r = _deposer(pa, nom, _memoire(secret))
    assert chef.get("cle")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "espace_reinitialise", r.text
    assert r.json()["detail"]["message"] == dl.MSG_ESPACE_REINITIALISE
    from app.models import DepotLienDocument, DepotLienMorceau
    db = _db()
    try:
        assert db.query(DepotLienDocument).filter(DepotLienDocument.invite_id == a["id"]).count() == 0
        assert db.query(DepotLienMorceau).filter(DepotLienMorceau.invite_id == a["id"]).count() == 0
    finally:
        db.close()
    assert _fichiers(a["id"]) == [] and _partout(secret) == []
    hc = {ag.ENTETE_CLE: chef["cle"]}
    lst = client.get(f"/api/invite/{a['token']}/redaction/documents", headers=hc).json()
    assert lst["documents"] == [] and lst["conditions"]["a_accepter"] is True


def test_document_supprime_pendant_l_aide_ne_laisse_ni_nom_ni_passage(client, auth, fake_llm, monkeypatch):
    monkeypatch.setenv("ATELIER_LIBELLES_SOURCES", "1")
    secret, autre = _secret(), _secret()
    nom = f"Memoire-{secret}.txt"
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])
    did = _deposer_ok(pa, nom, _memoire(secret))["depose"]["id"]
    # Un second document, gardé : ses passages et son renvoi restent (le renvoi de sa place ne bouge pas).
    _deposer_ok(pa, "Plaquette.txt", "Plaquette : gestion des déchets du chantier de désamiantage, big-bags "
                                     f"étanches et bordereaux de suivi des déchets amiantés. {autre}\n")
    cle = pa.h[ag.ENTETE_CLE]
    fait = {}

    def ans(kw):
        if not fait:
            from app.models import Project, ProjectInvite
            db = _db()
            try:
                inv = db.get(ProjectInvite, a["id"])
                acc = ag.acces_partenaire(db, inv, db.get(Project, inv.project_id), mode="lien", cle=cle)
                fait["n"] = dl.supprimer(db, acc, did)
            finally:
                db.close()
        return ("Nous trions les déchets amiantés dans 6 big-bags étanches [S1]. Chaque évacuation est tracée par "
                "bordereau [S2]."), "end_turn"
    fake_llm(ans)
    job, _ = _aide(pa, sid)
    assert job["status"] == "done" and fait.get("n") == 1
    br = pa.get(f"/sections/{sid}").json()["brouillon"]
    assert nom not in json.dumps(br, ensure_ascii=False) and secret not in json.dumps(br, ensure_ascii=False)
    assert all(s.get("doc_name") != nom for s in br["sources"])
    assert _partout(secret) == []
    # Le passage encore présent garde sa source réelle.
    sources = {s["ref"]: s for s in br["sources"]}
    assert all(s.get("doc_name") == "Plaquette.txt" for s in sources.values())


# ═══ 3. Le journal du marché ne donne pas le rang des dépôts ═════════════════════════════

def test_journal_du_marche_sans_rang_ni_taille(client, auth):
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    pa = P(client, a["token"])
    _deposer_ok(pa, "Memoire.txt", _memoire(_secret()))
    _deposer_ok(pa, "Plaquette.txt", "Plaquette : notre entreprise intervient en Bretagne, désamiantage des "
                                     "bâtiments publics et gestion des déchets du chantier.\n" * 2)
    au = [x for x in client.get(f"/api/projects/{pid}/audit", headers=h).json() if x["action"] == "redaction.document_depose"]
    assert len(au) == 2
    assert all(x["detail"] == "Document déposé dans l'espace privé du partenaire, lu sans IA" for x in au)
    assert not any(" sur " in x["detail"] for x in au)


# ═══ 4. Noms de personnes d'un document déposé (aucune équipe connue) ═══════════════════

NOMS = ("Yann Tanguy", "Gwenola Riou", "Loïc Cadiou", "Pierre Martin", "Jean-Marc Riou", "Sophie Bernard",
        "Thomas Le Bihan")
DOC_NOMS = ("Plaquette de présentation\n\n"
            "Fondée en 2009 par Pierre Martin, notre entreprise trie les déchets du chantier.\n\n"
            "Notre gérant Pierre Martin et son associée Sophie Bernard pilotent la démarche environnementale.\n\n"
            "Jean-Marc Riou pilote nos chantiers de désamiantage et la gestion des déchets amiantés.\n\n"
            "Notre conducteur de travaux Yann Tanguy suit chaque chantier et la gestion des déchets du chantier.\n\n"
            "Le tri des déchets du chantier est assuré par Gwenola Riou et Loïc Cadiou, avec 6 big-bags étanches.\n\n"
            "Avec Thomas Le Bihan, responsable environnement, nous valorisons 80 % des déchets du chantier.\n")


def test_noms_d_un_document_depose_masques_avant_l_ia(client, auth, fake_llm):
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    fake = fake_llm(_reponse_partenaire("Nous trions les déchets amiantés dans 6 big-bags étanches [S1].")[0])
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])
    _deposer_ok(pa, "plaquette.txt", DOC_NOMS)
    assert _aide(pa, sid)[0]["status"] == "done"
    sent = fake.sent()
    assert "6 big-bags" in sent and "80 %" in sent                 # le passage part, sans les noms
    fuites = [n for n in NOMS if n in sent]
    assert fuites == [], fuites
    assert "Avec [Personne" in sent                 # « Avec » reste lu : seul le nom qui le suit est masqué
    # Les mots qui ne sont pas des noms restent lus par l'IA (rien de masqué en trop).
    for mot in ("Plaquette de présentation", "Notre gérant", "démarche environnementale", "responsable environnement"):
        assert mot in sent, mot


def test_reperage_des_noms_tournures_courantes_et_lieux():
    # Sans prénom connu (tout parcours) : la fonction, « par … », une suite « X et Y », « X, notre gérant ».
    assert fi.noms_probables("Notre gérant Pierre Martin pilote la démarche.") == ["Pierre Martin"]
    assert fi.noms_probables("Pierre Martin, notre gérant, pilote la démarche.") == ["Pierre Martin"]
    assert fi.noms_probables("Fondée en 2009 par Pierre Martin, notre entreprise trie.") == ["Pierre Martin"]
    assert fi.noms_probables("Créée par Pierre Martin et Sophie Bernard en 2009.") == ["Pierre Martin", "Sophie Bernard"]
    assert fi.noms_probables("Le tri est assuré par Gwenola Riou et Loïc Cadiou.") == ["Gwenola Riou", "Loïc Cadiou"]
    assert fi.noms_probables("Interlocuteur unique Pierre Martin (06 12 34 56 78).") == ["Pierre Martin"]
    assert fi.noms_probables("Notre conducteur de travaux Yann Tanguy suit le chantier.") == ["Yann Tanguy"]
    assert fi.noms_probables("Avec Thomas Le Bihan, responsable environnement, nous trions.") == ["Thomas Le Bihan"]
    # Par le lien, sans équipe connue : un prénom courant suffit (« X et Y dirigent », en tête de phrase).
    assert fi.noms_probables("Pierre Martin et Sophie Bernard dirigent l'entreprise.", etendu=True) == [
        "Pierre Martin", "Sophie Bernard"]
    assert fi.noms_probables("Jean-Marc Riou pilote nos chantiers.", etendu=True) == ["Jean-Marc Riou"]
    assert fi.noms_probables("Contact Sophie Bernard, 06 12 34 56 78.", etendu=True) == ["Sophie Bernard"]
    assert fi.noms_probables("TANGUY Yann, conducteur.", etendu=True) == ["TANGUY Yann"]
    assert fi.noms_probables("Notre interlocuteur est Pierre Martin.", etendu=True) == ["Pierre Martin"]
    # Jamais un lieu, un établissement ni l'entreprise.
    lieux = ("Rénovation de l'école Jules Ferry et du collège Jean Moulin, rue Victor Hugo à Quimper. Groupe scolaire "
             "Marie Curie. Département du Finistère. Breizh Couverture. Gestion Des Déchets.")
    assert fi.noms_probables(lieux, etendu=True) == []
    # Ce qui était repéré l'est toujours (vague 3).
    assert fi.noms_probables("| Jean-Yves Le Goff | Chef de chantier | 15 ans |") == ["Jean-Yves Le Goff"]
    assert fi.noms_probables("| Mairie de Quimper | 2024 |\n| Nacelle articulée | 2 |\nAcheteur : Mairie de Brest.") == []


def test_l_ecran_ne_promet_plus_un_masquage_complet():
    js = _read("app/static/redaction-partenaire.js")
    a_valider = _read("docs/A_VALIDER_depot_documents_par_lien.md")
    for texte in (dl.MSG_USAGE, js):
        assert "Les noms des personnes sont masqués avant l'IA" not in texte
        assert "un CV n'est jamais envoyé" not in texte
    assert "masque les noms de personnes qu'il repère" in dl.MSG_USAGE
    assert "masque les noms de personnes qu'il repère" in js
    assert "noms des personnes remplacés par des étiquettes avant tout envoi ; jamais un curriculum" not in a_valider
    assert "qu'Adjugo repère" in a_valider


# ═══ 5. Un CV sans le mot « CV » ═══════════════════════════════════════════════════════

CV_LIGNES = ["Yann TANGUY", "Conducteur de travaux désamiantage", "06 12 34 56 78 - yann.tanguy@mail.fr",
             "EXPÉRIENCE", "2015 - 2024 : Conducteur de travaux, Breizh Désamiantage",
             "Gestion des déchets du chantier amiantés, démarche environnementale.",
             "FORMATION", "2012 : BTS Travaux publics", "COMPÉTENCES",
             "SS3, SS4, gestion des déchets du chantier, tri sélectif."]
CV_PARCOURS = ("Anne Le Floch\nCheffe de chantier\n\nParcours\n2018-2024 Cheffe de chantier désamiantage chez Breizh "
               "Désamiantage (Quimper)\n2012-2018 Opératrice SS4 chez Armor Dépollution\n\nFormation\nCAP maçonnerie "
               "(2011)\nSS3 encadrement (2018)\n\nAtouts\nRigueur, sens de la sécurité, gestion des déchets du "
               "chantier.\n")


def test_cv_sans_le_mot_cv_refuse_en_pdf_word_et_texte(client, auth, fake_llm):
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    fake = fake_llm(_reponse_partenaire(TEXTE_IA)[0])
    pa = P(client, a["token"])
    for nom, contenu in (("Yann_Tanguy.pdf", _pdf(CV_LIGNES)), ("Yann_Tanguy.docx", _docx(CV_LIGNES)),
                         ("document_1.pdf", _pdf(CV_LIGNES)), ("presentation.txt", CV_PARCOURS)):
        r = _deposer(pa, nom, contenu)
        assert r.status_code == 422 and r.json()["detail"]["code"] == "document_cv", (nom, r.text)
    from app.models import DepotLienDocument
    db = _db()
    try:
        assert db.query(DepotLienDocument).filter(DepotLienDocument.invite_id == a["id"]).count() == 0
    finally:
        db.close()
    assert fake.calls == []


def test_cv_insere_dans_un_memoire_retire_et_plaquette_gardee(client, auth, fake_llm):
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    fake = fake_llm(_reponse_partenaire(TEXTE_IA)[0])
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])
    memoire = ("Mémoire technique\n\nDémarche environnementale : nous trions les déchets amiantés dans 6 big-bags "
               "étanches, évacués vers une installation agréée. Chaque évacuation est tracée par bordereau de suivi "
               "des déchets amiantés.\n\nOrganisation du chantier : confinement de la zone, sas de décontamination à "
               "trois compartiments, mesures d'empoussièrement avant, pendant et après les travaux.\n\n"
               "Erwan Kerhervé\nConducteur de travaux\nExpérience\n2015-2024 conducteur de travaux en désamiantage\n"
               "Formation\nBTS travaux publics (2012)\n\nPlanning\nLes travaux durent 6 semaines, évacuations "
               "hebdomadaires des déchets du chantier.\n")
    d = _deposer_ok(pa, "Memoire 2023.txt", memoire)["depose"]
    assert d["passages_cv_retires"] is True
    from app.models import DepotLienMorceau
    db = _db()
    try:
        textes = " ".join(m.texte for m in db.query(DepotLienMorceau).filter(DepotLienMorceau.invite_id == a["id"]))
    finally:
        db.close()
    assert "Kerhervé" not in textes and "BTS travaux publics" not in textes
    assert "6 big-bags" in textes and "évacuations hebdomadaires" in textes
    # Une plaquette avec des rubriques « Compétences » et « Formations » sous le nom de l'entreprise : gardée entière.
    plaquette = ("Breizh Désamiantage\n02 98 00 00 00 - contact@breizh.fr\n\nCompétences\nDésamiantage SS3, déplombage, "
                 "gestion des déchets du chantier.\n\nFormations\nNos opérateurs sont formés chaque année.\n\n"
                 "Références\nCollège Brizeux (2024).\n")
    d = _deposer_ok(pa, "Plaquette.txt", plaquette)["depose"]
    assert d["passages_cv_retires"] is False
    assert _aide(pa, sid)[0]["status"] == "done"
    sent = fake.sent()
    assert "Kerhervé" not in sent and "BTS travaux publics" not in sent and "Nos opérateurs sont formés" in sent


def test_reperage_du_cv_sans_titre_fonctions_pures():
    assert fi.est_cv(dl._Doc("document_neutre.pdf", "\n".join(CV_LIGNES)))
    assert fi.est_cv(dl._Doc("document_neutre.txt", CV_PARCOURS))
    # Une fiche d'une personne écrite en phrases, sans rubriques, n'est pas un CV (elle reste lue, noms masqués).
    fiche = ("Fiche individuelle — Jean-Yves Le Goff, chef de chantier\n15 ans d'expérience en désamiantage. "
             "Habilitations : SS3, SS4. Il assure la gestion des déchets du chantier.\n")
    assert not fi.est_cv(dl._Doc("fiche.txt", fiche))
    # Un nom d'entreprise en tête, suivi de rubriques : pas une personne, pas un CV.
    assert not fi.est_cv(dl._Doc("x.txt", "Armor Dépollution\n\nCompétences\nDésamiantage.\n\nFormations\nSS3.\n"))


# ═══ 6. Écran : réinitialiser, durée de conservation, nouvelles conditions ═══════════════

def test_reinitialiser_dit_que_les_documents_deposes_partent():
    js = _read("app/static/redaction-partenaire.js")
    i = js.index('title: "Réinitialiser votre espace privé ?"')
    fenetre = js[i:js.index("});", i)]
    assert "vos documents déposés pour Adjugo seront <b>effacés</b>" in fenetre
    k = js.index("Vous pouvez le réinitialiser ici")
    assert "vos documents déposés pour Adjugo seront effacés" in js[k:k + 160]
    for msg in (ag.MSG_ESPACE_OUVERT, ag.MSG_RATTACHER_ESPACE):
        assert "vos documents déposés pour Adjugo seront alors effacés" in msg, msg


def test_duree_de_conservation_dit_l_expiration_du_lien(client, auth):
    from app.models import ProjectInvite
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    pa = P(client, a["token"])
    assert _deposer(pa, "Memoire.txt", _memoire(_secret())).status_code == 201
    db = _db()
    try:
        exp = db.get(ProjectInvite, a["id"]).expires_at
    finally:
        db.close()
    assert exp is not None                         # lien par défaut : il expire
    txt = pa.get("/documents").json()["conservation"]
    assert "30 jours après l'expiration de ce lien" in txt and dl._jour_fr(exp) in txt
    assert "6 mois après le résultat du marché" in txt and "date limite" in txt and "dernier dépôt" in txt
    # C'est bien la règle appliquée : la purge efface 30 jours après l'expiration.
    from app.models import DepotLienDocument
    db = _db()
    try:
        dl.purger(db, exp + timedelta(days=29))
        assert db.query(DepotLienDocument).filter(DepotLienDocument.invite_id == a["id"]).count() == 1
        dl.purger(db, exp + timedelta(days=31))
        assert db.query(DepotLienDocument).filter(DepotLienDocument.invite_id == a["id"]).count() == 0
    finally:
        db.close()
    # Lien sans expiration : la phrase n'en parle pas.
    pid2, st2, c, d, vue2 = _groupement(client, auth, avec_b=False)
    _sans_expiration(c["id"])
    pc = P(client, c["token"])
    assert "expiration" not in pc.get("/documents").json()["conservation"]


def test_nouvelles_conditions_page_ouverte_font_apparaitre_les_cases(client, auth, monkeypatch):
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    pa = P(client, a["token"])
    _deposer_ok(pa, "Memoire.txt", _memoire(_secret()))
    # Une nouvelle version de la politique est publiée pendant que la page est ouverte.
    vrais = dl.textes_juridiques()
    monkeypatch.setattr(dl, "textes_juridiques",
                        lambda: [dict(t, version="9.9") if t["cle"] == "confidentialite" else t for t in vrais])
    r = _deposer(pa, "Plaquette.txt", "Plaquette : désamiantage et gestion des déchets du chantier en Bretagne.\n",
                 accepte=False)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "conditions_a_accepter"
    cond = r.json()["detail"]["conditions"]
    assert cond["a_accepter"] is True and {t["cle"] for t in cond["textes"]} == {"cgu", "confidentialite"}
    # L'écran recopie ces conditions pour dessiner les deux cases (sans recharger la page).
    js = _read("app/static/redaction-partenaire.js")
    i = js.index("async function deposerDoc")
    corps = js[i:js.index("async function telechargerDoc")]
    assert 'r.code === "conditions_a_accepter"' in corps and "r.data.detail.conditions" in corps
    assert "conditions: dc" in corps and "render();" in corps
