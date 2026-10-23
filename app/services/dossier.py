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
    # Le DCE importé garde le nom ET le type annoncés par le navigateur : on n'en retient que
    # le type dérivé de l'extension (table fixe), jamais « text/html » ou « image/svg+xml ».
    from app.core.mime import mime_for
    mime = mime_for(file_key)
    get_storage().save(file_key, content, mime)
    doc = Document(user_id=user_id, project_id=project_id, folder=folder,
                   name=name, file_key=file_key, file_size=len(content),
                   mime_type=mime, category="autre")
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _comptes_de_l_organisation(db, user_id: int) -> list:
    """Les comptes de l'organisation de `user_id` (member_ids) : le dossier d'un marché est celui de l'ORGANISATION,
    comme sa liste de pièces (projects.project_documents) et son export. Repli : le seul compte."""
    from app.core.org import member_ids
    from app.models import User
    u = db.get(User, user_id)
    return member_ids(u, db) if u is not None else [user_id]


def remove_from_dossier(db, user_id: int, project_id: int, folder: str, names) -> int:
    """Retire du dossier d'un AO les pièces GÉNÉRÉES de ces noms exacts (ex. ancienne archive
    « memoire_technique.md »), quel que soit le collègue de l'organisation qui les a rangées. Ne touche à rien
    d'autre (ni autre dossier, ni autre marché, ni une autre organisation). Contrôle des bugs (octobre 2026) : seules
    les pièces du compte courant étaient retirées ; « Préparer mes documents » lancé par deux collègues laissait un
    DC1.pdf, un DC2.pdf… par collègue (l'ancien jeu, périmé, à côté du nouveau, et deux fois dans le ZIP), de même
    pour le dossier de présentation exporté et pour le dossier de l'acheteur ré-importé."""
    names = [n for n in (names or []) if n]
    if not names:
        return 0
    old = db.query(Document).filter(
        Document.user_id.in_(_comptes_de_l_organisation(db, user_id)), Document.project_id == project_id,
        Document.folder == folder, Document.name.in_(names)).all()
    for d in old:
        try:
            get_storage().delete(d.file_key)
        except Exception:
            pass
        db.delete(d)
    db.commit()
    return len(old)


def replace_in_dossier(db, user_id: int, project_id: int, folder: str,
                       name: str, content: bytes, mime: str = "application/pdf") -> Document:
    """Comme save, mais remplace une pièce du même nom dans le même dossier
    (évite les doublons quand on régénère les CERFA)."""
    remove_from_dossier(db, user_id, project_id, folder, [name])
    return save_to_dossier(db, user_id, project_id, folder, name, content, mime)
