"""co-traitance : suivi d'envoi, relance et note du partenaire

Ajoute (idempotent) :
- project_invites.emailed_at    → date d'envoi réel du lien d'invitation
- project_invites.reminder_stage → palier de relance déjà notifié (0/1/2)
- project_contributions.note_au_mandataire → message libre du partenaire au chef de file

Revision ID: l6m7n8o9p0q1
Revises: k5l6m7n8o9p0
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "l6m7n8o9p0q1"
down_revision = "k5l6m7n8o9p0"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    import app.models  # noqa: F401
    from app.core.database import Base
    Base.metadata.create_all(bind=bind)
    insp = sa.inspect(bind)

    if "project_invites" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("project_invites")}
        if "emailed_at" not in cols:
            op.add_column("project_invites", sa.Column("emailed_at", sa.DateTime(), nullable=True))
        if "reminder_stage" not in cols:
            op.add_column("project_invites", sa.Column("reminder_stage", sa.Integer(),
                                                       nullable=True, server_default=sa.text("0")))
            op.execute("UPDATE project_invites SET reminder_stage = 0 WHERE reminder_stage IS NULL")

    if "project_contributions" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("project_contributions")}
        if "note_au_mandataire" not in cols:
            op.add_column("project_contributions", sa.Column("note_au_mandataire", sa.Text(),
                                                             nullable=True, server_default=""))


def downgrade():
    pass
