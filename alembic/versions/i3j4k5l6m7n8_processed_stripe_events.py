"""sync — table processed_stripe_events (idempotence webhooks Stripe)

create_all crée la table manquante (idempotent, dialect-agnostique). Non destructif.

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-06-24
"""
from alembic import op

revision = "i3j4k5l6m7n8"
down_revision = "h2i3j4k5l6m7"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    import app.models  # noqa: F401
    from app.core.database import Base
    Base.metadata.create_all(bind=bind)   # crée processed_stripe_events si absente


def downgrade():
    pass
