"""acheteurs + acheteur_dces (espace acheteur collectivités)

Crée les tables de l'espace acheteur (comptes cloisonnés du produit PME + DCE sauvegardés).
`create_all` est idempotent : il ne crée que les tables MANQUANTES, sans toucher aux
existantes — même idiome que la migration précédente.

Revision ID: k5l6m7n8o9p0
Revises: j4k5l6m7n8o9
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa  # noqa: F401

revision = "k5l6m7n8o9p0"
down_revision = "j4k5l6m7n8o9"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    import app.models  # noqa: F401  (enregistre Acheteur / AcheteurDce sur Base)
    from app.core.database import Base
    Base.metadata.create_all(bind=bind)   # crée `acheteurs` + `acheteur_dces` si absentes


def downgrade():
    op.drop_table("acheteur_dces")
    op.drop_table("acheteurs")
