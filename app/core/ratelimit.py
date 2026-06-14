"""
Rate limiting (slowapi).
Clé = IP réelle du client (prend en compte X-Forwarded-For derrière un proxy).
Stockage : mémoire en dev, Redis en prod multi-workers (RATELIMIT_STORAGE_URI).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import get_settings

settings = get_settings()


def client_key(request) -> str:
    """IP réelle : 1er IP de X-Forwarded-For si présent (reverse proxy), sinon IP directe."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(
    key_func=client_key,
    storage_uri=settings.RATELIMIT_STORAGE_URI or "memory://",
    default_limits=[],
)
