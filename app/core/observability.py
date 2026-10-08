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
from app.core.redact import install_log_redaction, redact

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
    # Masquage des jetons (invitation, confirmation, réinitialisation, JWT) et des emails
    # sur les handlers : racine + ceux d'uvicorn (déjà configurés quand l'app est
    # importée). Sentry lit le même enregistrement APRÈS les handlers : ses évènements et
    # fils d'Ariane issus des journaux partent donc eux aussi masqués.
    install_log_redaction()


# En-têtes jamais transmis à Sentry (secrets d'authentification).
_SENTRY_DROP_HEADERS = {"authorization", "cookie", "set-cookie", "proxy-authorization",
                        "x-cron-secret", "x-api-key"}


def _strip_request(event: dict) -> None:
    req = event.get("request")
    if not isinstance(req, dict):
        return
    req.pop("cookies", None)
    req.pop("data", None)          # corps de requête : contenu métier, jamais envoyé
    headers = req.get("headers")
    if isinstance(headers, dict):
        for h in list(headers):
            if str(h).lower() in _SENTRY_DROP_HEADERS:
                headers.pop(h, None)
    elif isinstance(headers, list):
        req["headers"] = [kv for kv in headers
                          if not (isinstance(kv, (list, tuple)) and kv
                                  and str(kv[0]).lower() in _SENTRY_DROP_HEADERS)]


def sentry_before_send(event, hint=None):
    """Crochet Sentry : retire cookies, en-tête Authorization et corps de requête, puis
    masque jetons et emails PARTOUT (URL, query string, messages, exceptions, fils
    d'Ariane, extras). Si le masquage échoue, l'évènement est ABANDONNÉ : on ne prend
    jamais le risque d'envoyer une donnée non masquée."""
    try:
        if not isinstance(event, dict):
            return None
        _strip_request(event)
        user = event.get("user")
        if isinstance(user, dict):   # identifiant technique seulement (ni email ni nom)
            event["user"] = {k: v for k, v in user.items() if k == "id"}
        return redact(event)
    except Exception:
        return None


def sentry_before_breadcrumb(crumb, hint=None):
    """Crochet Sentry des fils d'Ariane (journaux, requêtes HTTP sortantes…)."""
    try:
        if not isinstance(crumb, dict):
            return None
        return redact(crumb)
    except Exception:
        return None


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
            # Périmètre déclaré dans la politique de confidentialité (§6) : journaux
            # techniques, identifiants techniques, adresse IP. Donc pas de données
            # personnelles par défaut, pas de corps de requête, pas de variables locales
            # (elles peuvent contenir un DCE ou un profil), et masquage avant tout envoi.
            send_default_pii=False,
            max_request_body_size="never",
            include_local_variables=False,
            before_send=sentry_before_send,
            before_send_transaction=sentry_before_send,
            before_breadcrumb=sentry_before_breadcrumb,
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
