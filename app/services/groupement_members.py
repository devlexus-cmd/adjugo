"""
Adjugo — Membres et ÉTAT d'un groupement (co-traitance v2, source de vérité unique).

Avant cette vague, QUATRE notions de « membre » coexistaient (annuaire Cotraitant,
rattachement ProjectCotraitant, invitation ProjectInvite + contribution, profil réseau) et
13 requêtes filtraient `revoked` à la main : un partenaire qui DÉCLINE restait compté dans
la checklist, le cockpit, les CERFA… Ici, UNE définition :

    membre du groupement = invitation ACTIVE (revoked = false ET declined_at IS NULL)
                           + le mandataire (owner du projet)

Un ProjectCotraitant SANS invite_id est un CANDIDAT retenu (annuaire / SIRENE / simulation),
pas un membre. TOUT le code (checklist, cockpit, my_consortiums, cerfa, redaction, report,
export, convention, signatures) doit passer par `active_invites` / `active_invite_filter`.

L'ÉTAT du groupement n'est jamais stocké : `groupement_state()` le DÉRIVE des faits
(verdict, simulation retenue, invitations, parts, prix de lot, offre figée, convention,
dépôt). Rien à resynchroniser, impossible d'être incohérent.
"""
from typing import Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models import Project, ProjectContribution, ProjectInvite


# ── Membres ──────────────────────────────────────────────────────────────────────────

def is_active_invite(inv) -> bool:
    """Une invitation compte comme membre si elle n'est ni révoquée ni déclinée."""
    return bool(inv) and not bool(getattr(inv, "revoked", False)) \
        and getattr(inv, "declined_at", None) is None


def active_invite_filter():
    """Condition SQLAlchemy réutilisable dans toute requête sur ProjectInvite
    (équivalent de l'ancien `ProjectInvite.revoked.is_(False)`, déclin inclus)."""
    return and_(ProjectInvite.revoked.is_(False), ProjectInvite.declined_at.is_(None))


def active_invites(db: Session, project_id: int) -> list:
    """Invitations ACTIVES d'un projet, dans l'ordre de création (= les membres)."""
    return db.query(ProjectInvite).filter(
        ProjectInvite.project_id == project_id, active_invite_filter()
    ).order_by(ProjectInvite.created_at.asc()).all()


def active_invite_ids(db: Session, project_id: int) -> list:
    return [i.id for i in active_invites(db, project_id)]


def submitted_contributions(db: Session, project_id: int) -> list:
    """Parts SOUMISES des membres ACTIFS uniquement (jamais celles d'un partenaire révoqué
    ou qui a décliné) — base du mémoire fusionné, des CERFA, du ZIP, de la convention."""
    return db.query(ProjectContribution).join(
        ProjectInvite, ProjectContribution.invite_id == ProjectInvite.id).filter(
        ProjectContribution.project_id == project_id,
        ProjectContribution.status == "submitted",
        active_invite_filter()).all()


# ── État du groupement (dérivé) ───────────────────────────────────────────────────────
# Étapes, dans l'ordre du parcours « Répondre à plusieurs » :
STATES = ["seul", "potentiel", "composition", "invitation", "parts_completes",
          "convention_a_signer", "pret_a_deposer", "depose"]

STATE_LABELS = {
    "seul": "Analysé seul",
    "potentiel": "Bon potentiel en groupement",
    "composition": "Composition retenue",
    "invitation": "Partenaires invités",
    "parts_completes": "Toutes les parts reçues",
    "convention_a_signer": "Convention à signer",
    "pret_a_deposer": "Prêt à déposer",
    "depose": "Déposé",
}


def _plan(project) -> dict:
    p = getattr(project, "groupement_plan", None)
    return p if isinstance(p, dict) else {}


