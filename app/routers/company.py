"""
Adjugo — Routes Entreprise et Critères de matching
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.org import data_owner_id
from app.models import User, Company, MatchingCriteria
from app.schemas import CompanyCreate, CompanyOut, CriteriaUpdate, CriteriaOut

# === COMPANY ===
# Le profil entreprise et les critères Go/No-Go sont PARTAGÉS dans l'organisation :
# tous les membres lisent/éditent le profil du propriétaire (l'org = l'entreprise).

company_router = APIRouter(prefix="/api/company", tags=["Mon entreprise"])


def _refuser_demo(user) -> None:
    """Défense en profondeur (middleware démo) : le profil de la vitrine partagée ne change pas."""
    from app.core.demo_guard import refuser_demo
    refuser_demo(user, "modifier le profil de votre entreprise")


@company_router.get("/", response_model=CompanyOut)
def get_company(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.user_id == data_owner_id(current_user, db)).first()
    if not company:
        raise HTTPException(status_code=404, detail="Entreprise non renseignée (Mon entreprise, onglet « Identité »)")
    return company


@company_router.post("/", response_model=CompanyOut, status_code=201)
def create_company(
    data: CompanyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _refuser_demo(current_user)
    oid = data_owner_id(current_user, db)
    existing = db.query(Company).filter(Company.user_id == oid).first()
    if existing:
        raise HTTPException(status_code=400, detail="Profil déjà existant, utilisez PUT")

    company = Company(user_id=oid, **data.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    _sync_partner_profile(db, oid)
    return company


@company_router.put("/", response_model=CompanyOut)
def update_company(
    data: CompanyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _refuser_demo(current_user)
    oid = data_owner_id(current_user, db)
    company = db.query(Company).filter(Company.user_id == oid).first()
    if not company:
        company = Company(user_id=oid)
        db.add(company)

    for key, value in data.model_dump(exclude_unset=True).items():
        if value is None and key in ("ca_n1", "ca_n2", "ca_n3", "effectif",
                                     "distance_threshold_km", "distance_surcharge_pct"):
            continue   # champ numérique vidé → on garde la valeur en place
        setattr(company, key, value)

    db.commit()
    db.refresh(company)
    _sync_partner_profile(db, oid)
    return company


def _sync_partner_profile(db: Session, owner_id: int) -> None:
    """Réseau de partenaires : un SIRET modifié retire la publication du profil partenaire et
    exige une nouvelle validation de l'identité par Adjugo (sinon un compte validé pour une
    entreprise pouvait ensuite publier sous le SIREN d'une autre). Ne lève jamais."""
    from app.services.partner_network import on_company_saved
    on_company_saved(db, owner_id)


# NB : les critères Go/No-Go sont servis par criteria_v2 (MatchingCriteriaExt). L'ancien
# criteria_router (MatchingCriteria) n'était plus monté → supprimé (code mort).
