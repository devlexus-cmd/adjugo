"""
Lecture INTÉGRALE du dossier du marché, pièce par pièce (consigne : « on ne peut pas avoir que
la moitié de l'appel d'offres analysé »).

Chaque pièce est lue EN ENTIER : PDF texte (page par page), Word, tableurs (.xlsx, .ods),
OpenDocument (.odt), textes, CSV ; les pages scannées et les images passent par la
reconnaissance de caractères (OCR) en tâche de fond. Les plafonds sont TECHNIQUES (ils protègent
le process unique : mémoire, temps, bombes de décompression), larges et réglables par variables
d'environnement. Toute pièce ou page non lue est SIGNALÉE avec sa raison (scan illisible, format
non pris en charge, fichier protégé, plafond technique atteint, temps écoulé) : jamais un « lu en
entier » faux.

Deux modes :
  • « direct » (pendant la requête d'import, sans OCR, budget de temps court) : suffit pour la
    plupart des dossiers ; dit s'il faut continuer en tâche de fond (pages scannées à lire, temps
    écoulé) ;
  • « fond » (tâche de fond, OCR compris, budget de temps large) : reprend les pièces déjà lues
    en entier par le mode direct et lit le reste.

Aucune IA ici. Les primitives de lecture bornée (ZIP en flux, tailles des .docx, pages de PDF,
rendu OCR) sont celles d'app.services.analysis.
"""
import io
import logging
import os
import time
import zipfile
from datetime import datetime, timezone

from app.services import analysis as an
from app.services import dce_pieces as dp

logger = logging.getLogger("adjugo")
MB = 1024 * 1024


def _env_int(name: str, default: int) -> int:
    try:
        v = int(str(os.getenv(name, "")).strip() or default)
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        v = float(str(os.getenv(name, "")).strip() or default)
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default


# ── Plafonds TECHNIQUES (réglables) ───────────────────────────────────────────────────
# Un vrai dossier (RC + CCAP + CCTP de 10 lots + bordereaux + plans, ~40 Mo zippés, quelques
# milliers de pages) reste très en dessous. Au-delà, la pièce est signalée « non lue » ou « lue
# en partie » avec la raison « plafond technique ».
MAX_FICHIERS = _env_int("LECTURE_MAX_FICHIERS", 400)                 # pièces lues dans une archive
MAX_OCTETS_FICHIER = _env_int("LECTURE_MAX_MO_FICHIER", 80) * MB     # une pièce, décompressée
MAX_OCTETS_TOTAL = _env_int("LECTURE_MAX_MO_TOTAL", 400) * MB        # cumul décompressé lu
MAX_CARACTERES_PIECE = _env_int("LECTURE_MAX_CARACTERES_PIECE", 3_000_000)   # ≈ 1 000 pages
MAX_CARACTERES_TOTAL = _env_int("LECTURE_MAX_CARACTERES", 6_000_000)         # tout le dossier
MAX_PAGES_PDF = _env_int("LECTURE_MAX_PAGES_PDF", 5000)
MAX_MO_CONTENU_PDF = _env_int("LECTURE_MAX_MO_CONTENU_PDF", 600) * MB  # contenu décompressé des pages
TEMPS_DIRECT_S = _env_float("LECTURE_TEMPS_DIRECT_S", 20.0)          # lecture pendant la requête
TEMPS_FOND_S = _env_float("LECTURE_TEMPS_FOND_S", 1200.0)            # tâche de fond, OCR compris
OCR_MAX_PAGES = _env_int("LECTURE_OCR_MAX_PAGES", 300)               # pages en image lues par OCR

# Formats lus. Les autres sont SIGNALÉS (jamais ignorés en silence).
FORMATS = {".pdf": "pdf", ".docx": "docx", ".docm": "docx", ".xlsx": "xlsx", ".xlsm": "xlsx",
           ".ods": "ods", ".odt": "odt",
           ".txt": "texte", ".md": "texte", ".csv": "texte",
           ".png": "image", ".jpg": "image", ".jpeg": "image", ".tif": "image", ".tiff": "image"}
# Formats reconnus mais non lisibles : conseil donné à l'utilisateur.
CONSEILS = {".doc": "ancien format Word : enregistrez-le en .docx ou en PDF",
            ".xls": "ancien format Excel : enregistrez-le en .xlsx ou en PDF",
            ".rtf": "enregistrez-le en .docx ou en PDF",
            ".dwg": "plan au format de dessin : demandez-en une version PDF",
            ".dxf": "plan au format de dessin : demandez-en une version PDF",
            ".pptx": "présentation : enregistrez-la en PDF",
            ".ppt": "présentation : enregistrez-la en PDF",
            ".odp": "présentation : enregistrez-la en PDF",
            ".7z": "archive non prise en charge : envoyez un .zip",
            ".rar": "archive non prise en charge : envoyez un .zip"}

