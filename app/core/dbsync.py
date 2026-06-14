"""
Auto-migration légère pour la démo SQLite.

`create_all` crée les tables manquantes mais n'ALTERe jamais une table existante :
quand on ajoute une colonne à un modèle, elle n'apparaît pas sur la base déjà créée.
Cette passe idempotente lit le schéma réel (PRAGMA) et ajoute via
`ALTER TABLE … ADD COLUMN` toute colonne déclarée dans les modèles mais absente.

Uniquement pour SQLite (dev/démo). En prod (Postgres) on passe par Alembic.
"""
import logging

from sqlalchemy import inspect, text

logger = logging.getLogger("adjugo")


def _col_ddl(col, dialect) -> str:
    """Fragment DDL « <type> [DEFAULT <val>] » pour un ADD COLUMN SQLite."""
    try:
        coltype = col.type.compile(dialect=dialect)
    except Exception:
        coltype = "VARCHAR"
    ddl = coltype
    default = getattr(col, "default", None)
    if default is not None and not getattr(default, "is_callable", False):
        arg = getattr(default, "arg", None)
        if not callable(arg) and arg is not None and not isinstance(arg, (list, dict)):
            if isinstance(arg, bool):
                ddl += f" DEFAULT {1 if arg else 0}"
            elif isinstance(arg, (int, float)):
                ddl += f" DEFAULT {arg}"
            elif isinstance(arg, str):
                safe = arg.replace("'", "''")
                ddl += f" DEFAULT '{safe}'"
    return ddl


def ensure_sqlite_columns(engine, base) -> None:
    """Ajoute à chaque table existante les colonnes de modèle manquantes."""
    if not engine.url.get_backend_name().startswith("sqlite"):
        return
    insp = inspect(engine)
    try:
        existing_tables = set(insp.get_table_names())
    except Exception as e:
        logger.warning("dbsync : inspection impossible (%s)", e)
        return

    added = 0
    with engine.begin() as conn:
        # L'ordre n'importe pas pour des ADD COLUMN → on évite sorted_tables
        # (qui avertit sur les cycles de FK mutuelles).
        for table in base.metadata.tables.values():
            if table.name not in existing_tables:
                continue  # create_all s'en charge
            try:
                have = {c["name"] for c in insp.get_columns(table.name)}
            except Exception:
                continue
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = _col_ddl(col, engine.dialect)
                try:
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}'))
                    added += 1
                    logger.info("dbsync : + %s.%s (%s)", table.name, col.name, ddl)
                except Exception as e:
                    logger.warning("dbsync : échec ADD COLUMN %s.%s : %s", table.name, col.name, e)
    if added:
        logger.info("dbsync : %d colonne(s) ajoutée(s) à la base SQLite", added)
