"""Router Jobs — statut/résultat des traitements asynchrones (anti-timeout)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User, Job
from app.services.jobs import job_out

router = APIRouter(prefix="/api/jobs", tags=["Jobs asynchrones"])


@router.get("/{job_id}")
def get_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not j:
        raise HTTPException(404, "Job introuvable")
    return job_out(j)
