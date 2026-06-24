"""
Tâches d'administration / cron.
  - POST /api/admin/run-alerts : scanne les documents expirants et envoie les alertes.
    Protégé par l'en-tête X-Cron-Secret == CRON_SECRET (ou DEMO_MODE en dev).
    À appeler quotidiennement depuis un planificateur (cron, Vercel Cron…).
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.core.security import get_current_user
from app.models import User
from app.services.alerts import run_document_expiry_alerts, run_tender_alerts, run_amont_alerts

settings = get_settings()
router = APIRouter(prefix="/api/admin", tags=["Administration"])


@router.get("/storage-diag")
def storage_diag(current_user: User = Depends(get_current_user)):
    """Diagnostic du stockage (sans exposer les secrets) : ce que le serveur voit
    réellement + un test d'écriture/lecture sur le bucket. RÉSERVÉ aux administrateurs."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(403, "Réservé à l'administrateur")
    s = settings

    def mask(v):
        v = v or ""
        return {"length": len(v), "preview": (v[:3] + "…" + v[-2:]) if len(v) > 6 else ("*" * len(v))}

    info = {
        "backend": s.STORAGE_BACKEND,
        "bucket": s.S3_BUCKET,
        "endpoint": s.S3_ENDPOINT_URL,
        "region": s.S3_REGION,
        "access_key": mask(s.AWS_ACCESS_KEY_ID),                 # attendu length=32 pour R2
        "secret_key_length": len(s.AWS_SECRET_ACCESS_KEY or ""),  # attendu 64
    }
    try:
        from app.services.storage import get_storage
        st = get_storage()
        key = f"_diag/{current_user.id}.txt"
        st.save(key, b"adjugo-diag", "text/plain")
        ok = st.load(key) == b"adjugo-diag"
        st.delete(key)
        info["test"] = "OK — écriture/lecture/suppression réussies" if ok else "ÉCHEC — relecture incohérente"
    except Exception as e:
        info["test"] = "ÉCHEC"
        info["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    return info


def _check_cron(request: Request):
    # Endpoints cron PUBLICS (sans login) : on EXIGE toujours le secret. Plus de
    # contournement DEMO_MODE — sinon, secret vide + DEMO_MODE=True rendait run-alerts /
    # run-tender-alerts / run-amont-alerts (emails + IA) déclenchables par n'importe qui.
    import secrets as _secrets
    secret = settings.CRON_SECRET
    if not secret:
        raise HTTPException(403, "CRON_SECRET non configuré")
    provided = request.headers.get("x-cron-secret", "")
    if not _secrets.compare_digest(provided, secret):   # comparaison à temps constant
        raise HTTPException(403, "Secret cron invalide")


@router.post("/run-backup")
def run_backup_now(current_user: User = Depends(get_current_user)):
    """Déclenche une sauvegarde immédiate de la base vers R2. Réservé à l'administrateur.
    (La sauvegarde tourne aussi toute seule chaque jour via le planificateur.)"""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(403, "Réservé à l'administrateur")
    from app.services.backup import run_backup
    return run_backup(keep=settings.BACKUP_KEEP)


@router.get("/backups")
def list_backups(current_user: User = Depends(get_current_user)):
    """Liste les sauvegardes présentes dans R2 (preuve que le filet fonctionne)."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(403, "Réservé à l'administrateur")
    from app.services.storage import get_storage
    keys = sorted([k for k in get_storage().list_keys("backups/") if k.endswith(".json.gz")], reverse=True)
    return {"count": len(keys), "backups": keys[:30]}


@router.post("/run-alerts")
def run_alerts(request: Request, db: Session = Depends(get_db)):
    _check_cron(request)
    return run_document_expiry_alerts(db)


@router.post("/run-tender-alerts")
def run_tender_alerts_endpoint(request: Request, db: Session = Depends(get_db)):
    """Veille AO : rejoue les recherches sauvegardées et notifie les nouveaux marchés."""
    _check_cron(request)
    return run_tender_alerts(db)


@router.post("/run-amont-alerts")
def run_amont_alerts_endpoint(request: Request, db: Session = Depends(get_db)):
    """Veille AMONT : va chercher les délibérations, détecte les projets d'investissement
    et notifie chaque utilisateur de ses nouveaux projets pertinents (avant l'AO)."""
    _check_cron(request)
    return run_amont_alerts(db)


class _DeleteUserIn(BaseModel):
    email: str
    confirm: bool = False


@router.post("/delete-user")
def delete_user_by_email(data: _DeleteUserIn, request: Request, db: Session = Depends(get_db)):
    """SUPPORT : supprime un compte par email + ses données. Protégé par CRON_SECRET. IRRÉVERSIBLE.
    Refuse le compte démo et un propriétaire d'org ayant d'autres membres (transférer d'abord)."""
    _check_cron(request)
    if not data.confirm:
        raise HTTPException(400, "Ajoutez \"confirm\": true pour confirmer la suppression.")
    email = (data.email or "").strip().lower()
    if email in ("demo@adjugo.fr",):
        raise HTTPException(400, "Le compte démo est protégé.")
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if not user:
        raise HTTPException(404, "Compte introuvable.")
    uid = user.id
    import app.models as M
    from app.models import Organization

    def delete_by(name, field, value):
        model = getattr(M, name, None)
        if model is not None and hasattr(model, field):
            db.query(model).filter(getattr(model, field) == value).delete(synchronize_session=False)

    org = db.query(Organization).filter(Organization.id == user.org_id).first() if user.org_id else None
    is_owner = bool(org and org.owner_id == uid)
    if is_owner:
        others = db.query(User).filter(User.org_id == org.id, User.id != uid).count()
        if others:
            raise HTTPException(409, "Propriétaire d'une organisation avec d'autres membres : "
                                     "transférez la propriété avant de supprimer.")
    try:
        if org and not is_owner:
            # Membre : réassigne les données métier au propriétaire, n'efface que le perso.
            from app.routers.org import _reassign_member_data
            _reassign_member_data(db, uid, org.owner_id)
            for name in ("CoSpace", "ProjectInvite", "ProjectContribution", "ContributionPiece"):
                model = getattr(M, name, None)
                if model is not None and hasattr(model, "owner_id"):
                    db.query(model).filter(model.owner_id == uid).update(
                        {model.owner_id: org.owner_id}, synchronize_session=False)
            for name in ("SavedSearch", "Company", "MatchingCriteria", "MatchingCriteriaExt"):
                delete_by(name, "user_id", uid)
            db.query(User).filter(User.id == uid).delete(synchronize_session=False)
        else:
            # Propriétaire solo (ou sans org) : suppression complète, enfants avant parents.
            pids = [p.id for p in db.query(M.Project).filter(M.Project.user_id == uid).all()]
            delete_by("ContributionPiece", "owner_id", uid)
            delete_by("ProjectContribution", "owner_id", uid)
            delete_by("ProjectInvite", "owner_id", uid)
            if pids:
                db.query(M.GeneratedDoc).filter(M.GeneratedDoc.project_id.in_(pids)).delete(synchronize_session=False)
            delete_by("AuditLog", "owner_id", uid)
            for name in ("Project", "Contact", "Document", "Cotraitant", "Invoice",
                         "KnowledgeChunk", "KnowledgeDoc", "Signal", "SavedSearch",
                         "Company", "MatchingCriteria", "MatchingCriteriaExt"):
                delete_by(name, "user_id", uid)
            if org:
                db.query(Organization).filter(Organization.id == org.id).delete(synchronize_session=False)
            db.query(User).filter(User.id == uid).delete(synchronize_session=False)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Suppression impossible : {e}")
    return {"ok": True, "deleted_email": email}
