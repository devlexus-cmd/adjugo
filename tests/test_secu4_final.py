"""Non-régression — audit cyber oct. 2026, contre-vérification finale (4e passe).

  • changement d'adresse : plafond d'emails de confirmation par compte, prénom échappé ;
  • démo collectivités : pas de rédaction IA, pas de conseils IA au sourcing ;
  • notifications de groupement : jamais vers une adresse non confirmée ; codes plafonnés ;
  • PDF : page à milliers de flux et formulaire appelé en boucle bornés en temps ;
  • effacement RGPD : la chaîne d'une AUTRE entreprise reste intacte (pierre tombale) ;
  • coffre-fort : restaurer une ancienne version restaure la version courante.
"""
import io
import time
import uuid

import pytest


def _db():
    from app.core.database import SessionLocal
    return SessionLocal()


def _register(client, verified=True, prefix="s4", name=None):
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={"email": email, "password": "motdepasse123",
                                                "full_name": name or prefix,
                                                "company_name": prefix + " SARL"})
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


@pytest.fixture
def mails(monkeypatch):
    sent = []
    from app.services import email as _email
    monkeypatch.setattr(_email, "is_enabled", lambda: True)

    def _send(to, subj, text, html=None, **k):
        sent.append((to, subj, html))
        return True
    monkeypatch.setattr(_email, "send_email", _send)
    import app.routers.auth as auth_mod
    monkeypatch.setattr(auth_mod, "send_email", _send)
    return sent


# ── Changement d'adresse ──────────────────────────────────────────────────────────────
def test_changement_d_adresse_plafonne_par_compte(client, mails):
    from app.routers.auth import VERIFY_MAILS_PER_DAY
    h, _ = _register(client, verified=False, prefix="me")
    codes = []
    for i in range(VERIFY_MAILS_PER_DAY + 4):
        r = client.put("/api/auth/me", headers=h,
                       json={"email": f"victime{i}_{uuid.uuid4().hex[:6]}@exemple.fr",
                             "current_password": "motdepasse123"})
        codes.append(r.status_code)
    assert 429 in codes
    confirm = [m for m in mails if "Confirmez" in m[1]]
    assert len(confirm) <= VERIFY_MAILS_PER_DAY


def test_prenom_echappe_dans_l_email():
    from app.services.email_templates import verify_email_html, reset_password_html
    evil = '<a/href="https://evil.example/login"/style="color:red">Cliquez'
    for html in (verify_email_html("https://adjugo.pro/x", evil), reset_password_html("https://adjugo.pro/x", evil)):
        assert "evil.example" not in html.split("adjugo.pro/x")[0] or "&lt;a" in html
        assert "<a/href" not in html


def test_nom_borne_a_l_inscription(client):
    h, uid = _register(client, prefix="nm", name="A" * 400)
    from app.models import User
    db = _db()
    try:
        assert len(db.get(User, uid).full_name) <= 120
    finally:
        db.close()


# ── Démo collectivités ────────────────────────────────────────────────────────────────
def test_demo_acheteur_sans_ia(client, monkeypatch):
    monkeypatch.setenv("DCE_ACCESS_CODE", "code-secret-test")
    r = client.post("/api/acheteur/demo")
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    calls = {"n": 0}
    import app.routers.dce as dce
    monkeypatch.setattr(dce, "generer_dce", lambda *a, **k: calls.__setitem__("n", calls["n"] + 1) or {})
    r = client.post("/api/dce/generate", headers=h, json={"objet": "Réfection de la toiture de l'école"})
    assert r.status_code == 403 and calls["n"] == 0
    seen = {}

    def fake_sourcer(lots, **k):
        seen.update(k)
        return {"lots": [], "global": {}, "conseils": [], "disclaimer": ""}
    monkeypatch.setattr(dce, "sourcer_lots", fake_sourcer)
    r = client.post("/api/dce/sourcing", headers=h, json={"lots": [{"numero": 1, "intitule": "Toiture"}]})
    assert r.status_code == 200 and seen.get("with_conseils") is False


