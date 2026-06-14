"""
Observabilité : logs structurés + Sentry (optionnel).
Sentry n'est activé que si SENTRY_DSN est défini ; sinon tout est no-op
(et le paquet sentry-sdk n'a même pas besoin d'être installé en local).
"""
import logging
import sys
import time
import uuid

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger("adjugo")


def setup_logging() -> None:
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s", "%Y-%m-%dT%H:%M:%S"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Réduire le bruit
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def init_sentry() -> bool:
    """Initialise Sentry si un DSN est configuré. Retourne True si activé."""
    if not settings.SENTRY_DSN:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            integrations=[StarletteIntegration(), FastApiIntegration()],
        )
        logger.info("Sentry activé (env=%s)", settings.ENVIRONMENT)
        return True
    except Exception as e:  # paquet absent ou DSN invalide
        logger.warning("Sentry non initialisé : %s", e)
        return False


async def request_logger(request, call_next):
    """Middleware : log structuré de chaque requête + en-tête X-Request-ID."""
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        dur = (time.perf_counter() - start) * 1000
        logger.exception("request method=%s path=%s status=500 dur_ms=%.1f id=%s",
                         request.method, request.url.path, dur, rid)
        raise
    dur = (time.perf_counter() - start) * 1000
    # On ignore le bruit des assets statiques
    if not request.url.path.startswith("/static"):
        log = logger.warning if response.status_code >= 500 else (
            logger.info if response.status_code >= 400 else logger.debug)
        log("request method=%s path=%s status=%s dur_ms=%.1f id=%s",
            request.method, request.url.path, response.status_code, dur, rid)
    response.headers["X-Request-ID"] = rid
    return response
