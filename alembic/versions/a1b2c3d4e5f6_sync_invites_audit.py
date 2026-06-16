"""sync schéma — invitations co-traitant + journal d'accès RGPD

Passe de synchro idempotente (create_all + ADD COLUMN manquantes) pour les tables
`project_invites` (vue bridée par jeton) et `audit_logs` (traçabilité RGPD).
Non destructif : crée les tables manquantes, n'altère rien d'existant.

Revision ID: a1b2c3d4e5f6
Revises: c2d3e4f5a6b7
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def _server_default(col):
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
    import app.models  # noqa: F401
    from app.core.database import Base

    Base.metadata.create_all(bind=bind)

    insp = sa.inspect(bind)
    existing = set(insp.get_table_names())
    for table in Base.metadata.tables.values():
        if table.name not in existing:
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            op.add_column(table.name,
                          sa.Column(col.name, col.type, nullable=True,
                                    server_default=_server_default(col)))


def downgrade():
    pass
