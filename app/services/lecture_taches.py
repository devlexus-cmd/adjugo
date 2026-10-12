"""
Tâches de fond de LECTURE d'un gros dossier (lecture intégrale + analyse), à part des autres
tâches de fond.

Pourquoi à part : une lecture peut durer plusieurs dizaines de minutes (OCR, lecture en deux temps).
Dans le pool commun des tâches (app.services.jobs, 4 fils), quelques gros dossiers bloquaient la
génération des mémoires et des questionnaires de tous les clients. Ici :
  • un exécuteur dédié de LECTURE_TACHES fils (défaut 2) ;
  • une seule lecture en attente ou en cours par organisation, et LECTURE_FILE_MAX au plus pour
    tout le serveur (défaut 6) : au-delà, la demande est refusée tout de suite (429, « réessayez
    dans quelques minutes »), AVANT tout débit ;
  • le fichier importé n'est pas gardé en mémoire dans la file : la tâche le relit depuis le
    stockage du dossier quand elle démarre.
Cycle de vie identique à app.services.jobs.run_in_thread (statut du Job en base, espace facturé
pour les appels IA, remboursement de l'analyse si la tâche échoue) ; la reprise après un
redémarrage est celle de tous les jobs (app.main._recover_orphan_jobs).
"""
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException

logger = logging.getLogger("adjugo")

KIND = "lecture_dossier"


def _env_int(name: str, default: int) -> int:
    try:
        v = int(str(os.getenv(name, "")).strip() or default)
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default


LECTURE_TACHES = _env_int("LECTURE_TACHES", 2)
LECTURE_FILE_MAX = _env_int("LECTURE_FILE_MAX", 6)
_EXECUTOR = ThreadPoolExecutor(max_workers=LECTURE_TACHES, thread_name_prefix="adjugo-lecture-job")

MSG_ORGANISATION = ("Une autre lecture de dossier est déjà en cours pour votre organisation. Votre dossier est "
                    "bien importé : relancez « Ré-analyser » quand elle sera terminée. Rien n'a été débité.")
MSG_SERVEUR = ("Beaucoup de dossiers sont en cours de lecture en ce moment. Votre dossier est bien importé : "
               "relancez « Ré-analyser » dans quelques minutes. Rien n'a été débité.")


def _en_vol(db, user_ids=None) -> int:
    from sqlalchemy import func
    from app.models import Job
    q = db.query(func.count(Job.id)).filter(Job.kind == KIND, Job.status.in_(["pending", "running"]))
    if user_ids is not None:
        q = q.filter(Job.user_id.in_(user_ids))
    return int(q.scalar() or 0)


def admettre(db, user) -> None:
    """Refuse (429) une nouvelle lecture en tâche de fond si l'organisation en a déjà une en cours,
    ou si le serveur en a déjà LECTURE_FILE_MAX. À appeler AVANT de débiter l'analyse."""
    from app.core.org import member_ids
    if _en_vol(db, member_ids(user, db)) >= 1:
        raise HTTPException(429, MSG_ORGANISATION, headers={"Retry-After": "120"})
    if _en_vol(db) >= LECTURE_FILE_MAX:
        raise HTTPException(429, MSG_SERVEUR, headers={"Retry-After": "120"})


def lancer(job_id: int, work, on_error=None) -> None:
    """Lance `work(db) -> dict` sur l'exécuteur des lectures, avec une session dédiée. Même cycle
    de vie que jobs.run_in_thread ; on_error(db, job) est appelé après l'échec (avant le
    remboursement), pour que le marché ne reste pas « en cours »."""
    def _run():
        from app.core.database import SessionLocal
        from app.models import Job, User
        from app.services.llm import tenant_scope
        db = SessionLocal()
        try:
            j = db.get(Job, job_id)
            if not j:
                return
            j.status = "running"
            db.commit()
            with tenant_scope(j.user_id):
                result = work(db)
            j = db.get(Job, job_id)
            j.result = result
            j.status = "done"
            db.commit()
        except Exception as e:
            logger.warning("lecture %s en échec : %s", job_id, type(e).__name__)
            try:
                db.rollback()
                j = db.get(Job, job_id)
                if j:
                    j.status = "error"
                    j.error = str(e)[:1000]
                    db.commit()
                    if on_error is not None:
                        try:
                            on_error(db, j)
                        except Exception as e2:      # noqa: BLE001
                            db.rollback()
                            logger.warning("lecture %s : état du marché non mis à jour : %s", job_id, type(e2).__name__)
                    from app.core.quota import refund_analysis
                    u = db.get(User, j.user_id)
                    if u:
                        refund_analysis(u, db)
            except Exception as e3:      # noqa: BLE001
                logger.warning("lecture %s : nettoyage après échec impossible : %s", job_id, type(e3).__name__)
        finally:
            db.close()

    _EXECUTOR.submit(_run)
