"""Non-régression — audit cybersécurité oct. 2026, 2e lot, groupe « plateforme ».

Chaque test REJOUE un contournement trouvé par les vérificateurs du 1er lot et vérifie
qu'il échoue désormais :
  - faille 2  : Idempotency-Key faisait lire en mémoire un corps de taille illimitée, sans
                compte (≈ 790 Mo de pic pour 150 Mo envoyés) ; JSON géant sur /api/auth/login
                et /api/stripe/webhook lus sans borne ;
  - faille 7  : le garde « démo » lisait request.url.path, reconstruit depuis l'en-tête Host
                (« Host: x/y » → règle contournée) ;
  - faille 8  : les membres retirés AVANT le correctif gardaient leurs jobs (à leur nom) ;
  - faille 14 : MediaBox inversée → largeur négative → rendu OCR à 200 dpi d'une page géante.
"""
import asyncio
import hashlib
import hmac
import io
import json
import sys
import time
import types
import uuid
from datetime import timedelta

import pytest

from app.core.database import SessionLocal
from app.models import AuditLog, Job, User


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _email(prefix="plat"):
    return f"{prefix}_{uuid.uuid4().hex[:8]}@test.fr"


def _register(client):
    email = _email()
    r = client.post("/api/auth/register", json={
        "email": email, "password": "motdepasse123", "full_name": "Plateforme Test",
        "company_name": "Plateforme SARL"})
    assert r.status_code == 201, r.text
    return email, r.json()["access_token"]


def _set_verified(email):
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.email_verified = True
        db.commit()
        return u.id
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Faille 2 : lecture de corps non bornée
# ─────────────────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _Source:
    """Flux ASGI simulé : `n_chunks` morceaux de `chunk` octets ; compte ce qui est lu."""

    def __init__(self, n_chunks, chunk=64 * 1024):
        self.left = n_chunks
        self.chunk = chunk
        self.read_bytes = 0

    async def receive(self):
        if self.left <= 0:
            return {"type": "http.disconnect"}
        self.left -= 1
        self.read_bytes += self.chunk
        return {"type": "http.request", "body": b"x" * self.chunk, "more_body": self.left > 0}


def _scope(headers, path="/api/auth/login", method="POST"):
    return {"type": "http", "method": method, "path": path, "root_path": "", "query_string": b"",
            "headers": [(k.encode(), v.encode()) for k, v in headers.items()]}


def _probe_app(record):
    """Application ASGI qui note ce que le middleware avait DÉJÀ lu quand elle démarre,
    puis lit tout le corps et vérifie qu'il est intact."""
    async def app(scope, receive, send):
        record["read_before_app"] = record["src"].read_bytes
        total = 0
        while True:
            m = await receive()
            if m["type"] != "http.request":
                break
            total += len(m.get("body", b""))
            if not m.get("more_body"):
                break
        record["app_got"] = total
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})
    return app


@pytest.mark.parametrize("headers", [
    # EXPLOIT d'origine : Content-Length énorme + Idempotency-Key, sans compte.
    {"idempotency-key": "k1", "content-type": "application/json", "content-length": str(150 * 1024 * 1024)},
    # Transfert « chunked » (pas de Content-Length).
    {"idempotency-key": "k2", "content-type": "application/json"},
    # Envoi de fichier : jamais mis en cache, jamais lu ici.
    {"idempotency-key": "k3", "content-type": "multipart/form-data; boundary=x", "content-length": "1000"},
])
def test_idempotency_passe_plat_sans_lire_le_corps(headers):
    from app.core.idempotency import IdempotencyMiddleware
    src = _Source(n_chunks=64)          # 4 Mo envoyés
    rec = {"src": src}
    sent = []

    async def send(m):
        sent.append(m)
    _run(IdempotencyMiddleware(_probe_app(rec))(_scope(headers), src.receive, send))
    assert rec["read_before_app"] == 0, "le middleware a lu le corps avant l'application"
    assert rec["app_got"] == 64 * 64 * 1024, "l'application doit recevoir le corps complet"


