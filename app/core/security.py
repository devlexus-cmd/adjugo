import hashlib
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
        return check == stored_hash
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalide ou expire", headers={"WWW-Authenticate": "Bearer"})


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    from app.models import User
    payload = decode_token(token)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token invalide")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    # Révocation de session : si le token porte une version (tv), elle doit correspondre
    # à celle de l'utilisateur. Un retrait/transfert incrémente token_version → l'ancien
    # token est rejeté. Les tokens hérités (sans tv) restent acceptés (rétro-compat).
    tv = payload.get("tv")
    if tv is not None and int(tv) != int(getattr(user, "token_version", 0) or 0):
        raise HTTPException(status_code=401, detail="Session expirée, reconnectez-vous",
                            headers={"WWW-Authenticate": "Bearer"})
    return user
