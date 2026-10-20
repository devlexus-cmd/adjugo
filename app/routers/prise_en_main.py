"""
Routes de la PRISE EN MAIN (réorganisation de l'interface, vague 2b, chantier B1). Toutes les règles sont dans
app/services/prise_en_main.py ; contrat : docs/REORGANISATION_V2B.md, section B1.

  GET  /api/prise-en-main                               « Vos premiers pas » (tâches et statuts lus dans les données) et
                                                        la carte « Faites-vous trouver » à montrer, ou rien
  PUT  /api/prise-en-main                               {replie: bool} : replier ou déplier la liste de l'accueil
  POST /api/prise-en-main/suggestion-reseau/fermer      la carte « Faites-vous trouver » est fermée (ou suivie)

Portée : le compte connecté et les données de son organisation, en lecture (comptes, jamais un contenu). Aucune IA,
aucun courriel. Démonstration : lecture seule (rien à replier ni à fermer : elle n'a ni premiers pas ni carte).
"""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.ratelimit import limiter
from app.core.security import get_current_user
from app.models import User
from app.services import prise_en_main as pm

router = APIRouter(prefix="/api/prise-en-main", tags=["Prise en main"])


@router.get("")
def lire(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return pm.etat(db, current_user)


class RepliIn(BaseModel):
    replie: Optional[bool] = None


@router.put("")
@limiter.limit("120/hour")
def replier(request: Request, body: RepliIn, current_user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    from app.core.demo_guard import refuser_demo
    refuser_demo(current_user, "changer l'accueil")
    if body.replie is not None:
        pm.replier(db, current_user, body.replie)
    return pm.etat(db, current_user)


@router.post("/suggestion-reseau/fermer")
@limiter.limit("120/hour")
def fermer_suggestion(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.core.demo_guard import refuser_demo
    refuser_demo(current_user, "changer l'accueil")
    pm.fermer_suggestion_reseau(db, current_user)
    return {"ok": True}
