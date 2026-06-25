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

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, description="API pour la gestion des marches publics", docs_url="/docs")

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


app.middleware("http")(request_logger)

# CSP — verrouille les origines. 'unsafe-eval'/'unsafe-inline' requis car Vue (CDN)
# compile les templates à l'exécution et l'app utilise des styles inline (pas de build).
# Un build front permettrait de les retirer plus tard.
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "img-src 'self' data: blob: https://cdn.jsdelivr.net https://fastapi.tiangolo.com; "
    "connect-src 'self'; worker-src 'self' blob:; "
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


def _ai_subprocessor_fragments():
    """Fragments décrivant le sous-traitant IA RÉELLEMENT actif, injectés dans les pages
    légales (confidentialité + DPA). Ainsi le doc reflète toujours la vérité : Anthropic (US)
    tant que c'est Anthropic, Mistral (FR/UE) dès qu'on bascule — aucune mise à jour manuelle,
    aucun risque que la politique « mente » sur la localisation des données."""
    try:
        from app.services.llm import active_provider
        if active_provider().get("provider") == "mistral":
            return {
                "{{AI_PROVIDER}}": "Mistral AI",
                "{{AI_PRODUCT}}": "La Plateforme",
                "{{AI_LOCATION_FULL}}": "<strong>Union européenne</strong> (France — api.mistral.ai)",
                "{{AI_LOCATION_SHORT}}": "Union européenne (France)",
                "{{AI_TRANSFER_MENTION}}": "",   # IA hébergée en UE → plus de transfert pays tiers pour ce traitement
            }
    except Exception:
        pass
    # Défaut sûr : Anthropic (état de production actuel).
    return {
        "{{AI_PROVIDER}}": "Anthropic, PBC",
        "{{AI_PRODUCT}}": "Claude API",
        "{{AI_LOCATION_FULL}}": "<strong>États-Unis</strong> (API standard api.anthropic.com — encadré par CCT)",
        "{{AI_LOCATION_SHORT}}": "États-Unis (CCT)",
        "{{AI_TRANSFER_MENTION}}": "le fournisseur d&#x27;IA (Anthropic, États-Unis) pour l&#x27;analyse et la génération de documents, ",
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


@app.get("/app", tags=["Logiciel"], include_in_schema=False)
def software():
    from fastapi.responses import HTMLResponse
    with open(os.path.join(_static_dir, "app.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/invite/{token}", tags=["Co-traitance"], include_in_schema=False)
def invite_page(token: str):
    """Page d'accès co-traitant (vue bridée). Le jeton est lu côté client puis
    validé par l'API ; cette route ne sert que la coquille HTML."""
    from fastapi.responses import HTMLResponse
    with open(os.path.join(_static_dir, "invite.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())

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
    """Fournisseur IA actif (sans secret). Prouve que l'architecture est découplée :
    bascule Anthropic ↔ Mistral (souverain FR/EU) par simple variable d'environnement."""
    from app.services.llm import active_provider
    return active_provider()


@app.get("/api/public-config", tags=["Sante"], include_in_schema=False)
def public_config():
    """Config publique (sans secret) pour le front : analytics activé par env, etc."""
    s = settings
    return {"analytics_src": s.ANALYTICS_SRC or "", "analytics_domain": s.ANALYTICS_DOMAIN or ""}


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
            # Claim ATOMIQUE : seul le worker qui change réellement la ligne rembourse
            # (évite le double-remboursement quand 4 workers démarrent ensemble).
            res = db.execute(_update(Job).where(Job.id == j.id, Job.status.in_(["pending", "running"]))
                             .values(status="error", error="Interrompu par un redémarrage du serveur."))
            db.commit()
            if res.rowcount == 1:
                u = db.get(User, j.user_id)
                if u:
                    refund_analysis(u, db)
    except Exception:
        pass
    finally:
        db.close()


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
