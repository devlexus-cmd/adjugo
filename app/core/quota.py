"""
Quotas d'analyses IA par plan (PLAN_LIMITS).
Compteur mensuel avec reset automatique au changement de mois.
"""
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings

settings = get_settings()


def _billing_user(user, db):
    """Le quota d'analyses est porté par le PROPRIÉTAIRE de l'organisation : tous les
    membres consomment le MÊME pool, au plan du propriétaire (un client Business n'a
    plus N quotas starter indépendants). Repli sur l'utilisateur si pas d'org/db."""
    if db is None:
        return user
    try:
        from app.models import Organization, User as U
        oid = getattr(user, "org_id", None)
        if not oid:
            return user
        org = db.query(Organization).filter(Organization.id == oid).first()
        if org and org.owner_id and org.owner_id != user.id:
            owner = db.query(U).filter(U.id == org.owner_id).first()
            if owner:
                return owner
    except Exception:
        return user
    return user


def _plan_key(user) -> str:
    p = getattr(user, "plan", "starter")
    return p.value if hasattr(p, "value") else str(p)


def _limit(user) -> int:
    limits = settings.PLAN_LIMITS.get(_plan_key(user), {})
    return int(limits.get("analyses", 3))


def _period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _sync_period(user) -> None:
    """Réinitialise les compteurs MENSUELS si on a changé de mois."""
    cur = _period()
    if getattr(user, "analyses_period", "") != cur:
        user.analyses_period = cur
        user.analyses_used_this_month = 0
        # overage_count est « ce mois » (affiché « à facturer ce mois ») : sans cette remise à
        # zéro il cumulait depuis l'inscription → un montant faux et toujours plus gros.
        if hasattr(user, "overage_count"):
            user.overage_count = 0


OVERAGE_PRICE = 5  # € HT par analyse hors quota


def usage(user, db: Session = None) -> dict:
    user = _billing_user(user, db)   # le pool de l'org (propriétaire) si membre
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
    """Vérifie le quota et incrémente, de façon ATOMIQUE (verrou de ligne Postgres :
    ferme la course read-modify-write qui permettait de contourner le quota en lançant
    2 analyses en parallèle). Au-delà du quota : overage si activé, sinon 402."""
    # Verrou « email vérifié » : aucune action coûteuse (IA/quota) tant que l'adresse de l'utilisateur
    # AGISSANT n'est pas confirmée — anti-contournement par appel API direct (le front bloque déjà l'UI).
    if not getattr(user, "email_verified", True):
        from fastapi import HTTPException
        raise HTTPException(403, "Confirmez votre adresse email pour utiliser cette fonctionnalité.")
    from app.models import User as _User
    # Le quota est porté par le propriétaire de l'org (pool partagé).
    billing = _billing_user(user, db)
    # SELECT … FOR UPDATE : sérialise les consommations concurrentes (no-op SQLite dev,
    # protection réelle sur Postgres prod).
    locked = db.query(_User).filter(_User.id == billing.id).with_for_update().first() or billing
    _sync_period(locked)
    lim = _limit(locked)
    used = locked.analyses_used_this_month or 0
    if used >= lim:
        if getattr(locked, "overage_enabled", False):
            locked.overage_count = (getattr(locked, "overage_count", 0) or 0) + 1
            locked.analyses_used_this_month = used + 1
            db.commit()
            try:
                from app.services.billing_usage import report_overage
                report_overage(locked)
            except Exception as e:
                import logging
                logging.getLogger("adjugo").warning("Report d'usage facturable échoué (user %s) : %s", locked.id, e)
            return
        raise HTTPException(
            status_code=402,
            detail=f"Quota d'analyses IA atteint ({used}/{lim} ce mois) pour le plan "
                   f"« {_plan_key(locked)} ». Activez le paiement à l'usage ({OVERAGE_PRICE} € "
                   f"/ analyse) ou passez à un plan supérieur pour continuer.",
        )
    locked.analyses_used_this_month = used + 1
    db.commit()


def refund_analysis(user, db: Session) -> None:
    """Rembourse une analyse consommée quand le traitement IA échoue (le client ne doit
    pas être débité pour une analyse qui n'a rien produit). Annule aussi l'overage."""
    try:
        from app.models import User as _User
        billing = _billing_user(user, db)
        locked = db.query(_User).filter(_User.id == billing.id).with_for_update().first() or billing
        _sync_period(locked)   # remboursement après bascule de mois → ne pas décrémenter la nouvelle période
        used = locked.analyses_used_this_month or 0
        if used <= 0:
            return
        if used > _limit(locked) and (locked.overage_count or 0) > 0:
            locked.overage_count -= 1  # c'était une analyse hors quota facturée
        locked.analyses_used_this_month = used - 1
        db.commit()
    except Exception as e:
        import logging
        logging.getLogger("adjugo").warning("Remboursement quota échoué (user %s) : %s", getattr(user, "id", "?"), e)