LU = "lu_en_entier"
PARTIEL = "lu_en_partie"
NON_LU = "non_lu"

# Raisons (texte affiché à l'utilisateur, sans jargon).
RAISONS = {
    "format": "format non pris en charge",
    "protege": "fichier protégé par un mot de passe",
    "illisible": "fichier abîmé ou illisible",
    "vide": "aucun texte dans ce fichier",
    "scan_illisible": "scan : aucun texte reconnu",
    "scan_a_lire": "pages en image : lecture en cours",
    "ocr_indisponible": "pages en image : la lecture des images n'est pas disponible",
    "trop_gros": "fichier trop volumineux une fois décompressé",
    "imbrique": "archive placée dans une archive elle-même dans une archive",
    "compression": "compression de l'archive non prise en charge",
    "plafond_fichiers": "plafond technique : trop de fichiers dans l'archive",
    "plafond_volume": "plafond technique : volume total de l'archive atteint",
    "plafond_caracteres": "plafond technique : texte trop long",
    "plafond_pages": "plafond technique : trop de pages",
    "plafond_ocr": "plafond technique : trop de pages en image à lire",
    "temps": "temps de lecture écoulé",
    "lourde": "pages de plan ou de dessin trop lourdes",
    "rendu": "pages en image impossibles à ouvrir",
    "coupee": "page interrompue (trop longue à lire)",
    "page_illisible": "pages abîmées ou illisibles",
}

_PAGE_RAISON = {"lourde": "lourde", "temps": "temps", "plafond": "plafond_pages",
                "plafond_caracteres": "plafond_caracteres", "coupee": "coupee",
                "image": "scan_a_lire", "plafond_ocr": "plafond_ocr", "ocr_indisponible": "ocr_indisponible",
                "rendu": "rendu", "scan_illisible": "scan_illisible"}


def raison_texte(code: str) -> str:
    return RAISONS.get(code or "", code or "")


def _ext(name: str) -> str:
    return os.path.splitext(str(name or "").lower())[1]


def _is_noise(path: str) -> bool:
    """Fichiers système d'une archive (pas des pièces) : __MACOSX, fichiers cachés, Thumbs.db."""
    base = os.path.basename(path)
    return (not base or base.startswith(".") or "__MACOSX/" in path.replace("\\", "/")
            or base.lower() in ("thumbs.db", "desktop.ini"))


class _Etat:
    """Budget et suivi d'une lecture (archive imbriquée comprise)."""

    def __init__(self, mode: str, progress=None):
        self.mode = mode
        fond = mode == "fond"
        self.budget = an._Budget(total_bytes=MAX_OCTETS_TOTAL,
                                 ocr_pages=OCR_MAX_PAGES if fond else 0,
                                 time_s=TEMPS_FOND_S if fond else TEMPS_DIRECT_S,
                                 pdf_content=MAX_MO_CONTENU_PDF)
        self.ocr = fond and an.ocr_available()
        self.chars = 0
        self.fichiers = 0
        self.progress = progress
        self.pieces = []
        self.besoin_fond = False     # lecture directe : des pages restent à lire en tâche de fond
        self.t0 = time.monotonic()

    def expired(self) -> bool:
        return time.monotonic() > self.budget.deadline

    def tick(self, en_cours: str = ""):
        if self.progress is None:
            return
        try:
            self.progress({"etape": "lecture", "pieces_lues": len(self.pieces),
                           "pages_lues": sum(int(p.get("pages_lues") or 0) for p in self.pieces),
                           "piece_en_cours": en_cours[:120]})
        except Exception:
            pass


def _piece(nom: str, chemin: str, fmt: str) -> dict:
    return {"nom": nom, "chemin": chemin, "format": fmt, "type": dp.AUTRE, "libelle": dp.label(dp.AUTRE),
            "statut": NON_LU, "raison": "", "detail": "", "caracteres": 0, "pages": None,
            "pages_lues": None, "pages_non_lues": [], "texte": "", "page_starts": None}


def _finish(p: dict, texte: str, complet: bool, raison: str = "", detail: str = "") -> dict:
    texte = (texte or "").rstrip("\n")
    lead = len(texte) - len(texte.lstrip("\n"))
    if lead:
        # Pages sans texte en tête (page blanche, couverture en image) : les positions de début
        # de page suivent le texte (sinon toutes les pages citées seraient décalées).
        texte = texte[lead:]
        if p.get("page_starts"):
            p["page_starts"] = [max(0, st - lead) for st in p["page_starts"]]
    p["texte"] = texte
    p["caracteres"] = len(texte)
    p["type"] = dp.classify_piece(p["nom"], texte)
    p["libelle"] = dp.label(p["type"])
    if not texte.strip():
        p["statut"] = NON_LU
        p["raison"] = raison or "vide"
    else:
        p["statut"] = LU if complet else PARTIEL
        p["raison"] = "" if complet else (raison or "plafond_caracteres")
    p["detail"] = detail or (raison_texte(p["raison"]) if p["raison"] else "")
    return p


