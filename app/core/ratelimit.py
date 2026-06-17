"""
Rate limiting (slowapi).
Clé = IP réelle du client (prend en compte X-Forwarded-For derrière un proxy).
Stockage : mémoire en dev, Redis en prod multi-workers (RATELIMIT_STORAGE_URI).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import get_settings

settings = get_settings()


def real_client_ip(request, hops: int = None) -> str:
    """IP réelle du client, NON spoofable.

    Un client peut préfixer de faux IP dans X-Forwarded-For, mais ne peut pas retirer
    celui que le proxy de confiance (edge Railway) AJOUTE en DERNIER. On prend donc le
    hop le plus à droite (après TRUSTED_PROXY_HOPS proxies), pas le 1er — sinon le
    rate-limit anti-bruteforce de token et l'IP journalisée sont contournables par en-tête.
    """
    if hops is None:
        hops = getattr(settings, "TRUSTED_PROXY_HOPS", 1)
    hops = max(1, int(hops or 1))
    xff = request.headers.get("x-forwarded-for")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[-hops] if len(parts) >= hops else parts[0]
    return get_remote_address(request)


def client_key(request) -> str:
    """Clé de rate-limit = IP réelle (cf. real_client_ip)."""
    return real_client_ip(request)


limiter = Limiter(
    key_func=client_key,
    storage_uri=settings.RATELIMIT_STORAGE_URI or "memory://",
    default_limits=[],
)
