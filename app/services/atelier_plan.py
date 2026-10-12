"""
Le plan du dossier de présentation (rédaction, vague 2 — l'atelier, étude §6.4), SANS IA.

Doctrine (étude §7, règle 4) : le cadre de l'acheteur commande.
  • cadre de réponse IMPOSÉ (grille.contraintes.fichier_impose) : une section par question du
    cadre, dans SON ordre, avec SES numéros et SES intitulés (repérés dans le texte, sans IA) ;
  • sinon, la grille « Comment vous serez noté » confirmée : une section par critère du plan
    (lignes retrouvées dans le règlement ou confirmées par l'utilisateur), poids TEL QU'ÉCRIT ;
    le critère du prix n'appelle pas de texte (il est jugé sur le bordereau de prix) ;
  • sinon, un plan simple en parties libres, proposé par Adjugo et dit comme tel.
Jamais de critère, de poids ni d'ordre d'importance inventés. Les limites (pages, mots…)
repérées en vague 1 sont rattachées à la section qu'elles visent, ou au document entier.
"""
import re
from typing import Optional

from app.services import dce_pieces as dp
from app.services import grille_notation as gn

GRILLE = "grille"
CADRE = "cadre"
LIBRE = "libre"
UTILISATEUR = "utilisateur"
BASES = ("auto", GRILLE, CADRE, LIBRE)

MAX_SECTIONS = 40
QUESTION_MAX = 2000
INTITULE_MAX = 200

PARTIES_LIBRES = (
    "Présentation de l'entreprise",
    "Compréhension du besoin",
    "Moyens humains",
    "Moyens matériels",
    "Méthodologie et organisation du chantier",
    "Qualité, sécurité et environnement",
    "Planning et délais",
)
PRESENTATION_GROUPEMENT = "Présentation du groupement"

MSG_CADRE_IMPOSE = ("Plan construit sur le cadre de réponse imposé par l'acheteur : mêmes numéros, mêmes "
                    "intitulés, même ordre.")
MSG_CADRE_FOURNI = "Plan construit sur le cadre de réponse fourni par l'acheteur : mêmes numéros, mêmes intitulés."
MSG_CADRE_NON_DECOUPE = ("Ce marché impose son propre fichier de réponse, mais Adjugo n'y a pas repéré les "
                         "questions une à une : suivez l'ordre du fichier de l'acheteur.")
MSG_GRILLE = ("Plan construit sur les critères de « Comment vous serez noté », avec leur poids tel qu'il est écrit "
              "ou tel que vous l'avez lu.")
MSG_GRILLE_UN_CRITERE = ("Le règlement ne donne qu'un critère à traiter dans ce dossier (« {c} »). Adjugo propose "
                         "de le découper en parties : ce découpage n'est pas imposé par l'acheteur.")
MSG_GRILLE_UN_CONFIRME = ("Un seul critère est retenu pour l'instant (« {c} ») : Adjugo propose de le découper en "
                          "parties. Ce découpage n'est pas imposé par l'acheteur.")
MSG_LIBRE = ("Aucun critère n'a été retrouvé dans le règlement : Adjugo propose un plan simple, sans IA. "
             "Adaptez-le au marché.")
MSG_LIBRE_EN_ATTENTE = ("Aucun critère n'est encore retenu : Adjugo propose un plan simple, sans IA, à adapter au "
                        "marché.")
MSG_LIBRE_CHOISI = "Plan simple choisi par vous, sans IA : adaptez-le au marché."
MSG_SANS_DOSSIER = ("Adjugo n'a pas encore le dossier du marché : importez-le pour que le plan suive les critères et "
                    "le cadre de l'acheteur. En attendant, Adjugo propose un plan simple, sans IA.")
MSG_PAS_DE_CADRE = "Aucun cadre de réponse découpé en questions n'a été repéré dans le dossier."
MSG_PAS_DE_CRITERE = "Aucun critère n'est retenu dans « Comment vous serez noté »."
MSG_A_VERIFIER = ("{n} critère{s} reste{nt} à vérifier dans « Comment vous serez noté » : confirmez-{le} pour qu'{il} "
                  "entre{nt} dans le plan.")