def _cap_text(etat: _Etat, texte: str):
    """Plafond de caractères (pièce et dossier) : renvoie (texte gardé, coupé ?)."""
    room = max(0, min(MAX_CARACTERES_PIECE, MAX_CARACTERES_TOTAL - etat.chars))
    if len(texte) > room:
        return texte[:room], True
    return texte, False


# ── PDF ───────────────────────────────────────────────────────────────────────────────

def _assemble_pages(pages: list) -> tuple:
    """Texte d'un PDF à partir de ses pages (dans l'ordre) + position de début de chaque page
    (page_starts[i] = début de la page i+1 dans le texte)."""
    parts, starts, pos = [], [], 0
    for pg in pages:
        starts.append(pos)
        t = (pg.get("texte") or "").strip("\n")
        if t:
            parts.append(t)
            pos += len(t) + 2
        else:
            parts.append("")
            pos += 2
    return "\n\n".join(parts), starts


def _detail_pages(non_lues: dict, total: int) -> tuple:
    """(raison principale, texte « 12 pages sur 340 non lues : temps de lecture écoulé »)."""
    if not non_lues:
        return "", ""
    by = {}
    for _n, r in non_lues.items():
        by[r] = by.get(r, 0) + 1
    main = max(by.items(), key=lambda kv: kv[1])[0]
    n = len(non_lues)
    causes = ", ".join(f"{raison_texte(r)}" + (f" ({k})" if len(by) > 1 else "")
                       for r, k in sorted(by.items(), key=lambda kv: -kv[1]))
    return main, f"{n} page{'s' if n > 1 else ''} sur {total} non lue{'s' if n > 1 else ''} : {causes}"


def _avec_bandeau(tape: str, reconnu: str) -> str:
    """Texte d'une page scannée : le texte reconnu, précédé du bandeau tapé de la page (« Annexe 2
    – document numérisé ») s'il n'y figure pas déjà tel quel (citations vérifiables mot pour mot)."""
    t = " ".join((tape or "").split())
    if not t or " ".join(dp.fold(t).split()) in " ".join(dp.fold(reconnu).split()):
        return reconnu
    return tape.strip() + "\n" + reconnu


def _pages_precedentes(prev: dict) -> dict:
    """Texte des pages LUES par une lecture précédente de la même pièce (PDF) : {numéro: texte}.
    Sert à ne pas refaire la reconnaissance de caractères des pages déjà reconnues (une relecture
    avance au lieu de recommencer)."""
    if not isinstance(prev, dict) or prev.get("format") != "pdf" or not prev.get("page_starts"):
        return {}
    non = set(prev.get("pages_non_lues") or [])
    if len(non) >= 2000:                       # liste tronquée : pas de reprise page à page
        return {}
    starts, t, out = prev["page_starts"], prev.get("texte") or "", {}
    for i, st in enumerate(starts):
        if i + 1 in non:
            continue
        end = starts[i + 1] if i + 1 < len(starts) else len(t)
        out[i + 1] = t[st:end].strip("\n")
    return out


