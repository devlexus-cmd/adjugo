"""Suite de tests sur PostgreSQL (facultatif) : une base NEUVE par lancement de pytest.

Activé par la variable ADJUGO_TEST_PG_URL (lue par tests/conftest.py) : l'URL d'un serveur PostgreSQL dont le rôle peut
créer une base, p. ex. ``postgresql://postgres@localhost:5432/postgres``. Sans elle, la suite tourne sur SQLite, comme
avant. ``scripts/tests_postgres.py`` démarre un serveur jetable, lance la suite et l'arrête (docs/TESTS_POSTGRES.md).

À chaque lancement :
  1. une base au nom unique (``adjugo_test_<pid>_<hasard>``) est créée sur ce serveur : rien n'est repris d'un
     lancement précédent (PostgreSQL ne réutilise jamais un identifiant : une base réutilisée verrait ses compteurs
     continuer et les données d'avant s'accumuler) ;
  2. le schéma y est monté par les migrations (``alembic upgrade head``), exactement comme en production : sur
     PostgreSQL, app/main.py ne crée aucune table ;
  3. la base est supprimée en fin de session (``ADJUGO_TEST_PG_GARDER=1`` la garde pour l'inspecter).
La base nommée dans l'URL n'est jamais modifiée : elle ne sert qu'à se connecter au serveur.
"""
import os
import subprocess
import sys
import uuid
from urllib.parse import urlsplit, urlunsplit

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ETAT = {"serveur": "", "base": "", "nom": ""}


def _normaliser(url: str) -> str:
    url = url.strip()
    if url.startswith("postgres://"):            # forme courte des hébergeurs
        url = "postgresql://" + url[len("postgres://"):]
    if not url.startswith("postgresql"):
        raise RuntimeError(f"ADJUGO_TEST_PG_URL doit être une URL PostgreSQL (postgresql://…), reçu : {url[:30]}…")
    return url


def _avec_base(url: str, nom: str) -> str:
    """Même serveur, même rôle, mêmes options (``?host=`` d'un socket…), autre base. L'URL n'est pas réécrite par
    ailleurs : alembic.ini lit l'URL avec interpolation, un « % » ajouté par un ré-encodage la casserait."""
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, "/" + nom, p.query, p.fragment))


def _admin(url: str):
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    return create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")


def creer(url_serveur: str) -> str:
    """Crée la base neuve, y monte le schéma par les migrations et renvoie son URL (à mettre dans DATABASE_URL)."""
    from sqlalchemy import text
    url_serveur = _normaliser(url_serveur)
    nom = f"adjugo_test_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    moteur = _admin(url_serveur)
    try:
        with moteur.connect() as c:
            version = c.execute(text("SHOW server_version")).scalar()
            c.execute(text(f'CREATE DATABASE "{nom}"'))
    finally:
        moteur.dispose()
    url_base = _avec_base(url_serveur, nom)
    _ETAT.update(serveur=url_serveur, base=url_base, nom=nom, version=version)
    env = dict(os.environ, DATABASE_URL=url_base)
    p = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=RACINE, env=env,
                       capture_output=True, text=True)
    if p.returncode != 0:
        supprimer()
        raise RuntimeError("alembic upgrade head a échoué sur la base de test PostgreSQL :\n"
                           + p.stdout[-4000:] + "\n" + p.stderr[-4000:])
    if os.environ.get("ADJUGO_TEST_PG_IDS_DECALES", "").strip() in ("1", "true", "oui"):
        decaler_identifiants(url_base)
    return url_base


def decaler_identifiants(url_base: str) -> int:
    """Option de vérification (ADJUGO_TEST_PG_IDS_DECALES=1, ou --ids-decales du script) : chaque table numérote à
    partir d'un point différent (1 000 007, 2 000 007…), au lieu de 1 partout. Sur une base neuve, le compte n° 5,
    l'organisation n° 5 et le marché n° 5 coexistent : un identifiant pris pour un autre (compte pour organisation,
    marché d'un autre…) passe inaperçu, alors qu'en production les compteurs ont divergé depuis longtemps. Ici, il
    échoue ; et aucun test ne peut compter sur un identifiant précis (le compte de démonstration n'est plus le n° 1)."""
    from sqlalchemy import text
    moteur = _admin(url_base)
    try:
        with moteur.connect() as c:
            noms = [r[0] for r in c.execute(text(
                "SELECT sequencename FROM pg_sequences WHERE schemaname = 'public' ORDER BY sequencename"))]
            for i, nom in enumerate(noms):
                c.execute(text(f'ALTER SEQUENCE "{nom}" RESTART WITH {(i + 1) * 1_000_000 + 7}'))
    finally:
        moteur.dispose()
    _ETAT["ids_decales"] = len(noms)
    return len(noms)


def decrire() -> str:
    if not _ETAT["nom"]:
        return ""
    decales = f", identifiants décalés sur {_ETAT['ids_decales']} tables" if _ETAT.get("ids_decales") else ""
    return f"PostgreSQL {_ETAT.get('version', '?')}, base neuve {_ETAT['nom']} (migrations alembic{decales})"


def supprimer() -> None:
    """Supprime la base de ce lancement (connexions encore ouvertes coupées : WITH (FORCE), PostgreSQL 13 et plus)."""
    if not _ETAT["nom"] or os.environ.get("ADJUGO_TEST_PG_GARDER", "").strip() in ("1", "true", "oui"):
        return
    from sqlalchemy import text
    try:
        from app.core.database import engine
        engine.dispose()
    except Exception:       # app pas encore importée (échec des migrations)
        pass
    moteur = _admin(_ETAT["serveur"])
    try:
        with moteur.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{_ETAT["nom"]}" WITH (FORCE)'))
    finally:
        moteur.dispose()
    _ETAT["nom"] = ""
