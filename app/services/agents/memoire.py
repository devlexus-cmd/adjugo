"""
AGENT MÉMOIRE TECHNIQUE — pipeline multi-agents segmenté (façon TenderCrunch).

Au lieu d'un prompt monolithique, 4 étapes spécialisées :
  1. EXTRACTION  — lit le DCE (RC/CCTP/CCAP) → exigences + critères d'attribution.
  2. PLAN        — génère le sommaire de la réponse, calé sur les critères.
  3. RÉDACTION   — rédige chaque section en s'appuyant UNIQUEMENT sur la base de
                   connaissances de l'entreprise (RAG), avec citations [S1], [S2]…
  4. CONFORMITÉ  — vérifie que la réponse couvre bien chaque exigence extraite.

Ce qu'on affiche, sans promettre plus : chaque section porte les extraits que l'IA a
effectivement cités ([S1]…). Un renvoi ne prouve pas que la phrase est exacte : le contrôle
des faits arrive en vague 3 ; d'ici là, aucun badge « sourcé ». La consigne demande à l'IA
d'écrire « [À compléter] » quand rien ne couvre un point, sans garantie qu'elle s'y tienne.
"""
import logging

from sqlalchemy.orm import Session

from app.services.llm import complete_ex, complete_json, tenant_scope
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


def write_section(section: dict, chunks: list, criteres=None, user_id=None) -> dict:
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
    err, coupe = False, False
    try:
        # tenant_scope reposé : le contextvar (quota/disjoncteur PAR TENANT) n'est pas hérité
        # par les threads du ThreadPoolExecutor appelant → sinon ces appels (le gros du coût)
        # échappent à l'isolation « voisin bruyant ».
        with tenant_scope(user_id):
            content, stop = complete_ex(_WRITE_SYS, user, max_tokens=1400, temperature=0.3)
        coupe = stop == "max_tokens"
    except Exception as e:
        logger.warning("memoire.write en échec : %s", e)
        content = "[À compléter : la génération de cette section a échoué.]"
        err = True   # échec TECHNIQUE (IA indispo)
    return _section_out(section, content, chunks, err, coupe)


def _section_out(section, content, chunks, err, coupe, names_by_user=None) -> dict:
    """Section rédigée + ce qu'on peut en dire HONNÊTEMENT, sans badge « sourcé » :
    - `sources` : SEULS les extraits que l'IA a effectivement cités ([S1]…[Sn], numéros valides).
      Plus de repli « tous les extraits fournis » : un extrait non cité n'est pas une source.
      Un renvoi cité ne prouve pas que la phrase est exacte (contrôle des faits : vague 3) ;
    - `extraits_fournis` : combien d'extraits de vos documents l'IA avait sous les yeux ;
    - `coupe` : texte interrompu par la limite de longueur → marqué à la fin, jamais complet."""
    from app.services.memoire_export import TRUNCATED_NOTE
    if coupe and not err:
        content = (content or "").rstrip() + "\n\n" + TRUNCATED_NOTE
    n = len(chunks)
    cited = rag.cited_refs(content) & set(range(1, n + 1))
    used = []
    if not err:
        for i, c in enumerate(chunks):
            if (i + 1) in cited:
                s = {"ref": f"S{i+1}", "doc_name": c["doc_name"], "chunk_id": c["chunk_id"],
                     "excerpt": c["text"][:240]}
                if names_by_user is not None:
                    s["company"] = names_by_user.get(c.get("user_id"), "Entreprise")
                used.append(s)
    return {"titre": section.get("titre"), "content": content, "sources": used,
            "extraits_fournis": 0 if err else n, "coupe": bool(coupe and not err), "error": err}


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
def generate_memoire(db: Session, user_id: int, dce_text: str, max_sections: int = 9,
                     kb_user_ids: list = None) -> dict:
    """Pipeline complet. Renvoie un dossier de présentation structuré, avec les extraits cités.
    kb_user_ids = base COMMUNE à interroger (membres de l'organisation) ; défaut = [user_id].
    Les noms des salariés de l'organisation (équipe du profil entreprise) sont masqués avant
    chaque appel à l'IA (documents du savoir-faire compris) et remis en clair sans IA ; le coût
    IA du dossier complet est journalisé."""
    from app.services.llm import cost_meter, pii_scope
    from app.services.pii import from_team, team_of_users
    pz = from_team(team_of_users(db, kb_user_ids or [user_id]))
    with pii_scope(pz), cost_meter("dossier de présentation (savoir-faire)", user_id):
        return _generate_memoire(db, user_id, dce_text, max_sections, kb_user_ids)


