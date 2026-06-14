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
    # Mettre le compteur du nouvel utilisateur (plan starter, limite 3) au plafond
    from datetime import datetime, timezone
    from app.core.database import SessionLocal
    from app.models import User
    db = SessionLocal()
    u = db.query(User).filter(User.email == auth["email"]).first()
    u.analyses_used_this_month = 3
    u.analyses_period = datetime.now(timezone.utc).strftime("%Y-%m")
    db.commit(); db.close()

    # /api/sourcing/analyze consomme un quota avant tout appel LLM
    tender = {"objet": "Test", "provenance": {"source": "BOAMP",
              "source_url": "https://www.boamp.fr/x", "official_ref": "x"}}
    r = client.post("/api/sourcing/analyze", headers=auth["headers"], json={"tender": tender})
    assert r.status_code == 402  # quota atteint, sans appel LLM
    assert "uota" in r.json()["detail"]


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


def test_cron_endpoint_demo(client):
    # DEMO_MODE=true en test → endpoint accessible, renvoie un récap
    r = client.post("/api/admin/run-alerts")
    assert r.status_code == 200 and "scanned" in r.json()


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
