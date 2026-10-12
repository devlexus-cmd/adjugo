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
import bisect
import copy
import functools
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
# Côté partenaire : c'est le chef de file qui assemble et recopie le texte commun.
MSG_FICHIER_IMPOSE_PARTENAIRE = ("Ce marché impose son propre fichier de réponse : le chef de file y recopiera "
                                 "le texte commun.")
MSG_NON_PONDERES = "Critères non pondérés, sans ordre indiqué."
MSG_NON_PONDERES_ORDRE = "Critères non pondérés, classés dans l'ordre que donne le règlement."
MSG_CRITERE_UNIQUE = "Un seul critère retrouvé, sans poids indiqué."
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
    __slots__ = ("nom", "type", "libelle", "flat", "low", "idx", "breaks", "cuts")

    def __init__(self, idx, nom, kind, texte):
        self.idx, self.nom, self.type = idx, nom or "", kind
        self.libelle = dp.label(kind)
        self.flat, self.breaks = _flat_breaks(texte)
        self.low = _fold(self.flat)
        # Fins de phrase (blanc qui suit . ; ! ?), calculées une fois : recherche par bisection.
        self.cuts = [m.start() for m in _BOUND.finditer(self.flat)]

    def sentence(self, a: int, b: int) -> tuple:
        """Même résultat que _sentence_bounds(self.flat, a, b), sans relire le texte."""
        i = bisect.bisect_left(self.cuts, a)
        j = bisect.bisect_left(self.cuts, b)
        return (self.cuts[i - 1] + 1 if i else 0), (self.cuts[j] if j < len(self.cuts) else len(self.flat))

    def line_phrase(self, a: int, b: int) -> tuple:
        """(début, phrase) de la ligne ∩ phrase qui contient [a, b] (repli : la phrase)."""
        s, e = self.sentence(a, b)
        br = self.breaks
        i = bisect.bisect_right(br, a)
        ls = br[i - 1] if i else 0
        j = bisect.bisect_left(br, b)
        le = br[j] if j < len(br) else len(self.flat)
        inside = bisect.bisect_right(br, a) < bisect.bisect_left(br, b)     # un retour à la ligne dans ]a, b[
        if not inside:
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


@functools.lru_cache(maxsize=512)
def _stem_rx(stem: str):
    return re.compile(r"(?<![a-z0-9])" + re.escape(stem))


def _stem_at(low: str, stem: str, start: int = 0) -> int:
    m = _stem_rx(stem).search(low, max(0, start))
    return m.start() if m else -1


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


def _in_zone(p: _Piece, pos: int) -> bool:
    return any(z0 <= pos < z1 for z0, z1 in _crit_zones(p))


# ── Rattachement d'un poids à SON critère (sans IA) ─────────────────────────────────
# Un poids n'est attribué à un critère que s'il lui est RATTACHÉ dans le texte : le premier
# poids écrit après son nom (« Prix 40 % ; Valeur technique 60 % »), ou le dernier écrit juste
# avant (« 60 % pour la valeur technique et 40 % pour le prix ») — le sens est choisi pour toute
# la phrase —, sans le nom d'un autre critère entre les deux, sans fin de phrase ni « ; », et
# sans passer à la ligne suivante si autre chose qu'une ponctuation les sépare (« Valeur
# technique » puis, à la ligne, « Méthodologie : 40 % » : le poids d'un sous-critère). Un poids
# présent ailleurs dans la phrase, même de même valeur, n'est jamais retenu.

_GAP_APRES = 60          # « Valeur technique de l'offre, appréciée au vu du mémoire : 60 % »
_GAP_AVANT = 30          # « 60 % pour la valeur technique »
_GAP_PONCT = re.compile(r"^[\s:|=()\[\]\-–—,./]*$")
_GAP_STOP = re.compile(r";|[.!?](?:\s|$)")