def _read_pdf(etat: _Etat, data: bytes, p: dict, prev: dict = None) -> dict:
    info, pages = {}, []
    an.extract_text_from_pdf(data, max_pages=MAX_PAGES_PDF,
                             max_chars=max(1, min(MAX_CARACTERES_PIECE, MAX_CARACTERES_TOTAL - etat.chars)),
                             budget=etat.budget, info=info, pages_out=pages)
    if info.get("protege"):
        return _finish(p, "", False, "protege")
    total = int(info.get("pages") or len(pages) or 0)
    p["pages"] = total
    if not pages and total == 0:
        return _finish(p, "", False, "illisible")
    # Pages en image (scans) : OCR en tâche de fond ; en direct, signalées « à lire ».
    a_lire = [pg["num"] for pg in pages if pg["etat"] == "image"]
    # PDF entièrement scanné (aucun texte sur aucune page) : toutes les pages sont à lire.
    if not any(len((pg.get("texte") or "").strip()) >= 20 for pg in pages):
        a_lire = [pg["num"] for pg in pages if pg["etat"] in ("image", "vide", "lu")]
    # Relecture : les pages déjà reconnues par une lecture précédente sont reprises telles quelles.
    deja = _pages_precedentes(prev) if a_lire else {}
    if deja:
        sel = set(a_lire)
        for pg in pages:
            if pg["num"] in sel and (deja.get(pg["num"]) or "").strip():
                pg["texte"], pg["etat"] = deja[pg["num"]], "lu"
        a_lire = [n for n in a_lire if not (deja.get(n) or "").strip()]
    non_lues = {}
    if a_lire:
        if etat.ocr:
            res = {}
            out = an.ocr_pdf_pages(data, a_lire, etat.budget, res)
            for pg in pages:
                if pg["num"] in res:
                    txt = res[pg["num"]] or ""
                    if txt.strip():
                        pg["texte"], pg["etat"] = _avec_bandeau(pg.get("texte") or "", txt), "lu"
                    else:
                        pg["etat"] = "scan_illisible"      # le bandeau tapé, s'il y en a un, reste
                elif pg["num"] in out["non_lues"]:
                    pg["etat"] = out["non_lues"][pg["num"]]
        else:
            # Lecture directe : ces pages seront lues en tâche de fond. En tâche de fond sans
            # reconnaissance de caractères installée : signalées comme telles.
            code = "image" if etat.mode == "direct" else "ocr_indisponible"
            if etat.mode == "direct":
                etat.besoin_fond = True
            sel = set(a_lire)
            for pg in pages:
                if pg["num"] in sel:
                    pg["etat"] = code
    for pg in pages:
        if pg["etat"] in _PAGE_RAISON:
            non_lues[pg["num"]] = _PAGE_RAISON[pg["etat"]]
    # Lecture interrompue par une erreur du fichier : les pages jamais atteintes sont nommées.
    vues = {pg["num"] for pg in pages}
    for n in range(1, total + 1):
        if n not in vues:
            non_lues[n] = "page_illisible"
            pages.append({"num": n, "texte": "", "etat": "page_illisible"})
    pages.sort(key=lambda pg: pg["num"])
    texte, starts = _assemble_pages(pages)
    texte, coupe = _cap_text(etat, texte)
    if coupe:
        for i, st in enumerate(starts):
            if st >= len(texte):
                non_lues.setdefault(i + 1, "plafond_caracteres")
    p["page_starts"] = starts
    p["pages_non_lues"] = sorted(non_lues)[:2000]
    p["pages_lues"] = max(0, total - len(non_lues))
    main, detail = _detail_pages(non_lues, total)
    if not texte.strip():
        # Rien de lisible : scan sans OCR possible, scan illisible…
        code = main or "vide"
        if code in ("scan_a_lire", "ocr_indisponible", "scan_illisible", "temps", "plafond_ocr"):
            return _finish(p, "", False, code, raison_texte(code))
        return _finish(p, "", False, code, detail)
    return _finish(p, texte, not non_lues, main, detail)


# ── Autres formats ─────────────────────────────────────────────────────────────────────

def _read_data(etat: _Etat, nom: str, chemin: str, data: bytes, prev: dict = None) -> dict:
    ext = _ext(nom)
    fmt = FORMATS.get(ext, "")
    if not fmt and data[:5] == b"%PDF-":
        fmt = "pdf"                      # PDF sans extension (ou mal nommé)
    p = _piece(nom, chemin, fmt or ext.lstrip(".") or "inconnu")
    if not fmt:
        return _finish(p, "", False, "format", f"{raison_texte('format')}"
                       + (f" ({CONSEILS[ext]})" if ext in CONSEILS else ""))
    if not data:
        return _finish(p, "", False, "vide")
    if etat.chars >= MAX_CARACTERES_TOTAL:
        return _finish(p, "", False, "plafond_caracteres")
    if fmt == "pdf" or data[:5] == b"%PDF-":
        p["format"] = "pdf"
        return _read_pdf(etat, data, p, prev)
    if fmt in ("docx", "xlsx", "ods", "odt"):
        code = _office_chiffre(data, ext)
        if code:
            return _finish(p, "", False, code[0], code[1])
    info = {"complet": True}
    if fmt == "docx":
        if not an._docx_sizes_ok(data):
            # Archive trop volumineuse une fois décompressée, ou fichier qui n'est pas une archive
            # Word (abîmé) : deux raisons différentes, dites telles quelles.
            return _finish(p, "", False, "trop_gros" if _est_archive(data) else "illisible")
        t = an._extract_docx(data, info=info)
        if not t:
            return _finish(p, "", False, "illisible")
    elif fmt == "xlsx":
        t = an.extract_xlsx(data, info=info)
        if not t:
            return _finish(p, "", False, "illisible" if not an._office_parts_ok(data) else "vide")
    elif fmt in ("ods", "odt"):
        t = an.extract_odf(data, info=info)
        if not t:
            return _finish(p, "", False, "illisible" if not an._office_parts_ok(data) else "vide")
    elif fmt == "image":
        p["pages"] = 1
        if not etat.ocr:
            code = "scan_a_lire" if etat.mode == "direct" else "ocr_indisponible"
            if etat.mode == "direct":
                etat.besoin_fond = True
            p["pages_lues"], p["pages_non_lues"] = 0, [1]
            return _finish(p, "", False, code)
        t, raison = an.ocr_image(data, etat.budget)
        p["pages_lues"] = 1 if t.strip() else 0
        p["pages_non_lues"] = [] if t.strip() else [1]
        if not t.strip():
            return _finish(p, "", False, raison or "scan_illisible")
    else:   # texte, csv, md — UTF-8, sinon Windows-1252 (CSV exportés par Excel)
        try:
            t = data.decode("utf-8")
        except UnicodeDecodeError:
            t = data.decode("cp1252", errors="replace")
    t, coupe = _cap_text(etat, t)
    complet = bool(info.get("complet", True)) and not coupe
    return _finish(p, t, complet, "" if complet else "plafond_caracteres")


