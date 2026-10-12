"""rédaction, vague 2 : l'atelier du dossier de présentation (sections, versions, validation).

Idempotent (comme les révisions précédentes) : chaque table / colonne / index n'est créé que s'il
manque. SQLite (tests, démo) et Postgres (production). Ajoute :
- dossiers_presentation      → un par marché et par entreprise (UNIQUE(project_id, owner_id)) :
  source du plan, texte du dossier de l'acheteur lu pour la rédaction, quota (analyse débitée,
  régénérations), dérogation à l'export, compteur, dernier export ;
- dossier_sections           → sections ordonnées (numéro et intitulé du cadre ou critère de la
  grille, poids tel que retrouvé, lot, auteur, statut, limite, validation : qui / quand / empreinte) ;
- dossier_section_versions   → versions EN AJOUT SEUL (texte, origine ia | utilisateur | raccourci,
  sources PRIVÉES, faits à relire, empreinte sha256, auteur, date) ;
- projects.dce_importe_le / dce_fichier_impose → mesure de la décision 11 (combien de dossiers
  importés imposent leur fichier de réponse), remplies pour les analyses existantes.

Downgrade RÉEL (aucune autre révision ne dépend de ces tables) : supprime les trois tables et les
deux colonnes.

Revision ID: s3t4redactionv2
Revises: r2s3reseauvalid
Create Date: 2026-10-12
"""
import json

from alembic import op
import sqlalchemy as sa

revision = "s3t4redactionv2"
down_revision = "r2s3reseauvalid"
branch_labels = None
depends_on = None

DOSSIERS = "dossiers_presentation"
SECTIONS = "dossier_sections"
VERSIONS = "dossier_section_versions"


def _s(n):
    return lambda: sa.String(n)


_DOSSIER_COLS = [
    ("project_id", sa.Integer, None),
    ("owner_id", sa.Integer, None),
    ("created_by_user_id", sa.Integer, None),
    ("plan_source", _s(10), "libre"),
    ("plan_meta", sa.JSON, None),
    ("dce_lu", sa.JSON, None),
    ("analyse_debitee", sa.Boolean, sa.text("false")),
    ("regenerations", sa.Integer, "0"),
    ("regenerations_payantes", sa.Integer, "0"),
    ("derogation", sa.JSON, None),
    ("compteur", sa.JSON, None),
    ("dernier_export", sa.JSON, None),
    ("version", sa.Integer, "0"),
    ("created_at", sa.DateTime, None),
    ("updated_at", sa.DateTime, None),
]
_SECTION_COLS = [
    ("dossier_id", sa.Integer, None),
    ("project_id", sa.Integer, None),
    ("owner_id", sa.Integer, None),
    ("ordre", sa.Integer, "0"),
    ("numero", _s(20), ""),
    ("intitule", _s(300), ""),
    ("niveau", sa.Integer, "1"),
    ("parents", sa.JSON, None),
    ("question", sa.Text, None),
    ("source_plan", _s(12), "libre"),
    ("critere", _s(300), ""),
    ("critere_id", _s(20), ""),
    ("poids", _s(40), ""),
    ("partie_de_critere", sa.Boolean, sa.text("false")),
    ("lot", _s(120), ""),
    ("limite", sa.JSON, None),
    ("author_kind", _s(12), "organisation"),
    ("author_invite_id", sa.Integer, None),
    ("statut", _s(12), "a_ecrire"),
    ("current_version_id", sa.Integer, None),
    ("validated_version_id", sa.Integer, None),
    ("validated_hash", _s(64), ""),
    ("validated_at", sa.DateTime, None),
    ("validated_by", sa.Integer, None),
    ("job_id", sa.Integer, None),
    ("retiree_at", sa.DateTime, None),
    ("lock_version", sa.Integer, "0"),
    ("created_at", sa.DateTime, None),
    ("updated_at", sa.DateTime, None),
]
_VERSION_COLS = [
    ("section_id", sa.Integer, None),
    ("dossier_id", sa.Integer, None),
    ("project_id", sa.Integer, None),
    ("owner_id", sa.Integer, None),
    ("numero", sa.Integer, "1"),
    ("texte", sa.Text, None),
    ("origine", _s(12), "utilisateur"),
    ("ia", sa.Boolean, sa.text("false")),
    ("sources", sa.JSON, None),
    ("faits", sa.JSON, None),
    ("empreinte", _s(64), ""),
    ("coupe", sa.Boolean, sa.text("false")),
    ("base_version_id", sa.Integer, None),
    ("restaure_de", sa.Integer, None),
    ("author_kind", _s(12), "organisation"),
    ("author_invite_id", sa.Integer, None),
    ("auteur_user_id", sa.Integer, None),
    ("job_id", sa.Integer, None),
    ("created_at", sa.DateTime, None),
]
_PROJECT_COLS = [
    ("dce_importe_le", sa.DateTime, None),
    ("dce_fichier_impose", sa.Boolean, None),
]

