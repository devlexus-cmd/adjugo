"""
Empreintes des scripts servis (SRI, Subresource Integrity) — co-traitance v2, vague 4.

Pourquoi : le détail chiffré d'un partenaire est chiffré DANS SON NAVIGATEUR par le JavaScript
qu'Adjugo sert (cotraitance-crypto.js, app.js, invite.html). Ce n'est pas du zero-knowledge :
un script modifié pourrait exfiltrer la clé. Deux mitigations simples :
  1. chaque balise <script src="/static/…"> des pages servies porte integrity="sha384-…" : le
     navigateur REFUSE d'exécuter un fichier dont le contenu ne correspond pas à l'empreinte
     posée dans la page (fichier altéré ou périmé ENTRE le serveur et le navigateur : cache,
     proxy, fichier servi par erreur). Ce n'est PAS une protection contre une modification des
     fichiers sur le serveur lui-même : le filet de production (plus bas) recalcule les
     empreintes des pages à partir des fichiers présents sur le disque, donc un script modifié
     sur le serveur est servi avec SA propre empreinte. Une telle modification se voit en
     comparant avec le manifeste versionné (sri-manifest.json : `manifeste_publie_a_jour` vaut
     alors false) et dans les journaux du serveur (« empreintes périmées ») ;
  2. les empreintes sont PUBLIÉES (app/static/sri-manifest.json, versionné dans le dépôt, et
     GET /api/securite/empreintes-scripts calculé à chaud) : n'importe qui peut comparer ce que
     son navigateur reçoit à ce qui est publié (`openssl dgst -sha384 -binary app.js | openssl base64 -A`).

Limite honnête : la page HTML elle-même et ses scripts en ligne (inline) ne sont pas couverts
par SRI ; un serveur compromis (ou un fichier modifié sur le disque du serveur, voir le point 1)
peut servir une page ET des empreintes modifiées. La valeur est dans la comparaison avec les
empreintes publiées et versionnées (et, à terme, un audit tiers).

Régénération (après toute modification d'un script) :  python scripts/sri_update.py
Le test tests/test_cotraitance_v4.py::test_sri_empreintes_a_jour échoue avec cette commande si
une empreinte est périmée. Filet de production : si une page servie porte une empreinte périmée
(déploiement sans régénération), elle est CORRIGÉE à la volée et l'erreur est journalisée — le
logiciel ne se bloque jamais pour un oubli de régénération. Conséquence assumée (choix écrit au
§ 3 du contrat de la vague 4) : ce filet ne distingue pas un oubli d'une modification du fichier
sur le serveur, il sert les deux avec l'empreinte du fichier présent (voir le point 1).

CSP : inchangée (script-src garde 'unsafe-inline' — scripts en ligne dans app.html, invite.html,
landing… — et 'unsafe-eval' — Vue compile ses gabarits dans le navigateur). Piste de durcissement
documentée dans docs/COTRAITANCE_V2_VAGUE4_API.md (scripts en ligne externalisés ou hachés,
puis retrait de 'unsafe-inline').
"""
import base64
import hashlib
import json
import logging
import os
import re
import threading

logger = logging.getLogger("adjugo")

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
MANIFEST_NAME = "sri-manifest.json"
MANIFEST_PATH = os.path.join(STATIC_DIR, MANIFEST_NAME)
REGEN_CMD = "python scripts/sri_update.py"
ALGO = "sha384"
# Pages HTML servies qui chargent des scripts /static/… (landing, demande d'accès et pages
# légales n'en chargent aucun : uniquement du script en ligne ou rien).
PAGES = ("app.html", "invite.html", "acheteur.html", "acheteur-landing.html")

_SCRIPT_TAG = re.compile(r"<script\b[^>]*>", re.IGNORECASE)
_SRC = re.compile(r"""\bsrc\s*=\s*(["'])(/static/[^"'?#]+)\1""", re.IGNORECASE)
_INTEGRITY = re.compile(r"""\s+integrity\s*=\s*(["'])[^"']*\1""", re.IGNORECASE)


def script_files() -> list:
    """Scripts publiés : app/static/*.js + app/static/vendor/* (chemins relatifs, triés)."""
    out = []
    for name in sorted(os.listdir(STATIC_DIR)):
        if name.endswith(".js") and os.path.isfile(os.path.join(STATIC_DIR, name)):
            out.append(name)
    vend = os.path.join(STATIC_DIR, "vendor")
    if os.path.isdir(vend):
        for name in sorted(os.listdir(vend)):
            if os.path.isfile(os.path.join(vend, name)) and not name.startswith("."):
                out.append(f"vendor/{name}")
    return out


