"""
Connexion « Se connecter avec Google » (OAuth 2.0 — Authorization Code).

Flux (durci, audit cyber oct. 2026 rang 18) :
  1. /api/auth/google/login : on tire un nonce aléatoire, posé dans un cookie HttpOnly
     (SameSite=Lax, chemin restreint au retour, 10 min), et on envoie à Google un `state`
     signé qui contient l'empreinte de ce nonce → redirection vers l'écran de consentement.
  2. Google rappelle /api/auth/google/callback?code=…&state=… : on exige un `state` signé
     valide ET le cookie du MÊME navigateur (empreinte identique), puis on efface le cookie.
     Sans cela, un attaquant pourrait faire atterrir une victime dans SON compte Google.
     On échange ensuite le code (server-to-server, avec le client_secret) contre les infos
     du compte, et on retrouve/crée l'utilisateur (rattaché par email).
  3. Le jeton de session ne passe JAMAIS dans une URL : on renvoie le front sur
     /app#gcode=<code> — un code à usage unique, valable 60 s, gardé en mémoire du process
     (process unique) — que le front échange contre le jeton par POST /api/auth/google/exchange.
     Le fragment (#) n'est ni envoyé au serveur, ni journalisé, ni transmis dans le Referer.

Entièrement INACTIF tant que GOOGLE_CLIENT_ID/SECRET ne sont pas configurés (zéro risque).
"""
import hashlib
import hmac
import logging
import secrets as _secrets
import threading
import time
from datetime import timedelta
from urllib.parse import urlencode, quote, urlparse

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.core.ratelimit import limiter
from app.core.security import hash_password, create_access_token, decode_token
from app.models import User, MatchingCriteria, Organization

logger = logging.getLogger("adjugo")
router = APIRouter(prefix="/api/auth", tags=["Authentification"])

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

STATE_COOKIE = "adjugo_g_state"
STATE_TTL_S = 600          # durée de vie du state et du cookie lié (10 min)
EXCHANGE_TTL_S = 60        # durée de vie du code d'échange (60 s)
_EXCHANGE_MAX = 5000       # borne mémoire du magasin de codes

_MSG_STATE = "Session de connexion Google invalide ou expirée. Relancez « Se connecter avec Google »."
_MSG_BROWSER = ("Connexion Google refusée : elle n'a pas été lancée depuis ce navigateur, ou a expiré. "
                "Relancez « Se connecter avec Google ».")
_MSG_EXCHANGE = "Lien de connexion Google invalide ou expiré. Relancez « Se connecter avec Google »."

# Codes d'échange à usage unique : empreinte du code → (user_id, token_version, échéance).
# En mémoire du process : correct avec le process unique (cf. entrypoint.sh). Le code en
# clair n'est jamais conservé, seulement son empreinte.
_exchange_lock = threading.Lock()
_exchange_codes: dict = {}


def _now() -> float:
    return time.monotonic()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _redirect_uri() -> str:
    s = get_settings()
    return s.GOOGLE_REDIRECT_URI or (s.APP_BASE_URL.rstrip("/") + "/api/auth/google/callback")


def _front(path: str = "/app") -> str:
    return get_settings().APP_BASE_URL.rstrip("/") + path


def _callback_path() -> str:
    """Chemin du retour Google : le cookie du state n'est envoyé QUE là."""
    return urlparse(_redirect_uri()).path or "/api/auth/google/callback"


def _cookie_secure() -> bool:
    """Cookie Secure partout, sauf en développement servi en http (sinon il ne reviendrait
    jamais au navigateur et la connexion échouerait toujours en local)."""
    s = get_settings()
    return s.ENVIRONMENT == "production" or not _redirect_uri().lower().startswith("http://")


def _clear_state_cookie(resp):
    resp.delete_cookie(STATE_COOKIE, path=_callback_path(), secure=_cookie_secure(),
                       httponly=True, samesite="lax")
    return resp


def _fail(message: str):
    """Refus propre : retour au front avec un message en français, cookie effacé."""
    resp = RedirectResponse(_front("/app?gerror=" + quote(message)))
    resp.headers["Cache-Control"] = "no-store"
    return _clear_state_cookie(resp)


def _issue_exchange_code(user: User) -> str:
    code = _secrets.token_urlsafe(32)
    now = _now()
    with _exchange_lock:
        for k in [k for k, v in _exchange_codes.items() if v[2] <= now]:
            _exchange_codes.pop(k, None)
        while len(_exchange_codes) >= _EXCHANGE_MAX:            # borne mémoire : plus anciens d'abord
            _exchange_codes.pop(next(iter(_exchange_codes)), None)
        _exchange_codes[_digest(code)] = (user.id, int(user.token_version or 0), now + EXCHANGE_TTL_S)
    return code


def _consume_exchange_code(code: str):
    """Retire le code du magasin (usage unique, même en cas d'échec) ; None si inconnu/expiré."""
    if not code or not isinstance(code, str) or len(code) > 200:
        return None
    with _exchange_lock:
        entry = _exchange_codes.pop(_digest(code), None)
    if not entry or entry[2] <= _now():
        return None
    return entry


@router.get("/oauth-config")
def oauth_config():
    """Public : le front sait s'il doit afficher le bouton « Se connecter avec Google »."""
    s = get_settings()
    return {"google": bool(s.GOOGLE_CLIENT_ID and s.GOOGLE_CLIENT_SECRET)}