MSG_PRIX = "Jugé sur votre offre de prix (bordereau), pas dans le dossier de présentation."

# Fichier de réponse imposé (décision 11) : UNE phrase par cas, jamais deux consignes accolées.
AVERT_FICHIER_CADRE = ("Ce marché impose son propre fichier de réponse. Le fichier Word d'Adjugo suit l'ordre, les "
                       "numéros et les intitulés de ce cadre : recopiez-en le texte dans le fichier de l'acheteur.")
AVERT_FICHIER_AUTRE = ("Ce marché impose son propre fichier de réponse : recopiez votre texte dans le fichier de "
                       "l'acheteur, ne déposez pas le fichier Word d'Adjugo seul.")


def avertissement_fichier(impose: bool, source: str) -> str:
    if not impose:
        return ""
    return AVERT_FICHIER_CADRE if source == CADRE else AVERT_FICHIER_AUTRE


def msg_a_verifier(n: int) -> str:
    if not n:
        return ""
    un = n == 1
    return MSG_A_VERIFIER.format(n=n, s="" if un else "s", nt="" if un else "nt", le="le" if un else "les",
                                 il="il" if un else "ils")

# Critère jugé sur le prix : pas de texte à rédiger pour lui.
_PRIX = re.compile(r"\bprix\b|\bmontant|\bcouts?\b|\btarif|financ|\beconomique|\bprix global")


def _flat(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def est_critere_prix(name: str) -> bool:
    low = dp.fold(_flat(name))
    if re.search(r"technique|methodolog|qualite|delai|environnement|social", low):
        return False
    return bool(_PRIX.search(low))


# ── Les questions d'un cadre de réponse ─────────────────────────────────────────────

_NUM = r"\d{1,2}(?:[.\-]\d{1,2}){0,3}"
_Q_RE = re.compile(r"^(?:question|q)\s*(?:n\s?[°o]\s*|no\s*|numero\s*)?(" + _NUM + r")\b\s*[:.\-–—)]?\s*(.*)$")
_H_RE = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})(?:[.)]|\s*[-–—:])?\s+(\S.*)$")
_KW_RE = re.compile(r"^(?:chapitre|partie|section|rubrique|critere|sous[- ]critere|theme)\s+"
                    r"(\d{1,2}(?:\.\d{1,2}){0,3}|[ivx]{1,5})\b\s*[:.\-–—)]?\s*(.*)$")
_ROMAN_RE = re.compile(r"^([ivx]{1,5})[.)\-–]\s+(\S.*)$")
# Sommaire du cadre (« 2. Moyens humains ........ 4 ») : jamais une question.
_TOC = re.compile(r"(?:\.{3,}|…{2,}|_{4,})\s*\d{0,4}\s*$")
# Premier mot qui trahit une phrase ordinaire commençant par un nombre (« 10 jours ouvrés… »).
_UNIT_START = re.compile(r"^(?:%|€|eur\b|euros?\b|jours?\b|j\b|mois\b|ans?\b|annees?\b|heures?\b|h\b|semaines?\b"
                         r"|m2\b|m²|m3\b|ml\b|km\b|kg\b|t\b|tonnes?\b|pages?\b|mots\b|caracteres\b|lignes?\b"
                         r"|personnes?\b|salaries?\b|points?\b|pts?\b|fois\b|et\b|a\b|au\b|aux\b|ou\b)")
_ANSWER_CUT = re.compile(r"^(?:reponse du candidat|reponse de l'entreprise|votre reponse|reponse|zone de reponse"
                         r"|a completer par le candidat)\s*:?\s*$")
_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
          "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15}


