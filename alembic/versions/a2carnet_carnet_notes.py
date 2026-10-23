"""rédaction, vague 6 (F) : le carnet de notes — « Apprendre de ses résultats ».

Idempotent (comme les révisions précédentes) : la colonne n'est ajoutée que si elle manque. SQLite (tests, démo) et
Postgres (production). Ajoute :
- `projects.carnet_notes` (JSON, NULL) : le carnet de notes du marché (app.services.carnet_notes, seul point
  d'écriture) — date du passage à « Perdu », demande des notes marquée envoyée, notes validées par l'utilisateur
  critère par critère, courrier de l'acheteur collé, ajout au savoir-faire. Contrat : docs/REDACTION_V6.md
  (section F).

Déploiement sans casse : le code de production précédent ne lit ni n'écrit cette colonne (ses requêtes nomment leurs
colonnes une à une, l'ORM aussi). NULL partout au départ : aucun marché existant n'a de carnet.

Aucune donnée existante n'est touchée. Downgrade RÉEL : supprime la colonne.

Revision ID: a2carnetnotes
Revises: z1entretienchantier
Create Date: 2026-10-19
"""
from alembic import op

import sqlalchemy as sa

revision = "a2carnetnotes"
down_revision = "z1entretienchantier"
branch_labels = None
depends_on = None

TABLE = "projects"
COLONNE = "carnet_notes"


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if TABLE not in set(insp.get_table_names()):
        return
    have = {c["name"] for c in insp.get_columns(TABLE)}
    if COLONNE not in have:
        op.add_column(TABLE, sa.Column(COLONNE, sa.JSON(), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if TABLE in set(insp.get_table_names()) and COLONNE in {c["name"] for c in insp.get_columns(TABLE)}:
        # ALTER TABLE … DROP COLUMN : Postgres, et SQLite depuis 3.35 (colonne sans index ni contrainte).
        op.drop_column(TABLE, COLONNE)
