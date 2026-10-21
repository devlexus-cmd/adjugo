"""Non-régression — audit cyber oct. 2026, 3e passe (contournements trouvés après le 2e lot).

  • deux en-têtes Content-Type ne donnent plus la grande limite des fichiers ;
  • renvoi d'invitation : expéditeur confirmé, 1 renvoi / 15 min, compté dans le plafond ;
  • création d'invitation par un compte non confirmé : lien créé, email NON envoyé ;
  • PDF dont toutes les pages pointent vers le même flux : décompressé une seule fois ;
  • compte démo : profil (email, nom) non modifiable ;
  • coffre-fort : on ne remplace ni un document à la corbeille ni une ancienne version ;
  • corbeille des marchés : contenu effacé après 30 j, restauration refusée (410) ;
  • intégrité du journal : un ancien propriétaire parti fonder une autre entreprise n'est
    vérifié que sur sa période dans l'organisation.
"""
import io
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest


def _db():
    from app.core.database import SessionLocal
    return SessionLocal()


def _register(client, verified=True, prefix="s3"):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={"email": email, "password": "motdepasse123",
                                                "full_name": prefix, "company_name": prefix + " SARL"})
    assert r.status_code == 201, r.text
    from app.models import User
    db = _db()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.email_verified = verified
        db.commit()
        uid = u.id
    finally:
        db.close()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, uid


def _project(client, h, name="AO sécu 3"):
    r = client.post("/api/projects/", headers=h, json={"name": name, "budget": 1000})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture
def mails(monkeypatch):
    sent = []
    from app.services import email as _email
    monkeypatch.setattr(_email, "is_enabled", lambda: True)
    monkeypatch.setattr(_email, "send_email", lambda to, subj, text, **k: sent.append((to, subj)) or True)
    return sent


# ── Taille de corps : deux Content-Type ───────────────────────────────────────────────
def test_deux_content_type_donnent_la_petite_limite():
    from app.main import body_limit_for, BODY_LIMIT_DEFAULT
    scope = {"method": "POST", "path": "/api/documents/", "root_path": "", "headers": [
        (b"content-type", b"application/x-www-form-urlencoded"),
        (b"content-type", b"multipart/form-data; boundary=zz")]}
    limit, _ = body_limit_for(scope)
    assert limit == BODY_LIMIT_DEFAULT


def test_un_seul_content_type_multipart_garde_la_limite_fichiers():
    from app.main import body_limit_for, BODY_LIMIT_UPLOAD
    scope = {"method": "POST", "path": "/api/documents/", "root_path": "", "headers": [
        (b"content-type", b"multipart/form-data; boundary=zz")]}
    assert body_limit_for(scope)[0] == BODY_LIMIT_UPLOAD


# ── Invitations : anti-spam ───────────────────────────────────────────────────────────
def test_renvoi_borne_et_compte_non_confirme(client, mails):
    h, _ = _register(client)
    pid = _project(client, h)
    r = client.post(f"/api/projects/{pid}/invites", headers=h,
                    json={"recipient": "partenaire@exemple.fr", "company_name": "Partenaire"})
    assert r.status_code == 200 and r.json()["emailed"] is True
    iid = r.json()["id"]
    # Renvoi immédiat : refusé (1 renvoi par lien toutes les 15 min), aucun email de plus.
    n = len(mails)
    r = client.post(f"/api/projects/{pid}/invites/{iid}/resend", headers=h)
    assert r.status_code == 429, r.text
    assert len(mails) == n
    # Après 15 min : accepté, et le renvoi est compté.
    from app.models import ProjectInvite, AuditLog
    db = _db()
    try:
        inv = db.get(ProjectInvite, iid)
        inv.emailed_at = datetime.now(timezone.utc) - timedelta(minutes=16)
        db.commit()
    finally:
        db.close()
    r = client.post(f"/api/projects/{pid}/invites/{iid}/resend", headers=h)
    assert r.status_code == 200 and r.json()["sent"] is True
    db = _db()
    try:
        assert db.query(AuditLog).filter(AuditLog.action == "invite.resent",
                                         AuditLog.target_id == iid).count() == 1
    finally:
        db.close()


def test_compte_non_confirme_lien_cree_sans_email(client, mails):
    h, _ = _register(client, verified=False, prefix="nv")
    pid = _project(client, h)
    r = client.post(f"/api/projects/{pid}/invites", headers=h,
                    json={"recipient": "cible@exemple.fr", "company_name": "Cible"})
    assert r.status_code == 200, r.text
    assert r.json()["emailed"] is False and r.json()["token"]
    assert not [m for m in mails if m[0] == "cible@exemple.fr"]
    r = client.post(f"/api/projects/{pid}/invites/{r.json()['id']}/resend", headers=h)
    assert r.status_code == 403


