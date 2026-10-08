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


TRIAL_DAYS = 30


def _as_utc(dt):
    """Normalise une datetime éventuellement naïve (SQLite) en UTC pour comparer."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _trial_state(user) -> str:
    """État de l'essai gratuit 30j pour un compte au plan 'starter' :
      'active'  → essai en cours (accès niveau Pro),
      'expired' → essai terminé (bloqué : plus d'offre gratuite),
      'none'    → aucun essai attaché (trial_ends_at NULL = compte historique/démo,
                  ancien comportement Découverte conservé)."""
    ends = _as_utc(getattr(user, "trial_ends_at", None))
    if ends is None:
        return "none"
    return "active" if ends > datetime.now(timezone.utc) else "expired"


def _trial_days_left(user) -> int:
    import math
    ends = _as_utc(getattr(user, "trial_ends_at", None))
    if ends is None:
        return 0
    return max(0, math.ceil((ends - datetime.now(timezone.utc)).total_seconds() / 86400))


def _limit(user) -> int:
    plan = _plan_key(user)
    if plan in ("pro", "business"):
        return int(settings.PLAN_LIMITS.get(plan, {}).get("analyses", 0))
    # plan 'starter' (ou inconnu) : le quota depend de l'essai gratuit.
    st = _trial_state(user)
    if st == "active":
        return int(settings.PLAN_LIMITS.get("pro", {}).get("analyses", 30))   # acces Pro pendant l'essai
    if st == "expired":
        return 0   # essai termine → bloque
    return int(settings.PLAN_LIMITS.get("starter", {}).get("analyses", 5))     # historique/demo


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


def overage_billable(user) -> bool:
    """Le paiement à l'usage n'est honoré que s'il est FACTURABLE : abonnement payant (plan
    pro/business, posé par le webhook Stripe signé et rétrogradé à la résiliation) ET client
    Stripe connu. Sans cela (essai gratuit, compte sans carte, compte démo), chaque analyse
    hors quota coûterait réellement à Adjugo sans pouvoir être facturée."""
    return _plan_key(user) in ("pro", "business") and bool(getattr(user, "stripe_customer_id", None))


def _is_demo(user) -> bool:
    try:
        from app.services.demo_search import is_demo
        return is_demo(user)
    except Exception:
        return False


def usage(user, db: Session = None) -> dict:
    user = _billing_user(user, db)   # le pool de l'org (propriétaire) si membre
    _sync_period(user)
    lim = _limit(user)
    used = user.analyses_used_this_month or 0
    plan = _plan_key(user)
    tstate = _trial_state(user) if plan not in ("pro", "business") else None
    ends = _as_utc(getattr(user, "trial_ends_at", None))
    return {
        "plan": plan,
        "analyses_used": used,
        "analyses_limit": lim,
        "analyses_remaining": max(0, lim - used),
        "overage_enabled": bool(getattr(user, "overage_enabled", False)),
        "overage_count": getattr(user, "overage_count", 0) or 0,
        "overage_price": OVERAGE_PRICE,
        "period": _period(),
        "trial_state": tstate,                                   # 'active'|'expired'|'none'|None (payant)
        "trial_days_left": _trial_days_left(user) if tstate == "active" else 0,
        "trial_ends_at": ends.isoformat() if ends else None,
    }


def consume_analysis(user, db: Session) -> None:
    """Vérifie le quota et incrémente, de façon ATOMIQUE (verrou de ligne Postgres :
    ferme la course read-modify-write qui permettait de contourner le quota en lançant
    2 analyses en parallèle). Au-delà du quota : overage si activé, sinon 402."""
    # Compte démo public (vitrine en lecture guidée) : AUCUN appel IA réel. Les analyses des
    # marchés DEMO- sont servies en amont, sans passer par ici ; tout ce qui arrive ici est
    # donc un vrai appel payant (défense en profondeur derrière le middleware demo_guard).
    if _is_demo(user) or (db is not None and _is_demo(_billing_user(user, db))):
        from app.core.demo_guard import demo_message
        raise HTTPException(403, demo_message("lancer une analyse IA"))
    # Verrou « email vérifié » : aucune action coûteuse (IA/quota) tant que l'adresse de l'utilisateur
    # AGISSANT n'est pas confirmée — anti-contournement par appel API direct (le front bloque déjà l'UI).
    if not getattr(user, "email_verified", True):
        # NB : surtout PAS de « from fastapi import HTTPException » ici — un import local
        # rendait HTTPException locale à TOUTE la fonction → le 402 « quota atteint » plus
        # bas plantait en 500 (UnboundLocalError) pour tout utilisateur vérifié à la limite.
        raise HTTPException(403, "Confirmez votre adresse email pour utiliser cette fonctionnalité.")
    from app.models import User as _User
    # Le quota est porté par le propriétaire de l'org (pool partagé).
    billing = _billing_user(user, db)
    # SELECT … FOR UPDATE : sérialise les consommations concurrentes (no-op SQLite dev,
    # protection réelle sur Postgres prod). populate_existing() est INDISPENSABLE : l'objet
    # User est déjà dans l'identity map de la session (chargé par get_current_user), et sans
    # lui SQLAlchemy renvoie les attributs lus AVANT le verrou → le compteur périmé rouvrait
    # exactement la course que ce verrou prétend fermer.
    locked = (db.query(_User).filter(_User.id == billing.id)
              .populate_existing().with_for_update().first() or billing)
    _sync_period(locked)
    lim = _limit(locked)
    used = locked.analyses_used_this_month or 0
    # Essai gratuit 30j termine (plan starter, essai expire) → blocage net, SANS overage
    # (aucun abonnement pour le facturer). Message dedie orientant vers l'abonnement.
    if _plan_key(locked) == "starter" and _trial_state(locked) == "expired":
        raise HTTPException(
            status_code=402,
            detail="Votre essai gratuit de 30 jours est termine. Abonnez-vous (Pro ou Business) "
                   "pour continuer a lancer des analyses.",
        )
    if used >= lim:
        # Overage SEULEMENT s'il est facturable (abonnement payant + client Stripe) : un flag
        # activé pendant l'essai, ou laissé après une résiliation, ne doit jamais ouvrir des
        # analyses IA illimitées et non facturables → on retombe sur le 402 standard.
        if getattr(locked, "overage_enabled", False) and overage_billable(locked):
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
        if overage_billable(locked):
            hint = (f"Activez le paiement à l'usage ({OVERAGE_PRICE} € / analyse) ou passez "
                    f"à un plan supérieur pour continuer.")
        else:
            hint = "Abonnez-vous (Pro ou Business) pour continuer."
        raise HTTPException(
            status_code=402,
            detail=f"Quota d'analyses IA atteint ({used}/{lim} ce mois) pour le plan "
                   f"« {_plan_key(locked)} ». {hint}",
        )
    locked.analyses_used_this_month = used + 1
    db.commit()


def refund_analysis(user, db: Session) -> None:
    """Rembourse une analyse consommée quand le traitement IA échoue (le client ne doit
    pas être débité pour une analyse qui n'a rien produit). Annule aussi l'overage."""
    try:
        from app.models import User as _User
        billing = _billing_user(user, db)
        locked = (db.query(_User).filter(_User.id == billing.id)
                  .populate_existing().with_for_update().first() or billing)   # populate_existing : cf. consume_analysis
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
