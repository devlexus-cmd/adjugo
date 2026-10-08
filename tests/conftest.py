"""Fixtures de test — base SQLite isolée, rate-limit désactivé par défaut."""
import os
import pathlib

# Doit être défini AVANT tout import de l'app (config lue à l'import).
# ADJUGO_TEST_DB permet de lancer plusieurs suites en parallèle sans partager la même base
# (ex. ADJUGO_TEST_DB=test_auth.db). Défaut inchangé : test_adjugo.db.
_TEST_DB_FILE = os.environ.get("ADJUGO_TEST_DB", "test_adjugo.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{_TEST_DB_FILE}"
os.environ["DEMO_MODE"] = "true"
# La démo publique est FERMÉE par défaut en production ; la suite existante l'exerce
# (garde « lecture guidée ») → ouverte ici. tests/test_demande_acces.py teste la fermeture.
os.environ.setdefault("DEMO_PUBLIC", "1")
# Emails DÉSACTIVÉS en test : sans ça, chaque inscription tentait de vrais envois
# SMTP/Brevo (≈12 s de timeouts par test, et des emails réels depuis la machine).
os.environ["SMTP_HOST"] = ""
os.environ["SMTP_USER"] = ""
os.environ["BREVO_API_KEY"] = ""
# Clés LLM VIDES en test : aucun test ne doit dépendre d'un vrai appel payant (les
# tests IA remplacent le client par un faux ; les autres reçoivent un 503 propre).
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["MISTRAL_API_KEY"] = ""

_db = pathlib.Path(_TEST_DB_FILE)
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
    """Crée un utilisateur unique (adresse déjà confirmée, comme un client embarqué)
    et renvoie son header d'auth + email."""
    import uuid
    email = f"user_{uuid.uuid4().hex[:8]}@test.fr"
    r = client.post("/api/auth/register", json={
        "email": email, "password": "motdepasse123",
        "full_name": "Test User", "company_name": "Test SARL"})
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    # Le verrou « email vérifié » (403 sur les actions IA) a ses propres parcours ; ici on
    # teste les fonctionnalités, donc l'utilisateur de test est considéré vérifié.
    from app.core.database import SessionLocal
    from app.models import User
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.email_verified = True
        db.commit()
    finally:
        db.close()
    return {"headers": {"Authorization": f"Bearer {token}"}, "email": email}