_NOT_NULL = {
    DOSSIERS: {"project_id", "owner_id", "version"},
    SECTIONS: {"dossier_id", "project_id", "owner_id", "lock_version"},
    VERSIONS: {"section_id", "dossier_id", "project_id", "owner_id"},
}
_FKS = {
    DOSSIERS: {"project_id": "projects.id", "owner_id": "users.id"},
    SECTIONS: {"dossier_id": f"{DOSSIERS}.id"},
    VERSIONS: {"section_id": f"{SECTIONS}.id"},
}
# (nom, table, colonnes)
_INDEXES = [
    (f"ix_{DOSSIERS}_id", DOSSIERS, ["id"]),
    (f"ix_{DOSSIERS}_project_id", DOSSIERS, ["project_id"]),
    (f"ix_{DOSSIERS}_owner_id", DOSSIERS, ["owner_id"]),
    (f"ix_{SECTIONS}_id", SECTIONS, ["id"]),
    (f"ix_{SECTIONS}_dossier_id", SECTIONS, ["dossier_id"]),
    (f"ix_{SECTIONS}_project_id", SECTIONS, ["project_id"]),
    (f"ix_{SECTIONS}_owner_id", SECTIONS, ["owner_id"]),
    (f"ix_{SECTIONS}_author_invite_id", SECTIONS, ["author_invite_id"]),
    (f"ix_{VERSIONS}_id", VERSIONS, ["id"]),
    (f"ix_{VERSIONS}_section_id", VERSIONS, ["section_id"]),
    (f"ix_{VERSIONS}_dossier_id", VERSIONS, ["dossier_id"]),
    (f"ix_{VERSIONS}_project_id", VERSIONS, ["project_id"]),
    (f"ix_{VERSIONS}_owner_id", VERSIONS, ["owner_id"]),
]


def _col(table, name, typ, default, *, for_create=False):
    t = typ() if callable(typ) else typ
    args = []
    if for_create:
        ref = _FKS.get(table, {}).get(name)
        if ref:
            args.append(sa.ForeignKey(ref))
    nullable = not (for_create and name in _NOT_NULL.get(table, set()))
    kw = {"nullable": nullable}
    if default is not None:
        kw["server_default"] = default
    return sa.Column(name, t, *args, **kw)


def _ensure_table(insp, tables, name, specs, *extra):
    if name not in tables:
        op.create_table(name, sa.Column("id", sa.Integer(), primary_key=True),
                        *[_col(name, n, t, d, for_create=True) for n, t, d in specs], *extra)
        tables.add(name)
        return
    have = {c["name"] for c in insp.get_columns(name)}
    for n, t, d in specs:
        if n not in have:
            op.add_column(name, _col(name, n, t, d))


def _backfill_projects(bind) -> None:
    """Analyses déjà enregistrées : un dossier importé (dce_available) compte dans la mesure ; le
    fichier est « imposé » si la grille l'a repéré (contraintes.fichier_impose). Une analyse
    d'avant la grille n'est pas comptée (on ne sait pas)."""
    rows = bind.execute(sa.text(
        "SELECT id, ai_analysis, created_at FROM projects "
        "WHERE dce_importe_le IS NULL AND ai_analysis IS NOT NULL")).fetchall()
    for pid, raw, created in rows:
        try:
            a = raw if isinstance(raw, dict) else json.loads(raw or "null")
        except (TypeError, ValueError):
            continue
        if not isinstance(a, dict) or not a.get("dce_available"):
            continue
        det = a.get("details") if isinstance(a.get("details"), dict) else {}
        g = det.get("grille_notation") if isinstance(det.get("grille_notation"), dict) else None
        if g is None:
            continue
        imp = bool((g.get("contraintes") or {}).get("fichier_impose"))
        bind.execute(sa.text("UPDATE projects SET dce_importe_le = :d, dce_fichier_impose = :f WHERE id = :i"),
                     {"d": created, "f": imp, "i": pid})


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    _ensure_table(insp, tables, DOSSIERS, _DOSSIER_COLS,
                  sa.UniqueConstraint("project_id", "owner_id", name="uq_dossier_presentation_projet_owner"))
    _ensure_table(insp, tables, SECTIONS, _SECTION_COLS)
    _ensure_table(insp, tables, VERSIONS, _VERSION_COLS)

    # Index (idempotents). Pas de try/except : sur Postgres un échec avalé laisserait la
    # transaction « aborted » et masquerait la vraie cause.
    insp = sa.inspect(bind)
    for name, table, cols in _INDEXES:
        if name in {i["name"] for i in insp.get_indexes(table)}:
            continue
        op.create_index(name, table, cols, unique=False)

    if "projects" in tables:
        have = {c["name"] for c in sa.inspect(bind).get_columns("projects")}
        for n, t, d in _PROJECT_COLS:
            if n not in have:
                op.add_column("projects", _col("projects", n, t, d))
        _backfill_projects(bind)


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    for t in (VERSIONS, SECTIONS, DOSSIERS):
        if t in tables:
            op.drop_table(t)
    if "projects" in tables:
        have = {c["name"] for c in insp.get_columns("projects")}
        drop = [n for n, _t, _d in _PROJECT_COLS if n in have]
        if drop:
            with op.batch_alter_table("projects") as b:
                for n in drop:
                    b.drop_column(n)
