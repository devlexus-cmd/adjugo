"""
Router « MON SAVOIR-FAIRE » : la bibliothèque de documents de l'entreprise.

- Base de connaissances : l'entreprise dépose ses documents (mémoires passés, RSE,
  méthodologies…) → indexés (RAG) pour servir de SEULE source au contenu rédigé.
- Le dossier de présentation ne se rédige PLUS ici (rédaction, vague 2) : il se rédige dans
  l'atelier, sur la page du marché (app/routers/atelier.py), section par section, à partir de
  ces documents. Les anciennes routes /memoire et /memoire-upload répondent 410.
- Questionnaire : auto-complétion cellule par cellule (RFP/RFI/DDQ) avec sources.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ratelimit import limiter
from app.core.quota import consume_analysis
from app.core.org import member_ids
from app.models import User, KnowledgeDoc, KnowledgeChunk
from app.services.analysis import extract_dce_text
from app.core.uploads import aread_upload_limited
from starlette.concurrency import run_in_threadpool
from app.services import rag
from app.services.agents.questionnaire import answer_questions

logger = logging.getLogger("adjugo")
router = APIRouter(prefix="/api/knowledge", tags=["Base de connaissances & génération (RAG)"])

_KINDS = {"memoire", "rse", "methodologie", "certification", "reference", "autre"}


def _doc_out(d: KnowledgeDoc) -> dict:
    return {"id": d.id, "name": d.name, "kind": d.kind, "char_count": d.char_count,
            "n_chunks": d.n_chunks, "created_at": d.created_at.isoformat() if d.created_at else None}


# ── Base de connaissances ────────────────────────────────────────────────────
@router.get("/")
def list_docs(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    docs = (db.query(KnowledgeDoc).filter(KnowledgeDoc.user_id == current_user.id)
            .order_by(KnowledgeDoc.created_at.desc()).all())
    chunks = db.query(KnowledgeChunk).filter(KnowledgeChunk.user_id == current_user.id).count()
    return {"docs": [_doc_out(d) for d in docs], "total_docs": len(docs), "total_chunks": chunks}


@router.post("/upload")
@limiter.limit("60/hour")
async def upload_doc(request: Request, file: UploadFile = File(...), kind: str = Form("autre"),
                     current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    content = await aread_upload_limited(file)   # lecture bornée : 413 au-delà de 50 Mo
    try:
        text = await run_in_threadpool(extract_dce_text, file.filename, content, max_chars=400000)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if len((text or "").strip()) < 40:
        raise HTTPException(422, "Texte extrait trop court (document scanné/illisible ?).")
    k = kind if kind in _KINDS else "autre"
    doc = rag.index_document(db, current_user.id, file.filename or "Document", text, kind=k)
    return {"doc": _doc_out(doc)}


class TextDoc(BaseModel):
    name: str = "Document collé"
    text: str
    kind: str = "autre"


@router.post("/text")
@limiter.limit("60/hour")
def add_text(request: Request, req: TextDoc, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if len((req.text or "").strip()) < 40:
        raise HTTPException(422, "Texte trop court.")
    k = req.kind if req.kind in _KINDS else "autre"
    doc = rag.index_document(db, current_user.id, req.name or "Document collé", req.text, kind=k)
    return {"doc": _doc_out(doc)}


@router.delete("/{doc_id}")
def delete_doc(doc_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    doc = db.query(KnowledgeDoc).filter(KnowledgeDoc.id == doc_id,
                                        KnowledgeDoc.user_id == current_user.id).first()
    if not doc:
        raise HTTPException(404, "Document introuvable.")
    db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc.id).delete()
    db.delete(doc)
    db.commit()
    return {"ok": True}


class SearchReq(BaseModel):
    query: str
    k: int = 6


@router.post("/search")
@limiter.limit("120/hour")
def search(request: Request, req: SearchReq, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Recherche traçable dans la base : renvoie les extraits sources (clic-vers-source)."""
    res = rag.retrieve(db, current_user.id, req.query or "", k=max(1, min(req.k, 12)))
    return {"results": res, "count": len(res)}


# ── Dossier de présentation : remplacé par l'atelier (page du marché) ───────────────
MSG_ATELIER = ("Le dossier de présentation se rédige maintenant sur la page du marché, carte « Dossier de "
               "présentation ». Vos documents restent ici et servent de source.")


@router.post("/memoire-upload")
def memoire_upload(current_user: User = Depends(get_current_user)):
    raise HTTPException(410, MSG_ATELIER)


@router.post("/memoire")
def memoire_text(current_user: User = Depends(get_current_user)):
    raise HTTPException(410, MSG_ATELIER)


# ── Questionnaire (RFP/RFI/DDQ) ──────────────────────────────────────────────
class QuestionnaireReq(BaseModel):
    questions: list[str]


@router.post("/questionnaire")
@limiter.limit("20/hour")
def questionnaire(request: Request, req: QuestionnaireReq, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    qs = [q for q in (req.questions or []) if q and q.strip()]
    if not qs:
        raise HTTPException(422, "Aucune question fournie.")
    uids = member_ids(current_user, db)
    if db.query(KnowledgeChunk.id).filter(KnowledgeChunk.user_id.in_(uids)).first() is None:
        raise HTTPException(422, "La base de connaissances de votre organisation est vide : ajoutez au moins "
                                 "un document avant de répondre à un questionnaire.")
    consume_analysis(current_user, db)
    # Asynchrone (anti-timeout) : jusqu'à 40 questions × LLM, traitées en tâche de fond.
    from app.services.jobs import create_job, run_in_thread, job_out
    job = create_job(db, current_user.id, "questionnaire", f"Questionnaire ({len(qs)} questions)")
    uid = current_user.id
    run_in_thread(job.id, lambda jdb: answer_questions(jdb, uid, qs, kb_user_ids=uids))
    return job_out(job)