def groupement_state(project: Project, db: Session) -> dict:
    """Dérive l'étape courante du groupement et les compteurs utiles au stepper.

    Renvoie {state, label, index, members:[{invite_id, company, status, prix_lot_ht?}],
             n_members, n_submitted, n_with_price, offer_frozen, total_offre_ht,
             convention_status, warnings:[]}.
    - `members` : invitations actives (membres), avec le statut de leur part ;
      prix_lot_ht n'est inclus que si `include_prices=True` (vue mandataire) — ici on
      renvoie seulement un booléen `has_price` pour rester sûr par défaut.
    """
    plan = _plan(project)
    invites = active_invites(db, project.id)
    contribs = {c.invite_id: c for c in db.query(ProjectContribution).filter(
        ProjectContribution.project_id == project.id).all()}

    members, n_submitted, n_with_price = [], 0, 0
    for inv in invites:
        c = contribs.get(inv.id)
        submitted = bool(c and c.status == "submitted")
        has_price = bool(c and c.prix_lot_ht is not None)
        n_submitted += int(submitted)
        n_with_price += int(submitted and has_price)
        members.append({
            "invite_id": inv.id,
            "company": (c.company_name if c and c.company_name else inv.company_name) or "Partenaire",
            "role": inv.role or "cotraitant",
            "status": "submitted" if submitted else ("draft" if c else "invited"),
            "has_price": has_price,
            "viewed": bool(inv.view_count),
        })

    offre = plan.get("offre") if isinstance(plan.get("offre"), dict) else {}
    offer_frozen = bool(offre.get("frozen_at"))
    convention_status = ""   # vague 2 : lu depuis groupement_conventions
    try:
        from app.models import GroupementConvention  # type: ignore  (vague 2)
        conv = db.query(GroupementConvention).filter(
            GroupementConvention.project_id == project.id).first()
        convention_status = conv.status if conv else ""
    except Exception:
        convention_status = ""

    status = getattr(project, "status", None)
    status_v = status.value if hasattr(status, "value") else str(status or "")
    decision = getattr(project, "go_decision", None) or ""
    # Composition RETENUE par le mandataire (POST /groupement/retenir) — un plan calculé
    # automatiquement à l'analyse (plan.auto=True) ne vaut pas composition : l'état reste
    # « potentiel » tant que l'utilisateur n'a rien choisi.
    retained = (not plan.get("auto")) and bool(plan.get("members")) and any(
        m.get("kind") != "lead" for m in (plan.get("members") or []) if isinstance(m, dict))

    n = len(invites)
    if status_v in ("envoye", "gagne", "perdu") and n:
        state = "depose"
    elif n and convention_status == "signee":
        state = "pret_a_deposer"
    elif n and convention_status in ("a_signer",):
        state = "convention_a_signer"
    elif n and n_submitted == n and n_with_price == n:
        state = "parts_completes"
    elif n:
        state = "invitation"
    elif retained:
        state = "composition"
    elif decision == "go_groupement" or plan.get("gaps"):
        state = "potentiel"
    else:
        state = "seul"

    warnings = list(plan.get("warnings") or []) if isinstance(plan.get("warnings"), list) else []
    return {
        "state": state, "label": STATE_LABELS.get(state, state), "index": STATES.index(state),
        "steps": [{"key": s, "label": STATE_LABELS[s]} for s in STATES],
        "members": members, "n_members": n, "n_submitted": n_submitted, "n_with_price": n_with_price,
        "offer_frozen": offer_frozen,
        "total_offre_ht": offre.get("total_ht") if offer_frozen else None,
        "frozen_at": offre.get("frozen_at") if offer_frozen else None,
        "convention_status": convention_status,
        "warnings": warnings,
    }


def total_offre_ht(project: Project, db: Session, lead_total: Optional[float] = None) -> Optional[float]:
    """Total de l'offre commune = prix de lot de chaque membre (part soumise) + part du
    mandataire (estimate.total_ht ou valeur fournie). None si un membre n'a pas de prix."""
    parts = []
    for c in submitted_contributions(db, project.id):
        if c.prix_lot_ht is None:
            return None
        parts.append(float(c.prix_lot_ht))
    if lead_total is None:
        est = project.estimate if isinstance(project.estimate, dict) else {}
        try:
            lead_total = float(est.get("total_ht")) if est.get("total_ht") is not None else None
        except (TypeError, ValueError):
            lead_total = None
    if lead_total is not None:
        parts.append(float(lead_total))
    return round(sum(parts), 2) if parts else None
