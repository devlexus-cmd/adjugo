"""
Réseau de partenaires Adjugo — routes de la vague 3 (co-traitance v2, innovation B).

  GET    /api/reseau/profil                    — mon profil partenaire (pré-rempli si absent)
  PUT    /api/reseau/profil                    — enregistrer les capacités déclarées (admin)
  DELETE /api/reseau/profil                    — effacer le profil (admin, RGPD)
  POST   /api/reseau/profil/verifier           — vérifier SIRENE / BODACC / DECP (admin)
  POST   /api/reseau/profil/publier            — publier dans le réseau (admin, conditions)
  DELETE /api/reseau/profil/publier            — retirer la publication (admin)
  GET    /api/reseau/annuaire                  — annuaire (réciprocité : profil publié requis)
  GET    /api/reseau/annuaire/{profile_id}     — fiche publique d'un partenaire
  GET    /api/reseau/historique                — COUNT réels, dans les deux sens
  GET    /api/reseau/invitations               — invitations reçues via le réseau
  GET    /api/projects/{id}/partner-matches    — « Qui me complète ? » lot par lot
  POST   /api/projects/{id}/reseau/invitations         — mise en relation en 1 clic (réseau)
  POST   /api/projects/{id}/reseau/invitations-sirene  — entreprise hors réseau : lien à transmettre

Doctrine : un seul pourcentage affiché = le score de groupement (simulation) ; ici un RANG et
des CRITÈRES sourcés et datés. Fiche publique = sous-ensemble strict (jamais email, téléphone,
CA, effectif exact, documents, résultats). L'email d'un partenaire réseau est rempli côté
serveur et MASQUÉ au chef de file tant que le partenaire n'a pas répondu. Un profil ne sait
jamais qui l'a cherché. Aucun profil de démonstration. 0 LLM.
"""
import logging
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.org import data_owner_id, ensure_org, member_ids
from app.core.ratelimit import limiter
from app.core.security import get_current_user
from app.models import (Company, Organization, PartnerProfile, Project, ProjectContribution,
                        ProjectInvite, User, utcnow)
from app.services import audit
from app.services import partner_matching as pm
from app.services import partner_network as pn

logger = logging.getLogger("adjugo")
router = APIRouter(tags=["Réseau de partenaires"])
_settings = get_settings()

_DEMO_MSG = "La démo est en lecture guidée : créez votre compte gratuit pour rejoindre le réseau de partenaires."
_NOT_PUBLISHED = {"code": "profil_non_publie",
                  "message": "Publiez votre profil partenaire pour voir les fiches et inviter les entreprises du réseau."}
_NOT_FOUND = "Partenaire introuvable dans le réseau."
NETWORK_INVITES_PER_PROFILE_DAY = 10     # sollicitations (invitations + relances) d'un même profil / 24 h
_TOO_MANY_FOR_PROFILE = "Ce partenaire a reçu beaucoup d'invitations aujourd'hui : réessayez demain."
MAX_LOTS = 8
MAX_SIRENE_LOTS = 3
DAILY_MATCH_CAP = 200                    # par organisation (en plus du limiter par IP)
DAILY_ANNUAIRE_CAP = 300


# ── Helpers ──────────────────────────────────────────────────────────────────────────

def network_solicitations_24h(db: Session, profile_id: int) -> int:
    """Sollicitations d'un profil du réseau sur 24 h glissantes : invitations créées + relances
    (« invite.resent ») de ses invitations. Même compteur, donc même plafond
    (NETWORK_INVITES_PER_PROFILE_DAY), à l'envoi et à la relance : 9 relances puis 10 envois ne
    font plus 19 emails en un jour."""
    from sqlalchemy import select
    from app.models import AuditLog
    since = utcnow() - timedelta(hours=24)
    n_created = db.query(ProjectInvite).filter(ProjectInvite.partner_profile_id == profile_id,
                                               ProjectInvite.created_at >= since).count()
    ids = select(ProjectInvite.id).where(ProjectInvite.partner_profile_id == profile_id)
    n_resent = db.query(AuditLog).filter(AuditLog.action == "invite.resent", AuditLog.target_type == "invite",
                                         AuditLog.target_id.in_(ids),
                                         AuditLog.created_at >= since.replace(tzinfo=None)).count()
    return n_created + n_resent


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _refuse_demo(user: User) -> None:
    from app.services.demo_search import is_demo
    if is_demo(user):
        raise HTTPException(403, _DEMO_MSG)


def _is_org_admin(user: User, db: Session) -> bool:
    oid = getattr(user, "org_id", None) or ensure_org(user, db)
    org = db.query(Organization).filter(Organization.id == oid).first()
    return bool(org and (org.owner_id == user.id or (user.org_role or "") == "admin"))


def _require_admin(user: User, db: Session) -> None:
    if not _is_org_admin(user, db):
        raise HTTPException(403, "Seul un administrateur de votre organisation peut modifier ou publier "
                                 "le profil partenaire.")


def _company(db: Session, owner_id: int) -> Optional[Company]:
    return db.query(Company).filter(Company.user_id == owner_id).first()


def _split_deps(v) -> list:
    if isinstance(v, (list, tuple)):
        items = v
    else:
        items = re.split(r"[,;\s]+", str(v or ""))
    out = []
    for x in items:
        n = _norm_dep(x)
        if n and n not in out:
            out.append(n)
    return out


def _norm_dep(x) -> str:
    from app.services.groupement_scoring import _norm_dep as nd
    s = str(x or "").strip().upper()
    if not s or not re.fullmatch(r"\d{2,5}|2[AB]", s):
        return ""
    return nd(s)


def _trade_keys() -> set:
    return set(pm.trade_labels().keys())


# Cache in-process des recherches registre pour le pré-remplissage (process unique).
_LOOKUP_CACHE: dict = {}
_LOOKUP_LOCK = threading.Lock()
_LOOKUP_TTL = 600


def _lookup_cached(siret: str) -> Optional[dict]:
    if not siret:
        return None
    now = time.time()
    with _LOOKUP_LOCK:
        hit = _LOOKUP_CACHE.get(siret)
        if hit and now - hit[0] < _LOOKUP_TTL:
            return hit[1]
    try:
        from app.services import registre
        res = registre.lookup_company(siret, timeout=pn.HTTP_TIMEOUT)
    except Exception:
        res = None
    with _LOOKUP_LOCK:
        if len(_LOOKUP_CACHE) > 2000:
            _LOOKUP_CACHE.clear()
        _LOOKUP_CACHE[siret] = (now, res)
    return res


def _prefill(db: Session, user: User, owner_id: int, with_registry: bool = True) -> dict:
    """Valeurs proposées (non enregistrées) : profil entreprise + critères + registre SIRENE
    (lookup_company, délai court, cache 10 min). Rien n'est inventé : champ inconnu = vide."""
    from app.services.dce_scoring import _dept
    from app.services.profile import criteria_dict
    from app.sourcing.groupement import own_trades
    comp = _company(db, owner_id)
    crit = criteria_dict(user.id, db)
    siret = pn.clean_siret(comp.siret if comp else "")
    out = {"name": (comp.name if comp else "") or "", "siret": siret, "siren": siret[:9] if siret else "",
           "postal_code": (comp.postal_code if comp else "") or "", "city": (comp.city if comp else "") or "",
           "metiers": [], "departements": _split_deps(crit.get("departements") or ""),
           "codes_cpv": [c for c in re.split(r"[,;\s]+", str(crit.get("codes_cpv") or "")) if re.fullmatch(r"\d{8}", c)][:pn.MAX_CPV],
           "roles_acceptes": ["cotraitant"], "sources": ["profil entreprise"]}
    keys = _trade_keys()
    try:
        trades = own_trades({**(pn_company_dict(comp)), "specialites": crit.get("specialites") or ""})
        out["metiers"] = sorted(t for t in trades if t in keys)[:pn.MAX_METIERS]
    except Exception:
        pass
    if with_registry and siret:
        fiche = _lookup_cached(siret)
        if fiche:
            out["sources"].append("registre SIRENE")
            out["name"] = out["name"] or (fiche.get("name") or "")
            out["postal_code"] = out["postal_code"] or (fiche.get("postal_code") or "")
            out["city"] = out["city"] or (fiche.get("city") or "")
            if not out["metiers"]:
                try:
                    t = own_trades({"specialites": fiche.get("specialite") or "", "naf_label": fiche.get("naf_label") or ""})
                    out["metiers"] = sorted(x for x in t if x in keys)[:pn.MAX_METIERS]
                except Exception:
                    pass
    out["departement"] = (_dept(out["postal_code"]) or "")[:3] if out["postal_code"] else ""
    if not out["departements"] and out["departement"]:
        out["departements"] = [out["departement"]]
    return out


