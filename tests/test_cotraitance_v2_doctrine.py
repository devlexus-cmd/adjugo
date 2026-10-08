"""
Co-traitance v2 — vague 1 : doctrine de visibilité (D), déclin, journal membre,
coffre-fort croisé (E), « Figer l'offre », vue co-traitant « pourquoi vous ».

Invariants vérifiés ici :
- le mandataire voit le PRIX DE VENTE du lot (prix_lot_ht), JAMAIS l'enveloppe chiffrée
  (detail_chiffre) ni l'ancienne approche prix (chiffrage_note) ;
- un partenaire qui DÉCLINE sort partout (lien 410, cockpit, checklist) ;
- le journal du membre ne contient ni ip ni email, et pas les entrées d'un autre membre ;
- la grille du coffre croisé expose des STATUTS, pas les fichiers des autres ;
- le total de l'offre commune n'apparaît au membre qu'une fois l'offre figée ; toute
  modification de prix la défige ;
- « joindre depuis mon coffre-fort » copie le fichier sans exposer le Document d'origine ;
- le compte-rendu PDF n'imprime plus aucune « approche prix ».
"""
import base64
import io
import json
import uuid
from datetime import date, timedelta

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────
def _register(client, company="Autre SARL"):
    email = f"u_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={
        "email": email, "password": "motdepasse123", "full_name": "Partenaire", "company_name": company})
    assert r.status_code == 201, r.text
    from app.core.database import SessionLocal
    from app.models import User
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.email_verified = True
        db.commit()
    finally:
        db.close()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, email


def _project(client, headers, name="AO Groupement v2", deadline_days=30):
    r = client.post("/api/projects/", headers=headers, json={
        "name": name, "budget": 100000,
        "deadline": (date.today() + timedelta(days=deadline_days)).isoformat()})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _invite(client, headers, pid, company="Partenaire SARL", recipient=""):
    r = client.post(f"/api/projects/{pid}/invites", headers=headers,
                    json={"recipient": recipient, "company_name": company})
    assert r.status_code == 200, r.text
    return r.json()


def _contrib(client, token):
    r = client.get(f"/api/invite/{token}/contribution")
    assert r.status_code == 200, r.text
    return r.json()


def _put(client, token, **fields):
    v = _contrib(client, token)["version"]
    r = client.put(f"/api/invite/{token}/contribution", json={"version": v, **fields})
    return r


def _submit(client, token):
    r = client.post(f"/api/invite/{token}/contribution/submit")
    assert r.status_code == 200, r.text
    return r.json()


def _envelope(**over):
    env = {
        "ciphertext": base64.b64encode(b"x" * 64).decode(),
        "iv": base64.b64encode(b"\x01" * 12).decode(),        # 12 octets → 16 caractères
        "alg": "A256GCM", "kdf": "PBKDF2-SHA256",
        "kdf_salt": base64.b64encode(b"\x02" * 16).decode(),
        "kdf_iter": 600000, "key_fingerprint": "ab12cd34",
        "updated_at": "2026-10-06T10:00:00+00:00",
    }
    env.update(over)
    return env


def _upload(client, token, filename, data=b"%PDF-1.4 test", **form):
    return client.post(f"/api/invite/{token}/contribution/piece",
                       files={"file": (filename, io.BytesIO(data), "application/pdf")}, data=form)


