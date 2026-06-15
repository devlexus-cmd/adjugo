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


def answer_question(db: Session, user_id: int, question: str) -> dict:
    chunks = rag.retrieve(db, user_id, question, k=5)
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


def answer_questions(db: Session, user_id: int, questions: list, limit: int = 40) -> dict:
    qs = [q.strip() for q in (questions or []) if q and q.strip()][:limit]
    results = [answer_question(db, user_id, q) for q in qs]
    covered = sum(1 for r in results if r["covered"])
    return {"count": len(results), "covered": covered,
            "coverage_rate": round(100 * covered / len(results)) if results else 0,
            "answers": results}
