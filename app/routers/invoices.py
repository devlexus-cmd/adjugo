"""
Adjugo — Routes Facturation
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List
from datetime import date

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User, Invoice
from app.schemas import InvoiceCreate, InvoiceUpdate, InvoiceOut

router = APIRouter(prefix="/api/invoices", tags=["Facturation"])


def generate_reference(db: Session, user_id: int, inv_type: str) -> str:
    """Génère une référence unique : FAC-2026-001 ou DEV-2026-001."""
    prefix = "FAC" if inv_type == "facture" else "DEV" if inv_type == "devis" else "AVO"
    year = date.today().year
    count = db.query(Invoice).filter(
        Invoice.user_id == user_id,
        Invoice.reference.like(f"{prefix}-{year}-%")
    ).count()
    return f"{prefix}-{year}-{str(count + 1).zfill(3)}"


def _num(v, default=0.0):
    """Coerce qty/prix/taux en float (un champ vidé arrive en None/'' → 0, jamais un crash)."""
    try:
        f = float(v)
        return f if f == f else default   # écarte NaN
    except (TypeError, ValueError):
        return default


def calculate_totals(items: list, tva_rate: float) -> tuple:
    """Calcule sous-total HT, TVA et TTC. Montants ARRONDIS à 2 décimales (document
    comptable : pas de dérive de centime ni de double imprécision flottante)."""
    subtotal = round(sum(_num(i.get("qty", 1), 1.0) * _num(i.get("unit_price", 0)) for i in (items or [])), 2)
    tva = round(subtotal * _num(tva_rate) / 100, 2)
    return subtotal, tva, round(subtotal + tva, 2)


@router.get("/", response_model=List[InvoiceOut])
def list_invoices(
    type: str = None,
    status: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Invoice).filter(Invoice.user_id == current_user.id)
    if type:
        query = query.filter(Invoice.type == type)
    if status:
        query = query.filter(Invoice.status == status)
    return query.order_by(Invoice.created_at.desc()).all()


@router.post("/", response_model=InvoiceOut, status_code=201)
def create_invoice(
    data: InvoiceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ref = generate_reference(db, current_user.id, data.type)
    ht, tva, ttc = calculate_totals(data.items, data.tva_rate)

    invoice = Invoice(
        user_id=current_user.id,
        reference=ref,
        type=data.type,
        client_name=data.client_name,
        client_address=data.client_address,
        client_siret=data.client_siret,
        items=data.items,
        subtotal_ht=ht,
        tva_rate=data.tva_rate,
        tva_amount=tva,
        total_ttc=ttc,
        due_date=data.due_date,
        project_id=data.project_id,
        notes=data.notes,
    )
    db.add(invoice)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Conflit de numérotation, réessayez")
    db.refresh(invoice)
    return invoice


@router.put("/{invoice_id}", response_model=InvoiceOut)
def update_invoice(
    invoice_id: int,
    data: InvoiceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    inv = db.query(Invoice).filter(
        Invoice.id == invoice_id, Invoice.user_id == current_user.id
    ).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Facture introuvable")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(inv, key, value)

    # Recalculer dès que les lignes OU le taux de TVA changent (sinon TVA/TTC restaient
    # périmés après une simple modif de taux → document comptablement incohérent).
    if data.items is not None or data.tva_rate is not None:
        inv.subtotal_ht, inv.tva_amount, inv.total_ttc = calculate_totals(inv.items or [], inv.tva_rate)

    db.commit()
    db.refresh(inv)
    return inv


@router.post("/{invoice_id}/convert", response_model=InvoiceOut)
def convert_devis_to_facture(
    invoice_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Convertir un devis accepté en facture."""
    devis = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.user_id == current_user.id,
        Invoice.type == "devis",
    ).first()
    if not devis:
        raise HTTPException(status_code=404, detail="Devis introuvable")

    ref = generate_reference(db, current_user.id, "facture")
    facture = Invoice(
        user_id=current_user.id,
        reference=ref,
        type="facture",
        status="en_attente",
        client_name=devis.client_name,
        client_address=devis.client_address,
        client_siret=devis.client_siret,
        items=devis.items,
        subtotal_ht=devis.subtotal_ht,
        tva_rate=devis.tva_rate,
        tva_amount=devis.tva_amount,
        total_ttc=devis.total_ttc,
        project_id=devis.project_id,
        notes=devis.notes,
    )
    db.add(facture)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Conflit de numérotation, réessayez")
    db.refresh(facture)
    return facture
