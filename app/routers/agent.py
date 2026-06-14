"""
Statistiques d'activité (tableau de bord). L'ancien agent auto-exécuté a été
remplacé par le flux « Sourcing IA » à la demande (routers/sourcing.py).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.quota import usage
from app.models import User, Project

router = APIRouter(prefix="/api/agent", tags=["Tableau de bord"])


def _status(p) -> str:
    return p.status.value if hasattr(p.status, "value") else (p.status or "nouveau")


def _details(p) -> dict:
    return (p.ai_analysis or {}).get("details", {}) if isinstance(p.ai_analysis, dict) else {}


def _zone(p) -> str:
    """Département (2 chiffres) déduit du lieu d'exécution, sinon 'Inconnu'."""
    import re
    lieu = str(_details(p).get("lieu_execution") or "")
    m = re.search(r"\b(\d{2})\d{0,3}\b", lieu)
    return m.group(1) if m else "Inconnu"


def _segment(projects, keyfn):
    """Agrège won/lost/total + win_rate par clé (sur les AO tranchés gagne/perdu)."""
    agg = {}
    for p in projects:
        st = _status(p)
        if st not in ("gagne", "perdu"):
            continue
        k = keyfn(p) or "Inconnu"
        a = agg.setdefault(k, {"key": k, "won": 0, "lost": 0})
        a["won" if st == "gagne" else "lost"] += 1
    out = []
    for a in agg.values():
        tot = a["won"] + a["lost"]
        a["total"] = tot
        a["win_rate"] = round(a["won"] / tot * 100) if tot else 0
        out.append(a)
    out.sort(key=lambda a: (-a["total"], -a["win_rate"]))
    return out


@router.get("/stats")
def agent_stats(current_user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    projects = db.query(Project).filter(Project.user_id == current_user.id,
                                        Project.deleted_at.is_(None)).all()
    total = len(projects)
    by_status = {}
    for p in projects:
        key = _status(p)
        by_status[key] = by_status.get(key, 0) + 1
    won = by_status.get("gagne", 0)
    sent = by_status.get("envoye", 0) + won + by_status.get("perdu", 0)
    win_rate = round(won / sent * 100) if sent > 0 else 0
    total_budget = sum(p.budget or 0 for p in projects if _status(p) == "gagne")

    # Motifs de perte (boucle de feedback : « où vous perdez »)
    loss_reasons = {}
    for p in projects:
        if _status(p) == "perdu" and p.outcome_reason:
            loss_reasons[p.outcome_reason] = loss_reasons.get(p.outcome_reason, 0) + 1
    loss_reasons = sorted(
        [{"reason": r, "count": n} for r, n in loss_reasons.items()],
        key=lambda x: -x["count"])

    segments = {
        "by_zone": _segment(projects, _zone),
        "by_type": _segment(projects, lambda p: _details(p).get("type_marche")),
        "loss_reasons": loss_reasons,
    }

    u = usage(current_user)
    db.commit()
    return {
        "total_projects": total, "by_status": by_status, "win_rate": win_rate,
        "total_won_budget": total_budget, "decided": won + by_status.get("perdu", 0),
        "segments": segments,
        "analyses_this_month": u["analyses_used"], "usage": u,
    }
