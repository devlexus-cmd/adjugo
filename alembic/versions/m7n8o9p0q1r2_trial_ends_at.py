"""essai gratuit 30 jours : users.trial_ends_at

Ajoute (idempotent) :
- users.trial_ends_at → fin de l'essai gratuit 30j sans carte (NULL = compte historique/demo)

Revision ID: m7n8o9p0q1r2
Revises: l6m7n8o9p0q1
Create Date: 2026-07-22
"""
from alembic import op
import sqlalchemy as sa

revision = "m7n8o9p0q1r2"
down_revision = "l6m7n8o9p0q1"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    import app.models  # noqa: F401
    from app.core.database import Base
    Base.metadata.create_all(bind=bind)
    insp = sa.inspect(bind)
    if "users" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("users")}
        if "trial_ends_at" not in cols:
            op.add_column("users", sa.Column("trial_ends_at", sa.DateTime(), nullable=True))


def downgrade():
    pass