# ── (a) Doctrine : prix de lot visible, enveloppe jamais côté mandataire ──────
def test_doctrine_prix_visible_detail_chiffre_jamais_mandataire(client, auth):
    h = auth["headers"]
    pid = _project(client, h)
    token = _invite(client, h, pid)["token"]

    r = _put(client, token, lot="Lot 2 — Électricité", prix_lot_ht=125000.5,
             detail_chiffre=_envelope(), representant_legal="Jean Le Gall",
             signataire_qualite="Gérant", chiffrage_note="FUITE : marge 18 %")
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["prix_lot_ht"] == 125000.5
    assert me["detail_chiffre"]["alg"] == "A256GCM"       # le membre relit SON enveloppe
    assert "chiffrage_note" not in me
    assert me["representant_legal"] == "Jean Le Gall" and me["signataire_qualite"] == "Gérant"

    # Côté mandataire : prix oui, enveloppe ABSENTE (pas null), ancienne approche prix absente.
    owner_view = client.get(f"/api/projects/{pid}/contributions", headers=h).json()
    assert len(owner_view) == 1
    o = owner_view[0]
    assert o["prix_lot_ht"] == 125000.5
    assert "detail_chiffre" not in o
    assert o["has_detail_chiffre"] is True
    assert "chiffrage_note" not in o
    assert "FUITE" not in json.dumps(owner_view)

    # Vague 4 : la colonne dépréciée n'existe plus (supprimée, migration q1r2s3t4u5v6).
    from app.core.database import SessionLocal
    from app.models import ProjectContribution
    db = SessionLocal()
    try:
        c = db.query(ProjectContribution).filter(ProjectContribution.project_id == pid).first()
        assert c is not None and not hasattr(c, "chiffrage_note")
        assert "chiffrage_note" not in ProjectContribution.__table__.columns
    finally:
        db.close()

    # Cockpit : has_price + prix_lot_ht (vue mandataire), jamais l'enveloppe.
    ck = client.get(f"/api/projects/{pid}/consortium", headers=h).json()
    p = ck["partners"][0]
    assert p["has_price"] is True and p["prix_lot_ht"] == 125000.5
    assert "has_chiffrage" not in p and "detail_chiffre" not in p
    assert "ciphertext" not in json.dumps(ck) and p["has_detail_chiffre"] is True

    # Effacer l'enveloppe : {} ou None.
    r = _put(client, token, detail_chiffre={})
    assert r.status_code == 200 and r.json()["detail_chiffre"] is None
    assert client.get(f"/api/projects/{pid}/contributions", headers=h).json()[0]["has_detail_chiffre"] is False


# ── (b) Enveloppe invalide → 422 ─────────────────────────────────────────────
@pytest.mark.parametrize("bad", [
    {"alg": "AES-CBC"},
    {"kdf_iter": 1000},
    {"iv": base64.b64encode(b"\x01" * 8).decode()},
    {"extra": "x"},
    {"ciphertext": "not base64!!"},
    {"updated_at": "hier"},
])
def test_enveloppe_invalide_422(client, auth, bad):
    h = auth["headers"]
    pid = _project(client, h)
    token = _invite(client, h, pid)["token"]
    env = _envelope(**bad)
    r = _put(client, token, detail_chiffre=env)
    assert r.status_code == 422, r.text
    assert "Enveloppe chiffrée invalide" in r.text


def test_prix_lot_borne(client, auth):
    h = auth["headers"]
    pid = _project(client, h)
    token = _invite(client, h, pid)["token"]
    assert _put(client, token, prix_lot_ht=-1).status_code == 422
    assert _put(client, token, prix_lot_ht=2e10).status_code == 422
    r = _put(client, token, prix_lot_ht=None)
    assert r.status_code == 200 and r.json()["prix_lot_ht"] is None


