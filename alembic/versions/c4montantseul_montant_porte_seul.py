"""réorganisation de l'interface, vague 2a (A3) : « montant que je porte seul », dans Mon entreprise › Ce que je cherche.

Idempotent (comme les révisions précédentes) : la colonne n'est ajoutée que si elle manque. SQLite (tests, démo) et
Postgres (production). Ajoute :
- `matching_criteria_ext.montant_porte_seul` (FLOAT, NULL) : le plus gros marché, ou la plus grosse partie d'un
  marché, que l'entreprise réalise seule, en euros HT, DÉCLARÉ par elle. Aucune valeur par défaut : chaque ligne
  existante reste VIDE (NULL). On ne le déduit jamais de `budget_max` (500 000 € par défaut, une fourchette de
  préférence) ni d'un autre champ. Seul point d'écriture : PUT /api/criteria/ (app/routers/criteria_v2.py). Contrat :
  docs/REORGANISATION_V2A.md, section A3 (étude « organisation du logiciel », § 5.3 et § 7.1).

Déploiement sans casse : le code de production précédent ne lit ni n'écrit cette colonne (son modèle ne la déclare
pas) ; aucune donnée existante n'est touchée. Downgrade RÉEL : supprime la colonne (les montants saisis sont perdus,
rien d'autre).

Revision ID: c4montantseul
Revises: c4axeetapes (réunion de la vague 2a : une seule tête, A1 puis A3 ; les deux
révisions sont indépendantes, l'ordre ne change rien à l'une ni à l'autre)
Create Date: 2026-10-20
"""
from alembic import op

import sqlalchemy as sa

revision = "c4montantseul"
down_revision = "c4axeetapes"
branch_labels = None
depends_on = None

TABLE = "matching_criteria_ext"
COLONNE = "montant_porte_seul"


def _colonnes(bind) -> set:
    insp = sa.inspect(bind)
    if TABLE not in set(insp.get_table_names()):
        return set()
    return {c["name"] for c in insp.get_columns(TABLE)}


def upgrade():
    bind = op.get_bind()
    if TABLE not in set(sa.inspect(bind).get_table_names()):
        return                      # créée par la révision initiale : son absence n'est pas notre affaire ici
    if COLONNE in _colonnes(bind):
        return                      # déjà là (rejeu, ou table créée par create_all depuis le modèle actuel)
    op.add_column(TABLE, sa.Column(COLONNE, sa.Float(), nullable=True))


def downgrade():
    bind = op.get_bind()
    if COLONNE not in _colonnes(bind):
        return
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_column(COLONNE)
