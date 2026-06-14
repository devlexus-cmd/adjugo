"""
Report d'usage facturable (overage) vers Stripe — best-effort.

Si un prix « metered » est configuré (STRIPE_PRICE_OVERAGE) et que l'utilisateur a un
abonnement, on enregistre une unité d'usage. Sinon on log seulement : le dépassement
reste compté en base (User.overage_count) et facturable manuellement. Ne bloque jamais.
"""
import logging

from app.core.config import get_settings

logger = logging.getLogger("adjugo")
settings = get_settings()


def report_overage(user, quantity: int = 1) -> bool:
    price_id = getattr(settings, "STRIPE_PRICE_OVERAGE", "") or ""
    if not price_id or not getattr(user, "stripe_customer_id", None):
        logger.info("overage compté (user=%s, total=%s) — pas de metered Stripe configuré",
                    user.id, getattr(user, "overage_count", 0))
        return False
    try:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        # API Meter Events (Stripe billing à l'usage)
        stripe.billing.MeterEvent.create(
            event_name="adjugo_analyse_overage",
            payload={"value": str(quantity),
                     "stripe_customer_id": user.stripe_customer_id},
        )
        logger.info("overage Stripe reporté (user=%s)", user.id)
        return True
    except Exception as e:
        logger.warning("report overage Stripe échoué (user=%s) : %s", user.id, e)
        return False
