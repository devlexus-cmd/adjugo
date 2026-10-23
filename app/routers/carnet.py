"""
Router du CARNET DE NOTES (rédaction, vague 6 — F de l'étude, § 6.11).

Contrat : docs/REDACTION_V6.md (section F). Toute la logique est dans app/services/carnet_notes.py ; ici : contrôle
d'accès (le marché doit appartenir à l'organisation de l'utilisateur, hors corbeille, sinon 404), lecture des corps
et traduction des erreurs métier (`detail` = {code, message}).

Démo (vitrine partagée) : les lectures restent ouvertes (le carnet du marché perdu de la vitrine, le courrier
pré-rempli, « Où vous perdez des points », la lecture SANS IA d'un courrier collé, qui n'écrit rien) ; toute écriture
du carnet et la lecture avec l'IA sont refusées par le garde central (app/core/demo_guard.py) ET dans la route.
"""
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.org import member_ids
from app.core.ratelimit import limiter
from app.core.security import get_current_user
from app.models import Project, User
from app.services import carnet_notes as cn

router = APIRouter(prefix="/api/carnet", tags=["Carnet de notes"])


def _err(e: cn.CarnetError):
    return HTTPException(e.status, e.detail())


def _projet(db: Session, user: User, project_id: int) -> tuple:
    mids = member_ids(user, db)
    p = db.query(Project).filter(Project.id == project_id, Project.user_id.in_(mids),
                                 Project.deleted_at.is_(None)).first()
    if p is None:
        raise HTTPException(404, {"code": "marche_introuvable", "message": "Marché introuvable."})
    return p, mids


def _demo(user: User, action: str) -> None:
    from app.core.demo_guard import refuser_demo
    refuser_demo(user, action)        # défense en profondeur derrière le garde central


# ── Lectures ─────────────────────────────────────────────────────────────────────────

