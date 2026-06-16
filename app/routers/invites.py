"""
Adjugo — Partage d'un appel d'offres avec un co-traitant externe (vue bridée).

Le mandataire génère un lien secret limité à UN projet. Le co-traitant l'ouvre
SANS compte et n'accède qu'à une vue restreinte de ce seul projet (résumé + pièces
partagées). Chaque consultation/téléchargement est tracé dans le journal d'accès
(RGPD). La portée est TOUJOURS contrainte côté serveur à `invite.project_id` :
aucune route invité ne lit jamais une autre donnée du tenant.
"""
import io
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AuditLog, Company, Document, Project, ProjectInvite, User, utcnow
from app.services import audit
from app.services.storage import get_storage

router = APIRouter(tags=["Co-traitance"])

# Sous-ensemble SÛR de l'analyse exposé au co-traitant : de quoi comprendre le marché
# et préparer sa part, SANS la stratégie interne du mandataire (score, faiblesses…).
_SAFE_ANALYSIS_KEYS = {
    "objet", "acheteur", "lieu", "duree", "delais", "lots", "allotissement",
    "pieces_requises", "criteres_attribution", "criteres", "montant_estime",
    "type_marche", "procedure", "date_limite",
}


# ── Sérialisation bridée ─────────────────────────────────────────────────────
def _safe_analysis(ai_analysis) -> dict:
    if not isinstance(ai_analysis, dict):
        return {}
    out = {}
    details = ai_analysis.get("details") if isinstance(ai_analysis.get("details"), dict) else ai_analysis
    for k in _SAFE_ANALYSIS_KEYS:
        if isinstance(details, dict) and details.get(k) not in (None, "", [], {}):
            out[k] = details[k]
    return out


def _invite_public(inv: ProjectInvite, project: Project, owner_company: Optional[Company],
                   docs: list) -> dict:
    return {
        "project": {
            "name": project.name,
            "client": project.client,
            # NB : on N'expose PAS `ai_summary` — il est éditorialisé et peut révéler la
            # décision interne du mandataire (Go/No-Go, faiblesses). On ne donne que des
            # FAITS sur le marché (objet, lots, critères, échéance).
            "deadline": project.deadline.isoformat() if project.deadline else None,
            "source_url": project.source_url,
            "analysis": _safe_analysis(project.ai_analysis),
        },
        "mandataire": (owner_company.name if owner_company else "") or "",
        "invited": {"recipient": inv.recipient, "company": inv.company_name},
        "can_view_docs": bool(inv.can_view_docs),
        "documents": docs,
        "shared_at": inv.created_at.isoformat() if inv.created_at else None,
    }


# ── Côté MANDATAIRE (authentifié) ────────────────────────────────────────────
class InviteCreate(BaseModel):
    recipient: str = ""
    company_name: str = ""
    can_view_docs: bool = True
    expires_days: int = 30          # 0 = sans expiration


def _owned_project(pid: int, user: User, db: Session) -> Project:
    p = db.query(Project).filter(
        Project.id == pid, Project.user_id == user.id, Project.deleted_at.is_(None)
    ).first()
    if not p:
        raise HTTPException(404, "Projet introuvable")
    return p


def _serialize_invite(inv: ProjectInvite) -> dict:
    return {
        "id": inv.id, "token": inv.token, "path": f"/invite/{inv.token}",
        "recipient": inv.recipient, "company_name": inv.company_name,
        "can_view_docs": bool(inv.can_view_docs), "revoked": bool(inv.revoked),
        "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
        "view_count": inv.view_count or 0,
        "last_viewed_at": inv.last_viewed_at.isoformat() if inv.last_viewed_at else None,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
    }


