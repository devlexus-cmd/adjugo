"""
Adjugo — Journal d'accès (RGPD).

Trace immuable de qui consulte/télécharge quoi, et quand. Surtout : les accès des
co-traitants externes invités via un lien bridé. C'est la preuve de traçabilité
exigible (RGPD / confidentialité des dossiers de candidature).

Principe : un échec d'écriture du journal NE DOIT JAMAIS faire échouer l'action
métier sous-jacente — on isole donc l'écriture et on avale toute exception.
"""
import logging
from typing import Optional

logger = logging.getLogger("adjugo")


def client_ip(request) -> str:
    """IP réelle du client derrière le proxy Railway (X-Forwarded-For = 1er hop)."""
    try:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()[:45]
        return (request.client.host if request.client else "")[:45]
    except Exception:
        return ""


def record(db, *, action: str, owner_id: Optional[int] = None,
           project_id: Optional[int] = None, actor: str = "", actor_kind: str = "",
           target_type: str = "", target_id: Optional[int] = None,
           detail: str = "", ip: str = "", meta: Optional[dict] = None) -> None:
    """Écrit une entrée d'audit. Best-effort : ne propage jamais d'exception."""
    try:
        from app.models import AuditLog
        db.add(AuditLog(
            action=action[:60], owner_id=owner_id, project_id=project_id,
            actor=(actor or "")[:160], actor_kind=(actor_kind or "")[:20],
            target_type=(target_type or "")[:40], target_id=target_id,
            detail=(detail or "")[:255], ip=(ip or "")[:45], meta=meta,
        ))
        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("audit: écriture du journal échouée (%s) : %s", action, e)
