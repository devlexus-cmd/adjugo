"""
Router VEILLE AMONT — signaux d'investissement détectés en amont des appels d'offres.

Importez une délibération / compte-rendu de collectivité → l'IA détecte les projets
futurs (type, budget, localisation, collectivité) → feed de signaux, scorés selon le
profil de l'entreprise. La valeur : être informé des MOIS avant l'appel d'offres.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ratelimit import limiter
from app.core.quota import consume_analysis
from app.models import User, Signal, Organization
from app.services.analysis import extract_dce_text
from app.services.agents.amont import detect_projets, detect_from_deliberations, score_pertinence
from app.sourcing.sources.deliberations import DeliberationSource
from app.services.profile import criteria_dict as _criteria_dict
from app.core.countries import lang_name as _lang_name, country_config

logger = logging.getLogger("adjugo")
router = APIRouter(prefix="/api/amont", tags=["Veille amont (signaux d'investissement)"])


def _country(user, db) -> str:
    if getattr(user, "org_id", None):
        org = db.query(Organization).filter(Organization.id == user.org_id).first()
        if org and org.country:
            return org.country
    return "FR"


def _lang(user, db) -> str:
    return _lang_name(_country(user, db))


def _out(s: Signal) -> dict:
    return {
        "id": s.id, "intitule": s.intitule, "type_projet": s.type_projet,
        "budget": s.budget, "budget_texte": s.budget_texte, "localisation": s.localisation,
        "collectivite": s.collectivite, "calendrier": s.calendrier, "metiers": s.metiers or [],
        "extrait": s.extrait, "pertinence": s.pertinence, "pertinence_score": s.pertinence_score,
        "source_name": s.source_name, "source_url": s.source_url, "source_date": s.source_date,
        "domaine": s.domaine, "phase": s.phase, "echeance_ao": s.echeance_ao,
        "financement": s.financement, "maturite": s.maturite,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _persist(projets, default_coll, source_label, current_user, db, domaines=None) -> list:
    """Score, déduplique (vs signaux existants) et enregistre les projets détectés."""
    criteria = _criteria_dict(current_user.id, db)
    existing = {((s.intitule or "").lower()[:80], (s.collectivite or "").lower())
                for s in db.query(Signal).filter(Signal.user_id == current_user.id,
                                                  Signal.archived == False).all()}  # noqa: E712
    created = []
    for p in (projets or []):
        intitule = (p.get("intitule") or "").strip()
        coll = (p.get("collectivite") or default_coll or "").strip()
        if not intitule:
            continue
        key = (intitule.lower()[:80], coll.lower())
        if key in existing:
            continue
        existing.add(key)
        score, label = score_pertinence(p, criteria, domaines=domaines)
        src = f"Délibération · {p['source']}" if p.get("source") else source_label
        mat = p.get("maturite")
        sig = Signal(
            user_id=current_user.id, intitule=intitule[:500],
            type_projet=(p.get("type_projet") or "")[:120],
            budget=_num(p.get("budget")), budget_texte=(p.get("budget_texte") or "")[:120],
            localisation=(p.get("localisation") or "")[:255], collectivite=coll[:255],
            calendrier=(p.get("calendrier") or "")[:255], metiers=p.get("metiers") or [],
            extrait=(p.get("extrait") or "")[:2000], pertinence=label, pertinence_score=score,
            source_name=src[:255], source_url=(p.get("url") or "")[:700], source_date=(p.get("date") or "")[:40],
            domaine=(p.get("domaine") or "")[:80], phase=(p.get("phase") or "")[:40],
            echeance_ao=(p.get("echeance_ao") or "")[:120], financement=(p.get("financement") or "")[:255],
            maturite=int(mat) if isinstance(mat, (int, float)) else None,
        )
        db.add(sig)
        created.append(sig)
    db.commit()
    for s in created:
        db.refresh(s)
    created.sort(key=lambda s: s.pertinence_score, reverse=True)
    return [_out(s) for s in created]


def _analyze_text(text: str, source_name: str, current_user: User, db: Session, domaines=None) -> dict:
    from app.services.llm import tenant_scope
    with tenant_scope(current_user.id):
        res = detect_projets(text, lang_name=_lang(current_user, db), domaines=domaines)
    signals = _persist(res.get("projets", []), res.get("collectivite", ""), source_name, current_user, db, domaines=domaines)
    return {"collectivite": res.get("collectivite", ""), "count": len(signals), "signals": signals}


@router.post("/analyze-upload")
@limiter.limit("30/hour")
async def analyze_upload(request: Request, file: UploadFile = File(...), domaines: str = Form(""),
                         current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    content = await file.read()
    if not content:
        raise HTTPException(400, "Fichier vide.")
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(413, "Fichier trop volumineux (50 Mo max).")
    try:
        text = extract_dce_text(file.filename, content)
    except ValueError as e:
        raise HTTPException(422, str(e))
    consume_analysis(current_user, db)
    doms = [d.strip() for d in (domaines or "").split(",") if d.strip()]
    return _analyze_text(text, file.filename or "Délibération importée", current_user, db, domaines=doms)


@router.post("/analyze-text")
@limiter.limit("30/hour")
def analyze_text(request: Request, payload: dict,
                 current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    text = (payload or {}).get("text", "")
    if len(text.strip()) < 60:
        raise HTTPException(422, "Texte trop court pour une détection fiable.")
    consume_analysis(current_user, db)
    doms = (payload or {}).get("domaines") or []
    return _analyze_text(text, (payload.get("source") or "Texte collé")[:255], current_user, db, domaines=doms)


class ScanRequest(BaseModel):
    departements: list[str] = []   # cibler des régions/départements (ex. ["75","94"]) ; vide = toute la France
    domaines: list[str] = []       # cibler des domaines (bâtiment, voirie/VRD, réseaux, énergie…)


@router.post("/scan")
@limiter.limit("12/hour")
def scan(request: Request, req: ScanRequest = ScanRequest(),
         current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Adjugo VA CHERCHER les délibérations récentes des collectivités (open data),
    pré-filtre l'investissement, puis l'IA détecte les projets futurs.
    Si des départements sont ciblés, on ne garde que ces zones."""
    country = _country(current_user, db)
    deps = {d.strip()[:3] for d in (req.departements or []) if d.strip()}
    doms = [d.strip() for d in (req.domaines or []) if d.strip()]
    # Profondeur accrue : on récupère davantage de délibérations (60) pour creuser.
    records = DeliberationSource().fetch_recent(country=country, per=60, only_invest=True)
    if records and deps and country == "FR":   # filtrage régional = France
        records = [r for r in records if (r.get("dept") in deps) or not r.get("dept")]
    if not records:
        return {"scanned": 0, "count": 0, "signals": [], "country": country,
                "errors": ["Aucune délibération sur ce périmètre (élargissez les régions ou réessayez)."]}
    consume_analysis(current_user, db)
    from app.services.llm import tenant_scope
    with tenant_scope(current_user.id):
        projets = detect_from_deliberations(records, lang_name=_lang(current_user, db), domaines=doms)
    if deps and country == "FR":
        projets = [p for p in projets if (p.get("dept") in deps) or not p.get("dept")]
    signals = _persist(projets, "", "Délibération (open data)", current_user, db, domaines=doms)
    return {"scanned": len(records), "count": len(signals), "signals": signals}


