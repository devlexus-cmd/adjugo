"""rédaction, vague 4 : le dossier de groupement cloisonné (qui écrit quoi, brouillons des partenaires,
validation du dossier assemblé, tâches d'un partenaire).

Idempotent (comme les révisions précédentes) : chaque table n'est créée que si elle manque, chaque
colonne et chaque index ne sont ajoutés que s'ils manquent. SQLite (tests, démo) et Postgres
(production). Ajoute :
- table `dossier_repartitions` (app.models.DossierRepartition) : une ligne par partie du dossier de
  présentation d'un marché en groupement — qui la rédige (chef de file ou partenaire, par son
  invitation), le pré-remplissage sans IA et sa raison, la longueur conseillée, la date limite
  interne, la demande des parts, le plafond de l'aide de l'IA par partie ;
- table `dossier_parts_brouillons` (app.models.DossierPartBrouillon) : les brouillons PRIVÉS d'un
  partenaire (texte, sources, faits, compteurs), rangés à part, jamais lus par le chef de file ;
- table `dossier_validations` (app.models.DossierValidation) : la validation du dossier assemblé par
  chaque membre, sur son empreinte (« à revalider » dès qu'un texte commun change) ;
- colonnes `dossier_section_versions.partage`, `ecrit_par`, `compteurs` : le texte COMMUN d'une partie
  d'un partenaire (envoyé par lui, ou écrit par le chef de file sur sa partie) ;
- colonnes `jobs.portee`, `jobs.invite_id` et `jobs.user_id` rendu FACULTATIF : une tâche lancée par
  un partenaire n'a aucun compte propriétaire (NULL) ; elle appartient à son invitation ;
- colonne `project_invites.espace_hash` : empreinte de la clé de l'espace privé du lien (le chef de file,
  qui a pu transmettre le lien, ne lit jamais la matière privée du partenaire).
Les valeurs par défaut côté base sont celles du modèle : une base neuve (dont une révision ancienne crée
les tables depuis les modèles) et la production montée ont le même schéma.

Déploiement sans casse : le code de production précédent (d6504e4) ne lit ni n'écrit les nouvelles
tables ni les nouvelles colonnes ; il crée toujours ses tâches avec un compte (user_id rempli), et une
tâche de partenaire (user_id NULL) n'apparaît dans aucune de ses requêtes (`user_id IN (…)`).

Aucune donnée existante n'est touchée. Downgrade RÉEL : supprime les trois tables et les colonnes
ajoutées ; les tâches de partenaires (user_id NULL) sont supprimées AVANT de remettre user_id
obligatoire.

Revision ID: x8y9redactionv4
Revises: w7x8analysepartagee
Create Date: 2026-10-13
"""
from alembic import op

import sqlalchemy as sa

revision = "x8y9redactionv4"
down_revision = "w7x8analysepartagee"
branch_labels = None
depends_on = None

REP = "dossier_repartitions"
BRO = "dossier_parts_brouillons"
VAL = "dossier_validations"
VERS = "dossier_section_versions"
JOBS = "jobs"
INV = "project_invites"


