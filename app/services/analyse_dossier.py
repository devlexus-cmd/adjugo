"""
Analyse d'un dossier LU EN ENTIER (app.services.dce_lecture).

Deux façons, choisies par le volume du dossier, sans jamais en couper une partie en silence :

  • lecture d'un seul tenant (« integral ») : si tout le dossier tient dans un budget de contexte
    SÛR pour le modèle d'analyse (calcul ci-dessous, avec une marge), l'IA reçoit le dossier
    ENTIER, règlement de la consultation et cadre de réponse en tête ;
  • lecture en deux temps (« deux_temps ») : sinon, chaque pièce est d'abord lue SÉPARÉMENT par
    l'IA (découpée en parties si elle est très longue ; les petites pièces voisines regroupées dans
    un même appel, chacune sous son nom) qui en relève les informations utiles, chacune avec la
    phrase exacte du dossier ; une phrase introuvable dans la pièce (citation_guard) fait écarter
    l'information. Puis une synthèse reçoit le règlement et le cadre en entier et ce qui a été
    relevé dans toutes les autres pièces. Chaque pièce passe donc par l'IA.
    Robustesse : une partie dont la réponse est coupée est relue en deux moitiés (les informations
    complètes de la réponse coupée sont gardées sinon) ; une réponse illisible ou une panne de l'IA
    est relancée une fois ; une partie qui échoue encore est NOMMÉE (« non exploitée par l'IA »)
    dans la synthèse et la couverture, et l'analyse n'échoue (et n'est remboursée) que si plus de
    la moitié des parties échoue. Les informations relevées sont rangées avec la lecture
    (on_parties) : une nouvelle analyse du même dossier ne relit que les parties manquantes.
    Lectures du dossier limitées à ANALYSE_PLACES_IA appels simultanés pour TOUT le serveur
    (premier arrivé, premier servi) : les questions et analyses des autres clients gardent leurs
    places.

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
# Sortie d'une partie : 40 informations au plus (≈ 130 tokens chacune avec sa citation de 300
# caractères, soit ≈ 5 200 tokens) sous un plafond de 8 000 tokens (payé à l'usage, pas au plafond).
PIECES_MAX_TOKENS = _env_int("ANALYSE_PIECES_MAX_TOKENS", 8000)
FAITS_MAX = 40
MAX_APPELS = _env_int("ANALYSE_MAX_APPELS", 80)          # appels de lecture par l'IA dans un dossier
PARALLELE = _env_int("ANALYSE_PARALLELE", 3)
GROUPE_MAX_PIECES = _env_int("ANALYSE_GROUPE_MAX_PIECES", 12)   # petites pièces lues dans un même appel
RELANCES_MAX = _env_int("ANALYSE_RELANCES_MAX", 12)     # appels coupés en deux moitiés (dossier entier)
PROFONDEUR_MAX = 3                                       # une partie coupée au plus en 8
ECHEC_MAX = 0.5                                          # part des parties en échec qui fait échouer l'analyse
PLACES_IA = _env_int("ANALYSE_PLACES_IA", max(1, llm._MAX_CONCURRENT // 2))
ATTENTE_PLACE_S = _env_float("ANALYSE_ATTENTE_PLACE_S", 3600.0)
PAUSE_RELANCE_S = _env_float("ANALYSE_PAUSE_RELANCE_S", 2.0)
VERSION_LECTURE = "2"                                    # consigne de lecture : change → relecture
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
    "Tu lis UNE pièce (ou une partie d'une pièce), ou plusieurs courtes pièces, du dossier de "
    "consultation d'un marché public français, pour une entreprise qui va y répondre. Relève TOUTES "
    "les informations utiles pour décider d'y aller et pour répondre : objet, acheteur et contact, "
    "procédure, lots, montants, date limite, délais, lieu, forme des prix, critères de jugement et "
    "leur poids, pénalités, garanties, avance, sous-traitance, variantes, clauses sociales ou "
    "environnementales, capacités exigées (chiffre d'affaires, qualifications, références, effectif), "
    "groupement (forme imposée, mandataire, cumul des capacités), assurances, visite, pièces à "
    "fournir, contenu attendu du mémoire, clauses contractuelles sensibles, exigences techniques "
    "importantes.\n"
    "Règles :\n"
    "- Pour CHAQUE information : \"piece\" (le nom de la pièce tel qu'écrit après « Pièce : »), "
    "\"rubrique\" (une de : " + ", ".join(RUBRIQUES) + "), \"fait\" (une phrase courte et fidèle) et "
    "\"citation\" : la phrase du texte recopiée MOT POUR MOT (300 caractères au plus), sans la corriger "
    "ni la résumer. Sans citation exacte, n'inclus pas l'information : elle serait rejetée.\n"
    "- N'invente rien, ne déduis rien qui n'est pas écrit.\n"
    "- " + str(FAITS_MAX) + " informations au plus ; garde les plus importantes, et au moins une par "
    "pièce lue si elle contient quelque chose d'utile.\n"
    "- Rien d'utile : {\"faits\": []}.\n"
    "Réponds UNIQUEMENT en JSON : {\"faits\": [{\"piece\": \"...\", \"rubrique\": \"...\", "
    "\"fait\": \"...\", \"citation\": \"...\"}]}"
)


class _FairSlots:
    """Places de lecture par l'IA pour TOUT le serveur, attribuées dans l'ordre d'arrivée (une
    place rendue passe directement au premier qui attend : un fil qui enchaîne les parties ne peut
    pas la reprendre avant lui)."""

    def __init__(self, n: int):
        import collections
        import threading
        self.n = max(1, int(n))
        self.lock = threading.Lock()
        self.q = collections.deque()

    def acquire(self, timeout: float) -> bool:
        import threading
        with self.lock:
            if self.n > 0 and not self.q:
                self.n -= 1
                return True
            ev = threading.Event()
            self.q.append(ev)
        if ev.wait(timeout):
            return True
        with self.lock:
            if ev.is_set():
                return True
            try:
                self.q.remove(ev)
            except ValueError:
                pass
            return False

    def release(self) -> None:
        with self.lock:
            if self.q:
                self.q.popleft().set()
            else:
                self.n += 1


_PLACES = _FairSlots(PLACES_IA)
_RELANCES_LOCK = __import__("threading").Lock()


def _segments(piece: dict, seg_chars: int) -> list:
    from app.services.dce_texte import _chunks
    t = piece.get("texte") or ""
    if len(t) <= seg_chars:
        return [(0, len(t))] if t.strip() else []
    return _chunks(t, target=seg_chars)


def _cle(seg: dict) -> str:
    """Clé d'une partie lue (relecture inutile si la même partie a déjà été lue, avec la même
    consigne et le même modèle)."""
    import hashlib
    p, (a, b) = seg["piece"], seg["span"]
    h = hashlib.sha256()
    h.update(f"{VERSION_LECTURE}|{MODELE_PIECES}|{p.get('nom')}|{seg['i']}/{seg['n']}|".encode("utf-8"))
    h.update((p.get("texte") or "")[a:b].encode("utf-8", "surrogatepass"))
    return h.hexdigest()[:32]


def _groupes(segs: list, seg_chars: int) -> list:
    """Regroupe les petites parties voisines dans un même appel (jusqu'à seg_chars caractères et
    GROUPE_MAX_PIECES pièces) : un dossier de 90 plans d'une page ne coûte plus 90 appels."""
    out, cur, size = [], [], 0
    for sg in segs:
        n = sg["span"][1] - sg["span"][0] + 200
        if cur and (size + n > seg_chars or len(cur) >= GROUPE_MAX_PIECES):
            out.append(cur)
            cur, size = [], 0
        cur.append(sg)
        size += n
    if cur:
        out.append(cur)
    return out


