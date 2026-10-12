"""
« Comment vous serez noté » : la grille de l'acheteur, retrouvée dans le texte
(rédaction, vague 1 — C1 et C2 minimal de l'étude, §6.3).

Doctrine (étude §7) :
  • l'IA PROPOSE les critères et recopie leur phrase ; tout le reste est contrôlé SANS IA :
    la phrase doit exister dans le texte du dossier (citation_guard / _norm_citation) et le
    poids doit figurer dans cette phrase, TEL QU'ÉCRIT (« 60 % », « 40 points ») ;
  • jamais de poids ni d'ordre inventés : sans poids écrit, « critères non pondérés, sans
    ordre indiqué » (ou l'ordre que le règlement annonce, avec sa phrase) ;
  • une ligne non retrouvée est « à vérifier dans le règlement » et n'entre pas dans le plan
    tant que l'utilisateur ne l'a pas confirmée ;
  • contrôle du total sans IA : 100 % ou le nombre de points annoncé, sinon avertissement ;
  • on ne dit jamais « vérifié » : on dit où la phrase a été trouvée.

C2 minimal (sans IA, toujours avec la phrase source) : un cadre de réponse est fourni ; une
phrase en rend l'usage obligatoire ; limites de pages, mots, caractères, lignes ou police ;
visite obligatoire. Stockés dans l'analyse : ils serviront au compteur de l'atelier (vague 2).

Rien ici n'appelle l'IA ni le réseau : fonctions pures sur le texte déjà extrait.
"""
import copy
import re
from typing import Optional

from app.services import dce_pieces as dp
from app.services.analysis import citation_guard

VERSION = 1
MAX_CRITERES = 15
PHRASE_MAX = 300

RETROUVE = "retrouve"
A_VERIFIER = "a_verifier"

MSG_FICHIER_IMPOSE = "Ce marché impose son propre fichier de réponse : vous devrez y recopier votre texte."
MSG_NON_PONDERES = "Critères non pondérés, sans ordre indiqué."
MSG_NON_PONDERES_ORDRE = "Critères non pondérés, classés dans l'ordre que donne le règlement."
MSG_A_VERIFIER = "à vérifier dans le règlement"

_STOP = {"de", "des", "du", "la", "le", "les", "et", "en", "au", "aux", "a", "l", "d", "un", "une",
         "par", "pour", "sur", "dans", "offre", "offres", "candidat", "critere", "criteres", "note"}


# ── Texte : à plat, replié, découpé ───────────────────────────────────────────────────