def test_idempotency_client_qui_ment_sur_la_taille():
    """Content-Length annoncé petit mais flux énorme : lecture arrêtée à 256 Ko + 1 morceau,
    puis passe-plat avec réinjection : l'application reçoit tout, intact, sans cache."""
    from app.core import idempotency as I
    src = _Source(n_chunks=64)
    rec = {"src": src}
    hdr = {"idempotency-key": "menteur-" + uuid.uuid4().hex, "content-type": "application/json",
           "content-length": "100"}
    n0 = len(I._STORE)

    async def send(m):
        pass
    _run(I.IdempotencyMiddleware(_probe_app(rec))(_scope(hdr), src.receive, send))
    assert rec["read_before_app"] <= I._MAX_REQ_BODY + 64 * 1024
    assert rec["app_got"] == 64 * 64 * 1024
    assert len(I._STORE) == n0, "une requête hors borne ne doit pas être mise en cache"


def test_idempotency_rejeu_toujours_fonctionnel(client):
    """Usage légitime : petit corps JSON + même clé → réponse rejouée sans réexécution."""
    key = "rejeu-" + uuid.uuid4().hex
    body = {"email": _email("rejeu"), "password": "motdepasse123", "full_name": "R", "company_name": "R"}
    r1 = client.post("/api/auth/register", json=body, headers={"Idempotency-Key": key})
    r2 = client.post("/api/auth/register", json=body, headers={"Idempotency-Key": key})
    assert r1.status_code == 201 and r2.status_code == 201
    assert r2.headers.get("idempotent-replayed") == "true"
    assert r1.json() == r2.json()


def test_login_json_geant_refuse_413(client):
    # EXPLOIT : JSON géant anonyme (avant : ≈ 900 Mo de pic). Avec et sans Idempotency-Key.
    big = b'{"email": "a@b.fr", "password": "' + b"x" * (3 * 1024 * 1024) + b'"}'
    for extra in ({}, {"Idempotency-Key": "geant-" + uuid.uuid4().hex}):
        r = client.post("/api/auth/login", content=big,
                        headers={"Content-Type": "application/json", **extra})
        assert r.status_code == 413, r.text
        assert "volumineu" in r.json()["detail"]


def test_login_json_geant_en_chunked_refuse_413(client):
    """Sans Content-Length (transfert par morceaux) : on compte les octets reçus."""
    def gen():
        yield b'{"email": "a@b.fr", "password": "'
        for _ in range(48):
            yield b"x" * (64 * 1024)
        yield b'"}'
    r = client.post("/api/auth/login", content=gen(),
                    headers={"Content-Type": "application/json", "Idempotency-Key": "ch-" + uuid.uuid4().hex})
    assert r.status_code == 413, r.text
    assert "volumineu" in r.json()["detail"]


def test_multipart_hors_route_upload_borne_a_2_mo(client):
    """EXPLOIT : multipart anonyme + Idempotency-Key sur /api/auth/login (avant : 788 Mo)."""
    r = client.post("/api/auth/login", headers={"Idempotency-Key": "mp-" + uuid.uuid4().hex},
                    files={"file": ("a.bin", b"x" * (3 * 1024 * 1024), "application/octet-stream")})
    assert r.status_code == 413, r.text


def test_upload_legitime_non_bloque(client, auth):
    """Un dépôt de 3 Mo sur une vraie route d'upload n'est pas touché par la borne globale."""
    pdf = b"%PDF-1.4\n" + b"0" * (3 * 1024 * 1024)
    r = client.post("/api/documents/", headers={**auth["headers"], "Idempotency-Key": uuid.uuid4().hex},
                    files={"file": ("gros.pdf", pdf, "application/pdf")}, data={"category": "autre"})
    assert r.status_code == 201, r.text


