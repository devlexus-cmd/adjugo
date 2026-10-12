"""
MOTEUR DE RÉDACTION du dossier de présentation (le « mémoire technique »).

Depuis la vague 2 de la rédaction, c'est le moteur de l'ATELIER (app/services/atelier.py) :
une partie à la fois, en tâche de fond, Sonnet, extraits cités [S1], [S2]… (`rediger_partie`,
`raccourcir_partie`). Le plan ne vient plus de l'IA : il suit le cadre de réponse imposé, la
grille retrouvée dans le règlement ou un plan simple (app/services/atelier_plan.py), et la
« conformité notée par l'IA » a disparu (doctrine : jamais une note produite par l'IA).

Restent ici, pour le mémoire FUSIONNÉ de l'ancien espace co-traitance (routeur archivé, non
monté ; repris en vague 4) : extraction des exigences, plan, rédaction par section, contrôle.

Ce qu'on affiche, sans promettre plus : chaque section porte les extraits que l'IA a
effectivement cités ([S1]…). Un renvoi ne prouve pas que la phrase est exacte : les faits sans
source sont signalés « à relire » (app/services/faits_a_relire.py), rien n'est marqué comme bon.
"""
import logging

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
    {{"intitule": "critère (ex. valeur technique)", "ponderation": "pondération si citée, sinon \\"\\"",
      "extrait": "la phrase du règlement où figurent ce critère et son poids, recopiée MOT POUR MOT"}}
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


# ── 2 bis. La grille, contrôlée contre le texte du dossier (sans IA) ─────────
def _criteres_controles(requirements: dict, dce_text: str) -> list:
    """Critères PROPOSÉS par l'IA, passés par la grille « Comment vous serez noté »
    (app/services/grille_notation.py) : seules restent les lignes dont la phrase est retrouvée
    dans le dossier, avec leur poids TEL QU'ÉCRIT dans cette phrase (sinon sans poids). Une ligne
    non retrouvée n'entre pas dans le plan. Jamais de poids ni d'ordre inventés (étude §7)."""
    try:
        from app.services import grille_notation as gn
        g = gn.build_grille({"criteres_attribution": (requirements or {}).get("criteres_attribution") or []},
                            dce_text or "")
        return [{"intitule": x["critere"], "ponderation": x["poids"]} for x in gn.criteres_plan(g)]
    except Exception as e:      # noqa: BLE001 — jamais bloquant : la rédaction se fait sans grille
        logger.warning("memoire.grille en échec : %s", type(e).__name__)
        return []


def _grille_consigne(criteres) -> str:
    """Bloc « grille » de la consigne : critères et poids tels qu'écrits, jamais « ? »."""
    rows = [c for c in (criteres or []) if isinstance(c, dict) and c.get("intitule")]
    if not rows:
        return ""
    items = "; ".join(c["intitule"] + (f" ({c['ponderation']})" if c.get("ponderation") else "") for c in rows)
    if all(c.get("ponderation") for c in rows):
        return (f"\n\nGRILLE DE NOTATION DE L'ACHETEUR (poids tels qu'écrits dans le règlement) : {items}"
                "\nInsiste sur les critères les plus pondérés liés à cette section.")
    return (f"\n\nCRITÈRES DE JUGEMENT DE L'ACHETEUR : {items}"
            "\nPoids non retrouvés pour tout ou partie : ne suppose aucune pondération ni aucun ordre d'importance.")


# ── 3. Rédaction d'une section (RAG + citations) ─────────────────────────────
_WRITE_SYS = """Tu rédiges une section de mémoire technique pour un appel d'offres.
RÈGLES ABSOLUES :
- Tu ne t'appuies QUE sur les SOURCES fournies (savoir-faire réel de l'entreprise).
- Tu cites tes sources avec [S1], [S2]… à la fin des phrases concernées.
- Si une partie de l'objectif n'est couverte par aucune source, tu écris une phrase
  explicite : « [À compléter : information non présente dans votre base de connaissances] ».
- Style professionnel, concret, orienté preuve. Pas d'invention, pas de superlatifs creux.
- ALIGNEMENT SUR LA GRILLE : si la grille de l'acheteur donne des poids, développe davantage
  les critères les plus pondérés. Sans poids écrit, ne suppose aucune pondération ni aucun
  ordre d'importance, et ne cite jamais un poids qui ne t'est pas donné.
Réponds en texte (pas de JSON), prêt à intégrer dans le mémoire."""


def write_section(section: dict, chunks: list, criteres=None, user_id=None) -> dict:
    if chunks:
        src = rag.sources_block(chunks)
    else:
        src = "(aucune source disponible)"
    grille = _grille_consigne(criteres)
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


