"""
Router de l'ENTRETIEN CHANTIER (rédaction, vague 5 — D : « Adjugo demande au lieu de deviner »).

Contrat complet : docs/REDACTION_V5.md (section D). Toute la logique est dans app/services/entretien_chantier.py ;
ici : contrôle d'accès et traduction des erreurs métier (`detail` = {code, message, …}).

Chef de file (compte, portée organisation — le marché doit appartenir à son organisation, sinon 404) :
  GET  /api/atelier/{pid}/entretien                       les questions (ou la proposition, rien d'enregistré)
  POST /api/atelier/{pid}/entretien                       préparer l'entretien (idempotent, sans IA)
  PUT  /api/atelier/{pid}/entretien/{qid}                 répondre, passer, « sans objet », remettre à répondre
  PUT  /api/atelier/{pid}/entretien/{qid}/adresse         poser la question à un partenaire, ou la reprendre
  POST /api/atelier/{pid}/entretien/ia                    « Chercher d'autres questions avec Adjugo » (IA, option)

Partenaire — par le lien de son invitation (+ clé de son espace) ou par le compte qui a rattaché ce lien :
  PUT  /api/invite/{token}/redaction/entretien/{qid}      répondre à une question qui LUI est posée
  PUT  /api/shared/{pid}/redaction/entretien/{qid}        idem, depuis « Partagé avec moi »
Les questions qui lui sont posées se lisent dans GET …/redaction (clé `entretien`).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.ratelimit import limiter
from app.core.security import get_current_user
from app.models import User
from app.services import atelier as at
from app.services import entretien_chantier as ec

router = APIRouter(tags=["Entretien chantier (rédaction, vague 5)"])

DEMO_ACTION = "préparer votre dossier de présentation"


def _err(e: at.AtelierError):
    return HTTPException(e.status, e.detail())


def _refuser_demo(user: User, action: str = DEMO_ACTION) -> None:
    """Défense en profondeur, derrière le garde central : la vitrine de la démo ne change pas."""
    from app.core.demo_guard import refuser_demo
    refuser_demo(user, action)


def _acces(db: Session, user: User, project_id: int):
    from app.routers.atelier import _Acces
    acc = _Acces(db, user, project_id)
    acc.exiger_dossier()
    return acc


def _etat(acc) -> dict:
    return ec.etat(acc.db, acc.project, acc.dossier, acc.lecteur, acc.mids)


# ── Chef de file ─────────────────────────────────────────────────────────────────────

@router.get("/api/atelier/{project_id}/entretien")
def lire(project_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Les questions sur ce chantier ; pas encore préparé : la proposition (rien n'est enregistré)."""
    return _etat(_acces(db, current_user, project_id))


