"""
Preuve d'ISOLATION DES TENANTS (multi-tenancy).

Toute requête sur la base de connaissances est filtrée par user_id. Ces tests
prouvent qu'un client B ne peut PAS extraire les données d'un client A — ni par la
recherche, ni par l'IA — sauf consentement explicite via un espace co-traitance.
"""
import uuid


def _register(client):
    email = f"iso_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={
        "email": email, "password": "motdepasse123", "full_name": "X", "company_name": "Y SARL"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, email


def test_kb_tenant_isolation(client):
    a, _ = _register(client)
    b, _ = _register(client)
    # A dépose une donnée confidentielle ; B dépose autre chose.
    secret = "Notre marge financiere confidentielle est de quarante-deux pourcent sur ce marche strategique."
    assert client.post("/api/knowledge/text", headers=a,
                       json={"name": "Secret A", "text": secret}).status_code == 200
    assert client.post("/api/knowledge/text", headers=b,
                       json={"name": "Doc B", "text": "Travaux de peinture et de revetement de sols en region."}).status_code == 200

    # B cherche la donnée de A → AUCUNE fuite.
    rb = client.post("/api/knowledge/search", headers=b,
                     json={"query": "marge financiere confidentielle quarante-deux pourcent"})
    assert rb.status_code == 200
    for res in rb.json()["results"]:
        assert "marge" not in res["text"].lower(), "FUITE inter-tenant : B voit les données de A"

    # A retrouve bien SA donnée.
    ra = client.post("/api/knowledge/search", headers=a,
                     json={"query": "marge financiere confidentielle"})
    assert any("marge" in r["text"].lower() for r in ra.json()["results"])

    # B ne peut pas répondre à un questionnaire à partir de la base de A.
    qb = client.post("/api/knowledge/questionnaire", headers=b,
                     json={"questions": ["Quelle est votre marge financiere ?"]})
    assert qb.status_code == 200
    for ans in qb.json()["answers"]:
        assert "quarante-deux" not in ans["answer"].lower()
        assert "42" not in ans["answer"]


def test_retrieve_filters_by_user(client):
    """Garantie au niveau du moteur RAG : retrieve() est strictement borné à un user."""
    from app.core.database import SessionLocal
    from app.services import rag
    from app.models import User
    db = SessionLocal()
    try:
        users = db.query(User).order_by(User.id.desc()).limit(2).all()
        if len(users) < 2:
            return  # rien à comparer
        a, b = users[0].id, users[1].id
        a_chunks = {c["chunk_id"] for c in rag.retrieve(db, a, "donnee marge travaux peinture", k=20)}
        b_chunks = {c["chunk_id"] for c in rag.retrieve(db, b, "donnee marge travaux peinture", k=20)}
        assert a_chunks.isdisjoint(b_chunks), "retrieve() mélange les tenants"
    finally:
        db.close()