def test_borne_upload_60_mo_sur_content_length():
    """Au-delà de 60 Mo annoncés sur une route d'upload : 413 immédiat, rien n'est lu."""
    from app.main import BodySizeLimitMiddleware, body_limit_for, BODY_LIMIT_UPLOAD, BODY_LIMIT_DEFAULT
    mp = {"content-type": "multipart/form-data; boundary=x"}
    assert body_limit_for(_scope(mp, "/api/documents/"))[0] == BODY_LIMIT_UPLOAD
    assert body_limit_for(_scope(mp, "/api/invite/abc/contribution/piece"))[0] == BODY_LIMIT_UPLOAD
    assert body_limit_for(_scope(mp, "/api/documents/12/replace", "PUT"))[0] == BODY_LIMIT_UPLOAD
    assert body_limit_for(_scope(mp, "/api/auth/login"))[0] == BODY_LIMIT_DEFAULT
    assert body_limit_for(_scope({"content-type": "application/json"}, "/api/documents/"))[0] == BODY_LIMIT_DEFAULT

    src = _Source(n_chunks=10)
    called = []
    sent = []

    async def app(scope, receive, send):
        called.append(True)

    async def send(m):
        sent.append(m)
    hdr = dict(mp, **{"content-length": str(61 * 1024 * 1024)})
    _run(BodySizeLimitMiddleware(app)(_scope(hdr, "/api/documents/"), src.receive, send))
    assert not called and src.read_bytes == 0
    assert sent[0]["status"] == 413
    assert "60 Mo" in json.loads(sent[1]["body"])["detail"]


def _stripe_sig(payload: bytes, secret: str) -> str:
    t = int(time.time())
    mac = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={t},v1={mac}"


def test_webhook_stripe_corps_brut_intact_et_borne(client, monkeypatch):
    from app.routers import stripe_pay
    secret = "whsec_test_plateforme"
    monkeypatch.setattr(stripe_pay.settings, "STRIPE_WEBHOOK_SECRET", secret)
    # Corps légitime (espaces et ordre des clés conservés : la signature porte sur les octets).
    payload = ('{"id": "evt_secu2_%s", "object": "event",  "type": "ping.secu2", '
               '"data": {"object": {}}}' % uuid.uuid4().hex).encode()
    for extra in ({}, {"Idempotency-Key": "wh-" + uuid.uuid4().hex}):
        p = payload if not extra else payload.replace(b"evt_secu2_", b"evt_secu2_k")
        r = client.post("/api/stripe/webhook", content=p, headers={
            "Content-Type": "application/json", "Stripe-Signature": _stripe_sig(p, secret), **extra})
        assert r.status_code == 200, r.text   # signature valide → corps reçu octet pour octet
    # EXPLOIT : webhook géant anonyme (avant : ≈ 150 Mo de pic).
    big = b'{"id": "evt_big", "pad": "' + b"x" * (3 * 1024 * 1024) + b'"}'
    r = client.post("/api/stripe/webhook", content=big,
                    headers={"Content-Type": "application/json", "Stripe-Signature": "t=1,v1=x"})
    assert r.status_code == 413


# ─────────────────────────────────────────────────────────────────────────────
# Faille 7 : garde démo contourné par l'en-tête Host
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def demo_tok(client):
    r = client.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def sent_mails(monkeypatch):
    import app.services.email as E
    sent = []
    monkeypatch.setattr(E, "send_email", lambda to, *a, **k: (sent.append(to) or True))
    monkeypatch.setattr(E, "is_enabled", lambda: True)
    return sent


@pytest.mark.parametrize("host", ["testserver/x", "testserver?", "testserver#", "testserver/api/x?"])
def test_demo_host_forge_ne_contourne_plus(client, demo_tok, sent_mails, host):
    h = {**_h(demo_tok), "host": host}
    col = _email("col")
    r = client.post("/api/org/invite", headers=h, json={"email": col, "full_name": "x"})
    assert r.status_code == 403, r.text
    assert "démo" in r.json()["detail"]
    # « Mon avis » reste permis à la démo : le seul email part vers l'adresse fixe du fondateur.
    from app.routers.feedback import _FOUNDER
    r = client.post("/api/feedback", headers=h, json={"message": "retour visiteur", "kind": "idee"})
    assert r.status_code in (200, 201), r.text
    sent_mails[:] = [m for m in sent_mails if m != _FOUNDER]
    r = client.post("/api/documents/", headers=h,
                    files={"file": ("a.pdf", b"%PDF-1.4 x", "application/pdf")}, data={"category": "kbis"})
    assert r.status_code == 403, r.text
    assert sent_mails == []
    db = SessionLocal()
    try:
        assert db.query(User).filter(User.email == col).first() is None
    finally:
        db.close()