def _texte_seg(seg: dict) -> str:
    a, b = seg["span"]
    return (seg["piece"].get("texte") or "")[a:b]


def _tete_seg(seg: dict) -> str:
    p = seg["piece"]
    return (f"Pièce : {p.get('nom') or 'pièce'} ({p.get('libelle') or ''})"
            + (f" — partie {seg['i']} sur {seg['n']}" if seg["n"] > 1 else ""))


def _faits_complets(text: str) -> list:
    """Informations COMPLÈTES d'une réponse coupée en cours de route (plafond de sortie) : les
    objets du tableau « faits » décodés un à un jusqu'au dernier objet fermé."""
    import json
    i = text.find('"faits"')
    i = text.find("[", i) if i >= 0 else -1
    if i < 0:
        return []
    dec, out, pos = json.JSONDecoder(), [], i + 1
    while True:
        while pos < len(text) and text[pos] in " \t\r\n,":
            pos += 1
        if pos >= len(text) or text[pos] != "{":
            break
        try:
            obj, pos = dec.raw_decode(text, pos)
        except ValueError:
            break
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _appel(groupe: list):
    """Un appel de lecture : (texte de la réponse, coupée ?). Une place de lecture est tenue pendant
    l'appel ; une panne est relancée une fois (après une courte pause)."""
    import time
    user = "\n\n".join(_tete_seg(sg) + "\n\n<<<\n" + _texte_seg(sg) + "\n>>>" for sg in groupe)
    last = None
    for essai in range(2):
        if essai:
            time.sleep(PAUSE_RELANCE_S)          # place rendue pendant la pause
        if not _PLACES.acquire(ATTENTE_PLACE_S):
            raise llm.LLMUnavailable("Lecture du dossier : aucune place libre pour l'IA.")
        try:
            resp = llm.messages_create(model=MODELE_PIECES, max_tokens=PIECES_MAX_TOKENS, temperature=0,
                                       system=PIECE_SYSTEM, messages=[{"role": "user", "content": user}])
            text = "".join(getattr(x, "text", "") or "" for x in (getattr(resp, "content", None) or [])
                           if getattr(x, "type", "text") == "text")
            return text, (getattr(resp, "stop_reason", "") or "") == "max_tokens"
        except Exception as e:      # noqa: BLE001 — relancé une fois, puis nommé « non exploitée »
            last = e
        finally:
            _PLACES.release()
    raise last