# ── (c) Déclin : le membre sort partout ──────────────────────────────────────
def test_decline_sort_du_groupement(client, auth):
    h = auth["headers"]
    pid = _project(client, h)
    inv = _invite(client, h, pid, company="Qui Décline SARL")
    token = inv["token"]
    _put(client, token, lot="Lot 1", prix_lot_ht=1000)
    _submit(client, token)
    assert client.get(f"/api/projects/{pid}/consortium", headers=h).json()["readiness"]["invited"] == 1

    r = client.post(f"/api/invite/{token}/decline")
    assert r.status_code == 200 and r.json()["ok"] is True
    # Lien mort : 410 avec message clair ; second déclin impossible.
    r = client.get(f"/api/invite/{token}")
    assert r.status_code == 410 and "décliné" in r.text
    assert client.post(f"/api/invite/{token}/decline").status_code == 410

    # Plus membre nulle part.
    from app.core.database import SessionLocal
    from app.models import Project
    from app.services.groupement_members import active_invites
    from app.routers.checklist import _is_groupement
    db = SessionLocal()
    try:
        assert active_invites(db, pid) == []
        assert _is_groupement(db.query(Project).get(pid), db) is False
    finally:
        db.close()
    ck = client.get(f"/api/projects/{pid}/consortium", headers=h).json()
    assert ck["readiness"]["invited"] == 0 and ck["partners"] == []
    assert ck["state"]["n_members"] == 0

    # Vue mandataire : état calculé « declined », resend refusé, part repassée en brouillon.
    lst = client.get(f"/api/projects/{pid}/invites", headers=h).json()
    assert lst[0]["state"] == "declined" and lst[0]["declined_at"]
    assert lst[0]["contribution_status"] == "draft"
    assert client.post(f"/api/projects/{pid}/invites/{inv['id']}/resend", headers=h).status_code == 400
    # Notification in-app libellée.
    notifs = client.get("/api/notifications", headers=h).json()
    assert any(n["action"] == "invite.declined" and n["label"] == "a décliné l'invitation"
               and n["actor"] == "Qui Décline SARL" for n in notifs)


# ── (d) Journal membre : « qui a vu quoi », sans ip/email, cloisonné ──────────
def test_journal_membre_projection(client, auth):
    h = auth["headers"]
    pid = _project(client, h)
    t1 = _invite(client, h, pid, company="Alpha SARL", recipient="alpha@secret.fr")["token"]
    t2 = _invite(client, h, pid, company="Beta SAS", recipient="beta@secret.fr")["token"]
    client.get(f"/api/invite/{t1}")                                   # guest.view_project (Alpha)
    _put(client, t1, lot="Lot A", prix_lot_ht=10)
    _submit(client, t1)
    # Le mandataire consulte les parts (seule Alpha a une contribution) et télécharge une pièce.
    up = _upload(client, t1, "extrait_kbis.pdf")
    assert up.status_code == 200, up.text
    client.get(f"/api/projects/{pid}/contributions", headers=h)
    client.get(f"/api/projects/{pid}/contributions", headers=h)       # dédoublonné (1/heure)
    dl = client.get(f"/api/projects/{pid}/contribution-pieces/{up.json()['id']}", headers=h)
    assert dl.status_code == 200

    j1 = client.get(f"/api/invite/{t1}/journal")
    assert j1.status_code == 200, j1.text
    body = j1.json()
    assert body["integrity_label"] == "Journal vérifiable : toute modification ou suppression d'entrée est détectable"
    assert body["chained"] is True
    labels = [e["label"] for e in body["entries"]]
    assert "Le mandataire a consulté votre part" in labels
    assert labels.count("Le mandataire a consulté votre part") == 1
    assert any(l.startswith("Le mandataire a téléchargé votre pièce « extrait_kbis.pdf »") for l in labels)
    assert "Vous avez consulté le dossier" in labels
    assert "Vous avez soumis votre part" in labels
    raw = json.dumps(body, ensure_ascii=False)
    assert "@" not in raw and "secret.fr" not in raw
    assert "ip" not in body["entries"][0] and "target_id" not in body["entries"][0]
    assert all(e["who"] in ("vous", "mandataire", "partenaire") for e in body["entries"])

    # Beta ne voit PAS les entrées d'Alpha (hors événements de groupement).
    j2 = client.get(f"/api/invite/{t2}/journal").json()
    labels2 = [e["label"] for e in j2["entries"]]
    assert "Le mandataire a consulté votre part" not in labels2
    assert "Vous avez soumis votre part" not in labels2
    assert not any("téléchargé" in l for l in labels2)
    # …mais voit l'événement de groupement « un partenaire a été invité » (Alpha), sans email.
    grp = [e for e in j2["entries"] if e["action"] == "invite.created"]
    assert any(e["who"] == "partenaire" and e["detail"] == "Alpha SARL" for e in grp)
    assert any(e["who"] == "mandataire" and e["label"] == "Le mandataire vous a invité" for e in grp)
    assert "@" not in json.dumps(j2, ensure_ascii=False)

    # Journal mandataire (inchangé) : l'acteur invité est le nom d'entreprise, pas l'email.
    pa = client.get(f"/api/projects/{pid}/audit", headers=h).json()
    guest_actors = {e["actor"] for e in pa if e["actor_kind"] == "guest"}
    assert guest_actors and all("@" not in a for a in guest_actors)