@pytest.mark.parametrize("path", ["//api/org/invite", "/api%2Forg/invite", "/api/org%2Finvite",
                                  "/API/org/invite", "/api/Org/Invite", "/api/org/invite/",
                                  "/api//org///invite"])
def test_demo_chemins_alternatifs_jamais_servis(client, demo_tok, sent_mails, path):
    col = _email("alt")
    r = client.post(path, headers=_h(demo_tok), json={"email": col, "full_name": "x"})
    assert r.status_code in (403, 404, 405), (path, r.status_code, r.text)
    assert sent_mails == []
    db = SessionLocal()
    try:
        assert db.query(User).filter(User.email == col).first() is None
    finally:
        db.close()


def test_demo_routed_path_unitaire():
    from app.core.demo_guard import routed_path, blocked_action
    sc = {"path": "/api/org/invite", "root_path": ""}
    assert blocked_action("POST", routed_path(sc))
    assert blocked_action("POST", routed_path({"path": "/prefix/api/org/invite", "root_path": "/prefix"}))
    assert blocked_action("POST", routed_path({"path": "//API//org/invite/", "root_path": ""}))
    assert blocked_action("GET", routed_path(sc)) is None


# ─────────────────────────────────────────────────────────────────────────────
# Faille 8 : jobs des membres retirés AVANT le correctif
# ─────────────────────────────────────────────────────────────────────────────

def test_jobs_legacy_des_membres_retires_rendus_a_l_organisation(client):
    from app.main import _repair_removed_member_jobs
    owner_email, owner_tok = _register(client)
    _set_verified(owner_email)
    r = client.post("/api/org/invite", headers=_h(owner_tok), json={"email": _email("ex")})
    assert r.status_code == 201, r.text
    m_id, m_email, m_pwd = r.json()["id"], r.json()["email"], r.json()["temp_password"]
    _set_verified(m_email)

    # Le membre a lancé une génération (job créé AVEC SON id, comme en production).
    db = SessionLocal()
    try:
        owner_id = db.query(User).filter(User.email == owner_email).first().id
        j = Job(user_id=m_id, kind="memoire", status="done", label="ancien",
                result={"secret": "SAVOIR-FAIRE-ORG-LEGACY"})
        db.add(j)
        db.commit()
        jid = j.id
    finally:
        db.close()

    r = client.delete(f"/api/org/members/{m_id}", headers=_h(owner_tok))
    assert r.status_code == 200, r.text

    # État LEGACY : avant le correctif, le retrait ne réassignait pas les jobs → on remet
    # le job au nom de l'ex-membre, exactement comme en base de production.
    db = SessionLocal()
    try:
        db.get(Job, jid).user_id = m_id
        # Job créé APRÈS le retrait dans son nouvel espace : il doit lui rester.
        later = Job(user_id=m_id, kind="memoire", status="done", label="nouveau",
                    result={"secret": "A-MOI"})
        db.add(later)
        db.commit()
        later.created_at = later.created_at + timedelta(seconds=5)
        db.commit()
        later_id = later.id
        chain_before = [(a.id, a.owner_id, a.entry_hash) for a in
                        db.query(AuditLog).order_by(AuditLog.id).all()]
    finally:
        db.close()

    m_tok = client.post("/api/auth/login", json={"email": m_email, "password": m_pwd}).json()["access_token"]
    # EXPLOIT (sans réparation) : l'ex-membre relit le résultat de l'organisation.
    assert client.get(f"/api/jobs/{jid}", headers=_h(m_tok)).status_code == 200

    _repair_removed_member_jobs()

    r = client.get(f"/api/jobs/{jid}", headers=_h(m_tok))
    assert r.status_code == 404 and "SAVOIR-FAIRE-ORG-LEGACY" not in r.text
    assert client.get(f"/api/jobs/{jid}", headers=_h(owner_tok)).status_code == 200
    assert client.get(f"/api/jobs/{later_id}", headers=_h(m_tok)).status_code == 200

    # Idempotent, et le journal chaîné n'est jamais réécrit.
    _repair_removed_member_jobs()
    db = SessionLocal()
    try:
        assert db.get(Job, jid).user_id == owner_id
        assert db.get(Job, later_id).user_id == m_id
        after = {a.id: (a.id, a.owner_id, a.entry_hash) for a in db.query(AuditLog).all()}
        for entry in chain_before:
            assert after.get(entry[0]) == entry, "une entrée du journal a été modifiée"
    finally:
        db.close()


