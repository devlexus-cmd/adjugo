"""
AGENT MÉMOIRE TECHNIQUE — pipeline multi-agents segmenté (façon TenderCrunch).

Au lieu d'un prompt monolithique, 4 étapes spécialisées :
  1. EXTRACTION  — lit le DCE (RC/CCTP/CCAP) → exigences + critères d'attribution.
  2. PLAN        — génère le sommaire de la réponse, calé sur les critères.
  3. RÉDACTION   — rédige chaque section en s'appuyant UNIQUEMENT sur la base de
                   connaissances de l'entreprise (RAG), avec citations [S1], [S2]…
  4. CONFORMITÉ  — vérifie que la réponse couvre bien chaque exigence extraite.

Traçabilité : chaque section porte les sources (doc + extrait) réellement utilisées.
Anti-hallucination : si aucune source ne couvre un point, l'IA l'indique au lieu
d'inventer (« information non disponible dans votre base de connaissances »).
"""
import logging

from sqlalchemy.orm import Session

from app.services.llm import complete, complete_json
from app.services import rag

logger = logging.getLogger("adjugo")


# ── 1. Extraction des exigences ──────────────────────────────────────────────
_EXTRACT_SYS = """Tu es un analyste de la commande publique. À partir d'un dossier de
consultation (RC, CCTP, CCAP), tu extrais les EXIGENCES et CRITÈRES qui devront être
traités dans le mémoire technique. N'invente rien : n'extrais que ce qui est dans le
texte. Réponds en JSON strict."""


def extract_requirements(dce_text: str) -> dict:
    user = f"""Analyse ce dossier et renvoie EXACTEMENT ce JSON :
{{
  "objet": "objet du marché en une phrase",
  "criteres_attribution": [
    {{"intitule": "critère (ex. valeur technique)", "ponderation": "pondération si citée, sinon \\"\\""}}
  ],
  "exigences": [
    {{"theme": "thème (ex. méthodologie, sécurité, délais, RSE, moyens humains, références)",
      "exigence": "ce que l'acheteur attend précisément (fidèle au texte)"}}
  ]
}}

DOSSIER :
{(dce_text or '')[:24000]}"""
    try:
        data = complete_json(_EXTRACT_SYS, user, max_tokens=2200, temperature=0.1)
    except Exception as e:
        logger.warning("memoire.extract en échec : %s", e)
        return {"objet": "", "criteres_attribution": [], "exigences": []}
    if not isinstance(data, dict):
        return {"objet": "", "criteres_attribution": [], "exigences": []}
    return data


# ── 2. Plan / sommaire ───────────────────────────────────────────────────────
_PLAN_SYS = """Tu es un responsable d'offres. Tu construis le SOMMAIRE d'un mémoire
technique répondant à un marché, calé sur les critères d'attribution et les exigences.
Sections logiques, ordonnées, sans remplissage. Réponds en JSON strict."""


def build_plan(objet: str, requirements: dict) -> list:
    import json as _json
    user = f"""Objet : {objet}
Critères et exigences (JSON) :
{_json.dumps(requirements, ensure_ascii=False)[:6000]}

Renvoie EXACTEMENT ce JSON :
{{"sections": [
  {{"titre": "titre de section", "objectif": "ce que la section doit démontrer",
    "requete": "mots-clés pour retrouver le savoir-faire de l'entreprise (3-8 mots)"}}
]}}
6 à 9 sections maximum, couvrant les critères et exigences."""
    try:
        data = complete_json(_PLAN_SYS, user, max_tokens=1800, temperature=0.2)
        secs = data.get("sections") if isinstance(data, dict) else None
        return [s for s in (secs or []) if isinstance(s, dict) and s.get("titre")]
    except Exception as e:
        logger.warning("memoire.plan en échec : %s", e)
        return []


# ── 3. Rédaction d'une section (RAG + citations) ─────────────────────────────
_WRITE_SYS = """Tu rédiges une section de mémoire technique pour un appel d'offres.
RÈGLES ABSOLUES :
- Tu ne t'appuies QUE sur les SOURCES fournies (savoir-faire réel de l'entreprise).
- Tu cites tes sources avec [S1], [S2]… à la fin des phrases concernées.
- Si une partie de l'objectif n'est couverte par aucune source, tu écris une phrase
  explicite : « [À compléter : information non présente dans votre base de connaissances] ».
- Style professionnel, concret, orienté preuve. Pas d'invention, pas de superlatifs creux.
- ALIGNEMENT SUR LA GRILLE : développe davantage et apporte le plus de preuves sur les
  critères d'attribution les plus PONDÉRÉS (ex. 40 % valeur technique, 20 % RSE) — c'est
  là que se gagnent les points.
Réponds en texte (pas de JSON), prêt à intégrer dans le mémoire."""


