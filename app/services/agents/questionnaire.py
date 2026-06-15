"""
AGENT QUESTIONNAIRE — auto-complétion granulaire (RFP / RFI / DDQ).

Sortie bi-modale d'Adjugo : en complément du mémoire long, ce module répond
question par question (« cellule par cellule ») à un questionnaire structuré,
en s'appuyant sur la base de connaissances de l'entreprise (RAG) et en citant
ses sources. Si aucune source ne couvre la question, on le dit (pas d'invention).
"""
import logging

from sqlalchemy.orm import Session

from app.services.llm import complete
from app.services import rag

logger = logging.getLogger("adjugo")

_SYS = """Tu réponds à une question d'un questionnaire d'appel d'offres (RFP/RFI/DDQ)
pour le compte d'une entreprise. RÈGLES :
- Réponds UNIQUEMENT à partir des SOURCES fournies (savoir-faire réel de l'entreprise).
- Réponse concise, factuelle, professionnelle (2 à 6 phrases sauf si la question appelle oui/non).
- Termine par les références utilisées entre crochets : [S1], [S2]…
- Si aucune source ne permet de répondre, réponds exactement :
  « À compléter — non couvert par votre base de connaissances. »
N'invente jamais de chiffre, certification, référence ou engagement."""


def _answer_from_chunks(question: str, chunks: list) -> dict:
    """Répond à UNE question depuis des chunks déjà récupérés (appel LLM, AUCUN accès DB
    → exécutable en parallèle dans un thread sans partager la session SQLAlchemy)."""
    if not chunks:
        return {"question": question, "answer": "À compléter — non couvert par votre base de connaissances.",
                "sources": [], "covered": False}
    user = f"""Question : {question}

SOURCES AUTORISÉES :
{rag.sources_block(chunks)}

Réponds en citant [S1], [S2]…"""
    try:
        ans = complete(_SYS, user, max_tokens=600, temperature=0.2)
    except Exception as e:
        logger.warning("questionnaire.answer en échec : %s", e)
        ans = "À compléter — erreur de génération."
    covered = "à compléter" not in ans.lower()[:30]
    used = [{"ref": f"S{i+1}", "doc_name": c["doc_name"], "chunk_id": c["chunk_id"],
             "excerpt": c["text"][:200]} for i, c in enumerate(chunks)]
    return {"question": question, "answer": ans, "sources": used if covered else [], "covered": covered}


def answer_question(db: Session, user_id: int, question: str) -> dict:
    return _answer_from_chunks(question, rag.retrieve(db, user_id, question, k=5))


def answer_questions(db: Session, user_id: int, questions: list, limit: int = 40) -> dict:
    qs = [q.strip() for q in (questions or []) if q and q.strip()][:limit]
    if not qs:
        return {"count": 0, "covered": 0, "coverage_rate": 0, "answers": []}
    # 1) Récupération RAG SÉQUENTIELLE (la session SQLAlchemy n'est pas thread-safe)
    prepared = [(q, rag.retrieve(db, user_id, q, k=5)) for q in qs]
    # 2) Réponses LLM EN PARALLÈLE (I/O-bound, aucun accès DB) — latence divisée
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(8, len(qs))) as ex:
        results = list(ex.map(lambda pc: _answer_from_chunks(pc[0], pc[1]), prepared))
    covered = sum(1 for r in results if r["covered"])
    return {"count": len(results), "covered": covered,
            "coverage_rate": round(100 * covered / len(results)) if results else 0,
            "answers": results}
