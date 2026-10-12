"""
Report d'usage facturable (overage) vers Stripe — best-effort.

Chemin complet de la facturation au-delà du forfait (5 € HT par analyse) :
  1. quota.consume_analysis : au-delà du quota, si le paiement à l'usage est activé ET facturable
     (abonnement payant + client Stripe), l'analyse est comptée (User.overage_count) puis
     report_overage envoie UNE unité au compteur Stripe (Billing → Meters, événement
     STRIPE_METER_EVENT_OVERAGE) ;
  2. l'abonnement porte le prix « à l'usage » STRIPE_PRICE_OVERAGE (ajouté au paiement, et à
     l'activation du paiement à l'usage pour un abonnement plus ancien) : Stripe facture les unités
     du mois sur la facture suivante ;
  3. quota.refund_analysis : si l'IA tombe après le débit, l'unité est ANNULÉE chez Stripe
     (cancel_overage, ajustement d'événement par son identifiant).
Sans STRIPE_PRICE_OVERAGE (ou sans client Stripe) : on journalise seulement ; le dépassement reste
compté en base et facturable à la main. Ne bloque jamais une analyse.
"""
import logging
import threading
import uuid
from datetime import datetime, timezone

from app.core.config import get_settings

logger = logging.getLogger("adjugo")
settings = get_settings()

# Identifiants des unités envoyées ce mois, par client facturé (process unique) : sert à annuler la
# dernière si l'analyse est remboursée. Après un redémarrage, une annulation impossible est
# journalisée (à reprendre à la main dans Stripe, dans les 24 h permises par Stripe).
_SENT = {}
_SENT_LOCK = threading.Lock()
_SENT_MAX_USERS = 5000


def _event_name() -> str:
    return (getattr(settings, "STRIPE_METER_EVENT_OVERAGE", "") or "adjugo_analyse_overage").strip()


def overage_configured() -> bool:
    return bool((getattr(settings, "STRIPE_PRICE_OVERAGE", "") or "").strip())


def _period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def report_overage(user, quantity: int = 1) -> bool:
    price_id = getattr(settings, "STRIPE_PRICE_OVERAGE", "") or ""
    if not price_id or not getattr(user, "stripe_customer_id", None):
        logger.info("overage compté (user=%s, total=%s) — pas de metered Stripe configuré",
                    user.id, getattr(user, "overage_count", 0))
        return False
    ident = f"adjugo-ovr-{user.id}-{_period()}-{uuid.uuid4().hex[:16]}"
    try:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        # API Meter Events (Stripe billing à l'usage) ; identifiant unique = pas de double
        # comptage si Stripe reçoit deux fois la même unité, et annulation possible.
        stripe.billing.MeterEvent.create(
            event_name=_event_name(),
            payload={"value": str(quantity),
                     "stripe_customer_id": user.stripe_customer_id},
            identifier=ident,
        )
        with _SENT_LOCK:
            key = (user.id, _period())
            if key not in _SENT and len(_SENT) >= _SENT_MAX_USERS:
                _SENT.pop(next(iter(_SENT)), None)
            _SENT.setdefault(key, []).append(ident)
        logger.info("overage Stripe reporté (user=%s)", user.id)
        return True
    except Exception as e:
        logger.warning("report overage Stripe échoué (user=%s) : %s", user.id, e)
        return False


def cancel_overage(user) -> bool:
    """Annule chez Stripe la dernière unité envoyée pour ce client ce mois-ci (analyse remboursée)."""
    if not overage_configured() or not getattr(user, "stripe_customer_id", None):
        return False
    with _SENT_LOCK:
        lst = _SENT.get((user.id, _period())) or []
        ident = lst.pop() if lst else None
    if not ident:
        logger.warning("analyse hors forfait remboursée (user=%s) sans unité Stripe connue à annuler : "
                       "vérifiez l'usage du mois dans Stripe", user.id)
        return False
    try:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        stripe.billing.MeterEventAdjustment.create(
            event_name=_event_name(), type="cancel", cancel={"identifier": ident})
        logger.info("overage Stripe annulé (user=%s)", user.id)
        return True
    except Exception as e:
        logger.warning("annulation overage Stripe échouée (user=%s) : %s", user.id, e)
        return False


def ensure_overage_item(user) -> bool:
    """Ajoute le prix « à l'usage » à l'abonnement actif du client s'il n'y est pas (abonnements
    souscrits avant l'activation du dépassement). Sans lui, les unités envoyées au compteur ne
    seraient jamais facturées. Renvoie True si l'abonnement porte le prix (ou s'il n'y a rien à
    faire : dépassement non configuré). Lève l'exception Stripe en cas d'échec."""
    price_id = (getattr(settings, "STRIPE_PRICE_OVERAGE", "") or "").strip()
    if not price_id or not getattr(user, "stripe_customer_id", None):
        return not price_id
    import stripe
    stripe.api_key = settings.STRIPE_SECRET_KEY
    subs = stripe.Subscription.list(customer=user.stripe_customer_id, status="active", limit=1)
    if not subs.data:
        return False
    sub = subs.data[0]
    items = ((sub.get("items") or {}).get("data") or []) if hasattr(sub, "get") else []
    if any(((it.get("price") or {}).get("id") == price_id) for it in items):
        return True
    stripe.SubscriptionItem.create(subscription=sub["id"], price=price_id)
    return True


def plan_price_id(items) -> str:
    """Prix du FORFAIT dans les éléments d'un abonnement (ignore le prix à l'usage, quel que soit
    son rang) : Pro ou Business s'il y figure, sinon le premier prix."""
    ids = []
    for it in items or []:
        try:
            ids.append(it["price"]["id"])
        except (KeyError, TypeError, IndexError):
            continue
    for pid in ids:
        if pid and pid in (settings.STRIPE_PRICE_PRO, settings.STRIPE_PRICE_BUSINESS):
            return pid
    over = (getattr(settings, "STRIPE_PRICE_OVERAGE", "") or "").strip()
    rest = [pid for pid in ids if pid != over]
    return rest[0] if rest else (ids[0] if ids else None)
