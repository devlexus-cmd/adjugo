"""
Rangement automatique des documents dans le dossier d'un appel d'offres.
Réutilise le coffre-fort (modèle Document) + la couche de stockage.
Chaque pièce porte `project_id` (l'AO) et `folder` (l'arborescence).
"""
import uuid
import os
from app.services.storage import get_storage
from app.models import Document

# Arborescence type d'un dossier d'AO
FOLDERS = ["DCE", "CERFA", "Mémoire technique", "Pièces administratives",
           "Devis", "Sous-traitance", "Correspondances"]


def save_to_dossier(db, user_id: int, project_id: int, folder: str,
                    name: str, content: bytes, mime: str = "application/pdf") -> Document:
    ext = os.path.splitext(name)[1] or ""
    file_key = f"{user_id}/{uuid.uuid4().hex}{ext}"
    get_storage().save(file_key, content, mime)
    doc = Document(user_id=user_id, project_id=project_id, folder=folder,
                   name=name, file_key=file_key, file_size=len(content),
                   mime_type=mime, category="autre")
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def replace_in_dossier(db, user_id: int, project_id: int, folder: str,
                       name: str, content: bytes, mime: str = "application/pdf") -> Document:
    """Comme save, mais remplace une pièce du même nom dans le même dossier
    (évite les doublons quand on régénère les CERFA)."""
    old = db.query(Document).filter(
        Document.user_id == user_id, Document.project_id == project_id,
        Document.folder == folder, Document.name == name).all()
    for d in old:
        try:
            get_storage().delete(d.file_key)
        except Exception:
            pass
        db.delete(d)
    db.commit()
    return save_to_dossier(db, user_id, project_id, folder, name, content, mime)
