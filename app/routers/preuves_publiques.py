"""
Routes « Retrouver mes marchés publics » et « Retrouver mes qualifications RGE » (rédaction, vague 5, E2).

Dans « Mes preuves » (portée : l'organisation, SIRET du profil de l'entreprise) :
  GET  /api/preuves/publiques/marches        marchés DECP où l'entreprise est titulaire 1, 2 ou 3 (proposés)
  GET  /api/preuves/publiques/rge            qualifications RGE valables (proposées) et expirées (signalées)
  POST /api/preuves/publiques                {cles: [...]} → crée les fiches cochées

Dans la part d'un partenaire du groupement (SA donnée, jamais celle du chef de file) :
  GET  /api/invite/{token}/contribution/publiques/marches   avec le SIRET de sa part
  GET  /api/invite/{token}/contribution/publiques/rge
  POST /api/invite/{token}/contribution/reprendre           {publiques: [...], version} (lien)
  GET  /api/invite/{token}/contribution/preuves             SES preuves utilisables (compte qui a rattaché le lien)
  POST /api/invite/{token}/contribution/reprendre-preuves   {preuves: [...], publiques: [...], version} (compte)

Aucune IA. Les lectures du réseau sont des GET vers des API publiques ouvertes (DECP, data.ademe.fr,
annuaire des entreprises), en cache ; la démo (compte et lien de la vitrine) reçoit un exemple fictif et
n'écrit rien. Contrat : docs/REDACTION_V5.md, section E2.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.demo_guard import refuser_demo
from app.core.org import data_owner_id, member_ids
from app.core.ratelimit import limiter
from app.core.security import get_current_user
from app.models import ProjectContribution, User
from app.services import audit
from app.services import preuves as pv
from app.services import preuves_publiques as ppub

router = APIRouter(tags=["Mes preuves"])

MSG_RATTACHER = ("Rattachez d'abord ce lien à votre compte Adjugo (« Ouvrir dans mon Adjugo ») pour reprendre vos "
                 "preuves dans votre part.")
MSG_ORGANISATION_CHEF = ("Ce compte fait partie de l'organisation du chef de file : ses preuves ne vont pas dans la "
                         "part d'un partenaire.")


def _sortie(r: dict) -> dict:
    """Ce que l'écran reçoit : sans le relevé interne (il est relu à l'enregistrement)."""
    out = dict(r)
    for k in ("marches", "qualifications"):
        if isinstance(out.get(k), list):
            out[k] = [{kk: vv for kk, vv in x.items() if kk != "releve"} for x in out[k]]
    return out


# ── « Mes preuves » ───────────────────────────────────────────────────────────────────

@router.get("/api/preuves/publiques/marches")
@limiter.limit("30/minute")
def marches(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Les marchés publics de l'entreprise (DECP), PROPOSÉS : rien n'est enregistré."""
    return _sortie(ppub.apercu_marches(db, data_owner_id(current_user, db), current_user))


