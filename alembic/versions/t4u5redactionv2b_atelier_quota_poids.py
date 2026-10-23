"""rédaction, vague 2 (relecture) : quota par dossier et provenance du poids d'une partie.

Idempotent (comme les révisions précédentes) : chaque colonne n'est ajoutée que si elle manque.
SQLite (tests, démo) et Postgres (production). Ajoute :
- dossiers_presentation.premieres_incluses → premières rédactions comprises dans l'analyse du
  dossier (au plus une par partie active) : le plafond des refontes gratuites (décision 6a) ne se
  contourne plus en reconstruisant le plan ou en ajoutant des parties ;
- dossiers_presentation.job_analyse_id      → la tâche qui porte l'analyse du dossier : tant
  qu'elle tourne, aucune autre action de l'IA ne démarre (pas de double débit, pas de rédaction
  gratuite si la première tombe en panne) ;
- dossier_sections.poids_source             → d'où vient le poids d'une partie (« reglement » ou
  « utilisateur » : lu et saisi par vous dans « Comment vous serez noté »).
Les dossiers existants : premieres_incluses = nombre de parties qui ont déjà une version de l'IA
(rien n'est offert en plus) ; poids_source = celle de la ligne de la grille (« Comment vous serez
noté ») rattachée à la partie ; si la ligne n'existe plus, rien (« poids : 40 % », sans dire d'où
il vient).

Downgrade RÉEL : retire les trois colonnes.

Revision ID: t4u5redactionv2b
Revises: s3t4redactionv2
Create Date: 2026-10-12
"""
from alembic import op
import json

import sqlalchemy as sa

revision = "t4u5redactionv2b"
down_revision = "s3t4redactionv2"
branch_labels = None
depends_on = None

DOSSIERS = "dossiers_presentation"
SECTIONS = "dossier_sections"
VERSIONS = "dossier_section_versions"

_COLS = [
    (DOSSIERS, "premieres_incluses", sa.Integer(), "0"),
    (DOSSIERS, "job_analyse_id", sa.Integer(), None),
    (SECTIONS, "poids_source", sa.String(20), ""),
]


def _have(insp, table):
    return {c["name"] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    added = set()
    for table, name, typ, default in _COLS:
        if table not in tables or name in _have(insp, table):
            continue
        kw = {"nullable": True}
        if default is not None:
            kw["server_default"] = default
        op.add_column(table, sa.Column(name, typ, **kw))
        added.add((table, name))
    if (DOSSIERS, "premieres_incluses") in added and VERSIONS in tables:
        bind.execute(sa.text(
            f"UPDATE {DOSSIERS} SET premieres_incluses = (SELECT COUNT(DISTINCT v.section_id) FROM {VERSIONS} v "
            f"WHERE v.dossier_id = {DOSSIERS}.id AND v.origine IN ('ia', 'raccourci'))"))
    if (SECTIONS, "poids_source") in added and "projects" in tables:
        _backfill_poids_source(bind)


def _backfill_poids_source(bind) -> None:
    rows = bind.execute(sa.text(
        f"SELECT s.id, s.critere_id, p.ai_analysis FROM {SECTIONS} s JOIN projects p ON p.id = s.project_id "
        f"WHERE s.poids IS NOT NULL AND s.poids <> '' AND s.critere_id IS NOT NULL AND s.critere_id <> ''")).fetchall()
    for sid, cid, raw in rows:
        try:
            a = raw if isinstance(raw, dict) else json.loads(raw or "null")
        except (TypeError, ValueError):
            continue
        det = a.get("details") if isinstance(a, dict) and isinstance(a.get("details"), dict) else {}
        g = det.get("grille_notation") if isinstance(det.get("grille_notation"), dict) else {}
        ln = next((x for x in (g.get("criteres") or []) if isinstance(x, dict) and str(x.get("id")) == str(cid)), None)
        src = str((ln or {}).get("poids_source") or "")
        if src in ("reglement", "utilisateur"):
            bind.execute(sa.text(f"UPDATE {SECTIONS} SET poids_source = :s WHERE id = :i"), {"s": src, "i": sid})


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    for table in (DOSSIERS, SECTIONS):
        if table not in tables:
            continue
        have = _have(insp, table)
        drop = [n for t, n, _typ, _d in _COLS if t == table and n in have]
        if drop:
            with op.batch_alter_table(table) as b:
                for n in drop:
                    b.drop_column(n)
