"""
« Répondre à plusieurs ? » — routes du score de groupement (co-traitance v2, vague 1).

  GET    /api/projects/{id}/groupement/besoins?sirene=1  — ce que le marché exige et que vous
                                                           n'avez pas → qui l'a (preuves datées)
  POST   /api/projects/{id}/groupement/simulate          — « seul 54 % → avec X 81 % » (what-if)
  POST   /api/projects/{id}/groupement/retenir           — retenir une composition (rattache)
  GET    /api/projects/{id}/groupement/state             — étape dérivée + plan retenu
  GET    /api/projects/{id}/groupement/simulations       — historique (≤ 20)
  DELETE /api/projects/{id}/groupement/plan              — revenir au verdict seul

Anti-hallucination : pour un membre 'sirene' le serveur RE-FETCH par SIRET et IGNORE toute
capacité envoyée par le client (CA inconnu = « CA non publié — à demander ») ; 'attached' /
'annuaire' lisent la base, jamais le body ; 'saisi' est étiqueté « déclaré par vous le … ».
Un seul pourcentage : le score de groupement (score_dce réappliqué) ; match_score reste seul.
Avertir, pas bloquer : retirer le plan ne détache aucun partenaire.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.org import data_owner_id, member_ids
from app.core.ratelimit import limiter
from app.core.security import get_current_user
from app.models import Company, GroupementSimulation, Project, User
from app.services import audit
from app.services.groupement_members import groupement_state
from app.services.groupement_verdict import (
    apports_for, ca_label, lead_member, member_from_cotraitant, member_from_profile, member_from_sirene,
    plan_members, pool_for_project, proof_label, scoring_module, verdict_label,
    with_declare_warning,
)
from app.services.profile import company_dict as _company_dict, criteria_dict as _criteria_dict

logger = logging.getLogger("adjugo")
router = APIRouter(prefix="/api/projects/{project_id}/groupement", tags=["Répondre à plusieurs"])

MAX_MEMBERS = 4
KINDS = ("attached", "annuaire", "sirene", "saisi", "reseau")


# ── Helpers ──────────────────────────────────────────────────────────────────────────

def _project(project_id: int, user: User, db: Session) -> Project:
    p = db.query(Project).filter(Project.id == project_id,
                                 Project.user_id.in_(member_ids(user, db)),
                                 Project.deleted_at.is_(None)).first()
    if not p:
        raise HTTPException(404, "Appel d'offres introuvable")
    return p


def _details(project: Project) -> dict:
    a = project.ai_analysis if isinstance(project.ai_analysis, dict) else {}
    d = a.get("details")
    return d if isinstance(d, dict) else {}


def _lead_ctx(user: User, db: Session) -> tuple:
    """(company_data, criteria, lead) du mandataire = profil de l'organisation."""
    company = db.query(Company).filter(Company.user_id == data_owner_id(user, db)).first()
    company_data = _company_dict(company)
    criteria = _criteria_dict(user.id, db)
    return company_data, criteria, lead_member(company_data, criteria)


def _scoring():
    gs = scoring_module()
    if gs is None:
        raise HTTPException(503, "Le calcul de groupement est momentanément indisponible. Réessayez.")
    return gs


def _exigences(details: dict) -> dict:
    keys = ("ca_minimum_requis", "qualifications_requises", "references_requises",
            "effectif_minimum_requis", "capacites_groupement", "forme_groupement",
            "exigences_sources", "exigences_verifiees")
    return {k: details.get(k) for k in keys}


def _caps(gs, member: dict) -> dict:
    """Capacités normalisées (via member_capacities du service pur, repli sur le membre)."""
    try:
        c = gs.member_capacities(member) or {}
    except Exception:
        c = {}
    quals = c.get("qualifications")
    if not isinstance(quals, list):
        quals = member.get("qualifications") if isinstance(member.get("qualifications"), list) else []
    return {"ca_n1": c.get("ca_n1", member.get("ca_n1")),
            "effectif": c.get("effectif", member.get("effectif")),
            "qualifications": quals}


