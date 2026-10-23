"""
Routes des ÉCRANS « Mes preuves » (rédaction, vague 3, E1), en plus du socle (app/routers/preuves.py) :

  GET  /api/preuves/reprise                                   ce qui peut être repris d'ailleurs dans Adjugo
  POST /api/preuves/reprise                                   {cles: [...]} → reprend ce qui a été coché
  GET  /api/atelier/{project_id}/preuves                      fiches insérables dans l'atelier de ce marché
  POST /api/atelier/{project_id}/sections/{section_id}/inserer-preuve
                                                              {preuve_id, base_version_id} → fiche ajoutée
                                                              telle quelle à la partie, sans IA

Monté AVANT le socle (sinon « /api/preuves/reprise » serait lu comme une preuve n° « reprise »).
Portée : l'organisation (data_owner_id) ; un marché d'un autre compte → 404 ; erreurs métier :
`detail` = {code, message}. Aucune IA.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.org import data_owner_id
from app.core.ratelimit import limiter
from app.core.security import get_current_user
from app.models import User
from app.services import atelier as at
from app.services import preuves as pv
from app.services import preuves_atelier as pa
from app.services import preuves_reprise as rp

router = APIRouter(tags=["Mes preuves"])


@router.get("/api/preuves/reprise")
def reprise_apercu(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Ce que l'entreprise a déjà saisi ailleurs (profil, réseau, coffre-fort) et qui n'est pas
    encore dans « Mes preuves ». Rien n'est créé."""
    return rp.apercu(db, data_owner_id(current_user, db))


class RepriseIn(BaseModel):
    cles: List[str] = Field(default_factory=list, max_length=500)


@router.post("/api/preuves/reprise")
@limiter.limit("60/hour")
def reprise(request: Request, body: RepriseIn, current_user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    owner = data_owner_id(current_user, db)
    try:
        r = rp.reprendre(db, owner, body.cles, user=current_user)
    except pv.PreuveError as e:
        db.rollback()
        raise HTTPException(e.status, e.detail())
    etat = pv._Etat(db, owner, r["creees"])
    jour = pv.aujourd_hui()
    return {"creees": [pv.preuve_out(db, p, etat, jour) for p in r["creees"]], "deja": r["deja"],
            "ignorees": r["ignorees"]}


# ── Dans l'atelier du dossier de présentation ─────────────────────────────────────────

def _acces(db: Session, user: User, project_id: int):
    from app.routers.atelier import _Acces
    return _Acces(db, user, project_id)


@router.get("/api/atelier/{project_id}/preuves")
def atelier_fiches(project_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = _acces(db, current_user, project_id)
    return pa.fiches(db, acc.owner_id, acc.project.id)


class InsererIn(BaseModel):
    preuve_id: int
    base_version_id: Optional[int] = None


@router.post("/api/atelier/{project_id}/sections/{section_id}/inserer-preuve")
@limiter.limit("600/hour")
def atelier_inserer(request: Request, project_id: int, section_id: int, body: InsererIn,
                    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """La fiche choisie, telle quelle, à la fin de la partie (nouvelle version, aucune IA)."""
    from app.routers.atelier import _section
    acc = _acces(db, current_user, project_id)
    s = acc.section(section_id)
    try:
        pa.inserer(db, acc.contexte(), s, acc.lecteur, acc.owner_id, acc.project.id, body.preuve_id,
                   body.base_version_id)
    except at.AtelierError as e:
        db.rollback()
        raise HTTPException(e.status, e.detail())
    return _section(acc, s)
