"""
ESPACE ACHETEUR (collectivités) — comptes cloisonnés + DCE sauvegardés.

Strictement séparé du produit PME : identités dans la table `acheteurs`, JWT avec
`typ="acheteur"` (cf. `get_current_acheteur`). Aucune donnée d'un tenant PME n'est lue ni
écrite. Permet à une collectivité de retrouver et recharger ses projets de DCE.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.ratelimit import limiter
from app.core.security import (hash_password, verify_password, create_access_token,
                               get_current_acheteur, needs_rehash, DUMMY_HASH)
from app.models import Acheteur, AcheteurDce
from app.services.acheteur_demo_seed import DEMO_EMAIL

logger = logging.getLogger("adjugo")
router = APIRouter(prefix="/api/acheteur", tags=["Espace acheteur (collectivités)"])

_MAX_DCES = 200   # garde-fou par compte


def _token(a: Acheteur) -> str:
    # `typ="acheteur"` = la clé du cloisonnement (refusé par l'auth PME).
    return create_access_token(data={"sub": str(a.id), "tv": int(a.token_version or 0),
                                     "typ": "acheteur"})


def _norm_email(e: str) -> str:
    return (e or "").strip().lower()


def _is_demo(a: Acheteur) -> bool:
    return _norm_email(a.email) == DEMO_EMAIL


def _guard_not_demo(a: Acheteur) -> None:
    """Le compte de DÉMO est PARTAGÉ (vitrine publique) : on bloque toute écriture, sinon un
    visiteur corromprait ou supprimerait l'expérience de tous les suivants. Les flux de
    découverte (génération, sourcing, estimation, avis, export) ne touchent pas la base et
    restent disponibles en démo."""
    if _is_demo(a):
        raise HTTPException(403, "Compte de démonstration en lecture seule. Créez un espace gratuit pour enregistrer, piloter et diffuser vos consultations.")


class RegisterIn(BaseModel):
    email: EmailStr = Field(max_length=255)   # validation syntaxique réelle (email-validator)
    password: str = Field(min_length=8, max_length=200)
    nom_collectivite: str = Field(default="", max_length=255)


class LoginIn(BaseModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(max_length=200)


@router.post("/register", status_code=201)
@limiter.limit("5/minute")
def register(request: Request, data: RegisterIn, db: Session = Depends(get_db)):
    email = _norm_email(data.email)
    if email == DEMO_EMAIL:                       # adresse de la vitrine publique : non inscriptible
        raise HTTPException(400, "Adresse réservée.")
    if db.query(Acheteur).filter(func.lower(Acheteur.email) == email).first():
        raise HTTPException(400, "Cet email est déjà utilisé.")
    a = Acheteur(email=email, hashed_password=hash_password(data.password),
                 nom_collectivite=(data.nom_collectivite or "").strip())
    db.add(a)
    db.commit()
    db.refresh(a)
    return {"access_token": _token(a), "token_type": "bearer",
            "nom_collectivite": a.nom_collectivite, "email": a.email}


@router.post("/login")
@limiter.limit("10/minute")
def login(request: Request, data: LoginIn, db: Session = Depends(get_db)):
    a = db.query(Acheteur).filter(func.lower(Acheteur.email) == _norm_email(data.email)).first()
    # Anti-énumération par timing : on exécute TOUJOURS un PBKDF2 équivalent (hash factice si inconnu).
    ok = verify_password(data.password, a.hashed_password if a else DUMMY_HASH)
    if not a or not ok:
        raise HTTPException(401, "Identifiants incorrects.")
    if not a.is_active:
        raise HTTPException(403, "Compte désactivé.")
    # Migration transparente du hachage vers la cible OWASP courante, au login réussi.
    if needs_rehash(a.hashed_password):
        a.hashed_password = hash_password(data.password)
        db.commit()
    return {"access_token": _token(a), "token_type": "bearer",
            "nom_collectivite": a.nom_collectivite, "email": a.email}


@router.post("/demo")
@limiter.limit("30/hour")
def demo(request: Request, db: Session = Depends(get_db)):
    """Connexion au compte de DÉMONSTRATION (collectivité fictive pré-remplie), SANS mot de
    passe — bac à sable public, pour découvrir le produit immédiatement."""
    from app.services.acheteur_demo_seed import ensure_demo_acheteur
    a = ensure_demo_acheteur(db)
    return {"access_token": _token(a), "token_type": "bearer", "demo": True,
            "nom_collectivite": a.nom_collectivite, "email": a.email}


@router.get("/me")
def me(a: Acheteur = Depends(get_current_acheteur)):
    return {"email": a.email, "nom_collectivite": a.nom_collectivite, "demo": _is_demo(a)}


@router.get("/rgpd/export")
def rgpd_export(a: Acheteur = Depends(get_current_acheteur), db: Session = Depends(get_db)):
    """Droit d'accès et de portabilité (RGPD art. 15 & 20) : l'intégralité des données du
    compte acheteur et de ses DCE, en JSON réutilisable."""
    rows = (db.query(AcheteurDce).filter(AcheteurDce.acheteur_id == a.id)
            .order_by(AcheteurDce.id).all())
    return {
        "compte": {"email": a.email, "nom_collectivite": a.nom_collectivite,
                   "cree_le": a.created_at.isoformat() if a.created_at else None},
        "dces": [{**_out(d), "payload": d.payload} for d in rows],
    }


class EffacerIn(BaseModel):
    password: str = Field(max_length=200)


@router.post("/rgpd/effacer")
@limiter.limit("5/hour")
def rgpd_effacer(request: Request, data: EffacerIn,
                 a: Acheteur = Depends(get_current_acheteur), db: Session = Depends(get_db)):
    """Droit à l'effacement (RGPD art. 17) : supprime DÉFINITIVEMENT le compte et tous ses
    DCE. Confirmation par mot de passe — action irréversible."""
    _guard_not_demo(a)
    if not verify_password(data.password, a.hashed_password):
        raise HTTPException(403, "Mot de passe incorrect.")
    db.query(AcheteurDce).filter(AcheteurDce.acheteur_id == a.id).delete()
    db.delete(a)
    db.commit()
    return {"ok": True, "message": "Compte et données supprimés définitivement."}


# ── DCE sauvegardés ──────────────────────────────────────────────────────────
class DceSaveIn(BaseModel):
    id: int | None = None          # si fourni et possédé → mise à jour, sinon création
    objet: str = Field(default="", max_length=500)
    payload: dict


_STATUTS = {"preparation", "publie", "analyse", "attribue", "infructueux"}


def _out(d: AcheteurDce) -> dict:
    return {"id": d.id, "objet": d.objet,
            "statut": getattr(d, "statut", None) or "preparation",
            "date_limite": d.date_limite.isoformat()[:10] if getattr(d, "date_limite", None) else None,
            "diffuse": bool(getattr(d, "date_diffusion", None)),
            "date_diffusion": d.date_diffusion.isoformat()[:10] if getattr(d, "date_diffusion", None) else None,
            "nb_pme_diffusion": getattr(d, "nb_pme_diffusion", None),
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
            "created_at": d.created_at.isoformat() if d.created_at else None}


@router.post("/dce")
@limiter.limit("60/hour")
def save_dce(request: Request, data: DceSaveIn,
             a: Acheteur = Depends(get_current_acheteur), db: Session = Depends(get_db)):
    """Crée ou met à jour un DCE de l'acheteur connecté."""
    _guard_not_demo(a)
    import json
    payload = data.payload or {}
    if not isinstance(payload, dict) or not (payload.get("objet") or data.objet):
        raise HTTPException(422, "DCE vide ou invalide.")
    if len(json.dumps(payload, ensure_ascii=False)) > 400000:
        raise HTTPException(413, "DCE trop volumineux.")
    objet = (data.objet or payload.get("objet") or "Projet de DCE").strip()[:500]

    if data.id is not None:
        d = db.query(AcheteurDce).filter(AcheteurDce.id == data.id,
                                         AcheteurDce.acheteur_id == a.id).first()
        if not d:
            raise HTTPException(404, "DCE introuvable.")
        d.objet = objet
        d.payload = payload
    else:
        if db.query(AcheteurDce).filter(AcheteurDce.acheteur_id == a.id).count() >= _MAX_DCES:
            raise HTTPException(409, "Limite de DCE enregistrés atteinte (supprimez-en).")
        d = AcheteurDce(acheteur_id=a.id, objet=objet, payload=payload)
        db.add(d)
    db.commit()
    db.refresh(d)
    return _out(d)


