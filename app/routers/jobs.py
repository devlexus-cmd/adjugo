"""Router Jobs — statut/résultat des traitements asynchrones (anti-timeout)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.org import member_ids
from app.models import User, Job
from app.services.jobs import job_out

router = APIRouter(prefix="/api/jobs", tags=["Jobs asynchrones"])


@router.get("/{job_id}")
def get_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Portée = organisation COURANTE (comme projets/savoir-faire) : un membre voit les
    # générations de son équipe (bâties sur le savoir-faire commun), et un membre retiré
    # (qui a changé d'org) ne voit plus rien — même avec un id de job deviné.
    # Une tâche lancée par un PARTENAIRE du groupement (rédaction, vague 4 : portée « partenaire »,
    # aucun compte propriétaire) n'est JAMAIS lue ici, ni par le chef de file ni par personne : elle ne
    # se lit qu'avec le lien de ce partenaire ou le compte qui l'a rattaché (même réponse qu'un id inconnu).
    j = db.query(Job).filter(Job.id == job_id,
                             Job.user_id.in_(member_ids(current_user, db)),
                             or_(Job.portee.is_(None), Job.portee != "partenaire")).first()
    if not j:
        raise HTTPException(404, "Ce résultat est introuvable ou n'est plus accessible.")
    return job_out(j)
