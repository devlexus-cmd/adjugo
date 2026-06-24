import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.config import get_settings
from app.models import User

router = APIRouter(prefix="/api/stripe", tags=["Paiements Stripe"])
settings = get_settings()


@router.post("/create-checkout")
def create_checkout(plan: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stripe.api_key = settings.STRIPE_SECRET_KEY

    prices = {"pro": settings.STRIPE_PRICE_PRO, "business": settings.STRIPE_PRICE_BUSINESS}
    if plan not in prices:
        raise HTTPException(400, "Plan invalide. Choisissez 'pro' ou 'business'.")

    try:
        # Creer ou recuperer le customer Stripe
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                name=current_user.full_name or "",
                metadata={"user_id": str(current_user.id)}
            )
            current_user.stripe_customer_id = customer.id
            db.commit()

        session = stripe.checkout.Session.create(
            customer=current_user.stripe_customer_id,
            payment_method_types=["card"],
            line_items=[{"price": prices[plan], "quantity": 1}],
            mode="subscription",
            success_url=settings.APP_BASE_URL + "/app?payment=success",
            cancel_url=settings.APP_BASE_URL + "/app?payment=cancel",
            metadata={"user_id": str(current_user.id), "plan": plan}
        )
        return {"checkout_url": session.url, "session_id": session.id}

    except stripe.error.StripeError as e:
        raise HTTPException(400, str(e))


def _limit(plan: str) -> int:
    """Quota d'analyses du plan — source unique : settings.PLAN_LIMITS."""
    return settings.PLAN_LIMITS.get(plan, {}).get("analyses", 0)


