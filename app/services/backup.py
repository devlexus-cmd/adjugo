"""
Sauvegarde automatique de la base vers le stockage objet (R2).

Choix d'un dump LOGIQUE en JSON gzippé (pas pg_dump) : aucune dépendance binaire ni
problème de version de client Postgres, indépendant du fournisseur. Suffisant et robuste
comme filet de sécurité (les données réelles sont reconstructibles dans un schéma neuf).
Restauration : voir restore_backup() + scripts/restore_from_backup.py.

Déclenché par le planificateur interne (BACKUP_INTERVAL_HOURS) et l'endpoint
/api/admin/run-backup. Ne s'exécute QUE sur stockage objet (R2) — sauvegarder vers le
disque local éphémère de Railway n'aurait aucun sens.
"""
import gzip
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("adjugo")
PREFIX = "backups/"


def _backend_is_object() -> bool:
    from app.core.config import get_settings
    return (get_settings().STORAGE_BACKEND or "").lower() == "s3"


def run_backup(keep: int = 14) -> dict:
    """Dump toutes les tables → JSON gzippé → upload R2 → purge des anciens (garde `keep`)."""
    if not _backend_is_object():
        return {"ok": False, "skipped": "stockage local — sauvegarde inutile (disque éphémère)"}

    from app.core.database import Base, SessionLocal
    from app.services.storage import get_storage
    storage = get_storage()
    db = SessionLocal()
    try:
        dump = {"generated_at": datetime.now(timezone.utc).isoformat(),
                "schema_version": "logical-v1", "tables": {}}
        n_rows = 0
        for table in Base.metadata.sorted_tables:   # ordre FK-safe (utile à la restauration)
            rows = [dict(r._mapping) for r in db.execute(table.select())]
            n_rows += len(rows)
            dump["tables"][table.name] = json.loads(json.dumps(rows, default=str, ensure_ascii=False))
        payload = gzip.compress(json.dumps(dump, ensure_ascii=False).encode("utf-8"))
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        key = f"{PREFIX}adjugo-{ts}.json.gz"
        storage.save(key, payload, "application/gzip")
        pruned = _prune(storage, keep)
        logger.info("backup OK : %s (%d tables, %d lignes, %d o, %d purgés)",
                    key, len(dump["tables"]), n_rows, len(payload), pruned)
        return {"ok": True, "key": key, "size": len(payload),
                "tables": len(dump["tables"]), "rows": n_rows, "pruned": pruned}
    except Exception as e:
        logger.warning("backup en échec : %s", e)
        return {"ok": False, "error": str(e)[:300]}
    finally:
        db.close()


def _prune(storage, keep: int) -> int:
    """Garde les `keep` sauvegardes les plus récentes (tri lexical = chronologique)."""
    try:
        keys = sorted([k for k in storage.list_keys(PREFIX) if k.endswith(".json.gz")])
        old = keys[:-keep] if keep > 0 else []
        for k in old:
            storage.delete(k)
        return len(old)
    except Exception:
        return 0


def _coerce_rows(table, rows: list) -> list:
    """Reconvertit les valeurs texte du JSON vers les types attendus (dates → datetime/
    date), pour que l'insert passe aussi bien sur SQLite que sur Postgres."""
    from datetime import datetime, date
    from sqlalchemy import DateTime, Date
    dt_cols, d_cols = set(), set()
    for col in table.columns:
        if isinstance(col.type, DateTime):
            dt_cols.add(col.name)
        elif isinstance(col.type, Date):
            d_cols.add(col.name)
    if not dt_cols and not d_cols:
        return rows
    for r in rows:
        for c in dt_cols:
            v = r.get(c)
            if isinstance(v, str) and v:
                try: r[c] = datetime.fromisoformat(v)
                except ValueError: pass
        for c in d_cols:
            v = r.get(c)
            if isinstance(v, str) and v:
                try: r[c] = date.fromisoformat(v[:10])
                except ValueError: pass
    return rows


def restore_backup(blob: bytes, db) -> dict:
    """Recharge un backup dans une base au schéma DÉJÀ créé (migrations passées).
    Insère table par table dans l'ordre FK-safe. DESTRUCTIF sur les tables concernées
    (purge avant insert). À utiliser depuis un script d'urgence, pas exposé en HTTP."""
    from app.core.database import Base
    from sqlalchemy import text as _t
    data = json.loads(gzip.decompress(blob).decode("utf-8"))
    tables = data.get("tables", {})
    inserted = 0
    for table in reversed(Base.metadata.sorted_tables):   # purge enfants → parents
        if table.name in tables:
            db.execute(_t(f'DELETE FROM "{table.name}"'))
    for table in Base.metadata.sorted_tables:             # insert parents → enfants
        rows = tables.get(table.name) or []
        if rows:
            db.execute(table.insert(), _coerce_rows(table, rows))
            inserted += len(rows)
    db.commit()
    return {"ok": True, "tables": len(tables), "rows": inserted}
