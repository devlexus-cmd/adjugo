"""
Jobs asynchrones — traitements IA longs hors requête HTTP.

Les générations longues (mémoire fusionné ~3 min, war room, ingestion DCE) ne
doivent pas bloquer une requête HTTP synchrone (risque de timeout sur le PaaS et
de worker bloqué). On crée un Job, on le traite dans un thread avec sa PROPRE
session DB, et le client interroge GET /api/jobs/{id} jusqu'au résultat.

Le résultat est persisté en base (Postgres partagé entre workers) → le polling
fonctionne quel que soit le worker qui répond.
"""
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from app.core.database import SessionLocal
from app.models import Job

logger = logging.getLogger("adjugo")

# File d'exécution BORNÉE. Des threads démons illimités exposaient à l'épuisement
# mémoire/CPU et au dépassement des limites de l'API IA sous un pic de soumissions.
# Un pool borné traite N jobs à la fois ; les suivants restent 'pending' en base et
# sont pris dès qu'un worker se libère → back-pressure propre, sans dépendance externe.
# La durabilité inter-redémarrage est assurée par _recover_orphan_jobs (au démarrage).
_MAX_JOB_WORKERS = max(1, int(os.getenv("JOB_WORKERS", "4")))
_EXECUTOR = ThreadPoolExecutor(max_workers=_MAX_JOB_WORKERS, thread_name_prefix="adjugo-job")


def create_job(db, user_id: int, kind: str, label: str = "") -> Job:
    j = Job(user_id=user_id, kind=kind, status="pending", label=label[:255])
    db.add(j)
    db.commit()
    db.refresh(j)
    return j


def run_in_thread(job_id: int, work, on_error=None, tenant_id=None, error_message=None) -> None:
    """Lance `work(db) -> dict` dans un thread démon, avec une session DB dédiée.
    Le statut et le résultat du Job sont mis à jour en base.

    on_error(db, job) : ce qu'il faut défaire quand le traitement échoue (défaut : rembourser UNE
    analyse au propriétaire du job — le cas des traitements qui en ont consommé une à la
    soumission). tenant_id : espace facturé pour les appels IA (défaut : le propriétaire du job).
    error_message : message montré au client à la place de l'erreur technique (jamais de détail
    interne quand il est fourni)."""
    def _run():
        from app.services.llm import tenant_scope
        db = SessionLocal()
        try:
            j = db.get(Job, job_id)
            if not j:
                return
            j.status = "running"
            db.commit()
            # Attribution des tokens IA au tenant propriétaire du job (plafond par tenant).
            with tenant_scope(tenant_id if tenant_id is not None else j.user_id):
                result = work(db)
            j = db.get(Job, job_id)
            j.result = result
            j.status = "done"
            db.commit()
        except Exception as e:
            logger.warning("job %s en échec : %s", job_id, e)
            try:
                db.rollback()
                j = db.get(Job, job_id)
                if j:
                    j.status = "error"
                    j.error = (error_message or str(e))[:1000]
                    db.commit()
                    if on_error is not None:
                        on_error(db, j)
                    else:
                        # Le traitement a consommé une analyse à la soumission mais n'a rien
                        # produit → on rembourse le client.
                        from app.core.quota import refund_analysis
                        from app.models import User
                        u = db.get(User, j.user_id)
                        if u:
                            refund_analysis(u, db)
            except Exception as e2:
                logger.warning("job %s : nettoyage après échec impossible : %s", job_id, e2)
        finally:
            db.close()

    _EXECUTOR.submit(_run)


def job_out(j: Job) -> dict:
    return {"id": j.id, "kind": j.kind, "status": j.status, "label": j.label,
            "result": j.result if j.status == "done" else None,
            "error": j.error if j.status == "error" else "",
            "created_at": j.created_at.isoformat() if j.created_at else None}
