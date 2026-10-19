"""
PLUSIEURS LOTS, UN SEUL EFFORT (rédaction, vague 6 — J de l'étude, § 6.10). Contrat : docs/REDACTION_V6.md (J).

Pour un marché alloti auquel l'entreprise répond sur DEUX lots ou plus, l'atelier distingue :
  • des parties COMMUNES (présentation, qualité, sécurité, environnement…), rédigées une fois : UNE partie,
    un seul texte, une seule version, reprise telle quelle dans le dossier de chaque lot (une modification se
    répercute donc partout, par construction) ;
  • des parties PROPRES À CHAQUE LOT (méthodologie, moyens, planning…), une par lot ;
et l'export produit UN FICHIER PAR LOT (Word, PDF) : les parties communes et celles du lot, les limites de
pages contrôlées pour CE lot, nommé comme le règlement l'exige s'il le dit, sinon avec le numéro et
l'intitulé du lot.

Tout est SANS IA :
  • les lots sont repérés dans le règlement (lignes « Lot n° 2 : Couverture », énumération « lot 1, … ; lot 2,
    … »), chacun avec SA phrase ; un lot proposé par l'analyse n'est gardé que si son intitulé est retrouvé
    mot pour mot juste après son numéro ; un lot ajouté par l'utilisateur est dit « indiqué par vous » ;
  • la grille de chaque lot vient de SA phrase du règlement (critères et poids écrits pour ce lot) ; sans
    critère propre à un lot, la grille du règlement vaut pour chaque lot, et on le dit ; un tableau de poids
    par lot qu'Adjugo ne lit pas ligne à ligne donne les critères SANS poids, à vérifier (jamais un poids
    deviné) ;
  • le cadre de réponse d'un lot (pièce nommée ou titrée « lot n ») fait le plan de ce lot ;
  • commune ou propre à chaque lot : une règle explicite sur l'intitulé de la partie (`est_commune`), que
    l'utilisateur peut changer partie par partie ;
  • en groupement, « Qui écrit quoi » propose le membre qui a déclaré le lot (`proposition_du_lot`).
Marché à un seul lot, ou réponse à un seul lot : RIEN ne change (ce module ne s'active pas).

Données : `dossiers_presentation.plan_meta["lots"]` (lots choisis, grille et limites de chaque lot, règle de
nommage du règlement), `dossier_sections.lot` ("" = partie commune, sinon le numéro du lot — colonne prévue
depuis la vague 2), et, PAR LOT, la dérogation, le dernier export et le compteur (sous la clé « lots » des
colonnes JSON existantes) : aucune migration.
"""
import copy
import hashlib
import json
import logging
import re
from typing import Optional

from app.services import atelier_plan as ap
from app.services import dce_pieces as dp
from app.services import grille_notation as gn

logger = logging.getLogger("adjugo")

LOTS_REPERES_MAX = 20          # lots repérés au plus dans un dossier
LOTS_CHOISIS_MAX = 8           # lots d'un même dossier de présentation
INTITULE_MAX = 120
PHRASE_MAX = 300
COMMUNE = ""                   # dossier_sections.lot d'une partie commune

ORIGINE_REGLEMENT = "reglement"     # repéré dans le dossier de l'acheteur, avec sa phrase
ORIGINE_ANALYSE = "analyse"         # proposé par l'analyse, retrouvé mot pour mot à côté de son numéro
ORIGINE_UTILISATEUR = "utilisateur"  # indiqué par l'utilisateur (aucune phrase du dossier)

# Grille d'un lot : d'où viennent ses critères.
MODE_COMMUNE = "commune"       # le règlement ne distingue pas les critères par lot : sa grille vaut pour chacun
MODE_PROPRE = "propre"         # critères et poids écrits pour CE lot (sa phrase)
MODE_GENERALE = "generale"     # d'autres lots ont leurs critères ; celui-ci suit la grille générale
MODE_ILLISIBLE = "illisible"   # poids par lot dans un tableau non lu ligne à ligne : critères sans poids

MSG_MODE = {
    MODE_COMMUNE: "Le règlement ne distingue pas les critères par lot : la grille de « Comment vous serez noté » "
                  "vaut pour ce lot.",
    MODE_PROPRE: "Critères et poids écrits dans le règlement pour ce lot.",
    MODE_GENERALE: "Adjugo n'a pas trouvé de critères propres à ce lot dans le règlement : la grille générale est "
                   "reprise. Vérifiez dans le règlement.",
    MODE_ILLISIBLE: "Le règlement donne des poids différents selon les lots dans un tableau qu'Adjugo ne lit pas "
                    "ligne à ligne : les critères sont repris sans poids. Vérifiez le poids de chaque critère pour ce "
                    "lot dans le règlement.",
}
MSG_ORIGINE = {ORIGINE_REGLEMENT: "repéré dans le règlement", ORIGINE_ANALYSE: "repéré dans le règlement",
               ORIGINE_UTILISATEUR: "indiqué par vous"}
MSG_CRITERE_ABSENT = ("« {c} » n'a pas été retrouvé dans la partie du règlement propre à ce lot : il n'entre pas dans "
                      "le plan de ce lot. Vérifiez dans le règlement ; vous pouvez ajouter la partie vous-même.")
MSG_POIDS_ABSENT = "Aucun poids n'est écrit pour ce critère dans la partie du règlement propre à ce lot : vérifiez-le."


