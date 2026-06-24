"""
Adjugo — Routes d'authentification
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from sqlalchemy import func

from datetime import timedelta

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, get_current_user, decode_token
from app.core.config import get_settings
from app.core.ratelimit import limiter
from app.models import User, Company, MatchingCriteria
from app.schemas import UserCreate, UserLogin, Token, UserOut
from app.services.email import send_email
from app.services.email_templates import verify_email_html

router = APIRouter(prefix="/api/auth", tags=["Authentification"])


def _send_verification(user: User) -> None:
    """Génère un lien signé (3 jours) et envoie l'email de confirmation. Silencieux si l'email
    est désactivé/échoue → ne bloque JAMAIS l'inscription."""
    try:
        token = create_access_token(data={"sub": str(user.id), "purpose": "verify_email"},
                                    expires_delta=timedelta(days=3))
        base = (get_settings().APP_BASE_URL or "https://adjugo.pro").rstrip("/")
        link = f"{base}/app?verify={token}"
        send_email(user.email, "Confirmez votre adresse email — Adjugo",
                   "Bienvenue sur Adjugo !\n\nConfirmez votre adresse email (lien valable 3 jours) :\n"
                   f"{link}\n\nSi vous n'êtes pas à l'origine de cette inscription, ignorez ce message.\n\n— Adjugo",
                   html=verify_email_html(link, user.full_name or ""))
    except Exception:
        pass


@router.post("/register", response_model=Token, status_code=201)
@limiter.limit("5/minute")
def register(request: Request, data: UserCreate, db: Session = Depends(get_db)):
    """Créer un nouveau compte utilisateur."""
    # data.email est déjà normalisé (minuscules) par le schéma. Le doublon se teste en
    # INSENSIBLE à la casse pour couvrir d'éventuelles anciennes lignes en casse mixte.
    if db.query(User).filter(func.lower(User.email) == data.email).first():
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")

    fn = (data.full_name or "").strip()
    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=fn,
        org_role="admin",
    )
    db.add(user)
    db.flush()

    # Créer l'organisation (espace de travail) dont l'utilisateur est propriétaire. Repli si le
    # nom complet est vide (sinon on créait une organisation nommée « Équipe » + espace).
    from app.models import Organization
    org_name = data.company_name or (f"Équipe {fn}" if fn else "Mon organisation")
    org = Organization(name=org_name, owner_id=user.id)
    db.add(org)
    db.flush()
    user.org_id = org.id

    # Créer le profil entreprise si un nom est fourni
    if data.company_name:
        company = Company(user_id=user.id, name=data.company_name)
        db.add(company)

    # Créer les critères par défaut
    criteria = MatchingCriteria(user_id=user.id)
    db.add(criteria)

    db.commit()
    db.refresh(user)

    # Email de confirmation (n'empêche pas l'accès : on n'enferme personne si l'email tarde ;
    # le front affiche une bannière « vérifiez votre adresse » jusqu'à confirmation).
    _send_verification(user)

    token = create_access_token(data={"sub": str(user.id), "tv": int(user.token_version or 0)})
    return {"access_token": token, "token_type": "bearer"}


class VerifyIn(BaseModel):
    token: str


@router.post("/verify-email")
@limiter.limit("30/hour")
def verify_email(request: Request, data: VerifyIn, db: Session = Depends(get_db)):
    """Confirme l'adresse à partir du lien signé reçu par email."""
    try:
        payload = decode_token(data.token)
    except Exception:
        raise HTTPException(400, "Lien de vérification invalide ou expiré.")
    if payload.get("purpose") != "verify_email":
        raise HTTPException(400, "Lien de vérification invalide.")
    try:
        uid = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(400, "Lien de vérification invalide.")
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(404, "Compte introuvable.")
    if not user.email_verified:
        user.email_verified = True
        db.commit()
    return {"ok": True, "message": "Adresse email confirmée. Merci !"}