@router.get("/dce")
def list_dce(a: Acheteur = Depends(get_current_acheteur), db: Session = Depends(get_db)):
    rows = (db.query(AcheteurDce).filter(AcheteurDce.acheteur_id == a.id)
            .order_by(AcheteurDce.updated_at.desc()).limit(_MAX_DCES).all())
    return [_out(d) for d in rows]


@router.get("/dce/{dce_id}")
def get_dce(dce_id: int, a: Acheteur = Depends(get_current_acheteur), db: Session = Depends(get_db)):
    d = db.query(AcheteurDce).filter(AcheteurDce.id == dce_id,
                                     AcheteurDce.acheteur_id == a.id).first()
    if not d:
        raise HTTPException(404, "DCE introuvable.")
    return {**_out(d), "payload": d.payload}


class StatutIn(BaseModel):
    statut: str | None = None
    date_limite: str | None = None     # "AAAA-MM-JJ", "" pour effacer, ou None pour ne pas toucher


@router.post("/dce/{dce_id}/statut")
def set_statut(dce_id: int, data: StatutIn,
               a: Acheteur = Depends(get_current_acheteur), db: Session = Depends(get_db)):
    """Met à jour le statut de pilotage et/ou l'échéance d'une consultation."""
    _guard_not_demo(a)
    d = db.query(AcheteurDce).filter(AcheteurDce.id == dce_id,
                                     AcheteurDce.acheteur_id == a.id).first()
    if not d:
        raise HTTPException(404, "DCE introuvable.")
    if data.statut is not None:
        if data.statut not in _STATUTS:
            raise HTTPException(422, "Statut invalide.")
        d.statut = data.statut
    if data.date_limite is not None:
        if not data.date_limite.strip():
            d.date_limite = None
        else:
            from datetime import datetime
            try:
                d.date_limite = datetime.fromisoformat(data.date_limite.strip()[:10])
            except ValueError:
                raise HTTPException(422, "Date invalide (format AAAA-MM-JJ).")
    db.commit()
    db.refresh(d)
    return _out(d)


