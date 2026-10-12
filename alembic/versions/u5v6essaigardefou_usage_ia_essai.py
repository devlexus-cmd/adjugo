"""garde-fou de l'essai gratuit : analyses sur toute la durée de l'essai et coût réel de l'IA.

Idempotent (comme les révisions précédentes) : la table n'est créée que si elle manque, la colonne
n'est ajoutée que si elle manque. SQLite (tests, démo) et Postgres (production). Ajoute :
- users.trial_analyses_used → analyses consommées pendant l'essai, sur TOUTE sa durée (l'essai
  compte TRIAL_ANALYSES analyses au total, et non plus 30 par mois civil). Comptes déjà en essai :
  repris à leur compteur du mois en cours (rien n'est offert en plus) ;
- table usage_ia → coût réel des appels à l'IA (tarif public du fournisseur), cumulé par compte de
  facturation, par mois et selon que le compte était en essai ou non : budget de l'essai et alerte
  interne des forfaits payants. Jamais montré au client.

Downgrade RÉEL : retire la colonne et la table.

Revision ID: u5v6essaigardefou
Revises: t4u5redactionv2b
Create Date: 2026-10-12
"""
from alembic import op

import sqlalchemy as sa

revision = "u5v6essaigardefou"
down_revision = "t4u5redactionv2b"
branch_labels = None
depends_on = None

TABLE = "usage_ia"


def _have(insp, table):
    return {c["name"] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    if "users" in tables and "trial_analyses_used" not in _have(insp, "users"):
        op.add_column("users", sa.Column("trial_analyses_used", sa.Integer(), nullable=True, server_default="0"))
        # Comptes en essai à la mise en service : le compteur repart de ce qu'ils ont déjà consommé
        # ce mois-ci (borne basse sûre : jamais plus d'analyses que l'essai n'en compte).
        bind.execute(sa.text(
            "UPDATE users SET trial_analyses_used = COALESCE(analyses_used_this_month, 0) "
            "WHERE trial_ends_at IS NOT NULL"))
    if TABLE not in tables:
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("compte", sa.String(40), nullable=False),
            sa.Column("billing_user_id", sa.Integer(), nullable=True),
            sa.Column("org_id", sa.Integer(), nullable=True),
            sa.Column("periode", sa.String(7), nullable=False),
            sa.Column("essai", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("cout_eur", sa.Float(), nullable=False, server_default="0"),
            sa.Column("appels", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("tokens_entree", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("tokens_sortie", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("alerte_le", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("compte", "periode", "essai", name="uq_usage_ia_compte_periode_essai"),
        )
        op.create_index("ix_usage_ia_id", TABLE, ["id"])
        op.create_index("ix_usage_ia_compte", TABLE, ["compte"])
        op.create_index("ix_usage_ia_billing_user_id", TABLE, ["billing_user_id"])
        op.create_index("ix_usage_ia_org_id", TABLE, ["org_id"])


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    if TABLE in tables:
        op.drop_table(TABLE)
    if "users" in tables and "trial_analyses_used" in _have(insp, "users"):
        with op.batch_alter_table("users") as b:
            b.drop_column("trial_analyses_used")
