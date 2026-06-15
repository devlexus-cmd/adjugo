"""
Quotas d'analyses IA par plan (PLAN_LIMITS).
Compteur mensuel avec reset automatique au changement de mois.
"""
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings

settings = get_settings()


def _plan_key(user) -> str:
    p = getattr(user, "plan", "starter")
    return p.value if hasattr(p, "value") else str(p)


def _limit(user) -> int:
    limits = settings.PLAN_LIMITS.get(_plan_key(user), {})
    return int(limits.get("analyses", 3))


def _period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _sync_period(user) -> None:
    """Réinitialise le compteur si on a changé de mois."""
    cur = _period()
    if getattr(user, "analyses_period", "") != cur:
        user.analyses_period = cur
        user.analyses_used_this_month = 0


OVERAGE_PRICE = 5  # € HT par analyse hors quota


def usage(user) -> dict:
    _sync_period(user)
    lim = _limit(user)
    used = user.analyses_used_this_month or 0
    return {
        "plan": _plan_key(user),
        "analyses_used": used,
        "analyses_limit": lim,
        "analyses_remaining": max(0, lim - used),
        "overage_enabled": bool(getattr(user, "overage_enabled", False)),
        "overage_count": getattr(user, "overage_count", 0) or 0,
        "overage_price": OVERAGE_PRICE,
        "period": _period(),
    }


def consume_analysis(user, db: Session) -> None:
    """Vérifie le quota et incrémente. Au-delà du quota : facture un overage si
    l'utilisateur l'a activé (pas de blocage), sinon lève 402."""
    _sync_period(user)
    lim = _limit(user)
    used = user.analyses_used_this_month or 0
    if used >= lim:
        if getattr(user, "overage_enabled", False):
            user.overage_count = (getattr(user, "overage_count", 0) or 0) + 1
            user.analyses_used_this_month = used + 1
            db.commit()
            # Report de l'usage facturable (best-effort, ne bloque jamais l'analyse)
            try:
                from app.services.billing_usage import report_overage
                report_overage(user)
            except Exception as e:
                import logging
                logging.getLogger("adjugo").warning("Report d'usage facturable échoué (user %s) : %s", user.id, e)
            return
        raise HTTPException(
            status_code=402,
            detail=f"Quota d'analyses IA atteint ({used}/{lim} ce mois) pour le plan "
                   f"« {_plan_key(user)} ». Activez le paiement à l'usage ({OVERAGE_PRICE} € "
                   f"/ analyse) ou passez à un plan supérieur pour continuer.",
        )
    user.analyses_used_this_month = used + 1
    db.commit()
