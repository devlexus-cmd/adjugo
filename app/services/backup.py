"""
Sauvegarde automatique de la base vers le stockage objet (R2).

Choix d'un dump LOGIQUE en JSON gzippé (pas pg_dump) : aucune dépendance binaire ni
problème de version de client Postgres, indépendant du fournisseur. Suffisant et robuste
comme filet de sécurité (les données réelles sont reconstructibles dans un schéma neuf).

Chiffrement applicatif (audit cyber oct. 2026, rang 13) : si BACKUP_PUBLIC_KEY est posée,
le dump est chiffré AVANT l'envoi (hybride X25519 + AES-256-GCM, format décrit dans
app/services/backup_crypto.py) → fichier « .json.gz.enc ». Le serveur ne détient que la
clé publique : il ne peut pas relire ses propres sauvegardes. Sans la variable, la
sauvegarde part comme avant (« .json.gz », chiffrée au repos par l'hébergeur seulement)
avec un avertissement dans les logs — la sauvegarde n'est jamais bloquée.

Restauration (procédure complète : docs/GO_LIVE.md) : déchiffrer hors ligne avec
scripts/backup_decrypt.py (clé privée + mot de passe), puis restore_backup() sur le
.json.gz obtenu, dans une base au schéma déjà migré.

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
SUFFIXES = (".json.gz", ".json.gz.enc")      # en clair (historique) / chiffrée par Adjugo


def is_backup_key(key: str) -> bool:
    return (key or "").endswith(SUFFIXES)


def _encryption_key():
    """(clé publique, None) si BACKUP_PUBLIC_KEY est posée et valide ; (None, raison) sinon."""
    from app.core.config import get_settings
    raw = (getattr(get_settings(), "BACKUP_PUBLIC_KEY", "") or "").strip()
    if not raw:
        return None, "BACKUP_PUBLIC_KEY absente"
    try:
        from app.services.backup_crypto import load_public_key
        return load_public_key(raw), None
    except Exception as e:
        return None, f"BACKUP_PUBLIC_KEY invalide ({e})"


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
        n_tables = len(dump["tables"])
        payload = gzip.compress(json.dumps(dump, ensure_ascii=False).encode("utf-8"))
        del dump
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        # Chiffrement applicatif AVANT l'envoi. Jamais bloquant : clé absente, invalide ou
        # échec inattendu → sauvegarde en clair (comme avant) + avertissement explicite.
        pub, why = _encryption_key()
        extra = {"encrypted": False}
        if pub is not None:
            try:
                from app.services.backup_crypto import encrypt_bytes, fingerprint_hex
                payload = encrypt_bytes(payload, pub)
                extra = {"encrypted": True, "key_fingerprint": fingerprint_hex(pub)}
            except Exception as e:                       # ne doit pas arriver : on garde la sauvegarde
                why = f"chiffrement en échec ({type(e).__name__})"
                logger.error("backup : %s — sauvegarde envoyée NON chiffrée", why)
        if not extra["encrypted"]:
            extra["warning"] = (f"sauvegarde non chiffrée par l'application : {why} "
                                "(voir docs/GO_LIVE.md, chiffrement des sauvegardes)")
            logger.warning("backup : %s", extra["warning"])
        key = f"{PREFIX}adjugo-{ts}.json.gz" + (".enc" if extra["encrypted"] else "")
        storage.save(key, payload, "application/octet-stream" if extra["encrypted"] else "application/gzip")
        pruned = _prune(storage, keep)
        logger.info("backup OK : %s (%d tables, %d lignes, %d o, %d purgés, chiffrée=%s)",
                    key, n_tables, n_rows, len(payload), pruned, extra["encrypted"])
        return {"ok": True, "key": key, "size": len(payload),
                "tables": n_tables, "rows": n_rows, "pruned": pruned, **extra}
    except Exception as e:
        logger.warning("backup en échec : %s", e)
        return {"ok": False, "error": str(e)[:300]}
    finally:
        db.close()


def _prune(storage, keep: int) -> int:
    """Garde les `keep` sauvegardes les plus récentes (tri lexical = chronologique)."""
    try:
        keys = sorted([k for k in storage.list_keys(PREFIX) if is_backup_key(k)])
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
    from app.services.backup_crypto import is_encrypted
    if is_encrypted(blob):
        # La clé privée ne vit jamais sur le serveur : déchiffrement hors ligne d'abord.
        raise ValueError("sauvegarde chiffrée : déchiffrez-la d'abord avec "
                         "scripts/backup_decrypt.py (clé privée + mot de passe)")
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
