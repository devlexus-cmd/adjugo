"""
Adjugo — Journal d'accès (RGPD).

Trace immuable de qui consulte/télécharge quoi, et quand. Surtout : les accès des
co-traitants externes invités via un lien bridé. C'est la preuve de traçabilité
exigible (RGPD / confidentialité des dossiers de candidature).

Principe : un échec d'écriture du journal NE DOIT JAMAIS faire échouer l'action
métier sous-jacente — on isole donc l'écriture et on avale toute exception.
"""
import hashlib
import logging
from typing import Optional

logger = logging.getLogger("adjugo")


def _ts(dt) -> str:
    """Timestamp canonique : UTC naïf à la microseconde. Indispensable car selon le
    backend created_at est tz-aware (Python/utcnow) ou naïf (relu de SQLite) — sans
    normalisation le hash diffère entre écriture et relecture."""
    if dt is None:
        return ""
    try:
        if dt.tzinfo is not None:
            from datetime import timezone
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.isoformat(timespec="microseconds")
    except Exception:
        return str(dt)


def _entry_payload(a) -> str:
    """Représentation canonique d'une entrée pour le hash (ordre stable)."""
    return "|".join(str(x) for x in (
        a.id, _ts(a.created_at), a.owner_id, a.project_id, a.actor, a.actor_kind,
        a.action, a.target_type, a.target_id, a.detail, a.ip,
    ))


def _hash(prev_hash: str, a) -> str:
    return hashlib.sha256(((prev_hash or "") + _entry_payload(a)).encode("utf-8")).hexdigest()


def client_ip(request) -> str:
    """IP réelle du client derrière le proxy Railway, NON spoofable (dernier hop XFF).
    Voir app.core.ratelimit.real_client_ip — source unique de vérité."""
    try:
        from app.core.ratelimit import real_client_ip
        return (real_client_ip(request) or "")[:45]
    except Exception:
        try:
            return (request.client.host if request.client else "")[:45]
        except Exception:
            return ""


def record(db, *, action: str, owner_id: Optional[int] = None,
           project_id: Optional[int] = None, actor: str = "", actor_kind: str = "",
           target_type: str = "", target_id: Optional[int] = None,
           detail: str = "", ip: str = "", meta: Optional[dict] = None) -> None:
    """Écrit une entrée d'audit, chaînée par hash (tamper-evidence). Best-effort."""
    try:
        from app.models import AuditLog, utcnow
        entry = AuditLog(
            created_at=utcnow(),   # figé explicitement : doit être identique au hash
            action=action[:60], owner_id=owner_id, project_id=project_id,
            actor=(actor or "")[:160], actor_kind=(actor_kind or "")[:20],
            target_type=(target_type or "")[:40], target_id=target_id,
            detail=(detail or "")[:255], ip=(ip or "")[:45], meta=meta,
        )
        db.add(entry)
        db.flush()   # obtient l'id avant de calculer le hash
        # Maillon précédent du même tenant : la chaîne lie chaque entrée à la suivante.
        prev = db.query(AuditLog).filter(
            AuditLog.owner_id == owner_id, AuditLog.id < entry.id,
        ).order_by(AuditLog.id.desc()).first()
        entry.prev_hash = (prev.entry_hash if prev else "")
        entry.entry_hash = _hash(entry.prev_hash, entry)
        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("audit: écriture du journal échouée (%s) : %s", action, e)


def verify_chain(db, owner_id: int) -> dict:
    """Revérifie la chaîne de hash d'un tenant : recalcule chaque maillon et détecte
    toute entrée modifiée, supprimée ou réordonnée. Renvoie l'état d'intégrité."""
    from app.models import AuditLog
    rows = db.query(AuditLog).filter(AuditLog.owner_id == owner_id).order_by(AuditLog.id.asc()).all()
    prev = ""
    broken_at = None
    for a in rows:
        # Entrées historiques (avant l'activation du chaînage) : pas de hash → on saute.
        if not a.entry_hash:
            prev = ""
            continue
        if (a.prev_hash or "") != prev or _hash(prev, a) != a.entry_hash:
            broken_at = a.id
            break
        prev = a.entry_hash
    chained = [a for a in rows if a.entry_hash]
    return {
        "owner_id": owner_id,
        "entries": len(rows),
        "chained_entries": len(chained),
        "intact": broken_at is None,
        "broken_at_id": broken_at,
    }