# ── Notifications de groupement ───────────────────────────────────────────────────────
def test_pas_de_notification_vers_adresse_non_confirmee(client):
    from app.routers.invites import _mandataire_email
    _, uid_nv = _register(client, verified=False, prefix="mnv")
    _, uid_ok = _register(client, verified=True, prefix="mok")
    db = _db()
    try:
        assert _mandataire_email(uid_nv, db) is None
        assert _mandataire_email(uid_ok, db)
    finally:
        db.close()


def test_codes_invite_plafonnes_par_organisation(client):
    from app.routers.invites import _otp_cap_reached, OTP_DAILY_CAP_UNVERIFIED
    from app.services import audit
    _, uid = _register(client, verified=False, prefix="otp")

    class Inv:
        owner_id = uid
    db = _db()
    try:
        assert _otp_cap_reached(Inv, db) is False
        for _ in range(OTP_DAILY_CAP_UNVERIFIED):
            audit.record(db, action="guest.otp_request", owner_id=uid, actor="guest:x")
        assert _otp_cap_reached(Inv, db) is True
    finally:
        db.close()


# ── PDF : contenu d'une page borné ────────────────────────────────────────────────────
def _font(w):
    from pypdf.generic import NameObject, DictionaryObject
    return w._add_object(DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                           NameObject("/Subtype"): NameObject("/Type1"),
                                           NameObject("/BaseFont"): NameObject("/Helvetica")}))


def _flate(w, data):
    from pypdf.generic import StreamObject
    st = StreamObject()
    st.set_data(data)
    return w._add_object(st.flate_encode())


def test_pdf_page_a_milliers_de_flux():
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, ArrayObject, DictionaryObject
    from app.services.analysis import extract_text_from_pdf
    w = PdfWriter()
    page = w.add_blank_page(612, 792)
    fr = _font(w)
    body = b"BT /F1 12 Tf 72 712 Td " + b"(abc) Tj " * (2 * 1024 * 1024 // 9) + b"ET\n"
    page[NameObject("/Contents")] = ArrayObject([_flate(w, body) for _ in range(12)])
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): fr})})
    buf = io.BytesIO()
    w.write(buf)
    t0 = time.monotonic()
    extract_text_from_pdf(buf.getvalue(), max_chars=120000)
    assert time.monotonic() - t0 < 3


def test_pdf_formulaire_appele_en_boucle():
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, StreamObject, ArrayObject, DictionaryObject, NumberObject
    from app.services.analysis import extract_text_from_pdf
    w = PdfWriter()
    page = w.add_blank_page(612, 792)
    fr = _font(w)
    form = StreamObject()
    form.set_data(b"BT /F1 12 Tf 72 712 Td (" + b"y" * 200000 + b") Tj ET")
    form[NameObject("/Type")] = NameObject("/XObject")
    form[NameObject("/Subtype")] = NameObject("/Form")
    form[NameObject("/BBox")] = ArrayObject([NumberObject(0)] * 2 + [NumberObject(612), NumberObject(792)])
    form[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): fr})})
    fref = w._add_object(form.flate_encode())
    page[NameObject("/Contents")] = _flate(w, b"/Fm0 Do\n" * 3000)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/XObject"): DictionaryObject({NameObject("/Fm0"): fref}),
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): fr})})
    buf = io.BytesIO()
    w.write(buf)
    t0 = time.monotonic()
    txt = extract_text_from_pdf(buf.getvalue(), max_chars=120000)
    assert time.monotonic() - t0 < 8
    assert 0 < len(txt) <= 130000


