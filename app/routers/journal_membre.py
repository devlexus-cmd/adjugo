"""
Journal MEMBRE vérifiable (co-traitance v2, vague 4) — routes.

Lien magique (sans compte, portée stricte invite.project_id) :
  GET /api/invite/{token}/journal/integrity            — sous-chaîne recalculée + verdict
  GET /api/invite/{token}/journal/export?format=json   — export vérifiable hors ligne (JSON)
  GET /api/invite/{token}/journal/export?format=pdf    — même export, lisible (PDF)

« Partagé avec moi » (compte Adjugo qui a réclamé le lien ; {project_id} = champ project_id
d'un élément de GET /api/shared) :
  GET /api/shared/{project_id}/journal
  GET /api/shared/{project_id}/journal/integrity
  GET /api/shared/{project_id}/journal/export?format=json|pdf

Doctrine : jamais d'IP, d'email ni d'identifiant interne d'un autre membre ; les entrées des
autres sont engagées par un sceau (sha256 à sens unique), pas révélées. Aucun appel LLM, aucun
appel externe ; résultats en cache in-process (process unique). Logique : app/services/journal_membre.py.
"""
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.ratelimit import limiter
from app.core.security import get_current_user
from app.models import Project, ProjectInvite, User
from app.services import audit
from app.services import journal_membre as jm
from app.services.groupement_members import active_invite_filter

router = APIRouter(tags=["Co-traitance"])


def _project_of(inv, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == inv.project_id, Project.deleted_at.is_(None)).first()
    if not project:
        raise HTTPException(404, "Projet introuvable ou retiré")
    return project


def _guest_invite(token: str, db: Session):
    from app.routers.invites import _valid_invite
    inv = _valid_invite(token, db)
    return inv, _project_of(inv, db)


def _shared_invite(project_id: int, user: User, db: Session):
    """Lien réclamé par CE compte sur ce marché (actif, non expiré) — sinon 404."""
    from app.routers.invites import _is_expired
    rows = db.query(ProjectInvite).filter(
        ProjectInvite.project_id == project_id, ProjectInvite.accepted_by_user_id == user.id,
        active_invite_filter()).order_by(ProjectInvite.created_at.desc()).all()
    inv = next((i for i in rows if not _is_expired(i.expires_at)), None)
    if inv is None:
        raise HTTPException(404, "Dossier partagé introuvable")
    return inv, _project_of(inv, db)


def _safe_name(s: str) -> str:
    # Accents translittérés (« Réhabilitation » → « Rehabilitation ») plutôt que remplacés par « _ ».
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "marche").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9._ -]", "_", s)[:50].strip() or "marche"


def _export(inv, project, fmt: str, request: Request, db: Session) -> Response:
    fmt = (fmt or "json").strip().lower()
    if fmt not in ("json", "pdf"):
        raise HTTPException(422, "Format inconnu : json ou pdf.")
    payload = jm.export_payload(db, inv, project)
    name = f"Journal_{_safe_name(project.name)}"
    if fmt == "pdf":
        content, media, fname = jm.export_pdf(payload), "application/pdf", f"{name}.pdf"
    else:
        content, media, fname = jm.export_json_bytes(payload), "application/json", f"{name}.json"
    # Journalisé APRÈS construction : l'export suivant contiendra cette entrée (il prolonge
    # celui-ci, la comparaison des deux reste valable).
    audit.record(db, action="guest.export_journal", owner_id=inv.owner_id, project_id=inv.project_id,
                 actor=(inv.company_name or "invité")[:160], actor_kind="guest",
                 target_type="invite", target_id=inv.id, invite_id=inv.id,
                 detail=fmt.upper(), ip=audit.client_ip(request))
    jm.forget(inv.id)                 # le verdict en cache ne compte pas encore cette entrée
    return Response(content=content, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{fname}"',
                             "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


# ── Lien magique ───────────────────────────────────────────────────────────────────────

@router.get("/api/invite/{token}/journal/integrity")
@limiter.limit("30/minute")
def guest_journal_integrity(token: str, request: Request, db: Session = Depends(get_db)):
    """Sous-chaîne des entrées qui concernent le membre, recalculée, + verdict."""
    inv, _project = _guest_invite(token, db)
    return jm.verify_member(db, inv)


@router.get("/api/invite/{token}/journal/export")
@limiter.limit("10/minute")
def guest_journal_export(token: str, request: Request, format: str = Query("json"),
                         db: Session = Depends(get_db)):
    inv, project = _guest_invite(token, db)
    return _export(inv, project, format, request, db)


# ── « Partagé avec moi » (compte) ──────────────────────────────────────────────────────

@router.get("/api/shared/{project_id}/journal")
@limiter.limit("60/minute")
def shared_journal(project_id: int, request: Request, current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    inv, _project = _shared_invite(project_id, current_user, db)
    return {"entries": jm.journal_entries(db, inv), "integrity_label": jm.INTEGRITY_LABEL}


@router.get("/api/shared/{project_id}/journal/integrity")
@limiter.limit("30/minute")
def shared_journal_integrity(project_id: int, request: Request,
                             current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inv, _project = _shared_invite(project_id, current_user, db)
    return jm.verify_member(db, inv)


@router.get("/api/shared/{project_id}/journal/export")
@limiter.limit("10/minute")
def shared_journal_export(project_id: int, request: Request, format: str = Query("json"),
                          current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inv, project = _shared_invite(project_id, current_user, db)
    return _export(inv, project, format, request, db)
