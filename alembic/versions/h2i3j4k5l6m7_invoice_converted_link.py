"""sync — invoices.converted_invoice_id (anti double-conversion devis→facture)

Ajoute idempotemment la/les colonne(s) manquante(s) (create_all + ADD COLUMN nullable).
Non destructif. Dialect-agnostique.

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa

revision = "h2i3j4k5l6m7"
down_revision = "g1h2i3j4k5l6"
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
