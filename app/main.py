import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from app.core.config import get_settings
from app.core.database import engine, Base, _is_sqlite
from app.routers import auth, projects, invoices, contacts, documents, cerfa, stripe_pay, cotraitants, export_dossier, checklist, chiffrage
from app.routers.company import company_router
from app.routers.criteria_v2 import router as criteria_v2_router
from app.routers.agent import router as agent_router
from app.routers.registre import router as registre_router
from app.routers.admin import router as admin_router
from app.routers.sourcing import router as sourcing_router
from app.routers.saved_searches import router as saved_searches_router
from app.routers.org import router as org_router

settings = get_settings()

# Observabilité : logs structurés + Sentry (si DSN configuré)
from app.core.observability import setup_logging, init_sentry, request_logger
setup_logging()
init_sentry()

# Garde-fou prod : refuse de démarrer avec une clé secrète par défaut (JWT prévisibles).
import logging as _logging
if settings.ENVIRONMENT == "production" and settings.SECRET_KEY in ("", "change-this-in-production"):
    raise RuntimeError(
        "SECRET_KEY non configurée en production. Générez-en une (openssl rand -hex 32) "
        "et définissez la variable d'environnement SECRET_KEY."
    )
if settings.SECRET_KEY in ("", "change-this-in-production"):
    _logging.getLogger("adjugo").warning("SECRET_KEY par défaut — à changer avant la prod.")

# Garde-fou prod : fail-CLOSED. DEMO_MODE ouvre des endpoints sans auth ; CRON_SECRET
# protège les tâches admin coûteuses. Les deux doivent être verrouillés en production.
if settings.ENVIRONMENT == "production":
    if settings.DEMO_MODE:
        raise RuntimeError("DEMO_MODE=True interdit en production (endpoints sans auth). Mettez DEMO_MODE=false.")
    if not settings.CRON_SECRET:
        raise RuntimeError("CRON_SECRET requis en production (protège /api/admin/run-*). Définissez-le.")
    # L'endpoint acheteur /api/dce/generate appelle le LLM ; en prod il doit être protégé
    # par un code d'accès (sinon endpoint coûteux ouvert). Fail-closed, comme ci-dessus.
    if not os.getenv("DCE_ACCESS_CODE", "").strip():
        raise RuntimeError("DCE_ACCESS_CODE requis en production (protège /api/dce/generate, "
                           "endpoint LLM du produit acheteur). Définissez-le.")
# Rate-limit en mémoire = compteur PAR worker : avec >1 worker, la limite réelle est
# multipliée par le nombre de workers → protection illusoire. L'enforcement FAIL-SAFE
# est dans entrypoint.sh : sans RATELIMIT_STORAGE_URI=redis://, il ramène le nombre de
# workers à 1 (rate-limit correct) au lieu de planter. Ici on ne fait qu'un constat :
# si on voit malgré tout memory:// + plusieurs workers (démarrage hors entrypoint),
# on le SIGNALE fort — sans tuer le service (un souci de rate-limit ne doit pas mettre
# toute l'API à terre).
_mem_rl = settings.RATELIMIT_STORAGE_URI.startswith("memory://")
_workers = int(os.getenv("WEB_CONCURRENCY", "1"))
if _mem_rl and _workers > 1:
    _logging.getLogger("adjugo").error(
        "Rate-limit en mémoire avec %s workers : limites multipliées (protection illusoire). "
        "Configurez RATELIMIT_STORAGE_URI=redis://… ou démarrez via entrypoint.sh (clamp à 1 worker).",
        _workers)

# Dev (SQLite) : création directe des tables. Prod (Postgres) : migrations Alembic
# (`alembic upgrade head`) — on ne crée pas le schéma à la volée.
if _is_sqlite:
    Base.metadata.create_all(bind=engine)
    # Ajoute les colonnes de modèle manquantes sur une base déjà créée (idempotent).
    from app.core.dbsync import ensure_sqlite_columns
    ensure_sqlite_columns(engine, Base)

# Documentation interactive (Swagger /docs, ReDoc /redoc, schéma /openapi.json) : utile en
# dev, mais en PRODUCTION c'est une carte complète de l'API (routes admin/cron, schémas
# Stripe/RGPD/invitations) offerte sans authentification → coupée. Même détection de la prod
# que les garde-fous ci-dessus (settings.ENVIRONMENT, normalisé en minuscules dans config).
_IS_PROD = settings.ENVIRONMENT == "production"
app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION,
              description="API pour la gestion des marches publics",
              docs_url=None if _IS_PROD else "/docs",
              redoc_url=None if _IS_PROD else "/redoc",
              openapi_url=None if _IS_PROD else "/openapi.json")

# Rate limiting
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from app.core.ratelimit import limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Compression gzip des réponses texte (HTML/JS/CSS/JSON) — allège fortement le front
# (i18n.js, app.js…). Filet en plus de la compression de l'edge.
from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=800)

# Idempotence des requêtes mutantes (rejeu sûr d'un POST facturé). Opt-in via l'en-tête
# Idempotency-Key ; passe-plat strict sans l'en-tête.
from app.core.idempotency import IdempotencyMiddleware
app.add_middleware(IdempotencyMiddleware)

# Taille maximale des corps de requête (audit cyber oct. 2026, faille 2). Middleware ASGI
# pur, ajouté APRÈS l'idempotence donc exécuté AVANT elle (Starlette : dernier ajouté =
# premier traversé) et avant tout ce qui lit le corps (routes, formulaires, webhook Stripe).
# Deux contrôles : Content-Length annoncé (refus immédiat, rien n'est lu) ET octets
# réellement reçus (transfert « chunked » ou client qui ment). Le corps n'est ni copié ni
# modifié : le webhook Stripe reçoit ses octets bruts intacts pour vérifier la signature.
import re as _re
from starlette.exceptions import HTTPException as _StarletteHTTPException

