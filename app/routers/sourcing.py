"""
Pipeline de sourcing À LA DEMANDE (anti-hallucination, validation à chaque étape).
Aucune étape ne s'auto-exécute : l'utilisateur déclenche chaque action.

  1. POST /api/sourcing/search       — recherche AO multi-sources (sans LLM, gratuit)
  2. POST /api/sourcing/analyze      — analyse profonde d'UN AO choisi (LLM, quota)
  3. POST /api/sourcing/cotraitants  — sourcing co-traitants réels (sans LLM)
  4. POST /api/sourcing/documents    — génération du dossier (LLM, sur les choisis)
"""
import logging
import threading as _threading
import time as _time
from collections import OrderedDict as _OrderedDict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field as PydField

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.org import data_owner_id, member_ids
from app.core.ratelimit import limiter
from app.core.uploads import aread_upload_limited
from starlette.concurrency import run_in_threadpool
from app.models import User, Company, Project
from app.sourcing.base import TenderCriteria
from app.sourcing.sources.boamp import BoampSource
from app.sourcing.sources.ted import TedSource
from app.sourcing.sources.atexo import MEGALIS, PLACE
from app.sourcing.sources.sirene import SireneSource
from app.sourcing.sources.bodacc import BodaccSource
from app.sourcing.sources.buyer import BuyerProfileSource
from app.sourcing.search import TenderSearchService, CompanySearchService
from app.sourcing.schemas import NormalizedTender
from app.schemas import safe_link_url
from app.services.profile import company_dict as _company_dict, criteria_dict as _criteria_dict

logger = logging.getLogger("adjugo")
router = APIRouter(prefix="/api/sourcing", tags=["Sourcing (sources officielles)"])

# Sources AO actives : BOAMP (national FR) + TED (européen) + plateformes Atexo
# (profils acheteurs : PLACE = État national ; Mégalis = collectivités bretonnes — couvrent
# les MAPA sous-seuil absents du BOAMP). Pagination + cache 20 min + garde-fou template.
# DECP = marchés attribués → réservé à l'« intelligence marché », pas au feed d'AO ouverts.
TENDER_SOURCES = [BoampSource(), TedSource(), MEGALIS, PLACE]
COMPANY_SOURCES = [SireneSource()]


def _tender_sources(countries: list) -> list:
    """Sources à interroger selon les pays demandés. BOAMP (national FR) n'est
    pertinent que pour la France ; TED couvre tous les pays UE/EEE."""
    cc = [str(c).upper() for c in (countries or [])]
    fr_inclus = (not cc) or ("FR" in cc)
    sources = []
    if fr_inclus:
        # BOAMP (bulletin national) + les plateformes Atexo : Mégalis (MAPA Bretagne) et
        # PLACE (MAPA de l'État). Mégalis et PLACE s'auto-filtrent (Mégalis = départements
        # bretons uniquement ; PLACE = France) → aucun surcoût quand hors périmètre.
        sources += [BoampSource(), MEGALIS, PLACE]
    sources.append(TedSource())
    return sources
# Red-flag financier (procédure collective) — enrichissement parallèle, jamais bloquant.
RED_FLAG_SOURCE = BodaccSource()
BUYER_SOURCE = BuyerProfileSource()


def _company_service() -> CompanySearchService:
    return CompanySearchService(COMPANY_SOURCES, red_flag_source=RED_FLAG_SOURCE)


def _verdict(score, gonogo) -> str:
    """Verdict Go/À étudier/No-Go à partir des seuils du profil. Garde-fou CENTRAL :
    on force nogo_threshold < go_threshold pour que la bande « à étudier » existe toujours
    (sinon un profil mal réglé nogo≥go faisait disparaître la zone intermédiaire)."""
    go_t = (gonogo or {}).get("go_threshold") or 65
    nogo_t = (gonogo or {}).get("nogo_threshold") or 40
    nogo_t = min(nogo_t, go_t - 1)
    return "go" if score >= go_t else ("no_go" if score < nogo_t else "a_etudier")


def _apply_groupement(db, project, analysis, company_data, gonogo, current_user) -> None:
    """« Répondre à plusieurs ? » — verdict de groupement après une analyse sur DCE réel :
    manques + alliance automatique sur les partenaires rattachés et l'annuaire (JAMAIS de
    réseau ici). Pose go_decision='go_groupement' le cas échéant ; match_score reste le score
    SEUL. Tolérant : service absent / erreur → rien ne change, l'analyse est déjà sauvée."""
    try:
        from app.services.groupement_verdict import apply_groupement_verdict
        apply_groupement_verdict(db, project, analysis, company_data, gonogo,
                                 member_ids(current_user, db))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("verdict de groupement ignoré (projet %s) : %s", getattr(project, "id", "?"), e)


def _user_country(current_user, db) -> str:
    """Pays d'adaptation de l'organisation de l'utilisateur (défaut FR)."""
    from app.models import Organization
    if getattr(current_user, "org_id", None):
        org = db.query(Organization).filter(Organization.id == current_user.org_id).first()
        if org and org.country:
            return org.country
    return "FR"


def _user_lang_name(current_user, db) -> str:
    from app.core.countries import lang_name
    return lang_name(_user_country(current_user, db))


@router.get("/buyer-profile")
@limiter.limit("60/hour")
def buyer_profile(request: Request, acheteur: str = "",
                  current_user: User = Depends(get_current_user)):
    """Intelligence marché : historique de publication réel d'un acheteur (BOAMP).
    Renvoie {} si l'acheteur n'a aucun avis trouvé — jamais de profil inventé."""
    prof = BUYER_SOURCE.profile(acheteur)
    return prof or {"acheteur": acheteur, "found": False}


class MarketEstimateRequest(BaseModel):
    objet: str = ""
    departement: str = ""
    cpv: str = ""


@router.post("/market-estimate")
@limiter.limit("40/hour")
def market_estimate(request: Request, req: MarketEstimateRequest,
                    current_user: User = Depends(get_current_user)):
    """Repère de PRIX DE MARCHÉ (fourchette) à partir des marchés comparables réels (DECP).
    Déterministe, SANS LLM, SANS quota. C'est un repère INDICATIF sourcé — jamais le budget
    de l'acheteur, jamais un montant inventé. Utile quand l'avis ne publie pas de montant."""
    objet = (req.objet or "").strip()
    if len(objet) < 3:
        raise HTTPException(422, "Objet trop court pour estimer un repère de prix.")
    from app.services.estimation_budget import estimer_budget
    return estimer_budget(objet, departement=(req.departement or "").strip()[:3],
                          cpv=((req.cpv or "").strip() or None))


# ── Optimiseur de groupement (composition recommandée par lot) ────────────────────

class GroupementRequest(BaseModel):
    project_id: int


