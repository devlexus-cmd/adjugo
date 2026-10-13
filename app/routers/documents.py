"""
Adjugo — Routes Documents (Coffre-fort)
"""
import os
import uuid
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body
from fastapi.responses import StreamingResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import io

from app.core.database import get_db
from app.core.config import get_settings
from app.core.security import get_current_user
from app.core.org import member_ids
from app.core.mime import file_headers, mime_for
from app.core.uploads import read_upload_limited
from app.models import User, Document, DocCategory
from app.services.storage import get_storage

settings = get_settings()
router = APIRouter(prefix="/api/documents", tags=["Coffre-fort"])

_ALLOWED_EXT = {e.strip().lower() for e in settings.ALLOWED_UPLOAD_EXT.split(",") if e.strip()}
_MAX_BYTES = settings.MAX_UPLOAD_MB * 1024 * 1024
_VALID_CATS = {e.value for e in DocCategory}   # catégorie hors-liste → stockée invalide puis
#  casse le listing (doc.category.value) / rejetée par l'enum Postgres → on la borne.


def _validate_and_read(file: UploadFile) -> tuple[bytes, str]:
    """Valide l'extension et la taille ; retourne (contenu, extension)."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if _ALLOWED_EXT and ext not in _ALLOWED_EXT:
        raise HTTPException(400, f"Type de fichier non autorisé ({ext or 'inconnu'}). "
                                 f"Autorisés : {', '.join(sorted(_ALLOWED_EXT))}")
    # Lecture BORNÉE (limite + 1 octet) : un corps de plusieurs Go n'est jamais chargé en
    # mémoire avant le 413 (process unique partagé par tous les clients).
    content = read_upload_limited(file, _MAX_BYTES)
    return content, ext


@router.get("/", response_model=List[dict])
def list_documents(
    category: str = None,
    search: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lister les documents du coffre-fort."""
    query = db.query(Document).filter(
        Document.user_id.in_(member_ids(current_user, db)),
        Document.parent_id.is_(None),  # Ne montrer que les versions courantes
        Document.deleted_at.is_(None),  # hors corbeille
    )
    if category:
        query = query.filter(Document.category == category)
    if search:
        query = query.filter(Document.name.ilike(f"%{search}%"))

    docs = query.order_by(Document.created_at.desc()).all()

    # Noms des AO liés (pour afficher le rattachement dans le coffre-fort)
    from app.models import Project
    pids = {d.project_id for d in docs if d.project_id}
    pnames = {}
    if pids:
        for p in db.query(Project).filter(Project.id.in_(pids)).all():
            pnames[p.id] = p.name

    result = []
    for doc in docs:
        days_until_exp = None
        if doc.expiration_date:
            days_until_exp = (doc.expiration_date - date.today()).days

        result.append({
            "id": doc.id,
            "name": doc.name,
            "category": doc.category.value if doc.category else "autre",
            "file_size": doc.file_size,
            "mime_type": doc.mime_type,
            "expiration_date": str(doc.expiration_date) if doc.expiration_date else None,
            "days_until_expiration": days_until_exp,
            "version": doc.version,
            "created_at": doc.created_at.isoformat(),
            "project_id": doc.project_id,
            "folder": doc.folder or "",
            "project_name": pnames.get(doc.project_id),
        })

    return result


