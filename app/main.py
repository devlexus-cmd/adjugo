import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from app.core.config import get_settings
from app.core.database import engine, Base, _is_sqlite
from app.routers import auth, projects, invoices, contacts, documents, analysis, cerfa, stripe_pay, cotraitants, export_dossier, checklist
from app.routers.company import company_router, criteria_router
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


app.middleware("http")(request_logger)

# CSP — verrouille les origines. 'unsafe-eval'/'unsafe-inline' requis car Vue (CDN)
# compile les templates à l'exécution et l'app utilise des styles inline (pas de build).
# Un build front permettrait de les retirer plus tard.
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://unpkg.com https://cdn.jsdelivr.net; "
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
    # Anti-cache sur l'app et ses assets (évite d'exécuter un app.js/css périmé)
    p = request.url.path
    if p == "/app" or p == "/" or p.startswith("/static"):
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
    return resp


app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(analysis.router)
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

# Fichiers statiques du logiciel (SPA)
_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/", tags=["Site"], include_in_schema=False)
def root():
    from fastapi.responses import HTMLResponse
    with open(os.path.join(_static_dir, "landing.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/app", tags=["Logiciel"], include_in_schema=False)
def software():
    from fastapi.responses import HTMLResponse
    with open(os.path.join(_static_dir, "app.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/api/health", tags=["Sante"])
def health():
    return {"status": "ok"}


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
            db = SessionLocal()
            try:
                return run_amont_alerts(db)
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