def _flat(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _fold(s) -> str:
    """Repli de même longueur (cf. dce_pieces.fold) + guillemets droits."""
    t = dp.fold(s)
    return t.replace("“", '"').replace("”", '"').replace("„", '"')


_BOUND = re.compile(r"(?<=[.;!?])\s")


def _sentence_bounds(flat: str, a: int, b: int):
    """Début et fin de la phrase qui contient [a, b] (ponctuation forte, ou bornes du texte)."""
    start = 0
    for m in _BOUND.finditer(flat, 0, a):
        start = m.end()
    m = _BOUND.search(flat, b)
    end = m.start() if m else len(flat)
    return start, end


def _clip(flat: str, start: int, end: int, a: int, b: int, limit: int = PHRASE_MAX):
    """Réduit [start, end] à `limit` caractères autour de [a, b], sur des limites de mots."""
    if end - start <= limit:
        return start, end
    room = max(0, limit - (b - a))
    s = max(start, a - room // 2)
    e = min(end, s + limit)
    s = max(start, e - limit)
    if s > start:
        sp = flat.find(" ", s)
        if 0 <= sp < a:
            s = sp + 1
    if e < end:
        sp = flat.rfind(" ", b, e)
        if sp > b:
            e = sp
    return s, e


def _flat_breaks(s: str):
    """Texte à plat (blancs → une espace) + positions des anciens retours à la ligne : une
    ligne de tableau (« Prix | 40 % ») reste une ligne même une fois mise à plat."""
    parts, breaks, n, last = [], [], 0, 0
    s = str(s or "")
    for m in re.finditer(r"\s+", s):
        seg = s[last:m.start()]
        parts.append(seg)
        n += len(seg)
        if "\n" in m.group(0):
            breaks.append(n)
        parts.append(" ")
        n += 1
        last = m.end()
    parts.append(s[last:])
    return "".join(parts), breaks


class _Piece:
    __slots__ = ("nom", "type", "libelle", "flat", "low", "idx", "breaks")

    def __init__(self, idx, nom, kind, texte):
        self.idx, self.nom, self.type = idx, nom or "", kind
        self.libelle = dp.label(kind)
        self.flat, self.breaks = _flat_breaks(texte)
        self.low = _fold(self.flat)

    def line_phrase(self, a: int, b: int) -> tuple:
        """(début, phrase) de la ligne ∩ phrase qui contient [a, b] (repli : la phrase)."""
        s, e = _sentence_bounds(self.flat, a, b)
        ls = max([x for x in self.breaks if x <= a] or [0])
        le = min([x for x in self.breaks if x >= b] or [len(self.flat)])
        if not any(a < x < b for x in self.breaks):
            s, e = max(s, ls), min(e, le)
        s, e = _clip(self.flat, s, e, a, b)
        raw = self.flat[s:e]
        lead = len(raw) - len(raw.lstrip())
        return s + lead, raw.strip()


def _pieces(text: str) -> list:
    return [_Piece(i, p["nom"], p["type"], p["texte"]) for i, p in enumerate(dp.typed_pieces(text))]


def _source_label(p: Optional[_Piece]) -> str:
    if p is None:
        return ""
    return f"{p.libelle} ({p.nom})" if p.nom else p.libelle


def _locate(phrase: str, pieces: list):
    """(pièce, position, phrase d'ORIGINE) d'une phrase dans les pièces ; (None, None, '') sinon."""
    target = _fold(_flat(phrase))
    if len(target) < 4:
        return None, None, ""
    for p in pieces:
        i = p.low.find(target)
        if i >= 0:
            return p, i, p.flat[i:i + len(target)]
    return None, None, ""


# ── Poids tels qu'écrits ──────────────────────────────────────────────────────────────

_W_TOKEN = re.compile(r"(?<![\d.,])(\d{1,3}(?:[.,]\d{1,2})?)\s*(%|pour ?cent\b|points?\b|pts?\b|/\s*100\b)")
_BARE_NUM = re.compile(r"(?<![\d.,])(\d{1,3}(?:[.,]\d{1,2})?)(?![\d.,])")


def _unit(u: str) -> str:
    u = (u or "").replace(" ", "")
    if u.startswith("%") or u.startswith("pour") or u.startswith("/"):
        return "%"
    return "points"


def _num(s: str) -> float:
    return float(str(s).replace(",", "."))


def parse_weight(s) -> Optional[dict]:
    """« 60 % » → {valeur: 60.0, unite: '%'} ; « 40 points » → points ; nombre seul → unité
    inconnue (None). Rien de reconnaissable → None. Ne lève jamais."""
    try:
        low = _fold(_flat(s))
        if not low:
            return None
        m = _W_TOKEN.search(low)
        if m:
            return {"valeur": _num(m.group(1)), "unite": _unit(m.group(2))}
        m = _BARE_NUM.search(low)
        if m:
            return {"valeur": _num(m.group(1)), "unite": None}
    except Exception:
        pass
    return None


def _weights_in(flat: str) -> list:
    """Poids écrits dans un passage : [(valeur, unité, texte tel qu'écrit, début, fin)]."""
    low = _fold(flat)
    return [(_num(m.group(1)), _unit(m.group(2)), flat[m.start():m.end()], m.start(), m.end())
            for m in _W_TOKEN.finditer(low)]


def _weight_match(flat: str, claimed: dict, after: int = 0):
    """Le poids annoncé figure-t-il dans le passage (même valeur, même unité si connue) ?"""
    for v, u, raw, a, b in _weights_in(flat):
        if a < after:
            continue
        if abs(v - claimed["valeur"]) < 0.001 and (claimed.get("unite") in (None, u)):
            return v, u, raw, a, b
    return None


# ── Noms des critères ─────────────────────────────────────────────────────────────────

def _stems(name: str) -> list:
    words = [w for w in re.split(r"[^a-z0-9]+", _fold(name)) if w and w not in _STOP]
    sig = [w for w in words if len(w) >= 3] or words
    return [w[:5] if len(w) > 5 else w for w in sig][:6]


def _stem_at(low: str, stem: str, start: int = 0) -> int:
    m = re.search(r"(?<![a-z0-9])" + re.escape(stem), low[start:])
    return (m.start() + start) if m else -1


def _names_ok(low: str, stems: list) -> bool:
    """Le premier mot significatif du critère est présent, et au moins la moitié des autres."""
    if not stems:
        return False
    if _stem_at(low, stems[0]) < 0:
        return False
    hits = sum(1 for s in stems if _stem_at(low, s) >= 0)
    return hits * 2 >= len(stems)


_CRIT_ZONE = re.compile(r"crit[e]res? (?:d'attribution|de jugement|de choix|de selection|d'evaluation|de notation|retenus|"
                        r"d'analyse|de classement)|jugement des offres|attribution du marche|choix de l'offre|"
                        r"offre economiquement la plus avantageuse")


def _crit_zones(p: _Piece, span: int = 1500) -> list:
    return [(m.start(), min(len(p.low), m.end() + span)) for m in _CRIT_ZONE.finditer(p.low)]


def _recover(stems: list, claimed: Optional[dict], scope: list):
    """Recherche SANS IA de la phrase d'un critère que l'IA n'a pas su recopier :
    • poids annoncé : le nom suivi, à moins de 120 caractères, du même poids écrit ;
    • sans poids : le nom, seulement dans la zone « critères de jugement / d'attribution »
      du règlement (« prix » apparaît partout ailleurs)."""
    if not stems:
        return None
    for p in scope:
        pos = 0
        while True:
            i = _stem_at(p.low, stems[0], pos)
            if i < 0:
                break
            pos = i + 1
            if claimed is not None:
                w = _weight_match(p.flat[i:i + 120], claimed)
                if not w:
                    continue
                a, b = i, i + w[4]
            else:
                if not any(z0 <= i < z1 for z0, z1 in _crit_zones(p)):
                    continue
                a, b = i, i + len(stems[0])
            s, phrase = p.line_phrase(a, b)
            if len(phrase) >= 4 and _names_ok(_fold(phrase), stems):
                return p, s, phrase
    return None


# ── Lignes de critères ────────────────────────────────────────────────────────────────

def _raw_criteres(raw) -> list:
    out = []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return out
    for x in raw:
        if isinstance(x, dict):
            name = x.get("critere") or x.get("intitule") or x.get("nom") or x.get("libelle") or ""
            pond = x.get("ponderation") or x.get("poids") or ""
            ex = x.get("extrait") or x.get("phrase") or x.get("source") or ""
            if isinstance(ex, (list, tuple)):
                ex = " ".join(str(e) for e in ex if e)
        elif isinstance(x, str):
            name, pond, ex = x, "", ""
        else:
            continue
        name = _flat(name)[:160]
        if name:
            out.append((name, _flat(pond)[:40], str(ex or "")))
    return out


def _line(i, name, pond, ex, text, pieces, scope_rc) -> dict:
    claimed = parse_weight(pond) if pond else None
    if claimed is not None and claimed.get("valeur", 0) <= 0:
        claimed = None
    stems = _stems(name)
    phrase, piece, pos, poids, unite, valeur = "", None, None, "", None, None

    verified = citation_guard(text, ex) if ex else ""
    vp, vpos, vorig = _locate(verified, pieces) if verified else (None, None, "")
    if vorig and not _names_ok(_fold(vorig), stems):
        vp, vpos, vorig = None, None, ""            # la phrase ne parle pas de ce critère

    if claimed is not None:
        w = _weight_match(vorig, claimed) if vorig else None
        if w:
            phrase, piece, pos = vorig, vp, vpos
            valeur, unite, poids = w[0], w[1], w[2]
        else:
            rec = _recover(stems, claimed, scope_rc + [p for p in pieces if p not in scope_rc])
            if rec:
                piece, pos, phrase = rec
                w = _weight_match(phrase, claimed)
                valeur, unite, poids = (w[0], w[1], w[2]) if w else (None, None, "")
            else:
                phrase, piece, pos = vorig, vp, vpos   # vraie phrase, mais sans le poids annoncé
    else:
        if vorig:
            phrase, piece, pos = vorig, vp, vpos
        else:
            rec = _recover(stems, None, scope_rc)
            if rec:
                piece, pos, phrase = rec
        if phrase and len(phrase) <= 160:
            # Poids écrit juste après le nom, unique dans une phrase courte : repris tel quel.
            low = _fold(phrase)
            at = _stem_at(low, stems[0]) if stems else -1
            ws = [w for w in _weights_in(phrase) if at >= 0 and 0 <= w[3] - at <= 80]
            if len(ws) == 1 and len(_weights_in(phrase)) == 1:
                valeur, unite, poids = ws[0][0], ws[0][1], ws[0][2]

    if phrase and not citation_guard(text, phrase, min_len=4):
        phrase, piece, pos, poids, unite, valeur = "", None, None, "", None, None
    statut = RETROUVE if phrase and (claimed is None or poids) else A_VERIFIER
    return {
        "id": f"c{i + 1}", "critere": name,
        "poids": poids if statut == RETROUVE else "",
        "poids_valeur": valeur if statut == RETROUVE else None,
        "poids_unite": unite if statut == RETROUVE else None,
        "phrase": phrase,
        "source": _source_label(piece) if phrase else "",
        "statut": statut,
        "_pos": (piece.idx, pos) if piece is not None and pos is not None else None,
    }


# ── Ordre, total annoncé, poids présents dans le texte ───────────────────────────────

_ORDER_NEG = re.compile(r"(?:ne sont pas|non) (?:hierarchis|classes|ponderes|ordonnes)|sans (?:ordre|hierarchi|ponderation|priorit)"
                        r"|(?:egale|meme) importance|aucun ordre|aucune hierarchie")
_ORDER_POS = re.compile(r"ordre (?:decroissant|d'importance|de priorite|hierarchique)|par ordre (?:decroissant|d'importance)"
                        r"|classes? par ordre|hierarchises?|importance decroissante")
_TOTAL_RE = (
    re.compile(r"sur un total de (\d{1,4}) ?(?:points?|pts?)\b"),
    re.compile(r"\bnote (?:globale|finale|totale|maximale)\b[^.;]{0,30}?\b(?:sur|de|:) ?(\d{1,4})\b"),
    re.compile(r"\b(\d{1,4}) ?points? au total\b"),
    re.compile(r"\btotal (?:de|des notes ?:?|:) ?(\d{1,4}) ?(?:points?|pts?)\b"),
)


def _phrase_at(p: _Piece, a: int, b: int) -> str:
    """Phrase source d'un repérage : la ligne ∩ la phrase qui le contient (≤ PHRASE_MAX)."""
    return p.line_phrase(a, b)[1]


def _ordre(scope: list) -> dict:
    for rx, indique in ((_ORDER_NEG, False), (_ORDER_POS, True)):
        for p in scope:
            for m in rx.finditer(p.low):
                ph = _phrase_at(p, m.start(), m.end())
                if "crit" in _fold(ph):
                    return {"indique": indique, "phrase": ph, "source": _source_label(p)}
    return {"indique": None, "phrase": "", "source": ""}


def _total_annonce(scope: list) -> Optional[dict]:
    for rx in _TOTAL_RE:
        for p in scope:
            m = rx.search(p.low)
            if m:
                return {"valeur": float(m.group(1)), "phrase": _phrase_at(p, m.start(), m.end()),
                        "source": _source_label(p)}
    return None


def _poids_dans_le_texte(scope: list, lines: list) -> bool:
    """Un poids (%, points) est-il écrit près des critères ? Si oui, on ne prétend jamais que
    les critères sont « non pondérés » : on dit que les poids sont à vérifier."""
    for p in scope:
        zones = " ".join(p.low[z0:z1] for z0, z1 in _crit_zones(p))
        zones = re.sub(r"(?:sans|aucune|pas de|ni) ponderation|ponderation (?:n'est pas|non)", " ", zones)
        if re.search(r"\bponderations?\b|\bcoefficients?\b", zones):
            return True
        for z0, z1 in _crit_zones(p):
            if _weights_in(p.flat[z0:z1]):
                return True
    for ln in lines:
        if ln.get("_pos"):
            idx, pos = ln["_pos"]
            p = next((x for x in scope if x.idx == idx), None)
            if p is not None and _weights_in(p.flat[max(0, pos - 300):pos + len(ln["phrase"]) + 300]):
                return True
    return False


# ── C2 minimal : ce que le dossier impose ─────────────────────────────────────────────

_NUM = r"(?<![\d.,])(\d{1,3}(?:[  .]\d{3})+|\d{1,7})"
_LIMIT_WORDS = re.compile(
    r"maximum|\bmaxi\b|\bmax\b|au plus|limitee?s?\b|limite a|limite de|dans la limite|n'excedant pas|n'excede pas"
    r"|ne (?:doit|doivent|devra|devront|pourra|pourront|peut|peuvent|saurait|sauraient) (?:pas )?(?:exceder|depasser)"
    r"|ne (?:pas )?(?:exceder|depasser)|sans (?:exceder|depasser)|pas plus de|plafonnee?s?\b|au-dela de")
_UNITS = (
    ("pages", r"(?:pages?|feuillets?)\b", (1, 400)),
    ("mots", r"mots\b", (20, 200000)),
    ("caracteres", r"caracteres?\b", (100, 2000000)),
    ("lignes", r"lignes?\b", (1, 5000)),
)
_FONTS = (r"arial|calibri|times new roman|times|verdana|helvetica|tahoma|garamond|cambria|century gothic|marianne"
          r"|open sans|trebuchet(?: ms)?|georgia|segoe ui|liberation sans|dejavu sans|roboto|lato|source sans(?: pro)?")
_SIZE = r"(\d{1,2}(?:[.,]5)?)"
_FONT_RES = (
    re.compile(r"\bpolice\b(?: de caracteres?)?(?: de type| type)? ?:? ?(?P<font>" + _FONTS + r")\b"
               r"(?: ?,? ?(?:en |de )?(?:taille |corps )?(?P<size>" + _SIZE[1:-1] + r")\b)?"),
    re.compile(r"\b(?P<font>" + _FONTS + r")\b ?,? ?(?:en taille |de taille |taille |corps )?(?P<size>" + _SIZE[1:-1] + r")"
               r" ?(?:pt|pts|points?)?\b"),
    re.compile(r"\b(?:taille|corps) (?:minimale? )?(?:de |du )?(?:la )?(?:police|caracteres?)(?: minimale?)? ?(?::|de|egale a|=)? ?"
               r"(?P<size>" + _SIZE[1:-1] + r")\b"),
    re.compile(r"\bpolice (?:de )?(?:taille|corps)(?: minimale?)? ?(?::|de)? ?(?P<size>" + _SIZE[1:-1] + r")\b"),
)
_VISITE_RE = re.compile(r"\bvisites?\b(?P<mid>[^.;]{0,90}?)\bobligatoires?\b|\bobligatoires?\b(?P<mid2>[^.;]{0,25}?)\bvisites?\b")
_VISITE_NEG = re.compile(r"\b(?:pas|non|nullement|aucune?|plus)\b|facultati")
_VISITE_NEG_AVANT = re.compile(r"\b(?:pas|non|aucune?|sans|ni)\b(?: d[e'] ?| la | une )?\s*$")
_VISITE_HORS = re.compile(r"medical|maintenance|periodique|entretien|reception|reunion")
_CADRE_MENTION = re.compile(r"cadre (?:de |du )?(?:la )?(?:reponse|memoire)|cadre technique de reponse|trame (?:de |du )?(?:la )?(?:reponse|memoire)"
                            r"|questionnaire technique|\bcrt\b|\bcrmt\b")
_OBLIG = re.compile(
    r"obligatoire|obligatoirement|imperativement|imperatif|exclusivement|sous peine|a peine d"
    r"|sans (?:en )?(?:modifier|alterer)|ne (?:doit|doivent|devra|devront|pourra) (?:pas )?etre modifie"
    r"|(?:doit|doivent|devra|devront) (?:etre )?(?:utilises?|completes?|renseignes?|remplis?|respectes?|rediges?|presentes?)"
    r"|(?:est|sont) a (?:completer|renseigner|remplir|utiliser)|(?:doit|doivent|devra|devront) (?:y )?repondre"
    r"|(?:cadre|trame)[^.;]{0,60}\b(?:dument )?(?:completee?s?|renseignee?s?|remplie?s?)\b")
_FACULT = re.compile(r"facultati|a titre indicatif|a titre d'exemple|(?:pourra|pourront|peut|peuvent) (?:etre )?(?:utilise|s'appuyer|servir|s'inspirer)"
                     r"|\blibre\b|n'est pas (?:obligatoire|impose)|non obligatoire|pas obligatoire|ne sont pas imposes?|s'il le souhaite")


def _int(s: str) -> int:
    return int(re.sub(r"\D", "", s))


_CLAUSE_CUT = re.compile(r"[,;:()]| et | ou | mais | alors ")


def _limit_word_near(p: _Piece, a: int, b: int, kind: str):
    """Position d'un mot de LIMITE rattaché au nombre : dans la même proposition, juste avant
    (« ne devra pas excéder 10 pages ») ou juste après (« 10 pages A4 maximum »). « Le CCTP
    comporte 45 pages et les pénalités sont plafonnées » n'est pas une limite."""
    s, e = _sentence_bounds(p.flat, a, b)
    before = p.low[max(s, a - 45):a]
    cut = [m.end() for m in _CLAUSE_CUT.finditer(before)]
    b0 = max(s, a - 45) + (cut[-1] if cut else 0)
    after_end = min(e, b + 28)
    m2 = _CLAUSE_CUT.search(p.low, b, after_end)
    a1 = m2.start() if m2 and not p.low.startswith("(", m2.start()) else after_end
    m = _LIMIT_WORDS.search(p.low, b0, a)
    if m:
        return m.start()
    m = _LIMIT_WORDS.search(p.low, b, a1)
    if m:
        return m.end()
    if kind == "caracteres":
        m = re.compile(r"espaces (?:non )?(?:compris|inclus)").search(p.low, b, min(e, b + 40))
        if m:
            return m.end()
    return None


# « le nombre de pages est limité à 10 », « pages limitées à 20 »
_LIMIT_REVERSED = re.compile(r"(?:nombre (?:de |des )|nombre maximal (?:de |des )|nombre maximum (?:de |des ))?(pages?|feuillets?|mots|caracteres|lignes)"
                             r" (?:est |sont )?(?:limitee?s? a|plafonnee?s? a|ne (?:doit|devra|peut|pourra) (?:pas )?(?:exceder|depasser)) "
                             + _NUM + r"\b")
_KIND_OF = {"page": "pages", "pages": "pages", "feuillet": "pages", "feuillets": "pages", "mots": "mots",
            "caracteres": "caracteres", "lignes": "lignes"}


def _limites(scope: list) -> list:
    out, seen = [], set()

    def _add(p, kind, val, a, b, texte, lo, hi):
        if not (lo <= val <= hi):
            return
        ph = _phrase_at(p, a, b)
        key = (kind, val, _fold(ph))
        if key in seen:
            return
        seen.add(key)
        out.append({"type": kind, "valeur": val, "texte": texte, "phrase": ph, "source": _source_label(p)})

    bounds = {k: (lo, hi) for k, _rx, (lo, hi) in _UNITS}
    for p in scope:
        for kind, unit_rx, (lo, hi) in _UNITS:
            for m in re.finditer(_NUM + r" ?" + unit_rx, p.low):
                try:
                    val = _int(m.group(1))
                except ValueError:
                    continue
                s, e = _sentence_bounds(p.flat, m.start(), m.end())
                before = p.low[max(s, m.start() - 35):m.start()]
                after = p.low[m.end():min(e, m.end() + 30)]
                # « minimum 2 pages », « au moins 3 pages » : un plancher, pas une limite.
                if re.search(r"(?:minimum|au moins|minimal\w*|plus de)(?: de| d')? ?$", before) \
                        or re.match(r" ?(?:\([^)]{0,30}\) ?)?(?:minimum|au moins|minimal)", after):
                    continue
                w = _limit_word_near(p, m.start(), m.end(), kind)
                if w is None:
                    continue
                _add(p, kind, val, min(w, m.start()), max(w, m.end()), p.flat[m.start():m.end()], lo, hi)
        for m in _LIMIT_REVERSED.finditer(p.low):
            kind = _KIND_OF.get(m.group(1), "pages")
            try:
                val = _int(m.group(2))
            except ValueError:
                continue
            lo, hi = bounds[kind]
            _add(p, kind, val, m.start(), m.end(), p.flat[m.start():m.end()], lo, hi)
        for rx in _FONT_RES:
            for m in rx.finditer(p.low):
                font = m.groupdict().get("font")
                size = m.groupdict().get("size")
                taille = _num(size) if size else None
                if taille is not None and not (6 <= taille <= 24):
                    continue
                if not font and taille is None:
                    continue
                ph = _phrase_at(p, m.start(), m.end())
                key = ("police", font or "", taille, _fold(ph))
                if key in seen or any(o["type"] == "police" and _fold(o["phrase"]) == _fold(ph) for o in out):
                    continue
                seen.add(key)
                fs = m.start("font") if font else None
                out.append({"type": "police",
                            "police": p.flat[fs:m.end("font")] if font else "",
                            "taille": (int(taille) if taille is not None and float(taille).is_integer() else taille),
                            "texte": p.flat[m.start():m.end()].strip(" ,:"),
                            "phrase": ph, "source": _source_label(p)})
    return out[:20]


def _visite(scope: list) -> Optional[dict]:
    for p in scope:
        for m in _VISITE_RE.finditer(p.low):
            mid = m.group("mid") if m.group("mid") is not None else (m.group("mid2") or "")
            ph = _phrase_at(p, m.start(), m.end())
            low = _fold(ph)
            before = p.low[max(0, m.start() - 25):m.start()]
            if _VISITE_NEG.search(mid) or _VISITE_NEG_AVANT.search(before) or "facultati" in low:
                continue
            if _VISITE_HORS.search(p.low[m.start():m.end() + 30]):
                continue
            return {"obligatoire": True, "phrase": ph, "source": _source_label(p)}
    return None


def _sentences_with(rx, scope: list):
    for p in scope:
        for m in rx.finditer(p.low):
            yield p, m, _phrase_at(p, m.start(), m.end())


def _cadre(pieces: list, scope: list) -> dict:
    cadres = [p for p in pieces if p.type == dp.CADRE]
    mention, oblig = None, None
    for p, m, ph in _sentences_with(_CADRE_MENTION, scope):
        low = _fold(ph)
        if mention is None:
            mention = (ph, _source_label(p))
        if oblig is None and _OBLIG.search(low) and not _FACULT.search(low):
            oblig = (ph, _source_label(p))
        if mention and oblig:
            break
    return {
        "fourni": bool(cadres),
        "pieces": [p.nom for p in cadres if p.nom][:5],
        "mentionne": bool(mention),
        "phrase": mention[0] if mention else "",
        "source": mention[1] if mention else "",
        "obligatoire": {"phrase": oblig[0], "source": oblig[1]} if oblig else None,
    }


# ── Calculs dérivés (rejoués après chaque choix de l'utilisateur) ─────────────────────

def _in_plan(ln: dict) -> bool:
    choix = (ln.get("choix_utilisateur") or {}).get("choix")
    if choix == "ecarte":
        return False
    return ln.get("statut") == RETROUVE or choix == "confirme"


def _fmt_total(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(round(v, 2)).replace(".", ",")


def refresh(g: dict) -> dict:
    """Recalcule, SANS IA et sans le texte, ce qui dépend des lignes et des choix de
    l'utilisateur : lignes du plan, poids retenus, pondération, contrôle du total."""
    lines = g.get("criteres") or []
    for ln in lines:
        ch = ln.get("choix_utilisateur") or {}
        ln["dans_le_plan"] = _in_plan(ln)
        if ln.get("statut") == RETROUVE and ln.get("poids"):
            ln["poids_retenu"], ln["poids_source"] = ln["poids"], "reglement"
            ln["_v"], ln["_u"] = ln.get("poids_valeur"), ln.get("poids_unite")
        elif ch.get("choix") == "confirme" and ch.get("poids"):
            w = parse_weight(ch["poids"]) or {}
            ln["poids_retenu"], ln["poids_source"] = ch["poids"], "utilisateur"
            ln["_v"], ln["_u"] = w.get("valeur"), w.get("unite")
        else:
            ln["poids_retenu"], ln["poids_source"] = "", ""
            ln["_v"], ln["_u"] = None, None
    plan = [ln for ln in lines if ln["dans_le_plan"]]
    pending = [ln for ln in lines if ln.get("statut") == A_VERIFIER and not (ln.get("choix_utilisateur") or {}).get("choix")]
    weighted = [ln for ln in plan if ln["_v"] is not None]
    g["compteurs"] = {"criteres": len(lines), "dans_le_plan": len(plan), "a_verifier": len(pending),
                      "ecartes": sum(1 for ln in lines if (ln.get("choix_utilisateur") or {}).get("choix") == "ecarte")}

    ordre = g.get("ordre") or {}
    if not lines or (not plan and not pending):
        pond = "aucun"
        msg = ("Aucun critère de jugement n'a été retrouvé : lisez le règlement de la consultation."
               if not lines else "Aucun critère n'est retenu : vous les avez tous écartés.")
    elif plan and len(weighted) == len(plan) and not pending:
        pond, msg = "ponderes", ""
    elif not weighted and not pending and not g.get("poids_dans_le_texte"):
        pond = "non_ponderes"
        msg = MSG_NON_PONDERES_ORDRE if ordre.get("indique") is True else MSG_NON_PONDERES
    else:
        pond = "incomplet"
        sans_poids = len(plan) - len(weighted)
        parts = []
        if pending:
            parts.append(f"{len(pending)} critère(s) à vérifier dans le règlement : ils n'entrent pas dans "
                         "votre plan tant que vous ne les avez pas confirmés.")
        if sans_poids:
            parts.append(f"Le poids de {sans_poids} critère(s) n'a pas été retrouvé dans sa phrase : "
                         "vérifiez-le dans le règlement.")
        msg = " ".join(parts)
    g["ponderation"] = {"statut": pond, "message": msg}

    units = {ln["_u"] for ln in weighted}
    total = sum(ln["_v"] for ln in weighted) if weighted else 0.0
    ann = g.get("total_annonce") or None
    if not weighted:
        ct = {"statut": "sans_objet", "message": ""}
    elif len(units) > 1 or None in units:
        ct = {"statut": "ecart", "message": "Les poids ne sont pas exprimés dans la même unité : vérifiez dans le règlement."}
    elif len(weighted) < len(plan):
        ct = {"statut": "incomplet",
              "message": f"Total non vérifiable : {len(plan) - len(weighted)} critère(s) sans poids retrouvé."}
    else:
        unit = next(iter(units))
        attendu = 100.0 if unit == "%" else (ann.get("valeur") if ann else None)
        label = "%" if unit == "%" else "points"
        if attendu is None:
            ct = {"statut": "non_verifiable",
                  "message": f"Total des poids : {_fmt_total(total)} points. Le règlement n'annonce pas de total "
                             "de points qu'Adjugo ait retrouvé : comparez avec le règlement."}
        elif abs(total - attendu) < 0.01:
            ct = {"statut": "ok", "message": f"Les poids retrouvés font bien {_fmt_total(total)} {label} au total."}
        else:
            ct = {"statut": "ecart",
                  "message": f"Les poids retrouvés font {_fmt_total(total)} {label} au lieu de {_fmt_total(attendu)} "
                             f"{label} : un critère manque peut-être, vérifiez dans le règlement."}
        ct.update({"total": total, "unite": unit, "attendu": attendu})
    if pending and ct.get("statut") in ("ok", "non_verifiable"):
        ct["message"] += f" {len(pending)} ligne(s) à vérifier ne sont pas comptées."
    g["controle_total"] = ct
    for ln in lines:
        ln.pop("_v", None)
        ln.pop("_u", None)
    return g


# ── Construction ─────────────────────────────────────────────────────────────────────

def build_grille(details: dict, text: str, pieces: Optional[list] = None) -> dict:
    """Grille « Comment vous serez noté » + ce que le dossier impose, à partir des critères
    PROPOSÉS par l'IA (details.criteres_attribution) et du texte INTÉGRAL du dossier.
    pieces : ce qui a été lu, pièce par pièce (meta d'extract_dce_text), sinon déduit du texte."""
    details = details if isinstance(details, dict) else {}
    text = text or ""
    P = _pieces(text)
    rc = [p for p in P if p.type == dp.REGLEMENT]
    scope_rc = rc or P
    scope_limits = ([p for p in P if p.type in (dp.REGLEMENT, dp.CADRE)]
                    or [p for p in P if p.type not in (dp.CCTP, dp.CCAP, dp.BORDEREAU)] or P)
    scope_visite = [p for p in P if p.type in (dp.REGLEMENT, dp.CADRE, dp.AUTRE, dp.ACTE_ENGAGEMENT)] or P
    scope_cadre = [p for p in P if p.type in (dp.REGLEMENT, dp.CADRE, dp.AUTRE)] or P

    lines, seen = [], set()
    for i, (name, pond, ex) in enumerate(_raw_criteres(details.get("criteres_attribution"))[:MAX_CRITERES]):
        key = _fold(name)
        if key in seen:
            continue
        seen.add(key)
        lines.append(_line(i, name, pond, ex, text, P, scope_rc))
    # Ordre du règlement (position de la phrase) ; lignes non retrouvées à la suite.
    lines.sort(key=lambda ln: (ln["_pos"] is None, ln["_pos"] or (0, 0)))
    poids_texte = _poids_dans_le_texte(scope_rc, lines)
    for ln in lines:
        ln.pop("_pos", None)

    if pieces:
        lus = [{"nom": str(m.get("nom") or "")[:200], "type": m.get("type") or dp.AUTRE,
                "libelle": m.get("libelle") or dp.label(m.get("type")),
                "lu_en_entier": bool(m.get("lu_en_entier"))} for m in pieces if isinstance(m, dict)][:30]
    else:
        lus = [{"nom": p.nom, "type": p.type, "libelle": p.libelle, "lu_en_entier": None} for p in P][:30]

    cadre = _cadre(P, scope_cadre)
    g = {
        "version": VERSION,
        "criteres": lines,
        "ordre": _ordre(scope_rc),
        "total_annonce": _total_annonce(scope_rc),
        "poids_dans_le_texte": poids_texte,
        "lecture": {"pieces": lus,
                    "reglement": any(x["type"] == dp.REGLEMENT for x in lus),
                    "cadre": any(x["type"] == dp.CADRE for x in lus)},
        "contraintes": {
            "cadre": cadre,
            "fichier_impose": bool(cadre.get("obligatoire")),
            "message_fichier": MSG_FICHIER_IMPOSE if cadre.get("obligatoire") else "",
            "limites": _limites(scope_limits),
            "visite": _visite(scope_visite),
        },
    }
    return refresh(g)


# ── Choix de l'utilisateur (confirmer / écarter une ligne) ───────────────────────────

CHOIX = ("confirme", "ecarte", "annule")


def apply_choice(grille: dict, critere_id: str, choix: str, poids: str = "", when: str = "") -> dict:
    """Renvoie une NOUVELLE grille où la ligne `critere_id` porte le choix de l'utilisateur :
    • « confirme » : il a lu la ligne dans le règlement ; elle entre dans le plan. Il peut
      donner le poids tel qu'il l'a lu (« 60 % », « 40 points ») ;
    • « ecarte » : la ligne sort du plan (ex. un sous-critère pris pour un critère) ;
    • « annule » : retour à l'état lu dans le dossier.
    Lève ValueError (message affichable) si la ligne ou le poids est invalide."""
    if not isinstance(grille, dict) or not isinstance(grille.get("criteres"), list):
        raise ValueError("Aucune grille de notation pour ce marché : ré-analysez le dossier.")
    if choix not in CHOIX:
        raise ValueError("Choix inconnu.")
    g = copy.deepcopy(grille)
    ln = next((x for x in g["criteres"] if isinstance(x, dict) and x.get("id") == critere_id), None)
    if ln is None:
        raise ValueError("Ce critère n'existe plus : rechargez la page.")
    if choix == "annule":
        ln.pop("choix_utilisateur", None)
    elif choix == "ecarte":
        ln["choix_utilisateur"] = {"choix": "ecarte", "le": when}
    else:
        p = _flat(poids)[:40]
        if p:
            w = parse_weight(p)
            if not w or w.get("unite") is None or not (0 < w["valeur"] <= 1000):
                raise ValueError("Indiquez le poids tel qu'il est écrit dans le règlement, par exemple "
                                 "« 60 % » ou « 40 points », ou laissez vide.")
        ln["choix_utilisateur"] = {"choix": "confirme", "poids": p, "le": when}
    return refresh(g)


def carry_over(previous: Optional[dict], fresh: Optional[dict]) -> Optional[dict]:
    """Ré-analyse : les choix de l'utilisateur sur une ligne du même nom sont repris (une
    confirmation seulement si la ligne est encore à vérifier)."""
    if not isinstance(fresh, dict) or not isinstance(previous, dict):
        return fresh
    old = {_fold(x.get("critere")): x.get("choix_utilisateur") for x in (previous.get("criteres") or [])
           if isinstance(x, dict) and x.get("choix_utilisateur")}
    if not old:
        return fresh
    for ln in fresh.get("criteres") or []:
        ch = old.get(_fold(ln.get("critere")))
        if not ch:
            continue
        if ch.get("choix") == "ecarte" or (ch.get("choix") == "confirme" and ln.get("statut") == A_VERIFIER):
            ln["choix_utilisateur"] = dict(ch)
    return refresh(fresh)


# ── Lectures ─────────────────────────────────────────────────────────────────────────

def criteres_plan(grille: Optional[dict]) -> list:
    """Lignes qui entrent dans le plan du dossier de présentation : retrouvées dans le
    règlement, ou confirmées par l'utilisateur ; jamais une ligne « à vérifier » ou écartée."""
    if not isinstance(grille, dict):
        return []
    out = []
    for ln in grille.get("criteres") or []:
        if isinstance(ln, dict) and _in_plan(ln):
            out.append({"critere": ln.get("critere", ""), "poids": ln.get("poids_retenu", ""),
                        "source": ln.get("poids_source", "")})
    return out


def plan_text(grille: Optional[dict]) -> str:
    """Les critères du plan en une ligne (pour une consigne de rédaction) ; '' si aucun."""
    lines = criteres_plan(grille)
    if not lines:
        return ""
    body = " ; ".join(x["critere"] + (f" ({x['poids']})" if x["poids"] else "") for x in lines)
    pond = ((grille or {}).get("ponderation") or {}).get("statut")
    if pond == "non_ponderes":
        indique = ((grille or {}).get("ordre") or {}).get("indique") is True
        return ("critères non pondérés, dans l'ordre du règlement : " if indique
                else "critères non pondérés, sans ordre indiqué : ") + body
    return body


def public_grille(grille: Optional[dict]) -> Optional[dict]:
    """Vue LECTURE SEULE pour les partenaires du groupement : les critères tels qu'écrits
    dans le règlement (phrase publique du dossier de l'acheteur), la pondération, le
    contrôle du total et ce que le dossier impose. Ni noms de fichiers, ni dates, ni rien de
    chiffré (prix, montants) : la grille n'en contient pas."""
    if not isinstance(grille, dict) or not isinstance(grille.get("criteres"), list):
        return None
    cr = []
    for ln in grille["criteres"]:
        if not isinstance(ln, dict):
            continue
        cr.append({"critere": str(ln.get("critere") or "")[:160],
                   "poids": str(ln.get("poids_retenu") or "")[:40] if ln.get("dans_le_plan") else "",
                   "phrase": str(ln.get("phrase") or "")[:PHRASE_MAX + 100],
                   "statut": ln.get("statut") if ln.get("statut") in (RETROUVE, A_VERIFIER) else A_VERIFIER,
                   "dans_le_plan": bool(ln.get("dans_le_plan")),
                   "confirme": (ln.get("choix_utilisateur") or {}).get("choix") == "confirme",
                   "ecarte": (ln.get("choix_utilisateur") or {}).get("choix") == "ecarte"})
    c = grille.get("contraintes") if isinstance(grille.get("contraintes"), dict) else {}
    cadre = c.get("cadre") if isinstance(c.get("cadre"), dict) else {}
    ob = cadre.get("obligatoire") if isinstance(cadre.get("obligatoire"), dict) else None
    vis = c.get("visite") if isinstance(c.get("visite"), dict) else None
    ordre = grille.get("ordre") if isinstance(grille.get("ordre"), dict) else {}
    ct = grille.get("controle_total") if isinstance(grille.get("controle_total"), dict) else {}
    pond = grille.get("ponderation") if isinstance(grille.get("ponderation"), dict) else {}
    return {
        "criteres": cr,
        "ponderation": {"statut": pond.get("statut", ""), "message": pond.get("message", "")},
        "ordre": {"indique": ordre.get("indique"), "phrase": ordre.get("phrase", "")},
        "controle_total": {"statut": ct.get("statut", ""), "message": ct.get("message", "")},
        "contraintes": {
            "cadre_fourni": bool(cadre.get("fourni")),
            "cadre_mentionne": bool(cadre.get("mentionne")),
            "fichier_impose": bool(c.get("fichier_impose")),
            "message_fichier": c.get("message_fichier", "") if c.get("fichier_impose") else "",
            "phrase_obligation": ob.get("phrase", "") if ob else "",
            "limites": [{"type": x.get("type"), "texte": x.get("texte", ""), "phrase": x.get("phrase", "")}
                        for x in (c.get("limites") or []) if isinstance(x, dict)][:20],
            "visite": {"phrase": vis.get("phrase", "")} if vis else None,
        },
    }
