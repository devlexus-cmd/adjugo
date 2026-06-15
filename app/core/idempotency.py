"""
Idempotence des requêtes mutantes (POST/PUT/PATCH).

Un client qui REJOUE une requête (timeout réseau, double-clic, retry) avec le même
en-tête `Idempotency-Key` reçoit la RÉPONSE MISE EN CACHE de la première exécution,
sans réexécuter le traitement. Essentiel ici : une analyse AO est facturée — un retry
ne doit jamais débiter deux fois ni relancer deux fois le LLM.

OPT-IN et sûr : sans l'en-tête, c'est un passe-plat strict (comportement inchangé).
Ne s'active que sur POST/PUT/PATCH (les téléchargements de fichiers sont des GET, donc
jamais bufferisés ici). Cache mémoire borné + TTL ; pour le multi-worker, fournir Redis
(même clé) — cf. invariants d'architecture (état partagé par processus).
"""
import threading
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

_STORE = {}              # clé -> (expiration, status, headers, body)
_LOCK = threading.Lock()
_TTL = 300               # 5 min
_MAX_ENTRIES = 2000
_MAX_BODY = 256 * 1024   # on ne met en cache que des réponses JSON raisonnables


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        key = request.headers.get("idempotency-key")
        if not key or request.method not in ("POST", "PUT", "PATCH"):
            return await call_next(request)

        # Clé cantonnée à (clé client, méthode, chemin, identité) : pas de collision
        # entre endpoints ni entre utilisateurs.
        auth = request.headers.get("authorization", "")
        ck = f"{key}|{request.method}|{request.url.path}|{hash(auth)}"
        now = time.monotonic()

        with _LOCK:
            ent = _STORE.get(ck)
            if ent and ent[0] > now:
                _, status, headers, body = ent
                h = dict(headers)
                h["Idempotent-Replayed"] = "true"
                return Response(content=body, status_code=status, headers=h)

        resp = await call_next(request)

        # Bufferise le corps (BaseHTTPMiddleware consomme déjà l'itérateur).
        body = b""
        async for chunk in resp.body_iterator:
            body += chunk

        if 200 <= resp.status_code < 300 and len(body) <= _MAX_BODY:
            headers = [(k, v) for k, v in resp.headers.items() if k.lower() != "content-length"]
            with _LOCK:
                if len(_STORE) >= _MAX_ENTRIES:
                    _STORE.pop(next(iter(_STORE)), None)
                _STORE[ck] = (now + _TTL, resp.status_code, headers, body)

        return Response(content=body, status_code=resp.status_code,
                        headers=dict(resp.headers), media_type=resp.media_type)