def pn_company_dict(comp) -> dict:
    from app.services.profile import company_dict
    d = company_dict(comp)
    q = d.get("qualifications")
    if isinstance(q, list):
        d["qualifications"] = " ".join((x.get("name") or "") if isinstance(x, dict) else str(x) for x in q)
    return d


def _company_references(comp) -> list:
    out = []
    for r in (comp.references or []) if comp else []:
        if not isinstance(r, dict):
            continue
        name = str(r.get("name") or r.get("intitule") or "").strip()
        if not name:
            continue
        out.append({"intitule": name[:160], "client": str(r.get("client") or "")[:120],
                    "annee": r.get("year") or r.get("annee")})
    return out[:50]


def _options() -> dict:
    return {
        "metiers": [{"key": k, "label": v} for k, v in pm.trade_labels().items()],
        "roles": [{"value": r, "label": pm.ROLE_LABELS[r]} for r in pn.ROLES],
        "disponibilites": [{"value": d, "label": pm.DISPO_LABELS[d]} for d in pn.DISPONIBILITES],
        "presentation_max": 300,
        "references_max": pn.MAX_REFERENCES,
    }


def _conditions(db: Session, p: Optional[PartnerProfile], siret: str) -> list:
    vs = (p.verified_sirene if p and isinstance(p.verified_sirene, dict) else {}) or {}
    age = pn.verification_age_days(p) if p else None
    other = None
    if p and p.siren:
        other = db.query(PartnerProfile.id).filter(PartnerProfile.siren == p.siren, PartnerProfile.visible.is_(True),
                                                   PartnerProfile.id != p.id).first()
    return [
        {"key": "siret", "label": "SIRET à 14 chiffres renseigné dans le profil entreprise", "ok": bool(siret)},
        {"key": "verification", "label": f"Entreprise vérifiée active dans SIRENE il y a moins de {pn.PUBLISH_MAX_AGE_DAYS} jours",
         "ok": bool(vs.get("etat") == "actif" and age is not None and age < pn.PUBLISH_MAX_AGE_DAYS)},
        {"key": "metiers", "label": "Au moins un métier", "ok": bool(p and p.metiers)},
        {"key": "zones", "label": "Au moins un département d'intervention", "ok": bool(p and p.departements)},
        {"key": "unique", "label": "Aucun autre profil publié pour la même entreprise (SIREN)", "ok": other is None},
    ]


def _status(p: Optional[PartnerProfile]) -> tuple:
    if not p:
        return "aucun", "Pas encore créé"
    if p.visible:
        return "publie", "Publié dans le réseau Adjugo"
    vs = p.verified_sirene if isinstance(p.verified_sirene, dict) else {}
    if p.published_at and vs.get("etat") == "cesse":
        return "retire", "Retiré du réseau : SIRENE indique que l'entreprise a cessé son activité"
    if p.published_at:
        return "retire", "Publication retirée (non visible)"
    return "brouillon", "Brouillon (non visible dans le réseau)"


def _verifs(p: Optional[PartnerProfile]) -> dict:
    vs = p.verified_sirene if p and isinstance(p.verified_sirene, dict) else None
    vb = p.verified_bodacc if p and isinstance(p.verified_bodacc, dict) else None
    vd = p.verified_decp if p and isinstance(p.verified_decp, dict) else None
    return {"sirene": {"label": pm.sirene_label(vs), "etat": (vs or {}).get("etat"), "checked_at": (vs or {}).get("checked_at")},
            "bodacc": {"label": pm.bodacc_label(vb), "found": (vb or {}).get("found"), "checked_at": (vb or {}).get("checked_at")},
            "decp": {"label": pm.decp_label(vd), "count": (vd or {}).get("count"), "checked_at": (vd or {}).get("checked_at")},
            "verified_at": p.verified_at.isoformat() if p and p.verified_at else None,
            "age_jours": pn.verification_age_days(p) if p else None}


def _profile_view(db: Session, user: User, p: Optional[PartnerProfile], owner_id: int, message: str = None) -> dict:
    """Vue PROPRIÉTAIRE de son profil (tout son contenu + aperçu exact de la fiche publique)."""
    pre = None
    if p is None:
        pre = _prefill(db, user, owner_id)
    comp = _company(db, owner_id)
    siret = pn.clean_siret(comp.siret if comp else "")
    statut, statut_label = _status(p)
    if p is not None:
        declared = {"metiers": list(p.metiers or []), "codes_cpv": list(p.codes_cpv or []),
                    "departements": list(p.departements or []), "roles_acceptes": list(p.roles_acceptes or []),
                    "disponibilite": p.disponibilite or "", "dispo_jusqua": p.dispo_jusqua.isoformat() if p.dispo_jusqua else None,
                    "lot_max_eur": p.lot_max_eur, "presentation": p.presentation or "",
                    "references_publiques": list(p.references_publiques or []),
                    "declared_at": p.declared_at.isoformat() if p.declared_at else None}
        ident = {"name": p.name or "", "siren": p.siren or "", "siret": p.siret or "", "city": p.city or "",
                 "postal_code": p.postal_code or "", "departement": p.departement or "",
                 "nom_officiel": bool(isinstance(p.verified_sirene, dict) and p.verified_sirene.get("nom"))}
        card = pm.public_card(pn.profile_dict(p))
    else:
        declared = {"metiers": pre["metiers"], "codes_cpv": pre["codes_cpv"], "departements": pre["departements"],
                    "roles_acceptes": pre["roles_acceptes"], "disponibilite": "", "dispo_jusqua": None,
                    "lot_max_eur": None, "presentation": "", "references_publiques": [], "declared_at": None}
        ident = {"name": pre["name"], "siren": pre["siren"], "siret": pre["siret"], "city": pre["city"],
                 "postal_code": pre["postal_code"], "departement": pre["departement"], "nom_officiel": False}
        card = None
    conds = _conditions(db, p, siret)
    n_app = pn.appearances_this_month(p) if p else 0
    out = {
        "exists": p is not None,
        "profile_id": p.public_id if p else None,
        "visible": bool(p and p.visible),
        "statut": statut, "statut_label": statut_label,
        "identite": ident,
        "declare": declared,
        "hidden_from_sirens": list(p.hidden_from_sirens or []) if p else [],
        "verifications": _verifs(p),
        "badges": pm.badges(pn.profile_dict(p)) if p else [],
        "apercu_fiche": card,
        "publication": {"peut_publier": all(c["ok"] for c in conds) and p is not None, "conditions": conds,
                        "published_at": p.published_at.isoformat() if p and p.published_at else None},
        "apparitions_ce_mois": n_app,
        "apparitions_label": (f"Votre profil est apparu dans {n_app} recherche{'s' if n_app > 1 else ''} ce mois-ci. "
                              "Vous ne savez pas qui a cherché, et personne ne sait qui vous a vu."),
        "groupements_deposes": int(p.groupements_deposes or 0) if p else 0,
        "peut_modifier": _is_org_admin(user, db),
        "options": _options(),
        "references_disponibles": _company_references(comp),
        "prefill_sources": (pre or {}).get("sources") if pre else None,
        "suggestion": pn.suggest_profile(db, user),
    }
    if message:
        out["message"] = message
    return out