def _flat(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _fold(s) -> str:
    return dp.fold(s)


def _num(n) -> str:
    """Numéro de lot normalisé (« 02 » → « 2 ») ; '' si ce n'est pas un numéro de lot."""
    try:
        v = int(str(n).strip())
    except (TypeError, ValueError):
        return ""
    return str(v) if 1 <= v <= 99 else ""


def _cle_num(n) -> int:
    try:
        return int(n)
    except (TypeError, ValueError):
        return 999


# ── 1. Les lots du marché, repérés dans le règlement (sans IA) ───────────────────────────────────────

_TETE = r"lot\s*(?:n\s?[°o]\.?\s*|no\.?\s+|numero\s+)?0*(\d{1,2})(?!\d|[.,]\d)"
# « Lot n° 2 : Couverture », « LOT 02 – GROS ŒUVRE », « - Lot 3. Étanchéité » (en tête de ligne).
_LIGNE = re.compile(r"^[\s\-•*–—>·]*" + _TETE + r"\s*(?:[:\-–—.)/]\s*|\s+)(\S.*)$")
# « … en trois lots : lot 1, désamiantage ; lot 2, isolation … » (dans une phrase qui parle des lots).
_ENUM = re.compile(r"\blot\s*(?:n\s?[°o]\.?\s*|no\.?\s+)?0*(\d{1,2})(?!\d|[.,]\d)\s*(?:[:\-–—,]\s*|\s+)"
                   r"((?:(?!\blots?\b)[^;:\n.()])+?)\s*(?=[;.)]|,\s*(?:et\s+)?(?:le\s+)?lot\b|\s+et\s+(?:le\s+)?lot\b|$)")
_PHRASE_DES_LOTS = re.compile(r"\blots\b|allot|decompos|reparti|divise")
# Une phrase, pas un intitulé : « Lot 1 : sera attribué… », « Lot 2 – Prix 40 % ».
_VERBE = re.compile(r"\b(?:est|sera|seront|sont|comprend|comprendra|comprennent|doit|devra|devront|peut|pourra|"
                    r"pourront|concerne|concernera|attribue|attribuee|attribues|passe|reserve|reservee|fait l'objet|"
                    r"feront|fera)\b|\bporte(?:ra)?\s+sur\b")
_PREMIER_MOT_REFUSE = {"et", "ou", "a", "n", "ne", "se", "s", "dont", "qui", "que", "si", "pour", "par", "en",
                       "sur", "avec", "au", "aux", "du", "des", "de", "d", "y", "ci"}
_TOC = re.compile(r"(?:\.{3,}|…{2,}|_{4,})\s*\d{0,4}\s*$")
_MONTANT = re.compile(r"\s*(?:[(\[][^)\]]*\d[^)\]]*[)\]]|[-–—]\s*(?:montant|estim|\d).*)$")
_UNIQUE = re.compile(r"\blot unique\b|n'est pas alloti|n'est pas allotie|non alloti|ne fait pas l'objet d'un allotissement"
                     r"|pas d'allotissement|sans allotissement|ne donne pas lieu a (?:un )?allotissement")
_NOMBRES = {"deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
            "onze": 11, "douze": 12}
_ANNONCE = re.compile(r"\b(?:en|de)\s+(\d{1,2}|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze)\s+lots\b")

# Pièces où chercher la liste des lots, dans cet ordre (jamais le bordereau : « Lot 1 — Installation du chantier »
# y est un poste de prix ; jamais le CCTP : ses articles par lot décrivent des travaux).
_ORDRE_PIECES = (dp.REGLEMENT, dp.ACTE_ENGAGEMENT, dp.AUTRE, dp.CCAP, dp.CADRE)


def _nettoyer(label: str) -> str:
    t = _flat(label)
    t = _TOC.sub("", t).strip()
    t = _MONTANT.sub("", t).strip()
    for sep in (" ; ", "; ", ". "):
        if sep in t:
            t = t.split(sep, 1)[0]
    t = t.strip(" .,;:–—-/")
    if len(t) > INTITULE_MAX:
        cut = t.rfind(" ", 0, INTITULE_MAX)
        t = t[:cut if cut > 20 else INTITULE_MAX].rstrip(" ,;:–—-")
    return t


def _intitule_valable(label: str) -> bool:
    low = _fold(label)
    if len(low) < 3 or not re.search(r"[a-z]", low) or low[:1].isdigit():
        return False
    first = re.split(r"[^a-z]+", low.strip(), maxsplit=1)[0]
    if first in _PREMIER_MOT_REFUSE:
        return False
    if _VERBE.search(low) or gn._W_TOKEN.search(low) or re.search(r"crit[e]re|ponder|\bpoints?\b|€|\beur\b", low):
        return False
    return True


def _majuscule(t: str) -> str:
    return (t[:1].upper() + t[1:]) if t else t


def _phrase_plate(flat: str, a: int, b: int) -> str:
    """La phrase d'un texte à plat qui contient [a, b), ≤ PHRASE_MAX caractères (sur des limites de mots)."""
    s, e = gn._sentence_bounds(flat, a, b)
    s, e = gn._clip(flat, s, e, a, b, PHRASE_MAX)
    return flat[s:e].strip()


def _source(p: dict) -> str:
    lib = p.get("libelle") or dp.label(p.get("type"))
    return f"{lib} ({p['nom']})" if p.get("nom") else lib


def _lots_par_lignes(p: dict) -> dict:
    out = {}
    texte = p.get("texte") or ""
    for line in texte.split("\n"):
        raw = line.strip()
        if not raw or len(raw) > 400:
            continue
        m = _LIGNE.match(_fold(raw))
        if not m:
            continue
        n = _num(m.group(1))
        lab = _nettoyer(raw[m.start(2):])
        if not n or n in out or not _intitule_valable(lab):
            continue
        out[n] = {"numero": n, "intitule": _majuscule(lab), "phrase": _flat(raw)[:PHRASE_MAX], "source": _source(p),
                  "origine": ORIGINE_REGLEMENT}
    return out


def _lots_par_enumeration(p: dict) -> dict:
    out = {}
    flat = _flat(p.get("texte") or "")
    low = _fold(flat)
    for ph in re.finditer(r"[^.!?]+[.!?]?", low):
        seg = ph.group(0)
        if "lot" not in seg or not _PHRASE_DES_LOTS.search(seg):
            continue
        for m in _ENUM.finditer(seg):
            n = _num(m.group(1))
            a = ph.start() + m.start(2)
            lab = _nettoyer(flat[a:a + len(m.group(2))])
            if not n or n in out or not _intitule_valable(lab):
                continue
            s0, s1 = ph.start(), ph.end()
            phrase = flat[s0:s1].strip()
            if len(phrase) > PHRASE_MAX:
                rel = max(0, a - s0 - 40)
                phrase = phrase[rel:rel + PHRASE_MAX].strip()
            out[n] = {"numero": n, "intitule": _majuscule(lab), "phrase": phrase, "source": _source(p),
                      "origine": ORIGINE_REGLEMENT}
    return out


def _parse_lots_analyse(details: dict) -> list:
    try:
        from app.sourcing.groupement import parse_lots
        return parse_lots(str((details or {}).get("allotissement") or ""))
    except Exception:       # noqa: BLE001
        return []


def _lots_de_l_analyse(details: dict, pieces: list, deja: dict) -> dict:
    """Les lots proposés par l'analyse (details.allotissement), gardés SEULEMENT si leur intitulé est retrouvé
    mot pour mot dans le dossier, juste après leur numéro (dans les 60 caractères qui le suivent)."""
    out = {}
    for x in _parse_lots_analyse(details):
        n = _num(x.get("num"))
        lab = _nettoyer(x.get("label") or "")
        if not n or n in deja or n in out or not _intitule_valable(lab):
            continue
        cible = _fold(_flat(lab))
        for p in pieces:
            if p.get("type") in (dp.BORDEREAU,):
                continue
            flat = _flat(p.get("texte") or "")
            low = _fold(flat)
            i = low.find(cible)
            while i >= 0:
                avant = low[max(0, i - 60):i]
                if re.search(r"\blot\s*(?:n\s?[°o]\.?\s*|no\.?\s+)?0*" + n + r"(?!\d)[^.;]*$", avant):
                    out[n] = {"numero": n, "intitule": _majuscule(flat[i:i + len(cible)]),
                              "phrase": _phrase_plate(flat, max(0, i - 60), i + len(cible)), "source": _source(p),
                              "origine": ORIGINE_ANALYSE}
                    break
                i = low.find(cible, i + 1)
            if n in out:
                break
    return out


def _annonce(pieces: list) -> Optional[int]:
    for p in pieces:
        if p.get("type") != dp.REGLEMENT:
            continue
        m = _ANNONCE.search(_fold(_flat(p.get("texte") or "")))
        if m:
            v = m.group(1)
            return int(v) if v.isdigit() else _NOMBRES.get(v)
    return None


def _lot_unique(pieces: list) -> str:
    for p in pieces:
        if p.get("type") not in (dp.REGLEMENT, dp.AUTRE, dp.ACTE_ENGAGEMENT):
            continue
        flat = _flat(p.get("texte") or "")
        m = _UNIQUE.search(_fold(flat))
        if m:
            return _phrase_plate(flat, m.start(), m.end())
    return ""


def pieces_du_texte(texte: str) -> list:
    """Le texte assemblé du dossier (« === nom === ») en pièces typées [{nom, type, libelle, texte}]."""
    return [{"nom": p["nom"], "type": p["type"], "libelle": p["libelle"], "texte": p["texte"]}
            for p in dp.typed_pieces(texte or "")]


def reperer(texte: str, details: Optional[dict] = None, pieces: Optional[list] = None) -> dict:
    """Les lots du marché, SANS IA : {alloti, lots: [{numero, intitule, phrase, source, origine}], annonce,
    unique (phrase « lot unique »), message}. `alloti` : au moins deux lots repérés. Ne lève jamais."""
    out = {"alloti": False, "lots": [], "annonce": None, "unique": "", "message": ""}
    try:
        pcs = pieces if pieces is not None else pieces_du_texte(texte)
        ordre = sorted([p for p in pcs if p.get("type") in _ORDRE_PIECES],
                       key=lambda p: _ORDRE_PIECES.index(p.get("type")))
        trouves = {}
        for p in ordre:
            for n, x in _lots_par_lignes(p).items():
                trouves.setdefault(n, x)
            if len(trouves) >= 2 and p.get("type") == dp.REGLEMENT:
                break
        if len(trouves) < 2:
            for p in ordre:
                for n, x in _lots_par_enumeration(p).items():
                    trouves.setdefault(n, x)
                if len(trouves) >= 2:
                    break
        for n, x in _lots_de_l_analyse(details or {}, ordre, trouves).items():
            trouves.setdefault(n, x)
        lots = sorted(trouves.values(), key=lambda x: _cle_num(x["numero"]))[:LOTS_REPERES_MAX]
        out["lots"] = lots
        out["annonce"] = _annonce(pcs)
        out["alloti"] = len(lots) >= 2
        if not out["alloti"]:
            out["unique"] = _lot_unique(pcs)
        out["message"] = message_lots(out)
    except Exception as e:      # noqa: BLE001 — repérage facultatif : le dossier reste à un seul lot
        logger.warning("lots non repérés : %s", type(e).__name__)
    return out


def message_lots(r: dict) -> str:
    n = len(r.get("lots") or [])
    if n >= 2:
        msg = (f"Le règlement répartit ce marché en {n} lots. Si vous répondez à deux lots ou plus, Adjugo prépare des "
               "parties communes, rédigées une fois pour tous vos lots, et des parties propres à chaque lot, avec un "
               "fichier par lot à l'export.")
        a = r.get("annonce")
        if a and a != n:
            msg += (f" Le règlement annonce {a} lots et Adjugo en a repéré {n} : vérifiez dans le règlement, vous pouvez "
                    "ajouter un lot.")
        return msg
    return ""


# ── 2. Les pièces propres à un lot (« LOT 02/CCTP.pdf », « Cadre de réponse lot 3.docx ») ────────────

def _cle_nom(nom: str) -> str:
    k = _fold(str(nom or "").replace("\\", "/"))
    k = re.sub(r"\.(pdf|docx?|odt|txt|md|xlsx?|ods|zip)$", " ", k)
    k = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", k)
    return " " + re.sub(r"[^a-z0-9°]+", " ", k).strip() + " "


def lot_de_piece(nom: str, texte: str = "", numeros=None) -> str:
    """Le lot auquel une pièce est propre (par son chemin ou son nom, sinon par son titre), ou '' (pièce
    commune, ou plusieurs lots). Sans IA."""
    connus = {_num(x) for x in (numeros or [])} - {""}
    k = _cle_nom(nom)
    nums = {_num(m.group(1)) for m in re.finditer(r" lots? (?:n ?°? ?|no )?0*(\d{1,2}) ", k)} - {""}
    if connus:
        nums &= connus
    if len(nums) == 1:
        return nums.pop()
    if len(nums) > 1:
        return ""
    head = _fold(str(texte or "")[:800])
    nums = {_num(m.group(1)) for m in re.finditer(r"(?:^|\n)[\s\-–—]*" + _TETE, head)} - {""}
    if connus:
        nums &= connus
    return nums.pop() if len(nums) == 1 else ""


def cadres_par_lot(pieces: list, numeros: list) -> dict:
    """{numéro: texte du cadre de réponse propre à ce lot, '': cadres communs}."""
    out = {}
    for p in pieces or []:
        if p.get("type") != dp.CADRE or not (p.get("texte") or "").strip():
            continue
        n = lot_de_piece(p.get("nom") or "", p.get("texte") or "", numeros)
        out.setdefault(n, []).append(p.get("texte") or "")
    return {k: "\n\n".join(v) for k, v in out.items()}


# ── 3. La grille de chaque lot, depuis SA phrase du règlement (sans IA) ───────────────────────────────

_MARQUE = re.compile(r"\blots?\s*(?:n\s?[°o]\.?\s*|no\.?\s+)?0*(\d{1,2})(?!\d|[.,]\d)"
                     r"((?:\s*(?:,|\bet\b|\ba\b|\bau\b|-|–)\s*(?:le\s+lot\s+|lot\s+)?0*\d{1,2}(?!\d|[.,]\d))*)")
_GENERAL = re.compile(r"(?:tous les|l'ensemble des|chacun des|chaque|les differents|les autres) lots?\b|quel que soit le lot"
                      r"|identiques? pour (?:tous )?les lots|par lot\b")
_ARTICLE = re.compile(r"\b(?:article|chapitre)\s+\d")
_ZONE_MAX = 6000


def _nums_de_marque(m) -> set:
    first = _num(m.group(1))
    rest = m.group(2) or ""
    nums = [first] + [_num(x) for x in re.findall(r"\d{1,2}", rest)]
    nums = [x for x in nums if x]
    if re.search(r"\ba\b|\bau\b|-|–", rest) and len(nums) == 2 and _cle_num(nums[1]) > _cle_num(nums[0]):
        nums = [str(i) for i in range(_cle_num(nums[0]), _cle_num(nums[1]) + 1)]
    return set(nums)


def _zones_criteres(p) -> list:
    """Régions « critères de jugement » d'une pièce (_Piece) : du titre jusqu'à l'article suivant (≤ 6 000 car.)."""
    out = []
    for m in gn._CRIT_ZONE.finditer(p.low):
        z0 = m.start()
        z1 = min(len(p.low), z0 + _ZONE_MAX)
        a = _ARTICLE.search(p.low, m.end() + 40, z1)
        if a:
            z1 = a.start()
        if out and z0 < out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], z1))
        else:
            out.append((z0, z1))
    return out