def _est_archive(data: bytes) -> bool:
    """Le fichier est-il une archive ZIP lisible ? (Nombre d'entrées vérifié AVANT d'ouvrir.)"""
    if data[:2] != b"PK":
        return False
    if not an._zip_entry_count_ok(data):
        return True                      # archive, mais trop complexe
    try:
        with zipfile.ZipFile(io.BytesIO(data)):
            return True
    except Exception:
        return False


_CFB = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"      # conteneur OLE (Office chiffré ou ancien format)
_ENCRYPTED_PACKAGE = "EncryptedPackage".encode("utf-16-le")


def _office_chiffre(data: bytes, ext: str):
    """(raison, détail) si un fichier Office n'est pas lisible en l'état : protégé par un mot de
    passe (Word ou Excel enregistré avec mot de passe : conteneur chiffré, pas une archive ;
    OpenDocument : contenu chiffré dans l'archive) ou ancien format binaire renommé. None sinon."""
    if data[:8] == _CFB:
        if _ENCRYPTED_PACKAGE in data:
            return ("protege", raison_texte("protege") + " : demandez à l'acheteur une version sans mot de passe")
        # Sans la marque du chiffrement : le plus souvent un fichier protégé tout de même, parfois
        # un ancien format (.doc, .xls) renommé. Les deux causes sont dites.
        return ("protege", raison_texte("protege") + " ou ancien format renommé : demandez à l'acheteur "
                "une version sans mot de passe, en PDF ou au format actuel")
    if ext in (".odt", ".ods") and data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                info = z.getinfo("META-INF/manifest.xml")
                if info.file_size <= 2 * MB and info.compress_type in an._ZIP_SAFE_COMPRESSION:
                    if b"encryption-data" in z.read(info):
                        return ("protege", raison_texte("protege")
                                + " : demandez à l'acheteur une version sans mot de passe")
        except Exception:
            return None
    return None


# ── Archive ────────────────────────────────────────────────────────────────────────────

def _pdf_magic(zf, info) -> bool:
    """Le membre commence-t-il par « %PDF- » ? Lecture de 5 octets seulement."""
    try:
        if info.compress_type not in an._ZIP_SAFE_COMPRESSION:
            return False
        with zf.open(info) as fh:
            return fh.read(5) == b"%PDF-"
    except Exception:
        return False


