"""
Espace équipe / organisation : voir les membres, inviter un collègue (qui partagera
projets, contacts et co-traitants), renommer l'organisation, retirer un membre.
"""
import secrets
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.core.database import get_db
from app.core.security import get_current_user, hash_password
from app.core.org import ensure_org
from app.models import User, Organization

router = APIRouter(prefix="/api/org", tags=["Équipe / Organisation"])


class InviteIn(BaseModel):
    email: EmailStr
    full_name: Optional[str] = ""


class RenameIn(BaseModel):
    name: Optional[str] = None
    country: Optional[str] = None


def _org(user, db) -> Organization:
    oid = ensure_org(user, db)
    return db.query(Organization).filter(Organization.id == oid).first()


@router.get("/countries")
def adapted_countries(current_user: User = Depends(get_current_user)):
    """Pays pour lesquels Adjugo est pleinement adapté (donnée entreprise complète)."""
    from app.core.countries import COUNTRIES_FULL
    return [{"code": c["code"], "nom": c["nom"], "lang": c["lang"], "devise": c["devise"]}
            for c in COUNTRIES_FULL]


@router.get("/")
def get_org(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.core.countries import country_config
    org = _org(current_user, db)
    members = db.query(User).filter(User.org_id == org.id).order_by(User.created_at).all()
    cfg = country_config(org.country)
    return {
        "id": org.id, "name": org.name, "owner_id": org.owner_id,
        "is_owner": org.owner_id == current_user.id,
        "country": cfg["code"], "country_nom": cfg["nom"],
        "lang": cfg["lang"], "devise": cfg["devise"],
        "members": [{
            "id": m.id, "full_name": m.full_name, "email": m.email,
            "role": m.org_role or "membre", "is_owner": m.id == org.owner_id,
            "is_me": m.id == current_user.id,
        } for m in members],
    }


@router.put("/")
def update_org(data: RenameIn, current_user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    from app.core.countries import is_supported, country_config
    org = _org(current_user, db)
    if org.owner_id != current_user.id:
        raise HTTPException(403, "Seul le propriétaire peut modifier l'organisation")
    if data.name:
        org.name = data.name.strip() or org.name
    if data.country:
        cc = data.country.strip().upper()
        if not is_supported(cc):
            raise HTTPException(400, "Pays non pris en charge pour l'adaptation complète")
        org.country = cc
    db.commit()
    cfg = country_config(org.country)
    return {"id": org.id, "name": org.name, "country": cfg["code"],
            "lang": cfg["lang"], "devise": cfg["devise"]}


@router.post("/invite", status_code=201)
def invite_member(data: InviteIn, current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Invite un collègue dans l'organisation. Crée son compte avec un mot de passe
    provisoire (retourné une seule fois) à lui transmettre, et envoie un email si SMTP."""
    org = _org(current_user, db)
    if org.owner_id != current_user.id and (current_user.org_role or "") != "admin":
        raise HTTPException(403, "Seul un administrateur peut inviter des membres")

    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        if existing.org_id == org.id:
            raise HTTPException(400, "Cette personne fait déjà partie de l'organisation")
        raise HTTPException(400, "Cet email est déjà associé à un autre compte")

    temp_password = secrets.token_urlsafe(9)
    member = User(
        email=str(data.email),
        hashed_password=hash_password(temp_password),
        full_name=data.full_name or str(data.email).split("@")[0],
        org_id=org.id, org_role="membre",
    )
    db.add(member)
    db.commit()
    db.refresh(member)

    # Email best-effort (no-op si SMTP non configuré)
    try:
        from app.services.email import send_email
        send_email(member.email, f"Invitation à rejoindre {org.name} sur Adjugo",
                   f"Bonjour,\n\n{current_user.full_name} vous invite à rejoindre l'espace "
                   f"« {org.name} » sur Adjugo.\n\nIdentifiant : {member.email}\n"
                   f"Mot de passe provisoire : {temp_password}\n\nConnectez-vous puis "
                   f"changez votre mot de passe.\n\n— Adjugo")
    except Exception as e:
        import logging
        logging.getLogger("adjugo").warning("Email d'invitation non envoyé à %s : %s", member.email, e)

    return {"id": member.id, "email": member.email, "full_name": member.full_name,
            "temp_password": temp_password}


@router.delete("/members/{member_id}")
def remove_member(member_id: int, current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Retire un membre de l'organisation (lui recrée un espace personnel)."""
    org = _org(current_user, db)
    if org.owner_id != current_user.id:
        raise HTTPException(403, "Seul le propriétaire peut retirer un membre")
    if member_id == current_user.id:
        raise HTTPException(400, "Vous ne pouvez pas vous retirer vous-même")
    member = db.query(User).filter(User.id == member_id, User.org_id == org.id).first()
    if not member:
        raise HTTPException(404, "Membre introuvable")
    # Nouvel espace personnel pour l'ancien membre (ses futures données lui restent)
    new_org = Organization(name=f"Équipe {member.full_name}", owner_id=member.id)
    db.add(new_org)
    db.flush()
    member.org_id = new_org.id
    member.org_role = "admin"
    db.commit()
    return {"ok": True}