def _verifier(groupe: list, faits: list, res: dict) -> None:
    """Range dans res[clé de la partie] les informations dont la citation est retrouvée MOT POUR
    MOT dans la partie (celle que l'IA nomme d'abord, sinon les autres de l'appel)."""
    from app.services import dce_pieces as _dp
    locs = {}
    for f in faits[:FAITS_MAX * 2]:
        if not isinstance(f, dict):
            continue
        nom = _dp.fold(str(f.get("piece") or "")).strip()
        ordre = sorted(groupe, key=lambda sg: 0 if nom and _dp.fold(sg["piece"].get("nom") or "") == nom else 1)
        cit, cible = "", None
        for sg in ordre:
            cit = an.citation_guard(_texte_seg(sg), f.get("citation") or "", min_len=12)
            if cit:
                cible = sg
                break
        if not cible:
            res[groupe[0]["cle"]]["ecartes"] += 1
            continue
        a = cible["span"][0]
        loc = locs.setdefault(cible["cle"], an.Localisateur(_texte_seg(cible)))
        off = loc.offset(cit)
        page = lec.page_of(cible["piece"], a + off) if off is not None else None
        rub = str(f.get("rubrique") or "autre").strip().lower()[:30]
        res[cible["cle"]]["faits"].append({"rubrique": rub if rub in RUBRIQUES else "autre",
                                           "fait": str(f.get("fait") or "").strip()[:400],
                                           "citation": cit, "page": page})


