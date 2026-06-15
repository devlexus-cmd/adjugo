"""
Router ESPACE CO-TRAITANCE (Merged Brain).

Deux comptes Adjugo collaborent sur une réponse : le mandataire crée un espace,
invite un partenaire (qui a son propre compte + sa propre base de connaissances).
Une fois le partenaire accepté, l'IA fusionne les deux bases RAG en UN mémoire
technique unifié (références croisées, sources attribuées par entreprise).
"""
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ratelimit import limiter
from app.core.quota import consume_analysis
from app.models import User, Company, CoSpace, CoMember, KnowledgeChunk
from app.services.agents.memoire import generate_merged_memoire

logger = logging.getLogger("adjugo")
router = APIRouter(prefix="/api/cospace", tags=["Espace co-traitance (Merged Brain)"])


def _company_name(db, user_id) -> str:
    c = db.query(Company).filter(Company.user_id == user_id).first()
    return (c.name if c and c.name else "")


def _kb_count(db, user_id) -> int:
    return db.query(KnowledgeChunk).filter(KnowledgeChunk.user_id == user_id).count()


def _member_out(db, m: CoMember) -> dict:
    return {"id": m.id, "user_id": m.user_id, "email": m.email, "role": m.role,
            "status": m.status, "company_name": m.company_name,
            "kb_chunks": (_kb_count(db, m.user_id) if m.user_id else 0)}


def _space_out(db, s: CoSpace, members=None) -> dict:
    members = members if members is not None else db.query(CoMember).filter(CoMember.space_id == s.id).all()
    return {"id": s.id, "name": s.name, "marche": s.marche, "owner_id": s.owner_id,
            "owner_company": _company_name(db, s.owner_id),
            "owner_kb_chunks": _kb_count(db, s.owner_id),
            "members": [_member_out(db, m) for m in members],
            "warroom": s.warroom,
            "created_at": s.created_at.isoformat() if s.created_at else None}


def _accessible(db, space_id, user) -> CoSpace:
    s = db.query(CoSpace).filter(CoSpace.id == space_id).first()
    if not s:
        raise HTTPException(404, "Espace introuvable")
    if s.owner_id == user.id:
        return s
    mem = db.query(CoMember).filter(CoMember.space_id == s.id, CoMember.user_id == user.id,
                                    CoMember.status == "accepted").first()
    if not mem:
        raise HTTPException(403, "Accès refusé à cet espace.")
    return s


class CreateSpace(BaseModel):
    name: str
    marche: str = ""


@router.post("/")
def create_space(req: CreateSpace, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not (req.name or "").strip():
        raise HTTPException(422, "Nom requis.")
    s = CoSpace(owner_id=current_user.id, name=req.name.strip()[:255], marche=(req.marche or "")[:500])
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"space": _space_out(db, s)}