def _name_spans(p: _Piece, w0: int, w1: int, crit_stems: list) -> list:
    """Occurrences des noms des critères dans [w0, w1) : [(début, fin, index du critère ou None
    si l'occurrence est ambiguë)], triées, sans chevauchement. Le nom s'étend sur les mots du
    critère qui se suivent (« prix des prestations », « délai d'exécution ») ; à une même
    position, le critère dont le plus de mots se suivent l'emporte (« valeur technique » contre
    « valeur environnementale ») ; à égalité, l'occurrence est ambiguë."""
    def _word_end(e):
        while e < w1 and p.low[e].isalnum():
            e += 1
        return e
    found = {}
    for j, stems in enumerate(crit_stems):
        if not stems:
            continue
        pos = w0
        while True:
            i = _stem_at(p.low, stems[0], pos)
            if i < 0 or i >= w1:
                break
            pos = i + 1
            e, hits = _word_end(i + len(stems[0])), 1
            for s in stems[1:]:
                k = _stem_at(p.low, s, e)
                if 0 <= k <= e + 14 and k + len(s) <= w1:
                    e, hits = _word_end(k + len(s)), hits + 1
            if hits * 2 < len(stems):
                continue
            found.setdefault(i, []).append((hits, e, j))
    spans = []
    for i in sorted(found):
        cands = sorted(found[i], key=lambda c: (c[0], c[1]), reverse=True)
        hits, e, j = cands[0]
        if len(cands) > 1 and cands[1][0] == hits:
            j = None                              # « Valeur » seul : technique ou environnementale ?
        if spans and i < spans[-1][1]:
            continue                              # déjà dans le nom précédent
        spans.append((i, e, j))
    return spans


def _gap_cost(p: _Piece, a: int, b: int, max_len: int):
    """Coût de l'écart [a, b) entre un nom et un poids (None : pas de rattachement possible).
    Passer à la ligne coûte cher : dans un tableau, un nom et le poids de la ligne suivante
    ne vont pas ensemble, sauf cellule seule sur sa ligne (« Valeur technique » / « 60 % »)."""
    if b < a or b - a > max_len:
        return None
    gap = p.flat[a:b]
    if _GAP_STOP.search(gap):
        return None
    crosses = bisect.bisect_left(p.breaks, a) < bisect.bisect_left(p.breaks, b)    # un retour à la ligne dans [a, b)
    if crosses and not _GAP_PONCT.match(gap):
        return None
    return (b - a) + (20 if crosses else 0)


def _attribute(p: _Piece, w0: int, w1: int, crit_stems: list) -> dict:
    """{index du critère: (valeur, unité, texte tel qu'écrit, début, fin)} pour la fenêtre
    [w0, w1) de la pièce : chaque poids rattaché à SON critère (voir plus haut). Un critère dont
    le rattachement est ambigu n'a pas de poids."""
    names = _name_spans(p, w0, w1, crit_stems)
    if not names:
        return {}
    weights = [(v, u, raw, a + w0, b + w0) for v, u, raw, a, b in _weights_in(p.flat[w0:w1])]
    weights = [w for w in weights if not any(s <= w[3] < e for s, e, _j in names)]
    if not weights:
        return {}
    after, before = {}, {}
    for k, (s, e, _j) in enumerate(names):
        nxt = names[k + 1][0] if k + 1 < len(names) else w1
        w = next((w for w in weights if e <= w[3] < nxt), None)
        cost = _gap_cost(p, e, w[3], _GAP_APRES) if w else None
        if cost is not None:
            after[k] = (w, cost)
        prev = names[k - 1][1] if k else w0
        w = next((w for w in reversed(weights) if prev <= w[3] and w[4] <= s), None)
        cost = _gap_cost(p, w[4], s, _GAP_AVANT) if w else None
        if cost is not None:
            before[k] = (w, cost)

    def _score(d):
        return (len(d), -sum(g for _w, g in d.values()))
    if not after and not before:
        return {}
    if _score(after) == _score(before) and {k: w for k, (w, _g) in after.items()} != {k: w for k, (w, _g) in before.items()}:
        return {}                                  # aucun sens ne l'emporte : rien n'est rattaché
    chosen = after if _score(after) >= _score(before) else before
    out = {}
    for k, (w, _g) in chosen.items():
        j = names[k][2]
        if j is None:
            continue
        if j in out and out[j] is not None and out[j][:2] != w[:2]:
            out[j] = None                          # même critère, deux poids différents
        elif j not in out:
            out[j] = w
    return {j: w for j, w in out.items() if w is not None}


def _same_weight(w, claimed: dict) -> bool:
    return bool(w) and abs(w[0] - claimed["valeur"]) < 0.001 and claimed.get("unite") in (None, w[1])


_CRIT_WORD = re.compile(r"crit[e]res?|ponder|jugement des offres|notation|bareme|attribution")


