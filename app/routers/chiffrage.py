"""
Adjugo — Chiffrage estimatif d'une réponse à un appel d'offres.

POST .../estimate : l'IA propose un découpage en tâches + jours, le prix est calculé.
PUT  ...           : recalcul DÉTERMINISTE après ajustement manuel (jours/profil/distance),
                     sans nouvel appel IA.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.ratelimit import limiter
from app.core.security import get_current_user
from app.models import Company, Project, User
from app.services.agents.chiffrage import DEFAULT_RATES, compute_estimate, propose_tasks

router = APIRouter(prefix="/api/chiffrage", tags=["Chiffrage"])


def _project(pid: int, user: User, db: Session) -> Project:
    p = db.query(Project).filter(Project.id == pid, Project.user_id == user.id).first()
    if not p:
        raise HTTPException(404, "Projet introuvable")
    return p


def _rates(user: User, db: Session):
    c = db.query(Company).filter(Company.user_id == user.id).first()
    rates = (c.day_rates if c and c.day_rates else None) or DEFAULT_RATES
    th = c.distance_threshold_km if (c and c.distance_threshold_km is not None) else 50
    su = c.distance_surcharge_pct if (c and c.distance_surcharge_pct is not None) else 0
    return rates, th, su


class EstimateRequest(BaseModel):
    distance_km: float = 0


class SaveRequest(BaseModel):
    lignes: list = []
    distance_km: float = 0


@router.get("/{project_id}")
def get_estimate(project_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _project(project_id, current_user, db).estimate or {}


@router.post("/{project_id}/estimate")
@limiter.limit("20/hour")
def make_estimate(project_id: int, req: EstimateRequest, request: Request,
                  current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _project(project_id, current_user, db)
    details = (p.ai_analysis or {}).get("details", {})
    if not details:
        raise HTTPException(400, "Analysez d'abord le DCE pour pouvoir le chiffrer.")
    rates, th, su = _rates(current_user, db)
    from app.services.llm import LLMUnavailable, tenant_scope
    try:
        with tenant_scope(current_user.id):
            tasks = propose_tasks(details, [r.get("label") for r in rates])
    except LLMUnavailable as e:
        raise HTTPException(503, str(e), headers={"Retry-After": "30"})
    if not tasks:
        raise HTTPException(502, "Le chiffrage n'a pas pu être généré. Réessayez.")
    est = compute_estimate(tasks, rates, req.distance_km, th, su)
    est["rates_used"] = rates
    p.estimate = est
    db.commit()
    return est


@router.put("/{project_id}")
def save_estimate(project_id: int, req: SaveRequest,
                  current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Recalcul déterministe après ajustement manuel (aucun appel IA)."""
    p = _project(project_id, current_user, db)
    rates, th, su = _rates(current_user, db)
    est = compute_estimate(req.lignes, rates, req.distance_km, th, su)
    est["rates_used"] = rates
    p.estimate = est
    db.commit()
    return est