class DiffuserIn(BaseModel):
    nb_pme: int | None = Field(default=None, ge=0, le=100000)


@router.post("/dce/{dce_id}/diffuser")
def diffuser(dce_id: int, data: DiffuserIn,
             a: Acheteur = Depends(get_current_acheteur), db: Session = Depends(get_db)):
    """Diffuse la consultation au réseau de PME Adjugo (flywheel) : enregistre la diffusion
    (date + nombre de PME capables touchées) et passe la consultation en « publié ».

    INVARIANT : la diffusion réseau COMPLÈTE la publicité réglementaire (profil acheteur,
    BOAMP/JAL/JOUE selon le seuil), elle ne s'y SUBSTITUE jamais — le dossier reste ouvert à
    tout candidat, y compris hors réseau (égalité de traitement, anti-favoritisme 432-14 CP).
    Le compte `nb_pme` est indicatif (fourni par le client à titre de portée)."""
    _guard_not_demo(a)
    d = db.query(AcheteurDce).filter(AcheteurDce.id == dce_id,
                                     AcheteurDce.acheteur_id == a.id).first()
    if not d:
        raise HTTPException(404, "DCE introuvable.")
    from datetime import datetime, timezone
    # Idempotent : on conserve la 1re date de signalement (pas de réécriture silencieuse à
    # chaque clic). On rafraîchit seulement la portée indicative.
    if not d.date_diffusion:
        d.date_diffusion = datetime.now(timezone.utc)
    d.nb_pme_diffusion = int(data.nb_pme or 0)
    if d.statut == "preparation":
        d.statut = "publie"
    db.commit()
    db.refresh(d)
    return _out(d)


@router.delete("/dce/{dce_id}")
def delete_dce(dce_id: int, a: Acheteur = Depends(get_current_acheteur), db: Session = Depends(get_db)):
    _guard_not_demo(a)
    d = db.query(AcheteurDce).filter(AcheteurDce.id == dce_id,
                                     AcheteurDce.acheteur_id == a.id).first()
    if not d:
        raise HTTPException(404, "DCE introuvable.")
    db.delete(d)
    db.commit()
    return {"ok": True}
