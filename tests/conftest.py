"""Fixtures de test — base SQLite isolée, rate-limit désactivé par défaut."""
import os
import pathlib

# Doit être défini AVANT tout import de l'app (config lue à l'import).
os.environ["DATABASE_URL"] = "sqlite:///./test_adjugo.db"
os.environ["DEMO_MODE"] = "true"

_db = pathlib.Path("test_adjugo.db")
if _db.exists():
    _db.unlink()

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.ratelimit import limiter


@pytest.fixture(scope="session")
def client():
    limiter.enabled = False  # désactivé pour les tests fonctionnels
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth(client):
    """Crée un utilisateur unique et renvoie son header d'auth + email."""
    import uuid
    email = f"user_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={
        "email": email, "password": "motdepasse123",
        "full_name": "Test User", "company_name": "Test SARL"})
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    return {"headers": {"Authorization": f"Bearer {token}"}, "email": email}
