"""co-traitance v2 (vague 3) : profils partenaires du réseau Adjugo.

Idempotent (comme les migrations précédentes) : la table, chaque colonne et chaque index ne
sont créés que s'ils manquent. Compatible SQLite (tests, démo) et Postgres (production).
Ajoute :
- partner_profiles (1 par organisation, user_id UNIQUE = data_owner_id) → profil OPT-IN
  (visible = false par défaut), capacités déclarées datées, vérifications SIRENE / BODACC /
  DECP datées (NULL = « non vérifié »), compteur réel de groupements déposés, compteur
  anonyme d'apparitions, identifiant opaque public_id (UNIQUE) ;
- project_invites.source / partner_profile_id si absentes (déjà posées par n8o9p0q1r2s3 ;
  re-vérifiées ici pour une base qui aurait sauté cette révision).

Aucune donnée existante n'est modifiée ; aucun profil n'est créé (pas de profil de
démonstration). Pas de downgrade destructif (comme les précédentes).
NB : sur une base NEUVE, les create_all des révisions antérieures créent déjà cette table à
partir des modèles — cette révision ne fait alors rien (vérification d'existence partout).

Revision ID: p0q1r2s3t4u5
Revises: o9p0q1r2s3t4
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa

revision = "p0q1r2s3t4u5"
down_revision = "o9p0q1r2s3t4"
branch_labels = None
depends_on = None


# (nom, type, server_default) — colonnes hors clé primaire, NULLABLES à l'ajout (ajouter une
# colonne NOT NULL à une table existante échouerait sur une table non vide).
_COLS = [
    ("public_id", lambda: sa.String(32), None),
    ("user_id", sa.Integer, None),
    ("visible", sa.Boolean, sa.text("false")),
    ("name", lambda: sa.String(255), ""),
    ("siren", lambda: sa.String(9), ""),
    ("siret", lambda: sa.String(14), ""),
    ("postal_code", lambda: sa.String(10), ""),
    ("city", lambda: sa.String(120), ""),
    ("departement", lambda: sa.String(3), ""),
    ("metiers", sa.JSON, None),
    ("codes_cpv", sa.JSON, None),
    ("departements", sa.JSON, None),
    ("roles_acceptes", sa.JSON, None),
    ("disponibilite", lambda: sa.String(20), ""),
    ("dispo_jusqua", sa.Date, None),
    ("lot_max_eur", sa.Float, None),
    ("presentation", lambda: sa.String(300), ""),
    ("references_publiques", sa.JSON, None),
    ("declared_at", sa.DateTime, None),
    ("hidden_from_sirens", sa.JSON, None),
    ("verified_sirene", sa.JSON, None),
    ("verified_bodacc", sa.JSON, None),
    ("verified_decp", sa.JSON, None),
    ("verified_at", sa.DateTime, None),
    ("groupements_deposes", sa.Integer, "0"),
    ("last_groupement_at", sa.DateTime, None),
    ("appearances_count", sa.Integer, "0"),
    ("appearances_period", lambda: sa.String(7), ""),
    ("published_at", sa.DateTime, None),
    ("is_demo", sa.Boolean, sa.text("false")),
    ("created_at", sa.DateTime, None),
    ("updated_at", sa.DateTime, None),
]
_INVITE_COLS = [
    ("source", lambda: sa.String(20), "manuel"),
    ("partner_profile_id", sa.Integer, None),
]

# NOT NULL et clé étrangère à la CRÉATION de table seulement.
_NOT_NULL = {"public_id", "user_id", "visible", "is_demo"}
_FKS = {"user_id": "users.id"}

# (nom, table, colonnes, unique)
_INDEXES = [
    ("ix_partner_profiles_id", "partner_profiles", ["id"], False),
    ("ix_partner_profiles_public_id", "partner_profiles", ["public_id"], True),
    ("ix_partner_profiles_user_id", "partner_profiles", ["user_id"], True),
    ("ix_partner_profiles_siren", "partner_profiles", ["siren"], False),
    ("ix_project_invites_partner_profile_id", "project_invites", ["partner_profile_id"], False),
]


def _col(name, typ, default, *, existing_tables=(), for_create=False):
    t = typ() if callable(typ) else typ
    args = []
    if for_create:
        ref = _FKS.get(name)
        if ref and ref.split(".")[0] in existing_tables:
            args.append(sa.ForeignKey(ref))
    kw = {"nullable": not (for_create and name in _NOT_NULL)}
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

    if "partner_profiles" not in tables:
        op.create_table("partner_profiles",
                        sa.Column("id", sa.Integer(), primary_key=True),
                        *[_col(n, t, d, existing_tables=tables, for_create=True) for n, t, d in _COLS])
        tables.add("partner_profiles")
    else:
        _add_missing_columns(insp, "partner_profiles", _COLS)

    if "project_invites" in tables:
        _add_missing_columns(sa.inspect(bind), "project_invites", _INVITE_COLS)

    # Index (idempotents). Pas de try/except : sur Postgres un échec avalé laisserait la
    # transaction « aborted » et masquerait la vraie cause.
    insp = sa.inspect(bind)
    for name, table, cols, unique in _INDEXES:
        if table not in tables:
            continue
        idx = insp.get_indexes(table)
        if name in {i["name"] for i in idx}:
            continue
        have_cols = {tuple(i.get("column_names") or []) for i in idx}
        if unique:
            # Une contrainte UNIQUE équivalente (posée par create_all sur une base neuve) suffit.
            have = {tuple(u.get("column_names") or []) for u in insp.get_unique_constraints(table)}
            have |= {tuple(i.get("column_names") or []) for i in idx if i.get("unique")}
            if tuple(cols) in have:
                continue
        elif tuple(cols) in have_cols:
            continue
        op.create_index(name, table, cols, unique=unique)


def downgrade():
    pass
