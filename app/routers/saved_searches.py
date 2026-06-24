"""
Veille / alertes AO programmées : l'utilisateur sauvegarde ses critères de
recherche ; un cron quotidien rejoue la recherche et envoie un digest des
nouveaux appels d'offres pertinents. Passe de « je vérifie » à « ça arrive ».
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User, SavedSearch

router = APIRouter(prefix="/api/saved-searches", tags=["Veille / alertes AO"])


class SavedSearchIn(BaseModel):
    name: str
    query: Optional[str] = ""
    cpv: list[str] = []
    type_marche: Optional[str] = ""
    departements: list[str] = []
    countries: list[str] = []
    montant_min: Optional[float] = None
    montant_max: Optional[float] = None
    frequency: Optional[str] = "quotidienne"
    active: Optional[bool] = True
    min_score: Optional[int] = None


def _out(s: SavedSearch) -> dict:
    return {
        "id": s.id, "name": s.name, "query": s.query or "",
        "cpv": s.cpv or [], "type_marche": getattr(s, "type_marche", "") or "",
        "departements": s.departements or [], "countries": s.countries or [],
        "montant_min": s.montant_min, "montant_max": s.montant_max,
        "frequency": s.frequency, "active": s.active, "min_score": s.min_score,
        "last_run": s.last_run.isoformat() if s.last_run else None,
        "matches_seen": len(s.last_seen_refs or []),
    }


@router.get("/")
def list_saved_searches(current_user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    rows = db.query(SavedSearch).filter(SavedSearch.user_id == current_user.id) \
             .order_by(SavedSearch.created_at.desc()).all()
    return [_out(s) for s in rows]


@router.post("/", status_code=201)
def create_saved_search(data: SavedSearchIn, current_user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    s = SavedSearch(user_id=current_user.id, **data.model_dump())
    db.add(s); db.commit(); db.refresh(s)
    return _out(s)


@router.put("/{search_id}")
def update_saved_search(search_id: int, data: SavedSearchIn,
                        current_user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    s = db.query(SavedSearch).filter(SavedSearch.id == search_id,
                                     SavedSearch.user_id == current_user.id).first()
    if not s:
        raise HTTPException(404, "Alerte introuvable")
    # exclude_unset : on ne met à jour que les champs RÉELLEMENT envoyés → un PUT partiel
    # (ex. bascule actif/inactif) n'écrase plus les CPV/pays/montants/seuil avec leur défaut.
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit(); db.refresh(s)
    return _out(s)


@router.delete("/{search_id}")
def delete_saved_search(search_id: int, current_user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    s = db.query(SavedSearch).filter(SavedSearch.id == search_id,
                                     SavedSearch.user_id == current_user.id).first()
    if not s:
        raise HTTPException(404, "Alerte introuvable")
    db.delete(s); db.commit()
    return {"ok": True}


@router.post("/{search_id}/run")
def run_saved_search_now(search_id: int, current_user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """Exécute l'alerte immédiatement (APERÇU) et renvoie les nouveaux AO trouvés."""
    s = db.query(SavedSearch).filter(SavedSearch.id == search_id,
                                     SavedSearch.user_id == current_user.id).first()
    if not s:
        raise HTTPException(404, "Alerte introuvable")
    from app.services.alerts import run_one_saved_search
    # mark=False : c'est un APERÇU. Avec mark=True, les AO trouvés étaient marqués « déjà vus »
    # et n'étaient JAMAIS inclus dans le prochain digest email — le client les perdait d'un clic
    # sur un bouton « tester ». On ne mute donc ni last_seen_refs ni last_run.
    fresh = run_one_saved_search(s, db, mark=False)
    return {"new_matches": len(fresh), "tenders": fresh}