def _read_zip(etat: _Etat, content: bytes, depth: int, prefix: str, reprise: dict) -> None:
    if not an._zip_entry_count_ok(content):
        raise ValueError("Archive ZIP trop complexe (trop de fichiers). "
                         "Importez directement les pièces utiles (RC, CCAP, CCTP, DPGF).")
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except Exception:
        raise ValueError("Archive ZIP corrompue ou illisible.")
    with zf:
        def _rank(i):
            ln = i.filename.lower()
            if ln.endswith(".zip"):
                return (9, 2, ln)
            kind, _sure = dp.classify_name(os.path.basename(i.filename))
            return (dp.read_rank(kind), 0 if ln.endswith(".pdf") else 1, ln)
        for info in sorted(zf.infolist(), key=_rank):
            n = info.filename
            if info.is_dir() or _is_noise(n):
                continue
            chemin = (prefix + n)[:500]
            nom = os.path.basename(n)
            ext = _ext(nom)
            is_zip = ext == ".zip"
            if is_zip and depth >= an.ZIP_MAX_DEPTH:
                etat.pieces.append(_finish(_piece(nom, chemin, "zip"), "", False, "imbrique"))
                continue
            if not is_zip and etat.fichiers >= MAX_FICHIERS:
                etat.pieces.append(_finish(_piece(nom, chemin, FORMATS.get(ext, ext.lstrip("."))), "", False,
                                           "plafond_fichiers"))
                continue
            # Reprise (tâche de fond) : pièce déjà lue en entier par la lecture directe.
            prev = reprise.get(chemin)
            if prev is not None and prev.get("statut") == LU and prev.get("texte"):
                etat.fichiers += 1
                etat.chars += len(prev["texte"])
                etat.pieces.append(dict(prev))
                etat.tick(nom)
                continue
            if info.compress_type not in an._ZIP_SAFE_COMPRESSION:
                etat.pieces.append(_finish(_piece(nom, chemin, FORMATS.get(ext, ext.lstrip("."))), "", False,
                                           "compression"))
                continue
            if not is_zip and ext not in FORMATS and not _pdf_magic(zf, info):
                # Format non lisible : signalé SANS décompresser le fichier (seul son en-tête est lu,
                # pour reconnaître un PDF sans extension).
                etat.fichiers += 1
                etat.pieces.append(_read_data(etat, nom, chemin, b""))
                continue
            if etat.expired():
                # Temps écoulé : la pièce n'est pas ouverte (lue en tâche de fond si c'est la
                # lecture directe, signalée « temps de lecture écoulé » sinon).
                if etat.mode == "direct":
                    etat.besoin_fond = True
                etat.pieces.append(_finish(_piece(nom, chemin, FORMATS.get(ext, "zip")), "", False, "temps"))
                continue
            if etat.budget.bytes_left <= 0:
                etat.pieces.append(_finish(_piece(nom, chemin, FORMATS.get(ext, "zip")), "", False,
                                           "plafond_volume"))
                continue
            if info.file_size > MAX_OCTETS_FICHIER:
                etat.pieces.append(_finish(_piece(nom, chemin, FORMATS.get(ext, "zip")), "", False, "trop_gros",
                                           f"{raison_texte('trop_gros')} (plus de {MAX_OCTETS_FICHIER // MB} Mo)"))
                continue
            try:
                data = an._read_member_limited(zf, info, min(MAX_OCTETS_FICHIER, etat.budget.bytes_left))
            except Exception:
                data = None
                etat.pieces.append(_finish(_piece(nom, chemin, FORMATS.get(ext, "zip")), "", False, "illisible"))
                continue
            if data is None:
                code = "trop_gros" if info.file_size > etat.budget.bytes_left else "plafond_volume"
                etat.pieces.append(_finish(_piece(nom, chemin, FORMATS.get(ext, "zip")), "", False, code))
                continue
            etat.budget.bytes_left -= len(data)
            if is_zip:
                try:
                    _read_zip(etat, data, depth + 1, chemin + "/", reprise)
                except ValueError:
                    etat.pieces.append(_finish(_piece(nom, chemin, "zip"), "", False, "illisible"))
                continue
            etat.fichiers += 1
            etat.tick(nom)
            try:
                piece = _read_data(etat, nom, chemin, data, prev)
            except Exception as e:      # noqa: BLE001 — une pièce abîmée n'arrête pas les autres
                logger.info("lecture de la pièce %s impossible : %s", nom[:80], type(e).__name__)
                piece = _finish(_piece(nom, chemin, FORMATS.get(ext, "")), "", False, "illisible")
            del data
            etat.chars += piece["caracteres"]
            etat.pieces.append(piece)
            etat.tick(nom)


# ── Point d'entrée ─────────────────────────────────────────────────────────────────────

def lire_dossier(filename: str, content: bytes, mode: str = "direct", progress=None,
                 reprise: dict = None) -> dict:
    """Lit TOUT le dossier (fichier seul ou archive ZIP). Renvoie la lecture :
    {version, source, archive, mode, lu_le, pieces: [{nom, chemin, format, type, libelle,
    statut, raison, detail, caracteres, pages, pages_lues, pages_non_lues, texte, page_starts}],
    a_poursuivre (des pages en image restent à lire : tâche de fond), temps_ecoule}.
    Les pièces sont dans l'ordre d'assemblage (règlement, cadre de réponse, acte d'engagement,
    CCAP, CCTP, bordereaux, autres).
    Lève ValueError (message affichable) si RIEN n'est lisible et qu'aucune lecture en tâche de
    fond ne peut y remédier (format non pris en charge, archive vide ou corrompue…).
    reprise : lecture « direct » précédente ; ses pièces lues en entier ne sont pas relues."""
    etat = _Etat(mode if mode in ("direct", "fond") else "direct", progress=progress)
    name = filename or "dossier"
    base = os.path.basename(name.replace("\\", "/"))
    reprise_map = {}
    for pc in ((reprise or {}).get("pieces") or []):
        if isinstance(pc, dict) and pc.get("chemin"):
            reprise_map[pc["chemin"]] = pc
    ln = name.lower()
    is_office = ln.endswith((".docx", ".docm", ".xlsx", ".xlsm", ".ods", ".odt"))
    archive = (ln.endswith(".zip") or content[:2] == b"PK") and not is_office and not content[:5] == b"%PDF-"
    if archive:
        _read_zip(etat, content, 0, "", reprise_map)
        if not etat.pieces:
            raise ValueError("Aucun fichier dans l'archive.")
    else:
        prev = reprise_map.get(base)
        if prev is not None and prev.get("statut") == LU and prev.get("texte"):
            etat.pieces.append(dict(prev))
        else:
            if _ext(base) not in FORMATS and content[:5] != b"%PDF-":
                raise ValueError("Format non supporté. Importez le dossier en PDF, Word (.docx), tableur "
                                 "(.xlsx), texte ou archive ZIP.")
            if len(content) > MAX_OCTETS_FICHIER:
                raise ValueError(f"Fichier trop volumineux ({MAX_OCTETS_FICHIER // MB} Mo au plus).")
            etat.tick(base)
            etat.pieces.append(_read_data(etat, base, base, content, prev))
    _noms_affiches(etat.pieces)
    pieces = sorted(etat.pieces, key=lambda x: (dp.compose_rank(x["type"]), 0))
    lecture = {
        "version": 1, "source": base[:300], "archive": bool(archive), "mode": etat.mode,
        "lu_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pieces": pieces,
        "a_poursuivre": etat.mode == "direct" and (etat.besoin_fond or etat.expired() or any(
            p.get("raison") in ("scan_a_lire", "temps") for p in pieces)),
        "temps_ecoule": etat.expired(),
        "duree_s": round(time.monotonic() - etat.t0, 1),
    }
    if not any(p["caracteres"] for p in pieces) and not lecture["a_poursuivre"]:
        raise ValueError(_message_rien_lu(pieces))
    return lecture