# ── L'ATELIER (rédaction, vague 2) : une section à la fois, en tâche de fond ──────────
# Le moteur du savoir-faire devient le moteur de l'atelier : Sonnet, sources citées [S1]…,
# section par section. L'IA reçoit la LISTE DES FAITS AUTORISÉS (extraits du savoir-faire, profil
# de l'entreprise, équipe — noms masqués par pii_scope —, chiffrage sans prix) : tout autre fait
# sur l'entreprise doit être écrit « [À compléter : …] ». Le dossier de l'acheteur (règlement et
# cadre de réponse EN ENTIER, extraits ciblés du reste) ne sert qu'à parler du marché.
# Ces fonctions n'ouvrent AUCUNE session de base : elles tournent dans les fils d'une tâche de fond
# (app/services/atelier.py prépare tout avant, enregistre tout après).

_ATELIER_SYS = """Tu rédiges UNE partie du dossier de présentation (le « mémoire technique ») d'une
entreprise qui répond à un marché public. L'entreprise reste l'auteur : tu proposes un texte qu'elle relira.
RÈGLES ABSOLUES :
- Un fait sur l'entreprise (chiffre, effectif, nom, certification, qualification, référence, matériel,
  délai, engagement) ne peut venir QUE des FAITS AUTORISÉS (profil, équipe, chiffrage, extraits [S1], [S2]…).
  Cite [S1], [S2]… à la fin des phrases qui s'appuient sur un extrait.
- Tout autre fait sur l'entreprise s'écrit « [À compléter : ce qui manque] ». N'invente jamais.
- Le DOSSIER DE L'ACHETEUR ne sert qu'à parler du marché, de l'acheteur ou du chantier (« le CCTP prévoit… »).
  Une exigence de l'acheteur n'est JAMAIS la preuve que l'entreprise la remplit.
- Réponds exactement à la question ou au critère de cette partie, dans l'ordre demandé. Pas de superlatifs
  creux, pas de remplissage, aucun prix ni montant de l'offre.
- Si la partie porte un poids écrit dans le règlement, tu peux t'y référer ; sans poids écrit, ne suppose
  aucune importance ni aucun ordre.
- Format : paragraphes courts, listes à puces et tableaux simples en Markdown si utile. N'écris pas le titre
  de la partie (il est déjà posé) ; sous-titres « ### » seulement si nécessaire.
Réponds en texte (pas de JSON)."""

_RACCOURCIR_SYS = """Tu raccourcis une partie du dossier de présentation d'une entreprise (mémoire technique).
RÈGLES ABSOLUES :
- Garde le sens et l'ordre. N'ajoute AUCUN fait, chiffre, nom, certification, matériel ni engagement.
- Garde tels quels les passages « [À compléter …] » et les renvois [S1], [S2]…
- Respecte la longueur demandée. Markdown simple (paragraphes, listes, tableaux simples).
Réponds avec le texte raccourci seul (pas de JSON, pas de commentaire)."""


def _strip_answer(text: str, titre: str = "") -> str:
    """Retire la clôture de code et un titre qui répète celui de la partie."""
    import re as _re
    t = (text or "").strip()
    t = _re.sub(r"^\s*```[a-zA-Z]*\s*\n|\n?\s*```\s*$", "", t).strip()
    lines = t.split("\n")
    if lines and _re.match(r"^#{1,6}\s+", lines[0]):
        head = _re.sub(r"^#{1,6}\s+", "", lines[0]).strip().lower()
        if titre and (head == titre.strip().lower() or titre.strip().lower() in head):
            t = "\n".join(lines[1:]).strip()
    return t


def _consigne_partie(p: dict) -> str:
    out = [f"PARTIE À RÉDIGER : {p.get('titre') or ''}"]
    if p.get("source_plan") == "cadre" and p.get("question"):
        out.append(f"QUESTION DU CADRE DE RÉPONSE (n° {p.get('numero') or '?'}) : {p['question']}")
    if p.get("critere"):
        if p.get("poids"):
            out.append(f"CRITÈRE DE L'ACHETEUR : {p['critere']} (poids écrit dans le règlement : {p['poids']})")
        else:
            out.append(f"CRITÈRE DE L'ACHETEUR : {p['critere']} (aucun poids écrit : ne suppose aucune importance)")
        if p.get("partie_de_critere"):
            out.append("Cette partie est un découpage proposé par Adjugo, pas une rubrique imposée par l'acheteur.")
        if p.get("question") and p.get("source_plan") != "cadre":
            out.append(f"Phrase du règlement : {p['question']}")
    if p.get("cible_mots"):
        out.append(f"LONGUEUR : au plus {p['cible_mots']} mots.")
    else:
        out.append("LONGUEUR : 250 à 450 mots.")
    autres = [str(x) for x in (p.get("autres_parties") or []) if x]
    if autres:
        out.append("AUTRES PARTIES DU DOSSIER (traitées ailleurs, ne les développe pas ici) : "
                   + " ; ".join(autres[:40]))
    return "\n".join(out)


