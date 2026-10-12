"""
Analyse d'un dossier LU EN ENTIER (app.services.dce_lecture).

Deux façons, choisies par le volume du dossier, sans jamais en couper une partie en silence :

  • lecture d'un seul tenant (« integral ») : si tout le dossier tient dans un budget de contexte
    SÛR pour le modèle d'analyse (calcul ci-dessous, avec une marge), l'IA reçoit le dossier
    ENTIER, règlement de la consultation et cadre de réponse en tête ;
  • lecture en deux temps (« deux_temps ») : sinon, chaque pièce est d'abord lue SÉPARÉMENT par
    l'IA (découpée en parties si elle est très longue) qui en relève les informations utiles, chacune
    avec la phrase exacte du dossier ; une phrase introuvable dans la pièce (citation_guard) fait
    écarter l'information. Puis une synthèse reçoit le règlement et le cadre en entier et ce qui a
    été relevé dans toutes les autres pièces. Chaque pièce passe donc par l'IA.

Budget de contexte (modèle d'analyse actuel, Claude Sonnet 4.6) :
  fenêtre documentée : 1 000 000 de tokens ; on s'impose un budget d'entrée SÛR, réglable,
  ANALYSE_BUDGET_TOKENS = 150 000 tokens (coût, temps de réponse sous le délai LLM_TIMEOUT, et
  fiabilité de lecture des très longs contextes), dont on retire une marge de 10 %, la consigne,
  le profil et les critères ; conversion PRUDENTE de 3,0 caractères par token (français chiffré :
  3,0 à 3,6). Soit environ 390 000 caractères de dossier lus d'un seul tenant.
  Lecture des pièces (premier temps) : Claude Haiku 4.5 (fenêtre de 200 000 tokens), parties de
  40 000 tokens au plus (≈ 120 000 caractères).

Coût mesuré par llm.cost_meter (journal) ; aucun quota ici : l'appelant débite UNE analyse par
import (et la rembourse si l'IA tombe).
"""
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from app.services import analysis as an
from app.services import dce_lecture as lec
from app.services import dce_pieces as dp
from app.services import llm

logger = logging.getLogger("adjugo")


def _env_int(name, default):
    try:
        v = int(str(os.getenv(name, "")).strip() or default)
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default


def _env_float(name, default):
    try:
        v = float(str(os.getenv(name, "")).strip() or default)
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default


# Fenêtres de contexte documentées (tokens) des modèles actuels.
FENETRES_TOKENS = {llm.MODEL: 1_000_000, llm.MODEL_FAST: 200_000}
BUDGET_TOKENS = _env_int("ANALYSE_BUDGET_TOKENS", 150_000)
CARACTERES_PAR_TOKEN = _env_float("ANALYSE_CARACTERES_PAR_TOKEN", 3.0)
MARGE = min(0.5, _env_float("ANALYSE_MARGE", 0.10))
SEGMENT_TOKENS = _env_int("ANALYSE_SEGMENT_TOKENS", 40_000)
MODELE_PIECES = os.getenv("ANALYSE_MODELE_PIECES", "").strip() or llm.MODEL_FAST
PIECES_MAX_TOKENS = _env_int("ANALYSE_PIECES_MAX_TOKENS", 4000)
MAX_APPELS = _env_int("ANALYSE_MAX_APPELS", 80)          # parties lues par l'IA dans un dossier
PARALLELE = _env_int("ANALYSE_PARALLELE", 3)
PART_REGLEMENT = 0.6                                     # part du budget de synthèse : règlement + cadre


def _tokens(chars: int) -> int:
    return int(chars / CARACTERES_PAR_TOKEN) + 1


def budget_caracteres(overhead_chars: int = 0, modele: str = None, max_sortie: int = None) -> int:
    """Caractères de dossier remis d'un seul tenant à l'IA, en sécurité : budget d'entrée borné par
    la fenêtre du modèle (sortie comprise), moins une marge, moins la consigne et le reste du
    prompt (overhead_chars), converti avec une hypothèse prudente de caractères par token."""
    modele = modele or an.ANALYSE_MODEL
    max_sortie = an.ANALYSE_MAX_TOKENS if max_sortie is None else max_sortie
    fenetre = FENETRES_TOKENS.get(modele, 200_000)
    tokens = min(BUDGET_TOKENS, fenetre - max_sortie)
    utiles = tokens * (1.0 - MARGE) - _tokens(overhead_chars)
    return max(0, int(utiles * CARACTERES_PAR_TOKEN))