def test_reparation_jamais_bloquante(monkeypatch):
    """Base indisponible au démarrage : la réparation logge et rend la main."""
    import app.main as M

    class _Boom:
        def query(self, *a, **k):
            raise RuntimeError("base indisponible")

        def rollback(self):
            pass

        def close(self):
            pass
    monkeypatch.setattr("app.core.database.SessionLocal", lambda: _Boom())
    assert M._repair_removed_member_jobs() == 0


# ─────────────────────────────────────────────────────────────────────────────
# Faille 14 : rendu OCR borné quelle que soit la boîte de page
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def render_calls(monkeypatch):
    calls = []

    def convert_from_bytes(content, **kw):
        calls.append(kw)
        return [object()]
    monkeypatch.setitem(sys.modules, "pdf2image", types.SimpleNamespace(convert_from_bytes=convert_from_bytes))
    monkeypatch.setitem(sys.modules, "pytesseract", types.SimpleNamespace(
        image_to_string=lambda img, lang=None: "texte"))
    return calls


def _pdf_with_box(box):
    from pypdf import PdfWriter
    from pypdf.generic import ArrayObject, FloatObject, NameObject
    w = PdfWriter()
    p = w.add_blank_page(width=595, height=842)
    p[NameObject("/MediaBox")] = ArrayObject([FloatObject(v) for v in box])
    b = io.BytesIO()
    w.write(b)
    return b.getvalue()


def _rendered_side_px(kw, side_pt):
    if kw.get("size"):
        return kw["size"]                       # pdftoppm -scale-to : borne en pixels
    return side_pt * kw["dpi"] / 72


@pytest.mark.parametrize("box,side", [
    ([9500, 9500, 0, 0], 9500),                 # EXPLOIT : MediaBox inversée
    ([14400, 14400, 0, 0], 14400),
    ([0, 14400, 14400, 0], 14400),              # inversée sur un seul axe
    ([-7200, -7200, 7200, 7200], 14400),        # origine négative
    ([0, 0, 400000, 400000], 400000),           # si grande que 10 dpi dépasserait le plafond
])
def test_ocr_boite_inversee_ou_geante_bornee(render_calls, box, side):
    from app.services import analysis
    analysis._ocr_pdf(_pdf_with_box(box), max_pages=1)
    assert render_calls, "aucun rendu demandé"
    assert _rendered_side_px(render_calls[0], side) <= analysis.OCR_MAX_SIDE_PX, render_calls[0]


def test_ocr_pdf_illisible_par_pypdf_borne_en_pixels(render_calls):
    from app.services import analysis
    analysis._ocr_pdf(b"%PDF-1.4\n%%%% pas un vrai PDF %%%%\n" + b"\x00" * 64, max_pages=1)
    assert render_calls, "aucun rendu demandé"
    assert render_calls[0].get("size") == analysis.OCR_MAX_SIDE_PX


def test_ocr_page_a4_inchangee(render_calls):
    from app.services import analysis
    analysis._ocr_pdf(_pdf_with_box([0, 0, 595, 842]), max_pages=1)
    assert render_calls[0]["dpi"] == analysis.OCR_DPI
    assert "size" not in render_calls[0]