@router.get("/")
def list_spaces(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned = db.query(CoSpace).filter(CoSpace.owner_id == current_user.id).all()
    member_of = (db.query(CoSpace).join(CoMember, CoMember.space_id == CoSpace.id)
                 .filter(CoMember.user_id == current_user.id, CoMember.status == "accepted").all())
    spaces = {s.id: s for s in (owned + member_of)}.values()
    return {"spaces": [_space_out(db, s) for s in spaces]}


@router.get("/{space_id}")
def get_space(space_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _accessible(db, space_id, current_user)
    return {"space": _space_out(db, s)}


class InviteReq(BaseModel):
    email: str
    role: str = "cotraitant"


@router.post("/{space_id}/invite")
def invite(space_id: int, req: InviteReq, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.query(CoSpace).filter(CoSpace.id == space_id, CoSpace.owner_id == current_user.id).first()
    if not s:
        raise HTTPException(404, "Espace introuvable (seul le mandataire invite).")
    email = (req.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(422, "Email invalide.")
    token = secrets.token_urlsafe(24)
    role = req.role if req.role in ("mandataire", "cotraitant") else "cotraitant"
    m = CoMember(space_id=s.id, email=email, role=role, status="invited", token=token)
    db.add(m)
    db.commit()
    db.refresh(m)
    # Email best-effort (no-op si SMTP non configuré). On renvoie le lien dans tous les cas.
    try:
        from app.services.email import send_email
        from app.core.config import get_settings
        base = get_settings().APP_BASE_URL
        send_email(email, f"Invitation à co-traiter sur Adjugo — {s.name}",
                   f"Bonjour,\n\n{current_user.full_name} vous invite à répondre en groupement au marché "
                   f"« {s.marche or s.name} » sur Adjugo.\n\nConnectez-vous à votre compte Adjugo puis "
                   f"rejoignez l'espace avec ce code : {token}\n({base}/app)\n\n— Adjugo")
    except Exception as e:
        logger.warning("Email invitation co-traitance non envoyé : %s", e)
    return {"member": _member_out(db, m), "join_token": token}


class JoinReq(BaseModel):
    token: str


@router.post("/join")
def join(req: JoinReq, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = db.query(CoMember).filter(CoMember.token == (req.token or "").strip()).first()
    if not m:
        raise HTTPException(404, "Invitation introuvable ou expirée.")
    if m.status == "accepted" and m.user_id and m.user_id != current_user.id:
        raise HTTPException(409, "Invitation déjà utilisée.")
    m.user_id = current_user.id
    m.status = "accepted"
    m.company_name = _company_name(db, current_user.id) or (current_user.full_name or "")
    db.commit()
    s = db.query(CoSpace).filter(CoSpace.id == m.space_id).first()
    return {"ok": True, "space": _space_out(db, s)}


@router.delete("/{space_id}")
def delete_space(space_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.query(CoSpace).filter(CoSpace.id == space_id, CoSpace.owner_id == current_user.id).first()
    if not s:
        raise HTTPException(404, "Espace introuvable.")
    db.query(CoMember).filter(CoMember.space_id == s.id).delete()
    db.delete(s)
    db.commit()
    return {"ok": True}


class MergedMemoireReq(BaseModel):
    dce_text: str


@router.post("/{space_id}/memoire")
@limiter.limit("12/hour")
def merged_memoire(space_id: int, req: MergedMemoireReq, request: Request,
                   current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Génère le mémoire UNIFIÉ du groupement à partir des bases de connaissances de
    tous les membres acceptés (mandataire inclus)."""
    s = db.query(CoSpace).filter(CoSpace.id == space_id, CoSpace.owner_id == current_user.id).first()
    if not s:
        raise HTTPException(404, "Espace introuvable (seul le mandataire génère).")
    if len((req.dce_text or "").strip()) < 60:
        raise HTTPException(422, "DCE trop court pour générer un mémoire.")
    members = [{"user_id": s.owner_id, "name": _company_name(db, s.owner_id) or "Mandataire", "role": "mandataire"}]
    for m in db.query(CoMember).filter(CoMember.space_id == s.id, CoMember.status == "accepted").all():
        if m.user_id:
            members.append({"user_id": m.user_id, "name": m.company_name or "Co-traitant", "role": m.role})
    if len(members) < 2:
        raise HTTPException(422, "Invitez et faites accepter au moins un co-traitant avant de fusionner.")
    consume_analysis(current_user, db)
    return generate_merged_memoire(db, members, req.dce_text)


class WarRoomReq(BaseModel):
    dce_text: str


@router.post("/{space_id}/warroom")
@limiter.limit("12/hour")
def warroom(space_id: int, req: WarRoomReq, request: Request,
            current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """War Room : l'IA lit le DCE et pré-répartit les lots entre les membres selon leur
    savoir-faire (pré-projet remis au partenaire). Stocké sur l'espace pour tous les membres."""
    from app.services.agents.warroom import propose_allocation
    s = db.query(CoSpace).filter(CoSpace.id == space_id, CoSpace.owner_id == current_user.id).first()
    if not s:
        raise HTTPException(404, "Espace introuvable (seul le mandataire pré-répartit).")
    if len((req.dce_text or "").strip()) < 60:
        raise HTTPException(422, "DCE trop court.")
    members = [{"user_id": s.owner_id, "name": _company_name(db, s.owner_id) or "Mandataire", "role": "mandataire"}]
    for m in db.query(CoMember).filter(CoMember.space_id == s.id, CoMember.status == "accepted").all():
        if m.user_id:
            members.append({"user_id": m.user_id, "name": m.company_name or "Co-traitant", "role": m.role})
    # Aussi les invités non encore acceptés (pour pré-remplir leur dossier d'accueil)
    for m in db.query(CoMember).filter(CoMember.space_id == s.id, CoMember.status == "invited").all():
        members.append({"user_id": None, "name": m.email, "role": m.role})
    consume_analysis(current_user, db)
    result = propose_allocation(db, req.dce_text, [m for m in members if m.get("user_id")])
    s.warroom = result
    db.commit()
    return result
