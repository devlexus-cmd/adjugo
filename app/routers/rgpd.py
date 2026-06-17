"""
RGPD — droits de l'utilisateur sur ses données (art. 15/17/20 RGPD) :
  • GET  /api/rgpd/export          → portabilité : toutes ses données en JSON.
  • POST /api/rgpd/delete-account  → effacement : suppression du compte et des données.

L'effacement est déclenché par l'utilisateur LUI-MÊME, sur SES propres données, après
confirmation de son mot de passe. Action irréversible.
"""
import json
from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, verify_password
from app.core.ratelimit import limiter
from app.models import User

router = APIRouter(prefix="/api/rgpd", tags=["RGPD — mes données"])


def _ser(obj, cols) -> dict:
    out = {}
    for c in cols:
        v = getattr(obj, c, None)
        out[c] = v.isoformat() if isinstance(v, (datetime, date)) else v
    return out


@router.get("/export")
@limiter.limit("6/hour")
def export_my_data(request: Request, current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Portabilité (art. 20) : un export JSON téléchargeable de toutes les données du compte."""
    from app.models import (Company, MatchingCriteria, Project, Contact, Document,
                            Invoice, Signal, SavedSearch)
    uid = current_user.id
    data = {
        "export_genere_le": datetime.utcnow().isoformat() + "Z",
        "compte": _ser(current_user, ["id", "email", "full_name", "plan", "org_id",
                                      "org_role", "created_at"]),
    }

    def dump(model, cols, label):
        try:
            rows = db.query(model).filter(model.user_id == uid).all()
            data[label] = [_ser(r, cols) for r in rows]
        except Exception:
            data[label] = []

    comp = db.query(Company).filter(Company.user_id == uid).first()
    data["profil_entreprise"] = _ser(comp, ["name", "siret", "code_ape", "forme_juridique",
        "representant_legal", "address", "city", "postal_code", "tva_intracom", "email",
        "phone", "ca_n1", "ca_n2", "ca_n3", "effectif", "qualifications", "references"]) if comp else None
    crit = db.query(MatchingCriteria).filter(MatchingCriteria.user_id == uid).first()
    data["criteres"] = _ser(crit, ["specialites", "departements", "budget_min", "budget_max"]) if crit else None
    dump(Project, ["id", "name", "client", "budget", "status", "deadline", "match_score",
                   "go_decision", "created_at"], "appels_offres")
    dump(Contact, ["id", "name", "email", "phone", "organisation", "created_at"], "contacts")
    dump(Document, ["id", "name", "category", "file_size", "expiration_date", "created_at"], "documents_coffre_fort")
    dump(Invoice, ["id", "type", "client_name", "total_ttc", "created_at"], "factures")
    dump(Signal, ["id", "intitule", "collectivite", "pertinence", "created_at"], "signaux_veille")
    dump(SavedSearch, ["id", "name", "query", "frequency", "created_at"], "alertes")

    payload = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    return Response(content=payload, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="mes_donnees_adjugo.json"'})


class DeleteIn(BaseModel):
    password: str
    confirm: str = ""   # doit valoir "SUPPRIMER"


@router.post("/delete-account")
@limiter.limit("3/hour")
def delete_account(request: Request, data: DeleteIn,
                   current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Effacement (art. 17) : supprime le compte et ses données. Irréversible.
    Confirmé par le mot de passe + le mot « SUPPRIMER ». Suppression ORDONNÉE (enfants
    avant parents) pour respecter les clés étrangères en une seule transaction."""
    if not verify_password(data.password, current_user.hashed_password):
        raise HTTPException(400, "Mot de passe incorrect")
    if (data.confirm or "").strip().upper() != "SUPPRIMER":
        raise HTTPException(400, "Tapez SUPPRIMER pour confirmer")
    from app.models import Organization
    org = db.query(Organization).filter(Organization.owner_id == current_user.id).first()
    if org:
        others = db.query(User).filter(User.org_id == org.id, User.id != current_user.id).count()
        if others:
            raise HTTPException(409, "Transférez d'abord la propriété de l'organisation à un "
                                     "autre membre (ou retirez les membres) avant de supprimer votre compte.")

    uid = current_user.id
    import app.models as M

    def delete_by(model_name, field, value):
        model = getattr(M, model_name, None)
        if model is None or not hasattr(model, field):
            return
        db.query(model).filter(getattr(model, field) == value).delete(synchronize_session=False)

    try:
        pids = [p.id for p in db.query(M.Project).filter(M.Project.user_id == uid).all()]
        # 1) enfants liés aux contributions / invitations (owner_id = mandataire)
        delete_by("ContributionPiece", "owner_id", uid)
        delete_by("ProjectContribution", "owner_id", uid)
        delete_by("ProjectInvite", "owner_id", uid)
        # 2) docs générés liés aux projets de l'utilisateur
        if pids:
            db.query(M.GeneratedDoc).filter(M.GeneratedDoc.project_id.in_(pids)).delete(synchronize_session=False)
        # 3) journal d'audit du tenant
        delete_by("AuditLog", "owner_id", uid)
        # 4) projets puis le reste des données scopées utilisateur
        for name in ("Project", "Contact", "Document", "Cotraitant", "Invoice",
                     "KnowledgeChunk", "KnowledgeDoc", "Signal", "SavedSearch",
                     "Company", "MatchingCriteria", "MatchingCriteriaExt"):
            delete_by(name, "user_id", uid)
        # 5) organisation perso puis l'utilisateur
        if org:
            db.query(Organization).filter(Organization.id == org.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == uid).delete(synchronize_session=False)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Suppression impossible (contactez le support) : {e}")
    return {"ok": True, "message": "Compte et données supprimés."}
