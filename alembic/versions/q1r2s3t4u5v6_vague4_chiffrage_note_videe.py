"""co-traitance v2 (vague 4) : chiffrage_note vidée (filet), suppression REPORTÉE ; acceptation durable
d'une invitation du réseau.

Déploiement sans casse (« expand/contract ») : pendant le démarrage du nouveau conteneur, l'ancien
(code de production) sert encore le trafic, et son modèle mappe toujours chiffrage_note ; en cas
d'échec du démarrage, Railway garde l'ancienne version. La colonne doit donc RESTER en base tant
qu'une version déployable la mappe. Cette révision :
  1. FILET (chiffrage_note) : tout texte non vide encore présent (écrit entre la vague 1 et
     maintenant par un chemin oublié) est recopié en tête de note_au_mandataire, préfixé
     « (ancienne approche prix) » comme en vague 1, puis la colonne est vidée. Aucune perte,
     jamais de troncature (colonnes Text). La colonne N'EST PAS supprimée : le nouveau modèle ne
     la mappe plus (aucune lecture, aucune écriture ; NULL pour les nouvelles lignes, colonne
     nullable) et l'ancien code continue de la lire et de l'écrire sans erreur. Sa suppression
     (DROP COLUMN) viendra dans une révision d'une livraison ULTÉRIEURE, quand plus aucune version
     déployable ne la mappe (voir docs/COTRAITANCE_V2_ARCHITECTURE.md, « Suppressions différées »).
  2. project_invites.network_accepted_at (DateTime, NULL) : date de la PREMIÈRE réponse positive
     à une invitation du réseau (acceptée depuis le compte, adresse prouvée par code, ou part
     soumise). Jamais remise à zéro (effacement du compte qui l'avait acceptée, part repassée en
     brouillon) : l'aperçu minimal et la projection du journal du membre ne reviennent jamais en
     arrière, sinon un export conservé ne serait plus « prolongé » par le suivant (fausse alerte).
     Rempli pour les invitations réseau déjà acceptées. Colonne ajoutée : l'ancien code l'ignore.

Idempotent : chaque étape vérifie la table et la colonne (base neuve : chiffrage_note n'existe pas,
le modèle ne la mappe plus). downgrade ne fait rien, à dessein : chiffrage_note n'a jamais été
supprimée ici (l'ancien code la retrouve telle quelle) et network_accepted_at, absente de son
modèle, est ignorée par l'ancien code. Retour arrière vers l'image précédente (vérifié sur
Postgres avec le code de production) : `alembic downgrade o9p0q1r2s3t4` depuis l'image actuelle,
puis redéploiement de l'image précédente — sans ce downgrade, son entrypoint s'arrête sur une
révision inconnue (voir DEPLOIEMENT.md).

Revision ID: q1r2s3t4u5v6
Revises: p0q1r2s3t4u5
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa

revision = "q1r2s3t4u5v6"
down_revision = "p0q1r2s3t4u5"
branch_labels = None
depends_on = None

TABLE = "project_contributions"
COLUMN = "chiffrage_note"
INVITES = "project_invites"
ACCEPTED = "network_accepted_at"


def _columns(bind, table) -> set:
    insp = sa.inspect(bind)
    if table not in set(insp.get_table_names()):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    # 1) Filet : aucun texte ne disparaît ; la colonne est vidée, PAS supprimée.
    if COLUMN in _columns(bind, TABLE):
        rows = bind.execute(sa.text(
            f"SELECT id, {COLUMN}, note_au_mandataire FROM {TABLE} "
            f"WHERE {COLUMN} IS NOT NULL AND {COLUMN} <> ''")).fetchall()
        for rid, note, mand in rows:
            if not (note or "").strip():          # que des blancs : rien à recopier
                bind.execute(sa.text(f"UPDATE {TABLE} SET {COLUMN} = '' WHERE id = :i"), {"i": rid})
                continue
            merged = "(ancienne approche prix) " + (note or "").strip()
            if (mand or "").strip():
                merged += "\n\n" + mand.strip()
            bind.execute(sa.text(
                f"UPDATE {TABLE} SET note_au_mandataire = :m, {COLUMN} = '' WHERE id = :i"),
                {"m": merged, "i": rid})

    # 2) Acceptation durable d'une invitation du réseau.
    cols = _columns(bind, INVITES)
    if cols and ACCEPTED not in cols:
        op.add_column(INVITES, sa.Column(ACCEPTED, sa.DateTime(), nullable=True))
        cols.add(ACCEPTED)
    if ACCEPTED in cols and "source" in cols:
        submitted = ""
        if "invite_id" in _columns(bind, TABLE):
            submitted = (f" OR EXISTS (SELECT 1 FROM {TABLE} c WHERE c.invite_id = {INVITES}.id "
                         "AND c.status = 'submitted')")
        bind.execute(sa.text(
            f"UPDATE {INVITES} SET {ACCEPTED} = COALESCE(verified_at, CURRENT_TIMESTAMP) "
            f"WHERE {ACCEPTED} IS NULL AND source = 'reseau_adjugo' "
            f"AND (accepted_by_user_id IS NOT NULL OR verified_at IS NOT NULL{submitted})"))


def downgrade():
    pass