def _window(p: _Piece, a: int, b: int, next_line: bool = False):
    """Fenêtre d'analyse autour de [a, b) : la phrase qui le contient, bornée aux lignes qu'il
    occupe (et, si next_line, à la ligne suivante : un tableau mis en page coupe souvent
    « Valeur technique » / « 60 % »)."""
    s, e = p.sentence(a, b)
    br = p.breaks
    i = bisect.bisect_right(br, a)
    ls = br[i - 1] if i else 0
    j = bisect.bisect_left(br, b)
    if next_line and j < len(br):
        j += 1
    le = br[j] if j < len(br) else len(p.flat)
    return max(s, ls), min(e, le)


def _recover(j: int, crit_stems: list, claimed: Optional[dict], scope: list):
    """Recherche SANS IA de la phrase d'un critère que l'IA n'a pas su recopier, dans la seule
    zone « critères de jugement / d'attribution » du règlement (« prix » ou « 60 % »
    apparaissent partout ailleurs : acomptes, retenues, pénalités) :
    • poids annoncé : le nom ET le même poids, rattaché à ce critère (voir _attribute) ;
    • sans poids : le nom."""
    stems = crit_stems[j]
    if not stems:
        return None
    for p in scope:
        zones = _crit_zones(p)
        if not zones:
            continue
        pos = 0
        while True:
            i = _stem_at(p.low, stems[0], pos)
            if i < 0:
                break
            pos = i + 1
            if not any(z0 <= i < z1 for z0, z1 in zones):
                continue
            if claimed is not None:
                w0, w1 = _window(p, i, i + len(stems[0]), next_line=True)
                w = _attribute(p, w0, w1, crit_stems).get(j)
                if not _same_weight(w, claimed):
                    continue
                a, b = min(i, w[3]), max(i + len(stems[0]), w[4])
            else:
                a, b = i, i + len(stems[0])
            s, phrase = p.line_phrase(a, b)
            if len(phrase) >= 4 and _names_ok(_fold(phrase), stems):
                return p, s, phrase, (w if claimed is not None else None)
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


def _line(i, j, name, pond, ex, text, scope_crit, scope_rc, crit_stems) -> dict:
    """Ligne du critère n° j (index dans crit_stems). La phrase de l'IA n'est retenue que si elle
    est retrouvée mot pour mot dans le règlement (ou le cadre de réponse) et parle de ce
    critère ; un poids n'est affiché que s'il y est écrit ET rattaché à ce critère."""
    claimed = parse_weight(pond) if pond else None
    if claimed is not None and claimed.get("valeur", 0) <= 0:
        claimed = None
    stems = crit_stems[j]
    phrase, piece, pos, poids, unite, valeur = "", None, None, "", None, None

    verified = citation_guard(text, ex) if ex else ""
    vp, vpos, vorig = _locate(verified, scope_crit) if verified else (None, None, "")
    if vorig and not _names_ok(_fold(vorig), stems):
        vp, vpos, vorig = None, None, ""            # la phrase ne parle pas de ce critère

    if claimed is not None:
        w = None
        if vorig:
            w0, w1 = _window(vp, vpos, vpos + len(vorig))
            # Hors du règlement et du cadre de réponse (dossier en un seul fichier non reconnu), un
            # poids n'est retenu que dans la zone des critères ou dans une phrase qui parle de
            # notation (« le prix est payé par acompte à hauteur de 60 % » n'est pas un poids).
            if (vp.type in (dp.REGLEMENT, dp.CADRE) or _in_zone(vp, vpos)
                    or _CRIT_WORD.search(vp.low[w0:w1])):
                w = _attribute(vp, w0, w1, crit_stems).get(j)
        if _same_weight(w, claimed):
            phrase, piece, pos = vorig, vp, vpos
            valeur, unite, poids = w[0], w[1], w[2]
        else:
            rec = _recover(j, crit_stems, claimed, scope_rc)
            if rec:
                piece, pos, phrase, w = rec
                valeur, unite, poids = w[0], w[1], w[2]
            else:
                phrase, piece, pos = vorig, vp, vpos   # vraie phrase, mais sans le poids annoncé
    else:
        # Aucun poids annoncé : on n'en ajoute jamais un, même lu à côté du nom (ce peut être
        # celui d'un sous-critère). Si le règlement en écrit, la pondération reste « à vérifier ».
        if vorig:
            phrase, piece, pos = vorig, vp, vpos
        else:
            rec = _recover(j, crit_stems, None, scope_rc)
            if rec:
                piece, pos, phrase, _w = rec

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
# « Les offres seront classées par ordre décroissant de la note obtenue au regard des critères » :
# c'est le CLASSEMENT DES OFFRES, pas un ordre d'importance entre les critères.
_ORDER_OFFRES_AVANT = re.compile(r"(?:offres?|candidats?|notes?)\b[^.;]{0,30}class(?:ee|es|ees)?\s*$|classement (?:des|de l')\s?(?:offres?|candidats?)[^.;]{0,30}$")
_ORDER_OFFRES_APRES = re.compile(r"\s*(?:de (?:la|leur|leurs|sa) |des |du )(?:notes?|total|totaux|offres?|points|scores?|resultats?|moyennes?)\b")
_TOTAL_RE = (
    re.compile(r"sur un total de (\d{1,4}) ?(?:points?|pts?)\b"),
    re.compile(r"\bnote (?:globale|finale|totale|maximale)\b[^.;]{0,30}?\b(?:sur|de|:) ?(\d{1,4})\b"),
    re.compile(r"\b(\d{1,4}) ?points? au total\b"),
    re.compile(r"\btotal (?:de|des notes ?:?|:) ?(\d{1,4}) ?(?:points?|pts?)\b"),
    # « Les offres seront notées sur 100 points » (jamais « chaque critère est noté sur 20 »).
    re.compile(r"\boffres? (?:sont |seront )?notees? sur (\d{1,4}) ?(?:points?|pts?)\b"),
)


