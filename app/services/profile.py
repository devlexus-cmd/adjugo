"""
Helpers de profil : sérialisation du profil entreprise et des critères Go/No-Go
pour alimenter le moteur de sourcing et le scoring.
"""
from typing import Optional
from sqlalchemy.orm import Session

from app.models import Company


def company_dict(company: Optional[Company]) -> dict:
    if not company:
        return {}
    keys = ["name", "siret", "code_ape", "forme_juridique", "representant_legal",
            "address", "city", "postal_code", "tva_intracom", "email", "phone",
            "ca_n1", "ca_n2", "ca_n3", "effectif", "qualifications", "references"]
    return {k: getattr(company, k, None) for k in keys}


def criteria_dict(user_id: int, db: Session) -> dict:
    """Critères étendus (criteria_v2) si présents. PARTAGÉS dans l'organisation : on lit
    les critères du PROPRIÉTAIRE de l'org (un membre n'a pas les siens)."""
    try:
        from app.models import User
        from app.core.org import data_owner_id
        u = db.query(User).filter(User.id == user_id).first()
        oid = data_owner_id(u, db) if u else user_id
        from app.routers.criteria_v2 import MatchingCriteriaExt
        c = db.query(MatchingCriteriaExt).filter(MatchingCriteriaExt.user_id == oid).first()
        if c:
            return {col.name: getattr(c, col.name) for col in c.__table__.columns}
    except Exception as e:
        import logging
        logging.getLogger("adjugo").warning("criteria_dict a échoué pour user %s : %s", user_id, e)
    return {}