def _ligne_de(p, pos: int) -> tuple:
    """(début, fin) de la ligne (d'avant la mise à plat) qui contient `pos`."""
    import bisect
    br = p.breaks
    i = bisect.bisect_right(br, pos)
    return (br[i - 1] if i else 0), (br[i] if i < len(br) else len(p.flat))


def _utile(p, s0: int, s1: int, crit_stems: list) -> bool:
    """Un segment de lot qui parle des critères : le nom d'un critère ou un poids y est écrit (la liste des lots
    « Lot 1 : Désamiantage » d'un article sur l'attribution n'en est pas un)."""
    return bool(gn._W_TOKEN.search(p.low[s0:s1])) or bool(gn._name_spans(p, s0, s1, crit_stems))


def _tableau(p, marks: list, crit_stems: list) -> bool:
    """Poids par lot dans un tableau à colonnes : une ligne qui cite au moins deux lots, sans poids (l'en-tête
    « Critère | Lot 1 | Lot 2 »), suivie, dans les trois lignes d'après, d'une ligne qui porte le nom d'un critère et
    au moins deux poids (« Valeur technique | 60 % | 40 % »). Jamais lu ligne à ligne : aucun poids deviné."""
    par_ligne = {}
    for s0, _e, nums in marks:
        if nums:
            par_ligne.setdefault(_ligne_de(p, s0), set()).update(nums)
    for (ls, le), nums in par_ligne.items():
        if len(nums) < 2 or gn._W_TOKEN.search(p.low[ls:le]):
            continue
        pos = le
        for _ in range(3):
            if pos >= len(p.flat):
                break
            a, b = _ligne_de(p, pos + 1)
            if len(list(gn._W_TOKEN.finditer(p.low[a:b]))) >= 2 and gn._name_spans(p, a, b, crit_stems):
                return True
            pos = b
    return False


