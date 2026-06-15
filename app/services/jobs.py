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
import threading

from app.core.database import SessionLocal
from app.models import Job

logger = logging.getLogger("adjugo")


def create_job(db, user_id: int, kind: str, label: str = "") -> Job:
    j = Job(user_id=user_id, kind=kind, status="pending", label=label[:255])
    db.add(j)
    db.commit()
    db.refresh(j)
    return j


def run_in_thread(job_id: int, work) -> None:
    """Lance `work(db) -> dict` dans un thread démon, avec une session DB dédiée.
    Le statut et le résultat du Job sont mis à jour en base."""
    def _run():
        db = SessionLocal()
        try:
            j = db.get(Job, job_id)
            if not j:
                return
            j.status = "running"
            db.commit()
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
                    j.error = str(e)[:1000]
                    db.commit()
            except Exception:
                pass
        finally:
            db.close()

    threading.Thread(target=_run, daemon=True).start()


def job_out(j: Job) -> dict:
    return {"id": j.id, "kind": j.kind, "status": j.status, "label": j.label,
            "result": j.result if j.status == "done" else None,
            "error": j.error if j.status == "error" else "",
            "created_at": j.created_at.isoformat() if j.created_at else None}