def _overhead(company, criteria, lang_name, note: str) -> int:
    base = an.build_user_prompt("", company, criteria, lang_name, integral=True, note_lecture=note)
    return len(an.SYSTEM_PROMPT) + len(base) + 500


def plan(lecture: dict, company=None, criteria=None, lang_name=None) -> dict:
    """Mode de lecture par l'IA : « integral » si tout tient, sinon « deux_temps »."""
    texte, _meta = lec.texte_integral(lecture)
    note = lec.note_pour_ia(lecture)
    budget = budget_caracteres(_overhead(company, criteria, lang_name, note))
    return {"mode": "integral" if len(texte) <= budget else "deux_temps",
            "caracteres": len(texte), "budget_caracteres": budget,
            "tokens_estimes": _tokens(len(texte))}


# ── Premier temps : chaque pièce lue séparément ────────────────────────────────────────

RUBRIQUES = ("objet", "acheteur", "contact", "procedure", "lots", "budget", "date_limite", "delais",
             "lieu", "prix", "criteres", "penalites", "garanties", "avance", "sous_traitance", "variantes",
             "rse", "capacites", "qualifications", "references", "effectif", "groupement", "assurances",
             "visite", "pieces_a_fournir", "memoire", "clauses", "technique", "autre")

PIECE_SYSTEM = (
    "Tu lis UNE pièce (ou une partie d'une pièce) du dossier de consultation d'un marché public "
    "français, pour une entreprise qui va y répondre. Relève TOUTES les informations utiles pour "
    "décider d'y aller et pour répondre : objet, acheteur et contact, procédure, lots, montants, date "
    "limite, délais, lieu, forme des prix, critères de jugement et leur poids, pénalités, garanties, "
    "avance, sous-traitance, variantes, clauses sociales ou environnementales, capacités exigées "
    "(chiffre d'affaires, qualifications, références, effectif), groupement (forme imposée, "
    "mandataire, cumul des capacités), assurances, visite, pièces à fournir, contenu attendu du "
    "mémoire, clauses contractuelles sensibles, exigences techniques importantes.\n"
    "Règles :\n"
    "- Pour CHAQUE information : \"rubrique\" (une de : " + ", ".join(RUBRIQUES) + "), \"fait\" (une "
    "phrase courte et fidèle) et \"citation\" : la phrase du texte recopiée MOT POUR MOT (300 "
    "caractères au plus), sans la corriger ni la résumer. Sans citation exacte, n'inclus pas "
    "l'information : elle serait rejetée.\n"
    "- N'invente rien, ne déduis rien qui n'est pas écrit.\n"
    "- 60 informations au plus ; garde les plus importantes.\n"
    "- Rien d'utile : {\"faits\": []}.\n"
    "Réponds UNIQUEMENT en JSON : {\"faits\": [{\"rubrique\": \"...\", \"fait\": \"...\", \"citation\": \"...\"}]}"
)


def _segments(piece: dict, seg_chars: int) -> list:
    from app.services.dce_texte import _chunks
    t = piece.get("texte") or ""
    if len(t) <= seg_chars:
        return [(0, len(t))] if t.strip() else []
    return _chunks(t, target=seg_chars)


def _read_part(job: dict) -> dict:
    """Une partie d'une pièce lue par l'IA → faits dont la citation est vérifiée dans la pièce."""
    p, (a, b), i, n = job["piece"], job["span"], job["i"], job["n"]
    seg = (p.get("texte") or "")[a:b]
    head = f"Pièce : {p.get('nom') or 'pièce'} ({p.get('libelle') or ''})" + (f" — partie {i} sur {n}" if n > 1 else "")
    user = head + "\n\n<<<\n" + seg + "\n>>>"
    resp = llm.messages_create(model=MODELE_PIECES, max_tokens=PIECES_MAX_TOKENS, temperature=0,
                               system=PIECE_SYSTEM, messages=[{"role": "user", "content": user}])
    text = "".join(getattr(x, "text", "") or "" for x in (getattr(resp, "content", None) or [])
                   if getattr(x, "type", "text") == "text")
    stop = getattr(resp, "stop_reason", "") or ""
    out = {"piece_index": job["piece_index"], "i": i, "n": n, "faits": [], "ecartes": 0,
           "coupee": stop == "max_tokens", "illisible": False}
    try:
        data = llm.parse_json(text)
    except Exception:
        out["illisible"] = True
        return out
    loc = an.Localisateur(seg)
    for f in (data.get("faits") or [])[:80] if isinstance(data, dict) else []:
        if not isinstance(f, dict):
            continue
        cit = an.citation_guard(seg, f.get("citation") or "", min_len=12)
        if not cit:
            out["ecartes"] += 1
            continue
        off = loc.offset(cit)
        page = lec.page_of(p, a + off) if off is not None else None
        rub = str(f.get("rubrique") or "autre").strip().lower()[:30]
        out["faits"].append({"rubrique": rub if rub in RUBRIQUES else "autre",
                             "fait": str(f.get("fait") or "").strip()[:400], "citation": cit, "page": page})
    return out


