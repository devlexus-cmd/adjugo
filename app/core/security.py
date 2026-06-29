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


# PBKDF2-HMAC-SHA256. 600k itérations = recommandation OWASP 2024 (l'ancien 100k était 6×
# trop faible). Rétro-compatible : les hash existants `salt$hash` sont relus à 100k et
# re-hachés au login (cf. needs_rehash). Le nombre d'itérations est encodé dans le hash.
_PBKDF2_ITERS = 600_000
_LEGACY_ITERS = 100_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ITERS).hex()
    return f"pbkdf2_sha256${_PBKDF2_ITERS}${salt}${hashed}"


def _parse_hash(hashed: str):
    """(iters, salt, hash). Tolère l'ancien format `salt$hash` (100k itérations)."""
    parts = hashed.split("$")
    if len(parts) == 4 and parts[0] == "pbkdf2_sha256":
        return int(parts[1]), parts[2], parts[3]
    if len(parts) == 2:                       # legacy
        return _LEGACY_ITERS, parts[0], parts[1]
    raise ValueError("format de hash inconnu")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        iters, salt, stored_hash = _parse_hash(hashed)
        check = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), iters).hex()
        return hmac.compare_digest(check, stored_hash)   # comparaison à temps constant
    except Exception:
        return False


def needs_rehash(hashed: str) -> bool:
    """Vrai si le hash est plus faible que la cible actuelle → à re-hacher au prochain login."""
    try:
        iters, _, _ = _parse_hash(hashed)
        return iters < _PBKDF2_ITERS
    except Exception:
        return True


# Hash factice (au format courant) pour exécuter un PBKDF2 équivalent quand l'email est
# inconnu : empêche de distinguer « email inexistant » par le temps de réponse.
DUMMY_HASH = f"pbkdf2_sha256${_PBKDF2_ITERS}${'0' * 32}${'0' * 64}"


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
        # 401 (et non 404) : du point de vue du porteur de token, « compte introuvable » et
        # « session invalide » sont indistinguables — on n'expose pas la différence.
        raise HTTPException(status_code=401, detail="Session invalide, reconnectez-vous",
                            headers={"WWW-Authenticate": "Bearer"})
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
        raise HTTPException(status_code=401, detail="Session invalide, reconnectez-vous",
                            headers={"WWW-Authenticate": "Bearer"})
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
