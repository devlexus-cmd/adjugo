"""co-traitance v2 (vague 1) : score de groupement, doctrine de visibilité, journal membre,
coffre-fort croisé.

Idempotent (create_all + add_column si absente). Ajoute :
- projects.groupement_score / groupement_plan        → « seul 54 % → avec X 81 % »
- groupement_simulations (table)                      → historique des what-if
- cotraitants.references / capacites_source / capacites_updated_at
- project_cotraitants.invite_id                       → candidat ≠ membre (invitation active)
- project_invites.declined_at / source / partner_profile_id
- project_contributions.prix_lot_ht / detail_chiffre / representant_legal /
  signataire_qualite / capacites                      → doctrine de visibilité
- contribution_pieces.piece_type / expiration_date / source_document_id → coffre croisé
- audit_logs.invite_id                                → journal membre (projection)

DATA : chiffrage_note (approche prix EN CLAIR, visible du mandataire = fuite) est déplacée
en tête de note_au_mandataire avec le préfixe « (ancienne approche prix) » puis vidée.
La colonne est supprimée en vague 4. Décision fondateur du 06/10/2026.

Revision ID: n8o9p0q1r2s3
Revises: m7n8o9p0q1r2
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa

revision = "n8o9p0q1r2s3"
down_revision = "m7n8o9p0q1r2"
branch_labels = None
depends_on = None


_COLUMNS = {
    "projects": [
        sa.Column("groupement_score", sa.Integer(), nullable=True),
        sa.Column("groupement_plan", sa.JSON(), nullable=True),
    ],
    "cotraitants": [
        sa.Column("references", sa.JSON(), nullable=True),
        sa.Column("capacites_source", sa.String(20), nullable=True, server_default="declare"),
        sa.Column("capacites_updated_at", sa.DateTime(), nullable=True),
    ],
    "project_cotraitants": [
        sa.Column("invite_id", sa.Integer(), nullable=True),
    ],
    "project_invites": [
        sa.Column("declined_at", sa.DateTime(), nullable=True),
        sa.Column("source", sa.String(20), nullable=True, server_default="manuel"),
        sa.Column("partner_profile_id", sa.Integer(), nullable=True),
    ],
    "project_contributions": [
        sa.Column("prix_lot_ht", sa.Float(), nullable=True),
        sa.Column("detail_chiffre", sa.JSON(), nullable=True),
        sa.Column("representant_legal", sa.String(255), nullable=True, server_default=""),
        sa.Column("signataire_qualite", sa.String(120), nullable=True, server_default=""),
        sa.Column("capacites", sa.JSON(), nullable=True),
    ],
    "contribution_pieces": [
        sa.Column("piece_type", sa.String(20), nullable=True, server_default=""),
        sa.Column("expiration_date", sa.Date(), nullable=True),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
    ],
    "audit_logs": [
        sa.Column("invite_id", sa.Integer(), nullable=True),
    ],
}

_INDEXES = [
    ("ix_project_cotraitants_invite_id", "project_cotraitants", ["invite_id"]),
    ("ix_project_invites_partner_profile_id", "project_invites", ["partner_profile_id"]),
    ("ix_audit_logs_invite_id", "audit_logs", ["invite_id"]),
]


def upgrade():
    bind = op.get_bind()
    import app.models  # noqa: F401
    import app.routers.cotraitants  # noqa: F401  (Cotraitant / ProjectCotraitant)
    from app.core.database import Base
    Base.metadata.create_all(bind=bind)   # crée groupement_simulations si absente
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    for table, cols in _COLUMNS.items():
        if table not in tables:
            continue
        existing = {c["name"] for c in insp.get_columns(table)}
        for col in cols:
            if col.name not in existing:
                op.add_column(table, col)

    insp = sa.inspect(bind)
    for name, table, cols in _INDEXES:
        if table not in tables:
            continue
        have = {i["name"] for i in insp.get_indexes(table)}
        if name not in have:
            op.create_index(name, table, cols)   # pas de try/except : sur Postgres un échec
            # avalé laisserait la transaction « aborted » et masquerait la vraie cause

    # ── Migration de données : la fuite « approche prix » ────────────────────────────
    # Garde (vague 4) : la colonne n'existe plus dans le modèle ; sur une base NEUVE, les
    # create_all des révisions précédentes ne la créent donc plus → rien à déplacer.
    has_note = "project_contributions" in tables and "chiffrage_note" in {
        c["name"] for c in sa.inspect(bind).get_columns("project_contributions")}
    if has_note:
        rows = bind.execute(sa.text(
            "SELECT id, chiffrage_note, note_au_mandataire FROM project_contributions "
            "WHERE chiffrage_note IS NOT NULL AND chiffrage_note <> ''")).fetchall()
        for rid, note, mand in rows:
            prefix = "(ancienne approche prix) " + (note or "").strip()
            merged = prefix + (("\n\n" + mand.strip()) if (mand or "").strip() else "")
            bind.execute(sa.text(
                "UPDATE project_contributions SET note_au_mandataire = :m, chiffrage_note = '' "
                "WHERE id = :i"), {"m": merged, "i": rid})   # colonne Text : jamais tronquer


def downgrade():
    pass