def _segments(P: list, numeros: list, crit_stems: list) -> tuple:
    """(segments [(pièce, début, fin, lots, début de la mention)], tableau_illisible). Un segment va d'une mention
    « lot n » (ou « lots 1 et 2 ») au repère suivant, dans la zone des critères, et n'est gardé que s'il parle des
    critères. Une pièce propre à un lot (RC du lot 2) : sa zone des critères est un segment de ce lot."""
    connus = set(numeros)
    segs, illisible = [], False
    for p in P:
        lp = lot_de_piece(p.nom, p.flat[:800], numeros)
        zones = _zones_criteres(p)
        if lp and zones:
            for z0, z1 in zones:
                if _utile(p, z0, z1, crit_stems):
                    segs.append((p, z0, z1, {lp}, z0))
            continue
        for z0, z1 in zones:
            marks = []
            for m in _MARQUE.finditer(p.low, z0, z1):
                nums = _nums_de_marque(m) & connus
                if nums:
                    marks.append((m.start(), m.end(), nums))
            for m in _GENERAL.finditer(p.low, z0, z1):
                marks.append((m.start(), m.end(), None))
            marks.sort(key=lambda x: x[0])
            if _tableau(p, marks, crit_stems):
                illisible = True
                continue
            for i, (s0, e, nums) in enumerate(marks):
                nxt = marks[i + 1][0] if i + 1 < len(marks) else z1
                if nums is not None and nxt > e and _utile(p, e, nxt, crit_stems):
                    segs.append((p, e, nxt, nums, s0))
    return segs, illisible


def _phrase_du_lot(p, debut: int, a: int, b: int, fin: int) -> str:
    """La phrase du règlement pour un critère d'un lot, mot pour mot : de la ligne de la mention du lot (« Pour le
    lot 2 : valeur technique 60 % ; prix 40 %. ») jusqu'à la fin de la ligne du poids ; trop longue, la ligne du
    critère seule."""
    import bisect
    br = p.breaks
    i = bisect.bisect_right(br, debut)
    ls = br[i - 1] if i else 0
    if gn._W_TOKEN.search(p.low[ls:debut]):
        ls = debut                       # la ligne commence par un autre lot : on part de la mention de celui-ci
    j = bisect.bisect_left(br, b)
    le = min(br[j] if j < len(br) else len(p.flat), fin if fin > b else len(p.flat))
    if 0 <= ls <= a and le - ls <= PHRASE_MAX:
        return p.flat[ls:le].strip()
    _st, phrase = p.line_phrase(a, b)
    return phrase


def _ligne_du_lot(ln: dict, j: int, segs: list, crit_stems: list) -> Optional[dict]:
    """Le critère `ln` (index j) dans les segments d'un lot : poids rattaché, sa phrase ; None si le nom n'y est pas."""
    nom_vu = None
    for p, s0, s1, _nums, debut in segs:
        w = gn._attribute(p, s0, s1, crit_stems).get(j)
        if w:
            a = min(w[3], next((x[0] for x in gn._name_spans(p, s0, s1, crit_stems) if x[2] == j), w[3]))
            return {"poids": w[2], "poids_valeur": w[0], "poids_unite": w[1],
                    "phrase": _phrase_du_lot(p, debut, a, w[4], s1), "source": gn._source_label(p)}
        if nom_vu is None:
            sp = next((x for x in gn._name_spans(p, s0, s1, crit_stems) if x[2] == j), None)
            if sp is not None:
                nom_vu = {"poids": "", "poids_valeur": None, "poids_unite": None,
                          "phrase": _phrase_du_lot(p, debut, sp[0], sp[1], s1), "source": gn._source_label(p)}
    return nom_vu


def _sous_du_lot(ln: dict, segs: list) -> list:
    """Les sous-critères (du règlement, déjà retrouvés) qui figurent aussi dans la partie propre au lot, avec le
    poids qui y est écrit pour eux ; les autres ne sont pas repris pour ce lot."""
    subs = [x for x in (ln.get("sous_criteres") or []) if isinstance(x, dict) and x.get("critere")]
    if not subs:
        return []
    stems = [gn._stems(x["critere"]) for x in subs]
    out = []
    for k, x in enumerate(subs):
        hit = _ligne_du_lot(x, k, segs, stems)
        if hit is None:
            continue
        y = dict(x)
        y.update(poids=hit["poids"], poids_valeur=hit["poids_valeur"], poids_unite=hit["poids_unite"],
                 phrase=hit["phrase"], source=hit["source"], statut=gn.RETROUVE)
        out.append(y)
    return out


def _lots_cites(phrase: str) -> set:
    """Les lots que cite une phrase (« Pour le lot 3, … », « lots 1 et 2 ») ; « par lot » n'en cite aucun."""
    low = _fold(phrase or "")
    nums = set()
    for m in _MARQUE.finditer(low):
        nums |= _nums_de_marque(m)
    return nums


