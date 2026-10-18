"""rédaction, vague 4 (décision 5, option a) : les documents PRIVÉS déposés par le lien d'un partenaire.

Idempotent (comme les révisions précédentes) : chaque table n'est créée que si elle manque, chaque colonne et
chaque index ne sont ajoutés que s'ils manquent. SQLite (tests, démo) et Postgres (production). Ajoute :
- table `depots_lien_espaces` (app.models.DepotLienEspace) : l'accord du partenaire (conditions d'utilisation et
  politique de confidentialité, versions et empreintes des textes, horodaté) et la date du résultat du marché
  constatée par la purge (départ des 6 mois de conservation) ;
- table `depots_lien_documents` (app.models.DepotLienDocument) : les documents déposés, rattachés à l'INVITATION
  (jamais à l'organisation du chef de file), fichier rangé sous invitations/<id>/depots/… ;
- table `depots_lien_morceaux` (app.models.DepotLienMorceau) : leurs passages (CV retirés), cherchés sans IA.
Aucune clé étrangère (effacement explicite et ordonné, comme dossier_parts_brouillons.invite_id). Les valeurs par
défaut côté base sont celles du modèle : une base neuve (dont une révision ancienne crée les tables depuis les
modèles) et la production montée ont le même schéma.

Déploiement sans casse : le code de production précédent (a7f48d2) ne lit ni n'écrit ces tables. Aucune donnée
existante n'est touchée. Downgrade RÉEL : supprime les trois tables (les fichiers déposés restent dans le
stockage, sans plus aucun accès ; la purge les ignore : à supprimer à la main sous invitations/*/depots/ si le
retour arrière est définitif).

Revision ID: y9z0depotlien
Revises: x8y9redactionv4
Create Date: 2026-10-19
"""
from alembic import op

import sqlalchemy as sa

revision = "y9z0depotlien"
down_revision = "x8y9redactionv4"
branch_labels = None
depends_on = None

ESP = "depots_lien_espaces"
DOC = "depots_lien_documents"
MOR = "depots_lien_morceaux"


def _colonnes_esp(for_create: bool):
    """Colonnes (hors id), dans l'ordre du modèle. Hors création, aucune contrainte NOT NULL n'est posée sur une
    colonne ajoutée (lignes existantes)."""
    opt = not for_create
    return [
        sa.Column("invite_id", sa.Integer(), nullable=opt),
        sa.Column("project_id", sa.Integer(), nullable=opt),
        sa.Column("owner_id", sa.Integer(), nullable=opt),
        sa.Column("consentement", sa.JSON(), nullable=True),
        sa.Column("accepte_le", sa.DateTime(), nullable=True),
        sa.Column("resultat_le", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    ]


def _colonnes_doc(for_create: bool):
    opt = not for_create
    return [
        sa.Column("invite_id", sa.Integer(), nullable=opt),
        sa.Column("project_id", sa.Integer(), nullable=opt),
        sa.Column("owner_id", sa.Integer(), nullable=opt),
        sa.Column("nom", sa.String(300), nullable=opt, server_default=""),
        sa.Column("file_key", sa.String(500), nullable=opt, server_default=""),
        sa.Column("taille", sa.Integer(), nullable=opt, server_default="0"),
        sa.Column("type_mime", sa.String(100), nullable=opt, server_default=""),
        sa.Column("empreinte", sa.String(64), nullable=opt, server_default=""),
        sa.Column("caracteres", sa.Integer(), nullable=opt, server_default="0"),
        sa.Column("lecture", sa.String(12), nullable=opt, server_default="texte"),
        sa.Column("complet", sa.Boolean(), nullable=opt, server_default=sa.true()),
        sa.Column("morceaux", sa.Integer(), nullable=opt, server_default="0"),
        sa.Column("lignes_cv_retirees", sa.Integer(), nullable=opt, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    ]


def _colonnes_mor(for_create: bool):
    opt = not for_create
    return [
        sa.Column("document_id", sa.Integer(), nullable=opt),
        sa.Column("invite_id", sa.Integer(), nullable=opt),
        sa.Column("ordinal", sa.Integer(), nullable=opt, server_default="0"),
        sa.Column("texte", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    ]


# (table, nom, colonnes, unique) — mêmes noms que ceux que SQLAlchemy donne aux colonnes `index=True`
# (unique=True + index=True → index UNIQUE ix_<table>_<colonne>, comme une base neuve).
_INDEXES = [
    (ESP, f"ix_{ESP}_id", ["id"], False),
    (ESP, f"ix_{ESP}_invite_id", ["invite_id"], True),
    (ESP, f"ix_{ESP}_project_id", ["project_id"], False),
    (ESP, f"ix_{ESP}_owner_id", ["owner_id"], False),
    (DOC, f"ix_{DOC}_id", ["id"], False),
    (DOC, f"ix_{DOC}_invite_id", ["invite_id"], False),
    (DOC, f"ix_{DOC}_project_id", ["project_id"], False),
    (DOC, f"ix_{DOC}_owner_id", ["owner_id"], False),
    (MOR, f"ix_{MOR}_id", ["id"], False),
    (MOR, f"ix_{MOR}_document_id", ["document_id"], False),
    (MOR, f"ix_{MOR}_invite_id", ["invite_id"], False),
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
    _table(bind, ESP, _colonnes_esp)
    _table(bind, DOC, _colonnes_doc)
    _table(bind, MOR, _colonnes_mor)
    # Index (idempotents). Pas de try/except : sur Postgres un échec avalé laisserait la transaction « aborted »
    # et masquerait la vraie cause.
    insp = sa.inspect(bind)
    existants = {t: {i["name"] for i in insp.get_indexes(t)} for t in (ESP, DOC, MOR)}
    for table, name, cols, unique in _INDEXES:
        if name not in existants[table]:
            op.create_index(name, table, cols, unique=unique)


def downgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    for name in (MOR, DOC, ESP):
        if name in tables:
            op.drop_table(name)