# ── (e) Coffre-fort croisé : classification, expiration, statuts ─────────────
def test_coffre_croise_statuts(client, auth):
    h = auth["headers"]
    pid = _project(client, h, deadline_days=30)
    t1 = _invite(client, h, pid, company="Alpha SARL")["token"]
    t2 = _invite(client, h, pid, company="Beta SAS")["token"]
    up = _upload(client, t1, "attestation_urssaf.pdf")
    assert up.status_code == 200, up.text
    piece = up.json()
    assert piece["piece_type"] == "sociale"
    assert piece["expiration_date"] is None and "source_document_id" in piece

    # PATCH : expiration avant la date limite.
    exp = (date.today() + timedelta(days=10)).isoformat()
    r = client.patch(f"/api/invite/{t1}/contribution/piece/{piece['id']}", json={"expiration_date": exp})
    assert r.status_code == 200 and r.json()["expiration_date"] == exp
    assert client.patch(f"/api/invite/{t1}/contribution/piece/{piece['id']}",
                        json={"expiration_date": "pas-une-date"}).status_code == 422
    assert client.patch(f"/api/invite/{t1}/contribution/piece/{piece['id']}",
                        json={"piece_type": "inconnu"}).status_code == 422
    # Beta ne peut pas toucher la pièce d'Alpha.
    assert client.patch(f"/api/invite/{t2}/contribution/piece/{piece['id']}",
                        json={"piece_type": "kbis"}).status_code == 404

    # Grille mandataire.
    g = client.get(f"/api/projects/{pid}/coffre-croise", headers=h).json()
    assert [e["key"] for e in g["expected"]] == ["kbis", "fiscale", "sociale", "assurance", "rib"]
    alpha = next(m for m in g["members"] if m["company"] == "Alpha SARL")
    assert alpha["invite_id"] and alpha["pieces"]["sociale"]["status"] == "expire_avant_limite"
    assert alpha["pieces"]["sociale"]["name"] == "attestation_urssaf.pdf"
    assert alpha["pieces"]["kbis"]["status"] == "manquant" and alpha["complete"] is False
    assert g["all_complete"] is False
    assert any("Attest. sociale (URSSAF) de Alpha SARL expire avant la date limite" == a for a in g["alerts"])
    assert any(a.startswith("Kbis manquante : Beta SAS") for a in g["alerts"])

    # Grille membre (Beta) : statut de la pièce d'Alpha visible, mais SANS nom ni id.
    gb = client.get(f"/api/invite/{t2}/coffre-croise").json()
    alpha_b = next(m for m in gb["members"] if m["company"] == "Alpha SARL")
    assert alpha_b["is_me"] is False and "invite_id" not in alpha_b
    assert alpha_b["pieces"]["sociale"]["status"] == "expire_avant_limite"
    assert "name" not in alpha_b["pieces"]["sociale"] and "piece_id" not in alpha_b["pieces"]["sociale"]
    beta_b = next(m for m in gb["members"] if m["company"] == "Beta SAS")
    assert beta_b["is_me"] is True

    # Cockpit : le coffre et l'alerte remontent dans les manques.
    ck = client.get(f"/api/projects/{pid}/consortium", headers=h).json()
    assert ck["coffre"]["all_complete"] is False
    assert any("expire avant la date limite" in m for m in ck["readiness"]["missing"])

    # Expirée → 'expire' ; valide après la date limite → 'valide_jusquau' ; sans date → 'present'.
    past = (date.today() - timedelta(days=1)).isoformat()
    client.patch(f"/api/invite/{t1}/contribution/piece/{piece['id']}", json={"expiration_date": past})
    assert client.get(f"/api/projects/{pid}/coffre-croise", headers=h).json()["members"][0]["pieces"]["sociale"]["status"] == "expire"
    far = (date.today() + timedelta(days=400)).isoformat()
    client.patch(f"/api/invite/{t1}/contribution/piece/{piece['id']}", json={"expiration_date": far})
    assert client.get(f"/api/projects/{pid}/coffre-croise", headers=h).json()["members"][0]["pieces"]["sociale"]["status"] == "valide_jusquau"
    client.patch(f"/api/invite/{t1}/contribution/piece/{piece['id']}", json={"expiration_date": ""})
    assert client.get(f"/api/projects/{pid}/coffre-croise", headers=h).json()["members"][0]["pieces"]["sociale"]["status"] == "present"

    # Upload avec type + date explicites, et classification « qualification ».
    up2 = _upload(client, t1, "certificat_qualibat_1234.pdf", expiration_date=far)
    assert up2.json()["piece_type"] == "qualification" and up2.json()["expiration_date"] == far
    up3 = _upload(client, t1, "doc.pdf", piece_type="rib")
    assert up3.json()["piece_type"] == "rib"
    assert _upload(client, t1, "doc2.pdf", piece_type="nimporte").status_code == 422


