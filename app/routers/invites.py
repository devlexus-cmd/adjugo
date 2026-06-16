"""
Adjugo — Partage d'un appel d'offres avec un co-traitant externe (vue bridée).

Le mandataire génère un lien secret limité à UN projet. Le co-traitant l'ouvre
SANS compte et n'accède qu'à une vue restreinte de ce seul projet (résumé + pièces
partagées). Chaque consultation/téléchargement est tracé dans le journal d'accès
(RGPD). La portée est TOUJOURS contrainte côté serveur à `invite.project_id` :
aucune route invité ne lit jamais une autre donnée du tenant.
"""
import io
import mimetypes
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.ratelimit import limiter
from app.core.security import get_current_user
from app.models import (AuditLog, Company, ContributionPiece, Document, Project,
                        ProjectContribution, ProjectInvite, User, utcnow)
from app.services import audit
from app.services.storage import get_storage

router = APIRouter(tags=["Co-traitance"])
_settings = get_settings()
_ALLOWED_EXT = {e.strip().lower() for e in _settings.ALLOWED_UPLOAD_EXT.split(",") if e.strip()}
_MAX_BYTES = _settings.MAX_UPLOAD_MB * 1024 * 1024


def _read_upload(file: UploadFile) -> tuple:
    """Valide extension + taille d'un fichier téléversé par un invité ; (contenu, ext)."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if _ALLOWED_EXT and ext not in _ALLOWED_EXT:
        raise HTTPException(400, f"Type de fichier non autorisé ({ext or 'inconnu'}).")
    content = file.file.read()
    if not content:
        raise HTTPException(400, "Fichier vide")
    if len(content) > _MAX_BYTES:
        raise HTTPException(413, f"Fichier trop volumineux (max {_settings.MAX_UPLOAD_MB} Mo)")
    return content, ext


def _safe_mime(filename: str) -> str:
    """Type MIME DÉRIVÉ de l'extension (jamais le Content-Type fourni par le client) :
    l'extension étant en liste blanche (pdf/png/doc…), on ne peut jamais servir du
    text/html → pas de XSS au téléchargement. Repli neutre forçant le download."""
    return mimetypes.guess_type(filename or "")[0] or "application/octet-stream"


def _attachment_headers(name: str) -> dict:
    """Content-Disposition robuste : pas d'injection d'en-tête possible via le nom de
    fichier (guillemets/CRLF). Repli ASCII + variante RFC 5987 (filename*)."""
    base = os.path.basename(name or "fichier")
    ascii_name = re.sub(r'[^A-Za-z0-9._ -]', "_", base) or "fichier"
    return {"Content-Disposition":
            f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(base, safe='')}"}

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
        "invited": {"recipient": inv.recipient, "company": inv.company_name,
                    "role": inv.role or "cotraitant"},
        "can_view_docs": bool(inv.can_view_docs),
        "can_contribute": bool(getattr(inv, "can_contribute", True)),
        "documents": docs,
        "shared_at": inv.created_at.isoformat() if inv.created_at else None,
    }


# ── Côté MANDATAIRE (authentifié) ────────────────────────────────────────────
class InviteCreate(BaseModel):
    recipient: str = ""
    company_name: str = ""
    role: str = "cotraitant"        # cotraitant | sous_traitant
    can_view_docs: bool = True
    can_contribute: bool = True     # autorise la co-construction (apport de sa part)
    expires_days: int = 30          # 0 = sans expiration


def _owned_project(pid: int, user: User, db: Session) -> Project:
    p = db.query(Project).filter(
        Project.id == pid, Project.user_id == user.id, Project.deleted_at.is_(None)
    ).first()
    if not p:
        raise HTTPException(404, "Projet introuvable")
    return p


def _serialize_invite(inv: ProjectInvite, contribution: "ProjectContribution" = None) -> dict:
    return {
        "id": inv.id, "token": inv.token, "path": f"/invite/{inv.token}",
        "recipient": inv.recipient, "company_name": inv.company_name,
        "role": inv.role or "cotraitant",
        "can_view_docs": bool(inv.can_view_docs),
        "can_contribute": bool(getattr(inv, "can_contribute", True)),
        "revoked": bool(inv.revoked),
        "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
        "view_count": inv.view_count or 0,
        "last_viewed_at": inv.last_viewed_at.isoformat() if inv.last_viewed_at else None,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "contribution_status": (contribution.status if contribution else None),
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
        role=(body.role if body.role in ("cotraitant", "sous_traitant") else "cotraitant"),
        can_view_docs=bool(body.can_view_docs),
        can_contribute=bool(body.can_contribute),
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
    contribs = {c.invite_id: c for c in db.query(ProjectContribution).filter(
        ProjectContribution.project_id == project_id, ProjectContribution.owner_id == current_user.id).all()}
    return [_serialize_invite(r, contribs.get(r.id)) for r in rows]


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
    return dt <= datetime.now(timezone.utc)


def _valid_invite(token: str, db: Session) -> ProjectInvite:
    inv = db.query(ProjectInvite).filter(ProjectInvite.token == token).first()
    if not inv or inv.revoked:
        raise HTTPException(404, "Lien invalide ou révoqué")
    if _is_expired(inv.expires_at):
        raise HTTPException(410, "Ce lien de partage a expiré")
    return inv


@router.get("/api/invite/{token}")
@limiter.limit("120/minute")
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
@limiter.limit("60/minute")
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
        headers=_attachment_headers(doc.name),
    )


# ── CO-CONSTRUCTION : l'invité apporte SA part (cloisonnée) ──────────────────
# Cœur du réseau Adjugo : chaque PME contribue à un dossier commun sans jamais
# voir les données des autres. La contribution est liée à l'invitation (1-1) ;
# l'invité ne lit/écrit JAMAIS que la sienne.
def _piece_dict(pc: ContributionPiece) -> dict:
    return {"id": pc.id, "name": pc.name, "size": pc.file_size or 0,
            "created_at": pc.created_at.isoformat() if pc.created_at else None}


def _serialize_contribution(c: ProjectContribution, db: Session = None) -> dict:
    pieces = []
    if db is not None:
        pieces = [_piece_dict(p) for p in db.query(ContributionPiece).filter(
            ContributionPiece.contribution_id == c.id).order_by(ContributionPiece.created_at.asc()).all()]
    return {
        "id": c.id, "company_name": c.company_name, "role": c.role, "lot": c.lot,
        "references": c.references or [], "qualifications": c.qualifications or [],
        "chiffrage_note": c.chiffrage_note or "", "memoire_paragraph": c.memoire_paragraph or "",
        "contact": c.contact or {}, "status": c.status,
        "submitted_at": c.submitted_at.isoformat() if c.submitted_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        "pieces": pieces,
    }


def _get_or_create_contribution(inv: ProjectInvite, db: Session) -> ProjectContribution:
    c = db.query(ProjectContribution).filter(ProjectContribution.invite_id == inv.id).first()
    if c is None:
        c = ProjectContribution(
            invite_id=inv.id, project_id=inv.project_id, owner_id=inv.owner_id,
            company_name=inv.company_name or "", role=inv.role or "cotraitant",
        )
        db.add(c)
        db.commit()
        db.refresh(c)
    return c


class ContributionSave(BaseModel):
    company_name: Optional[str] = None
    lot: Optional[str] = None
    references: Optional[list] = None
    qualifications: Optional[list] = None
    chiffrage_note: Optional[str] = None
    memoire_paragraph: Optional[str] = None
    contact: Optional[dict] = None


@router.get("/api/invite/{token}/contribution")
@limiter.limit("120/minute")
def guest_get_contribution(token: str, request: Request, db: Session = Depends(get_db)):
    """Récupère (ou initialise) la contribution de CET invité — la sienne uniquement."""
    inv = _valid_invite(token, db)
    if not getattr(inv, "can_contribute", True):
        raise HTTPException(403, "La co-construction n'est pas activée pour ce lien")
    return _serialize_contribution(_get_or_create_contribution(inv, db), db)


@router.put("/api/invite/{token}/contribution")
@limiter.limit("90/minute")
def guest_save_contribution(token: str, body: ContributionSave, request: Request, db: Session = Depends(get_db)):
    """Enregistre le brouillon de la contribution de cet invité (ses champs uniquement)."""
    inv = _valid_invite(token, db)
    if not getattr(inv, "can_contribute", True):
        raise HTTPException(403, "La co-construction n'est pas activée pour ce lien")
    c = _get_or_create_contribution(inv, db)
    if body.company_name is not None:
        c.company_name = body.company_name.strip()[:255]
    if body.lot is not None:
        c.lot = body.lot.strip()[:255]
    if body.references is not None:
        c.references = body.references[:50]
    if body.qualifications is not None:
        c.qualifications = body.qualifications[:50]
    if body.chiffrage_note is not None:
        c.chiffrage_note = body.chiffrage_note[:8000]
    if body.memoire_paragraph is not None:
        c.memoire_paragraph = body.memoire_paragraph[:12000]
    if body.contact is not None:
        c.contact = {k: str(v)[:255] for k, v in (body.contact or {}).items()
                     if k in ("nom", "email", "telephone")}
    if c.status == "submitted":            # toute modif après soumission repasse en brouillon
        c.status = "draft"
        c.submitted_at = None
    db.commit()
    return _serialize_contribution(c, db)


@router.post("/api/invite/{token}/contribution/submit")
@limiter.limit("30/minute")
def guest_submit_contribution(token: str, request: Request, db: Session = Depends(get_db)):
    """Soumet la contribution au mandataire (et la rend disponible pour la fusion IA)."""
    inv = _valid_invite(token, db)
    if not getattr(inv, "can_contribute", True):
        raise HTTPException(403, "La co-construction n'est pas activée pour ce lien")
    c = _get_or_create_contribution(inv, db)
    c.status = "submitted"
    c.submitted_at = utcnow()
    db.commit()
    audit.record(db, action="guest.submit_contribution", owner_id=inv.owner_id, project_id=inv.project_id,
                 actor=(inv.recipient or inv.company_name or "invité")[:160], actor_kind="guest",
                 target_type="contribution", target_id=c.id,
                 detail=(c.company_name or inv.company_name or "")[:255], ip=audit.client_ip(request))
    return _serialize_contribution(c, db)


# ── Pièces administratives du co-traitant (DC2, attestations…) ───────────────
_MAX_PIECES_PER_CONTRIB = 20


def _guest_piece(token: str, piece_id: int, db: Session):
    """Résout (invite, contribution, piece) en garantissant que la pièce appartient
    bien à la contribution de CE jeton — jamais celle d'un autre co-traitant."""
    inv = _valid_invite(token, db)
    c = db.query(ProjectContribution).filter(ProjectContribution.invite_id == inv.id).first()
    if not c:
        raise HTTPException(404, "Aucune contribution")
    pc = db.query(ContributionPiece).filter(
        ContributionPiece.id == piece_id, ContributionPiece.contribution_id == c.id).first()
    if not pc:
        raise HTTPException(404, "Pièce introuvable")
    return inv, c, pc