def limites_du_lot(limites: list, numero: str, numeros: list) -> list:
    """Les limites écrites dans le dossier qui valent pour CE lot : celles de sa phrase (« Pour le lot 3, le mémoire
    compte 5 pages au maximum ») et celles qui ne citent aucun lot (« 8 pages au maximum par lot ») — une limite
    propre au lot remplace la limite générale du même type."""
    propres, generales = [], []
    for x in limites or []:
        if not isinstance(x, dict):
            continue
        cites = _lots_cites(x.get("phrase") or "")
        if not cites:
            generales.append(x)
        elif numero in cites:
            propres.append(x)
    types_propres = {(x.get("type"), x.get("objet") or "") for x in propres}
    return propres + [x for x in generales if (x.get("type"), x.get("objet") or "") not in types_propres
                      or x.get("type") == "police"]


def grilles_par_lot(grille: Optional[dict], texte: str, numeros: list) -> dict:
    """{numéro: grille du lot} au format de « Comment vous serez noté » (grille_notation), chacune avec
    `lot: {numero, mode, message, phrase, source}` et ses limites. Sans IA ; sans grille, {}."""
    if not isinstance(grille, dict) or not isinstance(grille.get("criteres"), list):
        return {}
    numeros = [n for n in numeros if n]
    lignes = [ln for ln in grille["criteres"] if isinstance(ln, dict) and ln.get("critere")]
    P = gn._pieces(texte or "")
    rc = [p for p in P if p.type == dp.REGLEMENT]
    scope = ([p for p in P if p.type in (dp.REGLEMENT, dp.CADRE)] if rc else P)
    stems = [gn._stems(ln["critere"]) for ln in lignes]
    try:
        segs, illisible = _segments(scope, numeros, stems)
    except Exception as e:      # noqa: BLE001
        logger.warning("grille par lot illisible : %s", type(e).__name__)
        segs, illisible = [], False
    phrase_commune, source_commune = "", ""
    for p in scope:
        for z0, z1 in _zones_criteres(p):
            m = _GENERAL.search(p.low, z0, z1)
            if m and not phrase_commune:
                _s, phrase_commune = p.line_phrase(m.start(), m.end())
                source_commune = gn._source_label(p)
    limites = ((grille.get("contraintes") or {}).get("limites") or [])
    a_des_segments = any(any(n in s[3] for s in segs) for n in numeros)
    out = {}
    for n in numeros:
        g = copy.deepcopy(grille)
        mine = [s for s in segs if n in s[3]]
        if illisible:
            mode = MODE_ILLISIBLE
        elif mine:
            mode = MODE_PROPRE
        elif a_des_segments:
            mode = MODE_GENERALE
        else:
            mode = MODE_COMMUNE
        nouvelles = []
        for j, ln in enumerate(lignes):
            x = copy.deepcopy(ln)
            ch = x.get("choix_utilisateur") or {}
            if mode == MODE_ILLISIBLE:
                x.update(poids="", poids_valeur=None, poids_unite=None)
                for sc in x.get("sous_criteres") or []:
                    if isinstance(sc, dict):
                        sc.update(poids="", poids_valeur=None, poids_unite=None)
                if ch.get("choix") == "confirme":
                    x["choix_utilisateur"] = dict(ch, poids="")
                x["message_lot"] = MSG_MODE[MODE_ILLISIBLE]
            elif mode == MODE_PROPRE:
                hit = _ligne_du_lot(x, j, mine, stems)
                if hit is None:
                    x.update(statut=gn.A_VERIFIER, poids="", poids_valeur=None, poids_unite=None, phrase="",
                             source="", sous_criteres=[])
                    x["message_lot"] = MSG_CRITERE_ABSENT.format(c=x["critere"])
                    if ch.get("choix") == "ecarte":
                        x["choix_utilisateur"] = dict(ch)
                    elif ch.get("choix") == "confirme":
                        x["choix_utilisateur"] = dict(ch, poids="")     # un critère confirmé, jamais son poids d'ailleurs
                    else:
                        x.pop("choix_utilisateur", None)
                else:
                    x.update(statut=gn.RETROUVE, poids=hit["poids"], poids_valeur=hit["poids_valeur"],
                             poids_unite=hit["poids_unite"], phrase=hit["phrase"], source=hit["source"],
                             sous_criteres=_sous_du_lot(ln, mine))
                    if not hit["poids"] and ln.get("poids"):
                        x["message_lot"] = MSG_POIDS_ABSENT
                    if ch.get("choix") == "confirme":
                        x["choix_utilisateur"] = dict(ch, poids="") if not hit["poids"] else dict(ch)
                        if hit["poids"]:
                            x["choix_utilisateur"].pop("poids", None)
            nouvelles.append(x)
        g["criteres"] = nouvelles
        g.setdefault("contraintes", {})
        g["contraintes"] = dict(g["contraintes"], limites=limites_du_lot(limites, n, numeros))
        gn.refresh(g)
        g["lot"] = {"numero": n, "mode": mode, "message": MSG_MODE[mode],
                    "phrase": phrase_commune if mode in (MODE_COMMUNE, MODE_GENERALE) else "",
                    "source": source_commune if mode in (MODE_COMMUNE, MODE_GENERALE) else ""}
        out[n] = g
    return out


def grille_out(g: Optional[dict]) -> Optional[dict]:
    """Ce que l'écran montre de la grille d'un lot (gardé dans plan_meta) : critères, poids tels qu'écrits pour ce
    lot, leur phrase, contrôle du total, d'où vient la grille."""
    if not isinstance(g, dict):
        return None
    lignes = []
    for ln in g.get("criteres") or []:
        if not isinstance(ln, dict):
            continue
        lignes.append({"id": str(ln.get("id") or "")[:20], "critere": _flat(ln.get("critere"))[:160],
                       "poids": _flat(ln.get("poids_retenu"))[:40] if ln.get("dans_le_plan") else "",
                       "poids_source": (ln.get("poids_source") or "") if ln.get("dans_le_plan") else "",
                       "phrase": _flat(ln.get("phrase"))[:PHRASE_MAX + 100], "source": _flat(ln.get("source"))[:200],
                       "statut": ln.get("statut") if ln.get("statut") in (gn.RETROUVE, gn.A_VERIFIER) else gn.A_VERIFIER,
                       "dans_le_plan": bool(ln.get("dans_le_plan")),
                       "prix": ap.est_critere_prix(ln.get("critere") or ""),
                       "message": _flat(ln.get("message_lot"))[:300],
                       "sous_criteres": [{"critere": _flat(x.get("critere"))[:160],
                                          "poids": _flat(x.get("poids"))[:40] if x.get("statut") == gn.RETROUVE else ""}
                                         for x in (ln.get("sous_criteres") or []) if isinstance(x, dict)][:gn.SOUS_MAX]})
    lot = g.get("lot") if isinstance(g.get("lot"), dict) else {}
    ct = g.get("controle_total") if isinstance(g.get("controle_total"), dict) else {}
    return {"mode": lot.get("mode") or MODE_COMMUNE, "message": lot.get("message") or "",
            "phrase": lot.get("phrase") or "", "source": lot.get("source") or "", "lignes": lignes,
            "controle_total": {"statut": ct.get("statut", ""), "message": ct.get("message", "")}}


# ── 4. Commune ou propre à chaque lot : une règle explicite ───────────────────────────────────────────

