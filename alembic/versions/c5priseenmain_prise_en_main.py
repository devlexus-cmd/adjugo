"""réorganisation de l'interface, vague 2b (B1) : la prise en main — l'état de « Vos premiers pas » et de la carte
« Faites-vous trouver » gardé sur le serveur, et la réponse « Je ne sais pas » au montant porté seul.

Idempotent (comme les révisions précédentes) : chaque colonne n'est ajoutée que si elle manque. SQLite (tests, démo)
et Postgres (production). Ajoute :
- `users.premiers_pas_replie` (BOOLEAN, défaut faux) : la liste « Vos premiers pas » de l'accueil est repliée ;
- `users.suggestion_reseau` (VARCHAR(12), défaut "") : la carte « Faites-vous trouver pour des groupements »
  — "" jamais proposée, "a_montrer" proposée (après l'inscription ou l'acceptation d'une invitation), "fermee" ;
- `matching_criteria_ext.montant_porte_seul_inconnu` (BOOLEAN, défaut faux) : « Je ne sais pas » coché à la
  question « Jusqu'à quel montant répondez-vous seul ? ». Distinct d'un montant VIDE (jamais répondu).
Chaque ligne existante prend la valeur par défaut : rien de replié, aucune carte proposée, aucune réponse inventée.
Seuls points d'écriture : app/routers/prise_en_main.py, app/services/prise_en_main.py, PUT /api/criteria/
(app/routers/criteria_v2.py). Contrat : docs/REORGANISATION_V2B.md, section B1.

Déploiement sans casse : le code de production précédent ne déclare pas ces colonnes ; ses écritures (création d'un
compte, de critères) les omettent et la base pose la valeur par défaut (server_default), ses lectures les ignorent.
Downgrade RÉEL : supprime les trois colonnes (l'état replié, la carte et les « Je ne sais pas » sont perdus, rien
d'autre).

Revision ID: c5priseenmain
Revises: c4montantseul
Create Date: 2026-10-20
"""
from alembic import op

import sqlalchemy as sa

revision = "c5priseenmain"
down_revision = "c4montantseul"
branch_labels = None
depends_on = None

# Mêmes définitions que celles que pose la réconciliation b7d9e1f3a2c4 (sync_models) sur une base NEUVE à partir du
# modèle actuel (colonne NULL permise, valeur par défaut du modèle côté base) : une base de production migrée et une
# base neuve ont exactement le même schéma. Le code lit NULL comme la valeur par défaut.
COLONNES = [
    ("users", "premiers_pas_replie", lambda: sa.Column("premiers_pas_replie", sa.Boolean(), nullable=True,
                                                      server_default=sa.text("false"))),
    ("users", "suggestion_reseau", lambda: sa.Column("suggestion_reseau", sa.String(12), nullable=True,
                                                    server_default=sa.text("''"))),
    ("matching_criteria_ext", "montant_porte_seul_inconnu",
     lambda: sa.Column("montant_porte_seul_inconnu", sa.Boolean(), nullable=True, server_default=sa.text("false"))),
]


def _colonnes(bind, table) -> set:
    insp = sa.inspect(bind)
    if table not in set(insp.get_table_names()):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    for table, nom, colonne in COLONNES:
        if table not in tables:
            continue                # créée par une révision antérieure : son absence n'est pas notre affaire ici
        if nom in _colonnes(bind, table):
            continue                # déjà là (rejeu, ou table créée par create_all depuis le modèle actuel)
        op.add_column(table, colonne())


def downgrade():
    bind = op.get_bind()
    for table, nom, _ in reversed(COLONNES):
        if nom not in _colonnes(bind, table):
            continue
        with op.batch_alter_table(table) as batch:
            batch.drop_column(nom)