def rediger_partie(p: dict, billing_id=None) -> dict:
    """Rédige une partie. p = {titre, numero, question, critere, poids, partie_de_critere,
    source_plan, cible_mots, autres_parties, faits: {profil, equipe, chiffrage, partenaires},
    chunks: [...], dossier_acheteur}.
    Renvoie {texte, sources, coupe, extraits_fournis, erreur}. Ne lève pas : une panne de l'IA rend
    erreur=True (l'appelant décide du remboursement)."""
    from app.services.memoire_export import TRUNCATED_NOTE
    chunks = p.get("chunks") or []
    f = p.get("faits") or {}
    src = rag.sources_block(chunks) if chunks else "(aucun extrait de vos documents ne correspond)"
    partenaires = (f"\n— Apports SOUMIS par les partenaires du groupement (chacun parle de sa propre entreprise) :\n"
                   f"{f['partenaires']}") if f.get("partenaires") else ""
    user = f"""{_consigne_partie(p)}

FAITS AUTORISÉS SUR L'ENTREPRISE (seule matière permise pour parler d'elle) :
— Profil : {f.get('profil') or '(non renseigné)'}
— Équipe : {f.get('equipe') or '(non renseignée)'}
— Chiffrage (phases, tâches, jours ; aucun prix) : {f.get('chiffrage') or '(pas de chiffrage)'}{partenaires}
— Extraits de vos documents :
{src}

DOSSIER DE L'ACHETEUR (ne prouve RIEN sur l'entreprise) :
{p.get('dossier_acheteur') or '(dossier non disponible)'}

Rédige la partie. Tout fait sur l'entreprise absent des faits autorisés : « [À compléter : …] »."""
    target = int(p.get("cible_mots") or 450)
    max_tokens = max(900, min(4000, int(target * 2.6)))
    try:
        with tenant_scope(billing_id):
            content, stop = complete_ex(_ATELIER_SYS, user, max_tokens=max_tokens, temperature=0.3)
    except Exception as e:
        logger.warning("atelier.rediger en échec : %s", type(e).__name__)
        return {"texte": "", "sources": [], "coupe": False, "extraits_fournis": 0, "erreur": True}
    texte = _strip_answer(content, p.get("titre") or "")
    coupe = stop == "max_tokens"
    if coupe:
        texte = (texte.rstrip() + "\n\n" + TRUNCATED_NOTE).strip()
    if not texte.strip():
        return {"texte": "", "sources": [], "coupe": False, "extraits_fournis": 0, "erreur": True}
    cited = rag.cited_refs(texte) & set(range(1, len(chunks) + 1))
    sources = [{"ref": f"S{i + 1}", "doc_name": c.get("doc_name", ""), "chunk_id": c.get("chunk_id"),
                "extrait": (c.get("text") or "")[:240]} for i, c in enumerate(chunks) if (i + 1) in cited]
    return {"texte": texte, "sources": sources, "coupe": coupe, "extraits_fournis": len(chunks), "erreur": False}


def raccourcir_partie(texte: str, cible_mots: int, titre: str = "", billing_id=None) -> dict:
    """Raccourcit un texte vers `cible_mots` sans rien y ajouter. Renvoie {texte, coupe, erreur}."""
    from app.services.memoire_export import TRUNCATED_NOTE
    import re as _re
    n = len(_re.findall(r"\w+", texte or ""))
    user = (f"TEXTE À RACCOURCIR (environ {n} mots) :\n\"\"\"\n{texte}\n\"\"\"\n\n"
            f"CIBLE : au plus {int(cible_mots)} mots.")
    try:
        with tenant_scope(billing_id):
            content, stop = complete_ex(_RACCOURCIR_SYS, user, max_tokens=max(600, min(4000, int(cible_mots * 2.6))),
                                        temperature=0.2)
    except Exception as e:
        logger.warning("atelier.raccourcir en échec : %s", type(e).__name__)
        return {"texte": "", "coupe": False, "erreur": True}
    out = _strip_answer(content, titre)
    coupe = stop == "max_tokens"
    if coupe:
        out = (out.rstrip() + "\n\n" + TRUNCATED_NOTE).strip()
    if not out.strip():
        return {"texte": "", "coupe": False, "erreur": True}
    return {"texte": out, "coupe": coupe, "erreur": False}


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
- Si la grille de notation donne des poids, insiste sur les critères les plus pondérés ;
  sans poids écrit, ne suppose aucune pondération ni aucun ordre d'importance.
Réponds en texte (pas de JSON)."""


def _write_merged_section(section, chunks, names_by_user, criteres=None, billing_user_id=None):
    src = rag.sources_block_attributed(chunks, names_by_user) if chunks else "(aucune source)"
    grille = _grille_consigne(criteres)
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
    criteres = _criteres_controles(requirements, dce_text)
    plan = build_plan(objet, dict(requirements, criteres_attribution=criteres))[:max_sections]
    if not plan:
        plan = [{"titre": "Méthodologie et organisation du groupement",
                 "objectif": "Démontrer l'organisation conjointe", "requete": "méthodologie organisation"}]

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