# Propres à chaque lot (l'étude : méthodologie, moyens…) — prioritaires sur les mots des parties communes.
_PROPRE = re.compile(r"methodolog|\bmoyens?\b|humain|materiel|organisation du chantier|organisation des travaux"
                     r"|organisation de l'intervention|planning|delai|calendrier|phasage|mode operatoire|comprehension"
                     r"|execution|technique|approvisionnement|sous-traitan|equipe|encadrement|intervention"
                     r"|prestations?\b|travaux de|ouvrages?\b|fournitures?\b|references?\b")
# Communes à tous les lots (l'étude : présentation, qualité, environnement…).
_COMMUNE = re.compile(r"presentation\b|qualite|securite|sante\b|hygiene|environnement|developpement durable|\brse\b"
                      r"|responsabilite (?:sociale|societale)|\bsocial|insertion|dechets?\b|carbone|ecolog|groupement")
REGLE_COMMUNE = ("Partie commune quand son intitulé parle de présentation, de qualité, de sécurité, d'environnement, de "
                 "déchets, d'insertion ou du groupement, et pas de méthodologie, de moyens, de planning, de délais ni "
                 "d'exécution ; sinon propre à chaque lot. Vous pouvez changer chaque partie.")


def est_commune(intitule: str) -> bool:
    low = _fold(_flat(intitule))
    if _PROPRE.search(low):
        return False
    return bool(_COMMUNE.search(low))


def _cle(s: dict) -> tuple:
    """La « case » d'une partie du plan, la même d'un lot à l'autre (même source, même critère, même intitulé,
    mêmes titres au-dessus ; même numéro pour une question du cadre)."""
    par = "/".join(_fold(_flat(x.get("intitule"))) for x in (s.get("parents") or []) if isinstance(x, dict))
    num = str(s.get("numero") or "") if s.get("source_plan") == ap.CADRE else ""
    return (str(s.get("source_plan") or ""), num, str(s.get("critere_id") or ""), _fold(_flat(s.get("intitule"))), par)


def cle_section(s) -> tuple:
    """_cle pour une partie enregistrée (DossierSection)."""
    return _cle({"parents": s.parents or [], "numero": s.numero, "source_plan": s.source_plan,
                 "critere_id": s.critere_id, "intitule": s.intitule})


def fusionner(plans: dict, numeros: list) -> list:
    """Un seul plan pour tous les lots : chaque partie commune une fois (là où elle tombe dans le plan du premier
    lot), les parties propres à chaque lot entre elles, lot par lot. L'export d'un lot (parties communes + les
    siennes) suit ainsi l'ordre de SON plan. Une partie n'est commune que si la règle le dit ET qu'elle figure dans
    le plan de chacun des lots."""
    cles = {n: [_cle(s) for s in plans[n]["sections"]] for n in numeros}
    communes = set(cles[numeros[0]])
    for n in numeros[1:]:
        communes &= set(cles[n])
    modele = {}
    for s in plans[numeros[0]]["sections"]:
        modele.setdefault(_cle(s), s)
    communes = {k for k in communes if est_commune(modele[k].get("intitule") or "")}
    ordre_c = list(dict.fromkeys(k for k in cles[numeros[0]] if k in communes))
    idx = {k: i for i, k in enumerate(ordre_c)}
    segs = {n: [[] for _ in range(len(ordre_c) + 1)] for n in numeros}
    poids_c = {k: set() for k in ordre_c}
    for n in numeros:
        cur = 0
        for s, k in zip(plans[n]["sections"], cles[n]):
            if k in communes:
                cur = max(cur, idx[k] + 1)
                poids_c[k].add((s.get("poids") or "", s.get("poids_source") or ""))
                continue
            segs[n][cur].append(dict(s, lot=n))
    out = []
    for i in range(len(ordre_c) + 1):
        for n in numeros:
            out.extend(segs[n][i])
        if i < len(ordre_c):
            k = ordre_c[i]
            s = dict(modele[k], lot=COMMUNE)
            if len(poids_c[k]) > 1:
                # Le poids n'est pas le même d'un lot à l'autre : la partie commune n'en porte aucun (chaque lot
                # le dit dans sa grille), jamais celui d'un seul lot.
                s.update(poids="", poids_source="")
            out.append(s)
    return out


# ── 5. Le plan d'un dossier à plusieurs lots ──────────────────────────────────────────────────────────

def numeros(lots: list) -> list:
    return [x["numero"] for x in lots or [] if isinstance(x, dict) and x.get("numero")]


def _analyse_du_lot(analysis: dict, g: Optional[dict]) -> dict:
    a = dict(analysis or {})
    det = dict(a.get("details") or {}) if isinstance(a.get("details"), dict) else {}
    if g is not None:
        det["grille_notation"] = g
    a["details"] = det
    return a


def construire_plan(analysis: Optional[dict], lots: list, texte: str, pieces: list, cadre_global: str = "",
                    base: str = "auto", en_groupement: bool = False, dossier_present: bool = True) -> dict:
    """Le plan d'un dossier à plusieurs lots, SANS IA, au format d'atelier_plan.build_plan (chaque partie porte
    `lot` : '' commune, sinon son numéro) + `lots` : ce que le dossier garde de chaque lot (plan_meta)."""
    nums = numeros(lots)
    det = (analysis or {}).get("details") if isinstance((analysis or {}).get("details"), dict) else {}
    g = det.get("grille_notation") if isinstance(det.get("grille_notation"), dict) else None
    grilles = grilles_par_lot(g, texte, nums) if g is not None else {}
    cadres = cadres_par_lot(pieces, nums)
    plans = {}
    for n in nums:
        cadre = cadres.get(n) or cadres.get("") or cadre_global or ""
        plans[n] = ap.build_plan(_analyse_du_lot(analysis, grilles.get(n)), cadre, base=base,
                                 en_groupement=en_groupement, dossier_present=dossier_present)
    premier = plans[nums[0]]
    sources = {n: plans[n]["source"] for n in nums}
    source = premier["source"] if len(set(sources.values())) == 1 else (
        ap.GRILLE if ap.GRILLE in sources.values() else ap.LIBRE)
    sections = fusionner(plans, nums)
    n_c = sum(1 for s in sections if not s.get("lot"))
    n_p = len(sections) - n_c
    out = dict(premier)
    out["grille"] = ap.empreinte_grille(analysis)
    out["source"] = source
    out["sections"] = sections
    out["message"] = (premier.get("message") or "").strip() + " " + message_plan(len(nums), n_c, n_p)
    out["message"] = out["message"].strip()
    out["lots"] = {"actif": True, "liste": [dict(x) for x in lots],
                   "grilles": {n: grille_out(grilles.get(n)) for n in nums if grilles.get(n) is not None},
                   "limites": {n: plans[n].get("limites") or {} for n in nums},
                   "sources": sources,
                   "criteres_hors_dossier": {n: plans[n].get("criteres_hors_dossier") or [] for n in nums},
                   "nommage": nommage(texte, pieces),
                   "regle_commune": REGLE_COMMUNE}
    return out