def _moities(groupe: list) -> list:
    """Coupe un appel en deux : deux groupes de parties, ou une partie longue en deux moitiés
    (sous-parties qui gardent la clé de leur partie). [] si on ne peut pas couper."""
    if len(groupe) > 1:
        k = len(groupe) // 2
        return [groupe[:k], groupe[k:]]
    sg = groupe[0]
    a, b = sg["span"]
    if b - a < 8000:
        return []
    from app.services.dce_texte import _chunks
    t = (sg["piece"].get("texte") or "")[a:b]
    cuts = _chunks(t, target=(b - a) // 2 + 1)
    if len(cuts) < 2:
        return []
    halves = [cuts[0], (cuts[1][0], cuts[-1][1])]
    return [[dict(sg, span=(a + x, a + y))] for x, y in halves]


def _lire_groupe(groupe: list, budget_relances: list, profondeur: int = 0) -> dict:
    """Lit un groupe de parties ; renvoie {clé de partie: résultat}. Ne lève jamais : une panne
    persistante est notée dans le résultat (« erreur »)."""
    res = {sg["cle"]: {"faits": [], "ecartes": 0, "coupee": False, "illisible": False, "erreur": False}
           for sg in groupe}

    def _par_moities(moit):
        for m in moit:
            sous = _lire_groupe(m, budget_relances, profondeur + 1)
            for k, r in sous.items():
                base = res[k]
                base["faits"].extend(r["faits"])
                base["ecartes"] += r["ecartes"]
                for flag in ("coupee", "illisible", "erreur"):
                    base[flag] = base[flag] or r[flag]
        return res

    def _relance_possible(moit) -> bool:
        with _RELANCES_LOCK:
            if moit and profondeur < PROFONDEUR_MAX and budget_relances[0] > 0:
                budget_relances[0] -= 1
                return True
        return False

    try:
        text, coupee = _appel(groupe)
    except Exception as e:      # noqa: BLE001
        logger.info("lecture d'une partie du dossier en échec : %s", type(e).__name__)
        # Plusieurs pièces dans l'appel : chacune de ses moitiés est retentée (une pièce en cause
        # n'emporte pas ses voisines) ; sinon la partie est nommée « non exploitée ».
        moit = _moities(groupe) if len(groupe) > 1 else []
        if not isinstance(e, llm.LLMUnavailable) and _relance_possible(moit):
            return _par_moities(moit)
        for r in res.values():
            r["erreur"] = True
        return res
    data = None
    if not coupee:
        try:
            data = llm.parse_json(text)
        except Exception:
            # Réponse illisible : relancée une fois.
            try:
                text, coupee = _appel(groupe)
                data = None if coupee else llm.parse_json(text)
            except Exception:
                data = None
            if data is None and not coupee:
                for r in res.values():
                    r["illisible"] = True
                return res
    if coupee:
        # Réponse coupée par le plafond de sortie : relue en deux moitiés (une fois), sinon les
        # informations complètes sont gardées et la partie est dite « exploitée en partie ».
        moit = _moities(groupe)
        if _relance_possible(moit):
            return _par_moities(moit)
        _verifier(groupe, _faits_complets(text), res)
        for r in res.values():
            r["coupee"] = True
        return res
    faits = (data.get("faits") or []) if isinstance(data, dict) else []
    _verifier(groupe, faits, res)
    return res


def _etat_ia(parts: list, n: int) -> tuple:
    """(lue en entier par l'IA ?, texte « lue en partie par l'IA (…) ») d'après ses parties."""
    ok = [r for r in parts if not (r["illisible"] or r["erreur"] or r["coupee"])]
    coupees = [r for r in parts if r["coupee"] and not (r["illisible"] or r["erreur"])]
    if len(parts) == n and len(ok) == n:
        return True, ""
    if not ok and not coupees:
        causes = []
        if any(r["erreur"] for r in parts):
            causes.append("IA indisponible")
        if any(r["illisible"] for r in parts):
            causes.append("réponse de l'IA illisible")
        if len(parts) < n:
            causes.append("plafond technique")
        return False, "non exploitée par l'IA (" + ", ".join(causes or ["raison inconnue"]) + ")"
    bits = [f"{len(ok)} partie{'s' if len(ok) > 1 else ''} exploitée{'s' if len(ok) > 1 else ''} sur {n}"]
    if coupees:
        bits.append(f"{len(coupees)} exploitée{'s' if len(coupees) > 1 else ''} en partie (réponse trop longue)")
    rest = n - len(ok) - len(coupees)
    if rest:
        bits.append(f"{rest} non exploitée{'s' if rest > 1 else ''}")
    return False, "lue en partie par l'IA (" + ", ".join(bits) + ")"


def _lecture_note(p: dict) -> str:
    """Nuance de LECTURE du texte (avant l'IA) : pièce lue en partie (pages abîmées, scan…)."""
    if p.get("statut") == lec.LU:
        return ""
    return " ; texte de la pièce lu en partie (" + (p.get("detail") or lec.raison_texte(p.get("raison"))) + ")"


def _bloc_faits(p: dict, parts: list, n: int) -> str:
    entier, nuance = _etat_ia(parts, n)
    if entier:
        lu = "lue en entier par l'IA" + (f" en {n} parties" if n > 1 else "")
    else:
        lu = nuance
    lu += _lecture_note(p)
    faits = [f for r in parts for f in r["faits"]]
    head = (f"=== {p.get('nom') or 'pièce'} : {(p.get('libelle') or '').lower()}, {lu}"
            " — informations relevées, avec la phrase exacte ===")
    if not faits:
        if entier:
            return head + "\n- (aucune information utile relevée dans cette pièce)"
        return head + "\n- (aucune information exploitable : n'en conclus rien sur le contenu de cette pièce)"
    lignes = []
    for f in faits:
        pg = f" (p. {f['page']})" if f.get("page") else ""
        lignes.append(f"- [{f['rubrique']}] {f['fait']} — « {f['citation']} »{pg}")
    return head + "\n" + "\n".join(lignes)


def _deux_temps(lecture: dict, company, criteria, lang_name, budget: int, progress=None,
                on_parties=None) -> tuple:
    """Premier temps (pièces lues une à une, petites pièces regroupées) + texte de la synthèse.
    Renvoie (texte, rapport). Lève LLMUnavailable si plus de la moitié des parties échoue."""
    pieces = [p for p in lecture.get("pieces") or [] if (p.get("texte") or "").strip()]
    prio = [p for p in pieces if p.get("type") in dp.PRIORITAIRES]
    # Règlement et cadre : en entier dans la synthèse s'ils tiennent dans leur part du budget.
    room_prio = int(budget * PART_REGLEMENT)
    alloc = dp.water_fill([len(p["texte"]) for p in prio], room_prio)
    entiers = {id(p) for p, n in zip(prio, alloc) if n >= len(p["texte"])}
    a_lire = [p for p in pieces if id(p) not in entiers]
    seg_chars = max(20_000, int(SEGMENT_TOKENS * CARACTERES_PAR_TOKEN))
    index_of = {id(p): i for i, p in enumerate(pieces)}
    segs = []
    for p in a_lire:
        spans = _segments(p, seg_chars)
        for i, sp in enumerate(spans, 1):
            sg = {"piece": p, "piece_index": index_of[id(p)], "span": sp, "i": i, "n": len(spans)}
            sg["cle"] = _cle(sg)
            segs.append(sg)
    cache = lecture.get("analyse_parties") if isinstance(lecture.get("analyse_parties"), dict) else {}
    results = {}
    for sg in segs:
        hit = cache.get(sg["cle"])
        if isinstance(hit, dict) and isinstance(hit.get("faits"), list):
            results[sg["cle"]] = {"faits": hit["faits"], "ecartes": int(hit.get("ecartes") or 0),
                                  "coupee": False, "illisible": False, "erreur": False}
    a_appeler = [sg for sg in segs if sg["cle"] not in results]
    groupes = _groupes(a_appeler, seg_chars)
    rapport = {"parties": len(segs), "appels": 0, "reprises": len(segs) - len(a_appeler), "non_analysees": [],
               "illisibles": [], "erreurs": [], "coupees": [], "faits": 0, "faits_ecartes": 0,
               "pieces_entieres": [p.get("nom") for p in prio if id(p) in entiers], "synthese_partielle": False}
    plafond = set()
    if len(groupes) > MAX_APPELS:
        for g in groupes[MAX_APPELS:]:
            for sg in g:
                plafond.add(sg["cle"])
        groupes = groupes[:MAX_APPELS]
    done = [0]
    budget_relances = [RELANCES_MAX]

    def _run(groupe):
        r = _lire_groupe(groupe, budget_relances)
        done[0] += 1
        if progress is not None:
            try:
                progress({"etape": "analyse", "parties_lues": done[0], "parties_total": len(groupes),
                          "piece_en_cours": str(groupe[-1]["piece"].get("nom") or "")[:120]})
            except Exception:
                pass
        return r

    if groupes:
        with ThreadPoolExecutor(max_workers=max(1, min(PARALLELE, len(groupes))),
                                thread_name_prefix="adjugo-lecture") as ex:
            for r in llm.map_in_context(ex, _run, groupes):
                results.update(r)
    rapport["appels"] = len(groupes)
    rapport["relances"] = RELANCES_MAX - budget_relances[0]
    # Ce qui vient d'être lu (exploitable) est rangé avec la lecture : une nouvelle analyse du même
    # dossier ne relira que ce qui manque.
    neufs = {k: {"faits": r["faits"], "ecartes": r["ecartes"]} for k, r in results.items()
             if k not in cache and not (r["coupee"] or r["illisible"] or r["erreur"])}
    if neufs and on_parties is not None:
        try:
            on_parties(neufs)
        except Exception as e:      # noqa: BLE001 — jamais bloquant
            logger.warning("informations relevées non rangées : %s", type(e).__name__)
    echecs = [sg for sg in segs if sg["cle"] in results and (results[sg["cle"]]["erreur"] or results[sg["cle"]]["illisible"])]
    tentes = [sg for sg in segs if sg["cle"] in results]
    if tentes and len(echecs) > ECHEC_MAX * len(tentes):
        raise llm.LLMUnavailable("La lecture du dossier par l'IA a échoué pour trop de parties.")
    by_piece = {}
    for sg in segs:
        nom = f"{sg['piece'].get('nom')} (partie {sg['i']} sur {sg['n']})"
        if sg["cle"] in plafond:
            rapport["non_analysees"].append(nom + " : plafond technique")
            continue
        r = results.get(sg["cle"])
        if r is None:
            continue
        by_piece.setdefault(sg["piece_index"], []).append(r)
        rapport["faits"] += len(r["faits"])
        rapport["faits_ecartes"] += r["ecartes"]
        if r["erreur"]:
            rapport["erreurs"].append(nom + " : IA indisponible")
        elif r["illisible"]:
            rapport["illisibles"].append(nom + " : réponse de l'IA illisible")
        elif r["coupee"]:
            rapport["coupees"].append(nom + " : réponse de l'IA trop longue, exploitée en partie")
    # Synthèse : règlement et cadre en entier, puis ce qui a été relevé pièce par pièce.
    blocs_prio = []
    for p in prio:
        if id(p) not in entiers:
            continue
        etat = "lu en entier" if p.get("statut") == lec.LU else ("texte lu en partie ("
                                                                 + (p.get("detail") or lec.raison_texte(p.get("raison"))) + ")")
        blocs_prio.append(f"=== {p.get('nom') or 'pièce'} : {(p.get('libelle') or '').lower()}, remis tel quel, "
                          f"{etat} ===\n" + p["texte"])
    n_of = {}
    for sg in segs:
        n_of[sg["piece_index"]] = sg["n"]
    blocs, manques_ia = [], False
    for pi, p in enumerate(pieces):
        if id(p) in entiers:
            continue
        parts = by_piece.get(pi, [])
        n = n_of.get(pi, 0)
        if not parts:
            manques_ia = True
            blocs.append(f"=== {p.get('nom')} : {(p.get('libelle') or '').lower()} — non analysée par l'IA "
                         "(plafond technique) : n'en conclus rien ===")
            continue
        if not _etat_ia(parts, n)[0]:
            manques_ia = True
        blocs.append(_bloc_faits(p, parts, n))
    used = sum(len(b) + 2 for b in blocs_prio)
    room = max(0, budget - used - 1200)
    if sum(len(b) + 2 for b in blocs) > room:
        rapport["synthese_partielle"] = True
        cuts = dp.water_fill([len(b) for b in blocs], room)
        blocs = [b[:c].rsplit("\n", 1)[0] + "\n- (suite des informations relevées : non reprise, place insuffisante)"
                 if c < len(b) else b for b, c in zip(blocs, cuts)]
    if not manques_ia and not rapport["synthese_partielle"]:
        intro = ("[Dossier volumineux lu en deux temps : le règlement de la consultation et le cadre de réponse "
                 "sont remis en entier ; chaque autre pièce a été lue en entier par l'IA, pièce par pièce, et voici "
                 "ce qui y a été relevé, chaque information avec la phrase exacte du dossier entre « ».]")
    else:
        manquants = rapport["non_analysees"] + rapport["erreurs"] + rapport["illisibles"] + rapport["coupees"]
        intro = ("[Dossier volumineux lu en deux temps : le règlement de la consultation et le cadre de réponse "
                 "sont remis en entier ; les autres pièces ont été lues par l'IA, pièce par pièce, et voici ce qui y "
                 "a été relevé, chaque information avec la phrase exacte du dossier entre « ». ATTENTION : certaines "
                 "parties n'ont pas pu être exploitées entièrement (voir l'en-tête de chaque pièce"
                 + ("" if not manquants else " et la liste : " + " ; ".join(manquants[:30]))
                 + "). Pour ce qui n'y figure pas, écris que l'information n'a pas été trouvée dans ce qui a été lu "
                 "— jamais qu'elle n'existe pas.]")
    return "\n\n".join([intro] + blocs_prio + blocs), rapport


# ── Point d'entrée ─────────────────────────────────────────────────────────────────────

def analyser(lecture: dict, company=None, criteria=None, lang_name=None, progress=None,
             on_parties=None) -> dict:
    """Analyse complète d'un dossier lu en entier. Renvoie l'analyse (format d'analyze_dce_text)
    complétée de : lecture (pièces lues, sans le texte), couverture (« dossier lu en entier : N
    pièces, P pages » ou les pièces non lues et pourquoi), mode_lecture, dce_excerpt.
    on_parties(dict) : range les informations relevées pièce par pièce (lecture en deux temps).
    Propage toute panne de l'IA (l'appelant rembourse le quota) ; en deux temps, une partie en
    échec est nommée dans la couverture sans faire échouer l'analyse (sauf échec massif)."""
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
                                            progress=progress, on_parties=on_parties)
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
        manques = rapport["non_analysees"] + rapport["erreurs"] + rapport["illisibles"]
        cov["analyse"] = {"parties": rapport["parties"], "appels_ia": rapport["appels"],
                          "parties_relues_en_deux": rapport.get("relances", 0),
                          "parties_reprises": rapport["reprises"], "faits_releves": rapport["faits"],
                          "faits_ecartes": rapport["faits_ecartes"], "non_analysees": manques[:100],
                          "coupees": rapport["coupees"][:100], "synthese_partielle": rapport["synthese_partielle"]}
        if manques or rapport["coupees"] or rapport["synthese_partielle"]:
            cov["complet"] = False
            if manques or rapport["coupees"]:
                cov["message"] += " Certaines parties n'ont pas pu être exploitées entièrement par l'IA (voir la liste)."
            else:
                cov["message"] += " Toutes les informations relevées n'ont pas tenu dans la synthèse."
    analysis["lecture"] = mani
    analysis["couverture"] = cov
    analysis["mode_lecture"] = pl["mode"]
    analysis["dce_excerpt"] = texte[:30000]     # compatibilité : nom du mémoire, anciens usages
    return analysis