def _candidate(gs, details: dict, lead: dict, criteria: dict, member: dict) -> dict:
    """Un candidat du panneau « Trouver qui l'a » : ce qu'il comblerait SEUL avec le lead."""
    apporte, score_avec, warns = [], None, []
    try:
        res = gs.score_groupement(details, lead, criteria, [lead, member]) or {}
        score_avec = res.get("score_groupement")
        gc = res.get("gaps_combles") or []
        apporte = [g.get("key") if isinstance(g, dict) else g for g in gc]
        apporte = [k for k in apporte if k]
        if not apporte:
            apporte = apports_for(member, res.get("breakdown") or [])
        warns = list(res.get("warnings") or [])
    except Exception as e:
        logger.warning("score candidat %s en échec : %s", member.get("name"), e)
    cl = ca_label(member)
    if cl and member.get("kind") == "sirene":
        warns.append(f"CA de {member.get('name')} non connu — {cl.lower()}")
    out = {
        "kind": member.get("kind"), "id": member.get("id"), "name": member.get("name"),
        "siret": member.get("siret") or "", "city": member.get("city") or "",
        "departement": member.get("departement") or "",
        "specialites": member.get("specialites") or "",
        "capacites": _caps(gs, member),
        "capacites_source": member.get("source"), "as_of": member.get("as_of"),
        "verified": bool(member.get("verified")),
        "apporte": apporte, "score_avec": int(score_avec) if score_avec is not None else None,
        "proof_label": proof_label(member), "ca_label": cl,
        "warnings": warns,
    }
    for k in ("link_id", "invite_id", "role", "lot", "deja_partenaire", "trade", "profile_id", "rang"):
        if k in member:
            out[k] = member[k]
    return out


def _sort(cands: list) -> list:
    return sorted(cands, key=lambda c: (-(c.get("score_avec") or 0), (c.get("name") or "").lower()))


def _state_payload(project: Project, db: Session) -> dict:
    st = groupement_state(project, db)
    st.update({"plan": project.groupement_plan, "score_seul": project.match_score,
               "score_groupement": project.groupement_score, "decision": project.go_decision,
               "decision_label": verdict_label(project.go_decision)})
    return st