NOM_MAX = 180       # nom affiché d'une pièce (en-tête « === nom === » : 200 caractères au plus)


def _noms_affiches(pieces: list) -> None:
    """Nom affiché de chaque pièce (en-têtes remis à l'IA, sources des réponses, liste des pièces
    lues) : son chemin dans l'archive, sans le dossier commun à toutes les pièces. Dans un dossier
    rangé par lots (« LOT 01/CCTP.pdf », « LOT 02/CCTP.pdf »), chaque pièce garde ainsi son lot ;
    dans une archive à plat, le nom reste celui du fichier. Le type de pièce est reconnu sur le
    nom du fichier seul (déjà fait à la lecture)."""
    chemins = [str(p.get("chemin") or p.get("nom") or "").replace("\\", "/") for p in pieces]
    dirs = [c.split("/")[:-1] for c in chemins]
    common = os.path.commonprefix(dirs) if dirs else []
    for p, c in zip(pieces, chemins):
        segs = c.split("/")
        rel = "/".join(segs[len(common):]) or os.path.basename(c) or p.get("nom") or ""
        if len(rel) > NOM_MAX:
            rel = "…" + rel[-(NOM_MAX - 1):]
        p["nom"] = rel


def _message_rien_lu(pieces: list) -> str:
    codes = {p.get("raison") for p in pieces}
    if codes == {"trop_gros"} or ("trop_gros" in codes and len(codes) == 1):
        return (f"Un fichier de l'archive est trop volumineux une fois décompressé ({MAX_OCTETS_FICHIER // MB} Mo "
                "au plus par fichier). Importez directement les pièces utiles (RC, CCAP, CCTP, DPGF).")
    if codes == {"imbrique"}:
        return "Archive trop imbriquée (un ZIP dans un ZIP dans un ZIP). Décompressez-la puis importez les pièces."
    if "protege" in codes and codes <= {"protege", "format", "compression", "vide"}:
        return "Le dossier est protégé par un mot de passe : demandez à l'acheteur une version sans mot de passe."
    if codes <= {"format", "compression"}:
        return ("Aucun fichier lisible : formats non pris en charge. Importez le dossier en PDF, Word (.docx), "
                "tableur (.xlsx), texte ou archive ZIP.")
    if codes & {"ocr_indisponible", "scan_illisible"}:
        return "Le dossier ne contient que des pages scannées, et aucun texte n'a pu y être reconnu."
    return "Aucun texte lisible dans le dossier (fichiers vides, abîmés ou protégés)."


# ── Résumé de la lecture (sans le texte) ──────────────────────────────────────────────

def manifeste(lecture: dict) -> dict:
    """Ce qui a été lu, pièce par pièce, SANS le texte (stocké dans l'analyse et montré à
    l'écran) : nom, type, statut, raison, caractères, pages."""
    out = []
    for p in (lecture or {}).get("pieces") or []:
        out.append({"nom": str(p.get("nom") or "")[:NOM_MAX + 20], "chemin": str(p.get("chemin") or "")[:300],
                    "format": p.get("format") or "", "type": p.get("type") or dp.AUTRE,
                    "libelle": p.get("libelle") or dp.label(p.get("type")),
                    "statut": p.get("statut") or NON_LU, "raison": p.get("raison") or "",
                    "detail": str(p.get("detail") or "")[:300], "caracteres": int(p.get("caracteres") or 0),
                    "pages": p.get("pages"), "pages_lues": p.get("pages_lues"),
                    "lu_en_entier": (p.get("statut") == LU)})
    tot = totaux(lecture)
    return {"version": 1, "source": (lecture or {}).get("source") or "", "lu_le": (lecture or {}).get("lu_le"),
            "mode": (lecture or {}).get("mode"), "pieces": out, "totaux": tot}