# ── (f) Figer l'offre ────────────────────────────────────────────────────────
def test_figer_offre(client, auth):
    h = auth["headers"]
    pid = _project(client, h)
    inv = _invite(client, h, pid, company="Alpha SARL")
    token = inv["token"]

    # Avant soumission : rien à figer, message clair (422 listant les manques).
    r = client.post(f"/api/projects/{pid}/offre/figer", headers=h, json={})
    assert r.status_code == 422 and "n'a pas encore soumis sa part" in r.text

    _put(client, token, lot="Lot A")
    _submit(client, token)
    r = client.post(f"/api/projects/{pid}/offre/figer", headers=h, json={})
    assert r.status_code == 422 and "prix de lot manquant" in r.text

    # Avant figement : le membre ne voit PAS de total.
    fm = client.get(f"/api/invite/{token}").json()["for_member"]
    assert fm["state"]["offer_frozen"] is False and fm["state"]["total_offre_ht"] is None
    assert fm["warning_two_members"] is True
    assert "has_price" not in json.dumps(fm["state"]["members"])
    assert "match_score" not in json.dumps(fm)

    _put(client, token, prix_lot_ht=40000)
    _submit(client, token)
    r = client.post(f"/api/projects/{pid}/offre/figer", headers=h, json={"lead_total_ht": 60000})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["total_ht"] == 100000.0 and body["n_members"] == 1
    assert body["warning_two_members"] is True and body["frozen_at"]

    # Après : total visible du membre ; plan stocké avec un NOUVEAU dict (détecté par SQLAlchemy).
    fm = client.get(f"/api/invite/{token}").json()["for_member"]
    assert fm["state"]["offer_frozen"] is True and fm["state"]["total_offre_ht"] == 100000.0
    assert fm["state"]["state"] == "parts_completes"
    ck = client.get(f"/api/projects/{pid}/consortium", headers=h).json()
    assert ck["offre"]["frozen"] is True and ck["offre"]["total_ht"] == 100000.0
    assert ck["state"]["offer_frozen"] is True

    # Journal membre : « Le mandataire a figé l'offre commune ».
    labels = [e["label"] for e in client.get(f"/api/invite/{token}/journal").json()["entries"]]
    assert "Le mandataire a figé l'offre commune" in labels

    # Le membre modifie son prix → offre DÉFIGÉE.
    r = _put(client, token, prix_lot_ht=41000)
    assert r.status_code == 200
    ck = client.get(f"/api/projects/{pid}/consortium", headers=h).json()
    assert ck["offre"]["frozen"] is False and ck["state"]["offer_frozen"] is False
    fm = client.get(f"/api/invite/{token}").json()["for_member"]
    assert fm["state"]["total_offre_ht"] is None
    labels = [e["label"] for e in client.get(f"/api/invite/{token}/journal").json()["entries"]]
    assert "Votre modification a défigé l'offre commune" in labels

    # Re-figer puis défiger explicitement par le mandataire.
    _submit(client, token)
    assert client.post(f"/api/projects/{pid}/offre/figer", headers=h, json={"lead_total_ht": 1}).status_code == 200
    r = client.delete(f"/api/projects/{pid}/offre/figer", headers=h)
    assert r.status_code == 200 and r.json()["was_frozen"] is True
    assert client.get(f"/api/projects/{pid}/consortium", headers=h).json()["offre"]["frozen"] is False


