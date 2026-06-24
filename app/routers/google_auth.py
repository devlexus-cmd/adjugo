"""
Connexion « Se connecter avec Google » (OAuth 2.0 — Authorization Code).

Flux : le front ouvre /api/auth/google/login → redirection vers l'écran de consentement Google
→ Google rappelle /api/auth/google/callback?code=… → on échange le code (server-to-server, avec
le client_secret) contre les infos du compte → on retrouve/crée l'utilisateur (rattaché par email)
→ on émet notre JWT maison et on renvoie le front sur /app?gtoken=…

Entièrement INACTIF tant que GOOGLE_CLIENT_ID/SECRET ne sont pas configurés (zéro risque).
"""
import logging
import secrets as _secrets
from datetime import timedelta
from urllib.parse import urlencode, quote

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
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


def _redirect_uri() -> str:
    s = get_settings()
    return s.GOOGLE_REDIRECT_URI or (s.APP_BASE_URL.rstrip("/") + "/api/auth/google/callback")


def _front(path: str = "/app") -> str:
    return get_settings().APP_BASE_URL.rstrip("/") + path


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
    # state signé (anti-CSRF) : on le revérifie au retour. Court (10 min), à usage unique de fait.
    state = create_access_token({"purpose": "google_oauth", "nonce": _secrets.token_urlsafe(8)},
                                expires_delta=timedelta(minutes=10))
    params = {
        "client_id": s.GOOGLE_CLIENT_ID,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return RedirectResponse(_AUTH_URL + "?" + urlencode(params))


@router.get("/google/callback")
def google_callback(code: str = "", state: str = "", error: str = "",
                    db: Session = Depends(get_db)):
    s = get_settings()
    if not (s.GOOGLE_CLIENT_ID and s.GOOGLE_CLIENT_SECRET):
        return RedirectResponse(_front("/app?gerror=" + quote("Connexion Google non configurée")))
    if error or not code:
        return RedirectResponse(_front("/app?gerror=" + quote(error or "Connexion annulée")))
    # Vérifie l'état (anti-CSRF)
    try:
        st = decode_token(state)
        if st.get("purpose") != "google_oauth":
            raise ValueError("purpose")
    except Exception:
        return RedirectResponse(_front("/app?gerror=" + quote("Session OAuth invalide, réessayez")))

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
        return RedirectResponse(_front("/app?gerror=" + quote("Échec de la connexion Google, réessayez")))

    email = (info.get("email") or "").strip().lower()
    # On EXIGE un email vérifié par Google (sinon usurpation d'identité possible).
    if not email or not info.get("email_verified", False):
        return RedirectResponse(_front("/app?gerror=" + quote("Adresse Google non vérifiée")))
    name = (info.get("name") or "").strip()

    user = db.query(User).filter(func.lower(User.email) == email).first()
    is_new = user is None
    if user:
        if not user.is_active:
            return RedirectResponse(_front("/app?gerror=" + quote("Compte désactivé")))
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

    jwt = create_access_token({"sub": str(user.id), "tv": int(user.token_version or 0)})
    return RedirectResponse(_front("/app?gtoken=" + jwt))
