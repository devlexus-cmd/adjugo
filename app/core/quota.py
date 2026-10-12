"""
Quotas d'analyses IA par plan (PLAN_LIMITS).
Compteur mensuel avec reset automatique au changement de mois.

Essai gratuit (30 jours, comptes en essai actif SEULEMENT) : TRIAL_ANALYSES analyses sur TOUTE la
durée de l'essai (compteur users.trial_analyses_used, jamais remis à zéro au changement de mois),
TRIAL_QUESTIONS_PAR_JOUR questions par jour, et le budget IA de l'essai vérifié avant chaque
opération (app/services/budget_ia.py). Forfaits payants : comportement inchangé.

Essai TERMINÉ sans formule payante (décision du fondateur, 12/10/2026, option a) : toutes les
fonctions d'IA sont en pause (analyses, questions, atelier, questionnaire, chiffrage, veille…) ;
`exiger_ia` refuse (402, code « essai_termine ») AVANT tout appel et tout débit. Un traitement
commencé avant la fin de l'essai va au bout (aucune vérification en cours de route). Comptes
historiques sans essai (trial_ends_at NULL), compte de démonstration et forfaits payants : inchangés.
Tout NOUVEAU compte a une date de fin d'essai, quel que soit le mode d'inscription (mot de passe ou
Google). Un compte déjà passé par le paiement (client Stripe connu) dont le forfait n'est plus actif
reçoit le même refus, avec un message qui ne lui parle pas d'essai (motif « forfait »).
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


def essai_actif(user) -> bool:
    """Compte en essai gratuit EN COURS (plan non payant, essai pas encore terminé)."""
    return _plan_key(user) not in ("pro", "business") and _trial_state(user) == "active"


CODE_ESSAI_TERMINE = "essai_termine"
MSG_ESSAI_TERMINE = ("Votre essai gratuit est terminé : les fonctions d'IA sont en pause. Choisissez un "
                     "forfait (Pro ou Business) pour continuer. Vos marchés, documents et dossiers restent "
                     "accessibles.")
# Même pause, pour un compte déjà passé par le paiement (ancien abonné, paiement en échec, paiement
# commencé puis abandonné) : on ne lui parle pas d'un essai.
MSG_SANS_FORFAIT = ("Aucun forfait n'est actif sur votre compte : les fonctions d'IA sont en pause. "
                    "Choisissez un forfait (Pro ou Business) pour continuer. Vos marchés, documents et "
                    "dossiers restent accessibles.")


def essai_termine(user) -> bool:
    """Essai gratuit TERMINÉ sans formule payante : forfait « starter » (seul forfait non payant, même
    règle que budget_ia.est_payant) et date de fin d'essai passée. Faux pour un compte historique sans
    essai (trial_ends_at NULL) et pour tout forfait payant."""
    p = getattr(user, "plan", None)
    plan = p.value if hasattr(p, "value") else str(p or "starter")
    return plan in ("starter", "") and _trial_state(user) == "expired"


def motif_pause_ia(user):
    """Pourquoi les fonctions d'IA sont en pause pour ce compte de facturation, ou None :
      'essai'   → essai gratuit terminé, compte jamais passé par le paiement ;
      'forfait' → même règle (essai_termine), mais le compte est déjà passé par le paiement (client
                  Stripe connu : ancien abonné, paiement en échec, ou paiement commencé puis
                  abandonné). Le refus et l'écran ne lui parlent pas d'un essai."""
    if not essai_termine(user):
        return None
    return "forfait" if getattr(user, "stripe_customer_id", None) else "essai"


def pause_ia(user, db):
    """Motif de la pause de l'IA (voir motif_pause_ia) porté par le compte de facturation
    (propriétaire de l'organisation), ou None. Toujours None pour le compte de démonstration."""
    if _is_demo(user):
        return None
    billing = _billing_user(user, db) if db is not None else user
    if _is_demo(billing):
        return None
    return motif_pause_ia(billing)


def _refus_essai_termine(motif: str = "essai") -> HTTPException:
    msg = MSG_SANS_FORFAIT if motif == "forfait" else MSG_ESSAI_TERMINE
    return HTTPException(status_code=402, detail={"code": CODE_ESSAI_TERMINE, "motif": motif, "message": msg})


def exiger_ia(user, db) -> None:
    """Refus propre (402) AVANT tout appel à l'IA et tout débit quand le compte de facturation
    (propriétaire de l'organisation) a terminé son essai sans formule payante. Sans effet pour tout
    autre compte. Le compte de démonstration garde son propre refus (lecture guidée, 403)."""
    motif = pause_ia(user, db)
    if motif:
        raise _refus_essai_termine(motif)


def trial_analyses_limit() -> int:
    try:
        v = int(getattr(settings, "TRIAL_ANALYSES", 30))
        return v if v >= 0 else 30
    except (TypeError, ValueError):
        return 30


def _trial_used(user) -> int:
    """Analyses consommées pendant l'essai, sur toute sa durée. Le compteur du mois (s'il est bien
    celui du mois en cours) est un minimum : une analyse du mois est toujours une analyse de l'essai."""
    t = int(getattr(user, "trial_analyses_used", 0) or 0)
    m = int(getattr(user, "analyses_used_this_month", 0) or 0) if getattr(user, "analyses_period", "") == _period() else 0
    return max(t, m)


def _limit(user) -> int:
    plan = _plan_key(user)
    if plan in ("pro", "business"):
        return int(settings.PLAN_LIMITS.get(plan, {}).get("analyses", 0))
    # plan 'starter' (ou inconnu) : le quota depend de l'essai gratuit.
    st = _trial_state(user)
    if st == "active":
        return trial_analyses_limit()   # essai : TRIAL_ANALYSES au total, sur toute sa durée
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
    essai = tstate == "active"
    if essai:
        used = _trial_used(user)          # l'essai se compte sur toute sa durée, pas par mois
    out = {
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
        # Fonctions d'IA en pause (essai terminé sans forfait) : 'essai' | 'forfait' | None.
        "ia_pause": None if _is_demo(user) else motif_pause_ia(user),
    }
    if essai:
        # Compteur de l'essai : analyses sur 30 (toute la durée), questions par jour, et l'état de la
        # limite d'usage SANS aucun montant (« ok » | « proche » | « atteint »).
        out["quota_scope"] = "essai"
        out["trial_questions_per_day"] = questions_limit(user, db) if db is not None else _trial_questions()
        try:
            from app.services.budget_ia import etat_essai
            out["trial_usage"] = etat_essai(db, user)
        except Exception:
            out["trial_usage"] = "ok"
    return out


def consume_analysis(user, db: Session, operation: str = "analyse", estimation_eur: float = None) -> None:
    """Vérifie le quota et incrémente, de façon ATOMIQUE (verrou de ligne Postgres :
    ferme la course read-modify-write qui permettait de contourner le quota en lançant
    2 analyses en parallèle). Au-delà du quota : overage si activé, sinon 402.
    Essai gratuit en cours : TRIAL_ANALYSES analyses sur toute la durée de l'essai, et le budget IA
    de l'essai vérifié AVANT l'opération (`operation` et `estimation_eur` : son coût estimé, prudent ;
    app/services/budget_ia.py). Forfaits payants : inchangé."""
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
    # Essai gratuit terminé sans formule payante → blocage net, SANS overage (aucun abonnement pour
    # le facturer), avant tout débit : toutes les fonctions d'IA sont en pause (exiger_ia).
    if essai_termine(locked):
        raise _refus_essai_termine(motif_pause_ia(locked))
    if essai_actif(locked):
        # Essai : analyses comptées sur TOUTE sa durée (un essai à cheval sur deux mois n'en donne
        # pas deux fois plus), jamais de paiement à l'usage (rien à facturer).
        t_used = _trial_used(locked)
        if t_used >= lim:
            raise HTTPException(
                status_code=402,
                detail=f"Quota d'analyses de l'essai gratuit atteint ({t_used} sur {lim}, pour toute la durée "
                       f"de l'essai). Choisissez un forfait (Pro ou Business) pour continuer.",
            )
        from app.services.budget_ia import verifier
        verifier(locked, db, operation, estimation_eur)        # 402 avant tout appel si la limite d'usage est atteinte
        locked.trial_analyses_used = t_used + 1
        locked.analyses_used_this_month = used + 1
        db.commit()
        return
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
                report_overage(locked, db=db)
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
        if essai_actif(locked):
            # Essai : le compteur de toute la durée est rendu, même après un changement de mois.
            t_used = _trial_used(locked)
            locked.trial_analyses_used = max(0, t_used - 1)
            if used > 0:
                locked.analyses_used_this_month = used - 1
            db.commit()
            return
        if used <= 0:
            return
        was_overage = used > _limit(locked) and (locked.overage_count or 0) > 0
        if was_overage:
            locked.overage_count -= 1  # c'était une analyse hors quota facturée
        locked.analyses_used_this_month = used - 1
        db.commit()
        if was_overage:
            # L'unité déjà envoyée à Stripe est annulée (sinon le client paierait une analyse
            # que l'IA n'a pas rendue).
            try:
                from app.services.billing_usage import cancel_overage
                cancel_overage(locked, db=db)
            except Exception as e:      # noqa: BLE001
                import logging
                logging.getLogger("adjugo").warning("Annulation d'usage Stripe échouée (user %s) : %s",
                                                    locked.id, e)
    except Exception as e:
        import logging
        logging.getLogger("adjugo").warning("Remboursement quota échoué (user %s) : %s", getattr(user, "id", "?"), e)


# ── Questions sur un dossier : hors quota d'analyses, bornées par organisation et par jour ──
# Avant, seule l'adresse IP les limitait (90 par heure) : dix membres derrière dix adresses, ou un
# script, pouvaient poser des milliers de questions par jour à la charge d'Adjugo. Chaque question
# réservée laisse une ligne `jobs` (kind « question_dossier », sans le texte de la question) : le
# compte est PERSISTANT (redémarrage compris) et partagé par tous les membres de l'organisation.
QUESTION_KIND = "question_dossier"


def _trial_questions() -> int:
    try:
        v = int(getattr(settings, "TRIAL_QUESTIONS_PAR_JOUR", 15) or 0)
        return v if v > 0 else 15
    except (TypeError, ValueError):
        return 15


def questions_limit(user, db) -> int:
    """Questions par jour pour l'organisation de l'utilisateur (forfait du propriétaire). Essai en
    cours : TRIAL_QUESTIONS_PAR_JOUR (au plus QUESTIONS_PAR_JOUR s'il est réglé)."""
    override = int(getattr(settings, "QUESTIONS_PAR_JOUR", 0) or 0)
    billing = _billing_user(user, db)
    if essai_actif(billing):
        return min(_trial_questions(), override) if override > 0 else _trial_questions()
    if override > 0:
        return override
    plan = _plan_key(billing)
    if plan not in ("pro", "business"):
        plan = "pro" if _trial_state(billing) == "active" else "starter"
    lim = (settings.PLAN_LIMITS.get(plan) or {}).get("questions_jour")
    return int(lim) if lim else 15


def _day_start_utc_naive():
    """Début du jour en cours, heure de Paris, exprimé en UTC sans fuseau (format des dates en base)."""
    from datetime import datetime as _dt, timezone as _tz
    try:
        from zoneinfo import ZoneInfo
        now = _dt.now(ZoneInfo("Europe/Paris"))
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start.astimezone(_tz.utc).replace(tzinfo=None)
    except Exception:
        now = _dt.now(_tz.utc)
        return now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


def questions_today(user, db) -> int:
    from sqlalchemy import func
    from app.models import Job
    from app.core.org import member_ids
    return int(db.query(func.count(Job.id)).filter(
        Job.user_id.in_(member_ids(user, db)), Job.kind == QUESTION_KIND,
        Job.created_at >= _day_start_utc_naive()).scalar() or 0)


def reserve_question(user, db) -> int:
    """Réserve une question pour aujourd'hui ; 429 si l'organisation a atteint sa borne. Renvoie
    l'identifiant de la réservation (à libérer si l'IA ne répond pas)."""
    from datetime import timedelta
    from app.models import Job
    exiger_ia(user, db)          # essai terminé sans forfait : aucune question (402), rien n'est réservé
    lim = questions_limit(user, db)
    if questions_today(user, db) >= lim:
        raise HTTPException(429, f"Limite de questions atteinte pour aujourd'hui ({lim} par organisation et "
                                 f"par jour). Elle repart demain matin.")
    # Essai gratuit : limite d'usage vérifiée avant la question (sans effet pour un forfait payant).
    from app.services.budget_ia import verifier
    verifier(user, db, "question")
    j = Job(user_id=user.id, kind=QUESTION_KIND, status="done", label="Question sur le dossier")
    db.add(j)
    db.commit()
    db.refresh(j)
    # Course entre deux questions simultanées : la réservation de trop est rendue.
    if questions_today(user, db) > lim:
        release_question(db, j.id)
        raise HTTPException(429, f"Limite de questions atteinte pour aujourd'hui ({lim} par organisation et "
                                 f"par jour). Elle repart demain matin.")
    # Ménage : réservations de plus de 7 jours de cette organisation (le compte ne lit que le jour).
    try:
        from app.core.org import member_ids
        old = _day_start_utc_naive() - timedelta(days=7)
        db.query(Job).filter(Job.user_id.in_(member_ids(user, db)), Job.kind == QUESTION_KIND,
                             Job.created_at < old).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
    return j.id


def release_question(db, job_id) -> None:
    """Rend une question réservée (l'IA n'a pas répondu : la question ne compte pas)."""
    if not job_id:
        return
    try:
        from app.models import Job
        db.query(Job).filter(Job.id == job_id, Job.kind == QUESTION_KIND).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
