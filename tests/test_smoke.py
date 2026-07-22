"""Tests de fumée — flux critiques d'Adjugo."""
import io


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_app_served(client):
    assert client.get("/app").status_code == 200


# ── Auth ──

def test_register_login_me(client, auth):
    me = client.get("/api/auth/me", headers=auth["headers"])
    assert me.status_code == 200
    assert me.json()["email"] == auth["email"]


def test_me_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401


def test_login_wrong_password(client, auth):
    r = client.post("/api/auth/login", json={"email": auth["email"], "password": "faux"})
    assert r.status_code in (400, 401)


# ── Profil / critères ──

def test_company_update(client, auth):
    r = client.put("/api/company/", headers=auth["headers"],
                   json={"name": "BTP Test", "city": "Quimper", "ca_n1": 500000, "effectif": 8})
    assert r.status_code == 200
    assert client.get("/api/company/", headers=auth["headers"]).json()["name"] == "BTP Test"


def test_criteria_update(client, auth):
    r = client.put("/api/criteria/", headers=auth["headers"],
                   json={"budget_min": 10000, "budget_max": 800000, "go_threshold": 60, "nogo_threshold": 40})
    assert r.status_code == 200


# ── Co-traitants ──

def test_cotraitant_crud(client, auth):
    h = auth["headers"]
    r = client.post("/api/cotraitants/", headers=h,
                    json={"name": "Élec Test", "specialites": "Électricité", "codes_cpv": "45310000"})
    assert r.status_code in (200, 201)
    lst = client.get("/api/cotraitants/", headers=h).json()
    assert any(c["name"] == "Élec Test" for c in lst)
    cid = next(c["id"] for c in lst if c["name"] == "Élec Test")
    assert client.delete(f"/api/cotraitants/{cid}", headers=h).status_code in (200, 204)


def test_registre_trades(client, auth):
    r = client.get("/api/registre/trades", headers=auth["headers"])
    assert r.status_code == 200 and len(r.json()) >= 10


# ── Documents (storage local + validation) ──

def test_document_upload_download_validate(client, auth):
    h = auth["headers"]
    content = b"%PDF-1.4 contenu de test"
    up = client.post("/api/documents/", headers=h,
                     files={"file": ("kbis.pdf", io.BytesIO(content), "application/pdf")},
                     data={"name": "Kbis", "category": "administratif"})
    assert up.status_code == 201, up.text
    doc_id = up.json()["id"]

    dl = client.get(f"/api/documents/{doc_id}/download", headers=h)
    assert dl.status_code == 200 and dl.content == content

    bad = client.post("/api/documents/", headers=h,
                      files={"file": ("malware.exe", io.BytesIO(b"x"), "application/octet-stream")})
    assert bad.status_code == 400  # extension refusée

    assert client.delete(f"/api/documents/{doc_id}", headers=h).status_code == 204


# ── Quota par plan ──

def test_quota_blocks_at_limit(client, auth):
    # Mettre le compteur du nouvel utilisateur AU PLAFOND EFFECTIF — lu via quota._limit
    # (un compte fraîchement inscrit est en essai gratuit 30j = accès niveau Pro, plus
    # « starter/5 »). Sans ça le quota n'était pas atteint → VRAI appel LLM payant.
    from datetime import datetime, timezone
    from app.core.database import SessionLocal
    from app.core.quota import _limit
    from app.models import User
    db = SessionLocal()
    u = db.query(User).filter(User.email == auth["email"]).first()
    lim = _limit(u)
    u.analyses_used_this_month = lim
    u.analyses_period = datetime.now(timezone.utc).strftime("%Y-%m")
    db.commit(); db.close()

    # /api/sourcing/analyze consomme un quota avant tout appel LLM
    tender = {"objet": "Test", "provenance": {"source": "BOAMP",
              "source_url": "https://www.boamp.fr/x", "official_ref": "x"}}
    r = client.post("/api/sourcing/analyze", headers=auth["headers"], json={"tender": tender})
    assert r.status_code == 402  # quota atteint, sans appel LLM
    assert "uota" in r.json()["detail"]