def message_plan(n_lots: int, n_communes: int, n_propres: int) -> str:
    c = f"{n_communes} partie{'s' if n_communes > 1 else ''} commune{'s' if n_communes > 1 else ''}"
    p = f"{n_propres} partie{'s' if n_propres > 1 else ''} propre{'s' if n_propres > 1 else ''} à un lot"
    return (f"Vous répondez à {n_lots} lots : {c}, rédigée{'s' if n_communes > 1 else ''} une fois pour tous vos "
            f"lots, et {p} ; un fichier par lot à l'export.")


# ── 6. Le nom de chaque fichier : celui du règlement, sinon le numéro et l'intitulé du lot ──────────────

_NOMMAGE = re.compile(r"(?:\bnomm|\bdenomm|\bintitul|\brenomm|\bnommage|\bnomenclature|\bnom (?:du|des|de chaque) fichiers?)"
                      r"[^.;«\"“]{0,90}?[«\"“]\s*([^»\"”\n]{4,140}?)\s*[»\"”]")
_PH_LOT = re.compile(r"(lot\s*(?:n\s?[°o]\.?\s*|_|-|\.)?)(x{1,3}(?![a-z])|n(?![a-z])|\d{1,2}(?!\d)|#+|\?+|\[[^\]]{0,30}\]|\([^)]{0,30}\)"
                     r"|<[^>]{0,30}>|_{2,}|\.{2,}|…)", re.IGNORECASE)
_PH_NOM = re.compile(r"(?:[\[(<]\s*)?(?:nom|raison sociale|d[ée]nomination)\s*(?:de l['’]\s*|du |de la |d['’]\s*)?\s*"
                     r"(?:candidat|entreprise|soumissionnaire|soci[ée]t[ée]|titulaire|mandataire|groupement)\s*[\])>]?"
                     r"|\b(?:nom_?candidat|nom_?entreprise|nom_?soci[ée]t[ée]|raison_?sociale|nomducandidat"
                     r"|nomdelentreprise)\b", re.IGNORECASE)
_PH_INTITULE = re.compile(r"(?:[\[(<]\s*)?(?:intitul[ée]|nom|libell[ée]|d[ée]signation)\s+du\s+lot\s*[\])>]?", re.IGNORECASE)
_PH_RESTE = re.compile(r"\[[^\]]*\]|<[^>]*>|\bx{2,}\b|_{3,}|\.{3,}|…", re.IGNORECASE)
_MEMOIRE = re.compile(r"memoire|\bmt\b|offre technique|note (?:methodologique|technique)|\blot")
_SUR = re.compile(r"[\x00-\x1f/\\:*?\"<>|]+")
NOM_MAX = 110


def nommage(texte: str, pieces: Optional[list] = None) -> Optional[dict]:
    """La règle de nommage des fichiers écrite dans le règlement (« Chaque mémoire est remis dans un fichier nommé
    « Lot X - Mémoire technique - Nom du candidat » »), avec SA phrase ; None si le règlement n'en donne pas."""
    try:
        pcs = pieces if pieces is not None else pieces_du_texte(texte)
        for p in pcs:
            if p.get("type") not in (dp.REGLEMENT, dp.AUTRE):
                continue
            flat = _flat(p.get("texte") or "")
            low = _fold(flat)
            for m in _NOMMAGE.finditer(low):
                modele = flat[m.start(1):m.end(1)].strip()
                if not _MEMOIRE.search(_fold(modele)):
                    continue
                return {"modele": modele[:140], "phrase": _phrase_plate(flat, m.start(), m.end()), "source": _source(p)}
    except Exception as e:      # noqa: BLE001
        logger.warning("règle de nommage non lue : %s", type(e).__name__)
    return None


def _sur(s: str) -> str:
    return re.sub(r"\s+", " ", _SUR.sub(" ", str(s or ""))).strip(" .")


def _court(stem: str) -> str:
    if len(stem) <= NOM_MAX:
        return stem
    cut = stem.rfind(" ", 0, NOM_MAX)
    return stem[:cut if cut > 40 else NOM_MAX].rstrip(" -–,.")


def nom_du_lot(lot: dict, label: str, entreprise: str = "", regle: Optional[dict] = None) -> dict:
    """{stem, selon_reglement, message} : le nom (sans extension) du fichier d'un lot. La règle du règlement est
    suivie quand Adjugo sait remplir chacun de ses champs (numéro du lot, nom du candidat, intitulé du lot) ;
    sinon, un nom clair : « <document> - Lot 2 - <intitulé du lot> », et on le dit."""
    n = str(lot.get("numero") or "")
    intit = _flat(lot.get("intitule"))
    defaut = _court(_sur(f"{label} - Lot {n}" + (f" - {intit}" if intit else ""))) or f"Lot {n}"
    if not regle or not regle.get("modele"):
        return {"stem": defaut, "selon_reglement": False, "message": ""}
    modele = str(regle["modele"])
    a_un_lot = bool(_PH_LOT.search(modele))

    def _lot(m):
        ph = m.group(2)
        width = len(ph) if (ph.lower().startswith("x") or ph.isdigit()) and len(ph) > 1 else 1
        return m.group(1) + n.zfill(width)
    t = _PH_LOT.sub(_lot, modele, count=1)
    nom = _flat(entreprise)
    if _PH_NOM.search(t):
        if not nom:
            return {"stem": defaut, "selon_reglement": False,
                    "message": f"Le règlement impose un nom de fichier (« {modele} ») : renseignez le nom de votre "
                               "entreprise dans votre profil pour qu'Adjugo le suive."}
        t = _PH_NOM.sub(nom, t)
    if _PH_INTITULE.search(t):
        t = _PH_INTITULE.sub(intit or f"Lot {n}", t)
    if _PH_RESTE.search(t):
        return {"stem": defaut, "selon_reglement": False,
                "message": f"Le règlement impose un nom de fichier (« {modele} ») qu'Adjugo ne sait pas compléter : "
                           f"renommez le fichier avant de le déposer."}
    if not a_un_lot:
        t = f"{t} - Lot {n}"
    stem = _court(_sur(t))
    if not stem:
        return {"stem": defaut, "selon_reglement": False, "message": ""}
    return {"stem": stem, "selon_reglement": True,
            "message": f"Nommé comme le règlement l'exige : « {modele} »." + (
                "" if a_un_lot else " Le numéro du lot est ajouté : un fichier par lot.")}


# ── 7. Lecture d'un dossier enregistré ────────────────────────────────────────────────────────────────

def meta(dossier) -> dict:
    m = getattr(dossier, "plan_meta", None)
    x = m.get("lots") if isinstance(m, dict) else None
    return x if isinstance(x, dict) else {}


def actif(dossier) -> bool:
    """Le dossier répond-il à plusieurs lots (au moins deux) ?"""
    x = meta(dossier)
    return bool(x.get("actif")) and len(numeros(x.get("liste") or [])) >= 2


def liste(dossier) -> list:
    return [dict(x) for x in (meta(dossier).get("liste") or []) if isinstance(x, dict) and x.get("numero")] \
        if actif(dossier) else []