def _heading(line: str) -> Optional[tuple]:
    """(numéro, titre) si la ligne ouvre une question / une rubrique du cadre, sinon None."""
    raw = _flat(line)
    if not raw or len(raw) > 320 or _TOC.search(raw):
        return None
    low = dp.fold(raw)
    m = _Q_RE.match(low)
    if m:
        num = m.group(1).replace("-", ".")
        return num, raw[len(raw) - len(m.group(2)):].strip() if m.group(2) else ""
    m = _KW_RE.match(low)
    if m:
        tok = m.group(1)
        num = str(_ROMAN[tok]) if tok in _ROMAN else tok
        return num, raw[len(raw) - len(m.group(2)):].strip() if m.group(2) else ""
    m = _ROMAN_RE.match(low)
    if m and m.group(1) in _ROMAN:
        title = raw[len(raw) - len(m.group(2)):].strip()
        if title[:1].isupper():
            return str(_ROMAN[m.group(1)]), title
        return None
    m = _H_RE.match(raw)
    if m:
        num, title = m.group(1), m.group(2).strip()
        if _UNIT_START.match(dp.fold(title)) or not (title[:1].isupper() or title[:1] in "«\"'(“"):
            return None
        if any(int(x) > 40 for x in num.split(".")):
            return None
        return num, title
    return None


def _num_key(num: str) -> tuple:
    try:
        return tuple(int(x) for x in num.split("."))
    except ValueError:
        return (999,)


def parse_cadre(text: str) -> list:
    """Questions / rubriques d'un cadre de réponse, dans l'ordre du texte :
    [{numero, intitule, niveau, parents: [{numero, intitule}], question}] — seulement les FEUILLES
    (une rubrique qui a des sous-questions devient un titre, porté par ses enfants). [] si le
    texte ne se découpe pas en au moins deux questions numérotées."""
    lines = str(text or "").replace("\r", "\n").split("\n")
    items = []
    cur = None
    for line in lines:
        h = _heading(line)
        if h is not None:
            cur = {"numero": h[0], "titre": h[1], "body": [], "cut": False}
            items.append(cur)
            continue
        if cur is None or cur["cut"]:
            continue
        s = _flat(line)
        if not s:
            continue
        if _ANSWER_CUT.match(dp.fold(s)):
            cur["cut"] = True
            continue
        cur["body"].append(s)
    if not items:
        return []
    # Même numéro vu deux fois (sommaire sans points de suite) : on garde celui qui a un corps.
    best = {}
    for i, it in enumerate(items):
        k = it["numero"]
        size = len(" ".join(it["body"]))
        if k not in best or size > best[k][1]:
            best[k] = (i, size)
    kept = [it for i, it in enumerate(items) if best[it["numero"]][0] == i]
    nums = {it["numero"] for it in kept}
    out = []
    for it in kept:
        num = it["numero"]
        has_child = any(n != num and n.startswith(num + ".") for n in nums)
        if has_child:
            continue
        parents = []
        parts = num.split(".")
        for k in range(1, len(parts)):
            pn = ".".join(parts[:k])
            par = next((x for x in kept if x["numero"] == pn), None)
            if par is not None:
                parents.append({"numero": pn, "intitule": _flat(par["titre"])[:INTITULE_MAX]})
        body = " ".join(it["body"])
        titre = _flat(it["titre"])
        if not titre:
            titre = body[:160].rstrip(" ,;:")
        if not titre:
            continue
        question = _flat((it["titre"] + " " + body) if it["titre"] else body)[:QUESTION_MAX]
        out.append({"numero": num, "intitule": titre[:INTITULE_MAX], "niveau": len(parts),
                    "parents": parents, "question": question})
    if len(out) < 2:
        return []
    # L'ordre des numéros doit être globalement croissant (sinon ce n'est pas un cadre numéroté).
    keys = [_num_key(x["numero"]) for x in out]
    rising = sum(1 for a, b in zip(keys, keys[1:]) if b > a)
    if rising < 0.7 * (len(keys) - 1):
        return []
    return out[:MAX_SECTIONS]