@router.post("/api/invite/{token}/contribution/piece")
@limiter.limit("30/minute")
def guest_upload_piece(token: str, request: Request, file: UploadFile = File(...),
                       db: Session = Depends(get_db)):
    """Le co-traitant téléverse UNE de ses pièces administratives (scopée à sa part)."""
    inv = _valid_invite(token, db)
    if not getattr(inv, "can_contribute", True):
        raise HTTPException(403, "La co-construction n'est pas activée pour ce lien")
    c = _get_or_create_contribution(inv, db)
    if db.query(ContributionPiece).filter(ContributionPiece.contribution_id == c.id).count() >= _MAX_PIECES_PER_CONTRIB:
        raise HTTPException(400, f"Maximum {_MAX_PIECES_PER_CONTRIB} pièces par partenaire.")
    content, ext = _read_upload(file)
    safe_mime = _safe_mime(file.filename)        # type dérivé de l'extension, pas du client
    file_key = f"{inv.owner_id}/cotraitant/{uuid.uuid4().hex}{ext}"
    get_storage().save(file_key, content, safe_mime)
    pc = ContributionPiece(
        contribution_id=c.id, project_id=inv.project_id, owner_id=inv.owner_id,
        name=os.path.basename(file.filename or "piece")[:500], file_key=file_key,
        file_size=len(content), mime_type=safe_mime[:100])
    db.add(pc)
    db.commit()
    db.refresh(pc)
    audit.record(db, action="guest.upload_piece", owner_id=inv.owner_id, project_id=inv.project_id,
                 actor=(inv.recipient or inv.company_name or "invité")[:160], actor_kind="guest",
                 target_type="piece", target_id=pc.id, detail=(pc.name or "")[:255],
                 ip=audit.client_ip(request))
    return _piece_dict(pc)