def _digests(path: str) -> tuple:
    with open(path, "rb") as f:
        data = f.read()
    return (f"{ALGO}-" + base64.b64encode(hashlib.sha384(data).digest()).decode("ascii"),
            hashlib.sha256(data).hexdigest(), len(data))


def compute_manifest() -> dict:
    """Empreintes ACTUELLES des fichiers (déterministe : pas d'horodatage)."""
    files = {}
    for rel in script_files():
        integ, sha256, size = _digests(os.path.join(STATIC_DIR, rel))
        files[f"/static/{rel}"] = {"integrity": integ, "sha256": sha256, "octets": size}
    return {
        "schema": "adjugo-sri-v1",
        "algorithme": ALGO,
        "regeneration": REGEN_CMD,
        "verification": "openssl dgst -sha384 -binary <fichier> | openssl base64 -A  (à préfixer par « sha384- »)",
        "fichiers": files,
    }


def manifest_bytes(manifest: dict) -> bytes:
    return (json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8")


def read_published_manifest() -> dict:
    try:
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def apply_integrity(html: str, files: dict) -> str:
    """Pose (ou remplace) integrity="…" sur chaque <script src="/static/…"> connu. Idempotent ;
    une balise vers un fichier inconnu est laissée telle quelle."""
    def fix(m):
        tag = m.group(0)
        src = _SRC.search(tag)
        if not src or src.group(2) not in files:
            return tag
        # Ancien attribut retiré AVANT de repérer src : sa position change si integrity était
        # placé avant src (sinon la nouvelle empreinte atterrissait hors de la balise).
        tag = _INTEGRITY.sub("", tag)
        src = _SRC.search(tag)
        integ = files[src.group(2)]["integrity"]
        end = src.end()
        return tag[:end] + f' integrity="{integ}"' + tag[end:]
    return _SCRIPT_TAG.sub(fix, html)


# ── Service des pages (filet de production) ────────────────────────────────────────────

_LOCK = threading.Lock()
_CACHE: dict = {}      # page → (signature des mtimes, html)


def _signature(page: str) -> tuple:
    paths = [os.path.join(STATIC_DIR, page)] + [os.path.join(STATIC_DIR, r) for r in script_files()]
    sig = []
    for p in paths:
        try:
            st = os.stat(p)
            sig.append((p, st.st_mtime_ns, st.st_size))
        except OSError:
            sig.append((p, None, None))
    return tuple(sig)


def page_html(page: str) -> str:
    """HTML d'une page servie, empreintes SRI garanties à jour (process unique : cache en
    mémoire invalidé dès qu'un fichier change)."""
    sig = _signature(page)
    with _LOCK:
        hit = _CACHE.get(page)
        if hit and hit[0] == sig:
            return hit[1]
    with open(os.path.join(STATIC_DIR, page), encoding="utf-8") as f:
        raw = f.read()
    html = raw
    try:
        fixed = apply_integrity(raw, compute_manifest()["fichiers"])
        if fixed != raw:
            logger.error("SRI : empreintes périmées dans %s (corrigées à la volée). Lancez : %s",
                         page, REGEN_CMD)
        html = fixed
    except Exception as e:      # jamais une page indisponible à cause du calcul d'empreintes
        logger.warning("SRI : calcul impossible pour %s (%s)", page, type(e).__name__)
    with _LOCK:
        _CACHE[page] = (sig, html)
    return html


def regenerate() -> list:
    """Réécrit les attributs integrity des pages et le manifeste publié. Renvoie les fichiers
    modifiés (utilisé par scripts/sri_update.py)."""
    manifest = compute_manifest()
    changed = []
    for page in PAGES:
        path = os.path.join(STATIC_DIR, page)
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        new = apply_integrity(raw, manifest["fichiers"])
        if new != raw:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new)
            changed.append(f"app/static/{page}")
    data = manifest_bytes(manifest)
    try:
        with open(MANIFEST_PATH, "rb") as f:
            old = f.read()
    except OSError:
        old = b""
    if old != data:
        with open(MANIFEST_PATH, "wb") as f:
            f.write(data)
        changed.append(f"app/static/{MANIFEST_NAME}")
    with _LOCK:
        _CACHE.clear()
    return changed


def stale_report() -> dict:
    """{pages: [pages dont une balise n'a pas la bonne empreinte], manifeste_a_jour: bool}."""
    manifest = compute_manifest()
    stale = []
    for page in PAGES:
        with open(os.path.join(STATIC_DIR, page), encoding="utf-8") as f:
            raw = f.read()
        if apply_integrity(raw, manifest["fichiers"]) != raw:
            stale.append(page)
    try:
        with open(MANIFEST_PATH, "rb") as f:
            published = f.read()
    except OSError:
        published = b""
    return {"pages": stale, "manifeste_a_jour": published == manifest_bytes(manifest)}