def _colonnes_rep(for_create: bool):
    """Colonnes (hors id), dans l'ordre du modèle. Hors création, aucune contrainte NOT NULL n'est
    posée sur une colonne ajoutée (lignes existantes)."""
    opt = not for_create
    fk_d = [sa.ForeignKey("dossiers_presentation.id")] if for_create else []
    fk_s = [sa.ForeignKey("dossier_sections.id")] if for_create else []
    return [
        sa.Column("dossier_id", sa.Integer(), *fk_d, nullable=opt),
        sa.Column("section_id", sa.Integer(), *fk_s, nullable=opt),
        sa.Column("project_id", sa.Integer(), nullable=opt),
        sa.Column("owner_id", sa.Integer(), nullable=opt),
        sa.Column("redacteur", sa.String(14), nullable=opt, server_default="chef_de_file"),
        sa.Column("invite_id", sa.Integer(), nullable=True),
        sa.Column("proposition", sa.JSON(), nullable=True),
        sa.Column("choix", sa.String(12), nullable=opt, server_default="propose"),
        sa.Column("longueur_mots", sa.Integer(), nullable=True),
        sa.Column("date_limite", sa.Date(), nullable=True),
        sa.Column("demandee_le", sa.DateTime(), nullable=True),
        sa.Column("relance_palier", sa.Integer(), nullable=opt, server_default="0"),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("aides_ia", sa.Integer(), nullable=opt, server_default="0"),
        sa.Column("lock_version", sa.Integer(), nullable=opt, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    ]


def _colonnes_bro(for_create: bool):
    opt = not for_create
    fk_s = [sa.ForeignKey("dossier_sections.id")] if for_create else []
    return [
        sa.Column("section_id", sa.Integer(), *fk_s, nullable=opt),
        sa.Column("dossier_id", sa.Integer(), nullable=opt),
        sa.Column("project_id", sa.Integer(), nullable=opt),
        sa.Column("owner_id", sa.Integer(), nullable=opt),
        sa.Column("invite_id", sa.Integer(), nullable=opt),
        sa.Column("numero", sa.Integer(), nullable=opt, server_default="1"),
        sa.Column("texte", sa.Text(), nullable=True),
        sa.Column("origine", sa.String(12), nullable=opt, server_default="utilisateur"),
        sa.Column("ia", sa.Boolean(), nullable=opt, server_default=sa.false()),
        sa.Column("sources", sa.JSON(), nullable=True),
        sa.Column("faits", sa.JSON(), nullable=True),
        sa.Column("compteurs", sa.JSON(), nullable=True),
        sa.Column("empreinte", sa.String(64), nullable=opt, server_default=""),
        sa.Column("coupe", sa.Boolean(), nullable=opt, server_default=sa.false()),
        sa.Column("base_id", sa.Integer(), nullable=True),
        sa.Column("base_version_id", sa.Integer(), nullable=True),
        sa.Column("auteur_user_id", sa.Integer(), nullable=True),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    ]


def _colonnes_val(for_create: bool):
    opt = not for_create
    fk_d = [sa.ForeignKey("dossiers_presentation.id")] if for_create else []
    return [
        sa.Column("dossier_id", sa.Integer(), *fk_d, nullable=opt),
        sa.Column("project_id", sa.Integer(), nullable=opt),
        sa.Column("owner_id", sa.Integer(), nullable=opt),
        sa.Column("membre", sa.String(14), nullable=opt, server_default="chef_de_file"),
        sa.Column("membre_cle", sa.String(24), nullable=opt),
        sa.Column("invite_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("empreinte", sa.String(64), nullable=opt, server_default=""),
        sa.Column("statut", sa.String(12), nullable=opt, server_default="valide"),
        sa.Column("valide_le", sa.DateTime(), nullable=True),
        sa.Column("perime_le", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    ]


# Colonnes ajoutées à des tables EXISTANTES : facultatives (comme dans le modèle), valeur par défaut
# côté base identique à celle du modèle.
_AJOUTS = [
    (VERS, sa.Column("partage", sa.Boolean(), nullable=True, server_default=sa.false())),
    (VERS, sa.Column("ecrit_par", sa.String(14), nullable=True, server_default="")),
    (VERS, sa.Column("compteurs", sa.JSON(), nullable=True)),
    (JOBS, sa.Column("portee", sa.String(12), nullable=True, server_default="")),
    (JOBS, sa.Column("invite_id", sa.Integer(), nullable=True)),
    (INV, sa.Column("espace_hash", sa.String(64), nullable=True, server_default="")),
]

# (table, nom, colonnes, unique) — mêmes noms que ceux que SQLAlchemy donne aux colonnes `index=True`
# (unique=True + index=True → index UNIQUE ix_<table>_<colonne>, comme une base neuve).
_INDEXES = [
    (REP, f"ix_{REP}_id", ["id"], False),
    (REP, f"ix_{REP}_dossier_id", ["dossier_id"], False),
    (REP, f"ix_{REP}_section_id", ["section_id"], True),
    (REP, f"ix_{REP}_project_id", ["project_id"], False),
    (REP, f"ix_{REP}_owner_id", ["owner_id"], False),
    (REP, f"ix_{REP}_invite_id", ["invite_id"], False),
    (BRO, f"ix_{BRO}_id", ["id"], False),
    (BRO, f"ix_{BRO}_section_id", ["section_id"], False),
    (BRO, f"ix_{BRO}_dossier_id", ["dossier_id"], False),
    (BRO, f"ix_{BRO}_project_id", ["project_id"], False),
    (BRO, f"ix_{BRO}_owner_id", ["owner_id"], False),
    (BRO, f"ix_{BRO}_invite_id", ["invite_id"], False),
    (VAL, f"ix_{VAL}_id", ["id"], False),
    (VAL, f"ix_{VAL}_dossier_id", ["dossier_id"], False),
    (VAL, f"ix_{VAL}_project_id", ["project_id"], False),
    (VAL, f"ix_{VAL}_owner_id", ["owner_id"], False),
    (VAL, f"ix_{VAL}_invite_id", ["invite_id"], False),
    (JOBS, f"ix_{JOBS}_invite_id", ["invite_id"], False),
]


def _table(bind, name, colonnes, contraintes=()):
    insp = sa.inspect(bind)
    if name not in set(insp.get_table_names()):
        op.create_table(name, sa.Column("id", sa.Integer(), primary_key=True), *colonnes(for_create=True),
                        *contraintes)
        return
    have = {c["name"] for c in insp.get_columns(name)}
    for col in colonnes(for_create=False):
        if col.name not in have:
            op.add_column(name, col)


def upgrade():
    bind = op.get_bind()
    _table(bind, REP, _colonnes_rep)
    _table(bind, BRO, _colonnes_bro)
    _table(bind, VAL, _colonnes_val,
           (sa.UniqueConstraint("dossier_id", "membre_cle", name="uq_dossier_validations_membre"),))
    insp = sa.inspect(bind)
    for table, col in _AJOUTS:
        if col.name not in {c["name"] for c in insp.get_columns(table)}:
            op.add_column(table, col)
    # Une tâche de partenaire n'a aucun compte propriétaire : user_id devient facultatif.
    insp = sa.inspect(bind)
    uid = next((c for c in insp.get_columns(JOBS) if c["name"] == "user_id"), None)
    if uid is not None and not uid.get("nullable", True):
        with op.batch_alter_table(JOBS) as b:
            b.alter_column("user_id", existing_type=sa.Integer(), nullable=True)
    # Index (idempotents). Pas de try/except : sur Postgres un échec avalé laisserait la transaction
    # « aborted » et masquerait la vraie cause.
    insp = sa.inspect(bind)
    existants = {t: {i["name"] for i in insp.get_indexes(t)} for t in (REP, BRO, VAL, JOBS)}
    for table, name, cols, unique in _INDEXES:
        if name not in existants[table]:
            op.create_index(name, table, cols, unique=unique)


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    for name in (VAL, BRO, REP):
        if name in tables:
            op.drop_table(name)
    insp = sa.inspect(bind)
    jcols = {c["name"]: c for c in insp.get_columns(JOBS)}
    # Les tâches de partenaires (sans compte) ne peuvent pas survivre au retour de user_id obligatoire.
    bind.execute(sa.text("DELETE FROM jobs WHERE user_id IS NULL"))
    if f"ix_{JOBS}_invite_id" in {i["name"] for i in insp.get_indexes(JOBS)}:
        op.drop_index(f"ix_{JOBS}_invite_id", table_name=JOBS)
    with op.batch_alter_table(JOBS) as b:
        for name in ("invite_id", "portee"):
            if name in jcols:
                b.drop_column(name)
        if "user_id" in jcols and jcols["user_id"].get("nullable", True):
            b.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
    vcols = {c["name"] for c in sa.inspect(bind).get_columns(VERS)}
    with op.batch_alter_table(VERS) as b:
        for name in ("compteurs", "ecrit_par", "partage"):
            if name in vcols:
                b.drop_column(name)
    if "espace_hash" in {c["name"] for c in sa.inspect(bind).get_columns(INV)}:
        with op.batch_alter_table(INV) as b:
            b.drop_column("espace_hash")
