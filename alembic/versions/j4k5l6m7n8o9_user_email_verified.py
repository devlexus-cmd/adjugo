"""users.email_verified (vérification d'email à l'inscription)

Ajoute la colonne (idempotent) PUIS marque tous les comptes EXISTANTS comme vérifiés
(grand-père : ils sont déjà légitimes ; seuls les NOUVEAUX comptes devront confirmer).

Revision ID: j4k5l6m7n8o9
Revises: i3j4k5l6m7n8
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa

revision = "j4k5l6m7n8o9"
down_revision = "i3j4k5l6m7n8"
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
        if "email_verified" not in cols:
            op.add_column("users", sa.Column("email_verified", sa.Boolean(),
                                             nullable=True, server_default=sa.text("false")))
        # Grand-père : comptes déjà créés = vérifiés (on ne verrouille pas les utilisateurs existants).
        op.execute("UPDATE users SET email_verified = true WHERE email_verified IS NULL OR email_verified = false")


def downgrade():
    pass
