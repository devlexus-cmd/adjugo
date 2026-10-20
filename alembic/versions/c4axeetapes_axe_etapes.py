"""réorganisation de l'interface, vague 2a (A1) : un seul axe d'étapes pour un marché (décision 7).

À venir → Repéré → Décidé → En préparation → Déposé → Gagné / Perdu, plus Abandonné. Clés : suivi, nouveau, decide,
en_cours, depose, gagne, perdu, abandonne (app.models.ProjectStatus). Contrat : docs/REORGANISATION_V2A.md, A1.

Ce que fait la révision, sur `projects.status` seulement :
- la clé « envoye » (Déposé) devient « depose ». Postgres : `ALTER TYPE projectstatus RENAME VALUE` (instantané, aucune
  ligne réécrite, transactionnel) ; SQLite : `UPDATE`. Les devis et factures (type `invoicestatus`, où « envoye » reste
  juste) ne sont pas touchés ;
- deux étapes s'ajoutent au type énuméré de Postgres : « suivi » (À venir : une carte de Mes marchés avant la
  publication, décision 11), avant « nouveau », et « decide » (Décidé), après « nouveau ». Aucune ligne ne les porte au
  départ. `ADD VALUE IF NOT EXISTS` dans un bloc hors transaction (exigé avant Postgres 12, sans effet ensuite).

Le journal d'audit n'est PAS touché : ses entrées sont chaînées par empreinte (journal vérifiable de chaque membre) ;
une ancienne clé « envoye » qui y serait lue est comprise comme « depose » (`ProjectStatus._missing_`).

Idempotent : chaque étape regarde d'abord l'état réel (étiquettes du type, valeurs des lignes) ; un rejeu ou une
révision interrompue entre deux étapes se termine sans erreur.

Déploiement : le code de production précédent ne connaît pas « depose ». Pendant la bascule (migration passée,
ancienne instance encore en service, quelques secondes), un marché déposé lu par l'ancienne instance répond en erreur ;
la nouvelle instance prend le relais aussitôt. Retour au code précédent : lancer d'abord
`alembic downgrade b3mesureecrans`.

Downgrade RÉEL : « depose » redevient « envoye » ; un marché « suivi » redevient « nouveau » et un marché « decide »
redevient « en_cours » (le code précédent n'a pas ces étapes : ce sont les siennes les plus proches). Sur Postgres, les
étiquettes « suivi » et « decide » restent dans le type (Postgres ne retire pas une valeur d'un type énuméré) : aucune
ligne ne les porte, le code précédent les ignore, et une remontée ne les ajoute pas deux fois.

Revision ID: c4axeetapes
Revises: b3mesureecrans
Create Date: 2026-10-20
"""
from alembic import op

import sqlalchemy as sa

revision = "c4axeetapes"
down_revision = "b3mesureecrans"
branch_labels = None
depends_on = None

TABLE = "projects"
TYPE = "projectstatus"


def _etiquettes(bind) -> list:
    """Étiquettes du type énuméré Postgres, dans leur ordre (vide : pas de type, ou autre base)."""
    return [r[0] for r in bind.execute(sa.text(
        "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
        "WHERE t.typname = :t ORDER BY e.enumsortorder"), {"t": TYPE})]


def _table_presente(bind) -> bool:
    return TABLE in set(sa.inspect(bind).get_table_names())


def upgrade():
    bind = op.get_bind()
    if not _table_presente(bind):
        return
    if bind.dialect.name != "postgresql":
        op.execute(sa.text(f"UPDATE {TABLE} SET status = 'depose' WHERE status = 'envoye'"))
        return
    etiquettes = _etiquettes(bind)
    if not etiquettes:                     # colonne sans type énuméré : les valeurs suivent
        op.execute(sa.text(f"UPDATE {TABLE} SET status = 'depose' WHERE status = 'envoye'"))
        return
    if "envoye" in etiquettes and "depose" not in etiquettes:
        op.execute(sa.text(f"ALTER TYPE {TYPE} RENAME VALUE 'envoye' TO 'depose'"))
    elif "envoye" in etiquettes:           # les deux étiquettes (ajout manuel) : les lignes passent à « depose »
        op.execute(sa.text(f"UPDATE {TABLE} SET status = 'depose' WHERE status = 'envoye'"))
    manquantes = [(v, pos) for v, pos in (("suivi", "BEFORE 'nouveau'"), ("decide", "AFTER 'nouveau'"))
                  if v not in etiquettes]
    if manquantes:
        with op.get_context().autocommit_block():
            for valeur, position in manquantes:
                op.execute(sa.text(f"ALTER TYPE {TYPE} ADD VALUE IF NOT EXISTS '{valeur}' {position}"))


def downgrade():
    bind = op.get_bind()
    if not _table_presente(bind):
        return
    retour = (("suivi", "nouveau"), ("decide", "en_cours"))
    if bind.dialect.name != "postgresql":
        for de, vers in retour:
            op.execute(sa.text(f"UPDATE {TABLE} SET status = '{vers}' WHERE status = '{de}'"))
        op.execute(sa.text(f"UPDATE {TABLE} SET status = 'envoye' WHERE status = 'depose'"))
        return
    etiquettes = _etiquettes(bind)
    if not etiquettes:
        for de, vers in retour + (("depose", "envoye"),):
            op.execute(sa.text(f"UPDATE {TABLE} SET status = '{vers}' WHERE status = '{de}'"))
        return
    for de, vers in retour:
        if de in etiquettes:
            op.execute(sa.text(f"UPDATE {TABLE} SET status = '{vers}' WHERE status = '{de}'"))
    if "depose" in etiquettes and "envoye" not in etiquettes:
        op.execute(sa.text(f"ALTER TYPE {TYPE} RENAME VALUE 'depose' TO 'envoye'"))
    elif "depose" in etiquettes:
        op.execute(sa.text(f"UPDATE {TABLE} SET status = 'envoye' WHERE status = 'depose'"))