def _generate_memoire(db: Session, user_id: int, dce_text: str, max_sections: int = 9,
                      kb_user_ids: list = None) -> dict:
    requirements = extract_requirements(dce_text)
    objet = requirements.get("objet", "")
    plan = build_plan(objet, requirements)[:max_sections]
    if not plan:
        plan = [{"titre": "Méthodologie et organisation", "objectif": "Démontrer la démarche",
                 "requete": "méthodologie organisation qualité"}]

    criteres = requirements.get("criteres_attribution") or []
    # Récupération RAG (rapide) puis rédaction des sections EN PARALLÈLE (latence ÷ ~6)
    from concurrent.futures import ThreadPoolExecutor
    pool = kb_user_ids or [user_id]   # base COMMUNE de l'organisation (sinon le seul user)
    prepared = []
    for sec in plan:
        chunks = rag.retrieve_multi(db, pool, sec.get("requete") or sec.get("titre", ""), k=5, relevance=True)
        prepared.append((sec, chunks))
    # map_in_context : chaque fil reçoit la portée du job (noms masqués, compteur de coût).
    from app.services.llm import map_in_context
    with ThreadPoolExecutor(max_workers=min(6, len(prepared) or 1)) as ex:
        sections = map_in_context(ex, lambda pc: write_section(pc[0], pc[1], criteres=criteres, user_id=user_id),
                                  prepared)
    # Si TOUTES les sections ont échoué techniquement (IA indispo / plafond / panne), le mémoire
    # est 100 % « [À compléter] » : on LÈVE pour que le job passe en 'error' et que le quota soit
    # REMBOURSÉ — au lieu de débiter le client pour un livrable vide.
    errs = sum(1 for s in sections if s.get("error"))
    if sections and errs == len(sections):
        from app.services.llm import LLMUnavailable
        raise LLMUnavailable("Service IA indisponible — mémoire non généré.")

    conformity = conformity_check(requirements, sections)

    return {
        "objet": objet,
        "criteres_attribution": requirements.get("criteres_attribution", []),
        "exigences": requirements.get("exigences", []),
        "sections": sections,
        "conformity": conformity,
        "n_sections": len(sections),
        "n_coupees": sum(1 for s in sections if s.get("coupe")),
    }


# ── MERGED BRAIN : mémoire unifié de co-traitance ────────────────────────────
_MERGED_SYS = """Tu rédiges UNE section de mémoire technique pour un GROUPEMENT d'entreprises
qui répondent ensemble à un marché. Tu disposes du savoir-faire de PLUSIEURS entreprises
(sources attribuées à chacune).
RÈGLES ABSOLUES :
- Tu ne t'appuies QUE sur les SOURCES fournies. Cite [S1], [S2]…
- Rédige un texte UNIFIÉ et FLUIDE, comme une seule offre cohérente (ton homogène),
  jamais un copier-coller de deux parties juxtaposées.
- Attribue chaque savoir-faire à la BONNE entreprise et, quand c'est pertinent, CROISE
  les apports (ex. « la méthodologie de [Entreprise A] s'appuie sur les moyens de [Entreprise B] »).
- Si l'objectif n'est pas couvert par les sources, écris « [À compléter : … ] » plutôt qu'inventer.
- Insiste sur les critères les plus PONDÉRÉS de la grille de notation.
Réponds en texte (pas de JSON)."""


