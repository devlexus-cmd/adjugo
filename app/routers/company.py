"""
Adjugo — Routes Entreprise et Critères de matching
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User, Company, MatchingCriteria
from app.schemas import CompanyCreate, CompanyOut, CriteriaUpdate, CriteriaOut

# === COMPANY ===

company_router = APIRouter(prefix="/api/company", tags=["Mon entreprise"])


@company_router.get("/", response_model=CompanyOut)
def get_company(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.user_id == current_user.id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Profil entreprise non créé")
    return company


@company_router.post("/", response_model=CompanyOut, status_code=201)
def create_company(
    data: CompanyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = db.query(Company).filter(Company.user_id == current_user.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Profil déjà existant, utilisez PUT")

    company = Company(user_id=current_user.id, **data.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@company_router.put("/", response_model=CompanyOut)
def update_company(
    data: CompanyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.user_id == current_user.id).first()
    if not company:
        company = Company(user_id=current_user.id)
        db.add(company)

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(company, key, value)

    db.commit()
    db.refresh(company)
    return company


# === CRITÈRES DE MATCHING ===

criteria_router = APIRouter(prefix="/api/criteria", tags=["Critères Go/No-Go"])


@criteria_router.get("/", response_model=CriteriaOut)
def get_criteria(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    criteria = db.query(MatchingCriteria).filter(
        MatchingCriteria.user_id == current_user.id
    ).first()
    if not criteria:
        criteria = MatchingCriteria(user_id=current_user.id)
        db.add(criteria)
        db.commit()
        db.refresh(criteria)
    return criteria


@criteria_router.put("/", response_model=CriteriaOut)
def update_criteria(
    data: CriteriaUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    criteria = db.query(MatchingCriteria).filter(
        MatchingCriteria.user_id == current_user.id
    ).first()
    if not criteria:
        criteria = MatchingCriteria(user_id=current_user.id)
        db.add(criteria)

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(criteria, key, value)

    db.commit()
    db.refresh(criteria)
    return criteria
