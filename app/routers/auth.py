"""
Adjugo — Routes d'authentification
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, get_current_user
from app.core.ratelimit import limiter
from app.models import User, Company, MatchingCriteria
from app.schemas import UserCreate, UserLogin, Token, UserOut

router = APIRouter(prefix="/api/auth", tags=["Authentification"])


@router.post("/register", response_model=Token, status_code=201)
@limiter.limit("5/minute")
def register(request: Request, data: UserCreate, db: Session = Depends(get_db)):
    """Créer un nouveau compte utilisateur."""
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")

    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        org_role="admin",
    )
    db.add(user)
    db.flush()

    # Créer l'organisation (espace de travail) dont l'utilisateur est propriétaire
    from app.models import Organization
    org = Organization(name=data.company_name or f"Équipe {data.full_name}", owner_id=user.id)
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

    token = create_access_token(data={"sub": str(user.id), "tv": int(user.token_version or 0)})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
def login(request: Request, data: UserLogin, db: Session = Depends(get_db)):
    """Connexion — retourne un JWT."""
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Identifiants incorrects")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")

    token = create_access_token(data={"sub": str(user.id), "tv": int(user.token_version or 0)})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/demo", response_model=Token)
@limiter.limit("30/hour")
def demo_login(request: Request, db: Session = Depends(get_db)):
    """Connexion au compte de DÉMONSTRATION (sans mot de passe) — données pré-remplies."""
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