def _write_merged_section(section, chunks, names_by_user, criteres=None, billing_user_id=None):
    src = rag.sources_block_attributed(chunks, names_by_user) if chunks else "(aucune source)"
    grille = ""
    if criteres:
        items = "; ".join(f"{c.get('intitule','')} ({c.get('ponderation') or '?'})"
                          for c in criteres if isinstance(c, dict) and c.get("intitule"))
        if items:
            grille = f"\n\nGRILLE PONDÉRÉE : {items}"
    companies = ", ".join(sorted(set(names_by_user.values())))
    user = f"""Section : {section.get('titre')}
Objectif : {section.get('objectif','')}
Entreprises du groupement : {companies}{grille}

SOURCES ATTRIBUÉES :
{src}

Rédige la section unifiée (250-450 mots), en attribuant et en croisant les apports."""
    err, coupe = False, False
    try:
        with tenant_scope(billing_user_id):
            content, stop = complete_ex(_MERGED_SYS, user, max_tokens=1500, temperature=0.3)
        coupe = stop == "max_tokens"
    except Exception as e:
        logger.warning("merged.write en échec : %s", e)
        content = "[À compléter : génération échouée.]"
        err = True
    return _section_out(section, content, chunks, err, coupe, names_by_user=names_by_user)


def generate_merged_memoire(db, members: list, dce_text: str, max_sections: int = 9, billing_user_id=None) -> dict:
    """Mémoire UNIFIÉ d'un groupement. members = [{user_id, name, role}] (routeur archivé, non monté).
    Les noms des salariés de TOUS les membres sont masqués avant l'IA."""
    from app.services.llm import cost_meter, pii_scope
    from app.services.pii import from_team, team_of_users
    pz = from_team(team_of_users(db, [m.get("user_id") for m in members if m.get("user_id")]))
    with pii_scope(pz), cost_meter("dossier de présentation (groupement)", billing_user_id):
        return _generate_merged_memoire(db, members, dce_text, max_sections, billing_user_id)


def _generate_merged_memoire(db, members: list, dce_text: str, max_sections: int = 9, billing_user_id=None) -> dict:
    user_ids = [m["user_id"] for m in members if m.get("user_id")]
    names_by_user = {m["user_id"]: (m.get("name") or "Entreprise") for m in members if m.get("user_id")}

    requirements = extract_requirements(dce_text)
    objet = requirements.get("objet", "")
    plan = build_plan(objet, requirements)[:max_sections]
    if not plan:
        plan = [{"titre": "Méthodologie et organisation du groupement",
                 "objectif": "Démontrer l'organisation conjointe", "requete": "méthodologie organisation"}]
    criteres = requirements.get("criteres_attribution") or []

    from concurrent.futures import ThreadPoolExecutor
    prepared, contributors = [], set()
    for sec in plan:
        chunks = rag.retrieve_multi(db, user_ids, sec.get("requete") or sec.get("titre", ""), k=8)
        for c in chunks:
            contributors.add(names_by_user.get(c.get("user_id")))
        prepared.append((sec, chunks))
    from app.services.llm import map_in_context
    with ThreadPoolExecutor(max_workers=min(6, len(prepared) or 1)) as ex:
        sections = map_in_context(ex, lambda pc: _write_merged_section(pc[0], pc[1], names_by_user, criteres,
                                                                       billing_user_id=billing_user_id), prepared)

    errs = sum(1 for s in sections if s.get("error"))
    if sections and errs == len(sections):
        from app.services.llm import LLMUnavailable
        raise LLMUnavailable("Service IA indisponible — mémoire de groupement non généré.")

    conformity = conformity_check(requirements, sections)
    return {
        "objet": objet, "membres": [{"name": names_by_user[u], "user_id": u} for u in user_ids],
        "criteres_attribution": criteres, "exigences": requirements.get("exigences", []),
        "sections": sections, "conformity": conformity,
        "contributors": sorted([c for c in contributors if c]),
        "n_sections": len(sections),
    }