def test_pdf_texte_normal_inchange():
    from pypdf import PdfWriter, PdfReader
    from pypdf.generic import NameObject, DictionaryObject
    from app.services.analysis import extract_text_from_pdf
    w = PdfWriter()
    fr = _font(w)
    for i in range(5):
        page = w.add_blank_page(612, 792)
        page[NameObject("/Contents")] = _flate(w, f"BT /F1 12 Tf 72 712 Td (Article {i} du CCTP) Tj ET".encode())
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): fr})})
    buf = io.BytesIO()
    w.write(buf)
    ref = "\n\n".join(p.extract_text() for p in PdfReader(io.BytesIO(buf.getvalue())).pages).strip()
    assert extract_text_from_pdf(buf.getvalue()) == ref and "Article 4" in ref


# ── Effacement RGPD : chaîne d'une autre entreprise ───────────────────────────────────
# Clés étrangères appliquées comme en production : fixture « fk_on » de tests/conftest.py (SQLite : PRAGMA ;
# PostgreSQL : contraintes réelles des migrations ; sur les deux, une ligne orpheline vérifiée refusée).


def test_effacement_ne_casse_pas_la_chaine_d_une_autre_entreprise(client, fk_on):
    from app.models import Project, AuditLog
    from app.services import audit
    h_s, uid_s = _register(client, prefix="efs")
    _, uid_g = _register(client, prefix="efg")
    r = client.post("/api/projects/", headers=h_s, json={"name": "Marché partagé", "budget": 1000})
    pid = r.json()["id"]
    db = _db()
    try:
        # G (autre entreprise) a des entrées chaînées sur le marché de S.
        audit.record(db, action="g.avant", owner_id=uid_g, actor=f"user:{uid_g}")
        audit.record(db, action="g.sur_marche_de_s", owner_id=uid_g, project_id=pid, actor=f"user:{uid_g}")
        audit.record(db, action="g.apres", owner_id=uid_g, actor=f"user:{uid_g}")
        assert audit.verify_chain(db, uid_g)["intact"] is True
    finally:
        db.close()
    r = client.post("/api/rgpd/delete-account", headers=h_s,
                    json={"password": "motdepasse123", "confirm": "SUPPRIMER"})
    assert r.status_code == 200, r.text
    db = _db()
    try:
        assert audit.verify_chain(db, uid_g)["intact"] is True
        p = db.get(Project, pid)
        assert p is not None and p.name == "Marché supprimé" and p.deleted_at is not None
        assert db.query(AuditLog).filter(AuditLog.owner_id == uid_g).count() == 3
    finally:
        db.close()


# ── Coffre-fort : restauration d'une ancienne version ─────────────────────────────────
def test_restaurer_ancienne_version_restaure_la_tete(client):
    h, _ = _register(client, prefix="cv")
    pdf = b"%PDF-1.4\n%%EOF"
    r = client.post("/api/documents/", headers=h, files={"file": ("a.pdf", io.BytesIO(pdf), "application/pdf")},
                    data={"category": "autre"})
    v1 = r.json()["id"]
    r = client.put(f"/api/documents/{v1}/replace", headers=h, files={"file": ("b.pdf", io.BytesIO(pdf), "application/pdf")})
    v2 = r.json()["id"]
    r = client.put(f"/api/documents/{v2}/replace", headers=h, files={"file": ("c.pdf", io.BytesIO(pdf), "application/pdf")})
    v3 = r.json()["id"]
    assert client.delete(f"/api/documents/{v3}", headers=h).status_code == 204
    r = client.post(f"/api/documents/{v2}/restore", headers=h)
    assert r.status_code == 200 and r.json()["id"] == v3
    from app.models import Document
    db = _db()
    try:
        assert all(db.get(Document, i).deleted_at is None for i in (v1, v2, v3))
    finally:
        db.close()
    # Remplacer deux fois la même version : le second voit une version déjà archivée.
    r = client.put(f"/api/documents/{v2}/replace", headers=h, files={"file": ("d.pdf", io.BytesIO(pdf), "application/pdf")})
    assert r.status_code in (404, 409)
