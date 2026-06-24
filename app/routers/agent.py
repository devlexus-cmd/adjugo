"""
Statistiques d'activité (tableau de bord). L'ancien agent auto-exécuté a été
remplacé par le flux « Sourcing IA » à la demande (routers/sourcing.py).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.quota import usage
from app.core.org import member_ids
from app.models import User, Project

router = APIRouter(prefix="/api/agent", tags=["Tableau de bord"])


def _status(p) -> str:
    return p.status.value if hasattr(p.status, "value") else (p.status or "nouveau")


def _details(p) -> dict:
    return (p.ai_analysis or {}).get("details", {}) if isinstance(p.ai_analysis, dict) else {}


def _zone(p) -> str:
    """Département déduit du CODE POSTAL (5 chiffres) du lieu d'exécution, sinon 'Inconnu'.
    On exige un vrai code postal pour ne pas confondre une année (« 2024 ») ou un n° de rue
    avec un département. DOM-TOM (97x/98x) conservés sur 3 chiffres."""
    import re
    lieu = str(_details(p).get("lieu_execution") or "")
    m = re.search(r"\b(\d{5})\b", lieu)
    if not m:
        return "Inconnu"
    cp = m.group(1)
    if cp[:2] == "20":                 # Corse : 2A (20000-20199) / 2B (20200-20999), pas « 20 »
        return "2A" if cp < "20200" else "2B"
    return cp[:3] if cp[:2] in ("97", "98") else cp[:2]


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
    # Périmètre ORGANISATION (comme la liste « Mes marchés ») : le tableau de bord compte
    # les marchés de toute l'équipe, pas seulement ceux du compte courant.
    projects = db.query(Project).filter(Project.user_id.in_(member_ids(current_user, db)),
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

    # Pilotage enrichi (donnée propriétaire que personne d'autre n'a) :
    # win rate GROUPEMENT vs SOLO, et par partenaire. Défensif : jamais de 500.
    by_groupement, by_partner = [], []
    try:
        from app.routers.cotraitants import ProjectCotraitant, Cotraitant
        from app.models import ProjectInvite
        pids2 = [p.id for p in projects]
        grp_ids, partners_by_proj = set(), {}
        if pids2:
            links = db.query(ProjectCotraitant).filter(ProjectCotraitant.project_id.in_(pids2)).all()
            ct_ids = {lk.cotraitant_id for lk in links}
            names = {c.id: c.name for c in db.query(Cotraitant).filter(Cotraitant.id.in_(ct_ids)).all()} if ct_ids else {}
            for lk in links:
                grp_ids.add(lk.project_id)
                partners_by_proj.setdefault(lk.project_id, set()).add(names.get(lk.cotraitant_id) or "Partenaire")
            for inv in db.query(ProjectInvite).filter(ProjectInvite.project_id.in_(pids2),
                                                      ProjectInvite.revoked.is_(False)).all():
                grp_ids.add(inv.project_id)
                if getattr(inv, "company_name", None):
                    partners_by_proj.setdefault(inv.project_id, set()).add(inv.company_name)
        by_groupement = _segment(projects, lambda p: "Groupement" if p.id in grp_ids else "Solo")
        pagg = {}
        for p in projects:
            st = _status(p)
            if st not in ("gagne", "perdu"):
                continue
            for nm in partners_by_proj.get(p.id, ()):
                a = pagg.setdefault(nm, {"key": nm, "won": 0, "lost": 0})
                a["won" if st == "gagne" else "lost"] += 1
        for a in pagg.values():
            tot = a["won"] + a["lost"]; a["total"] = tot
            a["win_rate"] = round(a["won"] / tot * 100) if tot else 0
            by_partner.append(a)
        by_partner.sort(key=lambda a: (-a["total"], -a["win_rate"]))
    except Exception:
        db.rollback()

    segments = {
        "by_zone": _segment(projects, _zone),
        "by_type": _segment(projects, lambda p: _details(p).get("type_marche")),
        "by_groupement": by_groupement,
        "by_partner": by_partner[:6],
        "loss_reasons": loss_reasons,
    }

    # Métrique de MOAT : part des groupements formés avec un partenaire NOUVEAU
    # (suggéré par Adjugo via SIRENE) vs un partenaire du carnet d'adresses du Client.
    # Si elle reste basse, le produit n'est qu'un générateur de documents (copiable) ;
    # si elle monte, le réseau se forme et devient défendable.
    from app.routers.cotraitants import ProjectCotraitant
    moat = {"groupements": 0, "avec_partenaire_suggere": 0, "rate": 0,
            "liens_suggeres": 0, "liens_reseau": 0}
    pids = [p.id for p in projects]
    try:
        if pids:
            links = db.query(ProjectCotraitant).filter(ProjectCotraitant.project_id.in_(pids)).all()
            by_proj = {}
            for lk in links:
                src = getattr(lk, "source", None) or "reseau"
                moat["liens_suggeres" if src == "discover" else "liens_reseau"] += 1
                by_proj.setdefault(lk.project_id, set()).add(src)
            moat["groupements"] = len(by_proj)
            moat["avec_partenaire_suggere"] = sum(1 for s in by_proj.values() if "discover" in s)
            moat["rate"] = round(moat["avec_partenaire_suggere"] / moat["groupements"] * 100) if moat["groupements"] else 0
    except Exception:
        db.rollback()   # filet : colonne absente / souci DB → moat à zéro, stats jamais cassées

    u = usage(current_user, db)
    db.commit()
    return {
        "total_projects": total, "by_status": by_status, "win_rate": win_rate,
        "total_won_budget": total_budget, "decided": won + by_status.get("perdu", 0),
        "segments": segments, "moat": moat,
        "analyses_this_month": u["analyses_used"], "usage": u,
    }
