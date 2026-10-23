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


def _instantane(db) -> None:
    """Toutes les tables sont lues dans UN SEUL instantané de la base (contrôle des bugs, 22/10/2026). Avant, chaque
    table était lue à son tour sur une base vivante : un marché enregistré avec sa pièce entre la lecture des marchés
    et celle des pièces donnait une sauvegarde avec la pièce sans son marché, que PostgreSQL refuse ensuite à la
    restauration (clé étrangère), en entier. PostgreSQL : transaction en lecture seule « repeatable read » (l'application
    continue d'écrire, la sauvegarde ne voit pas ces écritures). SQLite (poste local, démo) : transaction ouverte le
    temps de la lecture (une écriture attend la fin de la sauvegarde). Ne bloque jamais la sauvegarde : si l'instantané
    ne peut pas être pris, elle part comme avant, avec un avertissement dans les logs."""
    from sqlalchemy import text as _t
    try:
        moteur = db.get_bind().dialect.name
        if moteur == "postgresql":
            db.execute(_t("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        elif moteur == "sqlite":
            db.execute(_t("BEGIN"))
    except Exception as e:                            # noqa: BLE001
        db.rollback()
        logger.warning("backup : lecture en un seul instantané impossible (%s), sauvegarde lue table par table",
                       type(e).__name__)


def run_backup(keep: int = 14) -> dict:
    """Dump toutes les tables → JSON gzippé → upload R2 → purge des anciens (garde `keep`)."""
    if not _backend_is_object():
        return {"ok": False, "skipped": "stockage local — sauvegarde inutile (disque éphémère)"}

    from app.core.database import Base, SessionLocal
    from app.services.storage import get_storage
    storage = get_storage()
    db = SessionLocal()
    try:
        _instantane(db)
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
    date), pour que l'insert passe aussi bien sur SQLite que sur Postgres. Un champ JSON
    vide (None dans la sauvegarde) redevient un champ vide de la base (SQL NULL) : inséré
    tel quel, il était rangé comme le texte JSON « null », que « groupement_plan IS NULL »
    ne reconnaît pas (contrôle des bugs, 22/10/2026). Une colonne JSON obligatoire garde
    l'ancienne écriture (le vide n'y est pas permis)."""
    from datetime import datetime, date
    from sqlalchemy import DateTime, Date, JSON, null
    dt_cols, d_cols, j_cols = set(), set(), set()
    for col in table.columns:
        if isinstance(col.type, DateTime):
            dt_cols.add(col.name)
        elif isinstance(col.type, Date):
            d_cols.add(col.name)
        elif isinstance(col.type, JSON) and col.nullable:
            j_cols.add(col.name)
    if not dt_cols and not d_cols and not j_cols:
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
        for c in j_cols:
            if c in r and r[c] is None:
                r[c] = null()
    return rows


def _colonnes_en_cycle(table) -> list:
    """Clés étrangères posées « après coup » (use_alter) : organizations.owner_id → users, alors que users.org_id →
    organizations. Elles pointent vers une table insérée PLUS TARD dans l'ordre des tables : PostgreSQL, qui contrôle
    les clés étrangères, refuse de les insérer d'un coup (et de purger users tant qu'une organisation y pointe)."""
    return sorted({fk.parent.name for fk in table.foreign_keys if fk.use_alter})


def _remettre_les_compteurs(db, tables) -> None:
    """PostgreSQL : chaque compteur de numéros (séquence) repart au-dessus du plus grand numéro restauré. Sans cela,
    le compteur d'une base neuve restait à 1 et la première ligne nouvelle (une inscription, un marché) était refusée
    (« numéro déjà pris »). SQLite numérote toujours au-dessus du plus grand numéro présent : rien à faire."""
    from sqlalchemy import text as _t
    if db.get_bind().dialect.name != "postgresql":
        return
    for table in tables:
        pk = list(table.primary_key.columns)
        if len(pk) != 1 or not pk[0].autoincrement:
            continue
        try:
            if pk[0].type.python_type is not int:
                continue
        except NotImplementedError:
            continue
        col = pk[0].name
        seq = db.execute(_t("SELECT pg_get_serial_sequence(:t, :c)"), {"t": f'"{table.name}"', "c": col}).scalar()
        if not seq:
            continue
        plus_grand = db.execute(_t(f'SELECT max("{col}") FROM "{table.name}"')).scalar()
        if plus_grand is not None:
            db.execute(_t("SELECT setval(:s, :v, true)"), {"s": seq, "v": int(plus_grand)})


def restore_backup(blob: bytes, db) -> dict:
    """Recharge un backup dans une base au schéma DÉJÀ créé (migrations passées).
    Insère table par table dans l'ordre FK-safe. DESTRUCTIF sur les tables concernées
    (purge avant insert). À utiliser depuis un script d'urgence, pas exposé en HTTP.

    Vaut sur PostgreSQL (la production) comme sur SQLite (contrôle des bugs, 22/10/2026) :
    les liens en cycle (organizations.owner_id) sont détachés avant la purge et reposés
    une fois toutes les lignes insérées, les compteurs de numéros repartent au-dessus des
    numéros restaurés, un champ JSON vide reste vide."""
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
    ordre = list(Base.metadata.sorted_tables)
    cycles = {t.name: _colonnes_en_cycle(t) for t in ordre}
    for table in ordre:                                   # liens en cycle détachés avant la purge
        if table.name in tables:
            for col in cycles[table.name]:
                db.execute(_t(f'UPDATE "{table.name}" SET "{col}" = NULL WHERE "{col}" IS NOT NULL'))
    for table in reversed(ordre):                         # purge enfants → parents
        if table.name in tables:
            db.execute(_t(f'DELETE FROM "{table.name}"'))
    a_reposer = []                                        # (table, colonne, clé primaire, [(clé, valeur)])
    for table in ordre:                                   # insert parents → enfants
        rows = tables.get(table.name) or []
        if not rows:
            continue
        rows = _coerce_rows(table, rows)
        pk = [c.name for c in table.primary_key.columns]
        for col in cycles[table.name]:
            valeurs = [({k: r.get(k) for k in pk}, r[col]) for r in rows if r.get(col) is not None]
            for r in rows:
                if col in r:
                    r[col] = None
            if valeurs:
                a_reposer.append((table, col, pk, valeurs))
        db.execute(table.insert(), rows)
        inserted += len(rows)
    for table, col, pk, valeurs in a_reposer:             # liens en cycle reposés, toutes les lignes en place
        ou = " AND ".join(f'"{k}" = :cle_{k}' for k in pk)
        db.execute(_t(f'UPDATE "{table.name}" SET "{col}" = :valeur WHERE {ou}'),
                   [{"valeur": v, **{f"cle_{k}": cle[k] for k in pk}} for cle, v in valeurs])
    _remettre_les_compteurs(db, ordre)
    db.commit()
    return {"ok": True, "tables": len(tables), "rows": inserted}
