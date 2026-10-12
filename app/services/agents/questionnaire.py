"""
AGENT QUESTIONNAIRE — auto-complétion granulaire (RFP / RFI / DDQ).

Sortie bi-modale d'Adjugo : en complément du mémoire long, ce module répond
question par question (« cellule par cellule ») à un questionnaire structuré,
en s'appuyant sur la base de connaissances de l'entreprise (RAG) et en citant
ses sources. Si aucune source ne couvre la question, on le dit (pas d'invention).
"""
import logging

from sqlalchemy.orm import Session

from app.services.llm import complete_ex, tenant_scope, LLMUnavailable
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


def _answer_from_chunks(question: str, chunks: list, user_id=None) -> dict:
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
        # tenant_scope reposé (perdu dans le ThreadPoolExecutor → isolation quota/disjoncteur).
        with tenant_scope(user_id):
            ans, stop = complete_ex(_SYS, user, max_tokens=600, temperature=0.2)
    except Exception as e:
        # Panne IA (disjoncteur/plafond) ≠ « base ne couvre pas » : on le marque comme ERREUR
        # technique (error=True) au lieu de faire croire que le savoir-faire est absent.
        logger.warning("questionnaire.answer en échec : %s", e)
        return {"question": question, "answer": "Génération momentanément indisponible — réessayez.",
                "sources": [], "covered": False, "error": True}
    # « Couvert » = l'IA a PROPOSÉ une réponse (pas la formule d'abstention). Ce n'est pas une
    # preuve que la réponse est exacte : l'écran dit « réponse proposée, à relire ».
    is_abstention = ans.strip().lower().startswith(("à compl", "a compl", "non couvert"))
    covered = not is_abstention
    coupe = stop == "max_tokens"
    if coupe:     # réponse interrompue : jamais présentée comme complète
        from app.services.memoire_export import TRUNCATED_NOTE
        ans = ans.rstrip() + "\n\n" + TRUNCATED_NOTE
    # Extraits affichés : SEULS ceux que l'IA a effectivement cités (plus de repli « tous les
    # extraits fournis », qui faisait passer une réponse non étayée pour « sourcée »).
    valid = rag.cited_refs(ans) & set(range(1, len(chunks) + 1))
    used = [{"ref": f"S{i+1}", "doc_name": c["doc_name"], "chunk_id": c["chunk_id"],
             "excerpt": c["text"][:200]} for i, c in enumerate(chunks) if (i + 1) in valid]
    return {"question": question, "answer": ans, "sources": used, "covered": covered, "coupe": coupe}


def answer_question(db: Session, user_id: int, question: str, kb_user_ids: list = None) -> dict:
    pool = kb_user_ids or [user_id]
    from app.services.llm import pii_scope
    from app.services.pii import from_team, team_of_users
    chunks = rag.retrieve_multi(db, pool, question, k=5, relevance=True)
    with pii_scope(from_team(team_of_users(db, pool))):
        return _answer_from_chunks(question, chunks, user_id=user_id)


def answer_questions(db: Session, user_id: int, questions: list, limit: int = 40, kb_user_ids: list = None) -> dict:
    qs = [q.strip() for q in (questions or []) if q and q.strip()][:limit]
    if not qs:
        return {"count": 0, "covered": 0, "errors": 0, "coverage_rate": 0, "answers": []}
    pool = kb_user_ids or [user_id]   # base COMMUNE de l'organisation
    # 1) Récupération RAG SÉQUENTIELLE (la session SQLAlchemy n'est pas thread-safe)
    prepared = [(q, rag.retrieve_multi(db, pool, q, k=5, relevance=True)) for q in qs]
    # 2) Réponses LLM EN PARALLÈLE (I/O-bound, aucun accès DB) — latence divisée. Noms des
    #    salariés masqués avant l'IA (documents du savoir-faire compris), coût journalisé.
    from concurrent.futures import ThreadPoolExecutor
    from app.services.llm import cost_meter, map_in_context, pii_scope
    from app.services.pii import from_team, team_of_users
    pz = from_team(team_of_users(db, pool))
    with pii_scope(pz), cost_meter("questionnaire", user_id), \
            ThreadPoolExecutor(max_workers=min(8, len(qs))) as ex:
        results = map_in_context(ex, lambda pc: _answer_from_chunks(pc[0], pc[1], user_id=user_id), prepared)
    # Panne IA TOTALE → on fait échouer le job (jobs.py rembourse + statut 'error') au lieu
    # de facturer un faux « 0 couvert ». Les erreurs partielles sont exclues de la couverture.
    errors = sum(1 for r in results if r.get("error"))
    if results and errors == len(results):
        raise LLMUnavailable("Service IA indisponible — aucune réponse générée.")
    scored = [r for r in results if not r.get("error")]
    covered = sum(1 for r in scored if r["covered"])
    return {"count": len(results), "covered": covered, "errors": errors,
            "coverage_rate": round(100 * covered / len(scored)) if scored else 0,
            "answers": results}
