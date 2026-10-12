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
     (cancel_overage, ajustement d'événement par son identifiant). L'identifiant de chaque unité
     envoyée est rangé en base (une ligne `jobs` de type « unite_depassement », sans autre donnée) :
     l'annulation fonctionne aussi après un redémarrage du serveur (une longue lecture de dossier
     interrompue par un déploiement est remboursée au démarrage), dans les 24 h permises par Stripe.
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

# Identifiants des unités envoyées ce mois, par client facturé : rangés en base (UNITE_KIND), et en
# mémoire pour les appels sans session (repli).
UNITE_KIND = "unite_depassement"
UNITE_GARDE_JOURS = 62
_SENT = {}
_SENT_LOCK = threading.Lock()
_SENT_MAX_USERS = 5000


def _event_name() -> str:
    return (getattr(settings, "STRIPE_METER_EVENT_OVERAGE", "") or "adjugo_analyse_overage").strip()


def overage_configured() -> bool:
    return bool((getattr(settings, "STRIPE_PRICE_OVERAGE", "") or "").strip())


def _period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _ranger_unite(db, user, ident: str):
    """Ligne `jobs` qui garde l'identifiant d'une unité envoyée (avant l'envoi : un arrêt du serveur
    entre les deux laisse une ligne « envoi », annulable elle aussi). None si impossible."""
    if db is None:
        return None
    try:
        from datetime import timedelta
        from app.models import Job
        row = Job(user_id=user.id, kind=UNITE_KIND, status="envoi", label=ident[:255])
        db.add(row)
        db.commit()
        try:
            old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=UNITE_GARDE_JOURS)
            db.query(Job).filter(Job.user_id == user.id, Job.kind == UNITE_KIND,
                                 Job.created_at < old).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        return row
    except Exception as e:      # noqa: BLE001 — jamais bloquant : repli en mémoire
        db.rollback()
        logger.warning("identifiant d'usage Stripe non rangé (user=%s) : %s", user.id, type(e).__name__)
        return None


def _statut_unite(db, row, statut: str) -> None:
    if db is None or row is None:
        return
    try:
        if statut is None:
            db.delete(row)
        else:
            row.status = statut
        db.commit()
    except Exception:
        db.rollback()


def report_overage(user, quantity: int = 1, db=None) -> bool:
    price_id = getattr(settings, "STRIPE_PRICE_OVERAGE", "") or ""
    if not price_id or not getattr(user, "stripe_customer_id", None):
        logger.info("overage compté (user=%s, total=%s) — pas de metered Stripe configuré",
                    user.id, getattr(user, "overage_count", 0))
        return False
    ident = f"adjugo-ovr-{user.id}-{_period()}-{uuid.uuid4().hex[:16]}"
    row = _ranger_unite(db, user, ident)
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
        _statut_unite(db, row, "envoyee")
        with _SENT_LOCK:
            key = (user.id, _period())
            if key not in _SENT and len(_SENT) >= _SENT_MAX_USERS:
                _SENT.pop(next(iter(_SENT)), None)
            _SENT.setdefault(key, []).append(ident)
        logger.info("overage Stripe reporté (user=%s)", user.id)
        return True
    except Exception as e:
        _statut_unite(db, row, None)             # rien d'envoyé : rien à annuler
        logger.warning("report overage Stripe échoué (user=%s) : %s", user.id, e)
        return False


def _unite_a_annuler(db, user):
    """Dernière unité envoyée ce mois-ci et pas encore annulée (ligne en base), ou None."""
    if db is None:
        return None
    try:
        from app.models import Job
        debut = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0,
                                                   tzinfo=None)
        return (db.query(Job).filter(Job.user_id == user.id, Job.kind == UNITE_KIND,
                                     Job.status.in_(["envoi", "envoyee"]), Job.created_at >= debut)
                .order_by(Job.id.desc()).first())
    except Exception:
        db.rollback()
        return None


def cancel_overage(user, db=None) -> bool:
    """Annule chez Stripe la dernière unité envoyée pour ce client ce mois-ci (analyse remboursée).
    L'identifiant est lu en base (fonctionne après un redémarrage), sinon en mémoire."""
    if not overage_configured() or not getattr(user, "stripe_customer_id", None):
        return False
    row = _unite_a_annuler(db, user)
    ident = row.label if row is not None else None
    with _SENT_LOCK:
        lst = _SENT.get((user.id, _period())) or []
        if ident is None:
            ident = lst.pop() if lst else None
        elif ident in lst:
            lst.remove(ident)
    if not ident:
        logger.warning("analyse hors forfait remboursée (user=%s) sans unité Stripe connue à annuler : "
                       "vérifiez l'usage du mois dans Stripe", user.id)
        return False
    try:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        stripe.billing.MeterEventAdjustment.create(
            event_name=_event_name(), type="cancel", cancel={"identifier": ident})
        _statut_unite(db, row, "annulee")
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