@router.post("/api/projects/{project_id}/invites")
def create_invite(project_id: int, body: InviteCreate, request: Request,
                  current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Génère un lien d'invitation co-traitant pour ce projet (mandataire only)."""
    project = _owned_project(project_id, current_user, db)
    inv = ProjectInvite(
        token=secrets.token_urlsafe(32),
        project_id=project.id, owner_id=current_user.id,
        recipient=(body.recipient or "").strip()[:255],
        company_name=(body.company_name or "").strip()[:255],
        can_view_docs=bool(body.can_view_docs),
        expires_at=(utcnow() + timedelta(days=body.expires_days)) if body.expires_days and body.expires_days > 0 else None,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    audit.record(db, action="invite.created", owner_id=current_user.id, project_id=project.id,
                 actor=f"user:{current_user.id}", actor_kind="owner",
                 target_type="invite", target_id=inv.id,
                 detail=(inv.company_name or inv.recipient or "")[:255],
                 ip=audit.client_ip(request))
    out = _serialize_invite(inv)
    out["url"] = str(request.base_url).rstrip("/") + out["path"]
    return out


@router.get("/api/projects/{project_id}/invites")
def list_invites(project_id: int, current_user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    _owned_project(project_id, current_user, db)
    rows = db.query(ProjectInvite).filter(
        ProjectInvite.project_id == project_id, ProjectInvite.owner_id == current_user.id
    ).order_by(ProjectInvite.created_at.desc()).all()
    return [_serialize_invite(r) for r in rows]


@router.delete("/api/projects/{project_id}/invites/{invite_id}")
def revoke_invite(project_id: int, invite_id: int, request: Request,
                  current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Révoque un lien : le co-traitant perd l'accès immédiatement."""
    inv = db.query(ProjectInvite).filter(
        ProjectInvite.id == invite_id, ProjectInvite.project_id == project_id,
        ProjectInvite.owner_id == current_user.id
    ).first()
    if not inv:
        raise HTTPException(404, "Invitation introuvable")
    inv.revoked = True
    db.commit()
    audit.record(db, action="invite.revoked", owner_id=current_user.id, project_id=project_id,
                 actor=f"user:{current_user.id}", actor_kind="owner",
                 target_type="invite", target_id=inv.id,
                 detail=(inv.company_name or inv.recipient or "")[:255],
                 ip=audit.client_ip(request))
    return {"ok": True}


@router.get("/api/projects/{project_id}/audit")
def project_audit(project_id: int, current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db), limit: int = 200):
    """Journal d'accès du projet (RGPD) — qui a consulté/téléchargé quoi, et quand."""
    _owned_project(project_id, current_user, db)
    rows = db.query(AuditLog).filter(
        AuditLog.project_id == project_id, AuditLog.owner_id == current_user.id
    ).order_by(AuditLog.created_at.desc()).limit(min(max(limit, 1), 500)).all()
    return [{
        "id": r.id, "at": r.created_at.isoformat() if r.created_at else None,
        "actor": r.actor, "actor_kind": r.actor_kind, "action": r.action,
        "target_type": r.target_type, "target_id": r.target_id,
        "detail": r.detail, "ip": r.ip,
    } for r in rows]


# ── Côté CO-TRAITANT INVITÉ (NON authentifié — jeton dans l'URL) ─────────────
def _is_expired(dt) -> bool:
    """Comparaison robuste : la base peut renvoyer un datetime naïf (UTC implicite)."""
    if not dt:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt < datetime.now(timezone.utc)


def _valid_invite(token: str, db: Session) -> ProjectInvite:
    inv = db.query(ProjectInvite).filter(ProjectInvite.token == token).first()
    if not inv or inv.revoked:
        raise HTTPException(404, "Lien invalide ou révoqué")
    if _is_expired(inv.expires_at):
        raise HTTPException(410, "Ce lien de partage a expiré")
    return inv


@router.get("/api/invite/{token}")
def guest_view(token: str, request: Request, db: Session = Depends(get_db)):
    """Vue bridée du projet partagé (aucune autre donnée du tenant n'est lisible)."""
    inv = _valid_invite(token, db)
    project = db.query(Project).filter(
        Project.id == inv.project_id, Project.deleted_at.is_(None)
    ).first()
    if not project:
        raise HTTPException(404, "Projet introuvable ou retiré")
    owner_company = db.query(Company).filter(Company.user_id == inv.owner_id).first()

    docs = []
    if inv.can_view_docs:
        rows = db.query(Document).filter(
            Document.project_id == inv.project_id, Document.deleted_at.is_(None)
        ).order_by(Document.created_at.desc()).all()
        docs = [{"id": d.id, "name": d.name,
                 "category": d.category.value if hasattr(d.category, "value") else str(d.category or ""),
                 "folder": d.folder or "", "size": d.file_size or 0} for d in rows]

    # Compteur de vues + trace d'accès
    inv.view_count = (inv.view_count or 0) + 1
    inv.last_viewed_at = utcnow()
    db.commit()
    audit.record(db, action="guest.view_project", owner_id=inv.owner_id, project_id=inv.project_id,
                 actor=(inv.recipient or inv.company_name or "invité")[:160], actor_kind="guest",
                 target_type="project", target_id=inv.project_id,
                 detail=(inv.company_name or "")[:255], ip=audit.client_ip(request))
    return _invite_public(inv, project, owner_company, docs)


@router.get("/api/invite/{token}/doc/{doc_id}")
def guest_download(token: str, doc_id: int, request: Request, db: Session = Depends(get_db)):
    """Télécharge une pièce partagée — STRICTEMENT limitée au projet de l'invitation."""
    inv = _valid_invite(token, db)
    if not inv.can_view_docs:
        raise HTTPException(403, "Le partage des pièces n'est pas autorisé pour ce lien")
    doc = db.query(Document).filter(
        Document.id == doc_id, Document.project_id == inv.project_id,
        Document.deleted_at.is_(None)
    ).first()
    if not doc or not doc.file_key:
        raise HTTPException(404, "Pièce introuvable")
    audit.record(db, action="guest.download_doc", owner_id=inv.owner_id, project_id=inv.project_id,
                 actor=(inv.recipient or inv.company_name or "invité")[:160], actor_kind="guest",
                 target_type="document", target_id=doc.id, detail=(doc.name or "")[:255],
                 ip=audit.client_ip(request))
    storage = get_storage()
    signed = storage.url(doc.file_key)
    if signed:
        return RedirectResponse(signed)
    try:
        content = storage.load(doc.file_key)
    except FileNotFoundError:
        raise HTTPException(410, "Fichier absent du stockage")
    return StreamingResponse(
        io.BytesIO(content),
        media_type=doc.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{doc.name}"'},
    )