_MB = 1024 * 1024
BODY_LIMIT_UPLOAD = 60 * _MB     # routes d'envoi de fichiers (multipart)
BODY_LIMIT_DEFAULT = 2 * _MB     # tout le reste (JSON, formulaires, webhook)
_UPLOAD_ROUTES = [(m, _re.compile(rx)) for m, rx in (
    ("POST", r"^/api/documents/?$"),
    ("PUT",  r"^/api/documents/[^/]+/replace/?$"),
    ("POST", r"^/api/sourcing/analyze-upload/?$"),
    ("POST", r"^/api/amont/analyze-upload/?$"),
    ("POST", r"^/api/knowledge/upload/?$"),
    ("POST", r"^/api/invite/[^/]+/contribution/piece/?$"),
)]
_MSG_TOO_BIG_UPLOAD = "Fichier trop volumineux : 60 Mo maximum."
_MSG_TOO_BIG = "Les données envoyées sont trop volumineuses."


def _routed_path(scope) -> str:
    """Chemin réellement routé (scope ASGI, root_path retiré) — jamais l'en-tête Host."""
    path = scope.get("path") or ""
    root = scope.get("root_path") or ""
    if root and path.startswith(root):
        path = path[len(root):] or "/"
    return path


def body_limit_for(scope) -> tuple:
    """(limite en octets, message) pour cette requête."""
    method = (scope.get("method") or "").upper()
    # Starlette (request.form, Headers.get) lit le PREMIER Content-Type : on fait de même.
    # Plusieurs Content-Type = requête ambiguë → limite basse (sinon « urlencoded » puis
    # « multipart » obtenait la limite des fichiers pour un formulaire analysé en mémoire).
    ctypes = [v for k, v in (scope.get("headers") or []) if k.lower() == b"content-type"]
    if len(ctypes) != 1:
        return BODY_LIMIT_DEFAULT, _MSG_TOO_BIG
    ctype = ctypes[0]
    if ctype.strip().lower().startswith(b"multipart/"):
        path = _routed_path(scope)
        if any(m == method and rx.match(path) for m, rx in _UPLOAD_ROUTES):
            return BODY_LIMIT_UPLOAD, _MSG_TOO_BIG_UPLOAD
    return BODY_LIMIT_DEFAULT, _MSG_TOO_BIG


class _BodyTooLarge(_StarletteHTTPException):
    """Levée par receive() au-delà de la limite. Sous-classe d'HTTPException : FastAPI la
    relaie telle quelle (413 en français) au lieu d'un 400 « error parsing the body »."""
    def __init__(self, detail: str):
        super().__init__(status_code=413, detail=detail)