# ── Limites : document, chaque question, une question ───────────────────────────────

_KINDS = ("pages", "mots", "caracteres", "lignes")


def _limit_out(x: dict, portee: str) -> dict:
    return {"type": x.get("type"), "valeur": x.get("valeur"), "phrase": str(x.get("phrase") or "")[:400],
            "source": str(x.get("source") or "")[:200], "portee": portee}


def limites_du_dossier(grille: Optional[dict]) -> dict:
    """Ce que le dossier impose au document : {document: [...], chaque_question: [...],
    police: {police, taille, phrase} | None, non_controlees: [...]}. Une limite sur une autre
    partie du dossier (CV, fiche référence…) n'est pas contrôlée par l'atelier : elle est rendue
    à part, pour être dite comme telle."""
    c = (grille or {}).get("contraintes") if isinstance(grille, dict) else None
    lims = (c or {}).get("limites") or []
    out = {"document": [], "chaque_question": [], "police": None, "non_controlees": []}
    for x in lims:
        if not isinstance(x, dict):
            continue
        t = x.get("type")
        if t == "police":
            if out["police"] is None and (x.get("police") or x.get("taille")):
                out["police"] = {"police": x.get("police") or "", "taille": x.get("taille"),
                                 "phrase": str(x.get("phrase") or "")[:400]}
            continue
        if t not in _KINDS or not isinstance(x.get("valeur"), (int, float)):
            continue
        obj = x.get("objet") or ""
        if obj == "":
            out["document"].append(_limit_out(x, "document"))
        elif obj == "question_chaque":
            out["chaque_question"].append(_limit_out(x, "chaque_question"))
        else:
            out["non_controlees"].append(dict(_limit_out(x, obj), objet=obj))
    return out


def _cle_phrase(s) -> str:
    return re.sub(r"[^a-z0-9]+", " ", dp.fold(_flat(s))).strip()


def _limite_d_une_question(x: dict, questions: list) -> bool:
    """La phrase de cette limite est-elle celle d'une question du cadre (« Présentez l'encadrement
    (2 pages maximum) ») ? Alors elle vaut pour cette question, pas pour tout le document."""
    ph = _cle_phrase(x.get("phrase"))
    if len(ph) < 8:
        return False
    return any(ph in _cle_phrase(q.get("question")) for q in questions or [])


def limites_section(question: str, chaque_question: list) -> list:
    """Limites d'une section du cadre : celles écrites dans sa question, puis celles qui valent
    pour chaque question."""
    out = []
    for x in gn.limites_texte(question):
        if x.get("type") in _KINDS:
            out.append(_limit_out(x, "section"))
    seen = {(x["type"], x["valeur"]) for x in out}
    for x in chaque_question or []:
        if (x["type"], x["valeur"]) not in seen:
            out.append(dict(x))
    return out


# ── Le plan ───────────────────────────────────────────────────────────────────────────

def _grille_lines(grille: Optional[dict]) -> list:
    if not isinstance(grille, dict):
        return []
    out = []
    for ln in grille.get("criteres") or []:
        if isinstance(ln, dict) and ln.get("dans_le_plan"):
            poids = _flat(ln.get("poids_retenu"))[:40]
            src = str(ln.get("poids_source") or "")
            out.append({"id": str(ln.get("id") or "")[:20], "critere": _flat(ln.get("critere"))[:300],
                        "poids": poids, "phrase": _flat(ln.get("phrase"))[:QUESTION_MAX],
                        "poids_source": (src if src in ("reglement", "utilisateur") else "") if poids else ""})
    return out


def _grille(analysis: Optional[dict]) -> Optional[dict]:
    a = analysis if isinstance(analysis, dict) else {}
    det = a.get("details") if isinstance(a.get("details"), dict) else {}
    g = det.get("grille_notation")
    return g if isinstance(g, dict) else None


