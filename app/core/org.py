"""
Espace de travail partagé (organisation / équipe).

Plutôt que de dupliquer un org_id sur chaque entité, on scope les requêtes par
« utilisateurs de la même organisation » : un membre voit les projets / contacts /
co-traitants de tous les membres. Rétro-compatible : un utilisateur seul a sa propre
organisation → la portée se réduit à lui-même (comportement mono-utilisateur d'origine).
"""
from sqlalchemy.orm import Session


def ensure_org(user, db: Session) -> int:
    """Garantit que l'utilisateur appartient à une organisation (backfill paresseux)."""
    if getattr(user, "org_id", None):
        return user.org_id
    from app.models import Organization, Company
    name = None
    comp = db.query(Company).filter(Company.user_id == user.id).first()
    if comp and comp.name:
        name = comp.name
    elif user.full_name:
        name = f"Équipe {user.full_name}"
    org = Organization(name=name or "Mon organisation", owner_id=user.id)
    db.add(org)
    db.flush()
    user.org_id = org.id
    if not getattr(user, "org_role", None):
        user.org_role = "admin"
    db.commit()
    return org.id


def member_ids(user, db: Session) -> list[int]:
    """Identifiants des utilisateurs partageant l'organisation de `user`."""
    oid = getattr(user, "org_id", None) or ensure_org(user, db)
    from app.models import User as U
    rows = db.query(U.id).filter(U.org_id == oid).all()
    return [r[0] for r in rows] or [user.id]


def data_owner_id(user, db: Session) -> int:
    """ID de l'utilisateur qui PORTE les données partagées de l'organisation (profil
    entreprise, critères Go/No-Go) = le propriétaire de l'org. Tous les membres lisent et
    éditent le MÊME profil/critères (l'org = l'entreprise). Repli sur l'utilisateur."""
    try:
        from app.models import Organization
        oid = getattr(user, "org_id", None)
        if oid:
            org = db.query(Organization).filter(Organization.id == oid).first()
            if org and org.owner_id:
                return org.owner_id
    except Exception:
        pass
    return user.id