def _phrase_at(p: _Piece, a: int, b: int) -> str:
    """Phrase source d'un repérage : la ligne ∩ la phrase qui le contient (≤ PHRASE_MAX)."""
    return p.line_phrase(a, b)[1]


def _ordre(scope: list) -> dict:
    for rx, indique in ((_ORDER_NEG, False), (_ORDER_POS, True)):
        for p in scope:
            for m in rx.finditer(p.low):
                if indique and (_ORDER_OFFRES_AVANT.search(p.low[max(0, m.start() - 60):m.start()])
                                or _ORDER_OFFRES_APRES.match(p.low, m.end())):
                    continue
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
_VISITE_NEG_AVANT = re.compile(r"\b(?:pas|non|aucune?|sans|ni)\b(?: d[e'] ?| la | une )?\s*$"
                               r"|\b(?:pas|aucune?|non)\s+(?:prevue?s?|organisee?s?|exigee?s?|imposee?s?|requise?s?|programmee?s?)"
                               r"\s*(?:d[e'] ?|une |la )?\s*$")
# « Visite obligatoire : non », « Visite obligatoire : sans objet », « … : néant ».
_VISITE_NEG_APRES = re.compile(r"\s*(?:[:\-–=]\s*)?(?:non\b|sans objet|neant\b|aucune?\b|pas\b|n'est pas|ne sera pas|n'a pas lieu)")
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
    s, e = p.sentence(a, b)
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


# Limite qui porte sur une PARTIE du dossier (un CV, une fiche référence, une question) et non
# sur le mémoire entier : gardée (le compteur de la vague 2 en aura besoin), dite comme telle.
_OBJETS = (
    ("cv", r"\bcv\b|curriculum"),
    ("reference", r"\breferences?\b"),
    ("question", r"\bquestions?\b"),
    ("fiche", r"\bfiches?\b"),
    ("synthese", r"\bsynthese\b|\bresume\b"),
    ("lettre", r"\blettre\b"),
    ("annexe", r"\bchaque annexe\b"),
)
_OBJET_GLOBAL = re.compile(r"memoire|offre technique|note (?:methodologique|technique)|dossier de presentation"
                           r"|cadre (?:de |du )?(?:la )?reponse|\breponse technique|\bdocument\b|\bproposition\b")
_OBJET_APRES = re.compile(r"[^.;]{0,25}?\b(?:par|pour chaque|chacune?)\b\s*(cv|curriculum|references?|questions?|fiches?)?")


