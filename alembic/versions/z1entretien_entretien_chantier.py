"""rédaction, vague 5 (D) : l'entretien chantier — « Adjugo demande au lieu de deviner ».

Idempotent (comme les révisions précédentes) : la table n'est créée que si elle manque, chaque colonne et
chaque index ne sont ajoutés que s'ils manquent. SQLite (tests, démo) et Postgres (production). Ajoute :
- table `entretien_questions` (app.models.EntretienQuestion) : une ligne par question de l'entretien
  chantier d'un dossier de présentation — la question, la phrase du dossier de l'acheteur qui la motive
  (retrouvée mot pour mot), son numéro STABLE (renvoi « [R3] » du contrôle des faits), à qui elle est posée
  (l'organisation du chef de file ou un partenaire du groupement, par son invitation) et la réponse (un fait
  « déclaré par vous », ou par ce partenaire). Contrat : docs/REDACTION_V5.md (section D).
Les valeurs par défaut côté base sont celles du modèle : une base neuve (dont une révision ancienne crée
les tables depuis les modèles) et la production montée ont le même schéma.

Déploiement sans casse : le code de production précédent ne lit ni n'écrit cette table ; elle ne référence
que `dossiers_presentation` (clé étrangère, comme les tables de la vague 4).

Aucune donnée existante n'est touchée. Downgrade RÉEL : supprime la table.

Revision ID: z1entretienchantier
Revises: y9z0depotlien
Create Date: 2026-10-19
"""
from alembic import op

import sqlalchemy as sa

revision = "z1entretienchantier"
down_revision = "y9z0depotlien"
branch_labels = None
depends_on = None

ENT = "entretien_questions"


def _colonnes(for_create: bool):
    """Colonnes (hors id), dans l'ordre du modèle. Hors création, aucune contrainte NOT NULL n'est posée sur
    une colonne ajoutée (lignes existantes)."""
    opt = not for_create
    fk_d = [sa.ForeignKey("dossiers_presentation.id")] if for_create else []
    return [
        sa.Column("dossier_id", sa.Integer(), *fk_d, nullable=opt),
        sa.Column("project_id", sa.Integer(), nullable=opt),
        sa.Column("owner_id", sa.Integer(), nullable=opt),
        sa.Column("numero", sa.Integer(), nullable=opt),
        sa.Column("code", sa.String(80), nullable=opt),
        sa.Column("origine", sa.String(10), nullable=opt, server_default="banque"),
        sa.Column("theme", sa.String(160), nullable=opt, server_default=""),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("type_reponse", sa.String(10), nullable=opt, server_default="texte"),
        sa.Column("motif", sa.Text(), nullable=True),
        sa.Column("motif_piece", sa.String(200), nullable=opt, server_default=""),
        sa.Column("ordre", sa.Integer(), nullable=opt, server_default="0"),
        sa.Column("retiree_le", sa.DateTime(), nullable=True),
        sa.Column("adresse_kind", sa.String(12), nullable=opt, server_default="organisation"),
        sa.Column("adresse_invite_id", sa.Integer(), nullable=True),
        sa.Column("adresse_choix", sa.String(10), nullable=opt, server_default="propose"),
        sa.Column("statut", sa.String(12), nullable=opt, server_default="a_repondre"),
        sa.Column("reponse", sa.Text(), nullable=True),
        sa.Column("reponse_preuve_id", sa.Integer(), nullable=True),
        sa.Column("reponse_kind", sa.String(12), nullable=opt, server_default=""),
        sa.Column("reponse_invite_id", sa.Integer(), nullable=True),
        sa.Column("reponse_user_id", sa.Integer(), nullable=True),
        sa.Column("repondu_le", sa.DateTime(), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=opt, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    ]


# (nom, colonnes, unique) — mêmes noms que ceux que SQLAlchemy donne aux colonnes `index=True`.
_INDEXES = [
    (f"ix_{ENT}_id", ["id"], False),
    (f"ix_{ENT}_dossier_id", ["dossier_id"], False),
    (f"ix_{ENT}_project_id", ["project_id"], False),
    (f"ix_{ENT}_owner_id", ["owner_id"], False),
    (f"ix_{ENT}_adresse_invite_id", ["adresse_invite_id"], False),
    (f"ix_{ENT}_reponse_invite_id", ["reponse_invite_id"], False),
]


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if ENT not in set(insp.get_table_names()):
        op.create_table(ENT, sa.Column("id", sa.Integer(), primary_key=True), *_colonnes(for_create=True),
                        sa.UniqueConstraint("dossier_id", "numero", name="uq_entretien_questions_numero"),
                        sa.UniqueConstraint("dossier_id", "code", name="uq_entretien_questions_code"))
    else:
        have = {c["name"] for c in insp.get_columns(ENT)}
        for col in _colonnes(for_create=False):
            if col.name not in have:
                op.add_column(ENT, col)
    # Index (idempotents). Pas de try/except : sur Postgres un échec avalé laisserait la transaction
    # « aborted » et masquerait la vraie cause.
    existants = {i["name"] for i in sa.inspect(bind).get_indexes(ENT)}
    for name, cols, unique in _INDEXES:
        if name not in existants:
            op.create_index(name, ENT, cols, unique=unique)


def downgrade():
    bind = op.get_bind()
    if ENT in set(sa.inspect(bind).get_table_names()):
        op.drop_table(ENT)
