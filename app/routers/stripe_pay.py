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
def get_subscription_status(current_user: User = Depends(get_current_user)):
    stripe.api_key = settings.STRIPE_SECRET_KEY

    if not current_user.stripe_customer_id:
        return {"plan": "starter", "status": "active", "analyses_limit": _limit("starter")}

    try:
        subscriptions = stripe.Subscription.list(
            customer=current_user.stripe_customer_id,
            status="active",
            limit=1
        )

        if not subscriptions.data:
            return {"plan": "starter", "status": "active", "analyses_limit": _limit("starter")}

        sub = subscriptions.data[0]
        price_id = sub["items"]["data"][0]["price"]["id"]

        if price_id == settings.STRIPE_PRICE_PRO:
            return {"plan": "pro", "status": "active", "analyses_limit": _limit("pro"), "current_period_end": sub.current_period_end}
        elif price_id == settings.STRIPE_PRICE_BUSINESS:
            return {"plan": "business", "status": "active", "analyses_limit": _limit("business"), "current_period_end": sub.current_period_end}

        return {"plan": "starter", "status": "active", "analyses_limit": _limit("starter")}

    except stripe.error.StripeError:
        return {"plan": "starter", "status": "active", "analyses_limit": _limit("starter")}


@router.post("/overage")
def set_overage(enabled: bool = True, current_user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """Active/désactive le paiement à l'usage au-delà du quota mensuel."""
    current_user.overage_enabled = bool(enabled)
    db.commit()
    from app.core.quota import OVERAGE_PRICE
    return {"overage_enabled": current_user.overage_enabled,
            "overage_count": current_user.overage_count or 0,
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

    try:
        if settings.STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig, settings.STRIPE_WEBHOOK_SECRET)
        else:
            import json
            event = json.loads(payload)
    except Exception:
        raise HTTPException(400, "Webhook invalide")

    from app.models import PlanType

    def _set_plan(user, plan_str):
        try:
            user.plan = PlanType(plan_str)
        except ValueError:
            user.plan = PlanType.pro

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("user_id")
        plan = session.get("metadata", {}).get("plan", "pro")
        customer_id = session.get("customer")
        if user_id:
            user = db.query(User).filter(User.id == int(user_id)).first()
            if user:
                _set_plan(user, plan)
                if customer_id:
                    user.stripe_customer_id = customer_id  # pour gérer la résiliation ensuite
                user.analyses_used_this_month = 0  # repart à zéro au passage payant
                db.commit()

    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        customer_id = sub["customer"]
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if user:
            _set_plan(user, "starter")
            db.commit()

    return JSONResponse({"status": "ok"})
