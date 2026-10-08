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
    "convention_a_signer": "Convention à valider",   # « accord enregistré », pas une signature électronique
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
    convention_status, convention = "", None   # vague 2 : lu depuis groupement_conventions
    conv = None
    try:
        from app.models import GroupementConvention, GroupementSignature
        conv = db.query(GroupementConvention).filter(
            GroupementConvention.project_id == project.id).first()
        convention_status = conv.status if conv else ""
        if conv is not None:
            active = conv.status in ("a_signer", "signee")
            sigs = db.query(GroupementSignature.status).filter(
                GroupementSignature.convention_id == conv.id).all() if active else []
            convention = {
                "id": conv.id, "status": conv.status, "version": conv.version or 0,
                "forme": conv.forme or "",
                "n_signataires": len(sigs),
                "n_accords": sum(1 for (s,) in sigs if s in ("signed", "hors_ligne")),
                "toutes_validees": conv.status == "signee",
                "frozen_at": conv.frozen_at.isoformat() if conv.frozen_at and active else None,
            }
    except Exception:
        convention_status, convention, conv = "", None, None

    status = getattr(project, "status", None)
    status_v = status.value if hasattr(status, "value") else str(status or "")
    decision = getattr(project, "go_decision", None) or ""
    # Composition RETENUE par le mandataire (POST /groupement/retenir) — un plan calculé
    # automatiquement à l'analyse (plan.auto=True) ne vaut pas composition : l'état reste
    # « potentiel » tant que l'utilisateur n'a rien choisi.
    retained = (not plan.get("auto")) and bool(plan.get("members")) and any(
        m.get("kind") != "lead" for m in (plan.get("members") or []) if isinstance(m, dict))

    n = len(invites)
    # Une convention générée peut ne compter que des partenaires « hors ligne » (rattachés
    # sans invitation) : le groupement existe alors même sans invitation active.
    has_members = bool(n) or convention_status in ("a_signer", "signee")
    if status_v in ("envoye", "gagne", "perdu") and has_members:
        state = "depose"
    elif has_members and convention_status == "signee":
        state = "pret_a_deposer"
    elif has_members and convention_status in ("a_signer",):
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
    label = STATE_LABELS.get(state, state)
    pret = None
    if state in ("pret_a_deposer", "depose") and conv is not None:
        pret = _pret_a_deposer(project, db, conv, invites)
        if state == "pret_a_deposer" and pret["pct"] < 100:
            label = "Convention validée — derniers contrôles avant dépôt"
    idx = STATES.index(state)
    return {
        "state": state, "label": label, "index": idx,
        "steps": [{"key": s, "label": STATE_LABELS[s]} for s in STATES],
        # Stepper « 1→5 » (étapes du parcours) — dérivé des 8 états ci-dessus.
        "etape": _etape_of(state), "etapes": _etapes(state),
        "members": members, "n_members": n, "n_submitted": n_submitted, "n_with_price": n_with_price,
        "offer_frozen": offer_frozen,
        "total_offre_ht": offre.get("total_ht") if offer_frozen else None,
        "frozen_at": offre.get("frozen_at") if offer_frozen else None,
        "convention_status": convention_status,
        "convention": convention,
        "pret": pret,
        "warnings": warnings,
    }


# Étapes du parcours (stepper 1→5) : regroupement des 8 états dérivés. L'ordre suit la
# machine à états : la convention (annexe de répartition) a besoin du prix de chaque part,
# donc « Réunir les parts » précède « Monter le groupement » — le brouillon de convention
# (forme, habilitation) peut toutefois être préparé dès l'étape 2.
ETAPES = [
    ("reperer", "Repérer le marché", ["seul", "potentiel"]),
    ("trouver", "Trouver les partenaires", ["composition", "invitation"]),
    ("reunir", "Réunir les parts", ["parts_completes"]),
    ("monter", "Monter le groupement", ["convention_a_signer"]),
    ("deposer", "Déposer", ["pret_a_deposer", "depose"]),
]


def _etape_of(state: str) -> int:
    for i, (_k, _l, states) in enumerate(ETAPES, start=1):
        if state in states:
            return i
    return 1


def _etapes(state: str) -> list:
    cur = _etape_of(state)
    out = []
    for i, (key, label, states) in enumerate(ETAPES, start=1):
        if i < cur or (state == "depose" and i == cur):
            st = "fait"
        elif i == cur:
            st = "en_cours"
        else:
            st = "a_faire"
        out.append({"n": i, "key": key, "label": label, "states": states, "status": st})
    return out


def _pret_a_deposer(project, db: Session, conv, invites: list) -> dict:
    """État 7 « prêt à déposer » : convention validée par tous + attestations de tous les
    membres valides à la date limite (coffre croisé) + formulaires officiels DC1/DC2/ATTRI1
    générés APRÈS la convention. Avertir, pas bloquer : renvoie les manques, ne bloque rien."""
    checks, manques = {}, []
    checks["convention_signee"] = conv.status == "signee"
    if not checks["convention_signee"]:
        manques.append("Convention à faire valider par tous les membres")
    try:
        from app.routers.invites import coffre_croise
        cc = coffre_croise(db, project, invites, viewer_invite_id=None, for_owner=True)
        checks["attestations_ok"] = bool(cc.get("all_complete")) or not invites
        if not checks["attestations_ok"]:
            manques += list(cc.get("alerts") or [])[:5]
    except Exception:
        checks["attestations_ok"] = False
    try:
        from app.models import GeneratedDoc
        since = conv.frozen_at
        if since is not None and since.tzinfo is not None:
            since = since.replace(tzinfo=None)
        ok = True
        for dt in ("dc1", "dc2", "attri1"):
            g = db.query(GeneratedDoc).filter(GeneratedDoc.project_id == project.id,
                                              GeneratedDoc.doc_type == dt).first()
            stamp = (g.updated_at or g.created_at) if g else None
            if stamp is not None and stamp.tzinfo is not None:
                stamp = stamp.replace(tzinfo=None)
            if not g or g.status not in ("pret", "signe") or (since and stamp and stamp < since):
                ok = False
                manques.append(f"Formulaire {dt.upper()} à (re)générer après la convention")
        checks["cerfa_generes"] = ok
    except Exception:
        checks["cerfa_generes"] = False
    pct = round(100 * sum(1 for v in checks.values() if v) / len(checks))
    return {"checks": checks, "pct": pct, "manques": manques}


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
