"""réorganisation de l'interface, vague 1 (1.1) : la mesure d'usage — un compteur par écran et par jour.

Idempotent (comme les révisions précédentes) : la table n'est créée que si elle manque. SQLite (tests, démo) et
Postgres (production). Ajoute :
- `mesure_ecrans` (jour DATE, ecran VARCHAR(40), ouvertures INTEGER) : clé primaire (jour, ecran). Combien de fois
  chaque écran de l'application a été ouvert ce jour-là (heure de Paris). AUCUNE donnée personnelle (ni compte, ni
  organisation, ni adresse IP). Seul point d'écriture : app.services.mesure_usage. Contrat :
  docs/REORGANISATION_V1.md, § 1.1 (décision 17 de l'étude « organisation du logiciel »).

Déploiement sans casse : le code de production précédent ignore cette table. Aucune donnée existante n'est
touchée. Downgrade RÉEL : supprime la table (les compteurs sont perdus, rien d'autre).

Revision ID: b3mesureecrans
Revises: a2carnetnotes
Create Date: 2026-10-19
"""
from alembic import op

import sqlalchemy as sa

revision = "b3mesureecrans"
down_revision = "a2carnetnotes"
branch_labels = None
depends_on = None

TABLE = "mesure_ecrans"


def upgrade():
    bind = op.get_bind()
    if TABLE in set(sa.inspect(bind).get_table_names()):
        return
    op.create_table(
        TABLE,
        sa.Column("jour", sa.Date(), nullable=False),
        sa.Column("ecran", sa.String(40), nullable=False),
        sa.Column("ouvertures", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("jour", "ecran"),
    )


def downgrade():
    bind = op.get_bind()
    if TABLE in set(sa.inspect(bind).get_table_names()):
        op.drop_table(TABLE)