@router.post("/", status_code=201)
def upload_document(
    file: UploadFile = File(...),
    name: str = Form(None),
    category: str = Form("autre"),
    expiration_date: str = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Uploader un document dans le coffre-fort."""
    from app.core.demo_guard import refuser_demo
    refuser_demo(current_user, "déposer des documents")     # défense en profondeur (middleware démo)
    content, ext = _validate_and_read(file)
    category = category if category in _VALID_CATS else "autre"
    file_key = f"{current_user.id}/{uuid.uuid4().hex}{ext}"
    # Type DÉRIVÉ de l'extension autorisée, jamais le Content-Type annoncé par le client.
    mime = mime_for(file_key)
    get_storage().save(file_key, content, mime)

    # Parser la date d'expiration
    exp_date = None
    if expiration_date:
        try:
            exp_date = date.fromisoformat(expiration_date)
        except ValueError:
            pass

    doc = Document(
        user_id=current_user.id,
        name=name or file.filename,
        category=category,
        file_key=file_key,
        file_size=len(content),
        mime_type=mime,
        expiration_date=exp_date,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "id": doc.id,
        "name": doc.name,
        "file_key": doc.file_key,
        "message": "Document uploadé avec succès",
    }


@router.put("/{doc_id}/replace", status_code=200)
def replace_document(
    doc_id: int,
    file: UploadFile = File(...),
    expiration_date: str = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remplacer un document par une nouvelle version."""
    from app.core.demo_guard import refuser_demo
    refuser_demo(current_user, "déposer des documents")     # défense en profondeur (middleware démo)
    # Seule la version COURANTE et active se remplace : remplacer un document à la corbeille
    # ou une ancienne version créait une version « vivante » orpheline de son historique.
    old_doc = db.query(Document).filter(
        Document.id == doc_id, Document.user_id.in_(member_ids(current_user, db)),
        Document.deleted_at.is_(None), Document.parent_id.is_(None),
    ).first()
    if not old_doc:
        raise HTTPException(status_code=404, detail="Document introuvable (peut-être à la corbeille "
                                                    "ou déjà remplacé) : rechargez la liste.")

    # Sauvegarder la nouvelle version
    content, ext = _validate_and_read(file)
    file_key = f"{current_user.id}/{uuid.uuid4().hex}{ext}"
    mime = mime_for(file_key)       # dérivé de l'extension, pas du client
    get_storage().save(file_key, content, mime)

    exp_date = None
    if expiration_date:
        try:
            exp_date = date.fromisoformat(expiration_date)
        except ValueError:
            exp_date = old_doc.expiration_date

    # Créer la nouvelle version = version COURANTE (parent_id NULL → visible dans la liste
    # et les alertes d'expiration, qui filtrent sur parent_id IS NULL).
    new_doc = Document(
        user_id=current_user.id,
        name=old_doc.name,
        category=old_doc.category,
        file_key=file_key,
        file_size=len(content),
        mime_type=mime,
        expiration_date=exp_date or old_doc.expiration_date,
        version=old_doc.version + 1,
        parent_id=None,
        # Conserver le rattachement : sans ça, remplacer une pièce la sortait de son AO
        # et de son dossier → elle disparaissait des exports du marché concerné.
        project_id=old_doc.project_id,
        folder=old_doc.folder,
    )
    db.add(new_doc)
    db.flush()                      # obtenir new_doc.id avant d'y rattacher l'ancien
    # L'ancienne version devient enfant (archivée, masquée) — par UPDATE CONDITIONNEL : deux
    # remplacements simultanés (double-clic, deux membres) créaient sinon deux versions
    # « courantes » dont une sans historique. Le second voit 0 ligne modifiée → 409.
    hit = db.query(Document).filter(
        Document.id == old_doc.id, Document.parent_id.is_(None), Document.deleted_at.is_(None),
    ).update({Document.parent_id: new_doc.id}, synchronize_session=False)
    if hit != 1:
        db.rollback()
        try:
            get_storage().delete(file_key)
        except Exception:
            pass
        raise HTTPException(status_code=409, detail="Ce document vient d'être remplacé ou supprimé. "
                                                    "Rechargez la liste puis réessayez.")
    db.commit()
    db.refresh(new_doc)

    return {
        "id": new_doc.id,
        "name": new_doc.name,
        "version": new_doc.version,
        "message": "Document mis à jour",
    }


@router.patch("/{doc_id}", status_code=200)
def rename_document(
    doc_id: int,
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Renommer un document (titre affiché dans le coffre-fort)."""
    doc = db.query(Document).filter(
        Document.id == doc_id, Document.user_id.in_(member_ids(current_user, db)),
        Document.deleted_at.is_(None), Document.parent_id.is_(None),
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Le nom ne peut pas être vide")
    doc.name = name[:500]
    db.commit()
    return {"id": doc.id, "name": doc.name}


@router.delete("/{doc_id}", status_code=204)
def delete_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mettre un document à la corbeille (suppression douce, réversible).
    Le fichier de stockage est conservé tant que la corbeille n'est pas purgée."""
    doc = db.query(Document).filter(
        Document.id == doc_id, Document.user_id.in_(member_ids(current_user, db)),
        Document.deleted_at.is_(None),
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    from app.models import utcnow
    now = utcnow()
    doc.deleted_at = now
    # Les ANCIENNES versions (chaîne parent_id → version plus récente) suivent le document
    # à la corbeille : sinon elles restaient téléchargeables et hors de la purge à 30 jours.
    old_ids = _older_version_ids(db, doc.id, member_ids(current_user, db))
    if old_ids:
        db.query(Document).filter(Document.id.in_(old_ids), Document.deleted_at.is_(None)).update(
            {Document.deleted_at: now}, synchronize_session=False)
    db.commit()


def _older_version_ids(db: Session, doc_id: int, owners) -> list:
    """Toutes les anciennes versions d'un document (transitivement), dans le périmètre."""
    ids, frontier = set(), {doc_id}
    while frontier:
        rows = db.query(Document.id).filter(
            Document.parent_id.in_(list(frontier)), Document.user_id.in_(owners)).all()
        children = {r[0] for r in rows} - ids - {doc_id}
        ids |= children
        frontier = children
    return list(ids)


@router.post("/{doc_id}/restore", status_code=200)
def restore_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Restaurer un document depuis la corbeille (annulation de suppression)."""
    doc = db.query(Document).filter(
        Document.id == doc_id, Document.user_id.in_(member_ids(current_user, db)),
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    # Ancienne version dont la version COURANTE est à la corbeille : on restaure la tête de
    # chaîne (et les versions jetées avec elle). Sinon la version restaurée devenait « vivante »
    # mais invisible, puis effacée avec la tête à la purge des 30 jours.
    owners = member_ids(current_user, db)
    head, hops = doc, 0
    while head.parent_id is not None and hops < 200:
        nxt = db.query(Document).filter(Document.id == head.parent_id,
                                        Document.user_id.in_(owners)).first()
        if not nxt:
            break
        head, hops = nxt, hops + 1
    if head is not doc and head.deleted_at is not None:
        doc = head
    trashed_at = doc.deleted_at
    doc.deleted_at = None
    # Restaure aussi les anciennes versions mises à la corbeille EN MÊME TEMPS que lui
    # (même horodatage) — pas celles qu'on aurait jetées séparément auparavant.
    if trashed_at is not None:
        old_ids = _older_version_ids(db, doc.id, member_ids(current_user, db))
        if old_ids:
            db.query(Document).filter(Document.id.in_(old_ids),
                                      Document.deleted_at == trashed_at).update(
                {Document.deleted_at: None}, synchronize_session=False)
    db.commit()
    return {"ok": True, "id": doc.id}


@router.get("/{doc_id}/download")
def download_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Télécharger un document. S3 → URL signée ; local → flux direct."""
    doc = db.query(Document).filter(
        Document.id == doc_id, Document.user_id.in_(member_ids(current_user, db))
    ).first()
    if not doc or not doc.file_key:
        raise HTTPException(404, "Document introuvable")
    storage = get_storage()
    signed = storage.url(doc.file_key, filename=doc.name)
    if signed:
        return RedirectResponse(signed)
    try:
        content = storage.load(doc.file_key)
    except FileNotFoundError:
        raise HTTPException(410, "Fichier absent du stockage")
    # Type recalculé depuis l'extension de la clé (validée à l'envoi), jamais doc.mime_type :
    # les anciennes lignes portent encore le type annoncé par le navigateur.
    return StreamingResponse(
        io.BytesIO(content),
        media_type=mime_for(doc.file_key),
        headers=file_headers(doc.name, doc.file_key),
    )


@router.get("/expiring")
def get_expiring_documents(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Récupérer les documents qui expirent dans les X prochains jours."""
    from datetime import timedelta
    # Bornage : days=99999999 provoquait un OverflowError (500) dans timedelta.
    days = max(0, min(int(days or 0), 3650))
    threshold = date.today() + timedelta(days=days)

    docs = db.query(Document).filter(
        Document.user_id.in_(member_ids(current_user, db)),
        Document.expiration_date.isnot(None),
        Document.expiration_date <= threshold,
        Document.parent_id.is_(None),
        Document.deleted_at.is_(None),
    ).order_by(Document.expiration_date).all()

    return [{
        "id": d.id,
        "name": d.name,
        "expiration_date": str(d.expiration_date),
        "days_remaining": (d.expiration_date - date.today()).days,
    } for d in docs]