# ── (g) Joindre depuis mon coffre-fort ───────────────────────────────────────
def test_from_vault_copie_sans_exposer_document(client, auth):
    h = auth["headers"]
    pid = _project(client, h)
    token = _invite(client, h, pid, company="Partenaire Avec Compte")["token"]

    partner_h, _ = _register(client, company="Partenaire Avec Compte")
    # Sans claim → 403.
    assert client.post(f"/api/invite/{token}/contribution/piece/from-vault", headers=partner_h,
                       json={"document_id": 1}).status_code == 403
    assert client.post(f"/api/invite/{token}/claim", headers=partner_h).status_code == 200

    content = b"%PDF-1.4 attestation urssaf du partenaire"
    exp = (date.today() + timedelta(days=90)).isoformat()
    up = client.post("/api/documents/", headers=partner_h,
                     files={"file": ("attestation_urssaf.pdf", io.BytesIO(content), "application/pdf")},
                     data={"category": "fiscal", "expiration_date": exp})
    assert up.status_code == 201, up.text
    doc_id = up.json()["id"]

    r = client.post(f"/api/invite/{token}/contribution/piece/from-vault", headers=partner_h,
                    json={"document_id": doc_id})
    assert r.status_code == 200, r.text
    piece = r.json()
    assert piece["source_document_id"] == doc_id
    assert piece["piece_type"] == "sociale" and piece["expiration_date"] == exp

    # Le mandataire télécharge la COPIE (octets identiques) ; la vue owner ne révèle pas l'id source.
    dl = client.get(f"/api/projects/{pid}/contribution-pieces/{piece['id']}", headers=h)
    assert dl.status_code == 200 and dl.content == content
    owner_pieces = client.get(f"/api/projects/{pid}/contributions", headers=h).json()[0]["pieces"]
    assert owner_pieces and "source_document_id" not in owner_pieces[0]
    # Le Document d'origine n'apparaît pas dans le coffre-fort du mandataire.
    assert all(d["id"] != doc_id for d in client.get("/api/documents/", headers=h).json())
    # Le fichier copié vit sous le tenant du mandataire, pas sous celui du partenaire.
    from app.core.database import SessionLocal
    from app.models import ContributionPiece, Document
    db = SessionLocal()
    try:
        pc = db.query(ContributionPiece).get(piece["id"])
        src = db.query(Document).get(doc_id)
        assert pc.file_key != src.file_key and "/cotraitant/" in pc.file_key
    finally:
        db.close()
    # Un autre compte ne peut pas joindre depuis ce lien ; un document étranger → 404.
    other_h, _ = _register(client)
    assert client.post(f"/api/invite/{token}/contribution/piece/from-vault", headers=other_h,
                       json={"document_id": doc_id}).status_code == 403
    assert client.post(f"/api/invite/{token}/contribution/piece/from-vault", headers=partner_h,
                       json={"document_id": 999999}).status_code == 404