def _objet_limite(p: _Piece, a: int) -> str:
    """'' (le mémoire, le cadre ou l'offre) ou la partie visée : « cv », « reference »,
    « question » (« question_chaque » pour « chaque question »), « fiche »…"""
    s, _e = p.sentence(a, a + 1)
    before = p.low[max(s, a - 160):a]
    best, best_pos = "", -1
    for key, rx in _OBJETS:
        for m in re.finditer(rx, before):
            # « Le mémoire, CV compris, … », « hors annexes » : une précision sur le mémoire.
            if re.match(r"\s*(?:\w+\s+)?(?:compris|comprises?|inclus|incluses?|exclus|exclues?)\b", before[m.end():]) \
                    or re.search(r"\b(?:hors|sans|y compris|avec|dont)\s+(?:les |le |la |des |l')?$", before[:m.start()]):
                continue
            if m.start() > best_pos:
                best, best_pos = key, m.start()
    g = None
    for m in _OBJET_GLOBAL.finditer(before):
        g = m.start()
    m2 = _OBJET_APRES.match(p.low, a)
    if m2 and m2.group(1):
        w = m2.group(1)
        best = "cv" if w in ("cv", "curriculum") else w.rstrip("s")
    elif best and g is not None and g > best_pos:
        best = ""                                 # « … des CV, le mémoire ne dépassera pas 10 pages »
    if best == "question" and re.search(r"chaque question|par question", p.low[max(s, a - 160):a + 40]):
        best = "question_chaque"
    return best


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
        out.append({"type": kind, "valeur": val, "texte": texte, "phrase": ph, "source": _source_label(p),
                    "objet": _objet_limite(p, a)})

    bounds = {k: (lo, hi) for k, _rx, (lo, hi) in _UNITS}
    for p in scope:
        for kind, unit_rx, (lo, hi) in _UNITS:
            for m in re.finditer(_NUM + r" ?" + unit_rx, p.low):
                try:
                    val = _int(m.group(1))
                except ValueError:
                    continue
                s, e = p.sentence(m.start(), m.end())
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
            before = p.low[max(0, m.start() - 40):m.start()]
            if (_VISITE_NEG.search(mid) or _VISITE_NEG_AVANT.search(before) or "facultati" in low
                    or _VISITE_NEG_APRES.match(p.low, m.end())):
                continue
            if _VISITE_HORS.search(p.low[m.start():m.end() + 30]):
                continue
            return {"obligatoire": True, "phrase": ph, "source": _source_label(p)}
    return None


def _sentences_with(rx, scope: list):
    for p in scope:
        for m in rx.finditer(p.low):
            yield p, m, _phrase_at(p, m.start(), m.end())


# Négation qui porte sur le cadre lui-même (dans la proposition qui le cite) : « aucun cadre de
# réponse n'est imposé », « n'est pas tenu d'utiliser un cadre », « sans cadre imposé ».
_CADRE_NEG = re.compile(
    r"\baucune?\b[^.;:]{0,25}\b(?:cadre|trame|questionnaire)|\b(?:pas|non) tenue?s?\b"
    r"|\bsans (?:utiliser |recourir a )?(?:le |un |de |d')?(?:cadre|trame)"
    r"|n'(?:est|sont) (?:pas )?(?:imposee?s?|obligatoires?|exigee?s?|requise?s?|fournie?s?)\b"
    r"|\bpas (?:de|d'un|d'une) (?:cadre|trame)|n'impose (?:pas|aucun)|\blibres? (?:de|d')|facultati")
_PROPOSITION = re.compile(r"\s*(?:[;:]|\bmais\b)\s*")


def _obligation(low: str, m_start: int) -> bool:
    """La phrase rend-elle le cadre obligatoire ? Seulement la proposition qui le cite (et, après
    « Cadre de réponse : », celle qui suit) ; jamais si cette proposition le dément, et jamais à
    cause d'un « obligatoirement » qui porte sur autre chose plus loin dans la phrase."""
    props, start = [], 0
    for sep in _PROPOSITION.finditer(low):
        props.append((start, sep.start(), sep.group(0).strip()))
        start = sep.end()
    props.append((start, len(low), ""))
    k = max(i for i, (a, _b, _s) in enumerate(props) if a <= m_start)
    a, b, sep = props[k]
    prop = low[a:b]
    if _CADRE_NEG.search(prop) or _FACULT.search(prop):
        return False
    if _OBLIG.search(prop):
        return True
    label = len(prop.split()) <= 6 and not re.search(r"\b(?:est|sont|sera|seront|doit|doivent|devra|devront|peut|pourra)\b", prop)
    if sep == ":" and label and k + 1 < len(props):     # « Cadre de réponse technique : obligatoire »
        nxt = low[props[k + 1][0]:props[k + 1][1]]
        return bool(_OBLIG.search(nxt)) and not (_CADRE_NEG.search(nxt) or _FACULT.search(nxt))
    return False


