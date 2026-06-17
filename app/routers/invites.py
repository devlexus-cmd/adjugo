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
from fastapi.responses import RedirectResponse, Response, StreamingResponse
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

import hashlib

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_OTP_TTL_MIN = 15
_OTP_MAX_ATTEMPTS = 5


def _is_email(s) -> bool:
    return bool(_EMAIL_RE.match((s or "").strip()))


def _binding_required(inv) -> bool:
    """Le binding d'identité OTP s'applique UNIQUEMENT si l'email est configuré ET le
    destinataire est une adresse. Sinon : flux inchangé, zéro friction (l'ADN CaaS)."""
    try:
        from app.services import email as _email
        return _email.is_enabled() and _is_email(getattr(inv, "recipient", ""))
    except Exception:
        return False


def _mask_email(e: str) -> str:
    e = (e or "").strip()
    if "@" not in e:
        return e
    user, _, dom = e.partition("@")
    return ((user[0] + "***") if user else "***") + "@" + dom


def _hash_otp(code: str) -> str:
    return hashlib.sha256(("adjugo-otp:" + (code or "")).encode("utf-8")).hexdigest()


def _send_invite_email(inv, project, base_url: str) -> bool:
    """Envoie le lien d'invitation au co-traitant. No-op gracieux si email désactivé."""
    if not _is_email(inv.recipient):
        return False
    try:
        from app.services import email as _email
        url = base_url.rstrip("/") + f"/invite/{inv.token}"
        who = inv.company_name or "votre entreprise"
        subj = f"Invitation à co-traiter sur un marché — {project.name[:60]}"
        text = (f"Bonjour,\n\nVous êtes invité(e) à rejoindre le groupement pour répondre au "
                f"marché « {project.name} » sur Adjugo, en tant que {who}.\n\n"
                f"Accédez à votre espace dédié (cloisonné à ce seul dossier) :\n{url}\n\n"
                f"Vous n'y voyez que ce dossier et votre propre contribution — jamais les "
                f"données des autres partenaires.\n\n— Adjugo, le réseau des PME")
        return _email.send_email(inv.recipient, subj, text)
    except Exception:
        return False
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