def _bloc_faits(p: dict, parts: list) -> str:
    n = len(parts)
    faits = [f for r in parts for f in r["faits"]]
    head = (f"=== {p.get('nom') or 'pièce'} : {(p.get('libelle') or '').lower()}, lue en entier par l'IA"
            + (f" en {n} parties" if n > 1 else "") + " — informations relevées, avec la phrase exacte ===")
    if not faits:
        return head + "\n- (aucune information utile relevée dans cette pièce)"
    lignes = []
    for f in faits:
        pg = f" (p. {f['page']})" if f.get("page") else ""
        lignes.append(f"- [{f['rubrique']}] {f['fait']} — « {f['citation']} »{pg}")
    return head + "\n" + "\n".join(lignes)


def _deux_temps(lecture: dict, company, criteria, lang_name, budget: int, progress=None) -> tuple:
    """Premier temps (pièces lues une à une) + texte de la synthèse. Renvoie (texte, rapport)."""
    pieces = [p for p in lecture.get("pieces") or [] if (p.get("texte") or "").strip()]
    prio = [p for p in pieces if p.get("type") in dp.PRIORITAIRES]
    # Règlement et cadre : en entier dans la synthèse s'ils tiennent dans leur part du budget.
    room_prio = int(budget * PART_REGLEMENT)
    alloc = dp.water_fill([len(p["texte"]) for p in prio], room_prio)
    entiers = {id(p) for p, n in zip(prio, alloc) if n >= len(p["texte"])}
    a_lire = [p for p in pieces if id(p) not in entiers]
    seg_chars = max(20_000, int(SEGMENT_TOKENS * CARACTERES_PAR_TOKEN))
    index_of = {id(p): i for i, p in enumerate(pieces)}
    jobs = []
    for p in a_lire:
        spans = _segments(p, seg_chars)
        for i, sp in enumerate(spans, 1):
            jobs.append({"piece": p, "piece_index": index_of[id(p)], "span": sp, "i": i, "n": len(spans)})
    rapport = {"parties": len(jobs), "appels": 0, "non_analysees": [], "illisibles": [], "coupees": [],
               "faits": 0, "faits_ecartes": 0, "pieces_entieres": [p.get("nom") for p in prio if id(p) in entiers],
               "synthese_partielle": False}
    if len(jobs) > MAX_APPELS:
        for j in jobs[MAX_APPELS:]:
            rapport["non_analysees"].append(f"{j['piece'].get('nom')} (partie {j['i']} sur {j['n']})")
        jobs = jobs[:MAX_APPELS]
    done = [0]

    def _run(job):
        r = _read_part(job)
        done[0] += 1
        if progress is not None:
            try:
                progress({"etape": "analyse", "parties_lues": done[0], "parties_total": len(jobs),
                          "piece_en_cours": str(job["piece"].get("nom") or "")[:120]})
            except Exception:
                pass
        return r

    results = []
    if jobs:
        with ThreadPoolExecutor(max_workers=max(1, min(PARALLELE, len(jobs))),
                                thread_name_prefix="adjugo-lecture") as ex:
            results = llm.map_in_context(ex, _run, jobs)
    rapport["appels"] = len(results)
    by_piece = {}
    for r in results:
        by_piece.setdefault(r["piece_index"], []).append(r)
        rapport["faits"] += len(r["faits"])
        rapport["faits_ecartes"] += r["ecartes"]
        nom = pieces[r["piece_index"]].get("nom")
        if r["illisible"]:
            rapport["illisibles"].append(f"{nom} (partie {r['i']} sur {r['n']})")
        if r["coupee"]:
            rapport["coupees"].append(f"{nom} (partie {r['i']} sur {r['n']})")
    # Synthèse : règlement et cadre en entier, puis ce qui a été relevé pièce par pièce.
    blocs_prio = [f"=== {p.get('nom') or 'pièce'} : {(p.get('libelle') or '').lower()}, lu en entier ===\n"
                  + p["texte"] for p in prio if id(p) in entiers]
    blocs = []
    for pi, p in enumerate(pieces):
        if id(p) in entiers:
            continue
        parts = sorted(by_piece.get(pi, []), key=lambda r: r["i"])
        blocs.append(_bloc_faits(p, parts) if parts else
                     f"=== {p.get('nom')} : {(p.get('libelle') or '').lower()} — non analysée (plafond technique) ===")
    used = sum(len(b) + 2 for b in blocs_prio)
    room = max(0, budget - used - 400)
    if sum(len(b) + 2 for b in blocs) > room:
        rapport["synthese_partielle"] = True
        cuts = dp.water_fill([len(b) for b in blocs], room)
        blocs = [b[:c].rsplit("\n", 1)[0] + "\n- (suite des informations relevées : non reprise, place insuffisante)"
                 if c < len(b) else b for b, c in zip(blocs, cuts)]
    intro = ("[Dossier volumineux lu en deux temps : le règlement de la consultation et le cadre de réponse "
             "sont remis en entier ; chaque autre pièce a été lue en entier par l'IA, pièce par pièce, et voici "
             "ce qui y a été relevé, chaque information avec la phrase exacte du dossier entre « ».]")
    return "\n\n".join([intro] + blocs_prio + blocs), rapport