def test_trial_states_and_lockout(client, auth):
    # Essai gratuit 30j SANS carte : actif → niveau Pro ; compte historique (NULL) →
    # ancien palier Découverte ; expiré → limite 0 + 402 « essai terminé » à la conso.
    from datetime import datetime, timezone, timedelta
    from fastapi import HTTPException
    from app.core.database import SessionLocal
    from app.core.config import get_settings
    from app.core.quota import _limit, _trial_state, consume_analysis
    from app.models import User
    PRO = get_settings().PLAN_LIMITS["pro"]["analyses"]
    STARTER = get_settings().PLAN_LIMITS["starter"]["analyses"]
    db = SessionLocal()
    u = db.query(User).filter(User.email == auth["email"]).first()

    # 1) Essai ACTIF (compte fraîchement inscrit) → accès niveau Pro
    assert _trial_state(u) == "active"
    assert _limit(u) == PRO

    # 2) Compte HISTORIQUE (trial_ends_at NULL) → ancien palier Découverte conservé
    u.trial_ends_at = None
    assert _trial_state(u) == "none"
    assert _limit(u) == STARTER

    # 3) Essai EXPIRÉ → limite 0 + 402 dédié (pas d'overage)
    u.trial_ends_at = datetime.now(timezone.utc) - timedelta(days=1)
    u.email_verified = True
    u.analyses_used_this_month = 0
    u.analyses_period = datetime.now(timezone.utc).strftime("%Y-%m")
    db.commit()
    assert _trial_state(u) == "expired"
    assert _limit(u) == 0
    try:
        consume_analysis(u, db)
        assert False, "l'essai expiré aurait dû bloquer"
    except HTTPException as e:
        assert e.status_code == 402
        assert "essai" in e.detail.lower()
    db.close()


# ── Sourcing : recherche d'AO (sources réelles, mock pour le test) ──

def test_sourcing_search_endpoint(client, auth, monkeypatch):
    # On mocke les sources pour ne pas dépendre du réseau en CI
    from app.sourcing.schemas import NormalizedTender, Provenance
    import app.routers.sourcing as sr
    fake = NormalizedTender(objet="Rénovation test", departements=["29"],
                            provenance=Provenance(source="BOAMP", source_url="https://x", official_ref="1"))
    class FakeSvc:
        def __init__(self, *a): pass
        def search(self, *a, **k): return {"tenders": [fake], "errors": [], "sources_queried": ["BOAMP"], "count": 1}
    monkeypatch.setattr(sr, "TenderSearchService", FakeSvc)
    r = client.post("/api/sourcing/search", headers=auth["headers"], json={"query": "rénovation"})
    assert r.status_code == 200
    d = r.json()
    assert d["count"] == 1 and d["tenders"][0]["provenance"]["source"] == "BOAMP"


# ── Alertes d'expiration de documents ──

def test_document_expiry_alert(client, auth, monkeypatch):
    from datetime import date, timedelta
    from app.core.database import SessionLocal
    from app.models import User, Document
    import app.services.alerts as alerts_mod

    sent = []
    monkeypatch.setattr(alerts_mod, "send_email",
                        lambda to, subject, text, html=None: (sent.append((to, subject)) or True))

    db = SessionLocal()
    u = db.query(User).filter(User.email == auth["email"]).first()
    doc = Document(user_id=u.id, name="Attestation URSSAF", category="administratif",
                   file_key="x/y.pdf", expiration_date=date.today() + timedelta(days=5))
    db.add(doc); db.commit()
    res = alerts_mod.run_document_expiry_alerts(db)
    assert res["alerts_sent"] >= 1
    assert sent and "renouveler" in sent[0][1]
    db.refresh(doc)
    assert doc.alert_7_sent is True   # flag marqué → pas de double envoi
    db.close()


def test_cron_endpoint_secret(client):
    # Le secret cron est TOUJOURS exigé (plus de contournement DEMO_MODE) : sans lui → 403,
    # avec le bon en-tête → récap. On configure un secret le temps du test.
    from app.routers import admin
    old = admin.settings.CRON_SECRET
    admin.settings.CRON_SECRET = "secret-de-test"
    try:
        assert client.post("/api/admin/run-alerts").status_code == 403
        r = client.post("/api/admin/run-alerts", headers={"x-cron-secret": "secret-de-test"})
        assert r.status_code == 200 and "scanned" in r.json()
    finally:
        admin.settings.CRON_SECRET = old


# ── Rate limiting (en dernier : réactive puis désactive le limiteur) ──

def test_rate_limit_login(client):
    from app.core.ratelimit import limiter
    limiter.enabled = True
    try:
        codes = [client.post("/api/auth/login",
                             json={"email": "nobody@test.fr", "password": "bad"}).status_code
                 for _ in range(13)]
        assert 429 in codes, codes  # limite 10/min dépassée
    finally:
        limiter.enabled = False
