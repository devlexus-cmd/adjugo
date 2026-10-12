"""
Texte INTÉGRAL du dossier du marché : rangement et accès commun pour tous les usages de l'IA
(analyse, questions-réponses, convention, atelier de rédaction).

Rangement (sans nouvelle table) : la lecture intégrale (app.services.dce_lecture), pièce par pièce
— nom, type reconnu, statut (lu en entier / en partie / non lu, avec la raison), nombre de
caractères et de pages, position des pages, texte — est rangée en UN fichier compressé dans le
stockage des fichiers du dossier (app.services.storage), référencé par `Project.dce_file_key`.
Ce champ est déjà traité partout où un marché disparaît : purge de la corbeille des marchés
(`rgpd._purge_trashed_projects`, `_tombstone_projects`), effacement du compte (`rgpd._erase_solo`)
et contrôle des références avant destruction d'un fichier (`rgpd._purge_files`). Le résumé de la
lecture (sans le texte) est dans `ai_analysis["lecture"]` et l'export RGPD le liste avec les
autres fichiers du dossier.

Le même fichier garde aussi, pour un gros dossier lu en deux temps, les informations relevées par
l'IA partie par partie (`analyse_parties`, phrases vérifiées) : une nouvelle analyse du même
dossier ne relit que les parties manquantes.

Accès commun (à utiliser par l'atelier de rédaction lors de la fusion) :
  • dce_pieces_text(project)   → [{nom, type, libelle, statut, raison, detail, caracteres, pages,
                                   pages_lues, page_starts, texte}] ou None ;
  • dce_fulltext(project, max_chars=None) → texte complet « === nom === », règlement et cadre de
                                   réponse en tête, ou None ;
  • dce_reglement(project)     → texte du ou des règlements de la consultation (RC, RC modificatif,
                                   RC de chaque lot : tous, avec leur en-tête « === nom === » quand
                                   il y en a plusieurs, le modificatif en premier) ou None ;
  • reglements(pieces)         → les pièces « règlement », modificatifs en premier ;
  • dce_texte_ou_extrait(project) → (texte, "integral" | "extrait" | "") : repli sur l'ancien
                                   extrait de 30 000 caractères pour les analyses antérieures ;
  • passages(project, question, k) → passages les plus pertinents de TOUTES les pièces (BM25
                                   sans accents ni pluriels : « penalites » retrouve « pénalité »),
                                   avec pièce et page ;
  • couverture(project)        → ce qui a été lu (message, pièces non lues et raisons) ;
  • pieces_remises(payload, n) → règlements puis cadres de réponse remis EN ENTIER (dans n
                                   caractères) et les numéros de ces pièces, à écarter de la recherche.
Le texte rendu par ces fonctions est la source contre laquelle toute citation est vérifiée
(analysis.citation_guard).
"""
import gzip
import json
import logging
import os
import re
import threading
import time
import uuid
import zlib
from collections import OrderedDict

from app.services import dce_lecture as lec
from app.services import dce_pieces as dp

logger = logging.getLogger("adjugo")

BUNDLE_VERSION = 1
FOLDER_KEY = "lecture"                  # préfixe de clé de stockage : {owner}/lecture/{uuid}.json.gz
MAX_BUNDLE_BYTES = 128 * 1024 * 1024    # décompression bornée du fichier relu (bombe gzip)

# Petit cache mémoire (process unique) : texte et index de recherche des derniers dossiers lus,
# pour qu'une série de questions ne relise pas le fichier à chaque fois. Borné en MÉMOIRE estimée :
# le texte compte 2 octets par caractère (un texte français contient presque toujours « ’ » ou
# « € », ce qui double la taille d'une chaîne Python) et l'index de recherche INDEX_OCTETS_PAR_CAR
# octets par caractère (mesuré avec tracemalloc sur 3 millions de caractères au vocabulaire très
# varié, pire cas : 10,7 octets par caractère ; construit en ≈ 2 s). Au plus 4 index gardés.
_CACHE_MAX_BYTES = int(os.getenv("LECTURE_CACHE_MO", "200")) * 1024 * 1024
_CACHE_MAX_ENTRIES = 32
_CACHE_MAX_INDEX = 4                     # dossiers dont l'index de recherche est gardé
TEXTE_OCTETS_PAR_CAR = 2
INDEX_OCTETS_PAR_CAR = 11
_CACHE_TTL_S = 1800.0
_CACHE = OrderedDict()                   # key -> (expire, octets, payload, index|None)
_LOCK = threading.Lock()


