"""
Router REGISTRE — connexion au monde professionnel réel (API Recherche d'entreprises).
  - GET  /api/registre/company?q=     : auto-remplissage du profil par SIRET/nom
  - GET  /api/registre/trades         : métiers BTP disponibles pour la découverte
  - GET  /api/registre/discover       : trouver de vraies entreprises co-traitantes
  - POST /api/registre/import         : importer une entreprise réelle comme co-traitant
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.services.dce_scoring import _dept   # Corse 2A/2B & DOM-TOM 97x corrects (au lieu de [:2])

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User
from app.services import registre

router = APIRouter(prefix="/api/registre", tags=["Registre entreprises (réel)"])


@router.get("/company")
def lookup(q: str = Query(..., description="SIRET, SIREN ou nom"),
           current_user: User = Depends(get_current_user)):
    res = registre.lookup_company(q)
    if not res:
        raise HTTPException(404, "Entreprise introuvable dans le registre")
    return res


@router.get("/trades")
def trades(current_user: User = Depends(get_current_user)):
    return [{"key": t["key"], "label": t["label"], "naf": t["naf"]} for t in registre.TRADES]


@router.get("/discover")
def discover(activity: str = Query("", description="Clé métier ou texte libre"),
             departement: str = Query("", description="Numéro de département"),
             query: str = Query("", description="Recherche libre"),
             current_user: User = Depends(get_current_user)):
    return registre.discover_cotraitants(activity=activity, departement=departement,
                                         query=query, limit=12)


class ImportCotraitant(BaseModel):
    siren: Optional[str] = ""
    name: str
    siret: Optional[str] = ""
    code_ape: Optional[str] = ""
    forme_juridique: Optional[str] = ""
    representant_legal: Optional[str] = ""
    address: Optional[str] = ""
    postal_code: Optional[str] = ""
    city: Optional[str] = ""
    departement: Optional[str] = ""
    effectif: Optional[int] = 0
    specialites: Optional[str] = ""
    qualifications: Optional[str] = ""
    codes_cpv: Optional[str] = ""


@router.post("/import")
def import_cotraitant(data: ImportCotraitant,
                      current_user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """Crée un co-traitant à partir d'une entreprise réelle découverte dans le registre."""
    from app.routers.cotraitants import Cotraitant
    from app.core.org import member_ids
    existing = None
    if data.siret:
        # Dé-duplication au niveau ORGANISATION (cohérent avec le reste) : éviter qu'un
        # coéquipier ré-importe un partenaire déjà présent dans le carnet de l'équipe.
        existing = db.query(Cotraitant).filter(
            Cotraitant.user_id.in_(member_ids(current_user, db)), Cotraitant.siret == data.siret).first()
    if existing:
        raise HTTPException(409, "Ce co-traitant existe déjà")
    ct = Cotraitant(
        user_id=current_user.id,
        name=data.name, siret=data.siret, code_ape=data.code_ape,
        forme_juridique=data.forme_juridique, representant_legal=data.representant_legal,
        address=data.address, postal_code=data.postal_code, city=data.city,
        departement=data.departement or _dept(data.postal_code or "") or (data.postal_code or "")[:2],
        effectif=data.effectif or 0, specialites=data.specialites,
        qualifications=data.qualifications, codes_cpv=data.codes_cpv,
    )
    db.add(ct); db.commit(); db.refresh(ct)
    return ct