# Sous-ensemble SÛR de l'analyse exposé au co-traitant : FAITS PUBLICS du marché (déjà
# dans l'avis publié), de quoi comprendre et préparer sa part — SANS la stratégie interne
# du mandataire (score, faiblesses) NI le montant estimé (= cible de prix : un co-traitant
# pourrait s'en servir pour caler son lot ; il chiffre sa part sur sa propre base).
_SAFE_ANALYSIS_KEYS = {
    "objet", "acheteur", "lieu", "duree", "delais", "lots", "allotissement",
    "pieces_requises", "criteres_attribution", "criteres",
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
    # Envoi du lien par email au destinataire (si adresse + SMTP configuré).
    out["emailed"] = _send_invite_email(inv, project, _settings.APP_BASE_URL or str(request.base_url))
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
    # Notifie le partenaire que son accès est coupé (s'il a une adresse + SMTP configuré).
    emailed = False
    if _is_email(inv.recipient):
        try:
            from app.services import email as _email
            proj = db.query(Project).filter(Project.id == project_id).first()
            emailed = _email.send_email(
                inv.recipient, "Accès à un dossier Adjugo retiré",
                f"Bonjour,\n\nVotre accès au dossier « {proj.name if proj else 'partagé'} » sur "
                f"Adjugo a été retiré par le mandataire. Vous n'y avez plus accès.\n\n— Adjugo")
        except Exception:
            emailed = False
    return {"ok": True, "notified": emailed}


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


@router.get("/api/audit/integrity")
def audit_integrity(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Vérifie l'intégrité du journal d'audit du tenant (chaîne de hash). Preuve RGPD
    que la traçabilité n'a pas été altérée."""
    return audit.verify_chain(db, current_user.id)


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
        "version": c.version or 0,
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
    version: Optional[int] = None     # verrou optimiste : la version chargée par le client


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
    # Verrou optimiste OBLIGATOIRE et ATOMIQUE. La version est exigée (un client qui
    # l'omettait écrasait silencieusement la saisie d'un autre). On « réserve » la
    # transition de version par un UPDATE ... WHERE version = attendue, exécuté en une
    # seule instruction SQL : deux PUT concurrents lisant la même version ne peuvent pas
    # passer tous les deux (le 2ᵉ matche 0 ligne → 409). Cela ferme la fenêtre TOCTOU
    # du simple read-then-write.
    if body.version is None:
        raise HTTPException(428, "Version requise (verrou optimiste). Rechargez la contribution.")
    expected = int(body.version)
    claimed = db.query(ProjectContribution).filter(
        ProjectContribution.id == c.id,
        ProjectContribution.version == expected,
    ).update({ProjectContribution.version: expected + 1}, synchronize_session="fetch")
    if not claimed:
        db.rollback()
        raise HTTPException(409, "Cette contribution a été modifiée ailleurs entre-temps. "
                                 "Rechargez pour récupérer la dernière version avant de réenregistrer.")
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
    # La version a déjà été incrémentée atomiquement par le claim ci-dessus (→ expected+1).
    db.commit()
    return _serialize_contribution(c, db)


# ── Binding d'identité par OTP email (sécurité « industrielle ») ─────────────
class OtpVerify(BaseModel):
    code: str = ""


@router.get("/api/invite/{token}/otp/status")
@limiter.limit("120/minute")
def guest_otp_status(token: str, request: Request, db: Session = Depends(get_db)):
    """Indique au front si une vérification d'identité est requise pour soumettre, et si
    elle est déjà faite. Si l'email n'est pas configuré, aucune vérification (flux libre)."""
    inv = _valid_invite(token, db)
    return {"required": _binding_required(inv),
            "verified": bool(inv.verified_at),
            "email_masked": _mask_email(inv.recipient) if _is_email(inv.recipient) else ""}


@router.post("/api/invite/{token}/otp/request")
@limiter.limit("6/hour")
def guest_otp_request(token: str, request: Request, db: Session = Depends(get_db)):
    """Envoie un code à 6 chiffres à l'adresse destinataire de l'invitation, pour prouver
    que l'invité la contrôle avant de soumettre sa part."""
    inv = _valid_invite(token, db)
    if not _binding_required(inv):
        return {"sent": False, "reason": "Vérification non requise pour ce lien."}
    code = f"{secrets.randbelow(1_000_000):06d}"
    inv.otp_hash = _hash_otp(code)
    inv.otp_expires_at = utcnow() + timedelta(minutes=_OTP_TTL_MIN)
    inv.otp_attempts = 0
    db.commit()
    from app.services import email as _email
    _email.send_email(
        inv.recipient,
        "Votre code de vérification Adjugo",
        f"Votre code pour valider votre contribution au groupement : {code}\n\n"
        f"Il expire dans {_OTP_TTL_MIN} minutes. Si vous n'êtes pas à l'origine de cette "
        f"demande, ignorez ce message.")
    audit.record(db, action="guest.otp_request", owner_id=inv.owner_id, project_id=inv.project_id,
                 actor=(inv.recipient or "")[:160], actor_kind="guest", target_type="invite",
                 target_id=inv.id, ip=audit.client_ip(request))
    return {"sent": True, "email_masked": _mask_email(inv.recipient), "ttl_min": _OTP_TTL_MIN}


@router.post("/api/invite/{token}/otp/verify")
@limiter.limit("20/hour")
def guest_otp_verify(token: str, body: OtpVerify, request: Request, db: Session = Depends(get_db)):
    """Vérifie le code reçu par email → marque l'identité de l'invité comme prouvée."""
    inv = _valid_invite(token, db)
    if not _binding_required(inv):
        return {"verified": True}
    if not inv.otp_hash or not inv.otp_expires_at:
        raise HTTPException(400, "Aucun code en attente. Demandez d'abord un code.")
    if _is_expired(inv.otp_expires_at):
        raise HTTPException(410, "Code expiré. Demandez-en un nouveau.")
    if (inv.otp_attempts or 0) >= _OTP_MAX_ATTEMPTS:
        raise HTTPException(429, "Trop de tentatives. Demandez un nouveau code.")
    if _hash_otp((body.code or "").strip()) != inv.otp_hash:
        inv.otp_attempts = (inv.otp_attempts or 0) + 1
        db.commit()
        raise HTTPException(400, "Code incorrect.")
    inv.verified_at = utcnow()
    inv.verified_email = inv.recipient
    inv.otp_hash = ""
    inv.otp_expires_at = None
    db.commit()
    audit.record(db, action="guest.otp_verified", owner_id=inv.owner_id, project_id=inv.project_id,
                 actor=(inv.recipient or "")[:160], actor_kind="guest", target_type="invite",
                 target_id=inv.id, detail=_mask_email(inv.recipient), ip=audit.client_ip(request))
    return {"verified": True}


@router.post("/api/invite/{token}/contribution/submit")
@limiter.limit("30/minute")
def guest_submit_contribution(token: str, request: Request, db: Session = Depends(get_db)):
    """Soumet la contribution au mandataire (et la rend disponible pour la fusion IA)."""
    inv = _valid_invite(token, db)
    if not getattr(inv, "can_contribute", True):
        raise HTTPException(403, "La co-construction n'est pas activée pour ce lien")
    # Binding d'identité : si requis (email configuré + destinataire = adresse), l'invité
    # doit avoir prouvé son adresse avant de soumettre. La saisie/brouillon reste libre.
    if _binding_required(inv) and not inv.verified_at:
        raise HTTPException(status_code=403,
                            detail={"code": "identity_unverified",
                                    "message": "Vérifiez votre adresse email avant de soumettre votre part."})
    c = _get_or_create_contribution(inv, db)
    c.status = "submitted"
    c.submitted_at = utcnow()
    db.commit()
    audit.record(db, action="guest.submit_contribution", owner_id=inv.owner_id, project_id=inv.project_id,
                 actor=(inv.recipient or inv.company_name or "invité")[:160], actor_kind="guest",
                 target_type="contribution", target_id=c.id,
                 detail=(c.company_name or inv.company_name or "")[:255], ip=audit.client_ip(request))
    return _serialize_contribution(c, db)


# ── Découverte d'appels d'offres pour l'invité (NON facturée, lecture seule) ──
# L'invité goûte au sourcing : il cherche des AO publics, mais « analyser / ajouter »
# l'invitera à créer son compte (conversion). Aucune dépense, aucune donnée du tenant.
class GuestSearch(BaseModel):
    query: str = ""
    departements: list = []
    countries: list = []
    montant_min: float = 0
    montant_max: float = 0
    limit: int = 20


@router.post("/api/invite/{token}/search")
@limiter.limit("30/hour")
def guest_search(token: str, body: GuestSearch, request: Request, db: Session = Depends(get_db)):
    """Recherche d'AO publics pour l'invité (découverte). Pas de LLM, pas de quota."""
    _valid_invite(token, db)
    from app.routers.sourcing import _tender_sources
    from app.sourcing.base import TenderCriteria
    from app.sourcing.search import TenderSearchService
    countries = [c for c in (body.countries or ["FR"]) if c] or ["FR"]
    crit = TenderCriteria(query=(body.query or "").strip()[:200], departements=body.departements or [],
                          montant_min=body.montant_min or None, montant_max=body.montant_max or None,
                          limit=min(max(int(body.limit or 20), 1), 30), countries=countries)
    try:
        result = TenderSearchService(_tender_sources(countries)).search(crit, {}, {})
    except Exception:
        raise HTTPException(503, "La recherche est momentanément indisponible. Réessayez.")
    return {"count": result.get("count", 0),
            "tenders": [t.model_dump(exclude={"raw"}) for t in result.get("tenders", [])]}


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


def _partner_flags(c) -> dict:
    return {
        "submitted": bool(c and c.status == "submitted"),
        "lot": bool(c and c.lot and c.lot.strip()),
        "references": bool(c and c.references),
        "memoire": bool(c and c.memoire_paragraph),
        "qualifications": bool(c and c.qualifications),
    }


def _partner_score(flags: dict) -> float:
    return min(1.0, sum(_READINESS_WEIGHTS[k] for k, v in flags.items() if v))


# Pièces administratives attendues de CHAQUE membre d'un groupement (au-delà des
# CERFA mutualisés). Permet au mandataire de voir, par partenaire, ce qui manque.
_PARTNER_PIECE_TYPES = [
    ("kbis", "Kbis", ("kbis", "extrait k", "registre")),
    ("fiscale", "Attest. fiscale", ("fiscal", "impot", "dgfip")),
    ("sociale", "Attest. sociale (URSSAF)", ("urssaf", "social", "vigilance", "cotisation")),
    ("assurance", "Assurance (RC/décennale)", ("assurance", "rc pro", "responsabilite", "decennale", "decenale")),
    ("rib", "RIB", ("rib", "bancaire", "iban")),
]


def _classify_partner_pieces(names: list) -> dict:
    """À partir des noms de pièces déposées par un partenaire, déduit quels types
    administratifs attendus sont présents/absents (rapprochement par mots-clés)."""
    low = [(n or "").lower() for n in names]
    have, missing = [], []
    for key, label, kw in _PARTNER_PIECE_TYPES:
        present = any(any(k in n for k in kw) for n in low)
        (have if present else missing).append(label)
    return {"have": have, "missing": missing}


@router.get("/api/consortiums")
def my_consortiums(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Tous les consortiums du mandataire (AO avec ≥1 partenaire) — pour l'accueil.
    Agrège partenaires, parts soumises, pièces et % de réponse prête par AO."""
    invites = db.query(ProjectInvite).filter(
        ProjectInvite.owner_id == current_user.id, ProjectInvite.revoked.is_(False)).all()
    if not invites:
        return {"consortiums": [], "active": 0, "partners_total": 0, "submitted_total": 0}
    pids = {i.project_id for i in invites}
    contribs = {c.invite_id: c for c in db.query(ProjectContribution).filter(
        ProjectContribution.owner_id == current_user.id,
        ProjectContribution.project_id.in_(pids)).all()}
    piece_counts = {}
    for pc in db.query(ContributionPiece).filter(
            ContributionPiece.owner_id == current_user.id,
            ContributionPiece.project_id.in_(pids)).all():
        piece_counts[pc.contribution_id] = piece_counts.get(pc.contribution_id, 0) + 1
    projects = {p.id: p for p in db.query(Project).filter(
        Project.id.in_(pids), Project.user_id == current_user.id, Project.deleted_at.is_(None)).all()}

    by_project = {}
    for inv in invites:
        by_project.setdefault(inv.project_id, []).append(inv)

    out, partners_total, submitted_total = [], 0, 0
    for pid, invs in by_project.items():
        proj = projects.get(pid)
        if not proj:
            continue
        total_score = submitted = pieces = 0
        for inv in invs:
            c = contribs.get(inv.id)
            flags = _partner_flags(c)
            total_score += _partner_score(flags)
            if flags["submitted"]:
                submitted += 1
            if c:
                pieces += piece_counts.get(c.id, 0)
        n = len(invs)
        partners_total += n
        submitted_total += submitted
        out.append({
            "project_id": pid, "project": proj.name,
            "status": proj.status.value if hasattr(proj.status, "value") else str(proj.status or ""),
            "deadline": proj.deadline.isoformat() if proj.deadline else None,
            "partners": n, "submitted": submitted, "pieces": pieces,
            "readiness_pct": round(100 * total_score / n) if n else 0,
        })
    out.sort(key=lambda x: (-x["submitted"], -x["readiness_pct"]))
    return {"consortiums": out, "active": len(out),
            "partners_total": partners_total, "submitted_total": submitted_total}


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
    piece_counts, piece_names = {}, {}
    for pc in db.query(ContributionPiece).filter(
            ContributionPiece.project_id == project_id,
            ContributionPiece.owner_id == current_user.id).all():
        piece_counts[pc.contribution_id] = piece_counts.get(pc.contribution_id, 0) + 1
        piece_names.setdefault(pc.contribution_id, []).append(pc.name or "")
    company = db.query(Company).filter(Company.user_id == current_user.id).first()

    partners, lots, missing, total_score = [], {}, [], 0.0
    for inv in invites:
        c = contribs.get(inv.id)
        lot_clean = (c.lot.strip() if c and c.lot else "")   # évite une clé de lot vide/espaces
        flags = _partner_flags(c)
        score = _partner_score(flags)                          # borné [0,1]
        total_score += score
        name = (c.company_name if c and c.company_name else inv.company_name) or inv.recipient or "Partenaire"
        pclass = _classify_partner_pieces(piece_names.get(c.id, []) if c else [])
        partners.append({
            "company": name, "role": inv.role or "cotraitant",
            "lot": lot_clean, "status": (c.status if c else "invited"),
            "has_references": flags["references"], "has_memoire": flags["memoire"],
            "has_chiffrage": bool(c and c.chiffrage_note),
            "qualifications_count": len(c.qualifications or []) if c else 0,
            "pieces_count": (piece_counts.get(c.id, 0) if c else 0),
            "pieces_have": pclass["have"], "pieces_missing": pclass["missing"],
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
        elif pclass["missing"]:
            # Part soumise mais pièces administratives obligatoires absentes du membre.
            missing.append(f"{name} : pièce(s) à fournir — {', '.join(pclass['missing'][:3])}")

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


# ── Notifications (activité des partenaires, in-app) ─────────────────────────
# Pas de modèle dédié : on s'appuie sur audit_logs (déjà rempli). Le mandataire voit
# l'activité de ses co-traitants sur TOUS ses AO d'un coup d'œil.
_NOTIF_LABELS = {
    "guest.submit_contribution": "a soumis sa part",
    "guest.upload_piece": "a déposé une pièce",
    "guest.view_project": "a consulté le dossier",
}


@router.get("/api/notifications")
def notifications(current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db), days: int = 21):
    """Activité récente des co-traitants sur les AO du mandataire (in-app, sans email)."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(1, min(days, 90)))
    rows = db.query(AuditLog).filter(
        AuditLog.owner_id == current_user.id, AuditLog.actor_kind == "guest",
        AuditLog.action.in_(list(_NOTIF_LABELS)),
        AuditLog.created_at >= since
    ).order_by(AuditLog.created_at.desc()).limit(40).all()
    pids = {r.project_id for r in rows if r.project_id}
    names = {}
    if pids:
        names = {p.id: p.name for p in db.query(Project).filter(
            Project.id.in_(pids), Project.user_id == current_user.id).all()}
    return [{
        "id": r.id, "at": r.created_at.isoformat() if r.created_at else None,
        "project_id": r.project_id, "project": names.get(r.project_id, "Appel d'offres"),
        "actor": r.actor or "Un partenaire", "action": r.action,
        "label": _NOTIF_LABELS.get(r.action, r.action), "detail": r.detail or "",
    } for r in rows]


# ── Compte-à-compte : « Partagé avec moi » ───────────────────────────────────
# Si l'invité possède un compte Adjugo, il réclame le lien → l'AO partagé apparaît
# dans SON espace (il contribue en tant que lui-même, pas en invité bridé).
def _shared_item(inv: ProjectInvite, db: Session) -> dict:
    project = db.query(Project).filter(Project.id == inv.project_id, Project.deleted_at.is_(None)).first()
    owner_company = db.query(Company).filter(Company.user_id == inv.owner_id).first()
    c = db.query(ProjectContribution).filter(ProjectContribution.invite_id == inv.id).first()
    return {
        "token": inv.token, "project_id": inv.project_id,
        "project": (project.name if project else "Appel d'offres"),
        "mandataire": (owner_company.name if owner_company else "") or "",
        "role": inv.role or "cotraitant",
        "can_contribute": bool(getattr(inv, "can_contribute", True)),
        "contribution_status": (c.status if c else None),
        "deadline": project.deadline.isoformat() if project and project.deadline else None,
    }


@router.post("/api/invite/{token}/claim")
def claim_invite(token: str, request: Request, current_user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """Un titulaire de compte réclame un lien → l'AO entre dans son « Partagé avec moi »."""
    inv = _valid_invite(token, db)
    if inv.owner_id == current_user.id:
        raise HTTPException(400, "Vous êtes le mandataire de ce partage.")
    if inv.accepted_by_user_id and inv.accepted_by_user_id != current_user.id:
        raise HTTPException(409, "Ce lien a déjà été réclamé par un autre compte.")
    # Binding d'identité : si le lien cible une adresse précise, seul le compte de CETTE
    # adresse peut le réclamer (le secret de l'URL ne suffit plus à usurper le partenaire).
    if _is_email(inv.recipient) and (current_user.email or "").strip().lower() != inv.recipient.strip().lower():
        raise HTTPException(403, f"Ce lien est réservé à {_mask_email(inv.recipient)}. "
                                 f"Connectez-vous avec ce compte pour l'accepter.")
    if not inv.accepted_by_user_id:
        inv.accepted_by_user_id = current_user.id
        db.commit()
        audit.record(db, action="invite.claimed", owner_id=inv.owner_id, project_id=inv.project_id,
                     actor=(current_user.full_name or current_user.email or f"user:{current_user.id}")[:160],
                     actor_kind="guest", target_type="invite", target_id=inv.id,
                     detail=(current_user.email or "")[:255], ip=audit.client_ip(request))
    return _shared_item(inv, db)


@router.get("/api/shared")
def shared_with_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Les AO partagés AVEC moi (liens que j'ai réclamés). Pour « Partagé avec moi »."""
    rows = db.query(ProjectInvite).filter(
        ProjectInvite.accepted_by_user_id == current_user.id,
        ProjectInvite.revoked.is_(False)).order_by(ProjectInvite.created_at.desc()).all()
    return [_shared_item(inv, db) for inv in rows if not _is_expired(inv.expires_at)]


# ── Aperçu du dossier commun (ce que contiendra le ZIP) — sans le générer ────
@router.get("/api/projects/{project_id}/dossier-preview")
def dossier_preview(project_id: int, current_user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Liste les fichiers que contiendra le dossier commun, SANS lancer la génération
    (pas de LLM, pas de quota) — pour voir avant d'exporter."""
    _owned_project(project_id, current_user, db)
    files = [
        {"name": "memoire_technique.pdf", "kind": "Mémoire technique (savoir-faire fusionnés)"},
        {"name": "cerfa/DC1.pdf", "kind": "CERFA — lettre de candidature (groupement)"},
        {"name": "cerfa/DC2.pdf", "kind": "CERFA — déclaration du candidat"},
        {"name": "cerfa/ATTRI1.pdf", "kind": "CERFA — acte d'engagement"},
        {"name": "synthese_groupement.pdf", "kind": "Composition du groupement"},
        {"name": "fiche_appel_offres.pdf", "kind": "Fiche récapitulative de l'AO"},
    ]
    rows = db.query(ContributionPiece, ProjectContribution).join(
        ProjectContribution, ContributionPiece.contribution_id == ProjectContribution.id).filter(
        ContributionPiece.project_id == project_id, ContributionPiece.owner_id == current_user.id,
        ProjectContribution.status == "submitted").all()
    for pc, cb in rows:
        co = (cb.company_name or "cotraitant")
        files.append({"name": f"pieces_cotraitants/{co}/{pc.name}",
                      "kind": f"Pièce — {co}", "size": pc.file_size or 0})
    n_pieces = len(rows)
    return {"files": files, "count": len(files), "pieces_count": n_pieces}


# ── Compte-rendu PDF du consortium (synthèse partageable) ────────────────────
@router.get("/api/projects/{project_id}/consortium/report")
def consortium_report(project_id: int, current_user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    project = _owned_project(project_id, current_user, db)
    data = consortium_cockpit(project_id, current_user, db)
    company = db.query(Company).filter(Company.user_id == current_user.id).first()
    contribs = [_serialize_contribution(c, db) for c in db.query(ProjectContribution).filter(
        ProjectContribution.project_id == project_id,
        ProjectContribution.owner_id == current_user.id).all()]
    from app.services.consortium_report import generate_consortium_report_pdf
    pdf = generate_consortium_report_pdf(project.name, (company.name if company else ""), data, contribs)
    safe = re.sub(r'[^A-Za-z0-9._ -]', "_", (project.name or "consortium"))[:50]
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="Compte-rendu_{safe}.pdf"'})
