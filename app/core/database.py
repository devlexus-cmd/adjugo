"""
Adjugo — Configuration base de données SQLAlchemy
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool
from app.core.config import get_settings

settings = get_settings()

# Détection du moteur : SQLite (démo locale, zéro dépendance) vs Postgres (prod)
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
# Base SQLite en mémoire (tests) : ":memory:" ou "sqlite://" sans chemin de fichier.
_is_sqlite_memory = _is_sqlite and (
    ":memory:" in settings.DATABASE_URL or settings.DATABASE_URL.rstrip("/").endswith("sqlite:")
)

if _is_sqlite_memory:
    # Base en mémoire : il FAUT une connexion unique partagée (StaticPool), sinon
    # chaque thread ouvrirait une base vide distincte.
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
elif _is_sqlite:
    # Base SQLite sur fichier : pool par défaut = une connexion par requête en vol
    # (checkout exclusif). NE PAS utiliser StaticPool ici : il forcerait toutes les
    # requêtes à partager une UNIQUE connexion sqlite — or les endpoints sync tournent
    # dans le threadpool de Starlette, donc plusieurs threads se partageraient le même
    # curseur, qui se corrompt en accès concurrent (IndexError: tuple index out of
    # range, intermittent). `timeout` laisse sqlite attendre le verrou d'écriture au
    # lieu d'échouer immédiatement ("database is locked").
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 30},
    )
else:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=1800,   # recycle les connexions > 30 min (évite les conn. mortes)
        pool_size=10,
        max_overflow=20,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dépendance FastAPI — fournit une session DB par requête."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
