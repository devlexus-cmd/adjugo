"""Fixtures de test — base SQLite isolée (ou PostgreSQL neuve, ADJUGO_TEST_PG_URL), rate-limit désactivé par défaut."""
import os
import pathlib

# Doit être défini AVANT tout import de l'app (config lue à l'import).
# ADJUGO_TEST_DB permet de lancer plusieurs suites en parallèle sans partager la même base
# (ex. ADJUGO_TEST_DB=test_auth.db). Défaut inchangé : test_adjugo.db.
_TEST_DB_FILE = os.environ.get("ADJUGO_TEST_DB", "test_adjugo.db")
# PostgreSQL, le moteur de la PRODUCTION (facultatif) : ADJUGO_TEST_PG_URL = URL d'un serveur PostgreSQL. La suite tourne
# alors sur une base NEUVE de ce serveur, montée par les migrations comme en production, supprimée en fin de session
# (tests/_base_postgres.py ; scripts/tests_postgres.py démarre un serveur jetable ; docs/TESTS_POSTGRES.md).
# Sans elle : SQLite, comme avant (la ligne ci-dessous), et ADJUGO_TEST_DB garde son rôle.
_TEST_PG_URL = os.environ.get("ADJUGO_TEST_PG_URL", "").strip()
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
os.environ["MISTRAL_API_KEY_ADJUGO"] = ""
# Routage IA par défaut (indépendant du shell du poste) : routage par tâche, sans forçage.
os.environ["LLM_PROVIDER"] = "auto"
os.environ["LLM_ROUTAGE"] = "nouveau"
os.environ["MISTRAL_POINT_ACCES"] = "auto"
# Fuseau de la PRODUCTION (image python:3.12-slim : UTC). Le serveur prend « aujourd'hui » en UTC
# (relances, dates de vérification) ; les tests, eux, calculent leurs dates avec date.today().
# Sur un poste à l'heure de Paris, les deux divergeaient entre 00:00 et 02:00 : 3 échecs la nuit.
# Les heures « de Paris » affichées ne dépendent pas de ce réglage (fuseau explicite, zoneinfo).
os.environ["TZ"] = "UTC"
import time as _time
if hasattr(_time, "tzset"):
    _time.tzset()

if _TEST_PG_URL:
    from tests import _base_postgres
    os.environ["DATABASE_URL"] = _base_postgres.creer(_TEST_PG_URL)
else:
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


@pytest.fixture(autouse=True)
def _analyse_partagee_vide():
    """Analyse partagée (app.services.analyse_partagee) : chaque test part sans extraction gardée ni
    mesure, pour que l'ordre des tests ne change rien (des tests différents importent le même dossier
    simulé, depuis des comptes différents). tests/test_analyse_partagee.py exerce le partage lui-même."""
    def vider():
        try:
            from app.core.database import SessionLocal
            from app.models import AnalyseEmpreinte, AnalysePartagee
            db = SessionLocal()
            try:
                db.query(AnalysePartagee).delete(synchronize_session=False)
                db.query(AnalyseEmpreinte).delete(synchronize_session=False)
                db.commit()
            finally:
                db.close()
        except Exception:       # base pas encore créée (premier test) : rien à vider
            pass
    vider()
    yield


@pytest.fixture
def fk_on():
    """Clés étrangères APPLIQUÉES, comme en production (PostgreSQL), quel que soit le moteur de la suite.

    SQLite les ignore par défaut (c'est pourquoi la suite ne voyait pas l'effacement RGPD échouer) : PRAGMA
    foreign_keys=ON sur chaque nouvelle connexion, le temps du test. PostgreSQL les applique toujours (contraintes
    réelles posées par les migrations) : aucun PRAGMA, qui n'existe pas sur ce moteur. Sur les deux, AVANT le test,
    une ligne orpheline (journal rattaché à un compte inexistant, audit_logs.owner_id → users.id) doit être refusée ;
    et l'écouteur est retiré quoi qu'il arrive (resté branché, il faisait échouer toute connexion suivante)."""
    from sqlalchemy import event, insert, text
    from sqlalchemy.exc import IntegrityError
    from app.core.database import engine, _is_sqlite
    from app.models import AuditLog

    def _on(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    if _is_sqlite:
        event.listen(engine, "connect", _on)
        engine.dispose()
    try:
        with engine.connect() as c:
            if _is_sqlite:
                assert c.execute(text("PRAGMA foreign_keys")).scalar() == 1
            try:
                with pytest.raises(IntegrityError):
                    c.execute(insert(AuditLog.__table__).values(action="verif.cles_etrangeres", owner_id=-1))
            finally:
                c.rollback()             # rien n'est écrit
        yield
    finally:
        if _is_sqlite:
            event.remove(engine, "connect", _on)
            engine.dispose()


def pytest_report_header(config):
    if _TEST_PG_URL:
        return "base de test : " + _base_postgres.decrire()
    return f"base de test : SQLite ({_TEST_DB_FILE})"


def pytest_sessionfinish(session, exitstatus):
    """Base PostgreSQL de ce lancement supprimée en fin de session (SQLite : le fichier l'est au lancement suivant)."""
    if _TEST_PG_URL:
        _base_postgres.supprimer()