# ── PDF : même flux partagé par toutes les pages ──────────────────────────────────────
def test_pdf_flux_partage_decompresse_une_fois():
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, StreamObject
    from app.services.analysis import extract_text_from_pdf
    w = PdfWriter()
    w.add_blank_page(612, 792)
    content = StreamObject()
    content.set_data(b"BT /F1 12 Tf 72 712 Td (" + b"x" * 400000 + b") Tj ET")
    ref = w._add_object(content)
    w.pages[0][NameObject("/Contents")] = ref
    for _ in range(150):
        w.add_blank_page(612, 792)[NameObject("/Contents")] = ref
    buf = io.BytesIO()
    w.write(buf)
    calls = {"n": 0}
    from pypdf import PageObject
    real = PageObject.extract_text

    def counting(self, *a, **k):
        calls["n"] += 1
        return real(self, *a, **k)
    PageObject.extract_text = counting
    try:
        t0 = time.monotonic()
        extract_text_from_pdf(buf.getvalue())
        assert time.monotonic() - t0 < 10
    finally:
        PageObject.extract_text = real
    assert calls["n"] == 1


def test_pdf_budget_de_temps_respecte():
    from app.services.analysis import extract_text_from_pdf
    from pypdf import PdfWriter
    w = PdfWriter()
    for _ in range(5):
        w.add_blank_page(612, 792)
    buf = io.BytesIO()
    w.write(buf)
    # Échéance déjà dépassée : aucune page lue, pas d'exception.
    assert extract_text_from_pdf(buf.getvalue(), deadline=time.monotonic() - 1) == ""


# ── Compte démo : identité figée ──────────────────────────────────────────────────────
def test_demo_profil_non_modifiable(client):
    r = client.post("/api/auth/demo")
    if r.status_code != 200:
        pytest.skip("démo indisponible dans cet environnement")
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.put("/api/auth/me", headers=h, params={"email": "pirate@exemple.fr"})
    assert r.status_code == 403
    me = client.get("/api/auth/me", headers=h).json()
    assert me["email"] != "pirate@exemple.fr"


# ── Coffre-fort : remplacement réservé à la version courante ──────────────────────────
def test_pas_de_remplacement_d_un_document_a_la_corbeille(client):
    h, _ = _register(client, prefix="cf")
    pdf = b"%PDF-1.4\n%%EOF"
    r = client.post("/api/documents/", headers=h, files={"file": ("a.pdf", io.BytesIO(pdf), "application/pdf")},
                    data={"category": "autre"})
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    assert client.delete(f"/api/documents/{did}", headers=h).status_code == 204
    r = client.put(f"/api/documents/{did}/replace", headers=h,
                   files={"file": ("b.pdf", io.BytesIO(pdf), "application/pdf")})
    assert r.status_code == 404


# ── Corbeille des marchés ─────────────────────────────────────────────────────────────
def test_corbeille_des_marches_purgee_et_non_restaurable(client):
    h, uid = _register(client, prefix="cm")
    pid = _project(client, h, name="Marché secret à purger")
    assert client.delete(f"/api/projects/{pid}", headers=h).status_code in (200, 204)
    from app.models import Project, AuditLog
    from app.routers.rgpd import purge_trash
    from app.services import audit
    db = _db()
    try:
        audit.record(db, action="test.marker", owner_id=uid, project_id=pid, actor=f"user:{uid}")
        p = db.get(Project, pid)
        p.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=40)
        db.commit()
        res = purge_trash(db)
        assert res.get("purged_projects", 0) >= 1
        db.expire_all()
        p = db.get(Project, pid)
        assert p.name == "Marché supprimé" and p.ai_analysis == {"purged": True}
        # Le journal chaîné reste intact (aucune entrée effacée ni réécrite).
        assert audit.verify_chain(db, uid)["intact"] is True
        assert db.query(AuditLog).filter(AuditLog.project_id == pid).count() >= 1
    finally:
        db.close()
    r = client.post(f"/api/projects/{pid}/restore", headers=h)
    assert r.status_code == 410


# ── Intégrité : préfixe de chaîne pour un ancien propriétaire parti ──────────────────
def test_verify_org_chains_prefixe():
    from app.services import audit
    from app.models import User
    db = _db()
    try:
        # Journal d'un compte RÉEL : sous des clés étrangères appliquées (PostgreSQL, la production), une entrée
        # rattachée à un compte inexistant est refusée et audit.record, qui l'avale, n'écrivait rien.
        u = User(email=f"journal_{uuid.uuid4().hex[:8]}@test.fr", hashed_password="!", full_name="Journal")
        db.add(u)
        db.commit()
        oid = u.id
        audit.record(db, action="a", owner_id=oid, actor="x")
        audit.record(db, action="b", owner_id=oid, actor="x")
        from app.models import AuditLog
        cut = db.query(AuditLog).filter(AuditLog.owner_id == oid).order_by(AuditLog.id.desc()).first().id
        audit.record(db, action="c-apres-depart", owner_id=oid, actor="x")
        full = audit.verify_org_chains(db, [oid])
        pref = audit.verify_org_chains(db, [(oid, cut)])
        assert full["entries"] == 3 and pref["entries"] == 2
        assert pref["intact"] is True
    finally:
        db.close()
