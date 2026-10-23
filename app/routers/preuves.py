"""
Router « MES PREUVES » (rédaction, vague 3 — socle commun de A, I et E1).

Contrat complet : docs/REDACTION_V3_PREUVES.md. Toutes les règles sont dans app/services/preuves.py ;
ici : portée de l'organisation (une preuve d'un autre compte → 404, jamais 403), lecture des corps
de requête et traduction des erreurs métier (`detail` = {code, message, …}).
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.org import data_owner_id
from app.core.ratelimit import limiter
from app.core.security import get_current_user
from app.models import User
from app.services import preuves as pv

router = APIRouter(prefix="/api/preuves", tags=["Mes preuves"])


def _err(e: pv.PreuveError):
    return HTTPException(e.status, e.detail())


def _nf():
    return HTTPException(404, {"code": "preuve_introuvable", "message": "Preuve introuvable."})


def _owner(user: User, db: Session) -> int:
    return data_owner_id(user, db)


def _preuve(db: Session, user: User, preuve_id: int):
    p = pv.get(db, _owner(user, db), preuve_id)
    if p is None:
        raise _nf()
    return p


@router.get("")
def lister(nature: Optional[str] = None, statut: Optional[str] = None,
           current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Les preuves de l'organisation (filtres facultatifs), et ce qu'il faut pour les écrans."""
    if nature and nature not in pv.NATURES:
        raise HTTPException(422, {"code": "nature_invalide", "message": "Type de preuve inconnu."})
    if statut and statut not in pv.STATUTS:
        raise HTTPException(422, {"code": "statut_invalide", "message": "Statut inconnu."})
    owner = _owner(current_user, db)
    ps = pv.lister(db, owner, nature=nature, statut=statut)
    etat = pv._Etat(db, owner, ps)
    jour = pv.aujourd_hui()
    return {
        "preuves": [pv.preuve_out(db, p, etat, jour) for p in ps],
        "compteurs": pv.compteurs(db, owner),
        "natures": [{"code": n, "libelle": pv.NATURE_LIBELLES[n]} for n in pv.NATURES],
        "types_source": [{"code": t, "libelle": pv.TYPE_SOURCE_LIBELLES[t],
                          "natures": list(pv.NATURES_PAR_SOURCE[t])} for t in pv.TYPES_SOURCE],
    }


class PreuveIn(BaseModel):
    nature: str
    valeur: dict
    type_source: str = pv.DECLARE
    source: Optional[dict] = None
    date_source: Optional[date] = None
    date_fin_validite: Optional[date] = None
    statut: str = pv.ACCEPTEE


@router.post("", status_code=201)
@limiter.limit("300/hour")
def creer(request: Request, body: PreuveIn, current_user: User = Depends(get_current_user),
          db: Session = Depends(get_db)):
    try:
        p = pv.creer(db, _owner(current_user, db), nature=body.nature, valeur=body.valeur,
                     type_source=body.type_source, source=body.source, date_source=body.date_source,
                     date_fin_validite=body.date_fin_validite, statut=body.statut, origine="saisie",
                     user=current_user)
    except pv.PreuveError as e:
        db.rollback()
        raise _err(e)
    return pv.preuve_out(db, p)


@router.get("/{preuve_id}")
def lire(preuve_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return pv.preuve_out(db, _preuve(db, current_user, preuve_id))


class PreuvePatch(BaseModel):
    valeur: Optional[dict] = None
    type_source: Optional[str] = None
    source: Optional[dict] = None
    date_source: Optional[date] = None
    date_fin_validite: Optional[date] = None
    version: Optional[int] = None


@router.patch("/{preuve_id}")
@limiter.limit("600/hour")
def modifier(request: Request, preuve_id: int, body: PreuvePatch, current_user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    """Seuls les champs ENVOYÉS changent (une date envoyée à null est effacée)."""
    p = _preuve(db, current_user, preuve_id)
    sent = body.model_fields_set
    kw = {k: getattr(body, k) for k in ("valeur", "type_source", "source", "date_source", "date_fin_validite")
          if k in sent}
    if "valeur" in kw and kw["valeur"] is None:
        raise HTTPException(422, {"code": "valeur_invalide", "message": "Les champs de la preuve sont attendus."})
    if "type_source" in kw and kw["type_source"] is None:
        raise HTTPException(422, {"code": "type_source_invalide", "message": "Source attendue."})
    try:
        p = pv.modifier(db, p, user=current_user, version=body.version, **kw)
    except pv.PreuveError as e:
        db.rollback()
        raise _err(e)
    return pv.preuve_out(db, p)


class VersionIn(BaseModel):
    version: Optional[int] = None


@router.post("/{preuve_id}/accepter")
@limiter.limit("600/hour")
def accepter(request: Request, preuve_id: int, body: Optional[VersionIn] = None,
             current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _preuve(db, current_user, preuve_id)
    try:
        p = pv.accepter(db, p, current_user, version=body.version if body else None)
    except pv.PreuveError as e:
        db.rollback()
        raise _err(e)
    return pv.preuve_out(db, p)


@router.post("/{preuve_id}/retirer")
@limiter.limit("600/hour")
def retirer(request: Request, preuve_id: int, body: Optional[VersionIn] = None,
            current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _preuve(db, current_user, preuve_id)
    try:
        p = pv.retirer(db, p, current_user, version=body.version if body else None)
    except pv.PreuveError as e:
        db.rollback()
        raise _err(e)
    return pv.preuve_out(db, p)


@router.delete("/{preuve_id}", status_code=204)
@limiter.limit("600/hour")
def supprimer(request: Request, preuve_id: int, current_user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """Efface définitivement le contenu (CV compris) ; le numéro reste réservé."""
    pv.supprimer(db, _preuve(db, current_user, preuve_id), current_user)
    return Response(status_code=204)


@router.get("/{preuve_id}/passage")
def passage(preuve_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Le passage exact dans son document de « Mon savoir-faire », avec le texte autour."""
    p = _preuve(db, current_user, preuve_id)
    try:
        return pv.passage(db, p)
    except pv.PreuveError as e:
        raise _err(e)
