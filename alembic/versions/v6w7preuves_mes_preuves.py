"""rédaction, vague 3 : « Mes preuves » (faits de l'entreprise, chacun avec sa source typée).

Idempotent (comme les révisions précédentes) : la table n'est créée que si elle manque, chaque
colonne et chaque index ne sont ajoutés que s'ils manquent. SQLite (tests, démo) et Postgres
(production). Ajoute la table `preuves` (app.models.Preuve), socle commun de A, I et E1 :
- nature (référence, qualification, équipe, matériel, chiffre clé) et valeur structurée ;
- type de source (dans vos documents | déclaré par vous | source publique | votre estimation),
  détail de la source (passage exact, URL publique datée…), liens vers le document de « Mon
  savoir-faire » et le justificatif déposé (sans clé étrangère : supprimer un document ne doit
  jamais échouer), date du document, date de fin de validité ;
- propriétaire : l'organisation (owner_id = data_owner_id) et, prévu pour la vague 4, le membre du
  groupement (proprietaire_kind / proprietaire_invite_id, 0 = l'organisation) ;
- numéro STABLE par propriétaire (UNIQUE(owner_id, proprietaire_invite_id, numero)) → « F3 » ;
- statut (proposee | acceptee | retiree ; 'supprimee' = numéro réservé, contenu effacé).
Les valeurs par défaut côté base sont celles du modèle : une base neuve (dont une révision
ancienne crée les tables depuis les modèles) et la production montée ont le même schéma.

Aucune donnée existante n'est touchée. Downgrade RÉEL : supprime la table.

Revision ID: v6w7preuves
Revises: u5v6essaigardefou
Create Date: 2026-10-12
"""
from alembic import op

import sqlalchemy as sa

revision = "v6w7preuves"
down_revision = "u5v6essaigardefou"
branch_labels = None
depends_on = None

TABLE = "preuves"


def _colonnes(for_create: bool):
    """Colonnes de la table (hors id), dans l'ordre du modèle. Hors création, aucune contrainte
    NOT NULL ni clé étrangère n'est posée sur une colonne ajoutée (lignes existantes)."""
    opt = not for_create             # colonne ajoutée à une table existante : nullable
    owner_args = [sa.ForeignKey("users.id")] if for_create else []
    return [
        sa.Column("owner_id", sa.Integer(), *owner_args, nullable=opt),
        sa.Column("proprietaire_kind", sa.String(12), nullable=opt, server_default="organisation"),
        sa.Column("proprietaire_invite_id", sa.Integer(), nullable=opt, server_default="0"),
        sa.Column("numero", sa.Integer(), nullable=opt),
        sa.Column("nature", sa.String(20), nullable=opt),
        sa.Column("valeur", sa.JSON(), nullable=True),
        sa.Column("type_source", sa.String(12), nullable=opt, server_default="declare"),
        sa.Column("source", sa.JSON(), nullable=True),
        sa.Column("source_doc_id", sa.Integer(), nullable=True),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("date_source", sa.Date(), nullable=True),
        sa.Column("date_fin_validite", sa.Date(), nullable=True),
        sa.Column("statut", sa.String(12), nullable=opt, server_default="proposee"),
        sa.Column("origine", sa.String(20), nullable=opt, server_default="saisie"),
        sa.Column("empreinte", sa.String(64), nullable=opt, server_default=""),
        sa.Column("cree_par", sa.Integer(), nullable=True),
        sa.Column("accepte_par", sa.Integer(), nullable=True),
        sa.Column("accepte_le", sa.DateTime(), nullable=True),
        sa.Column("retire_le", sa.DateTime(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=opt, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    ]


# (nom, colonnes) — mêmes noms que ceux que SQLAlchemy donne aux colonnes `index=True` du modèle.
_INDEXES = [
    (f"ix_{TABLE}_id", ["id"]),
    (f"ix_{TABLE}_owner_id", ["owner_id"]),
    (f"ix_{TABLE}_proprietaire_invite_id", ["proprietaire_invite_id"]),
    (f"ix_{TABLE}_source_doc_id", ["source_doc_id"]),
    (f"ix_{TABLE}_source_document_id", ["source_document_id"]),
    (f"ix_{TABLE}_empreinte", ["empreinte"]),
]


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if TABLE not in set(insp.get_table_names()):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            *_colonnes(for_create=True),
            sa.UniqueConstraint("owner_id", "proprietaire_invite_id", "numero",
                                name="uq_preuves_owner_proprietaire_numero"),
        )
    else:
        have = {c["name"] for c in insp.get_columns(TABLE)}
        for col in _colonnes(for_create=False):
            if col.name not in have:
                op.add_column(TABLE, col)
    # Index (idempotents). Pas de try/except : sur Postgres un échec avalé laisserait la
    # transaction « aborted » et masquerait la vraie cause.
    insp = sa.inspect(bind)
    existants = {i["name"] for i in insp.get_indexes(TABLE)}
    for name, cols in _INDEXES:
        if name not in existants:
            op.create_index(name, TABLE, cols, unique=False)


def downgrade():
    bind = op.get_bind()
    if TABLE in set(sa.inspect(bind).get_table_names()):
        op.drop_table(TABLE)