def _cadre(pieces: list, scope: list) -> dict:
    cadres = [p for p in pieces if p.type == dp.CADRE]
    mention, oblig = None, None
    for p, m, ph in _sentences_with(_CADRE_MENTION, scope):
        low = _fold(ph)
        if mention is None:
            mention = (ph, _source_label(p))
        if oblig is None:
            mm = _CADRE_MENTION.search(low)
            if mm and _obligation(low, mm.start()):
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


def _pond_message(g: dict, pond: str, partenaire: bool = False) -> str:
    """Phrase d'état de la pondération, pour le chef de file ou (partenaire=True) pour les
    membres du groupement, qui lisent la grille sans pouvoir la modifier."""
    cpt = g.get("compteurs") or {}
    n_av, n_sp = int(cpt.get("a_verifier") or 0), int(cpt.get("sans_poids") or 0)
    if pond == "aucun":
        if not cpt.get("criteres"):
            return "Aucun critère de jugement n'a été retrouvé : lisez le règlement de la consultation."
        return ("Aucun critère n'est retenu : le chef de file les a tous retirés." if partenaire
                else "Aucun critère n'est retenu : vous les avez tous retirés.")
    if pond == "non_ponderes":
        if int(cpt.get("dans_le_plan") or 0) == 1:
            return MSG_CRITERE_UNIQUE          # ni pluriel ni « ordre » pour un seul critère
        return MSG_NON_PONDERES_ORDRE if (g.get("ordre") or {}).get("indique") is True else MSG_NON_PONDERES
    if pond != "incomplet":
        return ""
    parts = []
    if n_av:
        un = n_av == 1
        tete = "1 critère est à vérifier dans le règlement" if un else f"{n_av} critères sont à vérifier dans le règlement"
        if partenaire:
            parts.append(tete + (" : le chef de file doit le confirmer." if un else " : le chef de file doit les confirmer."))
        else:
            parts.append(tete + (" : il n'entre dans votre plan qu'une fois confirmé." if un
                                 else " : ils n'entrent dans votre plan qu'une fois confirmés."))
    if n_sp:
        parts.append("Le poids d'un critère n'a pas été retrouvé dans sa phrase : vérifiez-le dans le règlement."
                     if n_sp == 1 else
                     f"Le poids de {n_sp} critères n'a pas été retrouvé dans leur phrase : vérifiez-les dans le règlement.")
    return " ".join(parts)


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
                      "sans_poids": len(plan) - len(weighted),
                      "ecartes": sum(1 for ln in lines if (ln.get("choix_utilisateur") or {}).get("choix") == "ecarte")}

    ordre = g.get("ordre") or {}
    if not lines or (not plan and not pending):
        pond = "aucun"
    elif plan and len(weighted) == len(plan) and not pending:
        pond = "ponderes"
    elif not weighted and not pending and not g.get("poids_dans_le_texte"):
        pond = "non_ponderes"
    else:
        pond = "incomplet"
    g["ponderation"] = {"statut": pond, "message": _pond_message(g, pond)}

    units = {ln["_u"] for ln in weighted}
    total = sum(ln["_v"] for ln in weighted) if weighted else 0.0
    ann = g.get("total_annonce") or None
    if not weighted:
        ct = {"statut": "sans_objet", "message": ""}
    elif len(units) > 1 or None in units:
        ct = {"statut": "ecart", "message": "Les poids ne sont pas exprimés dans la même unité : vérifiez dans le règlement."}
    elif len(weighted) < len(plan):
        n = len(plan) - len(weighted)
        ct = {"statut": "incomplet",
              "message": "Total non vérifiable : " + ("un critère n'a pas de poids retrouvé." if n == 1
                                                      else f"{n} critères n'ont pas de poids retrouvé.")}
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
    if pending and ct.get("statut") == "ok":
        ct["message"] = ct["message"][:-1] + (", sans la ligne à vérifier." if len(pending) == 1
                                              else f", sans les {len(pending)} lignes à vérifier.")
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

    # Phrases des critères : dans le règlement (et le cadre de réponse, qui reprend souvent la
    # grille) quand il est reconnu ; sinon dans tout le texte.
    scope_crit = [p for p in P if p.type in (dp.REGLEMENT, dp.CADRE)] if rc else P
    raws, seen = [], set()
    for i, (name, pond, ex) in enumerate(_raw_criteres(details.get("criteres_attribution"))[:MAX_CRITERES]):
        key = _fold(name)
        if key in seen:
            continue
        seen.add(key)
        raws.append((i, name, pond, ex))
    crit_stems = [_stems(name) for _i, name, _p, _e in raws]
    lines = [_line(i, j, name, pond, ex, text, scope_crit, scope_rc, crit_stems)
             for j, (i, name, pond, ex) in enumerate(raws)]
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
        # Texte sans fichier (annonce seule, texte collé) : rien à lister pièce par pièce.
        lus = []
    kinds = [x["type"] for x in lus] if lus else [p.type for p in P]

    cadre = _cadre(P, scope_cadre)
    g = {
        "version": VERSION,
        "criteres": lines,
        "ordre": _ordre(scope_rc),
        "total_annonce": _total_annonce(scope_rc),
        "poids_dans_le_texte": poids_texte,
        "lecture": {"pieces": lus,
                    "reglement": any(k == dp.REGLEMENT for k in kinds),
                    "cadre": any(k == dp.CADRE for k in kinds)},
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
    confirmation seulement si la ligne est encore à vérifier, ou si elle porte le poids que
    l'utilisateur a lu et que la ligne retrouvée n'a pas)."""
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
        # Confirmation reprise sur une ligne encore à vérifier, ou sur une ligne retrouvée SANS
        # poids quand l'utilisateur avait saisi le poids lu (sinon sa saisie se perdrait).
        if (ch.get("choix") == "ecarte"
                or (ch.get("choix") == "confirme" and ln.get("statut") == A_VERIFIER)
                or (ch.get("choix") == "confirme" and ch.get("poids") and not ln.get("poids"))):
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
        if len(lines) == 1:
            return "un seul critère retrouvé, sans poids indiqué : " + body
        indique = ((grille or {}).get("ordre") or {}).get("indique") is True
        return ("critères non pondérés, dans l'ordre du règlement : " if indique
                else "critères non pondérés, sans ordre indiqué : ") + body
    return body


def limites_texte(text: str, kind: str = dp.CADRE) -> list:
    """Limites (pages, mots, caractères, lignes, police) écrites dans UN texte (une question du
    cadre de réponse, par exemple « 2 pages maximum »), repérées SANS IA avec les mêmes motifs que
    la grille. [] si rien (ou texte vide). Ne lève jamais."""
    try:
        t = str(text or "")
        if len(t.strip()) < 6:
            return []
        return _limites([_Piece(0, "", kind, t)])
    except Exception:          # noqa: BLE001 — repérage facultatif
        return []


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
                   # Poids saisi par le chef de file en confirmant la ligne (pas lu par Adjugo) :
                   # le partenaire le voit dit comme tel.
                   "poids_saisi": bool(ln.get("dans_le_plan")) and ln.get("poids_source") == "utilisateur",
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
        "ponderation": {"statut": pond.get("statut", ""),
                        "message": _pond_message(grille, pond.get("statut", ""), partenaire=True)},
        "ordre": {"indique": ordre.get("indique"), "phrase": ordre.get("phrase", "")},
        "controle_total": {"statut": ct.get("statut", ""), "message": ct.get("message", "")},
        "contraintes": {
            "cadre_fourni": bool(cadre.get("fourni")),
            "cadre_mentionne": bool(cadre.get("mentionne")),
            "fichier_impose": bool(c.get("fichier_impose")),
            "message_fichier": MSG_FICHIER_IMPOSE_PARTENAIRE if c.get("fichier_impose") else "",
            "phrase_obligation": ob.get("phrase", "") if ob else "",
            "limites": [{"type": x.get("type"), "valeur": x.get("valeur"), "police": x.get("police", ""),
                         "taille": x.get("taille"), "texte": x.get("texte", ""), "phrase": x.get("phrase", ""),
                         "objet": x.get("objet", "")}
                        for x in (c.get("limites") or []) if isinstance(x, dict)][:20],
            "visite": {"phrase": vis.get("phrase", "")} if vis else None,
        },
    }
