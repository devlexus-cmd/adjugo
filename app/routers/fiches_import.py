"""
Router « PARTIR DE VOS ANCIENS DOSSIERS » (rédaction, vague 3, chantier I — étude § 6.6).

Dans « Mon savoir-faire » : Adjugo lit un document importé UNE fois et PROPOSE des fiches de preuves,
chacune avec le passage où il l'a trouvée ; l'utilisateur coche ce qu'il garde avec les routes du
socle (POST /api/preuves/{id}/accepter et /retirer). Toutes les règles sont dans
app/services/fiches_import.py ; contrat : docs/REDACTION_V3_IMPORT.md.

Portée : l'organisation (data_owner_id, comme « Mes preuves ») ; un document d'un autre compte →
404. Erreurs métier : `detail` = {code, message}. Compte démo : 403 (lecture guidée).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.org import data_owner_id
from app.core.ratelimit import limiter
from app.core.security import get_current_user
from app.models import User
from app.services import fiches_import as fi

router = APIRouter(prefix="/api/knowledge", tags=["Mes preuves : partir de vos anciens dossiers"])


def _nf():
    return HTTPException(404, {"code": "document_introuvable", "message": fi.MSG_INTROUVABLE})


@router.get("/fiches")
def etat_documents(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Pour la liste « Mon savoir-faire » : statut de chaque document (à lire, en cours, lu, échec,
    CV, pièce d'un acheteur, rien à lire), fiches à cocher et cochées, plafond du mois."""
    return fi.etat_documents(db, data_owner_id(current_user, db))


@router.get("/{doc_id}/fiches")
def etat_document(doc_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owner = data_owner_id(current_user, db)
    doc = fi.document(db, owner, doc_id)
    if doc is None:
        raise _nf()
    return fi.etat_document(db, owner, doc)


class LectureIn(BaseModel):
    date_document: Optional[str] = None


@router.post("/{doc_id}/fiches")
@limiter.limit("30/hour")
def proposer(request: Request, doc_id: int, body: Optional[LectureIn] = None,
             current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """« Proposer des fiches à partir de ce document » : 202 si la lecture est lancée (tâche de fond),
    200 si le document est déjà lu ou en cours de lecture (aucun nouvel appel à l'IA)."""
    owner = data_owner_id(current_user, db)
    try:
        etat, lancee = fi.lancer(db, current_user, owner, doc_id, (body.date_document if body else None))
    except fi.ImportError_ as e:
        if e.code == "demo":
            raise HTTPException(403, e.message)
        if e.code == "adresse_a_confirmer":
            raise HTTPException(403, e.message)
        raise HTTPException(e.status, e.detail())
    return JSONResponse(etat, status_code=202 if lancee else 200)