def lignes_techniques(analysis: Optional[dict]) -> list:
    """Lignes de « Comment vous serez noté » qui appellent du texte (le prix est jugé sur le
    bordereau) : [{id, critere, poids, poids_source, phrase}], dans l'ordre de la grille."""
    return [ln for ln in _grille_lines(_grille(analysis)) if not est_critere_prix(ln["critere"])]


def criteres_a_verifier(analysis: Optional[dict]) -> int:
    g = _grille(analysis) or {}
    try:
        return int((g.get("compteurs") or {}).get("a_verifier") or 0)
    except (TypeError, ValueError):
        return 0


def empreinte_grille(analysis: Optional[dict]) -> list:
    """Ce que le plan a lu de la grille (pour dire ensuite ce qui a changé) : [[id, critère, poids, source]]."""
    return [[ln["id"], ln["critere"], ln["poids"], ln["poids_source"]] for ln in lignes_techniques(analysis)]


def bases_disponibles(analysis: Optional[dict], cadre_text: str = "") -> dict:
    """Les bases de plan qui existent pour ce marché : {cadre, grille} (auto et libre existent toujours)."""
    return {"auto": True, "cadre": bool(parse_cadre(cadre_text)) if cadre_text else False,
            "grille": bool(lignes_techniques(analysis)), "libre": True}


def _libres(en_groupement: bool, critere: Optional[dict] = None) -> list:
    out = []
    for i, titre in enumerate(PARTIES_LIBRES, 1):
        if i == 1 and en_groupement:
            titre = PRESENTATION_GROUPEMENT
        s = {"numero": str(i), "intitule": titre, "niveau": 1, "parents": [], "question": "",
             "source_plan": LIBRE, "critere": "", "critere_id": "", "poids": "", "partie_de_critere": False,
             "limite": []}
        if critere:
            s.update(critere=critere["critere"], critere_id=critere["id"], poids=critere["poids"],
                     poids_source=critere.get("poids_source") or "", partie_de_critere=True,
                     question=critere["phrase"])
        out.append(s)
    return out


def section_de_critere(ln: dict, numero: str = "") -> dict:
    """Une partie pour une ligne de « Comment vous serez noté » (intitulé = le critère, poids et
    provenance tels quels, question = la phrase du règlement)."""
    return {"numero": numero, "intitule": ln["critere"][:INTITULE_MAX], "niveau": 1, "parents": [],
            "question": ln["phrase"], "source_plan": GRILLE, "critere": ln["critere"], "critere_id": ln["id"],
            "poids": ln["poids"], "poids_source": ln.get("poids_source") or "", "partie_de_critere": False,
            "limite": []}


def build_plan(analysis: Optional[dict], cadre_text: str = "", base: str = "auto",
               en_groupement: bool = False, dossier_present: bool = True) -> dict:
    """Plan proposé, SANS IA. base : auto (cadre imposé > grille > libre) | grille | cadre | libre.
    Renvoie {source, message, fichier_impose, message_fichier, avertissement_fichier,
    cadre_non_decoupe, criteres_hors_dossier, criteres_a_verifier, message_a_verifier,
    dossier_present, bases, grille, limites (limites_du_dossier), sections: [...]}.
    dossier_present=False : aucun dossier du marché importé (rien n'a été lu) — on le dit."""
    out = _build_plan(analysis, cadre_text, base, en_groupement, dossier_present)
    n_av = criteres_a_verifier(analysis)
    out["criteres_a_verifier"] = n_av
    out["message_a_verifier"] = msg_a_verifier(n_av) if out["source"] != CADRE and base != LIBRE else ""
    if out["message_a_verifier"]:
        out["message"] = (out["message"] + " " + out["message_a_verifier"]).strip()
    out["avertissement_fichier"] = avertissement_fichier(out["fichier_impose"], out["source"])
    out["dossier_present"] = bool(dossier_present)
    out["bases"] = bases_disponibles(analysis, cadre_text)
    out["grille"] = empreinte_grille(analysis)
    return out