# ── Point d'entrée ─────────────────────────────────────────────────────────────────────

def analyser(lecture: dict, company=None, criteria=None, lang_name=None, progress=None) -> dict:
    """Analyse complète d'un dossier lu en entier. Renvoie l'analyse (format d'analyze_dce_text)
    complétée de : lecture (pièces lues, sans le texte), couverture (« dossier lu en entier : N
    pièces, P pages » ou les pièces non lues et pourquoi), mode_lecture, dce_excerpt.
    Propage toute panne de l'IA (l'appelant rembourse le quota)."""
    texte, _meta = lec.texte_integral(lecture)
    mani = lec.manifeste(lecture)
    pieces_meta = mani["pieces"]
    note = lec.note_pour_ia(lecture)
    pl = plan(lecture, company, criteria, lang_name)
    tenant = llm._CURRENT_TENANT.get()
    t = mani["totaux"]
    label = f"analyse du dossier ({pl['mode']}, {t['pieces']} pièces, {pl['caracteres']} caractères)"
    rapport = None
    with llm.cost_meter(label, tenant):
        if pl["mode"] == "integral":
            analysis = an.analyze_dce_text(texte, company, criteria, lang_name=lang_name, pieces=pieces_meta,
                                           integral=True, note_lecture=note, text_integral=texte)
        else:
            synthese, rapport = _deux_temps(lecture, company, criteria, lang_name, pl["budget_caracteres"],
                                            progress=progress)
            if progress is not None:
                try:
                    progress({"etape": "synthese"})
                except Exception:
                    pass
            analysis = an.analyze_dce_text(synthese, company, criteria, lang_name=lang_name, pieces=pieces_meta,
                                           integral=True, note_lecture=note, text_integral=texte)
    cov = lec.couverture(lecture)
    cov["mode"] = pl["mode"]
    if rapport is not None:
        manques = rapport["non_analysees"] + rapport["illisibles"]
        cov["analyse"] = {"parties_lues_par_l_ia": rapport["appels"], "faits_releves": rapport["faits"],
                          "faits_ecartes": rapport["faits_ecartes"], "non_analysees": manques[:50],
                          "coupees": rapport["coupees"][:50], "synthese_partielle": rapport["synthese_partielle"]}
        if manques or rapport["synthese_partielle"]:
            cov["complet"] = False
            cov["message"] += (" Certaines parties n'ont pas pu être exploitées par l'IA (voir la liste)."
                               if manques else " Toutes les informations relevées n'ont pas tenu dans la synthèse.")
    analysis["lecture"] = mani
    analysis["couverture"] = cov
    analysis["mode_lecture"] = pl["mode"]
    analysis["dce_excerpt"] = texte[:30000]     # compatibilité : nom du mémoire, anciens usages
    return analysis