@router.get("/api/invite/{token}/contribution/piece/{piece_id}")
@limiter.limit("60/minute")
def guest_download_piece(token: str, piece_id: int, request: Request, db: Session = Depends(get_db)):
    """Le co-traitant re-télécharge SA pièce."""
    inv, c, pc = _guest_piece(token, piece_id, db)
    return _stream_piece(pc)


@router.delete("/api/invite/{token}/contribution/piece/{piece_id}")
@limiter.limit("30/minute")
def guest_delete_piece(token: str, piece_id: int, request: Request, db: Session = Depends(get_db)):
    """Le co-traitant retire SA pièce."""
    inv, c, pc = _guest_piece(token, piece_id, db)
    try:
        get_storage().delete(pc.file_key)
    except Exception:
        pass
    db.delete(pc)
    db.commit()
    return {"ok": True}


def _stream_piece(pc: ContributionPiece):
    storage = get_storage()
    signed = storage.url(pc.file_key)
    if signed:
        return RedirectResponse(signed)
    try:
        content = storage.load(pc.file_key)
    except FileNotFoundError:
        raise HTTPException(410, "Fichier absent du stockage")
    return StreamingResponse(io.BytesIO(content),
                             media_type=pc.mime_type or "application/octet-stream",
                             headers=_attachment_headers(pc.name))