# ── Rangement ──────────────────────────────────────────────────────────────────────────

def _payload(lecture: dict) -> dict:
    keep = ("nom", "chemin", "format", "type", "libelle", "statut", "raison", "detail", "caracteres",
            "pages", "pages_lues", "pages_non_lues", "page_starts", "texte")
    out = {"version": BUNDLE_VERSION, "source": lecture.get("source") or "",
           "source_empreinte": lecture.get("source_empreinte") or "",
           "lu_le": lecture.get("lu_le"), "mode": lecture.get("mode"),
           "pieces": [{k: p.get(k) for k in keep} for p in (lecture.get("pieces") or [])]}
    parties = lecture.get("analyse_parties")
    if isinstance(parties, dict) and parties:
        # Informations relevées par l'IA pièce par pièce (lecture en deux temps), avec leur phrase
        # vérifiée : une nouvelle analyse du même dossier ne relit que ce qui manque.
        out["analyse_parties"] = dict(list(parties.items())[-PARTIES_MAX:])
    return out


PARTIES_MAX = 3000                       # parties lues par l'IA gardées avec la lecture


def ranger_parties(db, project, parties: dict) -> None:
    """Ajoute à la lecture rangée du marché les informations relevées par l'IA, partie par partie
    (même fichier, rangé à nouveau : supprimé avec le marché comme le texte)."""
    payload = charger(project)
    if not payload or not parties:
        return
    lecture = dict(payload)
    merged = dict(payload.get("analyse_parties") or {})
    merged.update(parties)
    lecture["analyse_parties"] = merged
    sauver(db, project, lecture)


def sauver(db, project, lecture: dict) -> str:
    """Range le texte intégral du dossier avec les fichiers du marché et le rattache au marché
    (Project.dce_file_key). Remplace la lecture précédente (fichier supprimé après le commit).
    Renvoie la clé de stockage."""
    from app.services.storage import get_storage
    data = gzip.compress(json.dumps(_payload(lecture), ensure_ascii=False).encode("utf-8"), compresslevel=6)
    owner = getattr(project, "user_id", None) or 0
    key = f"{owner}/{FOLDER_KEY}/{uuid.uuid4().hex}.json.gz"
    get_storage().save(key, data, "application/gzip")
    old = getattr(project, "dce_file_key", None)
    project.dce_file_key = key
    db.commit()
    if old and old != key:
        _forget(old)
        _delete_if_unreferenced(db, old)
    lecture["taille_stockee"] = len(data)
    return key


def _delete_if_unreferenced(db, key: str) -> None:
    try:
        from app.routers.rgpd import _purge_files
        _purge_files(db, [key])
    except Exception as e:      # noqa: BLE001 — jamais bloquant : la nouvelle lecture est en place
        logger.warning("ancienne lecture du dossier non supprimée : %s", type(e).__name__)


def supprimer(db, project) -> None:
    """Retire la lecture rangée d'un marché (fichier compris)."""
    key = getattr(project, "dce_file_key", None)
    if not key:
        return
    project.dce_file_key = None
    db.commit()
    _forget(key)
    _delete_if_unreferenced(db, key)


# ── Relecture ──────────────────────────────────────────────────────────────────────────

def _forget(key: str) -> None:
    with _LOCK:
        _CACHE.pop(key, None)


def _cache_get(key: str):
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and hit[0] > time.monotonic():
            _CACHE.move_to_end(key)
            return hit
        if hit:
            _CACHE.pop(key, None)
    return None


def _taille(payload: dict, index=None) -> int:
    """Mémoire estimée d'une entrée du cache (octets) : texte, et index de recherche s'il y en a un."""
    chars = sum(len(p.get("texte") or "") for p in payload.get("pieces") or [])
    return chars * (TEXTE_OCTETS_PAR_CAR + (INDEX_OCTETS_PAR_CAR if index is not None else 0))


