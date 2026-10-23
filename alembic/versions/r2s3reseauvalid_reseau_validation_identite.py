"""co-traitance v2 (vague 3, correctifs) : validation de l'identité par Adjugo avant publication.

La vérification SIRENE prouve qu'une entreprise existe et est active, pas que le compte qui
publie la représente (un compte pouvait publier sous le SIREN d'une autre entreprise réelle).
Décision du fondateur : la PUBLICATION d'un profil passe par une validation d'un administrateur
Adjugo. Ajoute à partner_profiles :
- validation_status ('' | en_attente | validee | refusee), validation_siren (SIREN validé),
  validation_requested_at / _by, validated_at / _by, validation_motif (motif d'un refus) ;
- last_check_at : dernière TENTATIVE du cron (le tri du cron se fait sur cette date) ;
- groupements_checked_at : date du dernier recalcul du compteur de groupements (badge daté) ;
- index UNIQUE partiel « un seul profil publié par SIREN » (siren WHERE visible).

Donnée existante : un profil publié AVANT cette révision n'a jamais été validé → il repasse
« en attente de validation » (non visible) ; rien n'est supprimé. Idempotent (colonnes et index
créés seulement s'ils manquent). SQLite (tests, démo) et Postgres (production).

Revision ID: r2s3reseauvalid
Revises: q1r2s3t4u5v6
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa

revision = "r2s3reseauvalid"
down_revision = "q1r2s3t4u5v6"
branch_labels = None
depends_on = None

TABLE = "partner_profiles"
INDEX = "uq_partner_profiles_siren_publie"

_COLS = [
    ("validation_status", lambda: sa.String(20), ""),
    ("validation_siren", lambda: sa.String(9), ""),
    ("validation_requested_at", sa.DateTime, None),
    ("validation_requested_by", sa.Integer, None),
    ("validated_at", sa.DateTime, None),
    ("validated_by", sa.Integer, None),
    ("validation_motif", lambda: sa.String(300), ""),
    ("last_check_at", sa.DateTime, None),
    ("groupements_checked_at", sa.DateTime, None),
]


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if TABLE not in set(insp.get_table_names()):
        return
    existing = {c["name"] for c in insp.get_columns(TABLE)}
    for name, typ, default in _COLS:
        if name not in existing:
            t = typ() if callable(typ) else typ
            kw = {"nullable": True}
            if default is not None:
                kw["server_default"] = default
            op.add_column(TABLE, sa.Column(name, t, **kw))

    # Profils publiés jamais validés par Adjugo → en attente de validation (non visibles).
    true_lit = "1" if bind.dialect.name == "sqlite" else "true"
    false_lit = "0" if bind.dialect.name == "sqlite" else "false"
    bind.execute(sa.text(
        f"UPDATE {TABLE} SET validation_status = 'en_attente', "
        f"validation_requested_at = COALESCE(published_at, updated_at, created_at), visible = {false_lit} "
        f"WHERE visible = {true_lit} AND (validation_status IS NULL OR validation_status = '')"))
    bind.execute(sa.text(f"UPDATE {TABLE} SET validation_status = '' WHERE validation_status IS NULL"))

    insp = sa.inspect(bind)
    if INDEX not in {i["name"] for i in insp.get_indexes(TABLE)}:
        op.create_index(INDEX, TABLE, ["siren"], unique=True,
                        sqlite_where=sa.text("visible = 1"), postgresql_where=sa.text("visible"))


def downgrade():
    pass