@router.post("/groupement")
@limiter.limit("30/hour")
def optimize_groupement(request: Request, req: GroupementRequest,
                        current_user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """Décompose l'allotissement et recommande une composition de groupement :
    lots couverts en propre (mandataire) vs lots à confier à un co-traitant scoré."""
    import re as _re
    from app.sourcing.groupement import parse_lots, infer_trade, own_trades
    from app.sourcing.sources.sirene import TRADES

    project = db.query(Project).filter(Project.id == req.project_id,
                                       Project.user_id.in_(member_ids(current_user, db)),
                                       Project.deleted_at.is_(None)).first()
    if not project or not project.ai_analysis:
        raise HTTPException(404, "Projet ou analyse introuvable")

    details = (project.ai_analysis or {}).get("details", {})
    company = db.query(Company).filter(Company.user_id == data_owner_id(current_user, db)).first()
    company_data = _company_dict(company)
    gonogo = _criteria_dict(current_user.id, db)

    # Département d'exécution (pour cibler les co-traitants au plus près)
    dep = ""
    m = _re.search(r"\b(\d{2})\d{0,3}\b", str(details.get("lieu_execution") or ""))
    if m:
        dep = m.group(1)
    elif gonogo.get("departements"):
        dep = str(gonogo["departements"]).split(",")[0].strip()[:2]
    deps = [dep] if dep else []

    lots = parse_lots(details.get("allotissement", ""))
    mine = own_trades({**company_data, "specialites": gonogo.get("specialites", "")})
    trade_label = {t["key"]: t["label"] for t in TRADES}

    svc = _company_service()
    out_lots, n_propre, n_cot, n_non = [], 0, 0, 0
    for lot in lots:
        key = infer_trade(lot["label"])
        entry = {"num": lot["num"], "label": lot["label"],
                 "trade": trade_label.get(key), "candidate": None}
        if key and key in mine:
            entry["couverture"], entry["role"] = "propre", "mandataire"
            n_propre += 1
        elif key:
            res = svc.discover(activity=key, departement=dep, tender_departements=deps,
                               need_label=trade_label.get(key, ""), limit=6)
            best = res["companies"][0] if res["companies"] else None
            if best:
                entry["couverture"], entry["role"] = "co_traitance", "cotraitant"
                entry["candidate"] = best.model_dump(exclude={"raw"})
                n_cot += 1
            else:
                entry["couverture"], entry["role"] = "non_couvert", None
                n_non += 1
        else:
            entry["couverture"], entry["role"] = "indetermine", None
            n_non += 1
        out_lots.append(entry)

    return {
        "n_lots": len(out_lots), "n_propre": n_propre,
        "n_cotraitance": n_cot, "n_non_couverts": n_non,
        "mandataire": company_data.get("name") or "Votre entreprise",
        "lots": out_lots,
        "allotissement": details.get("allotissement", ""),
    }


# ── Étape 1 : recherche AO (déterministe, sans LLM) ──────────────────────────────

class SearchRequest(BaseModel):
    query: str = ""
    departements: list[str] = []
    cpv: list[str] = []
    montant_min: Optional[float] = None
    montant_max: Optional[float] = None
    limit: int = PydField(20, ge=1, le=100)          # borné : l'UI demande 15 par page
    offset: int = PydField(0, ge=0, le=10000)        # pagination « charger plus »
    countries: list[str] = []      # ISO alpha-2 (ex. ["FR","DE"]). Vide = toute l'UE/EEE.
    type_marche: str = ""          # "travaux" | "services" | "fournitures" | "" (tous)


@router.get("/countries")
def list_countries(current_user: User = Depends(get_current_user)):
    """Liste des pays couverts par TED (UE + EEE) pour le sélecteur de recherche."""
    from app.sourcing.sources.ted import EU_COUNTRIES
    return [{"code": c["a2"], "nom": c["nom"]} for c in EU_COUNTRIES]


@router.post("/search")
@limiter.limit("60/hour")
def search_tenders(request: Request, req: SearchRequest,
                   current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    from app.services.demo_search import is_demo as _is_demo, search_results as _demo_search
    if _is_demo(current_user):
        _t = _demo_search()   # le vrai BOAMP renverrait vide sur la requête démo → liste canned riche
        return {"count": len(_t), "sources_queried": ["BOAMP"], "sources_skipped": [], "errors": [],
                "tenders": [x.model_dump(exclude={"raw"}) for x in _t], "has_more": False,
                "closed_filtered": 0, "amount_filtered": 0}
    company = db.query(Company).filter(Company.user_id == data_owner_id(current_user, db)).first()
    company_data = _company_dict(company)
    gonogo = _criteria_dict(current_user.id, db)
    crit = TenderCriteria(query=req.query, cpv=req.cpv, departements=req.departements,
                          montant_min=req.montant_min, montant_max=req.montant_max,
                          limit=req.limit, countries=req.countries, type_marche=req.type_marche,
                          offset=req.offset)
    result = TenderSearchService(_tender_sources(req.countries)).search(crit, company_data, gonogo)
    return {
        "count": result["count"],
        "sources_queried": result["sources_queried"],
        "sources_skipped": result.get("sources_skipped", []),
        "errors": [e.model_dump() for e in result["errors"]],
        "tenders": [t.model_dump(exclude={"raw"}) for t in result["tenders"]],
        "has_more": result.get("has_more", False),
        # combien d'AO ÉCARTÉS (clôturés / hors fourchette) → le front distingue « rien trouvé »
        # de « des marchés existaient mais ont été filtrés » (message actionnable).
        "closed_filtered": result.get("closed_filtered", 0),
        "amount_filtered": result.get("amount_filtered", 0),
    }


# ── Radar des échéances : marchés attribués arrivant à terme (LLM, quota) ─────────

class RenewalRequest(BaseModel):
    query: str = "travaux"
    departements: list[str] = []
    domaines: list[str] = []


@router.post("/renewals")
@limiter.limit("12/hour")
def renewals(request: Request, req: RenewalRequest,
             current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Traque les marchés DÉJÀ ATTRIBUÉS dont le contrat arrive bientôt à échéance →
    se positionner auprès de l'acheteur avant la republication.

    PRIORITÉ DECP (Données Essentielles, open data) : durée + date réelles → échéance
    100 % DÉTERMINISTE, couverture de TOUS les profils acheteurs (pas que BOAMP),
    et GRATUIT (aucun quota consommé). Repli sur la version BOAMP+IA si DECP est vide."""
    gonogo = _criteria_dict(current_user.id, db)
    deps = [d.strip()[:2] for d in (req.departements or []) if d.strip()]

    # 1) DECP — déterministe, sans LLM, sans quota.
    try:
        from app.services.decp import detect_renewals_decp
        res = detect_renewals_decp(req.query or "travaux", deps, gonogo, domaines=req.domaines)
        if res.get("renewals"):
            return res
    except Exception as e:
        logger.warning("Radar DECP en échec, repli BOAMP+IA : %s", e)

    # 2) Repli : BOAMP + enrichissement IA (consomme un quota, remboursé si rien).
    from app.core.quota import consume_analysis, refund_analysis
    from app.services.renewal import detect_renewals
    consume_analysis(current_user, db)
    from app.services.llm import tenant_scope
    try:
        with tenant_scope(current_user.id):
            res = detect_renewals(req.query or "travaux", deps, gonogo, domaines=req.domaines)
    except Exception:
        refund_analysis(current_user, db)
        raise
    # Remboursement dès que le repli ne produit AUCUN renouvellement (BOAMP vide, hors
    # fenêtre, ou erreur) : pas de valeur rendue = pas de quota débité.
    if not res.get("renewals"):
        refund_analysis(current_user, db)
    return res


# ── Étape 2 : analyse profonde d'UN AO (LLM, quota) ──────────────────────────────

class AnalyzeRequest(BaseModel):
    tender: dict  # NormalizedTender choisi par l'utilisateur (étape 1)


@router.post("/analyze")
@limiter.limit("30/hour")
def analyze_tender(request: Request, req: AnalyzeRequest,
                   current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    from app.core.quota import consume_analysis, refund_analysis
    from app.services.analysis import analyze_dce_text

    try:
        tender = NormalizedTender(**req.tender)
    except Exception:
        raise HTTPException(400, "Objet AO invalide")

    from app.services.demo_search import is_demo as _is_demo, analysis_for as _demo_analysis
    if _is_demo(current_user) and (tender.provenance.official_ref or "").startswith("DEMO-"):
        _a = _demo_analysis(tender.provenance.official_ref)
        if _a:
            _score = _a.get("match_score", 0); _decision = _a.get("go_decision")
            _proj = Project(user_id=current_user.id,
                            name=(_a.get("details", {}).get("intitule_marche") or tender.objet)[:500],
                            client=tender.acheteur or "", match_score=_score, go_decision=_decision,
                            ai_summary=_a.get("summary", ""), ai_analysis=_a, source_url=_safe_link(tender.provenance.source_url))
            db.add(_proj); db.commit(); db.refresh(_proj)
            return {"project_id": _proj.id, "decision": _decision, "score": _score, "dce_available": True,
                    "confidence": tender.confidence, "summary": _a.get("summary", ""),
                    "details": _a.get("details", {}), "score_breakdown": _a.get("score_breakdown"),
                    "source": _safe_source(tender.provenance.model_dump())}

    consume_analysis(current_user, db)  # 402 si quota atteint

    company = db.query(Company).filter(Company.user_id == data_owner_id(current_user, db)).first()
    company_data = _company_dict(company)
    gonogo = _criteria_dict(current_user.id, db)

    # DCE RÉEL ou « non disponible » — jamais inventé
    src = next((s for s in TENDER_SOURCES if s.name == tender.provenance.source), TENDER_SOURCES[0])
    dce_text = src.fetch_dce(tender)
    dce_available = bool(dce_text)
    if not dce_text:
        # On analyse alors l'avis lui-même (objet + métadonnées), pas un DCE fabriqué
        dce_text = _tender_as_text(tender)

    from app.services.llm import tenant_scope
    try:
        with tenant_scope(current_user.id):
            analysis = analyze_dce_text(dce_text, company_data, gonogo,
                                        lang_name=_user_lang_name(current_user, db))
    except Exception:
        refund_analysis(current_user, db)   # l'IA a échoué → on ne débite pas le quota
        raise HTTPException(503, "L'analyse IA est momentanément indisponible. "
                                 "Réessayez — votre quota n'a pas été débité.")
    analysis["dce_available"] = dce_available
    analysis["source"] = _safe_source(tender.provenance.model_dump())
    analysis["lead_score"] = tender.score.model_dump() if tender.score else None

    # Le SCORE Go/No-Go n'est posé QU'À PARTIR D'UN VRAI DCE analysé : sur un avis
    # seul, scorer ne vaut rien. L'analyse reste préliminaire (pas de score/décision)
    # ; le score apparaît après import du DCE réel via /analyze-upload.
    if dce_available:
        score = analysis.get("match_score", 0)
        decision = _verdict(score, gonogo)
    else:
        score = None
        decision = None
        analysis.pop("match_score", None)
    analysis["go_decision"] = decision

    project = Project(
        user_id=current_user.id,
        name=(analysis.get("details", {}).get("intitule_marche") or tender.objet)[:500],
        client=tender.acheteur or "",
        match_score=score, go_decision=decision,
        ai_summary=analysis.get("summary", ""), ai_analysis=analysis,
        source_url=_safe_link(tender.provenance.source_url),
    )
    db.add(project); db.commit(); db.refresh(project)

    # Verdict de groupement SEULEMENT sur un vrai DCE scoré (sans DCE : pas de score, rien).
    if dce_available:
        _apply_groupement(db, project, analysis, company_data, gonogo, current_user)

    return {
        "project_id": project.id, "decision": project.go_decision, "score": score,   # score = SEUL
        "dce_available": dce_available,
        "confidence": tender.confidence,
        "summary": analysis.get("summary", ""),
        "details": analysis.get("details", {}),
        "score_breakdown": analysis.get("score_breakdown"),   # « pourquoi ce % » (déterministe)
        "source": _safe_source(tender.provenance.model_dump()),
        "groupement": analysis.get("groupement"),
        "groupement_score": project.groupement_score,
    }


# ── Étape 2 bis : analyse du DCE RÉEL importé (PDF/ZIP) — LECTURE INTÉGRALE ────────
#
# Chaque pièce est lue EN ENTIER (app.services.dce_lecture), le texte intégral est rangé avec les
# fichiers du marché (app.services.dce_texte) et l'IA reçoit tout le dossier, d'un seul tenant
# ou pièce par pièce (app.services.analyse_dossier). Un petit dossier est traité pendant la
# requête, comme avant ; un gros dossier (pages scannées à lire, lecture en deux temps) part en
# tâche de fond et sa progression se lit sur GET /api/sourcing/lecture/{project_id}.
# Quota : UNE analyse par import, remboursée si l'IA tombe.

_PROGRESS = _OrderedDict()          # job_id -> progression (process unique ; bornée)
_PROGRESS_LOCK = _threading.Lock()
_PROGRESS_MAX = 500


def _set_progress(job_id, **kw) -> None:
    with _PROGRESS_LOCK:
        d = _PROGRESS.setdefault(job_id, {})
        d.update(kw)
        d["maj"] = _time.time()
        _PROGRESS.move_to_end(job_id)
        while len(_PROGRESS) > _PROGRESS_MAX:
            _PROGRESS.popitem(last=False)


def _get_progress(job_id) -> dict:
    with _PROGRESS_LOCK:
        return dict(_PROGRESS.get(job_id) or {})


def _analyze_lecture_in_thread(user_id, lecture, company_data, gonogo, lang_name):
    """Analyse d'un dossier lu en entier, hors de la boucle d'événements, dans l'espace facturé."""
    from app.services.analyse_dossier import analyser
    from app.services.llm import tenant_scope
    with tenant_scope(user_id):
        return analyser(lecture, company_data, gonogo, lang_name=lang_name)


def _lire_direct(filename, content):
    from app.services.dce_lecture import lire_dossier
    return lire_dossier(filename, content, mode="direct")


def _empreinte(content: bytes) -> str:
    import hashlib
    return hashlib.sha256(content or b"").hexdigest()


def _needs_background(lecture: dict, company_data, gonogo, lang_name) -> bool:
    """Tâche de fond si des pages restent à lire (scans) ou si le dossier se lit en deux temps
    (plusieurs appels à l'IA) : la requête ne doit jamais tenir plusieurs minutes."""
    if lecture.get("a_poursuivre"):
        return True
    from app.services.analyse_dossier import plan
    return plan(lecture, company_data, gonogo, lang_name)["mode"] != "integral"


def _lecture_state(project) -> dict:
    wf = project.workflow if isinstance(project.workflow, dict) else {}
    st = wf.get("lecture")
    return st if isinstance(st, dict) else {}


def _set_lecture_state(db, project, state: dict) -> None:
    from sqlalchemy.orm.attributes import flag_modified
    wf = dict(project.workflow) if isinstance(project.workflow, dict) else {}
    wf["lecture"] = state
    project.workflow = wf
    flag_modified(project, "workflow")
    db.commit()


def _lecture_en_cours(db, project) -> bool:
    from app.models import Job
    st = _lecture_state(project)
    if st.get("etat") != "en_cours" or not st.get("job_id"):
        return False
    j = db.get(Job, st["job_id"])
    return bool(j and j.status in ("pending", "running"))


def _finish_analysis(db, project, analysis, company_data, gonogo, user, lecture=None) -> dict:
    """Enregistre une analyse de dossier réel sur le marché (verdict, grille, groupement) et
    renvoie la réponse de la route. Commun à l'analyse pendant la requête et en tâche de fond."""
    from datetime import datetime, timezone
    analysis["dce_available"] = True
    prev = project.ai_analysis or {}
    if lecture is not None and isinstance(analysis.get("lecture"), dict):
        # Taille du texte intégral rangé (export RGPD) ; ré-analyse du même texte : celle d'avant.
        analysis["lecture"]["taille_stockee"] = (lecture.get("taille_stockee")
                                                 or ((prev.get("lecture") or {}).get("taille_stockee")
                                                     if isinstance(prev, dict) else None))
    _keep_grille_choices(prev, analysis)
    analysis["source"] = _safe_source(prev.get("source"))
    analysis["lead_score"] = prev.get("lead_score")
    score = analysis.get("match_score", 0)
    decision = _verdict(score, gonogo)
    analysis["go_decision"] = decision
    project.match_score = score
    project.go_decision = decision
    project.ai_summary = analysis.get("summary", "")
    project.ai_analysis = analysis
    intitule = analysis.get("details", {}).get("intitule_marche")
    if intitule:
        project.name = intitule[:500]
    st = dict(_lecture_state(project))
    st.update({"etat": "termine", "fin": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    _set_lecture_state(db, project, st)        # commit
    _apply_groupement(db, project, analysis, company_data, gonogo, user)
    return {
        "project_id": project.id, "decision": project.go_decision, "score": score,   # score = SEUL
        "dce_available": True,
        "summary": analysis.get("summary", ""),
        "details": analysis.get("details", {}),
        "score_breakdown": analysis.get("score_breakdown"),   # « pourquoi ce % » (déterministe)
        "source": analysis["source"],
        "groupement": analysis.get("groupement"),
        "groupement_score": project.groupement_score,
        "couverture": analysis.get("couverture"),
    }


_ECHEC_LECTURE = ("La lecture ou l'analyse du dossier a échoué. Réessayez : votre analyse n'a pas été "
                  "débitée.")


def _sauver_lecture(db, project, lecture) -> None:
    """Range le texte intégral ; un échec du stockage n'empêche jamais l'analyse (les questions
    retombent alors sur l'extrait de l'analyse)."""
    from app.services import dce_texte
    try:
        dce_texte.sauver(db, project, lecture)
    except Exception as e:      # noqa: BLE001
        db.rollback()
        logger.warning("texte intégral du marché %s non rangé : %s", getattr(project, "id", "?"), type(e).__name__)


def _lecture_job(jdb, job_id: int, project_id: int, user_id: int, filename: str, content: bytes,
                 lecture: dict, stored: bool, company_data, gonogo, lang_name) -> dict:
    """Tâche de fond : lecture intégrale (OCR compris), rangement du texte, analyse, enregistrement.
    Toute exception passe le job en erreur ET rembourse l'analyse (app.services.jobs) ; le message
    gardé est toujours lisible par l'utilisateur (jamais un détail technique)."""
    from app.services.llm import LLMUnavailable
    try:
        return _lecture_job_run(jdb, job_id, project_id, user_id, filename, content, lecture, stored,
                                company_data, gonogo, lang_name)
    except (ValueError, LLMUnavailable):
        raise
    except Exception as e:
        logger.warning("lecture du dossier (marché %s) en échec : %s", project_id, type(e).__name__)
        raise RuntimeError(_ECHEC_LECTURE) from e


def _lecture_job_run(jdb, job_id, project_id, user_id, filename, content, lecture, stored,
                     company_data, gonogo, lang_name) -> dict:
    from app.models import Project, User
    from app.services.analyse_dossier import analyser
    from app.services.dce_lecture import lire_dossier, totaux

    def prog(d):
        _set_progress(job_id, **d)

    if not stored:
        _set_progress(job_id, etape="lecture", pieces_lues=0)
        lecture = lire_dossier(filename, content, mode="fond", progress=prog, reprise=lecture)
        lecture["source_empreinte"] = _empreinte(content)
    project = jdb.get(Project, project_id)
    if project is None:
        raise ValueError("Ce marché n'existe plus.")
    if not stored:
        _sauver_lecture(jdb, project, lecture)
    t = totaux(lecture)
    _set_progress(job_id, etape="analyse", pieces_lues=t["pieces"], pages_lues=t["pages_lues"])
    analysis = analyser(lecture, company_data, gonogo, lang_name=lang_name, progress=prog)
    project = jdb.get(Project, project_id)
    user = jdb.get(User, user_id)
    out = _finish_analysis(jdb, project, analysis, company_data, gonogo, user, lecture)
    _set_progress(job_id, etape="termine")
    return out


def _context(db, current_user) -> tuple:
    company = db.query(Company).filter(Company.user_id == data_owner_id(current_user, db)).first()
    return _company_dict(company), _criteria_dict(current_user.id, db), _user_lang_name(current_user, db)


def _start_job(db, project, current_user, filename: str, content: bytes, lecture: dict, stored: bool,
               company_data, gonogo, lang_name) -> int:
    """Lance la lecture intégrale et l'analyse en tâche de fond ; renvoie l'identifiant du job."""
    from datetime import datetime, timezone
    from app.services.jobs import create_job, run_in_thread
    from app.services.dce_lecture import totaux
    job = create_job(db, current_user.id, "lecture_dossier", "Lecture du dossier du marché")
    _set_lecture_state(db, project, {"etat": "en_cours", "job_id": job.id, "source": filename[:200],
                                     "debut": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    t = totaux(lecture)
    _set_progress(job.id, etape="lecture", pieces_total=t["pieces"], pieces_lues=0, pages_lues=0)
    pid, uid, jid = project.id, current_user.id, job.id
    run_in_thread(jid, lambda jdb: _lecture_job(jdb, jid, pid, uid, filename, content, lecture,
                                                stored, company_data, gonogo, lang_name))
    return jid


def _lecture_response(project_id: int, job_id: int):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=202, content={
        "project_id": project_id, "en_cours": True, "job_id": job_id,
        "message": "Dossier volumineux : Adjugo le lit en entier, pièce par pièce. Suivez la progression ici.",
        "progression": _get_progress(job_id)})


def _prepare_rangement(db, project, lecture: dict, content: bytes) -> None:
    lecture["source_empreinte"] = _empreinte(content)
    _sauver_lecture(db, project, lecture)


async def _import_and_analyze(db, project, current_user, filename: str, content: bytes,
                              lecture: dict, stored: bool):
    """Après la lecture directe : petit dossier analysé pendant la requête (d'un seul tenant),
    gros dossier en tâche de fond. Le travail lourd (assemblage, compression, empreinte, IA) se fait
    hors de la boucle d'événements. UNE analyse débitée par import."""
    from app.core.quota import consume_analysis, refund_analysis
    company_data, gonogo, lang_name = _context(db, current_user)
    background = await run_in_threadpool(_needs_background, lecture, company_data, gonogo, lang_name)
    consume_analysis(current_user, db)  # 402 si quota atteint — UNE analyse par import
    if background:
        return _lecture_response(project.id, _start_job(db, project, current_user, filename, content, lecture,
                                                        stored, company_data, gonogo, lang_name))
    if not stored:
        await run_in_threadpool(_prepare_rangement, db, project, lecture, content)
    try:
        analysis = await run_in_threadpool(_analyze_lecture_in_thread, current_user.id, lecture,
                                           company_data, gonogo, lang_name)
    except Exception:
        refund_analysis(current_user, db)   # l'IA a échoué → on ne débite pas le quota
        raise HTTPException(503, "L'analyse IA est momentanément indisponible. "
                                 "Réessayez — votre quota n'a pas été débité.")
    return _finish_analysis(db, project, analysis, company_data, gonogo, current_user, lecture)


@router.post("/analyze-upload")
@limiter.limit("30/hour")
async def analyze_upload(request: Request, file: UploadFile = File(...),
                         project_id: int = Form(...),
                         current_user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id,
                                       Project.user_id.in_(member_ids(current_user, db))).first()
    if not project:
        raise HTTPException(404, "Projet introuvable — analysez d'abord l'avis.")
    if _lecture_en_cours(db, project):
        raise HTTPException(409, "Une lecture du dossier est déjà en cours pour ce marché. Attendez sa fin.")

    content = await aread_upload_limited(file)   # lecture bornée : 413 au-delà de 50 Mo

    # Lecture INTÉGRALE, pièce par pièce (sans OCR pendant la requête) — message clair si rien
    # n'est lisible ou si le format n'est pas pris en charge.
    try:
        lecture = await run_in_threadpool(_lire_direct, file.filename, content)
    except ValueError as e:
        raise HTTPException(422, str(e))

    # Archiver le DCE importé dans le dossier de l'AO (coffre-fort, dossier "DCE").
    # replace_in_dossier (et non save) : un ré-import du même nom REMPLACE l'ancien
    # au lieu d'empiler des doublons (l'utilisateur croyait ses documents « écrasés »).
    # Archivé AVANT l'analyse : une analyse longue ou en échec peut être relancée sans ré-import.
    try:
        from app.services.dossier import replace_in_dossier
        replace_in_dossier(db, current_user.id, project.id, "DCE",
                           file.filename or "DCE.pdf", content, file.content_type or "application/pdf")
    except Exception as e:
        logger.warning("Archivage DCE échoué (projet %s): %s", project.id, e)

    return await _import_and_analyze(db, project, current_user, file.filename or "DCE.pdf", content,
                                     lecture, stored=False)


# ── Ré-analyser le DCE DÉJÀ importé (sans re-télécharger) ────────────────────────
@router.post("/reanalyze")
@limiter.limit("30/hour")
async def reanalyze_project(request: Request, project_id: int = Form(...),
                            current_user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """Relance l'analyse sur le dossier déjà importé — utile après avoir affiné ses
    critères, ou si l'analyse précédente semblait incomplète. Le texte intégral déjà lu est
    réutilisé tel quel (même fichier) ; une analyse antérieure à la lecture intégrale relit le
    dossier en entier."""
    from app.services import dce_texte
    from app.services.storage import get_storage
    from app.models import Document

    project = db.query(Project).filter(Project.id == project_id,
                                       Project.user_id.in_(member_ids(current_user, db))).first()
    if not project:
        raise HTTPException(404, "Projet introuvable.")
    if _lecture_en_cours(db, project):
        raise HTTPException(409, "Une lecture du dossier est déjà en cours pour ce marché. Attendez sa fin.")

    doc = (db.query(Document)
           .filter(Document.user_id.in_(member_ids(current_user, db)), Document.project_id == project.id,
                   Document.folder == "DCE", Document.deleted_at.is_(None))
           .order_by(Document.created_at.desc()).first())
    if not doc:
        raise HTTPException(400, "Aucun dossier importé à ré-analyser. Importez d'abord le dossier du marché.")
    try:
        content = get_storage().load(doc.file_key)
    except Exception:
        raise HTTPException(404, "Le fichier du dossier est introuvable dans le stockage.")
    stored = await run_in_threadpool(dce_texte.charger, project)
    if stored and stored.get("source_empreinte") == await run_in_threadpool(_empreinte, content):
        lecture = dict(stored)                      # déjà lu en entier : on ne relit pas
        lecture.setdefault("a_poursuivre", False)
        return await _import_and_analyze(db, project, current_user, doc.name, content, lecture, stored=True)
    try:
        lecture = await run_in_threadpool(_lire_direct, doc.name, content)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return await _import_and_analyze(db, project, current_user, doc.name, content, lecture, stored=False)


@router.get("/lecture/{project_id}")
def lecture_status(project_id: int, current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Progression de la lecture d'un gros dossier (tâche de fond) et ce qui a été lu."""
    from app.models import Job
    project = db.query(Project).filter(Project.id == project_id,
                                       Project.user_id.in_(member_ids(current_user, db))).first()
    if not project:
        raise HTTPException(404, "Projet introuvable.")
    st = _lecture_state(project)
    out = {"project_id": project.id, "etat": st.get("etat") or "aucune", "job_id": st.get("job_id"),
           "progression": {}, "erreur": ""}
    a = project.ai_analysis if isinstance(project.ai_analysis, dict) else {}
    out["couverture"] = a.get("couverture")
    out["integral"] = bool(a.get("lecture"))
    if st.get("etat") == "en_cours" and st.get("job_id"):
        j = db.get(Job, st["job_id"])
        if j is None or j.status == "error":
            out["etat"] = "erreur"
            out["erreur"] = (j.error if j else "") or "La lecture du dossier a échoué. Votre analyse n'a pas été débitée."
        elif j.status == "done":
            out["etat"] = "termine"
        else:
            out["progression"] = _get_progress(j.id)
    return out


# ── « Comment vous serez noté » : choix de l'utilisateur sur une ligne (0 IA) ─────

def _keep_grille_choices(prev: dict, analysis: dict) -> None:
    """Ré-analyse : les lignes que l'utilisateur avait confirmées ou écartées le restent."""
    try:
        from app.services.grille_notation import carry_over
        old = ((prev or {}).get("details") or {}).get("grille_notation")
        det = analysis.get("details") if isinstance(analysis.get("details"), dict) else None
        if det is not None and isinstance(det.get("grille_notation"), dict) and isinstance(old, dict):
            det["grille_notation"] = carry_over(old, det["grille_notation"])
    except Exception as e:      # noqa: BLE001 — jamais bloquant pour une analyse déjà payée
        logger.warning("reprise des choix de la grille impossible : %s", type(e).__name__)


class GrilleChoixRequest(BaseModel):
    project_id: int
    critere_id: str = PydField(..., min_length=1, max_length=12)
    choix: str = PydField(..., pattern="^(confirme|ecarte|annule)$")
    poids: str = PydField("", max_length=40)


@router.post("/grille/choix")
@limiter.limit("120/hour")
def grille_choix(request: Request, req: GrilleChoixRequest,
                 current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Le chef de file confirme (« je l'ai lu dans le règlement », avec le poids tel qu'il
    l'a lu s'il le souhaite) ou écarte une ligne de la grille. Une ligne « à vérifier »
    n'entre dans le plan qu'après cette confirmation. Aucun appel à l'IA, aucun quota."""
    import copy
    from app.models import utcnow
    from app.services.grille_notation import apply_choice
    project = db.query(Project).filter(Project.id == req.project_id,
                                       Project.user_id.in_(member_ids(current_user, db)),
                                       Project.deleted_at.is_(None)).first()
    if not project:
        raise HTTPException(404, "Projet introuvable.")
    a = copy.deepcopy(project.ai_analysis) if isinstance(project.ai_analysis, dict) else {}
    det = a.get("details") if isinstance(a.get("details"), dict) else {}
    try:
        g = apply_choice(det.get("grille_notation"), req.critere_id, req.choix,
                         poids=req.poids, when=utcnow().isoformat())
    except ValueError as e:
        raise HTTPException(422, str(e))
    det["grille_notation"] = g
    a["details"] = det
    project.ai_analysis = a                  # NOUVEAU dict : colonne JSON bien marquée modifiée
    db.commit()
    try:
        from app.services import audit
        from app.routers.invites import tenant_owner_id
        ln = next((x for x in g.get("criteres") or [] if x.get("id") == req.critere_id), {})
        audit.record(db, action="grille.choix", owner_id=tenant_owner_id(project, db), project_id=project.id,
                     actor=f"user:{current_user.id}", actor_kind="owner", target_type="project",
                     target_id=project.id, detail=f"{req.choix} : {str(ln.get('critere') or '')[:120]}",
                     ip=audit.client_ip(request), meta={"critere_id": req.critere_id, "choix": req.choix})
    except Exception:
        pass
    return {"grille_notation": g}


# ── Q&A IA sur un AO (après import du DCE réel) — sur TOUT le dossier ────────────
#
# Le texte intégral rangé (app.services.dce_texte) est interrogé par une recherche des passages
# pertinents dans TOUTES les pièces (BM25 sans accents ni pluriels) ; le ou les règlements de la
# consultation (RC, RC modificatif, RC de chaque lot) sont toujours remis, en entier dans la limite
# d'ASK_REGLEMENT_MAX, le modificatif en premier. La réponse cite la pièce et la page ; chaque
# phrase citée est vérifiée contre le texte (citation_guard) — une phrase non retrouvée n'est
# jamais présentée comme une citation. Si la réponse n'est pas dans les extraits remis, Adjugo dit
# ce qui a été consulté (jamais « absent du dossier ») et nomme les pièces non lues.
# Hors quota d'analyses, mais borné par organisation et par jour (app.core.quota).

class AskRequest(BaseModel):
    project_id: int
    question: str = PydField(..., min_length=1, max_length=2000)


ASK_SYSTEM = (
    "Tu es un assistant expert des marchés publics. Tu réponds à des questions sur un "
    "appel d'offres À PARTIR DU DCE fourni, de façon précise et concise. Appuie-toi "
    "UNIQUEMENT sur le document : cite le montant, le délai ou la clause exacte quand "
    "c'est pertinent. Si l'information ne figure pas dans le DCE, dis-le clairement — "
    "n'invente jamais."
)

ASK_SYSTEM_INTEGRAL = (
    "Tu es un assistant expert des marchés publics. Tu réponds à une question sur un appel d'offres "
    "à partir des SEULS extraits du dossier de consultation fournis : le ou les règlements de la "
    "consultation (repères [R], ou [R1], [R2]… s'il y en a plusieurs : un règlement modificatif "
    "l'emporte sur le règlement d'origine) et les passages des autres pièces les plus proches de la "
    "question (repères [P1], [P2]…, avec le nom de la pièce et la page).\n"
    "Règles :\n"
    "- Réponds de façon précise et concise (montant, délai, clause exacte), en t'appuyant UNIQUEMENT "
    "sur ces extraits. N'invente jamais.\n"
    "- Pour chaque élément de ta réponse, donne la phrase du dossier recopiée MOT POUR MOT (300 "
    "caractères au plus) et son repère. Une phrase qui n'est pas une copie exacte sera rejetée.\n"
    "- Si la réponse n'est pas dans ces extraits, dis-le clairement (\"trouve\": false) : elle n'a pas "
    "été trouvée dans les extraits fournis — n'écris jamais qu'elle n'existe pas dans le dossier.\n"
    "Réponds UNIQUEMENT en JSON : {\"trouve\": true, \"reponse\": \"...\", "
    "\"citations\": [{\"ref\": \"P1\", \"phrase\": \"...\"}]}"
)

ASK_REGLEMENT_MAX = 60000      # règlement remis en entier jusqu'à 60 000 caractères (≈ 20 000 tokens)
ASK_PASSAGES = 8
ASK_MAX_TOKENS = 1200
MSG_ANCIENNE_ANALYSE = ("Cette analyse date d'avant la lecture intégrale du dossier : la réponse ne s'appuie "
                        "que sur le début du dossier. Ré-analysez ou ré-importez le dossier pour qu'Adjugo le lise en entier.")


def _ask_legacy(project, q: str, lang: str) -> dict:
    """Analyse antérieure à la lecture intégrale : comportement d'origine (extrait de l'analyse),
    en signalant la limite et en invitant à ré-analyser."""
    from app.services.llm import complete, MODEL_FAST
    a = project.ai_analysis or {}
    ctx = a.get("dce_excerpt") or ""
    if not ctx:
        import json as _json
        ctx = (a.get("summary", "") + "\n\nDÉTAILS:\n"
               + _json.dumps(a.get("details", {}), ensure_ascii=False))
    user = (f"DCE de l'appel d'offres « {project.name} » (acheteur : {project.client or 'n/d'}) :\n"
            f"\"\"\"\n{ctx[:30000]}\n\"\"\"\n\nQUESTION : {q}\n\n"
            f"Réponds en {lang}, fondé uniquement sur le DCE ci-dessus.")
    answer = complete(ASK_SYSTEM, user, max_tokens=700, temperature=0.1, model=MODEL_FAST)
    return {"answer": (answer or "").strip() or "—", "sources": [], "integral": False,
            "trouve": None, "verifiee": False, "message": MSG_ANCIENNE_ANALYSE}


def _verify_citation(phrase: str, ref: str, regs: list, hits: list, pieces: list, locs: dict):
    """Source vérifiée d'une phrase citée : {piece, libelle, page, citation} ou None. La phrase doit
    se trouver dans un des extraits REMIS à l'IA (règlements, passages) : l'IA n'a rien lu d'autre.
    regs : [(repère, pièce, texte remis)]. Repère erroné : la phrase est cherchée dans les autres
    extraits remis."""
    from app.services.analysis import citation_guard, Localisateur
    from app.services.dce_lecture import page_of
    cand = []
    r = (ref or "").strip().upper().strip("[]")
    for key, piece, texte in regs:
        if r == key:
            cand.append((key, piece, texte, 0))
    if r.startswith("P") and r[1:].isdigit() and 1 <= int(r[1:]) <= len(hits):
        k = int(r[1:])
        h = hits[k - 1]
        cand.append((f"P{k}", pieces[h["piece_index"]], h["texte"], h["debut"]))
    for key, piece, texte in regs:
        cand.append((key, piece, texte, 0))
    for k, h in enumerate(hits, 1):
        cand.append((f"P{k}", pieces[h["piece_index"]], h["texte"], h["debut"]))
    for key, piece, src, base in cand:
        cit = citation_guard(src, phrase, min_len=12)
        if cit:
            loc = locs.setdefault(key, Localisateur(src))
            off = loc.offset(cit)
            page = page_of(piece, base + off) if off is not None else None
            return {"piece": piece.get("nom") or "", "libelle": piece.get("libelle") or "",
                    "page": page, "citation": cit}
    return None


def _reglements_remis(pieces: list) -> tuple:
    """Règlements remis à l'IA : TOUS ceux du dossier (RC, RC modificatif, RC de chaque lot), le
    modificatif en premier, en entier dans la limite d'ASK_REGLEMENT_MAX caractères au total ; un
    règlement qui n'y tient pas est remis en partie (son début), les suivants pas du tout — leurs
    passages restent alors cherchés comme ceux des autres pièces. Renvoie ([(repère, pièce, texte
    remis, en entier ?)], numéros des pièces remises EN ENTIER, à écarter de la recherche)."""
    from app.services import dce_texte
    regs = dce_texte.reglements(pieces)
    index = {id(p): i for i, p in enumerate(pieces)}
    room, out, entiers = ASK_REGLEMENT_MAX, [], set()
    for p in regs:
        t = p.get("texte") or ""
        if len(t) <= room:
            out.append((p, t, True))
            entiers.add(index[id(p)])
            room -= len(t)
        elif room >= 4000:
            out.append((p, t[:room], False))
            room = 0
    keys = ["R"] if len(out) == 1 else [f"R{i}" for i in range(1, len(out) + 1)]
    return [(k, p, t, full) for k, (p, t, full) in zip(keys, out)], entiers


def _ask_integral(project, payload: dict, q: str, lang: str) -> dict:
    from app.services import dce_texte
    from app.services.dce_lecture import couverture
    from app.services.llm import messages_create, MODEL_FAST, cached_text_block, parse_json
    pieces = payload.get("pieces") or []
    regs, entiers = _reglements_remis(pieces)
    hits = dce_texte.passages(project, q, k=ASK_PASSAGES, payload=payload, exclude_pieces=entiers)
    blocks = []
    head = f"Appel d'offres « {project.name} » (acheteur : {project.client or 'n/d'})."
    if regs:
        parts = []
        for key, p, t, full in regs:
            tag = "en entier" if full else f"début ({len(t)} premiers caractères)"
            modif = ", règlement modificatif" if dce_texte.est_modificatif(p) else ""
            parts.append(f"[{key}] Règlement de la consultation{modif} — pièce « {p.get('nom')} », {tag} :\n<<<\n{t}\n>>>")
        # Préfixe STABLE d'une question à l'autre : mis en cache de prompt (lu à 10 % du prix).
        blocks.append(cached_text_block(head + "\n\n" + "\n\n".join(parts)))
    lines = []
    for i, h in enumerate(hits, 1):
        pg = f", page {h['page']}" if h.get("page") else ""
        lines.append(f"[P{i}] pièce « {h['piece']} » ({h['libelle']}{pg}) :\n<<<\n{h['texte'].strip()}\n>>>")
    cov = couverture(payload)
    manque = cov["non_lues"] + cov["partielles"]
    note = ""
    if manque:
        note = ("\n\nPièces non lues ou lues en partie (l'information peut s'y trouver) : "
                + "; ".join(f"{m['nom']} ({m['raison']})" for m in manque[:15]))
    tail = ("Passages du dossier les plus proches de la question :\n\n" + ("\n\n".join(lines) or "(aucun)")
            + note + f"\n\nQUESTION : {q}\n\nRéponds en {lang}, en JSON.")
    if not regs:
        tail = head + "\n\n" + tail
    blocks.append({"type": "text", "text": tail})
    resp = messages_create(model=MODEL_FAST, max_tokens=ASK_MAX_TOKENS, temperature=0,
                           system=ASK_SYSTEM_INTEGRAL, messages=[{"role": "user", "content": blocks}])
    raw = "".join(getattr(b, "text", "") or "" for b in (getattr(resp, "content", None) or [])
                  if getattr(b, "type", "text") == "text").strip()
    try:
        data = parse_json(raw)
    except Exception:
        data = {"trouve": None, "reponse": raw, "citations": []}
    trouve = data.get("trouve")
    reponse = str(data.get("reponse") or "").strip()
    sources, seen, locs = [], set(), {}
    reg_src = [(k, p, t) for k, p, t, _full in regs]
    for c in (data.get("citations") or [])[:8]:
        if not isinstance(c, dict):
            continue
        src = _verify_citation(str(c.get("phrase") or ""), str(c.get("ref") or ""), reg_src, hits, pieces, locs)
        if src and (src["piece"], src["citation"]) not in seen:
            seen.add((src["piece"], src["citation"]))
            sources.append(src)
    out = {"integral": True, "trouve": trouve, "sources": sources, "verifiee": bool(sources),
           "message": "", "couverture": cov["message"]}
    if trouve is False:
        # Ce qui a été consulté, honnêtement : jamais « absent du dossier » (seuls des extraits ont
        # été remis à l'IA).
        nr, nh = len(regs), len(hits)
        reg_txt = ("le règlement de la consultation" if nr == 1 else f"{nr} règlements de la consultation") if nr else ""
        if nh == 0:
            pas_txt = "aucun autre passage du dossier ne contient les mots de la question"
        elif nh == 1:
            pas_txt = "le seul passage du dossier proche de la question"
        else:
            pas_txt = f"les {nh} passages du dossier les plus proches de la question"
        consulte = f"{reg_txt} ; {pas_txt}" if reg_txt else pas_txt
        msg = (f"Pas trouvé dans les extraits consultés ({consulte}). Reformulez la question avec les mots "
               "du dossier, ou vérifiez dans les pièces.")
        if manque:
            msg += (f" Attention : {len(manque)} pièce{'s' if len(manque) > 1 else ''} n'"
                    f"{'ont' if len(manque) > 1 else 'a'} pas pu être lue{'s' if len(manque) > 1 else ''} en entier "
                    f"({', '.join(m['nom'] for m in manque[:5])}).")
        out["answer"] = msg
        out["sources"], out["verifiee"] = [], False
        return out
    out["answer"] = reponse or "—"
    if not sources:
        out["message"] = ("Phrase non retrouvée telle quelle dans le dossier : vérifiez la réponse dans la "
                          "pièce concernée.")
    return out


@router.post("/ask")
@limiter.limit("90/hour")
def ask_ao(request: Request, req: AskRequest,
           current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.core.quota import reserve_question, release_question
    from app.services import dce_texte
    project = db.query(Project).filter(Project.id == req.project_id,
                                       Project.user_id.in_(member_ids(current_user, db))).first()
    if not project or not project.ai_analysis:
        raise HTTPException(404, "Projet ou analyse introuvable")
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(400, "Question vide")
    lang = _user_lang_name(current_user, db)
    slot = reserve_question(current_user, db)     # 429 au-delà de la borne du jour (organisation)
    try:
        from app.services.llm import tenant_scope, LLMUnavailable
        payload = dce_texte.charger(project)
        with tenant_scope(current_user.id):
            if payload and any(p.get("texte") for p in payload.get("pieces") or []):
                return _ask_integral(project, payload, q, lang)
            return _ask_legacy(project, q, lang)
    except LLMUnavailable as e:
        release_question(db, slot)
        # Dégradation gracieuse : service IA saturé/en pause → 503 RETRYABLE (Retry-After).
        raise HTTPException(503, str(e), headers={"Retry-After": "30"})
    except HTTPException:
        release_question(db, slot)
        raise
    except Exception:
        release_question(db, slot)
        logger.warning("question sur le marché %s en échec", project.id, exc_info=True)
        raise HTTPException(502, "IA momentanément indisponible : réessayez dans un instant.")


# ── Étape 3 : sourcing co-traitants réels (déterministe) ─────────────────────────

class CotraitantsRequest(BaseModel):
    project_id: int
    activity: str = ""          # clé métier (ex 'electricite') ou texte
    departement: str = ""
    query: str = ""


@router.post("/cotraitants")
@limiter.limit("60/hour")
def source_cotraitants(request: Request, req: CotraitantsRequest,
                       current_user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == req.project_id,
                                       Project.user_id.in_(member_ids(current_user, db))).first()
    if not project:
        raise HTTPException(404, "Projet introuvable")
    deps = [req.departement] if req.departement else []
    res = _company_service().discover(
        activity=req.activity, departement=req.departement, query=req.query,
        tender_departements=deps, need_label=req.activity)
    # Complementarity Graph : score de SYNERGIE vs l'entreprise pilote (ce que le
    # candidat APPORTE au groupement). On trie les partenaires par synergie décroissante.
    from app.sourcing.scoring import synergy_score
    lead = db.query(Company).filter(Company.user_id == data_owner_id(current_user, db)).first()
    lead_data = _company_dict(lead)
    for c in res["companies"]:
        if not c.procedure_collective:   # un partenaire en procédure reste plafonné/en bas
            c.synergy = synergy_score(c, lead_data, deps, req.activity)
    res["companies"].sort(key=lambda c: (c.synergy or {}).get("total", 0) if not c.procedure_collective else -1,
                          reverse=True)
    return {
        "count": res["count"],
        "errors": [e.model_dump() for e in res["errors"]],
        "companies": [c.model_dump(exclude={"raw"}) for c in res["companies"]],
    }


# ── Étape 4 : génération du dossier (LLM, sur les co-traitants choisis) ───────────

class DocumentsRequest(BaseModel):
    project_id: int
    cotraitants: list[dict] = []   # NormalizedCompany choisis (avec SIRET)


# Dossier du coffre où est rangé le dossier de présentation (identifiant inchangé : l'écran
# l'affiche « Dossier de présentation »). Ancienne archive, jamais reconnue par la liste des pièces.
MEMOIRE_FOLDER = "Mémoire technique"
_LEGACY_MEMOIRE_ARCHIVE = "memoire_technique.md"


def _archive_memoire(db: Session, user: User, project: Project, dossier: dict, files: dict) -> None:
    """Range le dossier de présentation (Word + PDF) dans le dossier du marché, sous le nom du
    règlement, et mémorise son état (passages à compléter, texte coupé) pour la liste des pièces.
    Remplace la génération précédente (y compris l'ancienne archive .md) ; jamais bloquant."""
    from datetime import datetime, timezone
    from sqlalchemy.orm.attributes import flag_modified
    from app.services.dossier import remove_from_dossier, replace_in_dossier
    mimes = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             "pdf": "application/pdf"}
    try:
        wf = dict(project.workflow) if isinstance(project.workflow, dict) else {}
        before = (wf.get("dossier_presentation") or {}).get("fichiers") or []
        names = [name for name, _b in files.values()]
        remove_from_dossier(db, user.id, project.id, MEMOIRE_FOLDER,
                            [n for n in before if n not in names] + [_LEGACY_MEMOIRE_ARCHIVE])
        for kind, (name, content) in files.items():
            replace_in_dossier(db, user.id, project.id, MEMOIRE_FOLDER, name, content, mimes.get(kind, ""))
        etat = dossier.get("memoire_etat") or {}
        wf["dossier_presentation"] = {
            "nom": dossier.get("memoire_nom") or "", "fichiers": names,
            "a_completer": int(etat.get("a_completer") or 0), "coupe": bool(etat.get("coupe")),
            "genere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        project.workflow = wf
        flag_modified(project, "workflow")
        db.commit()
    except Exception as e:
        db.rollback()
        logging.getLogger("adjugo").warning("archivage du dossier de présentation (projet %s) : %s", project.id, e)


@router.post("/documents")
@limiter.limit("20/hour")
def generate_documents(request: Request, req: DocumentsRequest,
                       current_user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    from app.services.agents import redaction

    project = db.query(Project).filter(Project.id == req.project_id,
                                       Project.user_id.in_(member_ids(current_user, db))).first()
    if not project or not project.ai_analysis:
        raise HTTPException(404, "Projet ou analyse introuvable")

    company = db.query(Company).filter(Company.user_id == data_owner_id(current_user, db)).first()
    company_data = _company_dict(company)

    verified = []
    if req.cotraitants:
        # Flux Sourcing : co-traitants choisis dans la liste SIRENE → re-vérifier le SIRET
        svc = _company_service()
        for c in req.cotraitants:
            siret = c.get("siret")
            official = svc.verify_siret(siret) if siret else None
            if official:
                verified.append({
                    "name": official.nom, "siret": official.siret,
                    "code_ape": official.naf, "specialites": official.naf_label or "",
                    "city": official.ville, "departement": official.departement,
                    "effectif": official.effectif or 0,
                })
    else:
        # Page AO : on prend les sous-traitants déjà RATTACHÉS à l'appel d'offres
        from app.routers.cotraitants import Cotraitant, ProjectCotraitant
        links = db.query(ProjectCotraitant).filter(ProjectCotraitant.project_id == project.id).all()
        for lk in links:
            ct = db.query(Cotraitant).filter(Cotraitant.id == lk.cotraitant_id).first()
            if ct:
                verified.append({
                    "name": ct.name, "siret": ct.siret, "code_ape": ct.code_ape,
                    "specialites": ct.specialites, "city": ct.city,
                    "departement": ct.departement, "effectif": ct.effectif or 0,
                    "role": lk.role or "sous_traitant",
                })

    from app.services.llm import tenant_scope, cost_meter
    # Coût IA d'un dossier complet (rédaction + fusion des apports) : journalisé, pour décider
    # plus tard du quota ; rien n'est montré au client.
    with tenant_scope(current_user.id), cost_meter("dossier de réponse complet", current_user.id):
        dossier = redaction.build_dossier(project.ai_analysis, company_data, verified, project.id,
                                          lang_name=_user_lang_name(current_user, db),
                                          country=_user_country(current_user, db),
                                          db=db, user_id=current_user.id, estimate=project.estimate)
    memoire_files = dossier.pop("_memoire_files", None) or {}

    # Archiver les CERFA + le dossier de présentation (Word ET PDF) dans le dossier de l'AO.
    try:
        import base64
        from app.services.dossier import replace_in_dossier
        for c in dossier.get("cerfas", []):
            replace_in_dossier(db, current_user.id, project.id, "CERFA",
                               c["name"], base64.b64decode(c["content_b64"]), "application/pdf")
    except Exception:
        pass
    if memoire_files:
        _archive_memoire(db, current_user, project, dossier, memoire_files)

    return {
        "cotraitants_verifies": len(verified),
        "cotraitants_rejetes": (len(req.cotraitants) - len(verified)) if req.cotraitants else 0,
        "dossier": dossier,
    }


def _safe_link(url) -> Optional[str]:
    """Lien d'avis stocké sur le projet (affiché ensuite comme lien cliquable, y compris
    à un partenaire) : l'objet AO vient du navigateur, donc UNE SEULE règle, celle de
    safe_link_url (http(s) absolu ou chemin interne « /… » ; jamais javascript:, data:,
    « //hôte », « /\\hôte »…). Plafond = taille de la colonne Project.source_url (500)."""
    return safe_link_url(url, 500)


def _safe_source(src) -> dict:
    """Bloc « source » d'une analyse (stocké dans ai_analysis puis renvoyé à l'interface) :
    son source_url passe par la même règle — une ancienne valeur douteuse ressort vide."""
    if not isinstance(src, dict):
        return {}
    out = dict(src)
    if "source_url" in out:
        out["source_url"] = safe_link_url(out.get("source_url"), 2000) or ""
    return out


def _tender_as_text(t: NormalizedTender) -> str:
    """Représentation texte de l'avis (pas un DCE complet) pour analyse de repli."""
    parts = [f"OBJET : {t.objet}", f"ACHETEUR : {t.acheteur or 'non précisé'}",
             f"LIEU/DÉPARTEMENTS : {', '.join(t.departements) or 'non précisé'}",
             f"DESCRIPTEURS : {', '.join(t.cpv) or 'non précisé'}",
             f"PROCÉDURE : {t.procedure or 'non précisée'}",
             f"DATE LIMITE : {t.date_limite or 'non précisée'}",
             f"SOURCE : {t.provenance.source} ({t.provenance.source_url})",
             "", "(DCE complet non accessible — analyse fondée sur l'avis publié.)"]
    return "\n".join(parts)