class AutoRequest(BaseModel):
    enabled: bool


@router.get("/auto")
def auto_status(current_user: User = Depends(get_current_user)):
    return {"enabled": bool(getattr(current_user, "amont_alerts_enabled", False))}


@router.post("/auto")
def set_auto(req: AutoRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Active/désactive la veille amont automatique : un scan régulier détecte les
    nouveaux projets et envoie un email des nouveautés pertinentes."""
    current_user.amont_alerts_enabled = bool(req.enabled)
    db.commit()
    return {"enabled": current_user.amont_alerts_enabled}


@router.get("/")
def list_signals(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sigs = (db.query(Signal)
            .filter(Signal.user_id == current_user.id, Signal.archived == False)  # noqa: E712
            .order_by(Signal.pertinence_score.desc(), Signal.created_at.desc())
            .limit(200).all())
    return [_out(s) for s in sigs]


@router.delete("/{signal_id}")
def delete_signal(signal_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.query(Signal).filter(Signal.id == signal_id, Signal.user_id == current_user.id).first()
    if not s:
        raise HTTPException(404, "Signal introuvable")
    s.archived = True
    db.commit()
    return {"ok": True}


def _num(v):
    try:
        return float(v) if v is not None and str(v) != "" else None
    except (ValueError, TypeError):
        return None