@router.get("/api/projects/{project_id}/contribution-pieces/{piece_id}")
def owner_download_piece(project_id: int, piece_id: int, request: Request,
                         current_user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """Le mandataire télécharge une pièce d'un co-traitant (scopée à SON projet)."""
    _owned_project(project_id, current_user, db)
    pc = db.query(ContributionPiece).filter(
        ContributionPiece.id == piece_id, ContributionPiece.project_id == project_id,
        ContributionPiece.owner_id == current_user.id).first()
    if not pc:
        raise HTTPException(404, "Pièce introuvable")
    audit.record(db, action="owner.download_piece", owner_id=current_user.id, project_id=project_id,
                 actor=f"user:{current_user.id}", actor_kind="owner",
                 target_type="piece", target_id=pc.id, detail=(pc.name or "")[:255],
                 ip=audit.client_ip(request))
    return _stream_piece(pc)


@router.get("/api/projects/{project_id}/contributions")
def list_contributions(project_id: int, current_user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """Toutes les contributions des co-traitants de CE projet (mandataire only)."""
    _owned_project(project_id, current_user, db)
    rows = db.query(ProjectContribution).filter(
        ProjectContribution.project_id == project_id,
        ProjectContribution.owner_id == current_user.id
    ).order_by(ProjectContribution.updated_at.desc()).all()
    return [_serialize_contribution(c, db) for c in rows]


# Pondération de complétude d'UNE part de partenaire (somme = 1.0). Déterministe et
# explicable : le % de préparation n'est jamais "deviné" par l'IA, c'est un calcul.
_READINESS_WEIGHTS = {"submitted": 0.40, "lot": 0.15, "references": 0.15,
                      "memoire": 0.20, "qualifications": 0.10}


@router.get("/api/projects/{project_id}/consortium")
def consortium_cockpit(project_id: int, current_user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """Cockpit du consortium (mandataire) : partenaires × lots, complétude de chaque part,
    et % de réponse commune PRÊTE — calcul DÉTERMINISTE (jamais inventé)."""
    _owned_project(project_id, current_user, db)
    invites = db.query(ProjectInvite).filter(
        ProjectInvite.project_id == project_id, ProjectInvite.owner_id == current_user.id,
        ProjectInvite.revoked.is_(False)).order_by(ProjectInvite.created_at.asc()).all()
    contribs = {c.invite_id: c for c in db.query(ProjectContribution).filter(
        ProjectContribution.project_id == project_id,
        ProjectContribution.owner_id == current_user.id).all()}
    piece_counts = {}
    for pc in db.query(ContributionPiece).filter(
            ContributionPiece.project_id == project_id,
            ContributionPiece.owner_id == current_user.id).all():
        piece_counts[pc.contribution_id] = piece_counts.get(pc.contribution_id, 0) + 1
    company = db.query(Company).filter(Company.user_id == current_user.id).first()

    partners, lots, missing, total_score = [], {}, [], 0.0
    for inv in invites:
        c = contribs.get(inv.id)
        lot_clean = (c.lot.strip() if c and c.lot else "")   # évite une clé de lot vide/espaces
        flags = {
            "submitted": bool(c and c.status == "submitted"),
            "lot": bool(lot_clean),
            "references": bool(c and c.references),
            "memoire": bool(c and c.memoire_paragraph),
            "qualifications": bool(c and c.qualifications),
        }
        score = min(1.0, sum(_READINESS_WEIGHTS[k] for k, v in flags.items() if v))   # borne [0,1]
        total_score += score
        name = (c.company_name if c and c.company_name else inv.company_name) or inv.recipient or "Partenaire"
        partners.append({
            "company": name, "role": inv.role or "cotraitant",
            "lot": lot_clean, "status": (c.status if c else "invited"),
            "has_references": flags["references"], "has_memoire": flags["memoire"],
            "has_chiffrage": bool(c and c.chiffrage_note),
            "qualifications_count": len(c.qualifications or []) if c else 0,
            "pieces_count": (piece_counts.get(c.id, 0) if c else 0),
            "completeness": round(score * 100),
        })
        if lot_clean:
            lots.setdefault(lot_clean, []).append(name)
        # File des manques (concrets, actionnables) — le plus bloquant d'abord.
        if not flags["submitted"]:
            missing.append(f"{name} n'a pas encore soumis sa part")
        elif not flags["memoire"]:
            missing.append(f"{name} : paragraphe de mémoire manquant")
        elif not flags["lot"]:
            missing.append(f"{name} : lot/périmètre non précisé")
        elif not flags["references"]:
            missing.append(f"{name} : aucune référence renseignée")

    n = len(invites)
    pct = round(100 * total_score / n) if n else 0
    return {
        "partners": partners,
        "lots": [{"lot": k, "partners": v} for k, v in lots.items()],
        "readiness": {
            "invited": n,
            "submitted": sum(1 for p in partners if p["status"] == "submitted"),
            "lots": len(lots),
            "pct": pct,
            "missing": missing[:12],
        },
        "mandataire": {
            "company": (company.name if company else "") or "",
            "qualifications": len(company.qualifications or []) if company else 0,
        },
    }
