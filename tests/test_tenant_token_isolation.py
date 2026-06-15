"""
Isolation des tokens IA par TENANT au niveau des ENDPOINTS HTTP.

Complète tests/test_llm_resilience.py (qui prouve l'isolation au niveau du moteur).
Ici on prouve que les deux routes IA qui appelaient le LLM HORS périmètre tenant —
/api/sourcing/ask (Q&A) et /api/sourcing/renewals — l'enveloppent désormais dans
tenant_scope(user_id) : la consommation IA est imputée au tenant appelant, pas au
pot commun. Un « voisin bruyant » ne peut donc pas ponctionner le budget des autres.

Sans réseau : le client Anthropic est remplacé par un faux à usage connu.
"""
from app.services import llm
from app.core.database import SessionLocal
from app.models import User, Project


class _FakeUsage:
    input_tokens = 10
    output_tokens = 20


class _FakeResp:
    usage = _FakeUsage()
    content = [type("B", (), {"text": "réponse de test"})()]


def _fake_client():
    return type("C", (), {
        "messages": type("M", (), {"create": staticmethod(lambda **kw: _FakeResp())})
    })


def _uid(email):
    db = SessionLocal()
    try:
        return db.query(User).filter(User.email == email).first().id
    finally:
        db.close()


def test_ask_impute_les_tokens_au_tenant(client, auth, monkeypatch):
    llm._TENANT_TOKENS.clear()
    monkeypatch.setattr(llm, "client", _fake_client)
    uid = _uid(auth["email"])
    db = SessionLocal()
    try:
        p = Project(user_id=uid, name="AO test",
                    ai_analysis={"dce_excerpt": "Texte du DCE.", "summary": "s", "details": {}})
        db.add(p); db.commit(); db.refresh(p); pid = p.id
    finally:
        db.close()

    r = client.post("/api/sourcing/ask", headers=auth["headers"],
                    json={"project_id": pid, "question": "Quel est le délai de remise ?"})
    assert r.status_code == 200, r.text
    # Les tokens de la Q&A sont imputés à CE tenant (preuve que /ask est sous tenant_scope).
    assert llm.tenant_usage(uid) == 30
    llm._TENANT_TOKENS.clear()


def test_renewals_impute_les_tokens_au_tenant(client, auth, monkeypatch):
    llm._TENANT_TOKENS.clear()
    monkeypatch.setattr(llm, "client", _fake_client)
    uid = _uid(auth["email"])

    # Faux détecteur : consomme un appel IA (via le client patché), sans réseau.
    def _fake_detect(query, deps, gonogo, domaines=None):
        llm.messages_create(model=llm.MODEL, messages=[], max_tokens=10)
        return {"renewals": [], "errors": []}

    monkeypatch.setattr("app.services.renewal.detect_renewals", _fake_detect)
    r = client.post("/api/sourcing/renewals", headers=auth["headers"],
                    json={"query": "travaux", "departements": [], "domaines": []})
    assert r.status_code == 200, r.text
    assert llm.tenant_usage(uid) == 30   # imputé au tenant (preuve que /renewals est sous tenant_scope)
    llm._TENANT_TOKENS.clear()