def write_section(section: dict, chunks: list, criteres=None) -> dict:
    if chunks:
        src = rag.sources_block(chunks)
    else:
        src = "(aucune source disponible)"
    grille = ""
    if criteres:
        items = "; ".join(f"{c.get('intitule','')} ({c.get('ponderation') or '?'})"
                          for c in criteres if isinstance(c, dict) and c.get("intitule"))
        if items:
            grille = f"\n\nGRILLE DE NOTATION PONDÉRÉE DE L'ACHETEUR : {items}\nMaximise le score : insiste sur les critères les plus pondérés liés à cette section."
    user = f"""Section à rédiger : {section.get('titre')}
Objectif : {section.get('objectif', '')}{grille}

SOURCES AUTORISÉES (savoir-faire de l'entreprise) :
{src}

Rédige la section (250-450 mots) en citant [S1], [S2]… Si rien ne couvre l'objectif,
indique-le explicitement plutôt que d'inventer."""
    try:
        content = complete(_WRITE_SYS, user, max_tokens=1400, temperature=0.3)
    except Exception as e:
        logger.warning("memoire.write en échec : %s", e)
        content = "[À compléter : la génération de cette section a échoué.]"
    used = [{"ref": f"S{i+1}", "doc_name": c["doc_name"], "chunk_id": c["chunk_id"],
             "excerpt": c["text"][:240]} for i, c in enumerate(chunks)]
    return {"titre": section.get("titre"), "content": content, "sources": used}


# ── 4. Contrôle de conformité ────────────────────────────────────────────────
_CHECK_SYS = """Tu es un contrôleur qualité. Tu vérifies qu'un mémoire technique couvre
bien CHAQUE exigence extraite du dossier de consultation. Pour chaque exigence : couverte,
partielle ou absente, avec une justification courte. Réponds en JSON strict, sans complaisance."""


def conformity_check(requirements: dict, sections: list) -> dict:
    import json as _json
    memo = "\n\n".join(f"## {s['titre']}\n{s['content']}" for s in sections)
    exig = requirements.get("exigences") or []
    user = f"""EXIGENCES (JSON) :
{_json.dumps(exig, ensure_ascii=False)[:5000]}

MÉMOIRE PRODUIT :
{memo[:14000]}

Renvoie EXACTEMENT ce JSON :
{{"couverture": [
  {{"exigence": "...", "statut": "couverte|partielle|absente", "commentaire": "court"}}
], "score_conformite": <0-100>, "manques": ["points à compléter avant dépôt"]}}"""
    try:
        data = complete_json(_CHECK_SYS, user, max_tokens=1800, temperature=0.1)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("memoire.check en échec : %s", e)
        return {}


# ── Orchestration ────────────────────────────────────────────────────────────
def generate_memoire(db: Session, user_id: int, dce_text: str, max_sections: int = 9) -> dict:
    """Pipeline complet. Renvoie un mémoire structuré, sourcé et contrôlé."""
    requirements = extract_requirements(dce_text)
    objet = requirements.get("objet", "")
    plan = build_plan(objet, requirements)[:max_sections]
    if not plan:
        plan = [{"titre": "Méthodologie et organisation", "objectif": "Démontrer la démarche",
                 "requete": "méthodologie organisation qualité"}]

    criteres = requirements.get("criteres_attribution") or []
    sections = []
    kb_used = False
    for sec in plan:
        chunks = rag.retrieve(db, user_id, sec.get("requete") or sec.get("titre", ""), k=5)
        if chunks:
            kb_used = True
        sections.append(write_section(sec, chunks, criteres=criteres))

    conformity = conformity_check(requirements, sections)

    return {
        "objet": objet,
        "criteres_attribution": requirements.get("criteres_attribution", []),
        "exigences": requirements.get("exigences", []),
        "sections": sections,
        "conformity": conformity,
        "kb_used": kb_used,
        "n_sections": len(sections),
    }