@router.post("/resend-verification")
@limiter.limit("3/hour")
def resend_verification(request: Request, current_user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """Renvoie l'email de confirmation au compte connecté."""
    if current_user.email_verified:
        return {"ok": True, "message": "Votre adresse est déjà confirmée."}
    _send_verification(current_user)
    return {"ok": True, "message": "Email de confirmation renvoyé."}


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
def login(request: Request, data: UserLogin, db: Session = Depends(get_db)):
    """Connexion — retourne un JWT."""
    # Recherche insensible à la casse : couvre les comptes créés avant la normalisation.
    user = db.query(User).filter(func.lower(User.email) == data.email).first()
    # Anti-énumération par timing : on exécute TOUJOURS un PBKDF2 (sur un faux hash si l'email
    # est inconnu) → la réponse « identifiants incorrects » prend le même temps, qu'un compte
    # existe ou non. Sinon le court-circuit révélait par chronométrie quels emails ont un compte.
    _DUMMY = "0" * 32 + "$" + "0" * 64
    pwd_ok = verify_password(data.password, user.hashed_password if user else _DUMMY)
    if not user or not pwd_ok:
        raise HTTPException(status_code=401, detail="Identifiants incorrects")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")

    token = create_access_token(data={"sub": str(user.id), "tv": int(user.token_version or 0)})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/demo", response_model=Token)
@limiter.limit("30/hour")
def demo_login(request: Request, db: Session = Depends(get_db)):
    """Connexion au compte de DÉMONSTRATION (sans mot de passe) — données pré-remplies.
    Le compte démo est un BAC À SABLE public (réinitialisé à chaque démarrage, aucune donnée
    client réelle) : son accès sans mot de passe est VOLONTAIRE (vitrine de la landing page).
    Le risque « passwordless » signalé par l'audit est neutralisé par cette nature sandbox, et
    le contournement du cron admin via DEMO_MODE a été fermé séparément (CRON_SECRET requis)."""
    from app.services.demo_seed import ensure_demo
    user = ensure_demo(db)   # crée le compte démo s'il n'existe pas encore
    token = create_access_token(data={"sub": str(user.id), "tv": int(user.token_version or 0)})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    """Récupérer le profil de l'utilisateur connecté."""
    return current_user


@router.put("/me", response_model=UserOut)
def update_me(
    full_name: str = None,
    email: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mettre à jour le profil."""
    if full_name:
        current_user.full_name = full_name
    if email:
        existing = db.query(User).filter(User.email == email, User.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email déjà utilisé")
        current_user.email = email
    db.commit()
    db.refresh(current_user)
    return current_user


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password", response_model=Token)
@limiter.limit("10/hour")
def change_password(request: Request, data: PasswordChange,
                    current_user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Change le mot de passe (notamment pour un membre invité qui doit remplacer son
    mot de passe provisoire). Invalide les autres sessions (token_version) et renvoie un
    token frais pour la session courante."""
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Mot de passe actuel incorrect")
    if len(data.new_password or "") < 8:
        raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit faire au moins 8 caractères")
    current_user.hashed_password = hash_password(data.new_password)
    current_user.token_version = (current_user.token_version or 0) + 1  # coupe les autres sessions
    db.commit()
    db.refresh(current_user)
    token = create_access_token(data={"sub": str(current_user.id), "tv": int(current_user.token_version or 0)})
    return {"access_token": token, "token_type": "bearer"}


# ── Mot de passe oublié (réinitialisation par email) ─────────────────────────
import hashlib as _hashlib
import secrets as _secrets
from datetime import datetime as _dt, timedelta as _td, timezone as _tz


def _hash_reset(t: str) -> str:
    return _hashlib.sha256(("adjugo-reset:" + (t or "")).encode("utf-8")).hexdigest()


class ForgotIn(BaseModel):
    email: str


class ResetIn(BaseModel):
    token: str
    new_password: str


@router.post("/forgot-password")
@limiter.limit("5/hour")
def forgot_password(request: Request, data: ForgotIn, db: Session = Depends(get_db)):
    """Envoie un lien de réinitialisation à l'adresse, SI elle correspond à un compte.
    Réponse identique dans tous les cas (on ne révèle pas l'existence d'un compte)."""
    # Insensible à la casse : un compte créé en casse mixte (« Jean.Dupont@… ») recevait
    # SILENCIEUSEMENT aucun email (le .lower() ne matchait pas la ligne stockée).
    user = db.query(User).filter(func.lower(User.email) == (data.email or "").strip().lower()).first()
    if user:
        raw = _secrets.token_urlsafe(32)
        user.reset_token_hash = _hash_reset(raw)
        user.reset_expires_at = _dt.now(_tz.utc) + _td(hours=1)
        db.commit()
        try:
            from app.services.email import send_email
            from app.core.config import get_settings
            base = (get_settings().APP_BASE_URL or "https://adjugo.pro").rstrip("/")
            link = f"{base}/app?reset={raw}"
            send_email(user.email, "Réinitialisation de votre mot de passe Adjugo",
                       f"Bonjour,\n\nVous avez demandé à réinitialiser votre mot de passe Adjugo.\n"
                       f"Cliquez sur ce lien (valable 1 heure) :\n{link}\n\n"
                       f"Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.\n\n— Adjugo")
        except Exception:
            pass
    return {"ok": True, "message": "Si un compte existe pour cette adresse, un email vient d'être envoyé."}


@router.post("/reset-password", response_model=Token)
@limiter.limit("10/hour")
def reset_password(request: Request, data: ResetIn, db: Session = Depends(get_db)):
    """Pose un nouveau mot de passe à partir d'un token reçu par email. Invalide les
    autres sessions et connecte directement (token frais)."""
    if len(data.new_password or "") < 8:
        raise HTTPException(400, "Le mot de passe doit faire au moins 8 caractères")
    h = _hash_reset((data.token or "").strip())
    user = db.query(User).filter(User.reset_token_hash == h, User.reset_token_hash != "").first()
    exp = getattr(user, "reset_expires_at", None) if user else None
    if exp is not None and exp.tzinfo is None:
        exp = exp.replace(tzinfo=_tz.utc)
    if not user or not exp or exp <= _dt.now(_tz.utc):
        raise HTTPException(400, "Lien de réinitialisation invalide ou expiré. Recommencez.")
    user.hashed_password = hash_password(data.new_password)
    user.reset_token_hash = ""
    user.reset_expires_at = None
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    db.refresh(user)
    token = create_access_token(data={"sub": str(user.id), "tv": int(user.token_version or 0)})
    return {"access_token": token, "token_type": "bearer"}