def _cache_put(key: str, payload: dict, index=None) -> None:
    size = _taille(payload, index)
    if size > _CACHE_MAX_BYTES:
        return
    with _LOCK:
        _CACHE[key] = (time.monotonic() + _CACHE_TTL_S, size, payload, index)
        _CACHE.move_to_end(key)
        # Index de recherche gardés pour les derniers dossiers seulement (les plus lourds).
        with_idx = [k for k, v in _CACHE.items() if v[3] is not None]
        for k in with_idx[:-_CACHE_MAX_INDEX] if len(with_idx) > _CACHE_MAX_INDEX else []:
            exp, _sz, pl, _ix = _CACHE[k]
            _CACHE[k] = (exp, _taille(pl), pl, None)
        while len(_CACHE) > _CACHE_MAX_ENTRIES or sum(v[1] for v in _CACHE.values()) > _CACHE_MAX_BYTES:
            _CACHE.popitem(last=False)


def _gunzip_bounded(data: bytes) -> bytes:
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = d.decompress(data, MAX_BUNDLE_BYTES + 1)
    if len(out) > MAX_BUNDLE_BYTES or d.unconsumed_tail:
        raise ValueError("lecture rangée trop volumineuse")
    return out


def charger(project) -> dict:
    """Lecture rangée du marché (texte compris), ou None (analyse antérieure à la lecture
    intégrale, fichier absent ou illisible)."""
    key = getattr(project, "dce_file_key", None)
    if not key or f"/{FOLDER_KEY}/" not in key:
        return None
    hit = _cache_get(key)
    if hit:
        return hit[2]
    try:
        from app.services.storage import get_storage
        raw = get_storage().load(key)
        payload = json.loads(_gunzip_bounded(raw).decode("utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("pieces"), list):
            return None
    except Exception as e:      # noqa: BLE001
        logger.info("lecture rangée du marché %s illisible : %s", getattr(project, "id", "?"), type(e).__name__)
        return None
    _cache_put(key, payload)
    return payload


# ── Accès commun ───────────────────────────────────────────────────────────────────────

def dce_pieces_text(project) -> list:
    """Pièces du dossier avec leur texte intégral (ordre : règlement, cadre de réponse, acte
    d'engagement, CCAP, CCTP, bordereaux, autres), ou None."""
    payload = charger(project)
    if not payload:
        return None
    return [dict(p) for p in payload.get("pieces") or []]


def dce_fulltext(project, max_chars: int = None) -> str:
    """Texte complet du dossier, pièce par pièce (« === nom === »), règlement et cadre de réponse
    en tête et en entier. max_chars : plafond facultatif (règlement et cadre gardés en entier, le
    reste partagé équitablement, cf. dce_pieces.compose). None si aucune lecture n'est rangée."""
    payload = charger(project)
    if not payload:
        return None
    texte, _meta = lec.texte_integral(payload, max_chars=max_chars)
    return texte or None


_MODIFICATIF = ("modif", "rectif", "additif", "erratum", "complement", "avenant", "report")


def est_modificatif(piece: dict) -> bool:
    """Pièce qui modifie le dossier (RC modificatif, rectificatif, additif, erratum) : souvent la
    date limite reportée ; à lire AVANT la pièce d'origine."""
    return any(m in dp.fold(str(piece.get("nom") or "")) for m in _MODIFICATIF)


def reglements(pieces: list) -> list:
    """Les pièces « règlement de la consultation » lues (RC, RC modificatif, RC de chaque lot…),
    les modificatifs en premier, puis dans l'ordre du dossier."""
    regs = [p for p in pieces or [] if p.get("type") == dp.REGLEMENT and (p.get("texte") or "").strip()]
    return [p for p in regs if est_modificatif(p)] + [p for p in regs if not est_modificatif(p)]


def dce_reglement(project) -> str:
    """Texte du règlement de la consultation : TOUS les règlements reconnus parmi les pièces lues
    (le modificatif en premier), chacun précédé de « === nom === » s'il y en a plusieurs ; None
    s'il n'y en a aucun."""
    regs = reglements(dce_pieces_text(project) or [])
    if not regs:
        return None
    if len(regs) == 1:
        return regs[0]["texte"]
    return "\n\n".join(dp.header(p.get("nom")) + "\n" + p["texte"] for p in regs)


def pieces_remises(payload: dict, max_chars: int, min_debut: int = 4000) -> dict:
    """Pièces remises EN ENTIER à l'IA à chaque appel (atelier de rédaction, exigences) : TOUS les
    règlements de la consultation (modificatif en premier) puis TOUS les cadres de réponse, dans la
    limite de `max_chars` caractères au total. Une pièce qui n'y tient pas est remise en partie
    (son début, s'il reste au moins `min_debut` caractères), les suivantes pas du tout : leurs
    passages restent alors cherchés comme ceux des autres pièces (`passages`).
    Renvoie {"pieces": [{index, nom, type, libelle, texte, entier}], "entiers": {numéros des pièces
    remises en entier, à écarter de la recherche}, "texte": « === nom === » + texte de chacune}."""
    pieces = (payload or {}).get("pieces") or []
    index = {id(p): i for i, p in enumerate(pieces)}
    cadres = [p for p in pieces if p.get("type") == dp.CADRE and (p.get("texte") or "").strip()]
    room, out, entiers = max(0, int(max_chars or 0)), [], set()
    for p in reglements(pieces) + cadres:
        t = p.get("texte") or ""
        i = index[id(p)]
        x = {"index": i, "nom": p.get("nom") or "", "type": p.get("type"),
             "libelle": p.get("libelle") or dp.label(p.get("type"))}
        if len(t) <= room:
            out.append(dict(x, texte=t, entier=True))
            entiers.add(i)
            room -= len(t)
        elif room >= min_debut:
            out.append(dict(x, texte=t[:room], entier=False))
            room = 0
    parts = []
    for x in out:
        tag = "" if x["entier"] else f"\n[Début de la pièce seulement : ses {len(x['texte'])} premiers caractères.]"
        parts.append(dp.header(x["nom"]) + tag + "\n" + x["texte"])
    return {"pieces": out, "entiers": entiers, "texte": "\n\n".join(parts)}


def dce_texte_ou_extrait(project) -> tuple:
    """(texte, nature) : le texte intégral s'il est rangé (« integral »), sinon l'ancien extrait
    de l'analyse (« extrait », 30 000 caractères), sinon ("", "")."""
    t = dce_fulltext(project)
    if t:
        return t, "integral"
    a = getattr(project, "ai_analysis", None)
    ex = (a or {}).get("dce_excerpt") if isinstance(a, dict) else None
    if ex:
        return ex, "extrait"
    return "", ""


def couverture(project) -> dict:
    """Ce qui a été lu (message et pièces non lues), d'après la lecture rangée ; None sinon."""
    payload = charger(project)
    return lec.couverture(payload) if payload else None


# ── Recherche des passages pertinents (questions-réponses, atelier) ────────────────────
#
# BM25 lexical (sans IA, sans réseau), avec une normalisation COMMUNE au dossier et à la question :
# minuscules, accents retirés, apostrophes, pluriels et terminaisons muettes (« pénalités »,
# « penalites », « PÉNALITÉ » donnent le même mot). Index compact (tableaux d'entiers) : un dossier
# de 6 millions de caractères tient en quelques dizaines de Mo.

PASSAGE_CHARS = 1400                     # taille cible d'un passage
_K1, _B = 1.5, 0.75
_WORD_RE = re.compile(r"[a-z0-9]+")


def _stem(w: str) -> str:
    """Racinisation française légère et symétrique : pluriels (s, x, -aux → -al) et « e » muets
    finaux (« fixées » → « fixe », « pénalité » → « penalit »)."""
    if len(w) > 4 and w.endswith("aux"):
        w = w[:-3] + "al"
    elif len(w) > 3 and w[-1] in "sx":
        w = w[:-1]
    while len(w) > 4 and w.endswith("e"):
        w = w[:-1]
    return w


def _fold_table() -> dict:
    """Table de repli des lettres accentuées (Latin-1 et Latin étendu A) vers l'ASCII, pour
    str.translate (bien plus rapide qu'une normalisation caractère par caractère)."""
    import unicodedata
    t = {0x153: "oe", 0x152: "oe", 0xE6: "ae", 0xC6: "ae", 0xDF: "ss", 0x2019: "'", 0x2018: "'"}
    for cp in range(0xC0, 0x250):
        if cp in t:
            continue
        d = "".join(x for x in unicodedata.normalize("NFKD", chr(cp)) if not unicodedata.combining(x))
        if d and d != chr(cp) and d.isascii():
            t[cp] = d.lower()
    return t


_FOLD = _fold_table()


def norm_tokens(text: str) -> list:
    """Mots d'un texte pour la recherche : sans accents, en minuscules, racinisés ; sans mots vides
    ni petits nombres (numéros d'article, années partielles)."""
    from app.services.rag import _STOP
    out = []
    for w in _WORD_RE.findall((text or "").lower().translate(_FOLD)):
        if len(w) <= 2 or w in _STOP or (w.isdigit() and len(w) < 4):
            continue
        out.append(_stem(w))
    return out


def _chunks(texte: str, target: int = PASSAGE_CHARS) -> list:
    """Découpe une pièce en passages d'environ `target` caractères, sur des fins de paragraphe ou
    de ligne quand c'est possible. Renvoie [(debut, fin)] — positions dans le texte de la pièce."""
    out, n, start = [], len(texte), 0
    while start < n:
        end = min(n, start + target)
        if end < n:
            cut = texte.rfind("\n\n", start + target // 2, end)
            if cut < 0:
                cut = texte.rfind("\n", start + target // 2, end)
            if cut < 0:
                cut = texte.rfind(". ", start + target // 2, end)
            if cut > start:
                end = cut + 1
        if texte[start:end].strip():
            out.append((start, end))
        start = end
    return out


def _index(payload: dict) -> dict:
    from array import array
    from collections import Counter
    spans, doc_len, postings, total = [], array("I"), {}, 0
    for pi, p in enumerate(payload.get("pieces") or []):
        t = p.get("texte") or ""
        for a, b in _chunks(t):
            toks = norm_tokens(t[a:b])
            i = len(spans)
            spans.append((pi, a, b))
            doc_len.append(len(toks))
            total += len(toks)
            for w, c in Counter(toks).items():
                e = postings.get(w)
                if e is None:
                    e = postings[w] = (array("I"), array("H"))
                e[0].append(i)
                e[1].append(min(c, 65535))
    n = len(spans)
    return {"postings": postings, "doc_len": doc_len, "N": n, "avgdl": (total / n) if n else 0.0,
            "spans": spans}


def _search(idx: dict, question: str, k: int, keep=None) -> list:
    """[(score, numéro du passage)] les k meilleurs, BM25 ; keep(numéro) : passages admis."""
    import heapq
    import math
    n = idx["N"]
    q = list(dict.fromkeys(norm_tokens(question)))
    if not n or not q:
        return []
    avgdl = idx["avgdl"] or 1.0
    doc_len, scores = idx["doc_len"], {}
    for w in q:
        e = idx["postings"].get(w)
        if not e:
            continue
        df = len(e[0])
        idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
        for i, tf in zip(e[0], e[1]):
            dl = doc_len[i]
            scores[i] = scores.get(i, 0.0) + idf * (tf * (_K1 + 1)) / (tf + _K1 * (1 - _B + _B * dl / avgdl))
    return heapq.nlargest(k, ((sc, i) for i, sc in scores.items() if keep is None or keep(i)))


def _index_for(project, payload: dict):
    key = getattr(project, "dce_file_key", None)
    hit = _cache_get(key) if key else None
    if hit and hit[3] is not None:
        return hit[3]
    idx = _index(payload)
    if key:
        _cache_put(key, payload, idx)
    return idx


def passages(project, question: str, k: int = 8, exclude_types=(), payload: dict = None,
             exclude_pieces=()) -> list:
    """Les k passages du dossier les plus pertinents pour `question`, dans TOUTES les pièces lues
    (BM25 normalisé, sans IA, sans réseau). Chaque passage : {piece, type, libelle, page, debut,
    fin, texte, score, piece_index}. exclude_pieces : numéros des pièces déjà remises EN ENTIER à
    l'IA (ex. le ou les règlements) ; exclude_types : types de pièces à écarter."""
    payload = payload or charger(project)
    if not payload:
        return []
    idx = _index_for(project, payload)
    pieces = payload.get("pieces") or []
    want = max(1, int(k))
    ex = set(exclude_pieces or ())
    skip = {i for i, p in enumerate(pieces) if i in ex or p.get("type") in exclude_types}
    spans = idx["spans"]
    out = []
    for score, i in _search(idx, question or "", want, keep=(lambda j: spans[j][0] not in skip) if skip else None):
        pi, a, b = spans[i]
        p = pieces[pi]
        out.append({"piece": p.get("nom") or "", "type": p.get("type"), "libelle": p.get("libelle") or "",
                    "page": lec.page_of(p, a), "debut": a, "fin": b, "texte": (p.get("texte") or "")[a:b],
                    "score": round(score, 3), "piece_index": pi})
        if len(out) >= want:
            break
    return out
