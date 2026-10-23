"""analyse partagée : extraction d'un dossier gardée sans donnée d'entreprise, et mesure des doublons.

Idempotent (comme les révisions précédentes) : chaque table n'est créée que si elle manque, chaque
colonne et chaque index ne sont ajoutés que s'ils manquent. SQLite (tests, démo) et Postgres
(production). Ajoute :
- table `analyses_partagees` (app.models.AnalysePartagee) : l'extraction d'un dossier de consultation
  par l'IA (faits du document PUBLIC de l'acheteur, aucune donnée d'entreprise, aucune colonne de
  propriétaire), resservie quand ce même dossier, exactement, est analysé à nouveau. Clé unique =
  empreinte de tout ce que l'IA reçoit (consignes, modèles, lecture, langue, texte des pièces). En
  lecture en deux temps, les informations relevées partie par partie (`parties`) et le déroulé de la
  lecture (`deroule` : durées, instants) ;
- table `analyse_empreintes` (app.models.AnalyseEmpreinte) : une ligne par analyse, avec l'empreinte
  normalisée des pièces (jamais leur contenu) et l'organisation, pour mesurer les doublons entre
  organisations (interne, jamais montré à un client). Sans clé étrangère, comme usage_ia.
Les valeurs par défaut côté base sont celles du modèle : une base neuve (dont une révision ancienne
crée les tables depuis les modèles) et la production montée ont le même schéma.

Aucune donnée existante n'est touchée. Downgrade RÉEL : supprime les deux tables.

Revision ID: w7x8analysepartagee
Revises: v6w7preuves
Create Date: 2026-10-13
"""
from alembic import op

import sqlalchemy as sa

revision = "w7x8analysepartagee"
down_revision = "v6w7preuves"
branch_labels = None
depends_on = None

CACHE = "analyses_partagees"
MESURE = "analyse_empreintes"


def _colonnes_cache(for_create: bool):
    """Colonnes (hors id), dans l'ordre du modèle. Hors création, aucune contrainte NOT NULL n'est
    posée sur une colonne ajoutée (lignes existantes)."""
    opt = not for_create
    return [
        sa.Column("cle", sa.String(64), nullable=opt),
        sa.Column("nature", sa.String(12), nullable=opt, server_default="dossier"),
        sa.Column("mode", sa.String(20), nullable=opt, server_default=""),
        sa.Column("version", sa.String(40), nullable=opt, server_default=""),
        sa.Column("modele", sa.String(200), nullable=opt, server_default=""),
        sa.Column("extraction", sa.JSON(), nullable=opt),
        sa.Column("rapport", sa.JSON(), nullable=True),
        sa.Column("parties", sa.JSON(), nullable=True),
        sa.Column("deroule", sa.JSON(), nullable=True),
        sa.Column("duree_s", sa.Float(), nullable=opt, server_default="0"),
        sa.Column("cout_eur", sa.Float(), nullable=opt, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("utilise_le", sa.DateTime(), nullable=True),
    ]


def _colonnes_mesure(for_create: bool):
    opt = not for_create
    return [
        sa.Column("owner_id", sa.Integer(), nullable=opt),
        sa.Column("nature", sa.String(12), nullable=opt, server_default="dossier"),
        sa.Column("empreinte", sa.String(64), nullable=opt),
        sa.Column("cle", sa.String(64), nullable=True),
        sa.Column("servi_du_cache", sa.Boolean(), nullable=opt, server_default=sa.false()),
        sa.Column("economie_eur", sa.Float(), nullable=opt, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    ]


# (table, nom, colonnes, unique) — mêmes noms que ceux que SQLAlchemy donne aux colonnes `index=True`
# (unique=True + index=True → index UNIQUE ix_<table>_<colonne>, comme une base neuve).
_INDEXES = [
    (CACHE, f"ix_{CACHE}_id", ["id"], False),
    (CACHE, f"ix_{CACHE}_cle", ["cle"], True),
    (CACHE, f"ix_{CACHE}_utilise_le", ["utilise_le"], False),
    (MESURE, f"ix_{MESURE}_id", ["id"], False),
    (MESURE, f"ix_{MESURE}_owner_id", ["owner_id"], False),
    (MESURE, f"ix_{MESURE}_empreinte", ["empreinte"], False),
    (MESURE, f"ix_{MESURE}_cle", ["cle"], False),
    (MESURE, f"ix_{MESURE}_created_at", ["created_at"], False),
]


def _table(bind, name, colonnes):
    insp = sa.inspect(bind)
    if name not in set(insp.get_table_names()):
        op.create_table(name, sa.Column("id", sa.Integer(), primary_key=True), *colonnes(for_create=True))
        return
    have = {c["name"] for c in insp.get_columns(name)}
    for col in colonnes(for_create=False):
        if col.name not in have:
            op.add_column(name, col)


def upgrade():
    bind = op.get_bind()
    _table(bind, CACHE, _colonnes_cache)
    _table(bind, MESURE, _colonnes_mesure)
    # Index (idempotents). Pas de try/except : sur Postgres un échec avalé laisserait la transaction
    # « aborted » et masquerait la vraie cause.
    insp = sa.inspect(bind)
    existants = {t: {i["name"] for i in insp.get_indexes(t)} for t in (CACHE, MESURE)}
    for table, name, cols, unique in _INDEXES:
        if name not in existants[table]:
            op.create_index(name, table, cols, unique=unique)


def downgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    for name in (MESURE, CACHE):
        if name in tables:
            op.drop_table(name)
