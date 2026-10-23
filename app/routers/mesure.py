"""
Mesure d'usage de l'interface (réorganisation, vague 1, point 1.1 ; décision 17).

POST /api/mesure/ecran {"ecran": "<vue>"} : l'application signale l'ouverture d'un écran ; le serveur ajoute 1 au
compteur (jour, écran) et ne garde RIEN d'autre (ni compte, ni organisation, ni adresse IP). Répond toujours 204,
sans corps : un écran inconnu ou une session de démonstration ne comptent pas, sans erreur à l'écran.
La lecture est réservée à l'administrateur de la plateforme : GET /api/admin/mesures/ecrans (routers/admin.py).
Contrat : docs/REORGANISATION_V1.md, § 1.1 ; service : app/services/mesure_usage.py.
"""
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.ratelimit import limiter
from app.core.security import get_current_user
from app.models import User

router = APIRouter(prefix="/api/mesure", tags=["Mesure d'usage"])


class EcranIn(BaseModel):
    ecran: str = Field(..., min_length=1, max_length=40)


@router.post("/ecran", status_code=204)
@limiter.limit("600/hour")
def ecran_ouvert(request: Request, data: EcranIn, current_user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    from app.services.demo_search import is_demo
    from app.services.mesure_usage import compter
    # La session sert seulement à refuser les appels anonymes ; elle n'est pas enregistrée.
    if not is_demo(current_user):
        compter(db, data.ecran.strip())
    return Response(status_code=204)
