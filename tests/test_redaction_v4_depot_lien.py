"""
Rédaction, vague 4 — décision 5, option a (validée par Eliot) : un partenaire venu par LIEN MAGIQUE (sans compte)
dépose des documents PRIVÉS pour que l'aide d'Adjugo rédige SES parties. Contrat : docs/REDACTION_V4_GROUPEMENT.md
§ 21 ; règles : app/services/depot_lien.py.

Invariants vérifiés :
 • cloisonnement : le chef de file (même avec le lien), un membre de son organisation, un autre partenaire et la
   démo reçoivent 403 ou 404 sur chaque route ; rien dans leurs écrans, leurs exports, leur coffre, « Mes
   documents », l'export ZIP du dossier, l'export RGPD du chef de file, ni le journal (aucun nom de document) ;
 • accord au premier dépôt (conditions d'utilisation et politique de confidentialité EXISTANTES, versions et
   empreintes enregistrées, horodaté, journalisé), redemandé quand une version change ; identité prouvée quand le
   lien vise une adresse ;
 • lecture SANS IA (aucun appel, rien de décompté) ; un CV n'est jamais gardé ni envoyé à l'IA, les passages de
   CV d'un mémoire sont retirés ; une pièce de l'acheteur n'est pas gardée ;
 • l'aide de l'IA : SES passages seulement (jamais rag.retrieve_multi), noms masqués, nom réel du document jamais
   envoyé, faits « trouvés dans vos documents » avec le passage exact ; le chef de file : compteurs seulement ;
 • coût : quota du chef de file, portée « inv:<id> », remboursé si l'IA tombe ;
 • suppression : par le partenaire (ses brouillons oublient les passages), invitation retirée ou déclinée,
   réinitialisation de l'espace, purge à 6 mois du résultat (horloge simulée) ou de la date limite, compte du chef
   de file effacé, corbeille des marchés ; lien rattaché à un compte (plus utilisés, téléchargeables, supprimables) ;
 • limites (nombre, taille, total, par jour, types, signature, doublon, illisible) ; démo ; migration ; écran.
Aucun appel réseau : le client IA est simulé.
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import date, datetime, timedelta, timezone

import pytest

from app.services import atelier_groupement as ag
from app.services import depot_lien as dl
from tests.test_convention_groupement import _register
from tests.test_redaction_socle0 import _db, _user_id, fake_llm  # noqa: F401
from tests.test_redaction_v4_groupement import (P, PC, _aide, _dossier_db, _envoyer, _groupement, _part_a,
                                                _reponse_partenaire, _trial, _vues_du_chef)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET_PASSAGE = "PASSAGEPRIVE58"
NOM_DOC = "Mémoire Brizeux 2024 - Anne Le Floch.txt"
MEMOIRE = ("Mémoire technique : désamiantage du collège Brizeux (2024)\n\n"
           "Démarche environnementale et gestion des déchets du chantier : nous trions les déchets amiantés dans "
           f"6 big-bags étanches, évacués vers une installation de stockage agréée. {SECRET_PASSAGE}\n\n"
           "Conductrice de travaux : Anne Le Floch.\n")
TEXTE_IA = "Nous trions les déchets amiantés dans 6 big-bags étanches [S1]. [À compléter : planning des évacuations]"
PLAQUETTE = ("Plaquette Breizh Désamiantage\n\nNotre entreprise intervient depuis 2009 en Bretagne pour le "
             "désamiantage des bâtiments publics, avec une gestion des déchets du chantier tracée par bordereaux.\n")


# ── Outils ───────────────────────────────────────────────────────────────────────────

def _deposer(p, nom, contenu, accepte=True, data=None):
    form = {"accepte_cgu": "1", "accepte_confidentialite": "1"} if accepte else {}
    form.update(data or {})
    if isinstance(contenu, str):
        contenu = contenu.encode("utf-8")
    return p.c.post(p.base + "/documents", headers=p.h, data=form,
                    files={"file": (nom, io.BytesIO(contenu), "application/octet-stream")})


def _deposer_ok(p, nom=NOM_DOC, contenu=MEMOIRE, accepte=True):
    r = _deposer(p, nom, contenu, accepte=accepte)
    assert r.status_code == 201, r.text
    return r.json()


def _pdf(lignes) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for ln in lignes:
        c.drawString(50, y, ln)
        y -= 16
    c.showPage()
    c.save()
    return buf.getvalue()


def _docx(paras) -> bytes:
    import docx
    d = docx.Document()
    for x in paras:
        d.add_paragraph(x)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _nb(model, **flt) -> int:
    db = _db()
    try:
        q = db.query(model)
        for k, v in flt.items():
            q = q.filter(getattr(model, k) == v)
        return q.count()
    finally:
        db.close()


def _cles(invite_id) -> list:
    from app.models import DepotLienDocument
    db = _db()
    try:
        return [r[0] for r in db.query(DepotLienDocument.file_key).filter(DepotLienDocument.invite_id == invite_id)]
    finally:
        db.close()


def _stocke(cle) -> bool:
    from app.services.storage import UPLOAD_DIR
    return os.path.exists(os.path.join(UPLOAD_DIR, cle))


def _plat(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _passage_exact(extrait, document) -> bool:
    """Le passage cité est recopié tel quel du document (les « … » marquent seulement une coupure)."""
    e = _plat(extrait).strip("… ").strip()
    return bool(e) and e in _plat(document)


def _sans_expiration(invite_id) -> None:
    """Lien sans date d'expiration : la purge suit alors le résultat du marché (sinon, 30 jours après l'expiration)."""
    from app.models import ProjectInvite
    db = _db()
    try:
        db.get(ProjectInvite, invite_id).expires_at = None
        db.commit()
    finally:
        db.close()


def _membre_du_chef(client, auth):
    from app.models import User
    hc, ec = _register(client, company="Collègue du chef")
    db = _db()
    try:
        org_id = db.query(User).filter(User.email == auth["email"]).first().org_id
        db.query(User).filter(User.email == ec).first().org_id = org_id
        db.commit()
    finally:
        db.close()
    return hc, ec


def _tout_du_chef(client, h, pid, sid, token):
    """Tout ce que lit le chef de file (ou un membre de son organisation) : écrans, exports, coffre, « Mes
    documents », export ZIP du dossier, journal du projet, et ce que le lien rend SANS la clé."""
    out = [_vues_du_chef(client, h, pid, sid, token=token),
           client.get("/api/documents/", headers=h).text,
           client.get(f"/api/projects/{pid}/coffre-croise", headers=h).text,
           client.get(f"/api/projects/{pid}/dossier-preview", headers=h).text,
           client.get(f"/api/projects/{pid}/contributions", headers=h).text,
           client.get(f"/api/atelier/{pid}/repartition/dossier", headers=h).text,
           client.get(f"/api/invite/{token}/journal").text]
    for chemin in ("/documents", f"/sections/{sid}"):
        out.append(client.get(f"/api/invite/{token}/redaction{chemin}").text)
    r = client.post(f"/api/export/{pid}", headers=h)
    assert r.status_code == 200, r.text[:300]
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        for n in z.namelist():
            out.append(n)
            out.append(z.read(n).decode("latin-1"))
    return "\n".join(out)


# ═══ 1. Le dépôt par le lien : accord, lecture sans IA, aide de l'IA sur SES documents ═══

def test_depot_accord_lecture_sans_ia_puis_aide_sur_ses_seuls_documents(client, auth, fake_llm, monkeypatch):
    h = auth["headers"]
    monkeypatch.setenv("ATELIER_LIBELLES_SOURCES", "1")
    pid, st, a, b, vue = _groupement(client, auth)
    ans, vus = _reponse_partenaire(TEXTE_IA)
    fake = fake_llm(ans)
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])
    v = pa.get("/documents").json()
    assert v["documents"] == [] and v["utilises"] is True and v["peut_deposer"] is True
    assert v["qui_voit"] == "Seuls vous et Adjugo les lisez ; le chef de file ne les voit jamais."
    c = v["conditions"]
    assert c["a_accepter"] is True and c["message"] == dl.MSG_CONDITIONS
    assert [(t["cle"], t["adresse"], t["version"]) for t in c["textes"]] == [("cgu", "/cgv", "1.2"),
                                                                          ("confidentialite", "/confidentialite", "1.3")]
    assert v["limites"]["types"] == [".pdf", ".docx", ".odt", ".txt"] and v["limites"]["fichiers"] == 10
    t0 = _trial(auth["email"])
    # Premier dépôt sans l'accord : refusé, rien n'est gardé.
    r = _deposer(pa, NOM_DOC, MEMOIRE, accepte=False)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "conditions_a_accepter"
    assert r.json()["detail"]["conditions"]["textes"][0]["adresse"] == "/cgv"
    from app.models import AuditLog, DepotLienDocument, DepotLienEspace, DepotLienMorceau
    assert _nb(DepotLienDocument, invite_id=a["id"]) == 0 and _nb(DepotLienEspace, invite_id=a["id"]) == 0
    r = _deposer(pa, NOM_DOC, MEMOIRE, accepte=True, data={"accepte_confidentialite": ""})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "conditions_a_accepter"
    # Avec l'accord : gardé, lu sans IA, rien de décompté.
    out = _deposer_ok(pa)
    d = out["depose"]
    assert d["nom"] == NOM_DOC and d["lecture"] == "texte" and d["lecture_libelle"] == "Lu sans IA (texte du document)"
    assert d["passages"] >= 1 and out["conditions"]["a_accepter"] is False
    assert fake.calls == [] and _trial(auth["email"]) == t0
    db = _db()
    try:
        esp = db.query(DepotLienEspace).filter(DepotLienEspace.invite_id == a["id"]).one()
        acc = esp.consentement
        assert acc["cgu"]["version"] == "1.2" and acc["confidentialite"]["version"] == "1.3"
        assert len(acc["cgu"]["empreinte"]) == 16 and acc["accepte_le"] and esp.accepte_le is not None
        doc = db.query(DepotLienDocument).filter(DepotLienDocument.invite_id == a["id"]).one()
        assert doc.file_key.startswith(f"invitations/{a['id']}/depots/") and doc.owner_id == _user_id(auth["email"])
        j = [(x.action, x.detail, x.entry_hash) for x in db.query(AuditLog).filter(AuditLog.invite_id == a["id"],
                                                                                    AuditLog.action.like("redaction.doc%"))
             .order_by(AuditLog.id)]
    finally:
        db.close()
    assert [x[0] for x in j] == ["redaction.documents_conditions", "redaction.document_depose"]
    assert "version 1.2" in j[0][1] and "version 1.3" in j[0][1] and all(x[2] for x in j)
    assert all(NOM_DOC not in x[1] and "Brizeux" not in x[1] for x in j)
    assert _stocke(doc.file_key)
    # Un second document, l'accord déjà donné ; puis un PDF et un Word, lus sans IA.
    assert _deposer_ok(pa, "Plaquette.docx", _docx(PLAQUETTE.split("\n")), accepte=False)["depose"]["lecture"] == "texte"
    r = _deposer_ok(pa, "References.pdf", _pdf(["Références : désamiantage de 3 écoles du Finistère en 2023.",
                                                "Gestion des déchets du chantier par bordereaux de suivi."]))
    assert r["depose"]["lecture"] == "texte" and len(r["documents"]) == 3 and fake.calls == []
    vue_p = pa.get().json()
    assert vue_p["documents"]["nombre"] == 3 and vue_p["documents"]["utilises"] is True
    assert vue_p["message_mode"] == ag.MSG_MODE_LIEN and "Vos documents pour Adjugo" in ag.MSG_MODE_LIEN
    # L'aide de l'IA : SES passages, jamais rag.retrieve_multi, noms masqués, aucun nom de document.
    from app.services import rag
    croises = []
    monkeypatch.setattr(rag, "retrieve_multi", lambda *x, **k: croises.append(x) or [])
    job, jid = _aide(pa, sid)
    assert job["status"] == "done", job
    assert job["result"]["sections"][0]["extraits_fournis"] >= 1
    sent = fake.sent()
    assert SECRET_PASSAGE in sent and "Votre document" in sent and "6 big-bags" in sent
    for interdit in ("Anne Le Floch", "Le Floch", NOM_DOC, "Mémoire Brizeux 2024"):
        assert interdit not in sent, interdit
    assert croises == [] and vus and all(t == f"inv:{a['id']}" for t in vus)
    # Coût : la rédaction, au quota du chef de file (une analyse pour le dossier), jamais la lecture.
    assert _trial(auth["email"])[0] == t0[0] + 1 and _dossier_db(pid)["analyse_debitee"] is True
    br = pa.get(f"/sections/{sid}").json()["brouillon"]
    assert br["origine"] == "ia" and br["sources"][0]["doc_name"] == NOM_DOC
    assert br["sources"][0]["depot_id"] == doc.id and "chunk_id" not in br["sources"][0]
    fait = next(f for f in br["faits_sources"] if f["fait"].startswith("6"))
    src = fait["source"]
    assert src["libelle"] == "trouvé dans vos documents" and src["type"] == "documents" and src["ref"] == "S1"
    assert src["doc_nom"] == NOM_DOC and "6 big-bags" in src["extrait"] and _passage_exact(src["extrait"], MEMOIRE)
    assert br["controle"]["libelles"] is True
    # « J'écris moi-même » à partir de ce brouillon : le fait garde sa source (passage relu dans SES documents).
    t2 = br["texte"].replace("[À compléter : planning des évacuations]", "Les évacuations sont hebdomadaires.")
    r = pa.put(f"/sections/{sid}/brouillon", {"texte": t2, "base_brouillon_id": br["id"]})
    assert r.status_code == 200, r.text
    f2 = next(f for f in r.json()["brouillon"]["faits_sources"] if f["fait"].startswith("6"))
    assert f2["source"]["libelle"] == "trouvé dans vos documents" and f2["source"]["doc_nom"] == NOM_DOC
    # Envoyé : le chef de file lit le texte et les COMPTEURS par type ; jamais un passage ni un nom de document.
    _envoyer(pa, sid)
    ligne = client.get(f"/api/atelier/{pid}/repartition/{sid}", headers=h).json()
    assert ligne["texte_commun"]["compteurs"]["par_type"]["documents"] >= 1
    tout = _tout_du_chef(client, h, pid, sid, a["token"])
    assert "6 big-bags étanches" in tout                                # le texte envoyé : oui
    for secret in (SECRET_PASSAGE, NOM_DOC, "Plaquette.docx", "References.pdf", "Anne Le Floch", "depuis 2009"):
        assert secret not in tout, secret
    # L'autre partenaire lit le dossier assemblé : le texte envoyé, rien de ses documents.
    pb = P(client, b["token"])
    d_b = pb.get("/dossier").text + pb.get("/documents").text
    assert "6 big-bags étanches" in d_b and SECRET_PASSAGE not in d_b and NOM_DOC not in d_b
    assert _nb(DepotLienMorceau, invite_id=a["id"]) >= 3


# ═══ 2. Cloisonnement : 403 ou 404 pour tout autre que lui ════════════════════════════

def test_cloisonnement_chef_de_file_son_organisation_autre_partenaire_et_demo(client, auth, fake_llm):
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth)
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])
    did = _deposer_ok(pa)["depose"]["id"]
    # Le chef de file, avec le lien mais sans la clé de l'espace : 403 partout, rien ne se lit ni ne s'écrit.
    chef = P(client, a["token"], ouvrir=False)
    for m, chemin in (("get", "/documents"), ("get", f"/documents/{did}/fichier")):
        r = getattr(chef, m)(chemin)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "cle_espace_requise", chemin
    r = chef.c.delete(chef.base + f"/documents/{did}", headers=chef.h)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "cle_espace_requise"
    r = _deposer(chef, "Autre.txt", "Un document du chef de file glissé dans l'espace du partenaire. " * 3)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "cle_espace_requise"
    chef.h = {ag.ENTETE_CLE: "cle-inventee"}
    assert chef.get("/documents").status_code == 403
    assert chef.get().json()["documents"] is None
    # Le chef de file et un membre de son organisation, par leur compte : 404 (ils ne sont jamais le partenaire),
    # même si un membre de l'organisation avait rattaché le lien.
    hc, ec = _membre_du_chef(client, auth)
    for hh in (h, hc):
        assert client.get(f"/api/shared/{pid}/redaction/documents", headers=hh).status_code == 404
        assert client.get(f"/api/shared/{pid}/redaction/documents/{did}/fichier", headers=hh).status_code == 404
        assert client.delete(f"/api/shared/{pid}/redaction/documents/{did}", headers=hh).status_code == 404
    from app.models import ProjectInvite
    db = _db()
    try:
        db.get(ProjectInvite, a["id"]).accepted_by_user_id = _user_id(ec)
        db.commit()
    finally:
        db.close()
    assert client.get(f"/api/shared/{pid}/redaction/documents", headers=hc).status_code == 404
    assert client.get(f"/api/shared/{pid}/redaction/documents/{did}/fichier", headers=hc).status_code == 404
    db = _db()
    try:
        db.get(ProjectInvite, a["id"]).accepted_by_user_id = None
        db.commit()
    finally:
        db.close()
    # Un autre partenaire, avec SA clé : le document de A n'existe pas pour lui (404), sa liste est vide.
    pb = P(client, b["token"])
    assert pb.get("/documents").json()["documents"] == []
    assert pb.get(f"/documents/{did}/fichier").status_code == 404
    r = pb.c.delete(pb.base + f"/documents/{did}", headers=pb.h)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "document_introuvable"
    # Rien chez le chef de file ni chez un membre de son organisation : écrans, exports, coffre, documents, ZIP.
    for hh in (h, hc):
        tout = _tout_du_chef(client, hh, pid, sid, a["token"])
        for secret in (SECRET_PASSAGE, NOM_DOC, "Anne Le Floch", "invitations/"):
            assert secret not in tout, secret
    # Le journal se lit avec le lien seul : il dit ce qui a été fait, jamais le nom d'un document.
    j = client.get(f"/api/invite/{a['token']}/journal").json()["entries"]
    labels = [e["label"] for e in j]
    assert "Vous avez déposé un document dans votre espace privé" in labels
    assert any("conditions d'utilisation" in x for x in labels)
    assert NOM_DOC not in json.dumps(j, ensure_ascii=False)
    # Le partenaire lui-même retrouve son document.
    assert pa.get(f"/documents/{did}/fichier").status_code == 200


def test_demo_le_lien_et_la_session_de_la_demo_ne_deposent_rien(client, monkeypatch):
    from app.core.demo_guard import blocked_action
    from app.models import DepotLienDocument, Project, ProjectInvite, User
    from app.services.demo_seed import DEMO_EMAIL, ensure_demo
    db = _db()
    try:
        ensure_demo(db, force=True)
        u = db.query(User).filter(User.email == DEMO_EMAIL).one()
        lorient = next(p for p in db.query(Project).filter(Project.user_id == u.id).all() if "Kerhel" in p.name)
        tok = db.query(ProjectInvite).filter(ProjectInvite.project_id == lorient.id).first().token
        pid = lorient.id
    finally:
        db.close()
    base = f"/api/invite/{tok}/redaction"
    r = client.post(base + "/documents", data={"accepte_cgu": "1", "accepte_confidentialite": "1"},
                    files={"file": ("memoire.txt", io.BytesIO(MEMOIRE.encode()), "text/plain")})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "demo"
    r = client.delete(base + "/documents/1")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "demo"
    assert client.post(base + "/espace", json={}).status_code == 403          # aucun espace à ouvrir
    assert client.get(base + "/documents").status_code in (403, 404)
    assert _nb(DepotLienDocument, project_id=pid) == 0
    # Le garde central refuse aussi une session démo sur ces routes ; la route « Partagé avec moi » aussi, même
    # sans le garde.
    for m, chemin in (("POST", f"/api/invite/x/redaction/documents"), ("DELETE", "/api/invite/x/redaction/documents/3"),
                      ("DELETE", "/api/shared/7/redaction/documents/3")):
        assert blocked_action(m, chemin), chemin
    r = client.post("/api/auth/demo")
    hd = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.delete(f"/api/shared/{pid}/redaction/documents/1", headers=hd)
    assert r.status_code == 403 and "lecture guidée" in r.text
    import app.core.demo_guard as g
    monkeypatch.setattr(g, "blocked_action", lambda *a, **k: None)
    r = client.delete(f"/api/shared/{pid}/redaction/documents/1", headers=hd)
    assert r.status_code == 403 and "lecture guidée" in r.text


# ═══ 3. Jamais un CV vers l'IA ; jamais une pièce de l'acheteur ═══════════════════════

def test_cv_jamais_garde_ni_envoye_et_passages_de_cv_retires(client, auth, fake_llm):
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    fake = fake_llm(_reponse_partenaire(TEXTE_IA)[0])
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])
    from app.models import DepotLienDocument, DepotLienMorceau
    # Un CV (par son nom, ou par son contenu) : pas gardé.
    r = _deposer(pa, "CV Jean Dupont.pdf", _pdf(["Jean Dupont", "Chef de chantier, 15 ans d'expérience.",
                                                 "Gestion des déchets du chantier."]))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "document_cv"
    cv = ("Curriculum vitae\n\nJean Dupont\nDate de naissance : 12/03/1980\nNationalité : française\n"
          "Expériences professionnelles : chef de chantier en désamiantage depuis 2008.\n"
          "Formations : SS3 encadrement technique, gestion des déchets du chantier.\n")
    r = _deposer(pa, "presentation.txt", cv)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "document_cv" and r.json()["detail"]["message"] == dl.MSG_CV
    assert _nb(DepotLienDocument, invite_id=a["id"]) == 0 and fake.calls == []
    # Une pièce du dossier de l'acheteur : pas gardée (elle ne dit rien de l'entreprise).
    rc = ("REGLEMENT DE LA CONSULTATION\nArticle 1 - Objet\nDésamiantage et gestion des déchets du chantier du "
          "collège.\nArticle 7 - Critères de jugement des offres\nValeur technique : 60 %\nPrix : 40 %\n")
    r = _deposer(pa, "RC.txt", rc)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "piece_acheteur"
    # Un mémoire avec une annexe « CV » : gardé, mais les lignes du CV ne sont ni cherchées ni envoyées.
    memoire = (MEMOIRE + "\nOrganisation du chantier : confinement de la zone, sas de décontamination à trois "
               "compartiments, mesures d'empoussièrement avant, pendant et après les travaux, restitution des "
               "locaux après examen visuel et mesures libératoires. Les déchets du chantier sont tracés par "
               "bordereaux de suivi jusqu'à leur élimination.\n"
               "\nANNEXE 3 : CV DU CONDUCTEUR DE TRAVAUX\nYves Kerhervé\nDate de naissance : 01/02/1985\n"
               "Expériences professionnelles : 12 ans en désamiantage, gestion des déchets du chantier.\n"
               "Loisirs : voile, randonnée.\n")
    d = _deposer_ok(pa, "Memoire complet.txt", memoire)["depose"]
    assert d["passages_cv_retires"] is True
    db = _db()
    try:
        textes = " ".join(m.texte for m in db.query(DepotLienMorceau).filter(DepotLienMorceau.invite_id == a["id"]))
    finally:
        db.close()
    assert "01/02/1985" not in textes and "Loisirs" not in textes and SECRET_PASSAGE in textes
    assert _aide(pa, sid)[0]["status"] == "done"
    sent = fake.sent()
    for interdit in ("01/02/1985", "Date de naissance", "Loisirs", "Kerhervé"):
        assert interdit not in sent, interdit
    assert SECRET_PASSAGE in sent
    # La recherche elle-même n'en rend jamais (filet sur chaque passage).
    db = _db()
    try:
        hits = dl.rechercher(db, a["id"], "date de naissance expériences professionnelles loisirs déchets chantier")
    finally:
        db.close()
    assert all("naissance" not in x["text"].lower() for x in hits)


# ═══ 4. Coût et remboursement ═══════════════════════════════════════════════════════

def test_lecture_gratuite_et_aide_remboursee_si_l_ia_tombe(client, auth, fake_llm):
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])

    def boom(kw):
        raise RuntimeError("fournisseur indisponible")
    fake = fake_llm(boom)
    t0 = _trial(auth["email"])
    _deposer_ok(pa)
    _deposer_ok(pa, "References.pdf", _pdf(["Gestion des déchets du chantier : 3 écoles désamiantées en 2023."]))
    assert fake.calls == [] and _trial(auth["email"]) == t0           # la lecture ne coûte rien (sans IA)
    job, _ = _aide(pa, sid)
    assert job["status"] == "error" and job["error"] == ag.MSG_IA_PANNE
    assert _trial(auth["email"]) == t0 and _dossier_db(pid)["analyse_debitee"] is False
    p = pa.get(f"/sections/{sid}").json()
    assert p["aide"]["utilisees"] == 0 and p["brouillon"] is None     # aide rendue, rien débité
    assert SECRET_PASSAGE in fake.sent()


# ═══ 5. Limites et contrôles du fichier ═══════════════════════════════════════════════

def test_limites_types_taille_nombre_jour_doublon_et_signature(client, auth, monkeypatch):
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    pa = P(client, a["token"])
    _deposer_ok(pa)                                                    # accord donné
    for nom, contenu, code in (("archive.zip", b"PK\x03\x04xxxx", "type_refuse"), ("outil.exe", b"MZ" * 40, "type_refuse"),
                               ("image.png", b"\x89PNG" * 20, "type_refuse"), ("vide.txt", b"", "fichier_vide"),
                               ("faux.pdf", ("Ceci n'est pas un PDF. " * 10).encode(), "fichier_invalide"),
                               ("faux.docx", b"<html>page web renommee</html>" * 5, "fichier_invalide"),
                               ("binaire.txt", b"abc\x00def" * 20, "fichier_invalide"),
                               ("court.txt", b"Trop court.", "document_illisible")):
        r = _deposer(pa, nom, contenu, accepte=False)
        assert r.status_code in (413, 422) and r.json()["detail"]["code"] == code, (nom, r.text)
    r = _deposer(pa, "copie.txt", MEMOIRE, accepte=False)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "document_deja_depose"
    # Réglables : taille d'un fichier, nombre, total, dépôts par jour, types.
    monkeypatch.setenv("DEPOT_LIEN_MO", "1")
    r = _deposer(pa, "gros.txt", ("Gestion des déchets du chantier. " * 40000).encode(), accepte=False)
    assert r.status_code == 413 and r.json()["detail"]["code"] == "fichier_trop_lourd" and "1 Mo" in r.json()["detail"]["message"]
    monkeypatch.setenv("DEPOT_LIEN_MO_TOTAL", "1")
    taille = dl.MB - len(MEMOIRE.encode("utf-8")) + 10           # sous 1 Mo, mais le total le dépasse
    r = _deposer(pa, "moyen.txt", ("Gestion des déchets du chantier, tri sélectif. " * 30000).encode()[:taille],
                 accepte=False)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "espace_plein"
    monkeypatch.delenv("DEPOT_LIEN_MO_TOTAL")
    monkeypatch.setenv("DEPOT_LIEN_FICHIERS", "2")
    _deposer_ok(pa, "Plaquette.txt", PLAQUETTE, accepte=False)
    r = _deposer(pa, "Troisieme.txt", PLAQUETTE + " Troisième document.", accepte=False)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "trop_de_documents"
    monkeypatch.setenv("DEPOT_LIEN_FICHIERS", "10")
    monkeypatch.setenv("DEPOT_LIEN_PAR_JOUR", "3")
    did = _deposer_ok(pa, "Troisieme.txt", PLAQUETTE + " Troisième document.", accepte=False)["depose"]["id"]
    assert pa.c.delete(pa.base + f"/documents/{did}", headers=pa.h).status_code == 200
    r = _deposer(pa, "Quatrieme.txt", PLAQUETTE + " Quatrième document.", accepte=False)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "trop_de_depots"    # supprimés compris
    monkeypatch.setenv("DEPOT_LIEN_PAR_JOUR", "30")
    monkeypatch.setenv("DEPOT_LIEN_TYPES", ".pdf")
    r = _deposer(pa, "Quatrieme.txt", PLAQUETTE + " Quatrième document.", accepte=False)
    assert r.status_code == 422 and r.json()["detail"]["message"] == "Déposez un fichier PDF."
    assert pa.get("/documents").json()["limites"]["types"] == [".pdf"]
    # Jamais un type de plus que ceux qu'Adjugo lit sans IA.
    monkeypatch.setenv("DEPOT_LIEN_TYPES", ".pdf,.html,.svg")
    assert dl.types_acceptes() == [".pdf"]


def test_accord_redemande_quand_un_texte_change_et_identite_prouvee(client, auth, monkeypatch):
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    pa = P(client, a["token"])
    _deposer_ok(pa)
    vrais = dl.textes_juridiques()
    monkeypatch.setattr(dl, "textes_juridiques", lambda: [dict(vrais[0], version="1.3"), vrais[1]])
    v = pa.get("/documents").json()["conditions"]
    assert v["a_accepter"] is True and v["message"] == dl.MSG_CONDITIONS_NOUVELLES
    r = _deposer(pa, "Plaquette.txt", PLAQUETTE, accepte=False)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "conditions_a_accepter"
    _deposer_ok(pa, "Plaquette.txt", PLAQUETTE)
    from app.models import DepotLienEspace
    db = _db()
    try:
        assert db.query(DepotLienEspace).filter(DepotLienEspace.invite_id == a["id"]).one().consentement["cgu"]["version"] == "1.3"
    finally:
        db.close()
    # Lien qui vise une adresse pas encore prouvée : déposer (et accepter) exige le code reçu par le partenaire.
    import app.routers.invites as invites
    monkeypatch.setattr(invites, "_binding_required", lambda inv: True)
    r = _deposer(pa, "Autre.txt", PLAQUETTE + " Autre.", accepte=False)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "identity_unverified"
    from app.models import ProjectInvite
    db = _db()
    try:
        db.get(ProjectInvite, a["id"]).verified_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()
    assert _deposer(pa, "Autre.txt", PLAQUETTE + " Autre.", accepte=False).status_code == 201


# ═══ 6. Télécharger, exporter, supprimer (par lui) ══════════════════════════════════════

def test_telecharger_exporter_et_supprimer_ses_documents(client, auth, fake_llm, monkeypatch):
    monkeypatch.setenv("ATELIER_LIBELLES_SOURCES", "1")
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    fake_llm(_reponse_partenaire(TEXTE_IA)[0])
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])
    brut = MEMOIRE.encode("utf-8")
    did = _deposer_ok(pa, NOM_DOC, brut)["depose"]["id"]
    r = pa.get(f"/documents/{did}/fichier")
    assert r.status_code == 200 and r.content == brut
    assert "attachment" in r.headers["content-disposition"] and r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "no-store" and r.headers["content-type"].startswith("text/plain")
    exp = pa.get("/export").json()["documents_deposes"]
    assert exp["documents"][0]["nom"] == NOM_DOC and exp["documents"][0]["telecharger"] == f"documents/{did}/fichier"
    assert exp["conditions_acceptees"]["cgu"]["version"] == "1.2"
    assert _aide(pa, sid)[0]["status"] == "done"
    br = pa.get(f"/sections/{sid}").json()["brouillon"]
    assert br["sources"] and any(f["source"].get("depot_id") == did for f in br["faits_sources"])
    cle = _cles(a["id"])[0]
    # Supprimer : le fichier, ses passages, et dans ses brouillons les extraits cités (leurs faits à relire).
    r = pa.c.delete(pa.base + f"/documents/{did}", headers=pa.h)
    assert r.status_code == 200 and r.json()["documents"] == []
    from app.models import DepotLienDocument, DepotLienMorceau
    assert _nb(DepotLienDocument, invite_id=a["id"]) == 0 and _nb(DepotLienMorceau, invite_id=a["id"]) == 0
    assert not _stocke(cle) and pa.get(f"/documents/{did}/fichier").status_code == 404
    br = pa.get(f"/sections/{sid}").json()["brouillon"]
    assert br["sources"] == [] and not any(f["source"].get("depot_id") == did for f in br["faits_sources"])
    six = next(f for f in br["faits"] if f.get("fait", "").startswith("6"))
    assert six["statut"] == "a_relire"
    assert SECRET_PASSAGE not in json.dumps(pa.get("/export").json(), ensure_ascii=False)
    j = [e["label"] for e in client.get(f"/api/invite/{a['token']}/journal").json()["entries"]]
    assert "Vous avez supprimé un document de votre espace privé" in j


# ═══ 7. Effacés : invitation retirée ou déclinée, espace réinitialisé ═══════════════════

def test_effaces_au_retrait_au_declin_et_a_la_reinitialisation(client, auth):
    h = auth["headers"]
    pid, st, a, b, vue = _groupement(client, auth)
    pa, pb = P(client, a["token"]), P(client, b["token"])
    _deposer_ok(pa)
    _deposer_ok(pb, "Plaquette Le Gall.txt", PLAQUETTE.replace("Désamiantage", "Électricité"))
    ca, cb = _cles(a["id"]), _cles(b["id"])
    assert ca and cb and all(_stocke(k) for k in ca + cb)
    from app.models import DepotLienDocument, DepotLienEspace
    # Retrait par le chef de file : effacés (lignes, fichiers, accord), inscrit au journal du membre.
    assert client.delete(f"/api/projects/{pid}/invites/{a['id']}", headers=h).status_code == 200
    assert _nb(DepotLienDocument, invite_id=a["id"]) == 0 and _nb(DepotLienEspace, invite_id=a["id"]) == 0
    assert not any(_stocke(k) for k in ca)
    from tests.test_redaction_v4_groupement import _audit
    assert any(x[0] == "redaction.documents_effaces" and NOM_DOC not in x[3] for x in _audit(invite_id=a["id"]))
    # Déclin par le partenaire : effacés aussi.
    assert client.post(f"/api/invite/{b['token']}/decline").status_code == 200
    assert _nb(DepotLienDocument, invite_id=b["id"]) == 0 and not any(_stocke(k) for k in cb)
    # Réinitialisation de l'espace : effacés SANS être lus ; le nouvel espace redonne son accord avant tout dépôt.
    pid2, st2, c, d, vue2 = _groupement(client, auth, avec_b=False)
    pc = P(client, c["token"])
    _deposer_ok(pc)
    cc = _cles(c["id"])
    autre = P(client, c["token"], ouvrir=False)
    r = autre.post("/espace", {"reinitialiser": True})
    assert r.status_code == 200 and r.json()["documents_effaces"] == 1 and "cle" in r.json()
    assert _nb(DepotLienDocument, invite_id=c["id"]) == 0 and _nb(DepotLienEspace, invite_id=c["id"]) == 0
    assert not any(_stocke(k) for k in cc)
    assert pc.get("/documents").status_code == 403                    # l'ancienne clé ne vaut plus
    autre.h = {ag.ENTETE_CLE: r.json()["cle"]}
    v = autre.get("/documents").json()
    assert v["documents"] == [] and v["conditions"]["a_accepter"] is True
    j = client.get(f"/api/invite/{c['token']}/journal").json()["entries"]
    reinit = next(e for e in j if e["action"] == "redaction.espace_reinitialise")
    assert "1 document déposé effacé" in reinit["detail"] and NOM_DOC not in json.dumps(j, ensure_ascii=False)


# ═══ 8. Purge quotidienne : 6 mois après le résultat (horloge simulée), à défaut la date limite ═══

def test_purge_six_mois_apres_le_resultat_ou_la_date_limite(client, auth, monkeypatch):
    h = auth["headers"]
    from app.models import DepotLienDocument, DepotLienEspace, Project
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    _sans_expiration(a["id"])
    pa = P(client, a["token"])
    _deposer_ok(pa)
    cles = _cles(a["id"])
    maintenant = datetime.now(timezone.utc)
    db = _db()
    try:
        dl.purger(db, maintenant)
        assert _nb(DepotLienDocument, invite_id=a["id"]) == 1             # marché en cours, sans date limite
    finally:
        db.close()
    # Résultat (perdu) : la purge note la date du résultat ; rien n'est effacé avant 6 mois.
    assert client.put(f"/api/projects/{pid}", headers=h, json={"status": "perdu"}).status_code == 200
    db = _db()
    try:
        dl.purger(db, maintenant)
        esp = db.query(DepotLienEspace).filter(DepotLienEspace.invite_id == a["id"]).one()
        resultat = esp.resultat_le
        assert resultat is not None and _nb(DepotLienDocument, invite_id=a["id"]) == 1
        dl.purger(db, dl.plus_mois(resultat, 6) - timedelta(days=1))
        assert _nb(DepotLienDocument, invite_id=a["id"]) == 1
    finally:
        db.close()
    # Un résultat retiré (le marché repasse « envoyé ») remet le compteur à zéro ; il repart au résultat suivant.
    assert client.put(f"/api/projects/{pid}", headers=h, json={"status": "envoye"}).status_code == 200
    db = _db()
    try:
        dl.purger(db, maintenant)
        assert db.query(DepotLienEspace).filter(DepotLienEspace.invite_id == a["id"]).one().resultat_le is None
    finally:
        db.close()
    assert client.put(f"/api/projects/{pid}", headers=h, json={"status": "gagne"}).status_code == 200
    db = _db()
    try:
        dl.purger(db, maintenant)
        resultat = db.query(DepotLienEspace).filter(DepotLienEspace.invite_id == a["id"]).one().resultat_le
        res = dl.purger(db, dl.plus_mois(resultat, 6) + timedelta(hours=1))
    finally:
        db.close()
    assert res["documents_partenaires_effaces"] >= 1 and res["espaces_documents_effaces"] >= 1
    assert _nb(DepotLienDocument, invite_id=a["id"]) == 0 and _nb(DepotLienEspace, invite_id=a["id"]) == 0
    assert not any(_stocke(k) for k in cles)
    j = client.get(f"/api/invite/{a['token']}/journal").json()["entries"]
    e = next(x for x in j if x["action"] == "redaction.documents_effaces")
    assert e["label"] == "Vos documents déposés pour Adjugo ont été effacés" and "6 mois après le résultat" in e["detail"]
    # À défaut de résultat : 6 mois après la date limite (purge du cron quotidien, secret exigé).
    pid2, st2, c, d, vue2 = _groupement(client, auth, avec_b=False)
    _sans_expiration(c["id"])
    pc = P(client, c["token"])
    _deposer_ok(pc)
    db = _db()
    try:
        dl.purger(db)
        assert _nb(DepotLienDocument, invite_id=c["id"]) == 1
        db.get(Project, pid2).deadline = date.today() - timedelta(days=200)
        db.commit()
    finally:
        db.close()
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "CRON_SECRET", "secret-de-test")
    r = client.post("/api/admin/run-trash-purge", headers={"x-cron-secret": "secret-de-test"})
    assert r.status_code == 200 and r.json()["documents_partenaires_effaces"] >= 1, r.text
    assert _nb(DepotLienDocument, invite_id=c["id"]) == 0
    assert client.post("/api/admin/run-trash-purge").status_code == 403
    # Ni résultat ni date limite : 6 mois après le dernier dépôt.
    pid3, st3, e, f, vue3 = _groupement(client, auth, avec_b=False)
    _sans_expiration(e["id"])
    _deposer_ok(P(client, e["token"]))
    plus_tard = dl.plus_mois(datetime.now(timezone.utc).replace(tzinfo=None), 6)
    db = _db()
    try:
        dl.purger(db, plus_tard - timedelta(days=1))
        assert _nb(DepotLienDocument, invite_id=e["id"]) == 1
        dl.purger(db, plus_tard + timedelta(days=1))
        assert _nb(DepotLienDocument, invite_id=e["id"]) == 0
    finally:
        db.close()
    assert dl.plus_mois(datetime(2026, 8, 31), 6) == datetime(2027, 2, 28)


def test_purge_lien_expire_compte_du_chef_efface_et_corbeille(client, auth):
    h = auth["headers"]
    from app.models import DepotLienDocument, DepotLienEspace, DepotLienMorceau, Project, ProjectInvite
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    pa = P(client, a["token"])
    _deposer_ok(pa)
    cles = _cles(a["id"])
    # Lien expiré depuis plus de 30 jours : effacés (comme les brouillons).
    db = _db()
    try:
        db.get(ProjectInvite, a["id"]).expires_at = datetime.now(timezone.utc) - timedelta(days=29)
        db.commit()
        dl.purger(db)
        assert _nb(DepotLienDocument, invite_id=a["id"]) == 1             # expiré depuis moins de 30 jours
        db.get(ProjectInvite, a["id"]).expires_at = datetime.now(timezone.utc) - timedelta(days=31)
        db.commit()
        assert dl.purger(db)["documents_partenaires_effaces"] >= 1
        assert _nb(DepotLienDocument, invite_id=a["id"]) == 0
    finally:
        db.close()
    assert not any(_stocke(k) for k in cles)
    # Corbeille des marchés : le marché supprimé depuis plus de 30 jours part avec ses documents déposés.
    pid2, st2, c, d, vue2 = _groupement(client, auth, avec_b=False)
    _deposer_ok(P(client, c["token"]))
    cles = _cles(c["id"])
    assert client.delete(f"/api/projects/{pid2}", headers=h).status_code == 204
    from app.routers.rgpd import purge_trash
    db = _db()
    try:
        db.get(Project, pid2).deleted_at = datetime.now(timezone.utc) - timedelta(days=40)
        db.commit()
        purge_trash(db)
    finally:
        db.close()
    assert _nb(DepotLienDocument, invite_id=c["id"]) == 0 and not any(_stocke(k) for k in cles)
    assert _nb(DepotLienMorceau, invite_id=c["id"]) == 0 and _nb(DepotLienEspace, invite_id=c["id"]) == 0
    # Effacement du compte du chef de file : ses marchés partent avec les documents déposés par ses partenaires.
    pid3, st3, e, f, vue3 = _groupement(client, auth, avec_b=False)
    _deposer_ok(P(client, e["token"]))
    cles = _cles(e["id"])
    r = client.post("/api/rgpd/delete-account", headers=h, json={"password": "motdepasse123", "confirm": "SUPPRIMER"})
    assert r.status_code == 200, r.text
    assert _nb(DepotLienDocument, invite_id=e["id"]) == 0 and not any(_stocke(k) for k in cles)
    assert _nb(DepotLienMorceau, invite_id=e["id"]) == 0 and _nb(DepotLienEspace, invite_id=e["id"]) == 0


# ═══ 9. Lien rattaché à un compte : ses documents de compte, inchangé ═══════════════════

def test_lien_rattache_a_un_compte_n_utilise_plus_les_documents_deposes(client, auth, fake_llm):
    pid, st, a, b, vue = _groupement(client, auth, avec_b=False)
    fake = fake_llm(_reponse_partenaire(TEXTE_IA)[0])
    sid = _part_a(vue)["section_id"]
    pa = P(client, a["token"])
    did = _deposer_ok(pa)["depose"]["id"]
    hp, ep = _register(client, company="Breizh Désamiantage")
    r = client.post(f"/api/invite/{a['token']}/claim", headers=dict(hp, **pa.h))     # depuis son navigateur (clé)
    assert r.status_code == 200, r.text
    # Par le lien : plus d'espace, plus de dépôt.
    assert pa.get("/documents").status_code == 403
    r = _deposer(pa, "Autre.txt", PLAQUETTE)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "depot_par_le_compte"
    # Par le compte : la liste (téléchargeable, supprimable), mais Adjugo ne s'en sert plus.
    pc = PC(client, pid, hp)
    v = pc.get("/documents").json()
    assert v["utilises"] is False and v["message"] == dl.MSG_COMPTE and v["conditions"] is None
    assert [x["id"] for x in v["documents"]] == [did] and v["peut_deposer"] is False
    assert pc.get().json()["documents"] == {"nombre": 1, "utilises": False, "possible": False}
    assert client.post(f"/api/shared/{pid}/redaction/documents", headers=hp).status_code == 405
    assert pc.get(f"/documents/{did}/fichier").content == MEMOIRE.encode("utf-8")
    assert _aide(pc, sid)[0]["status"] == "done"
    assert SECRET_PASSAGE not in fake.sent()                          # ses documents de compte, inchangé
    r = pc.c.delete(pc.base + f"/documents/{did}", headers=pc.h)
    assert r.status_code == 200 and r.json()["documents"] == []


# ═══ 10. Migration y9z0depotlien (SQLite) ═════════════════════════════════════════════

def test_migration_depot_lien_sqlite_neuve_retour_arriere_rejeu(tmp_path):
    import sqlalchemy as sa
    dbfile = tmp_path / "depot.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{dbfile}"}
    tables = ("depots_lien_espaces", "depots_lien_documents", "depots_lien_morceaux")

    def run(*args):
        r = subprocess.run([sys.executable, "-m", "alembic"] + list(args), cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stdout + r.stderr
        return r.stdout + r.stderr

    def schema():
        eng = sa.create_engine(f"sqlite:///{dbfile}")
        try:
            insp = sa.inspect(eng)
            return {t: ({c["name"]: (str(c["type"]), c["nullable"], str(c.get("default"))) for c in insp.get_columns(t)},
                        {i["name"]: (tuple(i["column_names"]), bool(i.get("unique"))) for i in insp.get_indexes(t)})
                    for t in tables}
        finally:
            eng.dispose()

    run("upgrade", "head")
    neuf = schema()
    assert neuf["depots_lien_espaces"][1]["ix_depots_lien_espaces_invite_id"] == (("invite_id",), True)
    assert neuf["depots_lien_documents"][0]["complet"][1] is False and "lecture" in neuf["depots_lien_documents"][0]
    eng = sa.create_engine(f"sqlite:///{dbfile}")
    with eng.begin() as cn:
        cn.execute(sa.text("INSERT INTO depots_lien_documents (invite_id, project_id, owner_id) VALUES (1, 1, 1)"))
        row = cn.execute(sa.text("SELECT nom, taille, lecture, complet, morceaux FROM depots_lien_documents")).one()
    eng.dispose()
    assert tuple(row) == ("", 0, "texte", 1, 0)                        # valeurs par défaut côté base
    run("downgrade", "x8y9redactionv4")
    eng = sa.create_engine(f"sqlite:///{dbfile}")
    try:
        assert not set(tables) & set(sa.inspect(eng).get_table_names())
        assert "dossier_parts_brouillons" in sa.inspect(eng).get_table_names()
    finally:
        eng.dispose()
    run("upgrade", "head")
    assert schema() == neuf
    run("stamp", "x8y9redactionv4")
    out = run("upgrade", "head")
    assert "y9z0depotlien" in out and schema() == neuf


# ═══ 11. L'écran « Vos documents pour Adjugo » ═══════════════════════════════════════

def _read(name):
    with open(os.path.join(ROOT, "app", "static", name), encoding="utf-8") as f:
        return f.read()


def test_ecran_vos_documents_pour_adjugo():
    js = _read("redaction-partenaire.js")
    assert "Vos documents pour Adjugo" in js
    assert "Seuls vous et Adjugo les lisez ; le chef de file ne les voit jamais." in js
    # Dépôt, liste, supprimer (confirmation), télécharger ; accord avec les liens vers les pages existantes.
    for x in ('"/documents"', 'btn("doc-deposer"', 'btn("doc-supprimer"', 'btn("doc-telecharger"', "new FormData()",
              '"accepte_cgu"', '"accepte_confidentialite"', "rpEsc(t.adresse)", 'target="_blank" rel="noopener"',
              'type="file"', "rpAccept(lim.types)", 'title: "Supprimer ce document ?"', "Cochez les deux cases"):
        assert x in js, x
    # La clé de l'espace en en-tête, même pour un fichier ; jamais dans une adresse ; un fichier part tel quel.
    assert "h[ENTETE] = k" in js and "cle=" not in js and "?cle" not in js
    assert "body: form ||" in js and '"/documents/" + encodeURIComponent(did) + "/fichier"' in js
    # Rien n'est interprété : les noms de fichiers et les messages passent par rpEsc.
    assert "rpEsc(d.nom)" in js and "insertAdjacentHTML" not in js
    # Section montrée dans l'espace privé seulement (clé valide), et par le compte s'il reste des documents.
    assert "if (st.docs && cleOk) h += renderDocs(st.docs);" in js
    assert 'o.mode === "lien" ? dv.possible : dv.nombre > 0' in js
    css = _read("styles.css")
    assert ".rp-docs" in css and ".rp-doc " in css


def test_fonctions_pures_de_l_ecran_documents_sous_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("node indisponible")
    js = _read("redaction-partenaire.js")
    prog = ("const window = {};\n" + js + "\nconst R = window.AdjugoRedactionPartenaire._pur;\n"
            "console.log(JSON.stringify({t: [R.rpTaille(0), R.rpTaille(812), R.rpTaille(1536), R.rpTaille(2621440)],"
            " a: R.rpAccept(['.pdf', '.docx'])}));")
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    r = json.loads(out.stdout)
    assert r["t"] == ["0 octet", "812 octets", "2 Ko", "2,5 Mo"] and r["a"] == ".pdf,.docx"