def _clean_siret(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


# ── Besoins : ce que le marché exige et que vous n'avez pas → qui l'a ────────────────

@router.get("/besoins")
@limiter.limit("60/hour")
def besoins(request: Request, project_id: int, sirene: int = 0,
            current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _project(project_id, current_user, db)
    gs = _scoring()
    details = _details(project)
    company_data, criteria, lead = _lead_ctx(current_user, db)
    owner = data_owner_id(current_user, db)
    ids = member_ids(current_user, db)

    try:
        gaps = gs.gaps_for(details, lead, criteria) or []
    except Exception as e:
        logger.warning("gaps_for en échec (projet %s) : %s", project.id, e)
        gaps = []
    # Vague 3 : pool « reseau » (profils publiés visibles par moi, si j'ai publié le mien).
    from app.services import partner_network as pn
    net_ctx = pn.searcher_context(db, current_user)
    pool = pool_for_project(db, project, ids, include_sirene=bool(sirene), max_sirene_calls=3,
                            gaps=gaps, lead=lead, criteria=criteria, company_data=company_data,
                            network_ctx=net_ctx)
    candidats = {k: _sort([_candidate(gs, details, lead, criteria, m) for m in pool[k]])
                 for k in ("rattaches", "annuaire", "sirene")}
    # Réseau : l'ORDRE est celui du classement partner_matching (B classe, A calcule le %).
    candidats["reseau"] = [_candidate(gs, details, lead, criteria, m) for m in pool.get("reseau") or []]
    if pool.get("reseau"):
        pn.count_appearances(db, net_ctx["owner_id"], [m.get("_db_id") for m in pool["reseau"]])
    warnings = list(pool.get("warnings") or [])
    if not details:
        warnings.insert(0, "Ce marché n'a pas encore été analysé à partir de son dossier : "
                           "importez le DCE pour connaître ses exigences.")
    if sirene:
        # Journalisé seulement quand des appels externes (SIRENE) sont déclenchés : la lecture
        # simple des besoins s'exécute à chaque ouverture de fiche (bruit inutile au journal).
        audit.record(db, action="groupement.besoins", owner_id=owner, project_id=project.id,
                     actor=f"user:{current_user.id}", actor_kind="owner", target_type="project",
                     target_id=project.id, detail=f"{len(gaps)} manque(s), recherche SIRENE",
                     ip=audit.client_ip(request))
    return {
        "project_id": project.id,
        "score_seul": project.match_score, "decision": project.go_decision,
        "decision_label": verdict_label(project.go_decision),
        "gaps": gaps, "exigences": _exigences(details),
        "candidats": candidats, "warnings": warnings,
        "state": groupement_state(project, db),
    }


# ── Simulation : « seul 54 % → avec X 81 % » ─────────────────────────────────────────

class SimMember(BaseModel):
    kind: str
    id: Optional[int] = None
    profile_id: Optional[str] = None     # kind 'reseau' : identifiant opaque du profil partenaire
    siret: Optional[str] = None
    name: Optional[str] = None
    ca_n1: Optional[float] = None
    effectif: Optional[int] = None
    qualifications: Optional[list] = None
    specialites: Optional[str] = ""
    departement: Optional[str] = ""


class SimulateIn(BaseModel):
    members: list[SimMember] = Field(default_factory=list)
    save: bool = True


def _resolve_member(m: SimMember, db: Session, project: Project, ids: list, user: User = None) -> dict:
    """Résolution CÔTÉ SERVEUR d'un membre : la base pour l'annuaire, le registre pour
    'sirene' (capacités du body IGNORÉES), le profil PUBLIÉ pour 'reseau' (visible par le
    chercheur : réciprocité, masquage, jamais démo), le body seulement pour 'saisi' (étiqueté)."""
    from app.routers.cotraitants import Cotraitant, ProjectCotraitant
    kind = (m.kind or "").strip().lower()
    if kind not in KINDS:
        raise HTTPException(422, f"Type de membre inconnu : {m.kind!r}")
    if kind == "reseau":
        from app.services import partner_network as pn
        if user is None:
            raise HTTPException(422, "Partenaire du réseau introuvable")
        ctx = pn.searcher_context(db, user)
        if not ctx["published"]:
            raise HTTPException(403, {"code": "profil_non_publie",
                                      "message": "Publiez votre profil partenaire pour simuler avec un partenaire du réseau."})
        prof = pn.find_visible(db, ctx, m.profile_id or "")
        if not prof:
            raise HTTPException(404, "Partenaire introuvable dans le réseau.")
        return member_from_profile(prof)
    if kind in ("attached", "annuaire"):
        if not m.id:
            raise HTTPException(422, "Identifiant du partenaire manquant")
        ct = db.query(Cotraitant).filter(Cotraitant.id == m.id, Cotraitant.user_id.in_(ids)).first()
        if not ct:
            raise HTTPException(404, "Partenaire introuvable dans « Mes partenaires »")
        lk = db.query(ProjectCotraitant).filter(ProjectCotraitant.project_id == project.id,
                                                ProjectCotraitant.cotraitant_id == ct.id).first()
        return member_from_cotraitant(ct, "attached" if lk else "annuaire",
                                      invite_id=getattr(lk, "invite_id", None) if lk else None)
    if kind == "sirene":
        siret = _clean_siret(m.siret)
        if len(siret) != 14:
            raise HTTPException(422, "Un SIRET à 14 chiffres est requis pour un membre SIRENE")
        from app.services import registre
        try:
            fiche = registre.lookup_company(siret)
        except Exception as e:
            logger.warning("lookup_company %s : %s", siret, e)
            fiche = None
        if not fiche:
            raise HTTPException(404, "Entreprise introuvable dans SIRENE pour ce SIRET")
        return member_from_sirene(fiche, siret)
    # 'saisi'
    name = (m.name or "").strip()
    if not name:
        raise HTTPException(422, "Nom du partenaire requis pour un membre saisi")
    quals = [str(q).strip() for q in (m.qualifications or []) if str(q).strip()]
    return {
        "kind": "saisi", "id": None, "invite_id": None, "name": name[:255],
        "siret": _clean_siret(m.siret), "ca_n1": m.ca_n1 if m.ca_n1 else None,
        "effectif": m.effectif if m.effectif else None, "qualifications": quals,
        "specialites": (m.specialites or "")[:255], "departement": (m.departement or "")[:3],
        "postal_code": "", "city": "", "references": [],
        "source": "saisi", "as_of": datetime.now(timezone.utc).date().isoformat(), "verified": False,
    }


def _run_simulation(gs, project: Project, lead: dict, criteria: dict, members: list) -> dict:
    details = _details(project)
    try:
        res = gs.score_groupement(details, lead, criteria, [lead] + members) or {}
    except Exception as e:
        logger.warning("score_groupement en échec (projet %s) : %s", project.id, e)
        raise HTTPException(503, "Le calcul de groupement a échoué. Réessayez.")
    warnings = list(res.get("warnings") or [])
    for m in members:
        if m.get("kind") == "sirene" and ca_label(m):
            warnings.append(f"CA de {m.get('name')} non connu (non publié dans SIRENE) — à demander au partenaire")
        elif m.get("kind") == "reseau" and ca_label(m):
            warnings.append(f"CA de {m.get('name')} non affiché sur le réseau Adjugo — à demander au partenaire")
    res["warnings"] = with_declare_warning(members, warnings)
    res["members"] = [lead] + members
    res["decision_label"] = verdict_label(res.get("decision"))
    return res


@router.post("/simulate")
@limiter.limit("60/hour")
def simulate(request: Request, project_id: int, data: SimulateIn,
             current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _project(project_id, current_user, db)
    gs = _scoring()
    if len(data.members) > MAX_MEMBERS:
        raise HTTPException(422, f"Au plus {MAX_MEMBERS} partenaires par simulation")
    if not data.members:
        raise HTTPException(422, "Choisissez au moins un partenaire")
    ids = member_ids(current_user, db)
    owner = data_owner_id(current_user, db)
    _company_data, criteria, lead = _lead_ctx(current_user, db)

    members = [_resolve_member(m, db, project, ids, current_user) for m in data.members]
    res = _run_simulation(gs, project, lead, criteria, members)

    sim_id = None
    if data.save:
        sim = GroupementSimulation(
            project_id=project.id, owner_id=owner, created_by_user_id=current_user.id,
            members=res["members"], score_seul=res.get("score_seul"),
            score_groupement=res.get("score_groupement"), decision=res.get("decision") or "",
            breakdown=res.get("breakdown"), cumul=res.get("cumul"), gaps=res.get("gaps"),
            warnings=res.get("warnings"), retained=False)
        db.add(sim); db.commit(); db.refresh(sim)
        sim_id = sim.id
        audit.record(db, action="groupement.simulate", owner_id=owner, project_id=project.id,
                     actor=current_user.email, actor_kind="owner", target_type="groupement_simulation",
                     target_id=sim.id, ip=audit.client_ip(request),
                     detail=f"seul {res.get('score_seul')} → groupement {res.get('score_groupement')} "
                            f"({res.get('decision')}) avec " + ", ".join(m.get("name") or "?" for m in members)[:150])
    return {**res, "simulation_id": sim_id, "state": groupement_state(project, db)}


# ── Retenir une composition ──────────────────────────────────────────────────────────

class RetenirIn(BaseModel):
    simulation_id: int


def _ensure_cotraitant(db, user: User, ids: list, m: dict):
    """Pour 'sirene'/'saisi' : crée le partenaire dans l'annuaire s'il n'y est pas (par SIRET,
    sinon par nom). Capacités étiquetées 'rne' (registre) ou 'declare' (saisi)."""
    from app.routers.cotraitants import Cotraitant
    ct = None
    siret = m.get("siret") or ""
    if siret:
        ct = db.query(Cotraitant).filter(Cotraitant.user_id.in_(ids), Cotraitant.siret == siret).first()
    # Pas d'appariement par nom (homonymes) : sans SIRET, on crée une fiche distincte.
    if ct:
        return ct
    now = datetime.now(timezone.utc)
    quals = m.get("qualifications")
    ct = Cotraitant(user_id=user.id, name=(m.get("name") or "Partenaire")[:255], siret=siret,
                    code_ape=m.get("code_ape") or "", city=m.get("city") or "",
                    postal_code=m.get("postal_code") or "", departement=m.get("departement") or "",
                    specialites=m.get("specialites") or "",
                    ca_n1=m.get("ca_n1") if m.get("kind") == "saisi" else None,
                    effectif=m.get("effectif") or 0,
                    qualifications=", ".join(quals) if isinstance(quals, list) else (quals or ""),
                    references=[], capacites_source={"sirene": "rne", "reseau": "reseau"}.get(m.get("kind"), "declare"),
                    capacites_updated_at=now)
    db.add(ct); db.flush()
    return ct


@router.post("/retenir")
@limiter.limit("60/hour")
def retenir(request: Request, project_id: int, data: RetenirIn,
            current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.routers.cotraitants import Cotraitant, ProjectCotraitant
    project = _project(project_id, current_user, db)
    gs = _scoring()
    owner = data_owner_id(current_user, db)
    ids = member_ids(current_user, db)
    sim = db.query(GroupementSimulation).filter(
        GroupementSimulation.id == data.simulation_id,
        GroupementSimulation.project_id == project.id,
        GroupementSimulation.owner_id == owner).first()
    if not sim:
        raise HTTPException(404, "Simulation introuvable")

    stored = [m for m in (sim.members or []) if isinstance(m, dict)]
    partners = [m for m in stored if m.get("kind") != "lead"]
    # Recalcul déterministe sur les membres STOCKÉS (mêmes entrées → même résultat ; aucun
    # re-fetch) pour obtenir gaps_combles ; repli sur les valeurs enregistrées.
    _cd, criteria, lead = _lead_ctx(current_user, db)
    try:
        res = gs.score_groupement(_details(project), lead, criteria, [lead] + partners) or {}
    except Exception as e:
        logger.warning("recalcul à la rétention en échec : %s", e)
        res = {}
    breakdown = res.get("breakdown") or sim.breakdown or []
    score_grp = res.get("score_groupement", sim.score_groupement)
    decision = res.get("decision") or sim.decision or ""
    warnings = with_declare_warning(partners, list(res.get("warnings") or sim.warnings or []))

    # 1) Rattacher chaque partenaire (annuaire créé au besoin, pas de doublon de liaison)
    members_out = plan_members(partners, breakdown, res.get("gaps_combles"))
    net_ctx = None
    for m, pm in zip(partners, members_out):
        ct = None
        if m.get("kind") == "reseau":
            # Profil du réseau : encore visible pour moi (publié, non masqué) ? Sinon on ne
            # recopie rien dans l'annuaire (le partenaire a pu retirer sa publication).
            from app.services import partner_network as _pn
            net_ctx = net_ctx or _pn.searcher_context(db, current_user)
            if not (net_ctx["published"] and _pn.find_visible(db, net_ctx, m.get("profile_id") or "")):
                warnings.append(f"{m.get('name')} n'est plus visible dans le réseau Adjugo — non rattaché.")
                continue
        if m.get("kind") in ("attached", "annuaire") and m.get("id"):
            ct = db.query(Cotraitant).filter(Cotraitant.id == m["id"], Cotraitant.user_id.in_(ids)).first()
            if not ct:
                warnings.append(f"{m.get('name')} n'est plus dans « Mes partenaires » — non rattaché.")
        else:
            ct = _ensure_cotraitant(db, current_user, ids, m)
        if ct:
            pm["id"] = ct.id
            exists = db.query(ProjectCotraitant).filter(ProjectCotraitant.project_id == project.id,
                                                        ProjectCotraitant.cotraitant_id == ct.id).first()
            if exists:
                if (exists.role or "sous_traitant") == "sous_traitant":
                    exists.role = "cotraitant"
                pm["link_id"] = exists.id
                pm["invite_id"] = getattr(exists, "invite_id", None)
            else:
                lk = ProjectCotraitant(project_id=project.id, cotraitant_id=ct.id, role="cotraitant",
                                       lot="", source="simulation")
                db.add(lk); db.flush()
                pm["link_id"] = lk.id

    # 2) Plan retenu + score + verdict (match_score inchangé)
    plan = {
        "members": members_out, "breakdown": breakdown,
        "gaps": res.get("gaps") if res else (sim.gaps or []),
        "gaps_combles": res.get("gaps_combles") or [], "warnings": warnings,
        "auto": False, "computed_at": datetime.now(timezone.utc).isoformat(),
        "score_seul": project.match_score if project.match_score is not None else sim.score_seul,
        "score_groupement": score_grp, "simulation_id": sim.id,
    }
    # Une offre figée ne survit pas à un changement de composition : on la défige AVEC trace
    # (offer.unfrozen) au lieu de l'effacer en silence en réécrivant le plan.
    _old_plan = project.groupement_plan if isinstance(project.groupement_plan, dict) else {}
    if isinstance(_old_plan.get("offre"), dict) and _old_plan["offre"].get("frozen_at"):
        from app.routers.invites import _unfreeze_offer_if_needed
        _unfreeze_offer_if_needed(db, project.id, "composition du groupement modifiée",
                                  actor=f"user:{current_user.id}", actor_kind="owner",
                                  ip=audit.client_ip(request))
    project.groupement_plan = plan
    project.groupement_score = int(score_grp) if score_grp is not None else None
    if decision == "go_groupement" and project.go_decision != "go":
        project.go_decision = "go_groupement"

    # 3) Une seule simulation retenue par projet
    db.query(GroupementSimulation).filter(GroupementSimulation.project_id == project.id,
                                          GroupementSimulation.id != sim.id).update(
        {GroupementSimulation.retained: False}, synchronize_session=False)
    sim.retained = True
    db.commit()
    audit.record(db, action="groupement.retenue", owner_id=owner, project_id=project.id,
                 actor=current_user.email, actor_kind="owner", target_type="groupement_simulation",
                 target_id=sim.id, ip=audit.client_ip(request),
                 detail=f"composition retenue ({len(members_out)} partenaire(s)) — "
                        f"groupement {score_grp} ({decision})")
    db.refresh(project)
    return {"ok": True, "plan": plan, "decision": project.go_decision,
            "decision_label": verdict_label(project.go_decision), "state": groupement_state(project, db)}


# ── État, historique, retrait du plan ────────────────────────────────────────────────

@router.get("/state")
@limiter.limit("240/hour")
def state(request: Request, project_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _project(project_id, current_user, db)
    # Vague 2 : une convention dont le texte figé ne correspond plus aux faits passe en
    # « perimee » avant de calculer l'étape (filet de sécurité, en plus des défigements tracés).
    try:
        from app.services.groupement_convention import get_convention, refresh
        refresh(db, project, get_convention(db, project.id))
    except Exception:
        pass
    return _state_payload(project, db)


@router.get("/simulations")
@limiter.limit("240/hour")
def simulations(request: Request, project_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _project(project_id, current_user, db)
    owner = data_owner_id(current_user, db)
    rows = db.query(GroupementSimulation).filter(
        GroupementSimulation.project_id == project.id, GroupementSimulation.owner_id == owner
    ).order_by(GroupementSimulation.created_at.desc(), GroupementSimulation.id.desc()).limit(20).all()
    return [{
        "id": s.id, "created_at": s.created_at.isoformat() if s.created_at else None,
        "members": [{"name": m.get("name"), "kind": m.get("kind")} for m in (s.members or [])
                    if isinstance(m, dict) and m.get("kind") != "lead"],
        "score_seul": s.score_seul, "score_groupement": s.score_groupement,
        "decision": s.decision, "decision_label": verdict_label(s.decision), "retained": bool(s.retained),
    } for s in rows]


@router.delete("/plan")
@limiter.limit("60/hour")
def delete_plan(request: Request, project_id: int,
                current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Revenir au verdict seul. N'enlève AUCUN partenaire rattaché (avertir, pas bloquer)."""
    from app.routers.sourcing import _verdict
    project = _project(project_id, current_user, db)
    owner = data_owner_id(current_user, db)
    # Vague 2 : retirer le plan efface aussi l'offre figée → défigement TRACÉ (offer.unfrozen)
    # et convention de groupement rendue caduque, au lieu d'une disparition silencieuse.
    from app.routers.invites import _unfreeze_offer_if_needed
    _unfreeze_offer_if_needed(db, project.id, "plan de groupement retiré",
                              actor=f"user:{current_user.id}", actor_kind="owner",
                              ip=audit.client_ip(request))
    db.refresh(project)
    project.groupement_plan = None
    project.groupement_score = None
    if project.go_decision == "go_groupement":
        gonogo = _criteria_dict(current_user.id, db)
        project.go_decision = _verdict(project.match_score, gonogo) if project.match_score is not None else None
    db.query(GroupementSimulation).filter(GroupementSimulation.project_id == project.id).update(
        {GroupementSimulation.retained: False}, synchronize_session=False)
    db.commit()
    audit.record(db, action="groupement.plan_retire", owner_id=owner, project_id=project.id,
                 actor=current_user.email, actor_kind="owner", target_type="project",
                 target_id=project.id, ip=audit.client_ip(request),
                 detail="plan de groupement retiré — partenaires rattachés conservés")
    db.refresh(project)
    return {"ok": True, "decision": project.go_decision, "decision_label": verdict_label(project.go_decision),
            "state": _state_payload(project, db)}
