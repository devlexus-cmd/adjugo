"""
Tâches d'administration / cron.
  - POST /api/admin/run-alerts : scanne les documents expirants et envoie les alertes.
    Protégé par l'en-tête X-Cron-Secret == CRON_SECRET (ou DEMO_MODE en dev).
    À appeler quotidiennement depuis un planificateur (cron, Vercel Cron…).
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.services.alerts import run_document_expiry_alerts, run_tender_alerts, run_amont_alerts

settings = get_settings()
router = APIRouter(prefix="/api/admin", tags=["Administration"])


def _check_cron(request: Request):
    secret = settings.CRON_SECRET
    provided = request.headers.get("x-cron-secret", "")
    if secret:
        if provided != secret:
            raise HTTPException(403, "Secret cron invalide")
    elif not settings.DEMO_MODE:
        raise HTTPException(403, "CRON_SECRET non configuré")


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
