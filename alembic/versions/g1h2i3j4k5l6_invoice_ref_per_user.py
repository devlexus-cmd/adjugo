"""sync — unicité invoices.reference PAR UTILISATEUR (composite user_id + reference)

Remplace l'unicité GLOBALE de invoices.reference par une unicité par utilisateur : la
numérotation FAC/DEV est séquentielle par user, donc deux users obtenaient « FAC-2026-001 »
et le 2e heurtait la contrainte globale (IntegrityError → 500). Idempotent + dialect-guard
(Postgres ; SQLite dev = create_all sur base fraîche). Non destructif.

Revision ID: g1h2i3j4k5l6
Revises: b4c5d6e7f8a9
Create Date: 2026-06-24
"""
from alembic import op

revision = "g1h2i3j4k5l6"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    import app.models  # noqa: F401
    from app.core.database import Base
    Base.metadata.create_all(bind=bind)   # idempotent (tables/colonnes manquantes)
    if bind.dialect.name != "postgresql":
        return   # SQLite (dev) : nouveau schéma déjà en composite via create_all
    # Remplace la contrainte unique GLOBALE par une contrainte composite (user_id, reference).
    op.execute("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS invoices_reference_key")
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_invoice_user_reference') THEN "
        "ALTER TABLE invoices ADD CONSTRAINT uq_invoice_user_reference UNIQUE (user_id, reference); "
        "END IF; END $$;"
    )


def downgrade():
    pass
