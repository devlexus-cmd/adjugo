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
    # Idempotent : si une table acheteur préexiste sans une colonne du modèle (pilotage /
    # diffusion ajoutés après coup), on l'ajoute (nullable, defaults gérés par l'app).
    insp = sa.inspect(bind)
    for tname in ("acheteurs", "acheteur_dces"):
        if tname not in insp.get_table_names():
            continue
        existing = {c["name"] for c in insp.get_columns(tname)}
        for col in Base.metadata.tables[tname].columns:
            if col.name not in existing:
                op.add_column(tname, sa.Column(col.name, col.type, nullable=True))


def downgrade():
    # Défensif et symétrique de l'upgrade idempotent : on ne drop que ce qui existe (et dans
    # l'ordre des dépendances), pour ne jamais planter un downgrade sur une base partielle.
    bind = op.get_bind()
    existing = sa.inspect(bind).get_table_names()
    for tname in ("acheteur_dces", "acheteurs"):
        if tname in existing:
            op.drop_table(tname)
