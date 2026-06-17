"""
Feedback in-app (bouton « Signaler / Idée »). Stocke le retour ET notifie le fondateur
par email (best-effort). Essentiel en phase de test avec de vraies PME.
"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ratelimit import limiter
from app.models import User, Feedback

router = APIRouter(prefix="/api/feedback", tags=["Feedback"])

_FOUNDER = "viegaseliot1@gmail.com"


class FeedbackIn(BaseModel):
    message: str = Field(..., min_length=2, max_length=4000)
    kind: str = "idee"           # bug | idee | autre
    page: str = ""


@router.post("")
@limiter.limit("20/hour")
def send_feedback(request: Request, data: FeedbackIn,
                  current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kind = data.kind if data.kind in ("bug", "idee", "autre") else "autre"
    fb = Feedback(user_id=current_user.id, email=(current_user.email or "")[:255],
                  kind=kind, message=data.message[:4000], page=(data.page or "")[:120])
    db.add(fb)
    db.commit()
    try:
        from app.services.email import send_email
        send_email(_FOUNDER, f"[Adjugo {kind}] retour de {current_user.email}",
                   f"De : {current_user.full_name or ''} <{current_user.email}>\n"
                   f"Type : {kind}\nPage : {data.page}\n\n{data.message}")
    except Exception:
        pass
    return {"ok": True, "message": "Merci, votre retour a bien été transmis !"}