@router.get("/google/login")
@limiter.limit("30/minute")
def google_login(request: Request):
    s = get_settings()
    if not (s.GOOGLE_CLIENT_ID and s.GOOGLE_CLIENT_SECRET):
        raise HTTPException(503, "Connexion Google non configurée.")
    # Nonce lié au navigateur : en clair dans le cookie HttpOnly, seulement son empreinte
    # dans le state signé (10 min). Le retour exige les deux.
    nonce = _secrets.token_urlsafe(32)
    state = create_access_token({"purpose": "google_oauth", "nh": _digest(nonce)},
                                expires_delta=timedelta(seconds=STATE_TTL_S))
    params = {
        "client_id": s.GOOGLE_CLIENT_ID,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    resp = RedirectResponse(_AUTH_URL + "?" + urlencode(params))
    resp.set_cookie(STATE_COOKIE, nonce, max_age=STATE_TTL_S, path=_callback_path(),
                    secure=_cookie_secure(), httponly=True, samesite="lax")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.get("/google/callback")
@limiter.limit("30/minute")
def google_callback(request: Request, code: str = "", state: str = "", error: str = "",
                    db: Session = Depends(get_db)):
    s = get_settings()
    if not (s.GOOGLE_CLIENT_ID and s.GOOGLE_CLIENT_SECRET):
        return _fail("Connexion Google non configurée.")
    if error or not code:
        # Message fixe : le paramètre `error` vient de l'URL, on ne le réaffiche pas.
        return _fail("Connexion Google annulée." if (not error or error == "access_denied")
                     else "Connexion Google interrompue. Réessayez.")
    # 1) state signé, émis par Adjugo il y a moins de 10 min (protection existante).
    try:
        st = decode_token(state)
        if st.get("purpose") != "google_oauth":
            raise ValueError("purpose")
    except Exception:
        return _fail(_MSG_STATE)
    # 2) …et lancé depuis CE navigateur : le cookie doit être présent et correspondre.
    nonce = request.cookies.get(STATE_COOKIE) or ""
    expected = str(st.get("nh") or "")
    if not nonce or not expected or not hmac.compare_digest(_digest(nonce), expected):
        logger.warning("google oauth: retour refusé (cookie de connexion absent ou différent)")
        return _fail(_MSG_BROWSER)

    # Échange code → access_token (server-to-server, avec le client_secret)
    try:
        tok = requests.post(_TOKEN_URL, timeout=15, data={
            "code": code,
            "client_id": s.GOOGLE_CLIENT_ID,
            "client_secret": s.GOOGLE_CLIENT_SECRET,
            "redirect_uri": _redirect_uri(),
            "grant_type": "authorization_code",
        }).json()
        access = tok.get("access_token")
        if not access:
            raise ValueError(tok.get("error_description") or "token")
        info = requests.get(_USERINFO_URL, timeout=15,
                            headers={"Authorization": "Bearer " + access}).json()
    except Exception as e:
        logger.warning("google oauth: échange/userinfo en échec : %s", e)
        return _fail("Échec de la connexion Google, réessayez.")

    email = (info.get("email") or "").strip().lower()
    # On EXIGE un email vérifié par Google (sinon usurpation d'identité possible).
    if not email or not info.get("email_verified", False):
        return _fail("Adresse Google non vérifiée.")
    name = (info.get("name") or "").strip()

    user = db.query(User).filter(func.lower(User.email) == email).first()
    is_new = user is None
    if user:
        if not user.is_active:
            return _fail("Compte désactivé.")
        # On NE force PLUS la vérification ici : la vérification d'email Adjugo s'applique à TOUT
        # le monde, quel que soit le mode de connexion (la bannière + le mail s'en chargent).
    else:
        # Création via Google : mot de passe aléatoire INUTILISABLE (il peut en définir un plus tard
        # via « mot de passe oublié »). email_verified=False → il devra confirmer son adresse comme
        # une inscription classique.
        user = User(email=email, hashed_password=hash_password(_secrets.token_urlsafe(24)),
                    full_name=name, org_role="admin", email_verified=False)
        db.add(user)
        db.flush()
        org = Organization(name=(f"Équipe {name}" if name else "Mon organisation"), owner_id=user.id)
        db.add(org)
        db.flush()
        user.org_id = org.id
        db.add(MatchingCriteria(user_id=user.id))
        db.commit()
        db.refresh(user)

    # Email de confirmation à la CRÉATION du compte (comme l'inscription par mot de passe) — pas à
    # chaque connexion, pour ne pas spammer. Un ancien compte non vérifié garde la bannière + « Renvoyer ».
    if is_new:
        from app.routers.auth import _send_verification
        _send_verification(user)

    # Jamais de jeton de session dans l'URL : code à usage unique dans le fragment.
    resp = RedirectResponse(_front("/app#gcode=" + _issue_exchange_code(user)))
    resp.headers["Cache-Control"] = "no-store"
    return _clear_state_cookie(resp)


class GoogleExchangeIn(BaseModel):
    code: str = Field("", max_length=200)


@router.post("/google/exchange")
@limiter.limit("30/minute")
def google_exchange(request: Request, payload: GoogleExchangeIn, db: Session = Depends(get_db)):
    """Échange le code à usage unique (60 s) reçu dans le fragment contre le jeton de session."""
    entry = _consume_exchange_code(payload.code)
    if not entry:
        raise HTTPException(400, _MSG_EXCHANGE)
    user_id, tv, _ = entry
    user = db.query(User).filter(User.id == user_id).first()
    # Compte désactivé ou sessions révoquées (changement de mot de passe…) entre-temps → refus.
    if not user or not user.is_active or int(user.token_version or 0) != tv:
        raise HTTPException(400, _MSG_EXCHANGE)
    jwt = create_access_token({"sub": str(user.id), "tv": tv})
    return JSONResponse({"access_token": jwt, "token_type": "bearer"},
                        headers={"Cache-Control": "no-store"})