def _build_plan(analysis: Optional[dict], cadre_text: str, base: str, en_groupement: bool,
                dossier_present: bool) -> dict:
    base = base if base in BASES else "auto"
    g = _grille(analysis)
    cont = (g or {}).get("contraintes") or {}
    impose = bool(cont.get("fichier_impose"))
    lims = limites_du_dossier(g)
    # Une limite écrite DANS une question du cadre vaut pour cette question : elle est rattachée à
    # la partie quand le plan suit le cadre ; sinon elle n'est pas contrôlée (dit comme tel).
    qs_all = parse_cadre(cadre_text) if cadre_text else []
    if qs_all:
        doc, par_question = [], []
        for x in lims["document"]:
            (par_question if _limite_d_une_question(x, qs_all) else doc).append(x)
        lims["document"] = doc
        lims["_par_question"] = par_question
    out = {"source": LIBRE, "message": "", "fichier_impose": impose,
           "message_fichier": gn.MSG_FICHIER_IMPOSE if impose else "",
           "cadre_non_decoupe": False, "criteres_hors_dossier": [], "limites": lims, "sections": []}

    # 1. Le cadre de réponse (imposé, ou choisi par l'utilisateur).
    par_question = lims.pop("_par_question", [])
    prefixe = ""
    if base in ("auto", CADRE) and (impose or base == CADRE):
        qs = qs_all
        if qs:
            out["source"] = CADRE
            out["message"] = MSG_CADRE_IMPOSE if impose else MSG_CADRE_FOURNI
            for q in qs:
                out["sections"].append({**q, "source_plan": CADRE, "critere": "", "critere_id": "", "poids": "",
                                        "poids_source": "", "partie_de_critere": False,
                                        "limite": limites_section(q["question"], lims["chaque_question"])})
            return out
        if impose:
            out["cadre_non_decoupe"] = True
        elif base == CADRE:
            prefixe = MSG_PAS_DE_CADRE       # demandé, mais introuvable : on le dit
    # Plan hors cadre : les limites propres à une question ne sont pas contrôlées par l'atelier.
    for x in par_question:
        lims["non_controlees"].append(dict(x, portee="question", objet="question"))

    # 2. La grille confirmée (sauf choix explicite du plan libre).
    lines = _grille_lines(g) if base != LIBRE else []
    tech = []
    for ln in lines:
        if est_critere_prix(ln["critere"]):
            out["criteres_hors_dossier"].append({"critere": ln["critere"], "poids": ln["poids"], "raison": MSG_PRIX})
        else:
            tech.append(ln)
    en_attente = criteres_a_verifier(analysis) > 0
    if len(tech) >= 2:
        out["source"] = GRILLE
        out["message"] = MSG_GRILLE
        for i, ln in enumerate(tech[:MAX_SECTIONS], 1):
            out["sections"].append(section_de_critere(ln, str(i)))
    elif len(tech) == 1:
        out["source"] = GRILLE
        # « ne donne qu'un critère » : jamais tant que d'autres lignes sont à vérifier.
        out["message"] = (MSG_GRILLE_UN_CONFIRME if en_attente else MSG_GRILLE_UN_CRITERE).format(c=tech[0]["critere"])
        out["sections"] = _libres(en_groupement, critere=tech[0])
    else:
        out["source"] = LIBRE
        if base == LIBRE:
            out["message"] = MSG_LIBRE_CHOISI
        elif not dossier_present and not g:
            out["message"] = MSG_SANS_DOSSIER
        elif base == GRILLE:
            out["message"] = MSG_PAS_DE_CRITERE + " Adjugo propose un plan simple, sans IA, à adapter au marché."
        elif en_attente:
            out["message"] = MSG_LIBRE_EN_ATTENTE
        else:
            out["message"] = MSG_LIBRE
        out["sections"] = _libres(en_groupement)
    if out["cadre_non_decoupe"]:
        out["message"] = MSG_CADRE_NON_DECOUPE + " " + out["message"]
    elif prefixe:
        out["message"] = prefixe + " " + out["message"]
    return out
