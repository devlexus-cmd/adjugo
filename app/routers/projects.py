"""
Adjugo — Routes des projets (Appels d'offres)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.org import member_ids
from app.models import User, Project, Document
from app.schemas import ProjectCreate, ProjectUpdate, ProjectOut

router = APIRouter(prefix="/api/projects", tags=["Projets / AO"])


@router.get("/{project_id}/documents")
def project_documents(project_id: int, current_user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """Dossier de l'AO : documents rangés par sous-dossier (arborescence)."""
    from app.services.dossier import FOLDERS
    ids = member_ids(current_user, db)
    project = db.query(Project).filter(Project.id == project_id,
                                       Project.user_id.in_(ids)).first()
    if not project:
        raise HTTPException(404, "Appel d'offres introuvable")
    docs = db.query(Document).filter(Document.project_id == project_id,
                                     Document.user_id.in_(ids),
                                     Document.deleted_at.is_(None)).order_by(Document.created_at).all()
    by_folder = {}
    for d in docs:
        f = d.folder or "Autres"
        by_folder.setdefault(f, []).append({
            "id": d.id, "name": d.name, "file_size": d.file_size,
            "mime_type": d.mime_type, "created_at": d.created_at.isoformat() if d.created_at else None,
        })
    # Ordonner selon l'arborescence type, puis les dossiers restants
    order = FOLDERS + [k for k in by_folder if k not in FOLDERS]
    folders = [{"folder": f, "documents": by_folder[f]} for f in order if f in by_folder]
    return {"project_id": project_id, "total": len(docs), "folders": folders}


@router.get("/", response_model=List[ProjectOut])
def list_projects(
    status: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lister tous les projets de l'organisation (hors corbeille)."""
    query = db.query(Project).filter(Project.user_id.in_(member_ids(current_user, db)),
                                     Project.deleted_at.is_(None))
    if status:
        query = query.filter(Project.status == status)
    return query.order_by(Project.created_at.desc()).all()


@router.post("/", response_model=ProjectOut, status_code=201)
def create_project(
    data: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Créer un nouveau projet / appel d'offres."""
    project = Project(user_id=current_user.id, **data.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Récupérer un projet par son ID."""
    project = db.query(Project).filter(
        Project.id == project_id, Project.user_id.in_(member_ids(current_user, db)),
        Project.deleted_at.is_(None),
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    return project


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    data: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mettre à jour un projet."""
    project = db.query(Project).filter(
        Project.id == project_id, Project.user_id.in_(member_ids(current_user, db)),
        Project.deleted_at.is_(None),
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(project, key, value)

    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mettre un projet à la corbeille (suppression douce, réversible)."""
    project = db.query(Project).filter(
        Project.id == project_id, Project.user_id.in_(member_ids(current_user, db)),
        Project.deleted_at.is_(None),
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    from app.models import utcnow, ProjectInvite
    project.deleted_at = utcnow()
    # Couper les liens d'invitation actifs : pas de lien « vivant » vers un AO en corbeille.
    db.query(ProjectInvite).filter(ProjectInvite.project_id == project.id,
                                   ProjectInvite.revoked.is_(False)).update({"revoked": True})
    db.commit()


@router.post("/{project_id}/restore", status_code=200)
def restore_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Restaurer un projet depuis la corbeille (annulation de suppression)."""
    project = db.query(Project).filter(
        Project.id == project_id, Project.user_id.in_(member_ids(current_user, db)),
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    project.deleted_at = None
    db.commit()
    return {"ok": True, "id": project.id}
