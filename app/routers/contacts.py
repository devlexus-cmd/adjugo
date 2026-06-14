"""
Adjugo — Routes Contacts (CRM)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.org import member_ids
from app.models import User, Contact
from app.schemas import ContactCreate, ContactUpdate, ContactOut

router = APIRouter(prefix="/api/contacts", tags=["Contacts"])


@router.get("/", response_model=List[ContactOut])
def list_contacts(
    type: str = None,
    search: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Contact).filter(Contact.user_id.in_(member_ids(current_user, db)))
    if type:
        query = query.filter(Contact.contact_type == type)
    if search:
        query = query.filter(
            Contact.name.ilike(f"%{search}%") | Contact.organization.ilike(f"%{search}%")
        )
    return query.order_by(Contact.name).all()


@router.post("/", response_model=ContactOut, status_code=201)
def create_contact(
    data: ContactCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contact = Contact(user_id=current_user.id, **data.model_dump())
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


@router.put("/{contact_id}", response_model=ContactOut)
def update_contact(
    contact_id: int,
    data: ContactUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contact = db.query(Contact).filter(
        Contact.id == contact_id, Contact.user_id.in_(member_ids(current_user, db))
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact introuvable")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(contact, key, value)
    db.commit()
    db.refresh(contact)
    return contact


@router.delete("/{contact_id}", status_code=204)
def delete_contact(
    contact_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contact = db.query(Contact).filter(
        Contact.id == contact_id, Contact.user_id.in_(member_ids(current_user, db))
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact introuvable")
    db.delete(contact)
    db.commit()
