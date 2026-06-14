"""sync schema avec les modèles (tables + colonnes hors migrations)

Crée les tables ajoutées après les migrations initiales (organizations,
saved_searches, signals…) et ajoute aux tables existantes les colonnes de
modèle manquantes. Réplique côté Postgres ce que `ensure_sqlite_columns`
(app/core/dbsync.py) fait en dev SQLite.

Non destructif et idempotent :
  - create_all(checkfirst=True) ne touche jamais une table existante ;
  - ADD COLUMN uniquement si la colonne est absente.

Revision ID: b7d9e1f3a2c4
Revises: 9734d3292bda
Create Date: 2026-06-14
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b7d9e1f3a2c4"
down_revision = "9734d3292bda"
branch_labels = None
depends_on = None


def _server_default(col):
    """Traduit un default modèle constant en server_default DDL (sinon None)."""
    d = getattr(col, "default", None)
    if d is None or getattr(d, "is_callable", False):
        return None
    arg = getattr(d, "arg", None)
    if callable(arg) or arg is None or isinstance(arg, (list, dict)):
        return None
    if isinstance(arg, bool):
        return sa.text("true" if arg else "false")
    if isinstance(arg, (int, float)):
        return sa.text(str(arg))
    if isinstance(arg, str):
        return sa.text("'" + arg.replace("'", "''") + "'")
    return None


def upgrade():
    bind = op.get_bind()

    # Charge tous les modèles → metadata complète, puis crée les tables absentes.
    import app.models  # noqa: F401  (enregistre tous les modèles sur Base)
    from app.core.database import Base

    Base.metadata.create_all(bind=bind)  # checkfirst=True par défaut

    # Ajoute aux tables existantes les colonnes de modèle manquantes (idempotent).
    insp = sa.inspect(bind)
    existing = set(insp.get_table_names())
    for table in Base.metadata.tables.values():
        if table.name not in existing:
            continue  # vient d'être créée par create_all
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            op.add_column(
                table.name,
                sa.Column(col.name, col.type, nullable=True,
                          server_default=_server_default(col)),
            )


def downgrade():
    # Migration de réconciliation : pas de rollback structurel.
    pass