def carte(dossier) -> dict:
    """{numéro: intitulé} des lots du dossier ({} pour un dossier à un seul lot)."""
    return {x["numero"]: _flat(x.get("intitule")) for x in liste(dossier)}


def libelle(dossier, numero: str) -> str:
    if not numero:
        return ""
    i = carte(dossier).get(numero)
    return f"Lot {numero}" + (f" — {i}" if i else "")


def lot_de(dossier, numero) -> Optional[dict]:
    n = _num(numero) if numero not in (None, "") else ""
    return next((x for x in liste(dossier) if x["numero"] == n), None) if n else None


def du_lot(sections: list, numero: str) -> list:
    """Les parties qui entrent dans le dossier d'un lot : les parties communes et les siennes."""
    return [s for s in sections if (getattr(s, "lot", "") or "") in ("", numero)]


def source_du_lot(dossier, numero: str) -> str:
    return str((meta(dossier).get("sources") or {}).get(numero) or getattr(dossier, "plan_source", "") or "")


def limites_doc(dossier, numero: str) -> dict:
    x = (meta(dossier).get("limites") or {}).get(numero)
    return x if isinstance(x, dict) else {}


def freres(sections: list, section) -> list:
    """Les parties de la même case dans les AUTRES lots (une partie propre à un lot) ; [] pour une partie commune."""
    if not (getattr(section, "lot", "") or ""):
        return []
    k = cle_section(section)
    return [s for s in sections if s.id != section.id and (s.lot or "") and s.lot != section.lot
            and cle_section(s) == k]


def etiquettes(dossier, sections: list) -> dict:
    """{section_id: « (lot 2) »} : pour dire de quel lot est une partie là où toutes les parties sont listées
    ensemble (blocage d'ensemble, exigences). Vide pour un dossier à un seul lot."""
    if not actif(dossier):
        return {}
    return {s.id: (f" (lot {s.lot})" if s.lot else "") for s in sections}


# ── 8. Le cache des lots repérés (process unique, borné) ──────────────────────────────────────────────

_CACHE = {}
_CACHE_MAX = 32


def cle_cache(*parts) -> str:
    return hashlib.sha256(json.dumps([str(p) for p in parts], ensure_ascii=False).encode("utf-8")).hexdigest()[:32]


def cache_get(cle: str):
    return copy.deepcopy(_CACHE.get(cle)) if cle in _CACHE else None


def cache_put(cle: str, valeur) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)), None)
    _CACHE[cle] = copy.deepcopy(valeur)


# ── 9. Les lots choisis par l'utilisateur ─────────────────────────────────────────────────────────────

class LotsInvalides(ValueError):
    pass


def choisir(reperes: list, choisis: list, ajoutes: Optional[list] = None) -> list:
    """Les lots du dossier, dans l'ordre de leur numéro : ceux repérés que l'utilisateur coche (`choisis` :
    numéros) et ceux qu'il indique lui-même (`ajoutes` : [{numero, intitule}], « indiqué par vous »). Lève
    LotsInvalides (message affichable) si un numéro est inconnu, en double, ou si un intitulé manque."""
    par_num = {x["numero"]: x for x in reperes or [] if isinstance(x, dict) and x.get("numero")}
    out = {}
    for c in choisis or []:
        n = _num(c)
        if not n or n not in par_num:
            raise LotsInvalides("Ce lot n'a pas été repéré dans le règlement : ajoutez-le avec son numéro et son intitulé.")
        out[n] = dict(par_num[n])
    for a in ajoutes or []:
        if not isinstance(a, dict):
            raise LotsInvalides("Indiquez le numéro et l'intitulé du lot.")
        n = _num(a.get("numero"))
        intit = _nettoyer(str(a.get("intitule") or ""))
        if not n:
            raise LotsInvalides("Le numéro d'un lot est un nombre de 1 à 99.")
        if len(intit) < 2:
            raise LotsInvalides(f"Donnez l'intitulé du lot {n}, tel qu'il est écrit dans le règlement.")
        if n in out:
            raise LotsInvalides(f"Le lot {n} est déjà dans la liste.")
        out[n] = {"numero": n, "intitule": _majuscule(intit), "phrase": "", "source": "", "origine": ORIGINE_UTILISATEUR}
    if len(out) > LOTS_CHOISIS_MAX:
        raise LotsInvalides(f"Un dossier de présentation couvre au plus {LOTS_CHOISIS_MAX} lots.")
    return sorted(out.values(), key=lambda x: _cle_num(x["numero"]))


def liste_out(lots: list) -> list:
    return [{"numero": x["numero"], "intitule": x.get("intitule") or "", "phrase": x.get("phrase") or "",
             "source": x.get("source") or "", "origine": x.get("origine") or ORIGINE_REGLEMENT,
             "origine_libelle": MSG_ORIGINE.get(x.get("origine") or ORIGINE_REGLEMENT, "")} for x in lots or []]


# ── 10. Groupement : « Qui écrit quoi » proposé d'après les lots (sans IA) ─────────────────────────────

def _lot_cite(texte: str, numero: str) -> bool:
    low = _fold(texte or "")
    for m in _MARQUE.finditer(low):
        if numero in _nums_de_marque(m):
            return True
    return False


def proposition_du_lot(section, candidats: list, lots: dict, mots_de, proches) -> Optional[dict]:
    """Pour la partie propre à un lot : le membre qui a déclaré CE lot (« Lot 2 », « lots 2 et 3 » dans sa part, ou
    les mots de l'intitulé du lot) — s'il est le seul. None : la règle ordinaire s'applique (partie commune, dossier
    à un seul lot). `mots_de` / `proches` : les règles de mots d'atelier_groupement (même début de mot)."""
    n = getattr(section, "lot", "") or ""
    if not n or n not in lots:
        return None
    intit = lots.get(n) or ""
    mots_lot = mots_de(intit)
    hits = []
    for m in candidats:
        if not m.get("peut_rediger") or not m.get("lot"):
            continue
        if _lot_cite(m["lot"], n):
            hits.append((2, m))
            continue
        if mots_lot and any(proches(w, c) for w in mots_de(m["lot"]) for c in mots_lot):
            hits.append((1, m))
    lib = f"lot {n}" + (f" (« {intit[:80]} »)" if intit else "")
    if not hits:
        return {"redacteur": "chef_de_file", "invite_id": None, "nom": "", "lot": "", "mots": [],
                "message": f"Proposé au chef de file : aucun partenaire n'a déclaré le {lib}."}
    hits.sort(key=lambda x: -x[0])
    if len(hits) > 1 and hits[0][0] == hits[1][0]:
        return {"redacteur": "chef_de_file", "invite_id": None, "nom": "", "lot": "", "mots": [],
                "message": f"Proposé au chef de file : plusieurs partenaires ont déclaré le {lib}, choisissez qui rédige."}
    m = hits[0][1]
    return {"redacteur": "partenaire", "invite_id": m["invite_id"], "nom": m["nom"], "lot": m["lot"], "mots": [],
            "message": f"Proposé d'après le lot de {m['nom']} (« {m['lot'][:80]} ») : cette partie est celle du {lib}."}