def totaux(lecture: dict) -> dict:
    pieces = (lecture or {}).get("pieces") or []
    return {"pieces": len(pieces),
            "lues_en_entier": sum(1 for p in pieces if p.get("statut") == LU),
            "lues_en_partie": sum(1 for p in pieces if p.get("statut") == PARTIEL),
            "non_lues": sum(1 for p in pieces if p.get("statut") == NON_LU),
            "pages": sum(int(p.get("pages") or 0) for p in pieces),
            "pages_lues": sum(int(p.get("pages_lues") or 0) for p in pieces),
            "caracteres": sum(int(p.get("caracteres") or 0) for p in pieces)}


def couverture(lecture: dict) -> dict:
    """Couverture HONNÊTE, pour l'analyse et l'écran : « Dossier lu en entier : N pièces, P pages »
    ou la liste des pièces non lues ou lues en partie, avec leur raison."""
    t = totaux(lecture)
    pieces = (lecture or {}).get("pieces") or []
    complet = t["pieces"] > 0 and t["lues_en_entier"] == t["pieces"]
    pl = f", {t['pages']} page{'s' if t['pages'] > 1 else ''}" if t["pages"] else ""
    if complet:
        msg = f"Dossier lu en entier : {t['pieces']} pièce{'s' if t['pieces'] > 1 else ''}{pl}."
    else:
        manque = t["non_lues"] + t["lues_en_partie"]
        pp = (f" ({t['pages_lues']} page{'s' if t['pages_lues'] > 1 else ''} lue{'s' if t['pages_lues'] > 1 else ''} "
              f"sur {t['pages']})") if t["pages"] else ""
        msg = (f"Dossier lu en partie : {t['lues_en_entier']} pièce{'s' if t['lues_en_entier'] > 1 else ''} "
               f"sur {t['pieces']} lue{'s' if t['lues_en_entier'] > 1 else ''} en entier{pp} ; "
               f"{manque} pièce{'s' if manque > 1 else ''} non lue{'s' if manque > 1 else ''} ou lue"
               f"{'s' if manque > 1 else ''} en partie (voir la liste).")
    return {"complet": complet, "message": msg, "totaux": t,
            "non_lues": [{"nom": p.get("nom"), "raison": p.get("detail") or raison_texte(p.get("raison"))}
                         for p in pieces if p.get("statut") == NON_LU][:100],
            "partielles": [{"nom": p.get("nom"), "raison": p.get("detail") or raison_texte(p.get("raison"))}
                           for p in pieces if p.get("statut") == PARTIEL][:100]}


def note_pour_ia(lecture: dict) -> str:
    """Avertissement remis à l'IA en tête du dossier : les pièces non lues (ou en partie), pour
    qu'elle ne conclue jamais qu'une information « n'existe pas » quand elle n'a pas été lue."""
    pieces = (lecture or {}).get("pieces") or []
    manquent = [p for p in pieces if p.get("statut") != LU]
    if not manquent:
        return (f"[Dossier lu en entier : {len(pieces)} pièce(s). Chaque pièce est précédée de "
                "« === nom === ».]")
    lignes = [f"- {p.get('nom')} : {'non lue' if p.get('statut') == NON_LU else 'lue en partie'} "
              f"({p.get('detail') or raison_texte(p.get('raison'))})" for p in manquent[:40]]
    return ("[Attention : certaines pièces n'ont pas pu être lues en entier. Si une information n'est pas "
            "dans le texte fourni, écris qu'elle n'a pas été trouvée dans les pièces lues — jamais qu'elle "
            "n'existe pas.]\n" + "\n".join(lignes))


def texte_integral(lecture: dict, max_chars: int = None) -> tuple:
    """Texte complet du dossier, pièce par pièce (« === nom === »), règlement et cadre de réponse
    en tête (app.services.dce_pieces.compose). Renvoie (texte, meta)."""
    pieces = [{"nom": p.get("nom") or "", "texte": p.get("texte") or "", "type": p.get("type"),
               "complet": p.get("statut") == LU}
              for p in (lecture or {}).get("pieces") or [] if p.get("texte")]
    budget = max_chars if max_chars else (sum(len(p["texte"]) + 300 for p in pieces) + 1000)
    return dp.compose(pieces, budget, headers=True)


def page_of(piece: dict, offset: int):
    """Numéro de page (1…) d'une position dans le texte d'une pièce, si la pièce est paginée."""
    starts = piece.get("page_starts") if isinstance(piece, dict) else None
    if not starts or offset is None or offset < 0:
        return None
    import bisect
    return bisect.bisect_right(starts, int(offset)) or None
