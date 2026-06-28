import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    return f"{salt}${hashed}"


def verify_password(plain: str, hashed: str) -> bool:
    try:
        salt, stored_hash = hashed.split("$")
        check = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 100000).hex()
        return hmac.compare_digest(check, stored_hash)   # comparaison à temps constant
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        # require=["exp"] : refuse un token SANS expiration (un token éternel ne doit jamais
        # être accepté). L'algorithme est fixé (pas de 'none'/confusion d'algo).
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
                          options={"require_exp": True})
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalide ou expire", headers={"WWW-Authenticate": "Bearer"})


oauth2_acheteur = OAuth2PasswordBearer(tokenUrl="/api/acheteur/login")


def get_current_acheteur(token: str = Depends(oauth2_acheteur), db: Session = Depends(get_db)):
    """Auth de l'ESPACE ACHETEUR (collectivités), strictement cloisonnée du produit PME :
    le token DOIT porter `typ="acheteur"` et l'identité est chargée depuis la table
    SÉPARÉE `acheteurs` (jamais `users`). Un token PME (sans `typ`) est donc rejeté."""
    from app.models import Acheteur
    payload = decode_token(token)
    if payload.get("typ") != "acheteur":
        raise HTTPException(status_code=401, detail="Token acheteur requis",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        aid = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Token invalide")
    acheteur = db.query(Acheteur).filter(Acheteur.id == aid).first()
    if acheteur is None:
        raise HTTPException(status_code=404, detail="Compte introuvable")
    if not getattr(acheteur, "is_active", True):
        raise HTTPException(status_code=403, detail="Compte désactivé",
                            headers={"WWW-Authenticate": "Bearer"})
    if int(payload.get("tv") or 0) != int(getattr(acheteur, "token_version", 0) or 0):
        raise HTTPException(status_code=401, detail="Session expirée, reconnectez-vous",
                            headers={"WWW-Authenticate": "Bearer"})
    return acheteur


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    from app.models import User
    payload = decode_token(token)
    # Cloisonnement 2 faces : un token ACHETEUR (qui porte `typ`) ne doit JAMAIS être
    # accepté par l'auth PME (sinon un sub=acheteur_id pourrait charger un User homonyme).
    if payload.get("typ"):
        raise HTTPException(status_code=401, detail="Token invalide pour cet espace",
                            headers={"WWW-Authenticate": "Bearer"})
    user_id = payload.get("sub")
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Token invalide")
    user = db.query(User).filter(User.id == uid).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    # Compte désactivé : un token déjà émis ne doit plus donner accès (le login le bloque déjà,
    # mais les sessions en cours restaient valides).
    if not getattr(user, "is_active", True):
        raise HTTPException(status_code=403, detail="Compte désactivé",
                            headers={"WWW-Authenticate": "Bearer"})
    # Révocation de session : la version du token (tv, défaut 0) DOIT correspondre à celle de
    # l'utilisateur. Un token SANS tv vaut 0 → rejeté dès que token_version a été incrémenté
    # (retrait/transfert/changement de mot de passe) : plus de contournement par token « legacy ».
    # Tous les tokens émis portent tv (register/login/demo), donc aucune régression.
    if int(payload.get("tv") or 0) != int(getattr(user, "token_version", 0) or 0):
        raise HTTPException(status_code=401, detail="Session expirée, reconnectez-vous",
                            headers={"WWW-Authenticate": "Bearer"})
    return user