# ── (h) Compte-rendu PDF : plus d'« Approche prix » ──────────────────────────
def test_consortium_report_sans_approche_prix(client, auth):
    import pathlib
    from app.services.consortium_report import generate_consortium_report_pdf
    src = pathlib.Path("app/services/consortium_report.py").read_text(encoding="utf-8")
    code_lines = [l for l in src.splitlines() if not l.strip().startswith("#") and '"""' not in l]
    assert not any("chiffrage_note" in l or "Approche prix" in l for l in code_lines)

    data = {"readiness": {"pct": 50, "submitted": 1, "invited": 1, "missing": []},
            "partners": [{"company": "Alpha", "status": "submitted", "completeness": 50, "pieces_count": 0}],
            "lots": [], "state": {"offer_frozen": True, "total_offre_ht": 100000, "frozen_at": "2026-10-06T10:00:00"}}
    contribs = [{"company_name": "Alpha", "status": "submitted", "lot": "A",
                 "chiffrage_note": "SECRET marge 18 %", "prix_lot_ht": 40000, "memoire_paragraph": "ok"}]
    pdf = generate_consortium_report_pdf("AO", "Mandataire", data, contribs)
    assert pdf[:4] == b"%PDF"

    # Route : 200 PDF.
    h = auth["headers"]
    pid = _project(client, h)
    _invite(client, h, pid)
    r = client.get(f"/api/projects/{pid}/consortium/report", headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/pdf")


# ── Capacités déclarées par le partenaire → journal + annuaire du mandataire ──
def test_capacites_declarees_sync_annuaire(client, auth):
    h = auth["headers"]
    pid = _project(client, h)
    token = _invite(client, h, pid, company="Le Gall Électricité")["token"]
    from app.core.database import SessionLocal
    from app.models import User
    from app.routers.cotraitants import Cotraitant
    db = SessionLocal()
    try:
        owner = db.query(User).filter(User.email == auth["email"]).first()
        # Partenaire RATTACHÉ à ce projet via cette invitation → synchronisé.
        ct = Cotraitant(user_id=owner.id, name="le gall électricité", ca_n1=0, effectif=0)
        # Homonyme NON rattaché : un invité (jeton seul) ne doit JAMAIS pouvoir réécrire ses
        # capacités (fausse provenance « déclaré par le partenaire » sur une autre fiche).
        other = Cotraitant(user_id=owner.id, name="Le Gall Électricité", ca_n1=50000, effectif=3)
        db.add(ct); db.add(other)
        db.commit()
        ct_id, other_id = ct.id, other.id
    finally:
        db.close()
    # Rattachement au projet lié à l'invitation (ce que fait « retenir » / l'invitation réseau).
    from app.core.database import SessionLocal as _SL
    from app.models import ProjectInvite
    from app.routers.cotraitants import ProjectCotraitant
    db = _SL()
    try:
        inv = db.query(ProjectInvite).filter(ProjectInvite.token == token).first()
        db.add(ProjectCotraitant(project_id=pid, cotraitant_id=ct_id, role="cotraitant", lot="",
                                 source="simulation", invite_id=inv.id))
        db.commit()
    finally:
        db.close()

    r = _put(client, token, capacites={"ca_n1": 1850000, "effectif": 14}, qualifications=["Qualifelec", "RGE"])
    assert r.status_code == 200, r.text
    cap = r.json()["capacites"]
    assert cap["ca_n1"] == 1850000 and cap["effectif"] == 14 and cap["declared_at"]

    db = SessionLocal()
    try:
        ct = db.query(Cotraitant).get(ct_id)
        assert ct.ca_n1 == 1850000 and ct.effectif == 14
        assert ct.capacites_source == "contribution" and ct.capacites_updated_at is not None
        assert "Qualifelec" in (ct.qualifications or "")
        other = db.query(Cotraitant).get(other_id)
        assert other.ca_n1 == 50000 and other.effectif == 3 and (other.capacites_source or "declare") != "contribution", \
            "un homonyme non rattaché ne doit jamais être réécrit par un invité"
    finally:
        db.close()
    notifs = client.get("/api/notifications", headers=h).json()
    assert any(n["action"] == "guest.capacites_updated" and n["label"] == "a mis à jour ses capacités"
               for n in notifs)
    # Vue membre : my_capacites.
    fm = client.get(f"/api/invite/{token}").json()["for_member"]
    assert fm["my_capacites"]["ca_n1"] == 1850000
    assert _put(client, token, capacites={"ca_n1": -5}).status_code == 422