@router.post("/api/atelier/{project_id}/entretien")
@limiter.limit("120/hour")
def preparer(request: Request, project_id: int, current_user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    """Enregistre l'entretien (idempotent, sans IA, sans débit) ; un dossier réimporté le remet à jour."""
    _refuser_demo(current_user)
    acc = _acces(db, current_user, project_id)
    try:
        res = ec.preparer(db, acc.project, acc.dossier, acc.lecteur, acc.mids)
    except at.AtelierError as e:
        raise _err(e)
    return dict(_etat(acc), preparation=res)


class RepondreIn(BaseModel):
    statut: str = ec.REPONDUE
    reponse: Optional[str] = Field(None, max_length=ec.REPONSE_MAX + 500)
    preuve_id: Optional[int] = None
    lock_version: Optional[int] = None


@router.put("/api/atelier/{project_id}/entretien/{question_id}")
@limiter.limit("600/hour")
def repondre(request: Request, project_id: int, question_id: int, body: RepondreIn,
             current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _refuser_demo(current_user)
    acc = _acces(db, current_user, project_id)
    try:
        r = ec.repondre(db, acc.project, acc.dossier, acc.lecteur, question_id, statut=body.statut, reponse=body.reponse,
                        preuve_id=body.preuve_id, lock_version=body.lock_version)
    except at.AtelierError as e:
        db.rollback()
        raise _err(e)
    return dict(_etat(acc), question_id=r.id)


class AdresseIn(BaseModel):
    invite_id: Optional[int] = None
    confirmer: bool = False


@router.put("/api/atelier/{project_id}/entretien/{question_id}/adresse")
@limiter.limit("600/hour")
def adresser(request: Request, project_id: int, question_id: int, body: AdresseIn,
             current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Pose la question à un partenaire du groupement (`invite_id`), ou la reprend (`null`). Aucun email."""
    from app.services.audit import client_ip
    _refuser_demo(current_user)
    acc = _acces(db, current_user, project_id)
    try:
        r = ec.adresser(db, acc.project, acc.dossier, acc.lecteur, question_id, body.invite_id, confirmer=body.confirmer,
                        ip=client_ip(request))
    except at.AtelierError as e:
        db.rollback()
        raise _err(e)
    return dict(_etat(acc), question_id=r.id)


class EntretienIaIn(BaseModel):
    accepte_debit: bool = False


@router.post("/api/atelier/{project_id}/entretien/ia", status_code=202)
@limiter.limit("10/hour")
def chercher_avec_ia(request: Request, project_id: int, body: Optional[EntretienIaIn] = None,
                     current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Questions supplémentaires proposées par l'IA, chacune gardée seulement si sa phrase du dossier est retrouvée
    mot pour mot. Tâche de fond : suivre /api/atelier/{pid}/taches/{job_id}."""
    _refuser_demo(current_user, "rédiger avec Adjugo")
    if not getattr(current_user, "email_verified", True):
        raise HTTPException(403, {"code": "email_non_confirme",
                                  "message": "Confirmez votre adresse email pour utiliser cette fonctionnalité."})
    acc = _acces(db, current_user, project_id)
    try:
        job = ec.lancer_ia(db, current_user, acc.project, acc.dossier, acc.lecteur, acc.mids,
                           accepte_debit=bool(body and body.accepte_debit))
    except at.AtelierError as e:
        raise _err(e)
    db.refresh(acc.dossier)
    return {"tache": at.job_public(job), "quota": at.quota_out(acc.dossier)}


# ── Partenaire ───────────────────────────────────────────────────────────────────────

class ReponsePartenaireIn(BaseModel):
    statut: str = ec.REPONDUE
    reponse: Optional[str] = Field(None, max_length=ec.REPONSE_MAX + 500)
    avertissement_lu: bool = False
    lock_version: Optional[int] = None


def _repondre_partenaire(acces, db: Session, question_id: int, body: ReponsePartenaireIn, request: Request) -> dict:
    from app.services.audit import client_ip
    try:
        ec.repondre_partenaire(db, acces, question_id, statut=body.statut, reponse=body.reponse,
                               avertissement_lu=body.avertissement_lu, lock_version=body.lock_version,
                               ip=client_ip(request))
    except at.AtelierError as e:
        db.rollback()
        raise _err(e)
    return ec.vue_partenaire(db, acces)


@router.put("/api/invite/{token}/redaction/entretien/{question_id}")
@limiter.limit("300/hour")
def lien_repondre(token: str, question_id: int, body: ReponsePartenaireIn, request: Request,
                  db: Session = Depends(get_db)):
    from app.routers.atelier_groupement import _par_lien
    return _repondre_partenaire(_par_lien(token, db, request, ecrire=True), db, question_id, body, request)


@router.put("/api/shared/{project_id}/redaction/entretien/{question_id}")
@limiter.limit("300/hour")
def compte_repondre(project_id: int, question_id: int, body: ReponsePartenaireIn, request: Request,
                    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.routers.atelier_groupement import DEMO_ACTION_PART, _par_compte
    _refuser_demo(current_user, DEMO_ACTION_PART)
    return _repondre_partenaire(_par_compte(project_id, current_user, db), db, question_id, body, request)
