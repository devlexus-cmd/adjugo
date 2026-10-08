"""co-traitance v2 (vague 2) : convention de groupement et accords des membres.

Idempotent (comme les migrations précédentes) : chaque table / colonne / index n'est créé
que s'il manque. Compatible SQLite (tests, démo) et Postgres (production). Ajoute :
- groupement_conventions (1 par marché)  → forme, ce que le règlement impose (citation
  vérifiée), habilitation du mandataire, paramètres, texte figé + empreinte sha256 unique,
  total de l'offre figé, version ;
- groupement_signatures                   → accord de chaque membre sur LE texte (même
  empreinte), niveau d'identité prouvé, statut pending|signed|perimee|hors_ligne ;
  UNIQUE(convention_id, invite_id) et UNIQUE(convention_id, cotraitant_link_id) ;
- project_contributions.representant_legal / signataire_qualite si absentes (déjà posées
  par n8o9p0q1r2s3 ; re-vérifiées ici pour une base qui aurait sauté cette révision).

Aucune donnée existante n'est modifiée. Pas de downgrade destructif (comme les précédentes).
NB : sur une base NEUVE, les create_all des révisions antérieures créent déjà ces tables à
partir des modèles — cette révision ne fait alors rien (vérification d'existence partout).

Revision ID: o9p0q1r2s3t4
Revises: n8o9p0q1r2s3
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa

revision = "o9p0q1r2s3t4"
down_revision = "n8o9p0q1r2s3"
branch_labels = None
depends_on = None


# (nom, type, server_default) — colonnes hors clé primaire, toutes NULLABLES à l'ajout
# (ajouter une colonne NOT NULL à une table existante échouerait sur une table non vide).
_CONV_COLS = [
    ("project_id", sa.Integer, None),
    ("owner_id", sa.Integer, None),
    ("forme", lambda: sa.String(12), ""),
    ("mandataire_solidaire", sa.Boolean, sa.text("false")),
    ("forme_imposee", lambda: sa.String(16), "non_verifie"),
    ("forme_imposee_extrait", sa.Text, None),
    ("habilitation", sa.JSON, None),
    ("params", sa.JSON, None),
    ("status", lambda: sa.String(12), "draft"),
    ("content_md", sa.Text, None),
    ("content_hash", lambda: sa.String(64), None),
    ("total_offre_ht", sa.Float, None),
    ("version", sa.Integer, "0"),
    ("frozen_at", sa.DateTime, None),
    ("created_at", sa.DateTime, None),
    ("updated_at", sa.DateTime, None),
]
_SIG_COLS = [
    ("convention_id", sa.Integer, None),
    ("project_id", sa.Integer, None),
    ("owner_id", sa.Integer, None),
    ("invite_id", sa.Integer, None),
    ("cotraitant_link_id", sa.Integer, None),
    ("user_id", sa.Integer, None),
    ("company_name", lambda: sa.String(255), ""),
    ("siret", lambda: sa.String(20), ""),
    ("signataire_nom", lambda: sa.String(255), ""),
    ("signataire_qualite", lambda: sa.String(120), ""),
    ("content_hash", lambda: sa.String(64), ""),
    ("identity_level", lambda: sa.String(20), ""),
    ("status", lambda: sa.String(12), "pending"),
    ("verified_email", lambda: sa.String(255), ""),
    ("signed_at", sa.DateTime, None),
    ("ip", lambda: sa.String(45), ""),
]
_CONTRIB_COLS = [
    ("representant_legal", lambda: sa.String(255), ""),
    ("signataire_qualite", lambda: sa.String(120), ""),
]

# Colonnes NOT NULL et clés étrangères à la CRÉATION de table (pas à l'ajout de colonne).
_NOT_NULL = {"groupement_conventions": {"project_id", "owner_id"},
             "groupement_signatures": {"convention_id", "project_id", "owner_id"}}
_FKS = {
    "groupement_conventions": {"project_id": "projects.id", "owner_id": "users.id"},
    "groupement_signatures": {"convention_id": "groupement_conventions.id",
                              "invite_id": "project_invites.id",
                              "cotraitant_link_id": "project_cotraitants.id"},
}

# (nom, table, colonnes, unique)
_INDEXES = [
    ("ix_groupement_conventions_id", "groupement_conventions", ["id"], False),
    ("ix_groupement_conventions_project_id", "groupement_conventions", ["project_id"], True),
    ("ix_groupement_conventions_owner_id", "groupement_conventions", ["owner_id"], False),
    ("ix_groupement_conventions_content_hash", "groupement_conventions", ["content_hash"], True),
    ("ix_groupement_signatures_id", "groupement_signatures", ["id"], False),
    ("ix_groupement_signatures_convention_id", "groupement_signatures", ["convention_id"], False),
    ("ix_groupement_signatures_project_id", "groupement_signatures", ["project_id"], False),
    ("ix_groupement_signatures_owner_id", "groupement_signatures", ["owner_id"], False),
]


def _col(name, typ, default, *, table=None, existing_tables=(), for_create=False):
    t = typ() if callable(typ) else typ
    args = []
    if for_create and table:
        ref = _FKS.get(table, {}).get(name)
        # FK seulement si la table visée existe (project_cotraitants vit hors app.models).
        if ref and ref.split(".")[0] in existing_tables:
            args.append(sa.ForeignKey(ref))
    nullable = not (for_create and name in _NOT_NULL.get(table, set()))
    kw = {"nullable": nullable}
    if default is not None:
        kw["server_default"] = default
    return sa.Column(name, t, *args, **kw)


def _add_missing_columns(insp, table, specs):
    existing = {c["name"] for c in insp.get_columns(table)}
    for name, typ, default in specs:
        if name not in existing:
            op.add_column(table, _col(name, typ, default))


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "groupement_conventions" not in tables:
        op.create_table("groupement_conventions",
                        sa.Column("id", sa.Integer(), primary_key=True),
                        *[_col(n, t, d, table="groupement_conventions", existing_tables=tables,
                               for_create=True) for n, t, d in _CONV_COLS])
        tables.add("groupement_conventions")
    else:
        _add_missing_columns(insp, "groupement_conventions", _CONV_COLS)

    if "groupement_signatures" not in tables:
        op.create_table("groupement_signatures",
                        sa.Column("id", sa.Integer(), primary_key=True),
                        *[_col(n, t, d, table="groupement_signatures", existing_tables=tables,
                               for_create=True) for n, t, d in _SIG_COLS],
                        sa.UniqueConstraint("convention_id", "invite_id", name="uq_gsig_convention_invite"),
                        sa.UniqueConstraint("convention_id", "cotraitant_link_id", name="uq_gsig_convention_link"))
        tables.add("groupement_signatures")
    else:
        _add_missing_columns(insp, "groupement_signatures", _SIG_COLS)

    # Index (idempotents). Pas de try/except : sur Postgres un échec avalé laisserait la
    # transaction « aborted » et masquerait la vraie cause.
    insp = sa.inspect(bind)
    for name, table, cols, unique in _INDEXES:
        idx = insp.get_indexes(table)
        if name in {i["name"] for i in idx}:
            continue
        if unique:
            # Une contrainte UNIQUE équivalente (posée par create_all sur une base neuve) suffit.
            have = {tuple(u.get("column_names") or []) for u in insp.get_unique_constraints(table)}
            have |= {tuple(i.get("column_names") or []) for i in idx if i.get("unique")}
            if tuple(cols) in have:
                continue
        op.create_index(name, table, cols, unique=unique)

    # Signataire du membre sur sa part (déjà posé en vague 1 ; filet pour une base en retard).
    if "project_contributions" in tables:
        _add_missing_columns(sa.inspect(bind), "project_contributions", _CONTRIB_COLS)


def downgrade():
    pass