# ── Mon profil ───────────────────────────────────────────────────────────────────────

@router.get("/api/reseau/profil")
@limiter.limit("120/hour")
def get_profil(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owner = data_owner_id(current_user, db)
    return _profile_view(db, current_user, pn.own_profile(db, owner), owner)


class ProfilIn(BaseModel):
    metiers: Optional[list] = None
    codes_cpv: Optional[list] = None
    departements: Optional[list] = None
    roles_acceptes: Optional[list] = None
    disponibilite: Optional[str] = None
    dispo_jusqua: Optional[date] = None
    lot_max_eur: Optional[float] = None
    presentation: Optional[str] = None
    references_publiques: Optional[list] = None
    hidden_from_sirens: Optional[list] = None


_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean_text(s, n: int) -> str:
    return _CTRL.sub("", str(s or "")).strip()[:n]


def _sync_identity(db: Session, p: PartnerProfile, owner_id: int, user: User) -> Optional[str]:
    """Le SIRET vient du profil entreprise (source unique). S'il change : vérifications
    remises à zéro et publication retirée (identité à re-vérifier). Renvoie un message."""
    comp = _company(db, owner_id)
    siret = pn.clean_siret(comp.siret if comp else "")
    msg = None
    if (p.siret or "") != siret:
        was_visible = bool(p.visible)
        if p.siret:
            p.verified_sirene = None
            p.verified_bodacc = None
            p.verified_decp = None
            p.verified_at = None
            p.visible = False
            msg = ("Le SIRET de votre profil entreprise a changé : vérifiez à nouveau votre entreprise"
                   + (" avant de republier (publication retirée)." if was_visible else "."))
        p.siret = siret
        p.siren = siret[:9] if siret else ""
    official = isinstance(p.verified_sirene, dict) and bool(p.verified_sirene.get("nom"))
    if not official:      # tant que SIRENE n'a pas donné le nom officiel : nom du profil entreprise
        p.name = ((comp.name if comp else "") or p.name or "")[:255]
    if not p.postal_code and comp and comp.postal_code:
        p.postal_code = comp.postal_code[:10]
    if not p.city and comp and comp.city:
        p.city = comp.city[:120]
    if not p.departement and p.postal_code:
        from app.services.dce_scoring import _dept
        p.departement = (_dept(p.postal_code) or "")[:3]
    return msg


@router.put("/api/reseau/profil")
@limiter.limit("60/hour")
def put_profil(request: Request, body: ProfilIn, current_user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    _refuse_demo(current_user)
    _require_admin(current_user, db)
    owner = data_owner_id(current_user, db)
    fields = body.model_fields_set
    upd = {}
    # ── Validation (messages en français, 422) ──
    if "metiers" in fields:
        keys = _trade_keys()
        vals = [str(m).strip() for m in (body.metiers or []) if str(m).strip()]
        bad = [m for m in vals if m not in keys]
        if bad:
            raise HTTPException(422, f"Métier inconnu : {bad[0][:40]}")
        upd["metiers"] = sorted(set(vals))[:pn.MAX_METIERS]
    if "codes_cpv" in fields:
        vals = [re.sub(r"\D", "", str(c)) for c in (body.codes_cpv or []) if str(c).strip()]
        if any(len(c) != 8 for c in vals):
            raise HTTPException(422, "Un code CPV comporte 8 chiffres (ex. 45310000).")
        upd["codes_cpv"] = sorted(set(vals))[:pn.MAX_CPV]
    if "departements" in fields:
        raw = [str(d).strip() for d in (body.departements or []) if str(d).strip()]
        vals = []
        for d in raw:
            n = _norm_dep(d)
            if not n:
                raise HTTPException(422, "Département invalide : indiquez un numéro (ex. 29, 2A, 974).")
            if n not in vals:
                vals.append(n)
        if len(vals) > pn.MAX_DEPARTEMENTS:
            raise HTTPException(422, f"Au plus {pn.MAX_DEPARTEMENTS} départements.")
        upd["departements"] = vals
    if "roles_acceptes" in fields:
        vals = [str(r).strip() for r in (body.roles_acceptes or []) if str(r).strip()]
        if any(r not in pn.ROLES for r in vals):
            raise HTTPException(422, "Rôle inconnu : cotraitant, sous_traitant ou mandataire.")
        upd["roles_acceptes"] = [r for r in pn.ROLES if r in vals]
    if "disponibilite" in fields:
        v = (body.disponibilite or "").strip()
        if v and v not in pn.DISPONIBILITES:
            raise HTTPException(422, "Disponibilité inconnue : disponible, limitee ou complet.")
        upd["disponibilite"] = v
    if "dispo_jusqua" in fields:
        upd["dispo_jusqua"] = body.dispo_jusqua
    if "lot_max_eur" in fields:
        v = body.lot_max_eur
        if v is not None and not (0 < float(v) <= 1e9):
            raise HTTPException(422, "Taille de lot maximale invalide (montant HT positif).")
        upd["lot_max_eur"] = float(v) if v is not None else None
    if "presentation" in fields:
        v = _clean_text(body.presentation, 1000)
        if len(v) > 300:
            raise HTTPException(422, "Présentation en une phrase : 300 caractères au plus.")
        upd["presentation"] = v
    if "references_publiques" in fields:
        refs = []
        for r in (body.references_publiques or []):
            if not isinstance(r, dict):
                raise HTTPException(422, "Référence invalide.")
            intitule = _clean_text(r.get("intitule"), 160)
            if not intitule:
                raise HTTPException(422, "Chaque référence publique doit avoir un intitulé.")
            annee = r.get("annee")
            if annee not in (None, ""):
                try:
                    annee = int(annee)
                except (TypeError, ValueError):
                    raise HTTPException(422, "Année de référence invalide.")
                if not (1990 <= annee <= _today().year):
                    raise HTTPException(422, "Année de référence invalide.")
            else:
                annee = None
            refs.append({"intitule": intitule, "client": _clean_text(r.get("client"), 120), "annee": annee})
        if len(refs) > pn.MAX_REFERENCES:
            raise HTTPException(422, f"Au plus {pn.MAX_REFERENCES} références publiques.")
        upd["references_publiques"] = refs
    if "hidden_from_sirens" in fields:
        vals = []
        for s in (body.hidden_from_sirens or []):
            sir = pn.clean_siren(s)
            if not sir:
                raise HTTPException(422, "SIREN invalide dans la liste de masquage (9 chiffres, ou SIRET à 14 chiffres).")
            if sir not in vals:
                vals.append(sir)
        if len(vals) > pn.MAX_HIDDEN:
            raise HTTPException(422, f"Au plus {pn.MAX_HIDDEN} entreprises masquées.")
        upd["hidden_from_sirens"] = vals

    p = pn.own_profile(db, owner)
    created = p is None
    if created:
        pre = _prefill(db, current_user, owner)
        p = PartnerProfile(public_id=pn.new_public_id(), user_id=owner, visible=False, is_demo=False,
                           name=pre["name"][:255], siret=pre["siret"], siren=pre["siren"],
                           postal_code=pre["postal_code"][:10], city=pre["city"][:120],
                           departement=pre["departement"], metiers=pre["metiers"], codes_cpv=pre["codes_cpv"],
                           departements=pre["departements"], roles_acceptes=pre["roles_acceptes"],
                           references_publiques=[], hidden_from_sirens=[], appearances_count=0,
                           appearances_period="", groupements_deposes=0, declared_at=pn.utcnow_naive())
        db.add(p)
    msg = _sync_identity(db, p, owner, current_user)
    declared_keys = {"metiers", "codes_cpv", "departements", "roles_acceptes", "disponibilite", "dispo_jusqua",
                     "lot_max_eur", "presentation", "references_publiques"}
    changed = False
    for k, v in upd.items():
        if getattr(p, k) != v:
            setattr(p, k, v)
            if k in declared_keys:
                changed = True
    if changed:
        p.declared_at = pn.utcnow_naive()
    if p.visible and (not p.metiers or not p.departements):
        p.visible = False
        msg = "Un profil publié doit garder au moins un métier et un département : publication retirée."
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(409, "Le profil a été modifié en même temps ailleurs : rechargez la page.")
    db.refresh(p)
    if created:
        audit.record(db, action="network.profile_created", owner_id=owner, actor=f"user:{current_user.id}",
                     actor_kind="owner", target_type="partner_profile", target_id=p.id,
                     ip=audit.client_ip(request))
    return _profile_view(db, current_user, p, owner, message=msg)


@router.delete("/api/reseau/profil")
@limiter.limit("10/hour")
def delete_profil(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Effacement du profil (RGPD) : la fiche disparaît du réseau et l'adresse du compte est
    retirée des invitations réseau déjà envoyées par les chefs de file."""
    _refuse_demo(current_user)
    _require_admin(current_user, db)
    owner = data_owner_id(current_user, db)
    p = pn.own_profile(db, owner)
    if not p:
        raise HTTPException(404, "Aucun profil partenaire à effacer.")
    pid = p.id
    pn.erase_profile(db, p)
    db.commit()
    audit.record(db, action="network.profile_deleted", owner_id=owner, actor=f"user:{current_user.id}",
                 actor_kind="owner", target_type="partner_profile", target_id=pid, ip=audit.client_ip(request))
    return {"ok": True, "message": "Profil partenaire effacé."}


_VERIFY_LAST: dict = {}
_VERIFY_LOCK = threading.Lock()


@router.post("/api/reseau/profil/verifier")
@limiter.limit("10/hour")
def verifier(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Vérifie l'entreprise dans SIRENE, BODACC et DECP (3 appels en parallèle, 5 s chacun,
    budget 8 s). Formulations honnêtes et datées ; une erreur réseau = « non vérifié »."""
    _refuse_demo(current_user)
    _require_admin(current_user, db)
    owner = data_owner_id(current_user, db)
    p = pn.own_profile(db, owner)
    if not p:
        raise HTTPException(404, "Créez d'abord votre profil partenaire (enregistrez-le une première fois).")
    msg = _sync_identity(db, p, owner, current_user)
    db.commit()
    if not p.siret:
        raise HTTPException(422, {"code": "siret_invalide",
                                  "message": "Renseignez un SIRET à 14 chiffres dans votre profil entreprise avant la vérification."})
    now_ts = time.time()
    with _VERIFY_LOCK:
        last = _VERIFY_LAST.get(p.id)
        if last and now_ts - last < pn.VERIFY_COOLDOWN_S:
            wait_min = int((pn.VERIFY_COOLDOWN_S - (now_ts - last)) // 60) + 1
            raise HTTPException(429, f"Vérification déjà lancée il y a moins de 10 minutes : réessayez dans {wait_min} min.")
        _VERIFY_LAST[p.id] = now_ts
        if len(_VERIFY_LAST) > 20000:
            _VERIFY_LAST.clear()
    now = pn.utcnow_naive()
    res = pn.run_checks(p.siren, now)
    summary = pn.apply_checks(p, res, now)
    pn.recompute_groupements(db, p)
    if (res.get("sirene") or {}).get("statut") == "ok" and (res["sirene"].get("etat") == "cesse") and p.visible:
        p.visible = False
        msg = "SIRENE indique que l'entreprise a cessé son activité : publication retirée."
    db.commit()
    db.refresh(p)
    audit.record(db, action="network.profile_verified", owner_id=owner, actor=f"user:{current_user.id}",
                 actor_kind="owner", target_type="partner_profile", target_id=p.id,
                 detail=" · ".join(f"{k}:{v.get('statut')}" for k, v in summary.items())[:255],
                 ip=audit.client_ip(request))
    out = _profile_view(db, current_user, p, owner, message=msg)
    out["verification"] = summary
    return out


class PublierIn(BaseModel):
    accepte: bool = False


@router.post("/api/reseau/profil/publier")
@limiter.limit("20/hour")
def publier(request: Request, body: PublierIn = None, current_user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    _refuse_demo(current_user)
    _require_admin(current_user, db)
    owner = data_owner_id(current_user, db)
    p = pn.own_profile(db, owner)
    if not p:
        raise HTTPException(404, "Créez d'abord votre profil partenaire.")
    if not (body and body.accepte):
        raise HTTPException(422, {"code": "consentement_requis",
                                  "message": "Cochez « J'accepte que la fiche ci-dessus soit visible des entreprises "
                                             "qui ont publié la leur » pour publier."})
    _sync_identity(db, p, owner, current_user)
    db.commit()
    if not re.fullmatch(r"\d{14}", p.siret or ""):
        raise HTTPException(422, {"code": "siret_invalide",
                                  "message": "Un SIRET à 14 chiffres est requis (profil entreprise)."})
    vs = p.verified_sirene if isinstance(p.verified_sirene, dict) else {}
    if vs.get("etat") == "cesse":
        raise HTTPException(409, {"code": "entreprise_inactive",
                                  "message": "SIRENE indique que l'entreprise a cessé son activité : publication impossible."})
    age = pn.verification_age_days(p)
    if vs.get("etat") != "actif" or age is None or age >= pn.PUBLISH_MAX_AGE_DAYS:
        raise HTTPException(409, {"code": "verification_requise",
                                  "message": f"Vérifiez votre entreprise (vérification de moins de {pn.PUBLISH_MAX_AGE_DAYS} jours) "
                                             "avant de publier."})
    missing = []
    if not p.metiers:
        missing.append("Au moins un métier")
    if not p.departements:
        missing.append("Au moins un département d'intervention")
    if missing:
        raise HTTPException(422, {"code": "profil_incomplet", "message": "Profil incomplet.", "missing": missing})
    other = db.query(PartnerProfile.id).filter(PartnerProfile.siren == p.siren, PartnerProfile.visible.is_(True),
                                               PartnerProfile.id != p.id).first()
    if other:
        raise HTTPException(409, {"code": "siren_deja_publie",
                                  "message": "Un profil est déjà publié pour cette entreprise (même SIREN). "
                                             "Contactez-nous si ce n'est pas vous."})
    p.visible = True
    p.is_demo = False
    p.published_at = pn.utcnow_naive()
    db.commit()
    db.refresh(p)
    audit.record(db, action="network.profile_published", owner_id=owner, actor=f"user:{current_user.id}",
                 actor_kind="owner", target_type="partner_profile", target_id=p.id, ip=audit.client_ip(request))
    return _profile_view(db, current_user, p, owner, message="Profil publié dans le réseau Adjugo.")


@router.delete("/api/reseau/profil/publier")
@limiter.limit("20/hour")
def depublier(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _refuse_demo(current_user)
    _require_admin(current_user, db)
    owner = data_owner_id(current_user, db)
    p = pn.own_profile(db, owner)
    if not p:
        raise HTTPException(404, "Aucun profil partenaire.")
    p.visible = False
    db.commit()
    db.refresh(p)
    audit.record(db, action="network.profile_unpublished", owner_id=owner, actor=f"user:{current_user.id}",
                 actor_kind="owner", target_type="partner_profile", target_id=p.id,
                 detail="publication retirée par l'entreprise", ip=audit.client_ip(request))
    return _profile_view(db, current_user, p, owner,
                         message="Publication retirée : votre fiche n'apparaît plus dans le réseau.")


# ── Annuaire (réciprocité) ───────────────────────────────────────────────────────────

def _teaser(n: int, scope: str = "cette recherche") -> str:
    if n <= 0:
        return f"Aucun partenaire du réseau Adjugo ne correspond encore à {scope}."
    if n == 1:
        return "Publiez votre profil pour voir le partenaire correspondant."
    return f"Publiez votre profil pour voir les {n} partenaires correspondants."


def _my_sirets(db: Session, ids: list) -> set:
    from app.routers.cotraitants import Cotraitant
    return {(r[0] or "")[:9] for r in db.query(Cotraitant.siret).filter(Cotraitant.user_id.in_(ids or [0])).all() if r[0]}


@router.get("/api/reseau/annuaire")
@limiter.limit("60/hour")
def annuaire(request: Request, metier: str = "", departement: str = "", role: str = "", cpv: str = "",
             q: str = "", page: int = 1, par_page: int = 20,
             current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ctx = pn.searcher_context(db, current_user)
    if not pn.owner_quota_ok(ctx["owner_id"], "annuaire", DAILY_ANNUAIRE_CAP):
        raise HTTPException(429, "Limite quotidienne de recherches dans l'annuaire atteinte : réessayez demain.")
    metier = (metier or "").strip()
    if metier and metier not in _trade_keys():
        raise HTTPException(422, "Métier inconnu.")
    dep = _norm_dep(departement) if departement else ""
    if departement and not dep:
        raise HTTPException(422, "Département invalide.")
    if role and role not in pn.ROLES:
        raise HTTPException(422, "Rôle inconnu.")
    cpv_list = [c for c in re.split(r"[,;\s]+", cpv or "") if re.fullmatch(r"\d{8}", c)]
    page = max(1, min(int(page or 1), 500))
    par_page = max(1, min(int(par_page or 20), 50))
    today = _today()
    profiles = pn.visible_profiles(db, ctx)
    dicts = [pn.profile_dict(p) for p in profiles]
    by_pid = {d["public_id"]: (p, d) for p, d in zip(profiles, dicts)}

    def _keep(d) -> bool:
        if role and d["roles_acceptes"] and role not in d["roles_acceptes"]:
            return False
        if dep:
            zones = _split_deps(d["departements"])
            if dep not in zones and _norm_dep(d["departement"]) != dep:
                return False
        if q and pm._fold(q) not in pm._fold(d["name"]):
            return False
        return True

    dicts = [d for d in dicts if _keep(d)]
    ranked = None
    if metier or cpv_list:
        lot = {"metier": metier, "departement": dep, "cpv": cpv_list, "role": role or "cotraitant"}
        ranked = pm.rank(lot, dicts, today, limit=len(dicts))
        total = len(ranked)
    else:
        dicts.sort(key=lambda d: (pm._fold(d["name"]), d["public_id"]))
        total = len(dicts)
    base = {"filtres": {"metier": metier, "departement": dep, "role": role, "cpv": cpv_list, "q": q[:80]},
            "explication": pm.EXPLICATION_CLASSEMENT}
    if not ctx["published"]:
        return {**base, "visible": False, "total": total, "message": _teaser(total), "profils": [],
                "page": page, "par_page": par_page}
    start = (page - 1) * par_page
    known = _my_sirets(db, ctx["member_ids"])
    out = []
    if ranked is not None:
        for r in ranked[start:start + par_page]:
            p, d = by_pid[r["profile_id"]]
            card = pm.public_card(d)
            card.update({"rang": r["rang"], "criteres": r["criteres"], "deja_partenaire": (p.siren or "") in known})
            out.append((p, card))
    else:
        for d in dicts[start:start + par_page]:
            p, _d = by_pid[d["public_id"]]
            card = pm.public_card(d)
            card["deja_partenaire"] = (p.siren or "") in known
            out.append((p, card))
    pn.count_appearances(db, ctx["owner_id"], [p.id for p, _c in out])
    audit.record(db, action="network.annuaire_query", owner_id=ctx["owner_id"], actor=f"user:{current_user.id}",
                 actor_kind="owner", target_type="reseau", detail=f"{total} résultat(s)"[:255],
                 meta={"metier": metier, "departement": dep}, ip=audit.client_ip(request))
    return {**base, "visible": True, "total": total, "page": page, "par_page": par_page,
            "profils": [c for _p, c in out]}


@router.get("/api/reseau/annuaire/{profile_id}")
@limiter.limit("120/hour")
def fiche(request: Request, profile_id: str, current_user: User = Depends(get_current_user),
          db: Session = Depends(get_db)):
    ctx = pn.searcher_context(db, current_user)
    if not ctx["published"]:
        raise HTTPException(403, _NOT_PUBLISHED)
    p = pn.find_visible(db, ctx, profile_id)
    if not p:
        raise HTTPException(404, _NOT_FOUND)
    card = pm.public_card(pn.profile_dict(p))
    card["deja_partenaire"] = (p.siren or "") in _my_sirets(db, ctx["member_ids"])
    card["historique_avec_vous"] = pn.historique_avec(db, ctx["member_ids"], ctx["profile"], p)
    audit.record(db, action="network.profile_view", owner_id=ctx["owner_id"], actor=f"user:{current_user.id}",
                 actor_kind="owner", target_type="reseau", detail=(p.name or "")[:255], ip=audit.client_ip(request))
    return card


# ── Historique réel (COUNT, dans les deux sens) ──────────────────────────────────────

@router.get("/api/reseau/historique")
@limiter.limit("60/hour")
def historique(request: Request, profile_id: str = "", current_user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    ctx = pn.searcher_context(db, current_user)
    prof = ctx["profile"]
    org = pn.org_member_ids(db, ctx["owner_id"])
    out = pn.historique(db, org, prof)
    if prof is not None:
        pn.recompute_groupements(db, prof)
        db.commit()
    out.update({
        "groupements_deposes": (int(prof.groupements_deposes or 0) if prof
                                else pn.count_groupements(db, org, None)[0]),
        "source": ("Comptes réels sur Adjugo : invitations actives, parts soumises et statut du marché "
                   "(envoyé, gagné, perdu) renseigné par le chef de file."),
        "avertissement": ("Compteur en construction : un marché n'est compté comme déposé que si le chef de file "
                          "a mis à jour son statut dans Adjugo."),
        "avec": None,
    })
    if profile_id:
        if not ctx["published"]:
            raise HTTPException(403, _NOT_PUBLISHED)
        other = pn.find_visible(db, ctx, profile_id)
        if not other:
            raise HTTPException(404, _NOT_FOUND)
        out["avec"] = {"partenaire": other.name or "", **pn.historique_avec(db, ctx["member_ids"], prof, other)}
    return out


# ── Invitations reçues via le réseau (côté partenaire) ───────────────────────────────

@router.get("/api/reseau/invitations")
@limiter.limit("120/hour")
def invitations_recues(request: Request, current_user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """Invitations reçues PAR MON PROFIL via le réseau : visibles dans l'application même si
    l'email n'est pas arrivé. Accepter = « Rattacher à mon compte » (claim du lien)."""
    from app.routers.cotraitants import ProjectCotraitant
    from app.routers.invites import _is_expired
    from app.services.groupement_members import active_invite_filter
    ctx = pn.searcher_context(db, current_user)
    prof = ctx["profile"]
    if not prof:
        return {"invitations": [], "suggestion": pn.suggest_profile(db, current_user)}
    rows = db.query(ProjectInvite).filter(ProjectInvite.partner_profile_id == prof.id,
                                          ProjectInvite.source == pn.NETWORK_SOURCE,
                                          active_invite_filter()).order_by(ProjectInvite.created_at.desc()).limit(100).all()
    out = []
    for inv in rows:
        if _is_expired(inv.expires_at):
            continue
        project = db.query(Project).filter(Project.id == inv.project_id, Project.deleted_at.is_(None)).first()
        if not project:
            continue
        chef = db.query(Company).filter(Company.user_id == inv.owner_id).first()
        lk = db.query(ProjectCotraitant).filter(ProjectCotraitant.invite_id == inv.id).first()
        out.append({
            "token": inv.token, "path": f"/invite/{inv.token}",
            "project": project.name, "mandataire": (chef.name if chef else "") or "",
            "role": inv.role or "cotraitant", "lot_propose": (lk.lot if lk else "") or "",
            "deadline": project.deadline.isoformat() if project.deadline else None,
            "recue_le": inv.created_at.isoformat() if inv.created_at else None,
            "statut": "acceptee" if inv.accepted_by_user_id else "a_repondre",
            "statut_label": "Acceptée" if inv.accepted_by_user_id else "À accepter ou décliner",
        })
    return {"invitations": out}


# ── « Qui me complète ? » : partenaires par lot ──────────────────────────────────────

def _project(project_id: int, user: User, db: Session) -> Project:
    p = db.query(Project).filter(Project.id == project_id, Project.user_id.in_(member_ids(user, db)),
                                 Project.deleted_at.is_(None)).first()
    if not p:
        raise HTTPException(404, "Projet introuvable")
    return p


def lots_to_complete(details: dict, company_data: dict, criteria: dict, lead: dict) -> tuple:
    """(lots à compléter, lots couverts, lots non reconnus, département d'exécution).
    Déterministe : allotissement du DCE → métier par mots-clés ; marché non alloti → métiers
    des manques (gaps_for). Montant d'un lot = inconnu (jamais une répartition inventée)."""
    from app.services.groupement_verdict import _execution_dept, scoring_module
    from app.sourcing.groupement import infer_trade, own_trades, parse_lots
    labels = pm.trade_labels()
    mine = own_trades({**pn_company_dict_from(company_data), "specialites": (criteria or {}).get("specialites", "")})
    dept = _execution_dept(details, criteria or {}, company_data or {})
    lots = parse_lots(str((details or {}).get("allotissement") or ""))
    todo, covered, unknown = [], [], []
    for lot in lots:
        k = infer_trade(lot["label"])
        item = {"num": lot["num"], "label": lot["label"], "metier": k or "", "metier_label": labels.get(k, "") if k else ""}
        if k and k in mine:
            covered.append(item)
        elif k:
            todo.append({**item, "departement": dept, "montant": None, "role": "cotraitant", "cpv": []})
        else:
            unknown.append(item)
    if not lots:
        gs = scoring_module()
        trades = []
        if gs is not None:
            try:
                for g in gs.gaps_for(details or {}, lead, criteria or {}) or []:
                    for t in (g.get("trades") or []) if isinstance(g, dict) else []:
                        if t and t not in trades and t not in mine:
                            trades.append(t)
            except Exception:
                trades = []
        for t in sorted(trades):
            todo.append({"num": None, "label": f"Compétence « {labels.get(t, t)} »", "metier": t,
                         "metier_label": labels.get(t, t), "departement": dept, "montant": None,
                         "role": "cotraitant", "cpv": []})
    return todo, covered, unknown, dept


def pn_company_dict_from(company_data: dict) -> dict:
    d = dict(company_data or {})
    q = d.get("qualifications")
    if isinstance(q, list):
        d["qualifications"] = " ".join((x.get("name") or "") if isinstance(x, dict) else str(x) for x in q)
    return d


def _sirene_fallback(trade: str, dept: str, warnings: list) -> list:
    """Repli registre SIRENE (cache in-process 10 min par (métier, département) dans
    groupement_verdict._discover_sirene ; procédures collectives et personnes physiques exclues)."""
    from app.services.groupement_verdict import _discover_sirene
    return _discover_sirene(trade, dept, warnings)


def _active_invite_sirens(db: Session, project_id: int) -> tuple:
    """(profils réseau déjà invités, SIREN déjà invités) sur ce marché — invitations ACTIVES."""
    from app.routers.cotraitants import Cotraitant, ProjectCotraitant
    from app.routers.invites import _is_expired
    from app.services.groupement_members import active_invites
    invs = [i for i in active_invites(db, project_id) if not _is_expired(i.expires_at)]
    prof_ids = {i.partner_profile_id for i in invs if i.partner_profile_id}
    ids = [i.id for i in invs]
    sirens = set()
    if ids:
        for c in db.query(ProjectContribution).filter(ProjectContribution.invite_id.in_(ids)).all():
            s = pn.clean_siren(c.siret)
            if s:
                sirens.add(s)
        for lk in db.query(ProjectCotraitant).filter(ProjectCotraitant.project_id == project_id,
                                                     ProjectCotraitant.invite_id.in_(ids)).all():
            ct = db.query(Cotraitant).filter(Cotraitant.id == lk.cotraitant_id).first()
            s = pn.clean_siren(ct.siret if ct else "")
            if s:
                sirens.add(s)
        if prof_ids:
            for p in db.query(PartnerProfile).filter(PartnerProfile.id.in_(list(prof_ids))).all():
                if p.siren:
                    sirens.add(p.siren)
    return prof_ids, sirens


@router.get("/api/projects/{project_id}/partner-matches")
@limiter.limit("60/hour")
def partner_matches(request: Request, project_id: int, lot: str = "",
                    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.groupement_verdict import lead_member
    from app.services.profile import company_dict, criteria_dict
    project = _project(project_id, current_user, db)
    ctx = pn.searcher_context(db, current_user)
    if not pn.owner_quota_ok(ctx["owner_id"], "matches", DAILY_MATCH_CAP):
        raise HTTPException(429, "Limite quotidienne de recherches de partenaires atteinte : réessayez demain.")
    details = (project.ai_analysis or {}).get("details") if isinstance(project.ai_analysis, dict) else None
    details = details if isinstance(details, dict) else {}
    comp = _company(db, ctx["owner_id"])
    company_data = company_dict(comp)
    criteria = criteria_dict(current_user.id, db)
    lead = lead_member(company_data, criteria)
    todo, covered, unknown, dept = lots_to_complete(details, company_data, criteria, lead)
    warnings = []
    if not details:
        warnings.append("Ce marché n'a pas encore été analysé à partir de son dossier : importez le DCE pour "
                        "connaître ses lots.")
    if lot:
        todo = [l for l in todo if str(l.get("num") or "") == str(lot)]
        if not todo:
            raise HTTPException(404, "Lot introuvable parmi les lots à compléter.")
    if len(todo) > MAX_LOTS:
        warnings.append(f"Seuls les {MAX_LOTS} premiers lots à compléter sont affichés.")
        todo = todo[:MAX_LOTS]

    today = _today()
    profiles = pn.visible_profiles(db, ctx)
    dicts = [pn.profile_dict(p) for p in profiles]
    by_pid = {d["public_id"]: (p, d) for p, d in zip(profiles, dicts)}
    network_sirens = {p.siren for p in profiles if p.siren}
    invited_profiles, invited_sirens = _active_invite_sirens(db, project.id)
    known = _my_sirets(db, ctx["member_ids"])
    matched_ids, shown = set(), set()
    sirene_calls, out_lots = 0, []
    for l in todo:
        lot_in = {"metier": l["metier"], "departement": l["departement"], "montant": l["montant"],
                  "cpv": l.get("cpv") or [], "role": l.get("role") or "cotraitant"}
        ranked_all = pm.rank(lot_in, dicts, today, limit=len(dicts))
        matched_ids |= {r["profile_id"] for r in ranked_all}
        entry = {"num": l["num"], "label": l["label"], "metier": l["metier"], "metier_label": l["metier_label"],
                 "departement": l["departement"] or None, "n_correspondants": len(ranked_all),
                 "reseau": [], "sirene": [], "sirene_cherche": False}
        if ctx["published"]:
            for r in ranked_all[:5]:
                p, d = by_pid[r["profile_id"]]
                card = pm.public_card(d)
                card.update({"rang": r["rang"], "criteres": r["criteres"],
                             "deja_invite": p.id in invited_profiles or (p.siren or "") in invited_sirens,
                             "deja_partenaire": (p.siren or "") in known,
                             "simulation": {"kind": "reseau", "profile_id": p.public_id}})
                entry["reseau"].append(card)
                shown.add(p.id)
        else:
            entry["message"] = _teaser(len(ranked_all), "ce lot")
        if len(entry["reseau"]) < 3 and l["metier"]:
            if sirene_calls < MAX_SIRENE_LOTS:
                sirene_calls += 1
                entry["sirene_cherche"] = True
                for m in _sirene_fallback(l["metier"], l["departement"] or "", warnings):
                    s = pn.clean_siren(m.get("siret"))
                    if not s or s in network_sirens or s == ctx["siren"]:
                        continue
                    badges = [{"key": "sirene", "label": f"Entreprise active (SIRENE au {pm.jjmm(m.get('as_of'))})",
                               "source": pm._SOURCE_SIRENE, "date": m.get("as_of"), "niveau": "ok"}]
                    if any("RGE" in str(q) for q in (m.get("qualifications") or [])):
                        badges.append({"key": "rge", "label": f"Inscrite au registre RGE (ADEME) au {pm.jjmm(m.get('as_of'))} — domaine à vérifier",
                                       "source": pm._SOURCE_RGE, "date": m.get("as_of"), "niveau": "info"})
                    entry["sirene"].append({
                        "name": m.get("name") or "", "siret": m.get("siret") or "", "siren": s,
                        "city": m.get("city") or "", "departement": m.get("departement") or "",
                        "activite": m.get("specialites") or "", "badges": badges,
                        "statut_reseau": "Hors réseau Adjugo — à inviter par lien",
                        "deja_invite": s in invited_sirens, "deja_partenaire": s in known,
                        "simulation": {"kind": "sirene", "siret": m.get("siret") or ""},
                    })
            else:
                entry["sirene_message"] = (f"Recherche dans le registre SIRENE limitée à {MAX_SIRENE_LOTS} lots par "
                                           f"requête : affichez ce lot seul pour la lancer.")
        out_lots.append(entry)

    n_total = len(matched_ids)
    if ctx["published"] and shown:
        pn.count_appearances(db, ctx["owner_id"], shown)
    audit.record(db, action="network.match_query", owner_id=ctx["owner_id"], project_id=project.id,
                 actor=f"user:{current_user.id}", actor_kind="owner", target_type="project", target_id=project.id,
                 detail=f"{len(out_lots)} lot(s), {len(shown)} profil(s) du réseau affiché(s), "
                        f"{sum(len(e['sirene']) for e in out_lots)} entreprise(s) SIRENE"[:255],
                 ip=audit.client_ip(request))
    return {
        "project_id": project.id,
        "reseau_visible": ctx["published"],
        "message": None if ctx["published"] else _teaser(n_total, "ces lots"),
        "n_correspondants": n_total,
        "lots": out_lots,
        "lots_couverts": covered,
        "lots_non_reconnus": unknown,
        "explication": pm.EXPLICATION_CLASSEMENT,
        "warnings": warnings,
    }


# ── Mise en relation en 1 clic ───────────────────────────────────────────────────────

class ReseauInviteIn(BaseModel):
    profile_id: str
    role: str = "cotraitant"
    lot: str = ""
    can_view_docs: bool = True
    expires_days: int = 30


class SireneInviteIn(BaseModel):
    siret: str
    role: str = "cotraitant"
    lot: str = ""
    can_view_docs: bool = True
    expires_days: int = 30


def _network_mailer(lot: str, chef: str):
    """Email d'invitation RÉSEAU (envoyé par Adjugo : le chef de file ne voit jamais l'adresse).
    Contenu minimal (objet, lot, chef de file, lien) + comment ne plus être sollicité."""
    def _send(inv, project, base_url: str) -> bool:
        from app.routers.invites import _is_email
        if not _is_email(inv.recipient):
            return False
        try:
            from app.services import email as _email
            url = base_url.rstrip("/") + f"/invite/{inv.token}"
            lot_txt = f", pour la part « {lot} »" if lot else ""
            subj = f"Une entreprise vous propose un groupement — {project.name[:60]}"
            text = (f"Bonjour,\n\n{chef or 'Une entreprise'} a trouvé votre profil sur le réseau Adjugo et vous "
                    f"propose de rejoindre son groupement pour répondre au marché « {project.name} »{lot_txt}.\n\n"
                    f"Ouvrez l'invitation (vous pourrez l'accepter ou la décliner) :\n{url}\n\n"
                    f"Votre adresse n'est pas communiquée au chef de file tant que vous n'avez pas accepté.\n"
                    f"Vous recevez ce message parce que le profil partenaire de votre entreprise est publié sur "
                    f"Adjugo. Vous pouvez retirer cette publication à tout moment depuis Réseau > Mon profil "
                    f"partenaire.\n\n— Adjugo, le réseau des PME")
            sent = _email.send_email(inv.recipient, subj, text)
            if sent:
                inv.emailed_at = utcnow()
            return sent
        except Exception:
            return False
    return _send


def _role(role: str) -> str:
    r = (role or "cotraitant").strip()
    if r not in ("cotraitant", "sous_traitant"):
        raise HTTPException(422, "Rôle invalide : cotraitant ou sous_traitant.")
    return r


def _attach_annuaire(db: Session, user: User, project: Project, inv: ProjectInvite, *, name: str, siret: str,
                     city: str, postal_code: str, departement: str, code_ape: str, specialites: str,
                     qualifications: str, caps_source: str, caps_date, link_source: str, lot: str, role: str) -> dict:
    """Rattachement à l'annuaire « Mes partenaires » (par SIRET au niveau organisation, jamais
    par nom) + liaison au marché portant l'invitation. Aucun email/téléphone n'y est copié."""
    from app.routers.cotraitants import Cotraitant, ProjectCotraitant
    ids = member_ids(user, db)
    ct = None
    if siret:
        ct = db.query(Cotraitant).filter(Cotraitant.user_id.in_(ids), Cotraitant.siret == siret).first()
    if ct is None:
        ct = Cotraitant(user_id=user.id, name=(name or "Partenaire")[:255], siret=siret or "", code_ape=code_ape or "",
                        city=city or "", postal_code=postal_code or "", departement=departement or "",
                        specialites=specialites or "", qualifications=qualifications or "", ca_n1=None, effectif=0,
                        references=[], capacites_source=caps_source, capacites_updated_at=caps_date)
        db.add(ct)
        db.flush()
    lk = db.query(ProjectCotraitant).filter(ProjectCotraitant.project_id == project.id,
                                            ProjectCotraitant.cotraitant_id == ct.id).first()
    if lk is None:
        lk = ProjectCotraitant(project_id=project.id, cotraitant_id=ct.id, role=role, lot=(lot or "")[:255],
                               source=link_source, invite_id=inv.id)
        db.add(lk)
    else:
        lk.invite_id = inv.id
        if (lk.role or "sous_traitant") == "sous_traitant" and role == "cotraitant":
            lk.role = role
        if lot and not lk.lot:
            lk.lot = lot[:255]
    db.commit()
    return {"cotraitant_id": ct.id, "link_id": lk.id}


def _network_invite_view(inv: ProjectInvite, db: Session) -> dict:
    from app.routers.invites import _serialize_invite
    c = db.query(ProjectContribution).filter(ProjectContribution.invite_id == inv.id).first()
    return _serialize_invite(inv, c, db=db)


@router.post("/api/projects/{project_id}/reseau/invitations")
@limiter.limit("30/hour")
def invite_reseau(request: Request, project_id: int, body: ReseauInviteIn,
                  current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Mise en relation en 1 clic avec un profil du réseau : Adjugo remplit l'adresse côté
    serveur et l'envoie ; le chef de file ne la voit qu'une fois que le partenaire a répondu."""
    from app.routers.invites import _check_daily_invite_cap, _create_invite, _refuse_demo_sender
    _refuse_demo_sender(current_user)
    # Expéditeur confirmé (même règle anti-spam que les emails d'invitation) : ici pas de repli
    # « copiez le lien », le lien d'une invitation réseau n'est jamais remis au chef de file.
    if not getattr(current_user, "email_verified", False):
        raise HTTPException(403, "Confirmez d'abord votre adresse email (lien reçu à l'inscription) pour "
                                 "inviter un partenaire du réseau.")
    project = _project(project_id, current_user, db)
    ctx = pn.searcher_context(db, current_user)
    if not ctx["published"]:
        raise HTTPException(403, _NOT_PUBLISHED)
    p = pn.find_visible(db, ctx, body.profile_id)
    if not p:
        raise HTTPException(404, _NOT_FOUND)
    role = _role(body.role)
    if p.roles_acceptes and role not in (p.roles_acceptes or []):
        raise HTTPException(422, f"Ce partenaire n'accepte pas le rôle « {pm.ROLE_LABELS.get(role, role)} ».")
    invited_profiles, invited_sirens = _active_invite_sirens(db, project.id)
    if p.id in invited_profiles or (p.siren and p.siren in invited_sirens):
        raise HTTPException(409, {"code": "deja_invite",
                                  "message": "Ce partenaire a déjà une invitation active sur ce marché."})
    recipient = pn.network_recipient(db, p)
    if not recipient:
        raise HTTPException(409, {"code": "injoignable",
                                  "message": "Ce partenaire ne peut pas être contacté pour le moment."})
    _check_daily_invite_cap(current_user, db)
    if network_solicitations_24h(db, p.id) >= NETWORK_INVITES_PER_PROFILE_DAY:   # relances comprises
        raise HTTPException(429, _TOO_MANY_FOR_PROFILE)
    chef = _company(db, ctx["owner_id"])
    lot = (body.lot or "").strip()[:255]
    inv, emailed = _create_invite(
        db, project, current_user, request, recipient=recipient, company_name=(p.name or "")[:255], role=role,
        can_view_docs=bool(body.can_view_docs), can_contribute=True, expires_days=body.expires_days,
        source=pn.NETWORK_SOURCE, partner_profile_id=p.id,
        mailer=_network_mailer(lot, (chef.name if chef else "") or ""))
    labels = pm.trade_labels()
    quals = []
    vs = p.verified_sirene if isinstance(p.verified_sirene, dict) else {}
    if vs.get("est_rge") is True:
        quals.append("RGE (registre ADEME)")
    if vs.get("est_qualiopi") is True:
        quals.append("Qualiopi (registre)")
    attach = _attach_annuaire(db, current_user, project, inv, name=p.name or "", siret=p.siret or "", city=p.city or "",
                              postal_code=p.postal_code or "", departement=p.departement or "",
                              code_ape=str(vs.get("naf") or "").replace(".", ""),
                              specialites=", ".join(labels.get(m, m) for m in (p.metiers or [])),
                              qualifications=", ".join(quals), caps_source="reseau", caps_date=p.declared_at,
                              link_source=pn.NETWORK_SOURCE, lot=lot, role=role)
    audit.record(db, action="network.invite_sent", owner_id=ctx["owner_id"], project_id=project.id,
                 actor=f"user:{current_user.id}", actor_kind="owner", target_type="invite", target_id=inv.id,
                 detail=(p.name or "")[:255], ip=audit.client_ip(request))
    return {
        "invitation": _network_invite_view(inv, db),
        "emailed": bool(emailed),
        "annuaire": attach,
        "message": ("Invitation envoyée par Adjugo. L'adresse du partenaire vous sera visible quand il aura "
                    "accepté ; il retrouve aussi l'invitation dans son espace Adjugo.") if emailed else
                   ("Invitation créée : le partenaire la retrouve dans son espace Adjugo (Réseau > Invitations "
                    "reçues). L'email n'a pas pu partir pour le moment."),
    }


@router.post("/api/projects/{project_id}/reseau/invitations-sirene")
@limiter.limit("30/hour")
def invite_sirene(request: Request, project_id: int, body: SireneInviteIn,
                  current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Entreprise HORS réseau trouvée dans SIRENE : identité re-vérifiée côté serveur, lien à
    transmettre par le chef de file (Adjugo ne connaît pas son adresse et n'envoie rien)."""
    from app.routers.invites import _check_daily_invite_cap, _create_invite, _refuse_demo_sender
    _refuse_demo_sender(current_user)
    project = _project(project_id, current_user, db)
    siret = pn.clean_siret(body.siret)
    if not siret:
        raise HTTPException(422, "Un SIRET à 14 chiffres est requis.")
    role = _role(body.role)
    ctx = pn.searcher_context(db, current_user)
    if ctx["siren"] and siret[:9] == ctx["siren"]:
        raise HTTPException(422, "C'est votre propre entreprise.")
    if ctx["published"]:
        # Visible pour moi dans le réseau → la mise en relation passe par Adjugo (adresse masquée).
        for p in pn.visible_profiles(db, ctx):
            if p.siren == siret[:9]:
                raise HTTPException(409, {"code": "sur_le_reseau", "profile_id": p.public_id,
                                          "message": "Cette entreprise est sur le réseau Adjugo : invitez-la depuis sa "
                                                     "fiche (Adjugo lui transmet l'invitation)."})
    _invited_profiles, invited_sirens = _active_invite_sirens(db, project.id)
    if siret[:9] in invited_sirens:
        raise HTTPException(409, {"code": "deja_invite",
                                  "message": "Cette entreprise a déjà une invitation active sur ce marché."})
    s = pn.fetch_sirene(siret[:9])
    if s.get("statut") == "erreur":
        raise HTTPException(503, "Le registre SIRENE est momentanément indisponible : réessayez dans un instant.")
    if s.get("statut") != "ok":
        raise HTTPException(404, "Entreprise introuvable dans SIRENE pour ce SIRET.")
    if s.get("etat") != "actif":
        raise HTTPException(422, "Cette entreprise n'est pas active selon SIRENE : invitation impossible.")
    _check_daily_invite_cap(current_user, db)
    lot = (body.lot or "").strip()[:255]
    inv, _emailed = _create_invite(db, project, current_user, request, recipient="",
                                   company_name=(s.get("nom") or "Entreprise")[:255], role=role,
                                   can_view_docs=bool(body.can_view_docs), can_contribute=True,
                                   expires_days=body.expires_days, source="sirene")
    from app.services.dce_scoring import _dept
    attach = _attach_annuaire(db, current_user, project, inv, name=s.get("nom") or "", siret=siret,
                              city=s.get("ville") or "", postal_code=s.get("code_postal") or "",
                              departement=(_dept(s.get("code_postal") or "") or "")[:3],
                              code_ape=str(s.get("naf") or "").replace(".", ""), specialites="",
                              qualifications="RGE (registre ADEME)" if s.get("est_rge") is True else "",
                              caps_source="rne", caps_date=pn.utcnow_naive(), link_source="discover", lot=lot, role=role)
    out = _network_invite_view(inv, db)
    out["url"] = str(request.base_url).rstrip("/") + out["path"]
    return {"invitation": out, "emailed": False, "annuaire": attach, "url": out["url"],
            "message": "Lien créé : transmettez-le à l'entreprise (Adjugo ne connaît pas son adresse et n'envoie rien)."}
