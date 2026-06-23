"""
Adjugo - Router criteres de matching etendus
Stocke les criteres supplementaires en JSON pour flexibilite.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, Float, String, JSON, ForeignKey
from pydantic import BaseModel, field_validator
from typing import Optional
from app.core.database import get_db, Base
from app.core.security import get_current_user
from app.core.org import data_owner_id
from app.models import User

# Modele etendu
try:
    from app.models import MatchingCriteria as ExistingCriteria
except ImportError:
    ExistingCriteria = None


class MatchingCriteriaExt(Base):
    __tablename__ = "matching_criteria_ext"
    __table_args__ = {"extend_existing": True}
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    # Budget
    budget_min = Column(Float, default=10000)
    budget_max = Column(Float, default=500000)
    ca_ratio_max = Column(Float, default=30)
    avance_min = Column(Float, default=5)
    delai_paiement_max = Column(Integer, default=60)
    # Geographie
    max_distance_km = Column(Integer, default=100)
    departements = Column(String, default="")
    regions = Column(String, default="")
    # Types
    types_marche = Column(String, default="Travaux, Services")
    procedures_acceptees = Column(String, default="MAPA, AOO")
    lot_min = Column(Float, default=5000)
    codes_cpv = Column(String, default="")
    # Technique
    qualifications = Column(String, default="")
    certifications = Column(String, default="")
    specialites = Column(String, default="")
    effectif_max_marche = Column(Integer, default=0)
    # Risques
    penalty_max = Column(Float, default=10)
    garantie_max = Column(Float, default=5)
    retenue_garantie_max = Column(Float, default=5)
    delai_reponse_min = Column(Integer, default=15)
    excluded_keywords = Column(String, default="")
    # Seuils
    go_threshold = Column(Integer, default=75)
    nogo_threshold = Column(Integer, default=40)


class CriteriaUpdate(BaseModel):
    budget_min: Optional[float] = 10000
    budget_max: Optional[float] = 500000
    ca_ratio_max: Optional[float] = 30
    avance_min: Optional[float] = 5
    delai_paiement_max: Optional[int] = 60
    max_distance_km: Optional[int] = 100
    departements: Optional[str] = ""
    regions: Optional[str] = ""
    types_marche: Optional[str] = "Travaux, Services"
    procedures_acceptees: Optional[str] = "MAPA, AOO"
    lot_min: Optional[float] = 5000
    codes_cpv: Optional[str] = ""
    qualifications: Optional[str] = ""
    certifications: Optional[str] = ""
    specialites: Optional[str] = ""
    effectif_max_marche: Optional[int] = 0
    penalty_max: Optional[float] = 10
    garantie_max: Optional[float] = 5
    retenue_garantie_max: Optional[float] = 5
    delai_reponse_min: Optional[int] = 15
    excluded_keywords: Optional[str] = ""
    go_threshold: Optional[int] = 75
    nogo_threshold: Optional[int] = 40

    # Un champ numérique laissé VIDE dans le formulaire arrive en "" (v-model.number)
    # → Pydantic refusait tout l'enregistrement (422). On accepte le vide = None,
    # et l'endpoint conserve alors la valeur existante / le défaut (jamais d'erreur).
    @field_validator("budget_min", "budget_max", "ca_ratio_max", "avance_min",
                     "delai_paiement_max", "max_distance_km", "lot_min",
                     "effectif_max_marche", "penalty_max", "garantie_max",
                     "retenue_garantie_max", "delai_reponse_min",
                     "go_threshold", "nogo_threshold", mode="before")
    @classmethod
    def _empty_num_to_none(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, float) and v != v:   # NaN
            return None
        return v


router = APIRouter(prefix="/api/criteria", tags=["Criteres de matching"])


@router.get("/")
def get_criteria(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.query(MatchingCriteriaExt).filter(MatchingCriteriaExt.user_id == data_owner_id(current_user, db)).first()
    if not c:
        return CriteriaUpdate().model_dump()
    result = {}
    for field in CriteriaUpdate.model_fields.keys():
        result[field] = getattr(c, field, None)
    return result


@router.put("/")
def update_criteria(data: CriteriaUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.query(MatchingCriteriaExt).filter(MatchingCriteriaExt.user_id == data_owner_id(current_user, db)).first()
    if not c:
        c = MatchingCriteriaExt(user_id=data_owner_id(current_user, db))
        db.add(c)
    for k, v in data.model_dump().items():
        if v is None:
            # Champ TEXTE explicitement vidé → on l'EFFACE (l'utilisateur doit pouvoir
            # retirer ses spécialités/départements/CPV). Champ numérique laissé vide → on
            # garde la valeur en place / le défaut (un nombre ne se « vide » pas en base).
            if "str" in str(CriteriaUpdate.model_fields[k].annotation):
                setattr(c, k, "")
            continue
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    result = {}
    for field in CriteriaUpdate.model_fields.keys():
        result[field] = getattr(c, field, None)
    return result
