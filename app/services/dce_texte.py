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

Accès commun (à utiliser par l'atelier de rédaction lors de la fusion) :
  • dce_pieces_text(project)   → [{nom, type, libelle, statut, raison, detail, caracteres, pages,
                                   pages_lues, page_starts, texte}] ou None ;
  • dce_fulltext(project, max_chars=None) → texte complet « === nom === », règlement et cadre de
                                   réponse en tête, ou None ;
  • dce_reglement(project)     → texte du règlement de la consultation (s'il est reconnu) ou None ;
  • dce_texte_ou_extrait(project) → (texte, "integral" | "extrait" | "") : repli sur l'ancien
                                   extrait de 30 000 caractères pour les analyses antérieures ;
  • passages(project, question, k) → passages les plus pertinents de TOUTES les pièces (BM25,
                                   app.services.rag), avec pièce et page ;
  • couverture(project)        → ce qui a été lu (message, pièces non lues et raisons).
Le texte rendu par ces fonctions est la source contre laquelle toute citation est vérifiée
(analysis.citation_guard).
"""
import gzip
import json
import logging
import os
import threading
import time
import uuid
import zlib
from collections import OrderedDict, namedtuple

from app.services import dce_lecture as lec
from app.services import dce_pieces as dp

logger = logging.getLogger("adjugo")

BUNDLE_VERSION = 1
FOLDER_KEY = "lecture"                  # préfixe de clé de stockage : {owner}/lecture/{uuid}.json.gz
MAX_BUNDLE_BYTES = 128 * 1024 * 1024    # décompression bornée du fichier relu (bombe gzip)

# Petit cache mémoire (process unique) : texte et index de recherche des derniers dossiers lus,
# pour qu'une série de questions ne relise pas le fichier à chaque fois. Borné en caractères.
_CACHE_MAX_CHARS = int(os.getenv("LECTURE_CACHE_CARACTERES", "30000000"))
_CACHE_MAX_ENTRIES = 32
_CACHE_TTL_S = 1800.0
_CACHE = OrderedDict()                   # key -> (expire, chars, payload, index|None)
_LOCK = threading.Lock()


# ── Rangement ──────────────────────────────────────────────────────────────────────────

def _payload(lecture: dict) -> dict:
    keep = ("nom", "chemin", "format", "type", "libelle", "statut", "raison", "detail", "caracteres",
            "pages", "pages_lues", "pages_non_lues", "page_starts", "texte")
    return {"version": BUNDLE_VERSION, "source": lecture.get("source") or "",
            "source_empreinte": lecture.get("source_empreinte") or "",
            "lu_le": lecture.get("lu_le"), "mode": lecture.get("mode"),
            "pieces": [{k: p.get(k) for k in keep} for p in (lecture.get("pieces") or [])]}


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


def _cache_put(key: str, payload: dict, index=None) -> None:
    chars = sum(len(p.get("texte") or "") for p in payload.get("pieces") or [])
    chars *= 2 if index is not None else 1      # l'index de recherche garde une copie des passages
    if chars > _CACHE_MAX_CHARS:
        return
    with _LOCK:
        _CACHE[key] = (time.monotonic() + _CACHE_TTL_S, chars, payload, index)
        _CACHE.move_to_end(key)
        while len(_CACHE) > _CACHE_MAX_ENTRIES or sum(v[1] for v in _CACHE.values()) > _CACHE_MAX_CHARS:
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


def dce_reglement(project) -> str:
    """Texte du règlement de la consultation, s'il est reconnu parmi les pièces lues."""
    for p in dce_pieces_text(project) or []:
        if p.get("type") == dp.REGLEMENT and p.get("texte"):
            return p["texte"]
    return None


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

PASSAGE_CHARS = 1400                     # taille cible d'un passage
_Row = namedtuple("_Row", "id doc_id doc_name ordinal user_id text")


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


def _index(payload: dict):
    from app.services import rag
    rows, spans = [], []
    for pi, p in enumerate(payload.get("pieces") or []):
        t = p.get("texte") or ""
        for j, (a, b) in enumerate(_chunks(t)):
            rows.append(_Row(len(rows), pi, p.get("nom") or "", j, 0, t[a:b]))
            spans.append((pi, a, b))
    return {"bm25": rag._build_index(rows), "spans": spans}


def _index_for(project, payload: dict):
    key = getattr(project, "dce_file_key", None)
    hit = _cache_get(key) if key else None
    if hit and hit[3] is not None:
        return hit[3]
    idx = _index(payload)
    if key:
        _cache_put(key, payload, idx)
    return idx


def passages(project, question: str, k: int = 8, exclude_types=(), payload: dict = None) -> list:
    """Les k passages du dossier les plus pertinents pour `question`, dans TOUTES les pièces lues
    (BM25 lexical, sans IA, sans réseau). Chaque passage : {piece, type, libelle, page, debut,
    fin, texte, score}. exclude_types : types de pièces déjà remises en entier (ex. règlement)."""
    from app.services import rag
    payload = payload or charger(project)
    if not payload:
        return []
    idx = _index_for(project, payload)
    pieces = payload.get("pieces") or []
    want = max(1, int(k))
    hits = rag._bm25_indexed(idx["bm25"], question or "", want * 3 + 6)
    out = []
    for score, meta in hits:
        pi, a, b = idx["spans"][meta[0]]
        p = pieces[pi]
        if p.get("type") in exclude_types:
            continue
        out.append({"piece": p.get("nom") or "", "type": p.get("type"), "libelle": p.get("libelle") or "",
                    "page": lec.page_of(p, a), "debut": a, "fin": b, "texte": (p.get("texte") or "")[a:b],
                    "score": round(score, 3), "piece_index": pi})
        if len(out) >= want:
            break
    return out
