"""
Router BASE DE CONNAISSANCES + génération assistée (parité TenderCrunch).

- Base de connaissances : l'entreprise dépose ses documents (mémoires passés, RSE,
  méthodologies…) → indexés (RAG) pour servir de SEULE source au contenu généré.
- Mémoire IA : pipeline multi-agents (extraction critères → plan → rédaction citée →
  contrôle conformité), 100% sourcé sur la base de connaissances.
- Questionnaire : auto-complétion cellule par cellule (RFP/RFI/DDQ) avec sources.

Onboarding "Do It For You" : import en masse pour construire la base rapidement.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ratelimit import limiter
from app.core.quota import consume_analysis
from app.models import User, KnowledgeDoc, KnowledgeChunk
from app.services.analysis import extract_dce_text
from app.services import rag
from app.services.agents.memoire import generate_memoire
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
    content = await file.read()
    if not content:
        raise HTTPException(400, "Fichier vide.")
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(413, "Fichier trop volumineux (50 Mo max).")
    try:
        text = extract_dce_text(file.filename, content, max_chars=400000)
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
def search(req: SearchReq, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Recherche traçable dans la base : renvoie les extraits sources (clic-vers-source)."""
    res = rag.retrieve(db, current_user.id, req.query or "", k=max(1, min(req.k, 12)))
    return {"results": res, "count": len(res)}


# ── Mémoire IA (multi-agents, sourcé) ────────────────────────────────────────
def _gen_memoire(text: str, current_user: User, db: Session) -> dict:
    # Génération longue → asynchrone (anti-timeout). Le client interroge /api/jobs/{id}.
    consume_analysis(current_user, db)
    from app.services.jobs import create_job, run_in_thread, job_out
    job = create_job(db, current_user.id, "memoire", "Mémoire technique")
    uid = current_user.id
    run_in_thread(job.id, lambda jdb: generate_memoire(jdb, uid, text))
    return job_out(job)


@router.post("/memoire-upload")
@limiter.limit("20/hour")
async def memoire_upload(request: Request, file: UploadFile = File(...),
                         current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    content = await file.read()
    if not content:
        raise HTTPException(400, "Fichier vide.")
    try:
        text = extract_dce_text(file.filename, content)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if len((text or "").strip()) < 60:
        raise HTTPException(422, "DCE trop court pour générer un mémoire.")
    return _gen_memoire(text, current_user, db)


class MemoireText(BaseModel):
    dce_text: str


@router.post("/memoire")
@limiter.limit("20/hour")
def memoire_text(request: Request, req: MemoireText, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if len((req.dce_text or "").strip()) < 60:
        raise HTTPException(422, "DCE trop court pour générer un mémoire.")
    return _gen_memoire(req.dce_text, current_user, db)


# ── Questionnaire (RFP/RFI/DDQ) ──────────────────────────────────────────────
class QuestionnaireReq(BaseModel):
    questions: list[str]


@router.post("/questionnaire")
@limiter.limit("20/hour")
def questionnaire(request: Request, req: QuestionnaireReq, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    qs = [q for q in (req.questions or []) if q and q.strip()]
    if not qs:
        raise HTTPException(422, "Aucune question fournie.")
    consume_analysis(current_user, db)
    # Asynchrone (anti-timeout) : jusqu'à 40 questions × LLM, traitées en tâche de fond.
    from app.services.jobs import create_job, run_in_thread, job_out
    job = create_job(db, current_user.id, "questionnaire", f"Questionnaire ({len(qs)} questions)")
    uid = current_user.id
    run_in_thread(job.id, lambda jdb: answer_questions(jdb, uid, qs))
    return job_out(job)