async def _send_413(send, detail: str):
    import json as _json
    body = _json.dumps({"detail": detail}, ensure_ascii=False).encode("utf-8")
    await send({"type": "http.response.start", "status": 413, "headers": [
        (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
        (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": body, "more_body": False})


class BodySizeLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        limit, detail = body_limit_for(scope)
        for k, v in scope.get("headers") or []:
            if k.lower() == b"content-length":
                try:
                    declared = int(v.decode("latin-1").strip())
                except ValueError:
                    declared = 0      # le serveur HTTP rejette déjà un Content-Length invalide
                if declared > limit:
                    return await _send_413(send, detail)
        received = 0
        started = False

        async def _receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge(detail)
            return message

        async def _send(message):
            nonlocal started
            if message.get("type") == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, _receive, _send)
        except _BodyTooLarge as e:
            if not started:
                await _send_413(send, e.detail)


app.add_middleware(BodySizeLimitMiddleware)


app.middleware("http")(request_logger)

# Compte démo public = vitrine en LECTURE GUIDÉE : 403 explicite sur l'envoi d'emails, les
# téléversements, les appels IA payants et la gestion du compte/abonnement/équipe (liste
# explicite dans app/core/demo_guard.py). Enregistré AVANT security_headers → la réponse
# 403 reçoit quand même les en-têtes de sécurité.
from app.core.demo_guard import demo_guard_middleware
app.middleware("http")(demo_guard_middleware)

# CSP — verrouille les origines. 'unsafe-eval'/'unsafe-inline' requis car Vue (CDN)
# compile les templates à l'exécution et l'app utilise des styles inline (pas de build).
# Un build front permettrait de les retirer plus tard.
# Si un outil de mesure d'audience est configuré (ANALYTICS_SRC), on autorise SON origine
# dans script-src ET connect-src — sinon le script et son beacon étaient bloqués par la CSP
# (fonctionnalité activable par variable d'env mais silencieusement inopérante).
def _analytics_origin() -> str:
    src = (settings.ANALYTICS_SRC or "").strip()
    if not src:
        return ""
    try:
        from urllib.parse import urlparse
        u = urlparse(src)
        return f"{u.scheme}://{u.netloc}" if u.scheme and u.netloc else ""
    except Exception:
        return ""


_ANALYTICS_ORIGIN = _analytics_origin()
_SCRIPT_EXTRA = (" " + _ANALYTICS_ORIGIN) if _ANALYTICS_ORIGIN else ""
_CONNECT_EXTRA = (" " + _ANALYTICS_ORIGIN) if _ANALYTICS_ORIGIN else ""
# cdn.jsdelivr.net / fastapi.tiangolo.com ne servent QU'À Swagger/ReDoc (le front auto-héberge
# ses libs) : autorisés seulement hors production, là où la doc interactive existe encore.
_DOCS_SCRIPT = "" if _IS_PROD else " https://cdn.jsdelivr.net"
_DOCS_IMG = "" if _IS_PROD else " https://cdn.jsdelivr.net https://fastapi.tiangolo.com"
_CSP = (
    "default-src 'self'; "
    f"script-src 'self' 'unsafe-inline' 'unsafe-eval'{_DOCS_SCRIPT}{_SCRIPT_EXTRA}; "
    f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com{_DOCS_SCRIPT}; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    f"img-src 'self' data: blob:{_DOCS_IMG}; "
    f"connect-src 'self'{_CONNECT_EXTRA}; worker-src 'self' blob:; "
    "frame-ancestors 'self'; base-uri 'self'; form-action 'self'; object-src 'none'"
)


@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["X-XSS-Protection"] = "0"
    resp.headers["Content-Security-Policy"] = _CSP
    if not settings.DEBUG:
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # Cache des assets :
    #  • /static/vendor/* : libs épinglées par VERSION dans le nom → immuables, cache long
    #    (un bump = nouveau nom de fichier = nouvelle URL, donc jamais de version périmée).
    #  • le reste (/app, /, app.js, styles.css) : no-store, pour ne jamais exécuter un build périmé.
    p = request.url.path
    if p.startswith("/static/vendor/"):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif p == "/app" or p == "/" or p.startswith("/static"):
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
    return resp


app.include_router(auth.router)
from app.routers import google_auth
app.include_router(google_auth.router)
app.include_router(projects.router)
app.include_router(documents.router)
app.include_router(invoices.router)
app.include_router(contacts.router)
app.include_router(company_router)
app.include_router(criteria_v2_router)
app.include_router(cerfa.router)
app.include_router(stripe_pay.router)
app.include_router(cotraitants.router)
from app.routers.groupement import router as groupement_router   # « Répondre à plusieurs ? »
app.include_router(groupement_router)
# « Monter le groupement » (co-traitance v2, vague 2) : convention + accords des membres.
from app.routers.convention import owner_router as convention_owner_router, guest_router as convention_guest_router
app.include_router(convention_owner_router)
app.include_router(convention_guest_router)
app.include_router(export_dossier.router)
app.include_router(checklist.router)
app.include_router(chiffrage.router)
app.include_router(agent_router)
app.include_router(registre_router)
app.include_router(admin_router)
app.include_router(sourcing_router)
app.include_router(saved_searches_router)
app.include_router(org_router)
from app.routers.amont import router as amont_router
app.include_router(amont_router)
from app.routers.knowledge import router as knowledge_router
app.include_router(knowledge_router)
# Rédaction, vague 3 : « Mes preuves » (faits de l'entreprise, chacun avec sa source typée).
# Les routes des écrans (reprise de l'existant, insertion dans l'atelier) passent AVANT le socle :
# « /api/preuves/reprise » ne doit pas être lu comme la preuve n° « reprise ».
from app.routers.preuves_ecrans import router as preuves_ecrans_router
app.include_router(preuves_ecrans_router)
from app.routers.preuves import router as preuves_router
app.include_router(preuves_router)
# Rédaction, vague 3 (chantier I) : fiches PROPOSÉES à partir des anciens documents de « Mon savoir-faire ».
from app.routers.fiches_import import router as fiches_import_router
app.include_router(fiches_import_router)
# Rédaction, vague 2 : l'atelier du dossier de présentation (sections, versions, validation,
# rédaction en tâche de fond, « à relire », export Word et PDF bloqué sauf dérogation).
# Rédaction, vague 4 : le dossier de groupement cloisonné (« Qui écrit quoi », parts des partenaires,
# validation du dossier assemblé). Avant l'atelier : ses chemins sont plus précis.
from app.routers.atelier_groupement import router as atelier_groupement_router
app.include_router(atelier_groupement_router)
from app.routers.atelier import router as atelier_router
app.include_router(atelier_router)
from app.routers.rgpd import router as rgpd_router
app.include_router(rgpd_router)
from app.routers.feedback import router as feedback_router
app.include_router(feedback_router)
# « Merged Brain » (CoSpace) ARCHIVÉ : doublon du Réseau Adjugo (lien d'invitation +
# contribution cloisonnée). Routeur non monté ; modèles conservés (pas de migration).
# from app.routers.cospace import router as cospace_router
# app.include_router(cospace_router)
from app.routers.jobs import router as jobs_router
app.include_router(jobs_router)
from app.routers.invites import router as invites_router
app.include_router(invites_router)
from app.routers.reseau import router as reseau_router     # réseau de partenaires (vague 3)
app.include_router(reseau_router)
# Co-traitance v2, vague 4 : journal vérifiable par chaque membre (intégrité + exports),
# dépôt (« Marquer déposé ») et tableau de bord des groupements.
from app.routers.journal_membre import router as journal_membre_router
app.include_router(journal_membre_router)
from app.routers.groupement import dashboard_router as groupement_dashboard_router
app.include_router(groupement_dashboard_router)
# Produit ACHETEUR (collectivités) — Pilier 1 : rédacteur de DCE. Cloisonné du logiciel
# PME (génération pure, aucune donnée tenant) ; page autonome /acheteur.
from app.routers.dce import router as dce_router
app.include_router(dce_router)
# Espace ACHETEUR (collectivités) : comptes cloisonnés (table séparée, JWT typ=acheteur)
# + DCE sauvegardés. Aucune donnée PME.
from app.routers.acheteur import router as acheteur_router
app.include_router(acheteur_router)
from app.routers import contact as _contact_router
app.include_router(_contact_router.router)

# Fichiers statiques du logiciel (SPA)
_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    from fastapi.responses import FileResponse
    return FileResponse(os.path.join(_static_dir, "favicon.svg"), media_type="image/svg+xml")


@app.get("/", tags=["Site"], include_in_schema=False)
def root():
    from fastapi.responses import HTMLResponse
    with open(os.path.join(_static_dir, "landing.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())


# « Lecture et analyse » : lire un document et en extraire des éléments (dossiers des acheteurs, et
# anciens documents de l'entreprise pour proposer des fiches de preuves, rédaction vague 3).
_TACHES_LECTURE = {"analyse", "lecture_pieces", "exigences", "veille", "deliberation", "renouvellements",
                   "fiches_preuves"}


def _h(texte: str) -> str:
    """Apostrophes échappées comme dans les pages juridiques générées."""
    return texte.replace("'", "&#x27;")


def _role_ia(taches) -> str:
    t = set(taches or [])
    lect, autres = bool(t & _TACHES_LECTURE), bool(t - _TACHES_LECTURE)
    if lect and autres:
        return "lecture des dossiers, questions et rédaction"
    if lect:
        return "lecture et analyse des dossiers"
    return "questions sur les dossiers et rédaction"


def _role_transfert(taches) -> str:
    """Même découpage que _role_ia, avec les articles (phrase sur les transferts)."""
    t = set(taches or [])
    lect, autres = bool(t & _TACHES_LECTURE), bool(t - _TACHES_LECTURE)
    if lect and autres:
        return "la lecture des dossiers, les questions et la rédaction"
    if lect:
        return "la lecture et l'analyse des dossiers"
    return "les questions sur les dossiers et la rédaction"


def _usage_transfert(principal, secours) -> str:
    """« pour … », « pour …, et en relais pour … » ou « en relais pour … », d'après les tâches
    RÉELLEMENT confiées au fournisseur (principal) et celles qu'il reprend en cas de panne (secours)."""
    parts = []
    if principal:
        parts.append("pour " + _role_transfert(principal))
    if secours:
        parts.append(("et " if principal else "") + "en relais pour " + _role_transfert(secours))
    return ", ".join(parts)


# Mistral AI : la liste de SES sous-traitants n'a pas pu être vérifiée (12/10/2026). Aucun nom ici,
# seulement le renvoi vers la liste qu'il publie lui-même.
_MISTRAL_SOUS_TRAITANTS_URL = "https://trust.mistral.ai/subprocessors"
_MISTRAL_SOUS_TRAITANTS = ("Mistral AI s'appuie sur ses propres sous-traitants techniques, dont la liste à jour est "
                           "publiée sur son centre de confiance "
                           f"(<a href=\"{_MISTRAL_SOUS_TRAITANTS_URL}\">{_MISTRAL_SOUS_TRAITANTS_URL}</a>)")
_MISTRAL_SOUS_TRAITANTS_COURT = "sous-traitants de Mistral AI : liste publiée sur trust.mistral.ai/subprocessors"
# Entraînement et conservation, par fournisseur (faits vérifiés le 12/10/2026). Mistral AI : « jusqu'à »
# 30 jours, jamais « aucune conservation » (la non-conservation n'est pas confirmée pour le compte).
_ANTH_ENTRAINEMENT = "Anthropic : jamais sans autorisation"
_MISTRAL_ENTRAINEMENT = "Mistral AI : utilisation pour l'amélioration des modèles désactivée sur le compte de l'Éditeur"
_MISTRAL_ENTRAINEMENT_NON_CONFIRME = ("Mistral AI : utilisation pour l'amélioration des modèles active par défaut, "
                                      "sa désactivation sur le compte de l'Éditeur n'étant pas encore confirmée")
_ANTH_CONSERVATION = ("Anthropic : 30 jours en règle générale, jusqu'à 2 ans pour les contenus signalés pour "
                      "non-respect de ses règles d'usage")
_MISTRAL_CONSERVATION = "Mistral AI : jusqu'à 30 jours glissants, pour la surveillance des abus"


def _phrase_roles(intervenants) -> str:
    """Qui fait quoi, d'après les tâches RÉELLEMENT confiées à chacun (principal) et celles qu'il reprend
    en cas de panne (secours). intervenants : [(libellé, principal, secours), …].
    Cas habituel (chacun est le relais exact de l'autre) : « A intervient pour … ; B, pour … ; chacun
    prend le relais de l'autre en cas de panne ou d'erreur. » Sinon, le détail de chacun."""
    actifs = [(lib, list(p or []), list(s or [])) for lib, p, s in intervenants if p or s]
    if len(actifs) == 2:
        (la, pa, sa), (lb, pb, sb) = actifs
        if pa and pb and set(sa) == set(pb) and set(sb) == set(pa):
            return (f"{la} intervient {_usage_transfert(pa, None)} ; {lb}, {_usage_transfert(pb, None)} ; "
                    "chacun prend le relais de l'autre en cas de panne ou d'erreur.")
    phrase = " ; ".join(f"{lib} intervient {_usage_transfert(p, s)}" for lib, p, s in actifs)
    if any(s for _lib, _p, s in actifs):
        phrase += " ; un relais ne joue qu'en cas de panne ou d'erreur de l'autre fournisseur"
    return phrase + "."


def _ai_subprocessor_fragments():
    """Fragments décrivant les fournisseurs d'IA RÉELLEMENT sollicités avec la configuration du serveur
    (routage par tâche ET secours, app.services.llm), injectés dans les pages légales (confidentialité,
    DPA, sécurité). Exacts dans TOUTES les configurations : Anthropic seul (Mistral non activé, ou
    LLM_PROVIDER=anthropic), Anthropic et Mistral AI (point d'accès UE ou mondial), Mistral AI seul
    (LLM_PROVIDER=mistral). Anthropic : stockage aux États-Unis, calcul possiblement hors des États-Unis
    par son routage mondial, CCT ; jamais d'entraînement sans autorisation ; conservation de 30 jours en
    règle générale. Mistral AI, dès qu'il est ACTIVÉ (clé, MISTRAL_ACTIF et désinscription de
    l'entraînement confirmée) : lieu de calcul du point d'accès RÉELLEMENT utilisé (UE et AELE par
    api.eu.mistral.ai, ou sans engagement de lieu par le point d'accès mondial), désinscription,
    conservation jusqu'à 30 jours glissants, renvoi vers la liste de SES sous-traitants (aucun nom).
    Le rôle de chacun (et les relais) est tiré du routage effectif, jamais écrit en dur. Repères et textes
    publiés : docs/IA_FOURNISSEURS_PAGES_JURIDIQUES.md."""
    anth_full = ("<strong>États-Unis</strong> pour le stockage (API standard api.anthropic.com) ; calcul "
                 "possiblement hors des États-Unis (routage mondial d'Anthropic) — encadré par CCT")
    anth_court = "États-Unis pour le stockage, calcul possiblement hors des États-Unis (CCT)"
    anth_transfert = "États-Unis ; calcul possiblement dans d'autres pays"
    defaut = {
        "{{AI_PROVIDER}}": "Anthropic, PBC",
        "{{AI_PRODUCT}}": "Claude API",
        "{{AI_LOCATION_FULL}}": _h(anth_full),
        "{{AI_LOCATION_SHORT}}": _h(anth_court),
        "{{AI_TRANSFER_MENTION}}": _h(f"le fournisseur d'IA (Anthropic, {anth_transfert}) pour l'analyse et la génération de "
                                      "documents, "),
        "{{AI_ROLES}}": _h("Anthropic (Claude API) intervient pour la lecture des dossiers, les questions et la rédaction."),
        "{{AI_ENTRAINEMENT}}": _h(_ANTH_ENTRAINEMENT),
        "{{AI_ENTRAINEMENT_FOURNISSEURS}}": _h("de notre fournisseur, Anthropic"),
        "{{AI_CONSERVATION}}": _h(_ANTH_CONSERVATION),
        "{{AI_SOUS_TRAITANTS_MISTRAL}}": "",
        "{{AI_CCT_MISTRAL}}": "",
    }
    try:
        from app.services.llm import etat_juridique
        e = etat_juridique()
    except Exception:
        return defaut
    if not e.get("mistral"):
        return defaut
    taches = e.get("taches") or {}
    t_m = taches.get("mistral") or {}
    t_a = taches.get("anthropic") or {}
    role_m = _role_ia(t_m.get("principal") or t_m.get("secours"))
    role_a = _role_ia(t_a.get("principal") or t_a.get("secours"))
    ue = e.get("mistral_zone") == "ue"
    if ue:
        lieu_m = ("calcul dans des centres de données de l'<strong>Union européenne et de l'AELE</strong> "
                  "(point d'accès régional api.eu.mistral.ai), les données de fonctionnement du compte "
                  "(facturation, configuration) pouvant être traitées hors de cette zone")
        lieu_m_court = "Union européenne et AELE pour le calcul (api.eu.mistral.ai)"
        transfert_m = "calcul dans l'Union européenne et l'AELE"
    else:
        lieu_m = ("point d'accès mondial (api.mistral.ai) <strong>sans engagement de lieu de calcul</strong> : "
                  "centres de données de ses sous-traitants, possiblement hors de l'Union européenne ; "
                  "stockage dans l'Union européenne par défaut")
        lieu_m_court = "lieu de calcul non garanti, possiblement hors Union européenne"
        transfert_m = "calcul possiblement hors de l'Union européenne"
    # Phrase complète (avec le lien) sous le tableau : ici, la forme courte.
    sous_traitants = f"{_MISTRAL_SOUS_TRAITANTS_COURT} ; transferts encadrés par CCT"
    desinscrit = bool(e.get("mistral_entrainement_desactive"))
    if desinscrit:
        entr = ("utilisation des contenus pour l'amélioration des modèles de Mistral AI désactivée par "
                "l'Éditeur sur son compte")
    else:
        entr = ("utilisation des contenus pour l'amélioration des modèles de Mistral AI : active par défaut "
                "chez ce fournisseur, sa désactivation étant à la charge du titulaire du compte (l'Éditeur), "
                "non encore confirmée")
    entr_m = _MISTRAL_ENTRAINEMENT if desinscrit else _MISTRAL_ENTRAINEMENT_NON_CONFIRME
    relais_m = " ; relais d'Anthropic en cas de panne" if t_m.get("secours") else ""
    relais_a = " ; relais de Mistral AI en cas de panne" if t_a.get("secours") else ""
    mistral_full = f"<strong>Mistral AI</strong> ({role_m}{relais_m}) : {lieu_m} ; {sous_traitants} ; {entr}."
    communs_mistral = {
        "{{AI_SOUS_TRAITANTS_MISTRAL}}": _h(f" {_MISTRAL_SOUS_TRAITANTS}."),
        "{{AI_CCT_MISTRAL}}": _h(" (pour Mistral AI : celles prévues par son accord de sous-traitance)"),
    }
    if not e.get("anthropic"):
        return {
            "{{AI_PROVIDER}}": "Mistral AI",
            "{{AI_PRODUCT}}": "La Plateforme",
            "{{AI_LOCATION_FULL}}": _h(mistral_full),
            "{{AI_LOCATION_SHORT}}": _h(f"{lieu_m_court} ; {_MISTRAL_SOUS_TRAITANTS_COURT} (CCT)"),
            "{{AI_TRANSFER_MENTION}}": _h(f"le fournisseur d'IA Mistral AI et ses propres sous-traitants techniques "
                                          f"— {transfert_m} —, "),
            "{{AI_ROLES}}": _h(_phrase_roles([("Mistral AI (La Plateforme)", t_m.get("principal"),
                                               t_m.get("secours"))])),
            "{{AI_ENTRAINEMENT}}": _h(entr_m),
            "{{AI_ENTRAINEMENT_FOURNISSEURS}}": _h("de notre fournisseur, Mistral AI"
                                                   + (" (nous avons désactivé cette utilisation sur notre compte)"
                                                      if desinscrit else "")),
            "{{AI_CONSERVATION}}": _h(_MISTRAL_CONSERVATION),
            **communs_mistral,
        }
    usage_a = _usage_transfert(t_a.get("principal"), t_a.get("secours"))
    usage_m = _usage_transfert(t_m.get("principal"), t_m.get("secours"))
    return {
        "{{AI_PROVIDER}}": "Anthropic, PBC et Mistral AI",
        "{{AI_PRODUCT}}": "Claude API ; La Plateforme de Mistral AI",
        "{{AI_LOCATION_FULL}}": _h(f"<strong>Anthropic</strong> ({role_a}{relais_a}) : {anth_full}. ") + _h(mistral_full),
        "{{AI_LOCATION_SHORT}}": _h(f"Anthropic : {anth_court} ; Mistral AI : {lieu_m_court} ; "
                                    f"{_MISTRAL_SOUS_TRAITANTS_COURT} (CCT)"),
        "{{AI_TRANSFER_MENTION}}": _h(f"le fournisseur d'IA Anthropic ({anth_transfert}) {usage_a}, le fournisseur "
                                      f"d'IA Mistral AI et ses propres sous-traitants techniques {usage_m} "
                                      f"— {transfert_m} —, "),
        "{{AI_ROLES}}": _h(_phrase_roles([("Anthropic (Claude API)", t_a.get("principal"), t_a.get("secours")),
                                          ("Mistral AI (La Plateforme)", t_m.get("principal"), t_m.get("secours"))])),
        "{{AI_ENTRAINEMENT}}": _h(f"{_ANTH_ENTRAINEMENT} ; {entr_m}"),
        "{{AI_ENTRAINEMENT_FOURNISSEURS}}": _h("de nos fournisseurs, Anthropic et Mistral AI"
                                               + (" (chez Mistral AI, nous avons désactivé cette utilisation sur "
                                                  "notre compte)" if desinscrit else "")),
        "{{AI_CONSERVATION}}": _h(f"{_ANTH_CONSERVATION} ; {_MISTRAL_CONSERVATION}"),
        **communs_mistral,
    }


def _legal_page(name: str):
    from fastapi.responses import HTMLResponse
    with open(os.path.join(_static_dir, "legal", name), encoding="utf-8") as f:
        html = f.read()
    if "{{AI_" in html:
        for k, v in _ai_subprocessor_fragments().items():
            html = html.replace(k, v)
    return HTMLResponse(html)


@app.get("/mentions-legales", tags=["Site"], include_in_schema=False)
def mentions_legales():
    return _legal_page("mentions-legales.html")


@app.get("/cgv", tags=["Site"], include_in_schema=False)
def cgv():
    return _legal_page("cgv.html")


@app.get("/confidentialite", tags=["Site"], include_in_schema=False)
def confidentialite():
    return _legal_page("confidentialite.html")


@app.get("/dpa", tags=["Site"], include_in_schema=False)
def dpa():
    return _legal_page("dpa.html")


@app.get("/securite", tags=["Site"], include_in_schema=False)
def securite():
    return _legal_page("securite.html")


@app.get("/demande-acces", tags=["Site"], include_in_schema=False)
def demande_acces_page():
    """Demander un accès / réserver une démonstration (remplace la démo publique)."""
    from fastapi.responses import HTMLResponse
    with open(os.path.join(_static_dir, "demande-acces.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/app", tags=["Logiciel"], include_in_schema=False)
def software():
    from fastapi.responses import HTMLResponse
    from app.core.sri import page_html      # empreintes SRI garanties à jour (vague 4)
    return HTMLResponse(page_html("app.html"))


@app.get("/invite/{token}", tags=["Co-traitance"], include_in_schema=False)
def invite_page(token: str):
    """Page d'accès co-traitant (vue bridée). Le jeton est lu côté client puis
    validé par l'API ; cette route ne sert que la coquille HTML."""
    from fastapi.responses import HTMLResponse
    from app.core.sri import page_html
    return HTMLResponse(page_html("invite.html"))

def _serve(name: str):
    from fastapi.responses import HTMLResponse
    from app.core.sri import PAGES, page_html
    if name in PAGES:
        return HTMLResponse(page_html(name))
    with open(os.path.join(_static_dir, name), encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/acheteur", tags=["Acheteur"], include_in_schema=False)
def acheteur_landing():
    """Landing acheteur (collectivités) : présentation + connexion/inscription/démo.
    Même design system et même ton qu'Adjugo. Les CTA pointent vers /acheteur/app."""
    return _serve("acheteur-landing.html")


@app.get("/acheteur/app", tags=["Acheteur"], include_in_schema=False)
def acheteur_app():
    """Application acheteur (collectivités) — même design system que le logiciel PME,
    distincte de ses données ; toute la logique tape /api/dce/* et /api/acheteur/*."""
    return _serve("acheteur.html")


@app.get("/api/health", tags=["Sante"])
def health():
    # Health-check RÉEL : teste la base. Si Postgres est injoignable, on renvoie 503 pour
    # que le load-balancer retire l'instance au lieu de lui envoyer du trafic qui 500.
    from fastapi.responses import JSONResponse
    from sqlalchemy import text as _sqltext
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        db.execute(_sqltext("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        import logging
        logging.getLogger("adjugo").warning("health: base injoignable : %s", e)
        return JSONResponse(status_code=503, content={"status": "error", "db": "unreachable"})
    finally:
        db.close()


@app.get("/api/llm/info", tags=["Sante"])
def llm_info():
    """Fournisseurs d'IA sollicités (sans secret ni détail du routage) : le détail par tâche est dans
    le diagnostic d'administration (GET /api/admin/ia/diagnostic)."""
    from app.services.llm import active_provider
    return active_provider()


@app.get("/api/public-config", tags=["Sante"], include_in_schema=False)
def public_config():
    """Config publique (sans secret) pour le front : analytics activé par env, etc."""
    s = settings
    return {"analytics_src": s.ANALYTICS_SRC or "", "analytics_domain": s.ANALYTICS_DOMAIN or ""}


@app.get("/api/securite/empreintes-scripts", tags=["Sante"])
@limiter.limit("60/minute")
def empreintes_scripts(request: Request):
    """Empreintes (SRI sha384 + sha256) des scripts RÉELLEMENT servis, calculées à chaud, pour
    la page sécurité : chacun peut comparer ce que son navigateur reçoit à ce qui est publié et
    versionné (app/static/sri-manifest.json). Aucune donnée personnelle, aucun secret."""
    from app.core import sri
    m = sri.compute_manifest()
    rep = sri.stale_report()
    m["manifeste_publie"] = "/static/" + sri.MANIFEST_NAME
    m["manifeste_publie_a_jour"] = bool(rep["manifeste_a_jour"])
    m["pages_a_jour"] = not rep["pages"]
    return m


@app.get("/api/health/ready", tags=["Sante"])
def health_ready():
    """Readiness détaillée : base + état du disjoncteur IA + backlog de jobs.
    503 si un sous-système CRITIQUE (base) est en panne."""
    from fastapi.responses import JSONResponse
    from app.core.metrics import readiness
    r = readiness()
    return JSONResponse(status_code=200 if r.get("ready") else 503, content=r)


@app.get("/metrics", tags=["Sante"], include_in_schema=False)
def metrics(request: Request):
    """Métriques Prometheus (agrégats opérationnels). Protégé par un jeton si
    METRICS_TOKEN ou CRON_SECRET est défini (sinon ouvert, pratique en dev)."""
    from fastapi.responses import PlainTextResponse, JSONResponse
    token = os.getenv("METRICS_TOKEN") or settings.CRON_SECRET
    if token:
        auth = request.headers.get("authorization", "")
        provided = auth[7:] if auth.lower().startswith("bearer ") else request.query_params.get("token", "")
        if provided != token:
            return JSONResponse(status_code=401, content={"error": "jeton metrics requis"})
    from app.core.metrics import render
    return PlainTextResponse(render(), media_type="text/plain; version=0.0.4")


# ── Routage de l'IA : résumé au démarrage (aucune clé, aucun appel réseau) ──
@app.on_event("startup")
def _journaliser_routage_ia():
    try:
        from app.services.llm import resume_routage, forcage
        log = _logging.getLogger("adjugo")
        for ligne in resume_routage():
            (log.warning if (forcage() or "ATTENTION" in ligne) else log.info)(ligne)
    except Exception as e:      # noqa: BLE001 — jamais bloquant
        _logging.getLogger("adjugo").warning("résumé du routage IA indisponible : %s", type(e).__name__)


# ── Récupération des jobs orphelins au démarrage ────────────────────────────
@app.on_event("startup")
def _recover_orphan_jobs():
    """Au démarrage, tout job resté « pending/running » est orphelin (le thread est mort
    au redémarrage) : on le passe en erreur et on rembourse l'analyse consommée."""
    from app.core.database import SessionLocal
    from app.models import Job, User
    from app.core.quota import refund_analysis
    from sqlalchemy import update as _update
    db = SessionLocal()
    try:
        for j in db.query(Job).filter(Job.status.in_(["pending", "running"])).all():
            # try PAR job : une panne sur un job (ex. utilisateur supprimé) ne doit pas
            # abandonner silencieusement la récupération de TOUS les jobs suivants.
            try:
                # Claim ATOMIQUE : seul le worker qui change réellement la ligne rembourse
                # (évite le double-remboursement quand 4 workers démarrent ensemble).
                res = db.execute(_update(Job).where(Job.id == j.id, Job.status.in_(["pending", "running"]))
                                 .values(status="error", error="Interrompu par un redémarrage du serveur."))
                db.commit()
                if res.rowcount == 1:
                    from app.services import atelier as _atelier
                    from app.services import fiches_import as _fiches
                    if j.kind in _fiches.JOB_KINDS:
                        # Fiches proposées (rédaction, vague 3) : lecture gratuite, rien n'a été débité ;
                        # passée en erreur, elle n'est plus comptée dans le plafond du mois.
                        continue
                    if j.kind in _atelier.JOB_KINDS:
                        # Atelier : rend EXACTEMENT ce que la tâche a débité (rien pour une refonte
                        # gratuite) et libère les parties qu'elle rédigeait.
                        db.refresh(j)
                        _atelier.rembourser(db, j)
                        _atelier.liberer_job(db, j.id)
                        continue
                    from app.services import atelier_groupement as _groupement
                    if j.kind in _groupement.JOB_KINDS:
                        # Aide de l'IA d'un PARTENAIRE (rédaction, vague 4) : rend au chef de file ce que la
                        # tâche a débité (relevé : payeur_id), libère la partie et rend l'aide au partenaire.
                        db.refresh(j)
                        _atelier.rembourser(db, j)
                        _groupement.liberer_job(db, j.id, rendre_aide=True)
                        continue
                    u = db.get(User, j.user_id) if j.user_id else None
                    if u:
                        refund_analysis(u, db)
            except Exception as e:
                db.rollback()
                _logging.getLogger("adjugo").warning(
                    "récupération du job orphelin %s échouée : %s", getattr(j, "id", "?"), e)
    except Exception as e:
        _logging.getLogger("adjugo").warning("récupération des jobs orphelins interrompue : %s", e)
    finally:
        db.close()


# ── Réparation : jobs des membres retirés AVANT le correctif (faille 8) ─────
@app.on_event("startup")
def _repair_removed_member_jobs():
    """Avant le correctif, retirer un membre ne réassignait pas ses jobs (résultats IA bâtis
    sur la base de l'organisation) : ils restaient à son nom, donc lisibles par lui dans son
    nouvel espace. On les rend à l'organisation, d'après le journal : pour chaque entrée
    `team.member_removed` (owner_id = propriétaire au moment du retrait, target_id = membre),
    les jobs du membre créés AVANT le retrait passent au propriétaire. Idempotent (un 2e
    passage ne trouve plus rien), best-effort, jamais bloquant au démarrage. Le journal
    n'est que LU (son owner_id entre dans le hash de la chaîne : on n'y touche pas)."""
    log = _logging.getLogger("adjugo")
    from app.core.database import SessionLocal
    from app.models import AuditLog, Job, User
    from sqlalchemy import update as _update
    db = SessionLocal()
    moved = 0
    try:
        rows = (db.query(AuditLog.id, AuditLog.owner_id, AuditLog.target_id, AuditLog.created_at)
                .filter(AuditLog.action == "team.member_removed").order_by(AuditLog.id).all())
        for aid, owner_id, member_id, removed_at in rows:
            try:
                if not owner_id or not member_id or owner_id == member_id or removed_at is None:
                    continue
                if db.get(User, owner_id) is None:      # propriétaire supprimé : rien à rendre
                    continue
                res = db.execute(_update(Job)
                                 .where(Job.user_id == member_id, Job.created_at <= removed_at)
                                 .values(user_id=owner_id)
                                 .execution_options(synchronize_session=False))
                db.commit()
                moved += res.rowcount or 0
            except Exception as e:
                db.rollback()
                log.warning("réparation des jobs (journal %s) échouée : %s", aid, e)
        if moved:
            log.info("jobs d'anciens membres rendus à leur organisation : %d", moved)
    except Exception as e:
        db.rollback()
        log.warning("réparation des jobs d'anciens membres interrompue : %s", e)
    finally:
        db.close()
    return moved


# ── Capacité du pool de threads (endpoints sync) ────────────────────────────
@app.on_event("startup")
def _raise_threadpool():
    """Les endpoints synchrones tournent dans un pool de threads partagé (défaut 40).
    On l'élargit pour qu'un appel externe lent (ex. profil acheteur BOAMP) ne puisse
    pas affamer les requêtes rapides et bloquer l'app."""
    try:
        import anyio
        anyio.to_thread.current_default_thread_limiter().total_tokens = 96
    except Exception as e:
        _logging.getLogger("adjugo").info("threadpool non ajusté : %s", e)


# ── Compte de démonstration : présent dès le démarrage ──────────────────────
@app.on_event("startup")
def _ensure_demo_account():
    """Garantit l'existence du compte démo (demo@adjugo.fr), pré-rempli, pour la
    connexion /api/auth/demo. Idempotent ; n'écrase pas un compte existant."""
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        from app.services.demo_seed import ensure_demo
        ensure_demo(db, force=True)   # repart propre à chaque démarrage (anti-dérive)
    except Exception as e:
        _logging.getLogger("adjugo").warning("seed démo ignoré : %s", e)
    finally:
        db.close()


@app.on_event("startup")
def _promote_admins():
    """Promeut en administrateurs les comptes listés dans ADMIN_EMAILS (idempotent)."""
    emails = [e.strip().lower() for e in (settings.ADMIN_EMAILS or "").split(",") if e.strip()]
    if not emails:
        return
    from app.core.database import SessionLocal
    from app.models import User
    db = SessionLocal()
    try:
        n = db.query(User).filter(User.email.in_(emails), User.is_admin.is_(False)).update(
            {User.is_admin: True}, synchronize_session=False)
        db.commit()
        if n:
            _logging.getLogger("adjugo").info("admins promus : %d", n)
    except Exception as e:
        db.rollback()
        _logging.getLogger("adjugo").warning("promotion admin ignorée : %s", e)
    finally:
        db.close()


# ── Veille amont autonome : scan périodique → emails des nouveautés ──
# Court-circuité (zéro appel IA) tant qu'aucun utilisateur n'a activé sa veille auto.
import asyncio as _asyncio
_AMONT_INTERVAL_MIN = int(os.getenv("AMONT_AUTO_INTERVAL_MIN", "240"))  # 0 = désactivé


@app.on_event("startup")
async def _amont_scheduler():
    if _AMONT_INTERVAL_MIN <= 0:
        return

    async def _loop():
        import logging
        from app.core.database import SessionLocal
        from app.services.alerts import run_amont_alerts
        log = logging.getLogger("adjugo")
        await _asyncio.sleep(120)  # premier passage 2 min après le démarrage

        def _run():
            # Verrou consultatif par tick : avec plusieurs workers uvicorn, UN SEUL
            # exécute le scan (plus de 4× emails/appels IA dupliqués).
            from app.core.database import _is_sqlite
            from sqlalchemy import text as _t
            db = SessionLocal()
            try:
                if not _is_sqlite:
                    got = db.execute(_t("SELECT pg_try_advisory_lock(815343)")).scalar()
                    if not got:
                        return None
                try:
                    return run_amont_alerts(db)
                finally:
                    if not _is_sqlite:
                        db.execute(_t("SELECT pg_advisory_unlock(815343)"))
            finally:
                db.close()

        while True:
            try:
                res = await _asyncio.get_event_loop().run_in_executor(None, _run)
                if res and res.get("new_signals"):
                    log.info("veille amont auto : %s", res)
            except Exception as e:
                log.warning("veille amont auto en échec : %s", e)
            await _asyncio.sleep(_AMONT_INTERVAL_MIN * 60)

    _asyncio.create_task(_loop())


@app.on_event("startup")
async def _backup_scheduler():
    """Sauvegarde quotidienne de la base vers R2 (filet de sécurité, gratuit)."""
    hours = settings.BACKUP_INTERVAL_HOURS
    if hours <= 0 or (settings.STORAGE_BACKEND or "").lower() != "s3":
        return  # désactivé, ou stockage local (sauvegarde inutile)

    async def _loop():
        import logging
        from sqlalchemy import text as _t
        from app.core.database import SessionLocal, _is_sqlite
        log = logging.getLogger("adjugo")
        await _asyncio.sleep(300)   # 5 min après le démarrage

        def _run():
            from app.services.backup import run_backup
            # Verrou consultatif : un seul worker sauvegarde par tick.
            db = SessionLocal()
            try:
                if not _is_sqlite:
                    if not db.execute(_t("SELECT pg_try_advisory_lock(815344)")).scalar():
                        return None
                try:
                    return run_backup(keep=settings.BACKUP_KEEP)
                finally:
                    if not _is_sqlite:
                        db.execute(_t("SELECT pg_advisory_unlock(815344)"))
            finally:
                db.close()

        while True:
            try:
                res = await _asyncio.get_event_loop().run_in_executor(None, _run)
                if res and res.get("ok"):
                    log.info("sauvegarde base → R2 : %s", res.get("key"))
            except Exception as e:
                log.warning("sauvegarde auto en échec : %s", e)
            await _asyncio.sleep(hours * 3600)

    _asyncio.create_task(_loop())