@router.get("/api/preuves/publiques/rge")
@limiter.limit("30/minute")
def rge(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Les qualifications RGE de l'entreprise (liste de l'ADEME), PROPOSÉES ; les expirées sont signalées."""
    return _sortie(ppub.apercu_rge(db, data_owner_id(current_user, db), current_user))


class ImportIn(BaseModel):
    cles: List[str] = Field(default_factory=list, max_length=300)


@router.post("/api/preuves/publiques")
@limiter.limit("60/hour")
def importer(request: Request, body: ImportIn, current_user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    """Crée les fiches COCHÉES (acceptées, source publique datée). Le contenu est relu ici."""
    refuser_demo(current_user, "renseigner vos preuves")
    owner = data_owner_id(current_user, db)
    try:
        r = ppub.importer(db, owner, body.cles, user=current_user)
    except pv.PreuveError as e:
        db.rollback()
        raise HTTPException(e.status, e.detail())
    if not r["creees"] and not r["deja"] and r["pannes"]:
        raise HTTPException(503, {"code": "source_indisponible", "message": " ".join(r["pannes"])})
    etat = pv._Etat(db, owner, r["creees"])
    jour = pv.aujourd_hui()
    return {"creees": [pv.preuve_out(db, p, etat, jour) for p in r["creees"]], "deja": r["deja"],
            "ignorees": r["ignorees"], "pannes": r["pannes"]}


# ── La part d'un partenaire du groupement ─────────────────────────────────────────────

def _part(token: str, db: Session):
    from app.routers.invites import _get_or_create_contribution, _valid_invite
    inv = _valid_invite(token, db)
    if not getattr(inv, "can_contribute", True):
        raise HTTPException(403, "La co-construction n'est pas activée pour ce lien")
    return inv, _get_or_create_contribution(inv, db)


def _demo(inv, db: Session) -> bool:
    from app.routers.invites import _invite_is_demo
    return _invite_is_demo(inv, db)


@router.get("/api/invite/{token}/contribution/publiques/marches")
@limiter.limit("30/minute")
def part_marches(token: str, request: Request, db: Session = Depends(get_db)):
    """Les marchés publics lus avec le SIRET de la part du partenaire (proposés, rien n'est enregistré)."""
    inv, c = _part(token, db)
    return _sortie(ppub.apercu_part(db, inv, c, "decp", demo=_demo(inv, db)))


@router.get("/api/invite/{token}/contribution/publiques/rge")
@limiter.limit("30/minute")
def part_rge(token: str, request: Request, db: Session = Depends(get_db)):
    inv, c = _part(token, db)
    return _sortie(ppub.apercu_part(db, inv, c, "rge", demo=_demo(inv, db)))


def _owner_partenaire(inv, user: User, db: Session) -> int:
    """L'organisation du PARTENAIRE (compte qui a rattaché le lien), jamais celle du chef de file."""
    if not inv.accepted_by_user_id or inv.accepted_by_user_id != user.id:
        raise HTTPException(403, MSG_RATTACHER)
    owner = data_owner_id(user, db)
    chef = set(pv.membres(db, inv.owner_id)) | {inv.owner_id}
    if owner in chef or set(member_ids(user, db)) & chef:
        raise HTTPException(403, MSG_ORGANISATION_CHEF)
    return owner


@router.get("/api/invite/{token}/contribution/preuves")
@limiter.limit("60/minute")
def part_preuves(token: str, request: Request, current_user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """SES références et qualifications utilisables, à reprendre dans sa part (compte seulement)."""
    inv, c = _part(token, db)
    owner = _owner_partenaire(inv, current_user, db)
    return {"preuves": ppub.preuves_du_partenaire(db, owner, c)}


class RepriseIn(BaseModel):
    publiques: List[str] = Field(default_factory=list, max_length=300)
    version: Optional[int] = None


class ReprisePreuvesIn(RepriseIn):
    preuves: List[int] = Field(default_factory=list, max_length=300)


def _reprendre(inv, c, request: Request, db: Session, *, version, publiques, preuves=(), owner=None) -> dict:
    """Même verrou de version que l'enregistrement de la part ; une part soumise repasse en brouillon
    (comme toute modification), l'offre figée et la convention suivent la même règle."""
    from app.routers.invites import (_guest_actor, _serialize_contribution, _sync_annuaire_capacites,
                                     _unfreeze_offer_if_needed)
    if version is None:
        raise HTTPException(428, "Version requise (verrou optimiste). Rechargez la contribution.")
    # Lecture des sources publiques AVANT de réserver la version : aucun appel réseau pendant que la ligne
    # de la part est verrouillée (la lecture reste en cache pour la suite).
    ppub.prechauffer(c.siret or "", publiques)
    expected = int(version)
    claimed = db.query(ProjectContribution).filter(
        ProjectContribution.id == c.id, ProjectContribution.version == expected,
    ).update({ProjectContribution.version: expected + 1}, synchronize_session="fetch")
    if not claimed:
        db.rollback()
        raise HTTPException(409, "Cette contribution a été modifiée ailleurs entre-temps. "
                                 "Rechargez pour récupérer la dernière version avant de réenregistrer.")
    r = ppub.reprendre_dans_part(db, c, publiques=publiques, preuves=preuves, owner_partenaire=owner,
                                 siret=c.siret or "", demo=False)
    resume = {"ajoutees": {"references": r["references"], "qualifications": r["qualifications"]},
              "deja": r["deja"], "ignorees": r["ignorees"], "pannes": r["pannes"]}
    if not (r["references"] or r["qualifications"]):
        db.rollback()
        db.refresh(c)
        if r["pannes"] and not r["deja"]:
            raise HTTPException(503, {"code": "source_indisponible", "message": " ".join(r["pannes"])})
        return dict(resume, contribution=_serialize_contribution(c, db))
    was_submitted = c.status == "submitted"
    if was_submitted:
        c.status = "draft"
        c.submitted_at = None
    db.commit()
    db.refresh(c)
    if was_submitted:
        _unfreeze_offer_if_needed(db, inv.project_id, c.company_name or inv.company_name or "un partenaire",
                                  actor=_guest_actor(inv), actor_kind="guest",
                                  ip=audit.client_ip(request), invite_id=inv.id)
    if r["qualifications"]:
        _sync_annuaire_capacites(inv, c, db)
    morceaux = []
    if r["references"]:
        n = len(r["references"])
        morceaux.append(f"{n} référence{'s' if n > 1 else ''}")
    if r["qualifications"]:
        n = len(r["qualifications"])
        morceaux.append(f"{n} qualification{'s' if n > 1 else ''}")
    origine = {"decp": "marchés publics (DECP)", "rge": "liste RGE de l'ADEME", "preuves": "« Mes preuves »"}
    n = len(r["references"]) + len(r["qualifications"])
    detail = (" et ".join(morceaux) + (" reprises (" if n > 1 else " reprise (")
              + ", ".join(origine[x] for x in r["provenances"]) + ")")
    audit.record(db, action="guest.contribution_reprise", owner_id=inv.owner_id, project_id=inv.project_id,
                 actor=_guest_actor(inv), actor_kind="guest", target_type="contribution", target_id=c.id,
                 invite_id=inv.id, detail=detail[:255], ip=audit.client_ip(request))
    return dict(resume, contribution=_serialize_contribution(c, db))


@router.post("/api/invite/{token}/contribution/reprendre")
@limiter.limit("60/hour")
def part_reprendre(token: str, body: RepriseIn, request: Request, db: Session = Depends(get_db)):
    """Ajoute à SA part les marchés publics et qualifications RGE cochés (lus avec le SIRET de sa part)."""
    from app.routers.invites import _refuse_if_demo_invite
    inv, c = _part(token, db)
    _refuse_if_demo_invite(inv, db)
    return _reprendre(inv, c, request, db, version=body.version, publiques=body.publiques)


@router.post("/api/invite/{token}/contribution/reprendre-preuves")
@limiter.limit("60/hour")
def part_reprendre_preuves(token: str, body: ReprisePreuvesIn, request: Request,
                           current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Ajoute à SA part ses preuves cochées (et, s'il le veut, ses marchés publics) : compte seulement."""
    from app.routers.invites import _refuse_if_demo_invite
    inv, c = _part(token, db)
    _refuse_if_demo_invite(inv, db)
    refuser_demo(current_user, "co-construire une réponse")
    owner = _owner_partenaire(inv, current_user, db)
    return _reprendre(inv, c, request, db, version=body.version, publiques=body.publiques, preuves=body.preuves,
                      owner=owner)
