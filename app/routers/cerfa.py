from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.ratelimit import limiter
from app.core.security import get_current_user
from app.core.org import member_ids
from app.models import User, Project, Company, GeneratedDoc
from app.services.cerfa import GENERATORS, missing_company_fields

router = APIRouter(prefix="/api/cerfa", tags=["Generation CERFA"])


@router.get("/types")
def list_types():
    return [
        {"id": "dc1", "name": "DC1", "description": "Lettre de candidature"},
        {"id": "dc2", "name": "DC2", "description": "Declaration du candidat"},
        {"id": "dc4", "name": "DC4", "description": "Sous-traitance"},
        {"id": "attri1", "name": "ATTRI1", "description": "Acte d'engagement"},
        {"id": "honneur", "name": "Déclaration sur l'honneur", "description": "Attestation art. R2143-3 (obligatoire)"},
        {"id": "dume", "name": "DUME", "description": "Document Unique de Marché Européen (pré-rempli)"},
    ]


@router.post("/{project_id}/{doc_type}")
@limiter.limit("20/hour")
def generate(
    project_id: int,
    doc_type: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if doc_type not in GENERATORS:
        raise HTTPException(status_code=400, detail=f"Type inconnu: {doc_type}")

    project = db.query(Project).filter(
        Project.id == project_id, Project.user_id.in_(member_ids(current_user, db))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable")

    company = db.query(Company).filter(Company.user_id == current_user.id).first()
    if not company:
        raise HTTPException(status_code=400, detail="Completez votre profil entreprise")

    cd = {}
    for k in ["name", "siret", "code_ape", "forme_juridique", "capital",
              "representant_legal", "address", "city", "postal_code",
              "tva_intracom", "ca_n1", "ca_n2", "ca_n3", "effectif"]:
        cd[k] = getattr(company, k, "") or ""
    cd["qualifications"] = company.qualifications or []

    # Pare-feu : un acte d'engagement / une déclaration aux champs de signature
    # vides est rejeté mécaniquement. On bloque AVANT de produire le PDF.
    if doc_type in ("attri1", "dc2", "honneur", "dc1"):
        missing = missing_company_fields(cd)
        if missing:
            raise HTTPException(
                status_code=422,
                detail={"message": "Champs obligatoires manquants dans votre profil entreprise "
                                   "avant génération de ce document.",
                        "missing_fields": missing},
            )

    pd = {
        "name": project.name,
        "client": project.client or "",
        "budget": project.budget or 0,
        "tva_rate": getattr(project, "tva_rate", 0) or 0,
        "reference": f"AO-{project.id:04d}",
    }

    pdf_bytes = GENERATORS[doc_type](cd, pd)

    gen = db.query(GeneratedDoc).filter(
        GeneratedDoc.project_id == project_id,
        GeneratedDoc.doc_type == doc_type,
    ).first()
    if not gen:
        gen = GeneratedDoc(project_id=project_id, doc_type=doc_type)
        db.add(gen)
    gen.status = "pret"
    gen.filled_data = {"company": company.name, "project": project.name}
    db.commit()

    filename = f"{doc_type.upper()}_{project.name[:30].replace(' ', '_')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{project_id}/status")
@limiter.limit("60/minute")
def get_status(
    project_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(
        Project.id == project_id, Project.user_id.in_(member_ids(current_user, db))
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable")

    generated = db.query(GeneratedDoc).filter(
        GeneratedDoc.project_id == project_id
    ).all()
    gen_map = {g.doc_type: g.status for g in generated}

    types = [
        ("dc1", "Lettre de candidature"),
        ("dc2", "Declaration du candidat"),
        ("dc4", "Sous-traitance"),
        ("attri1", "Acte d'engagement"),
        ("honneur", "Déclaration sur l'honneur (R2143-3)"),
        ("dume", "Document Unique de Marché Européen"),
    ]
    return [
        {"id": t, "name": t.upper(), "description": d, "status": gen_map.get(t, "vide")}
        for t, d in types
    ]