@router.get("/status")
def get_subscription_status(current_user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    stripe.api_key = settings.STRIPE_SECRET_KEY
    from app.core.quota import _billing_user
    # Le quota RÉEL est porté par le PROPRIÉTAIRE de l'org (pool partagé) : un membre doit voir
    # le plan de l'org, pas « starter / 2 » (son propre abonnement, inexistant).
    bu = _billing_user(current_user, db)

    def _persisted():
        plan = getattr(bu.plan, "value", bu.plan) or "starter"
        return {"plan": plan, "status": "active", "analyses_limit": _limit(plan)}

    if not bu.stripe_customer_id:
        return _persisted()

    try:
        subscriptions = stripe.Subscription.list(
            customer=bu.stripe_customer_id, status="active", limit=1)
        if not subscriptions.data:
            return _persisted()

        sub = subscriptions.data[0]
        price_id = sub["items"]["data"][0]["price"]["id"]
        if price_id == settings.STRIPE_PRICE_PRO:
            plan = "pro"
        elif price_id == settings.STRIPE_PRICE_BUSINESS:
            plan = "business"
        else:
            plan = "starter"

        # Réconciliation : si l'abonnement Stripe diverge du plan EN BASE (webhook en retard ou
        # non configuré), on persiste → l'AFFICHAGE et l'ENFORCEMENT du quota convergent (sinon
        # le client payait Pro, voyait « Pro / 30 », mais était bloqué à 2 avec un message « starter »).
        if (getattr(bu.plan, "value", bu.plan) or "starter") != plan:
            try:
                from app.models import PlanType
                bu.plan = PlanType(plan)
                db.commit()
            except Exception:
                db.rollback()
        return {"plan": plan, "status": "active", "analyses_limit": _limit(plan),
                "current_period_end": sub.current_period_end}

    except stripe.error.StripeError:
        return _persisted()


@router.post("/overage")
def set_overage(enabled: bool = True, current_user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """Active/désactive le paiement à l'usage au-delà du quota mensuel."""
    # Le quota/overage est porté par le PROPRIÉTAIRE du pool de facturation : on écrit SON
    # flag (sinon le toggle d'un membre n'avait aucun effet — consume_analysis lit l'owner).
    # Et c'est un engagement financier → réservé au propriétaire / admin de l'organisation.
    from app.core.quota import OVERAGE_PRICE, _billing_user
    bu = _billing_user(current_user, db)
    if bu.id != current_user.id and getattr(current_user, "org_role", "") not in ("owner", "admin"):
        raise HTTPException(403, "Seul le propriétaire ou un administrateur peut activer le paiement à l'usage")
    bu.overage_enabled = bool(enabled)
    db.commit()
    return {"overage_enabled": bu.overage_enabled,
            "overage_count": bu.overage_count or 0,
            "overage_price": OVERAGE_PRICE}


@router.post("/portal")
def create_portal(current_user: User = Depends(get_current_user)):
    stripe.api_key = settings.STRIPE_SECRET_KEY

    if not current_user.stripe_customer_id:
        raise HTTPException(400, "Pas d'abonnement actif")

    try:
        session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=settings.APP_BASE_URL + "/app"
        )
        return {"portal_url": session.url}

    except stripe.error.StripeError as e:
        raise HTTPException(400, str(e))


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    stripe.api_key = settings.STRIPE_SECRET_KEY

    # SIGNATURE OBLIGATOIRE : sans secret on REFUSE (plus de fallback JSON non signé). Sinon
    # n'importe qui pouvait POSTer un faux « checkout.session.completed » et s'offrir un plan
    # payant gratuitement (metadata user_id/plan entièrement contrôlés par l'attaquant).
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(503, "Webhook Stripe non configuré")
    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.STRIPE_WEBHOOK_SECRET)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Webhook invalide (signature)")

    from app.models import PlanType, ProcessedStripeEvent

    # Idempotence : si cet event_id a déjà été traité (Stripe rejoue ses webhooks), on s'arrête là.
    # On INSÈRE d'abord (la PK event_id rend l'opération atomique : un rejeu concurrent échoue).
    evt_id = event.get("id") if isinstance(event, dict) else getattr(event, "id", None)
    if evt_id:
        if db.query(ProcessedStripeEvent).filter(ProcessedStripeEvent.event_id == evt_id).first():
            return {"status": "ignored", "reason": "duplicate"}
        try:
            db.add(ProcessedStripeEvent(event_id=evt_id))
            db.commit()
        except Exception:
            db.rollback()
            return {"status": "ignored", "reason": "duplicate"}

    def _set_plan(user, plan_str):
        try:
            user.plan = PlanType(plan_str)
        except ValueError:
            user.plan = PlanType.starter   # plan inconnu → palier le PLUS BAS (jamais une montée)

    def _plan_for_price(price_id):
        if price_id and price_id == settings.STRIPE_PRICE_PRO:
            return "pro"
        if price_id and price_id == settings.STRIPE_PRICE_BUSINESS:
            return "business"
        return "starter"

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("user_id")
        plan = session.get("metadata", {}).get("plan", "pro")
        customer_id = session.get("customer")
        try:
            user_id = int(user_id) if user_id else None
        except (TypeError, ValueError):
            user_id = None
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                was = user.plan
                _set_plan(user, plan)
                if customer_id:
                    user.stripe_customer_id = customer_id  # pour gérer la résiliation ensuite
                # Idempotence : on ne remet le compteur d'analyses à zéro que sur un VRAI
                # changement de plan — un rejeu (Stripe retry / event signé répété) ne doit
                # pas réinitialiser le quota à chaque fois.
                if user.plan != was:
                    user.analyses_used_this_month = 0
                db.commit()

    elif event["type"] == "customer.subscription.updated":
        # Changement d'abonnement via le PORTAIL client (downgrade/upgrade) ou échec de paiement
        # (past_due/unpaid) → on re-dérive le plan depuis le price_id courant. Sans ça, un
        # downgrade Business→Pro n'était jamais reflété (le quota lisait l'ancien plan).
        sub = event["data"]["object"]
        customer_id = sub.get("customer")
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if user:
            if sub.get("status") in ("active", "trialing"):
                try:
                    price_id = sub["items"]["data"][0]["price"]["id"]
                except (KeyError, IndexError, TypeError):
                    price_id = None
                _set_plan(user, _plan_for_price(price_id))
            else:   # past_due / unpaid / incomplete / canceled → on rétrograde au gratuit
                _set_plan(user, "starter")
            db.commit()

    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        customer_id = sub["customer"]
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if user:
            _set_plan(user, "starter")
            db.commit()

    return JSONResponse({"status": "ok"})
