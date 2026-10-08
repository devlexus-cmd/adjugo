"""co-traitance v2 (vague 4) : suppression DÉFINITIVE de project_contributions.chiffrage_note.

L'« approche prix » en clair (visible du mandataire = violation de la doctrine de visibilité)
a été vidée en vague 1 (n8o9p0q1r2s3 : contenu déplacé en tête de note_au_mandataire, préfixé
« (ancienne approche prix) »). Depuis, plus aucun code ne la lit ni ne l'écrit (le PUT de la
part l'ignore). Cette révision :
  1. FILET : si une ligne contient encore un texte (écrit entre la vague 1 et maintenant par
     un chemin oublié), il est déplacé comme en vague 1 — aucune perte, jamais de troncature ;
  2. supprime la colonne. SQLite : batch_alter_table (recopie de la table, contraintes et index
     conservés) ; Postgres : ALTER TABLE … DROP COLUMN.

Idempotent : ne fait rien si la table ou la colonne n'existe pas (base neuve : la colonne n'est
plus dans le modèle). Pas de downgrade destructif inverse : recréer une colonne vide n'aurait
aucun sens (comme les révisions précédentes, downgrade ne fait rien).
L'intégration rechaînera down_revision après la vague 3 (réseau), développée en parallèle.

Revision ID: q1r2s3t4u5v6
Revises: o9p0q1r2s3t4
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa

revision = "q1r2s3t4u5v6"
down_revision = "o9p0q1r2s3t4"
branch_labels = None
depends_on = None

TABLE = "project_contributions"
COLUMN = "chiffrage_note"


def _has_column(bind) -> bool:
    insp = sa.inspect(bind)
    if TABLE not in set(insp.get_table_names()):
        return False
    return COLUMN in {c["name"] for c in insp.get_columns(TABLE)}


def upgrade():
    bind = op.get_bind()
    if not _has_column(bind):
        return
    # 1) Filet : aucun texte ne disparaît.
    rows = bind.execute(sa.text(
        f"SELECT id, {COLUMN}, note_au_mandataire FROM {TABLE} "
        f"WHERE {COLUMN} IS NOT NULL AND {COLUMN} <> ''")).fetchall()
    for rid, note, mand in rows:
        merged = "(ancienne approche prix) " + (note or "").strip()
        if (mand or "").strip():
            merged += "\n\n" + mand.strip()
        bind.execute(sa.text(
            f"UPDATE {TABLE} SET note_au_mandataire = :m, {COLUMN} = '' WHERE id = :i"),
            {"m": merged, "i": rid})
    # 2) Suppression de la colonne.
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_column(COLUMN)
    else:
        op.drop_column(TABLE, COLUMN)


def downgrade():
    pass
