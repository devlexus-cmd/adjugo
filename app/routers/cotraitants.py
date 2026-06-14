from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Float, ForeignKey
from pydantic import BaseModel
from typing import Optional, List
from app.core.database import get_db, Base
from app.core.security import get_current_user
from app.core.org import member_ids
from app.models import User

class Cotraitant(Base):
    __tablename__ = "cotraitants"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, nullable=False)
    siret = Column(String)
    code_ape = Column(String)
    forme_juridique = Column(String)
    representant_legal = Column(String)
    address = Column(String)
    postal_code = Column(String)
    city = Column(String)
    email = Column(String)
    phone = Column(String)
    tva_intracom = Column(String)
    ca_n1 = Column(Float, default=0)
    ca_n2 = Column(Float, default=0)
    ca_n3 = Column(Float, default=0)
    effectif = Column(Integer, default=0)
    qualifications = Column(String)
    # Champs de matching (moteur de suggestion de co-traitance)
    specialites = Column(String, default="")   # "Électricité, CFO/CFA, Domotique"
    codes_cpv = Column(String, default="")      # "45310000, 45315100"
    departement = Column(String, default="")    # "29"


class ProjectCotraitant(Base):
    """Liaison sous-traitant ↔ appel d'offres (un co-traitant du réseau peut
    être rattaché à plusieurs AO, un AO a plusieurs sous-traitants)."""
    __tablename__ = "project_cotraitants"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), index=True)
    cotraitant_id = Column(Integer, ForeignKey("cotraitants.id"))
    role = Column(String, default="sous_traitant")   # mandataire | cotraitant | sous_traitant
    lot = Column(String, default="")


class CotraitantCreate(BaseModel):
    name: str
    siret: Optional[str] = ""
    code_ape: Optional[str] = ""
    forme_juridique: Optional[str] = ""
    representant_legal: Optional[str] = ""
    address: Optional[str] = ""
    postal_code: Optional[str] = ""
    city: Optional[str] = ""
    email: Optional[str] = ""
    phone: Optional[str] = ""
    tva_intracom: Optional[str] = ""
    ca_n1: Optional[float] = 0
    ca_n2: Optional[float] = 0
    ca_n3: Optional[float] = 0
    effectif: Optional[int] = 0
    qualifications: Optional[str] = ""
    specialites: Optional[str] = ""
    codes_cpv: Optional[str] = ""
    departement: Optional[str] = ""

router = APIRouter(prefix="/api/cotraitants", tags=["Co-traitants"])

@router.get("/")
def list_cotraitants(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Cotraitant).filter(Cotraitant.user_id.in_(member_ids(current_user, db))).all()

@router.post("/")
def create_cotraitant(data: CotraitantCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ct = Cotraitant(user_id=current_user.id, **data.model_dump())
    db.add(ct)
    db.commit()
    db.refresh(ct)
    return ct

@router.put("/{ct_id}")
def update_cotraitant(ct_id: int, data: CotraitantCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ct = db.query(Cotraitant).filter(Cotraitant.id == ct_id, Cotraitant.user_id.in_(member_ids(current_user, db))).first()
    if not ct:
        raise HTTPException(404, "Co-traitant introuvable")
    for k, v in data.model_dump().items():
        setattr(ct, k, v)
    db.commit()
    db.refresh(ct)
    return ct


@router.delete("/{ct_id}")
def delete_cotraitant(ct_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ct = db.query(Cotraitant).filter(Cotraitant.id == ct_id, Cotraitant.user_id.in_(member_ids(current_user, db))).first()
    if not ct:
        raise HTTPException(404, "Co-traitant introuvable")
    db.delete(ct)
    db.commit()
    return {"ok": True}


# ── Sous-traitants rattachés à un appel d'offres ─────────────────────────────────

class AttachRequest(BaseModel):
    cotraitant_id: Optional[int] = None      # depuis le réseau existant
    company: Optional[dict] = None           # ou une entreprise réelle (SIRENE) à créer + lier
    role: Optional[str] = "sous_traitant"
    lot: Optional[str] = ""


def _own_project(project_id, user, db):
    from app.models import Project
    p = db.query(Project).filter(Project.id == project_id,
                                 Project.user_id.in_(member_ids(user, db))).first()
    if not p:
        raise HTTPException(404, "Appel d'offres introuvable")
    return p


@router.get("/project/{project_id}")
def list_project_cotraitants(project_id: int, current_user: User = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    _own_project(project_id, current_user, db)
    links = db.query(ProjectCotraitant).filter(ProjectCotraitant.project_id == project_id).all()
    out = []
    for lk in links:
        ct = db.query(Cotraitant).filter(Cotraitant.id == lk.cotraitant_id).first()
        if not ct:
            continue
        out.append({"link_id": lk.id, "role": lk.role, "lot": lk.lot,
                    "id": ct.id, "name": ct.name, "siret": ct.siret, "code_ape": ct.code_ape,
                    "city": ct.city, "departement": ct.departement, "specialites": ct.specialites,
                    "effectif": ct.effectif})
    return out


@router.post("/project/{project_id}")
def attach_cotraitant(project_id: int, req: AttachRequest,
                      current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _own_project(project_id, current_user, db)

    # 1) Résoudre / créer le co-traitant (réseau)
    ids = member_ids(current_user, db)
    ct = None
    if req.cotraitant_id:
        ct = db.query(Cotraitant).filter(Cotraitant.id == req.cotraitant_id,
                                         Cotraitant.user_id.in_(ids)).first()
        if not ct:
            raise HTTPException(404, "Co-traitant introuvable")
    elif req.company:
        c = req.company
        siret = c.get("siret")
        if siret:
            ct = db.query(Cotraitant).filter(Cotraitant.user_id.in_(ids),
                                             Cotraitant.siret == siret).first()
        if not ct:
            ct = Cotraitant(user_id=current_user.id, name=c.get("name") or c.get("nom") or "Sous-traitant",
                            siret=siret, code_ape=c.get("code_ape") or c.get("naf"),
                            city=c.get("city") or c.get("ville"),
                            departement=c.get("departement") or "",
                            specialites=c.get("specialites") or c.get("naf_label") or "",
                            effectif=c.get("effectif") or 0)
            db.add(ct); db.commit(); db.refresh(ct)
    else:
        raise HTTPException(400, "Fournir cotraitant_id ou company")

    # 2) Éviter un doublon de liaison
    exists = db.query(ProjectCotraitant).filter(
        ProjectCotraitant.project_id == project_id,
        ProjectCotraitant.cotraitant_id == ct.id).first()
    if exists:
        exists.role = req.role or exists.role
        exists.lot = req.lot or exists.lot
        db.commit()
        return {"link_id": exists.id, "cotraitant_id": ct.id, "name": ct.name}

    link = ProjectCotraitant(project_id=project_id, cotraitant_id=ct.id,
                             role=req.role or "sous_traitant", lot=req.lot or "")
    db.add(link); db.commit(); db.refresh(link)
    return {"link_id": link.id, "cotraitant_id": ct.id, "name": ct.name}


@router.delete("/project/{project_id}/{link_id}")
def detach_cotraitant(project_id: int, link_id: int,
                      current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _own_project(project_id, current_user, db)
    link = db.query(ProjectCotraitant).filter(ProjectCotraitant.id == link_id,
                                              ProjectCotraitant.project_id == project_id).first()
    if not link:
        raise HTTPException(404, "Liaison introuvable")
    db.delete(link); db.commit()
    return {"ok": True}