@router.get("/tableau")
def tableau(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """« Où vous perdez des points » et les rappels « Demandez vos notes » : marchés de l'organisation seulement."""
    return cn.tableau(db, current_user, member_ids(current_user, db))


@router.get("/{project_id}")
def lire(project_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p, mids = _projet(db, current_user, project_id)
    return cn.etat(db, p, current_user, mids)


@router.get("/{project_id}/courrier")
def lire_courrier_demande(project_id: int, procedure: Optional[str] = None,
                          current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Le courrier « Demandez vos notes », pré-rempli. Adjugo ne l'envoie jamais (lecture seule)."""
    p, _mids = _projet(db, current_user, project_id)
    if cn._statut(p) != cn.PERDU:
        raise HTTPException(409, {"code": "marche_pas_perdu",
                                  "message": "Le courrier se prépare pour un marché passé à « Perdu »."})
    proc = procedure if procedure in (cn.ADAPTEE, cn.FORMALISEE, "inconnue", "") else None
    return cn.courrier(db, p, procedure=cn.INCONNUE if proc == "inconnue" else proc)


# ── Lecture d'un courrier collé (rien n'est enregistré) ──────────────────────────────

class CourrierIn(BaseModel):
    courrier: str = Field("", max_length=cn.COURRIER_MAX + 1000)


@router.post("/{project_id}/lire")
@limiter.limit("60/hour")
def lire_courrier(request: Request, project_id: int, body: CourrierIn, current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Lecture SANS IA du courrier collé : des propositions, jamais enregistrées (l'utilisateur valide ensuite)."""
    p, _mids = _projet(db, current_user, project_id)
    try:
        texte = cn._texte_courrier(body.courrier)
    except cn.CarnetError as e:
        raise _err(e)
    from app.core.org import data_owner_id
    # Vague 6 (J) : plusieurs lots — les critères de chaque lot, le courrier découpé par lot (sans IA).
    lignes = cn.criteres_pour_lecture(p, cn.lots_du_marche(db, p, data_owner_id(current_user, db)))
    return cn.lire_courrier(texte, lignes)


@router.post("/{project_id}/lire-ia")
@limiter.limit("20/hour")
def lire_courrier_ia(request: Request, project_id: int, body: CourrierIn,
                     current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """« Lire avec l'IA » (option) : chaque nombre proposé est retrouvé tel quel dans le courrier ; rien n'est
    enregistré. Compte comme une question du jour, rendue si l'IA tombe ou si rien n'est retenu."""
    _demo(current_user, "lancer une analyse IA")
    p, mids = _projet(db, current_user, project_id)
    try:
        return cn.lire_courrier_ia(db, current_user, p, body.courrier, mids)
    except cn.CarnetError as e:
        raise _err(e)


# ── Écritures (refusées à la démo) ───────────────────────────────────────────────────

class LigneIn(BaseModel):
    cle: str = ""
    critere: str = ""
    parent: str = ""
    poids: str = ""
    note: Optional[Union[float, str]] = None
    note_max: Optional[Union[float, str]] = None
    note_gagnant: Optional[Union[float, str]] = None
    commentaire: str = Field("", max_length=4000)
    famille: str = ""
    origine: str = cn.SAISIE
    extrait_note: str = Field("", max_length=2000)
    extrait_gagnant: str = Field("", max_length=2000)
    commentaire_du_courrier: bool = False
    lot: str = Field("", max_length=4)        # vague 6 (J) : critère ajouté d'un marché à plusieurs lots


class NotesIn(BaseModel):
    lignes: List[LigneIn] = Field(default_factory=list)
    rev: Optional[int] = None
    courrier: Optional[str] = Field(None, max_length=cn.COURRIER_MAX + 1000)


@router.put("/{project_id}/notes")
@limiter.limit("60/hour")
def enregistrer(request: Request, project_id: int, body: NotesIn, current_user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """Les notes VALIDÉES par l'utilisateur ; les familles proposées sont confirmées par cet enregistrement."""
    _demo(current_user, "saisir vos notes")
    p, mids = _projet(db, current_user, project_id)
    try:
        cn.enregistrer(db, p, current_user, [x.model_dump() for x in body.lignes], rev=body.rev,
                       courrier_txt=body.courrier)
    except cn.CarnetError as e:
        db.rollback()
        raise _err(e)
    db.refresh(p)
    return cn.etat(db, p, current_user, mids)


class DemandeIn(BaseModel):
    envoyee: bool = True


@router.post("/{project_id}/demande")
@limiter.limit("60/hour")
def demande(request: Request, project_id: int, body: Optional[DemandeIn] = None,
            current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """« J'ai envoyé ma demande » (Adjugo n'a rien envoyé) : le rappel s'arrête."""
    _demo(current_user, "saisir vos notes")
    p, mids = _projet(db, current_user, project_id)
    try:
        cn.marquer_demande(db, p, current_user, envoyee=body.envoyee if body is not None else True)
    except cn.CarnetError as e:
        db.rollback()
        raise _err(e)
    db.refresh(p)
    return cn.etat(db, p, current_user, mids)


@router.post("/{project_id}/rappel/masquer")
@limiter.limit("60/hour")
def masquer_rappel(request: Request, project_id: int, current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    _demo(current_user, "saisir vos notes")
    p, mids = _projet(db, current_user, project_id)
    cn.masquer_rappel(db, p, current_user)
    db.refresh(p)
    return cn.etat(db, p, current_user, mids)


@router.post("/{project_id}/savoir-faire")
@limiter.limit("20/hour")
def savoir_faire(request: Request, project_id: int, current_user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """Marché gagné : le texte de VOS parties rejoint « Mon savoir-faire », à votre initiative (sans IA)."""
    _demo(current_user, "enrichir votre savoir-faire")
    p, _mids = _projet(db, current_user, project_id)
    try:
        return cn.ajouter_au_savoir_faire(db, p, current_user)
    except cn.CarnetError as e:
        db.rollback()
        raise _err(e)
