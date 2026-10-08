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

BORNÉ (audit cyber oct. 2026, faille 2) : ce middleware tourne AVANT l'authentification.
Il ne lit donc JAMAIS un corps sans limite : passe-plat strict (aucune mise en cache) si le
corps est un envoi de fichier (multipart/*), si Content-Length est absent/invalide ou
dépasse _MAX_REQ_BODY ; sinon lecture du flux par morceaux, arrêtée à _MAX_REQ_BODY + 1
octet (au-delà : passe-plat, les morceaux déjà lus sont réinjectés tels quels pour
l'application, qui reçoit exactement le flux d'origine). Middleware ASGI pur (pas de
BaseHTTPMiddleware) : la réponse est relayée au fil de l'eau, mise en cache seulement si
elle est petite.
"""
import hashlib
import threading
import time

_STORE = {}              # clé -> (expiration, status, headers bruts, body)
_LOCK = threading.Lock()
_TTL = 300               # 5 min
_MAX_ENTRIES = 2000
_MAX_BODY = 256 * 1024       # on ne met en cache que des réponses JSON raisonnables
_MAX_REQ_BODY = 256 * 1024   # au-delà, la requête n'est pas éligible au rejeu (passe-plat)
_METHODS = ("POST", "PUT", "PATCH")


def _replaying_receive(messages, receive):
    """receive() qui rend d'abord les messages déjà lus, puis délègue au flux d'origine."""
    pending = list(messages)

    async def _receive():
        if pending:
            return pending.pop(0)
        return await receive()
    return _receive


class IdempotencyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") not in _METHODS:
            return await self.app(scope, receive, send)
        headers = {}
        for k, v in scope.get("headers") or []:
            headers[k.lower()] = v
        key = headers.get(b"idempotency-key", b"").decode("latin-1").strip()
        if not key:
            return await self.app(scope, receive, send)

        # Éligibilité AVANT toute lecture : pas de fichier, taille annoncée et petite.
        ctype = headers.get(b"content-type", b"").decode("latin-1").strip().lower()
        if ctype.startswith("multipart/"):
            return await self.app(scope, receive, send)
        try:
            declared = int(headers[b"content-length"].decode("latin-1").strip())
        except (KeyError, ValueError):
            declared = -1
        if declared < 0 or declared > _MAX_REQ_BODY:
            return await self.app(scope, receive, send)

        # Lecture bornée du flux (jamais plus de _MAX_REQ_BODY + 1 octets en mémoire ici).
        messages, total, complete = [], 0, False
        while True:
            msg = await receive()
            messages.append(msg)
            if msg.get("type") != "http.request":
                break                                  # déconnexion : on laisse l'app gérer
            total += len(msg.get("body", b""))
            if total > _MAX_REQ_BODY:
                break                                  # client qui ment sur la taille
            if not msg.get("more_body", False):
                complete = True
                break
        if not complete:
            return await self.app(scope, _replaying_receive(messages, receive), send)
        body_bytes = b"".join(m.get("body", b"") for m in messages)
        app_receive = _replaying_receive(
            [{"type": "http.request", "body": body_bytes, "more_body": False}], receive)

        # Clé cantonnée à (clé client, méthode, chemin + QUERY, identité, EMPREINTE DU CORPS) :
        # pas de collision entre endpoints, utilisateurs, ni charges utiles différentes. La query
        # DOIT en faire partie : des POST portent leur charge en query (ex. create-checkout?plan=)
        # → sans elle, ?plan=pro et ?plan=business partageaient la même réponse cachée.
        # Chemin = celui réellement routé (scope), jamais reconstruit depuis l'en-tête Host.
        auth = headers.get(b"authorization", b"")
        auth_h = hashlib.sha256(auth).hexdigest()[:16]
        body_h = hashlib.sha256(body_bytes).hexdigest()[:16]
        qs = (scope.get("query_string") or b"").decode("latin-1")
        path_q = scope.get("path", "") + ("?" + qs if qs else "")
        ck = f"{key}|{scope['method']}|{path_q}|{auth_h}|{body_h}"
        now = time.monotonic()

        with _LOCK:
            ent = _STORE.get(ck)
            ent = ent if ent and ent[0] > now else None
        if ent:
            _, status, raw_headers, body = ent
            out = list(raw_headers) + [(b"content-length", str(len(body)).encode()),
                                       (b"idempotent-replayed", b"true")]
            await send({"type": "http.response.start", "status": status, "headers": out})
            await send({"type": "http.response.body", "body": body, "more_body": False})
            return

        state = {"status": 0, "headers": [], "chunks": [], "size": 0, "overflow": False, "done": False}

        async def _send(message):
            t = message.get("type")
            if t == "http.response.start":
                state["status"] = message.get("status", 0)
                state["headers"] = [(k, v) for k, v in message.get("headers") or []
                                    if k.lower() != b"content-length"]
            elif t == "http.response.body" and not state["overflow"]:
                chunk = message.get("body", b"")
                state["size"] += len(chunk)
                if state["size"] > _MAX_BODY:
                    state["overflow"], state["chunks"] = True, []
                else:
                    state["chunks"].append(chunk)
                if not message.get("more_body", False):
                    state["done"] = True
            await send(message)

        await self.app(scope, app_receive, _send)

        if 200 <= state["status"] < 300 and state["done"] and not state["overflow"]:
            with _LOCK:
                if len(_STORE) >= _MAX_ENTRIES:
                    _STORE.pop(next(iter(_STORE)), None)
                _STORE[ck] = (now + _TTL, state["status"], state["headers"], b"".join(state["chunks"]))
