"""
Pipeline de sourcing À LA DEMANDE (anti-hallucination, validation à chaque étape).
Aucune étape ne s'auto-exécute : l'utilisateur déclenche chaque action.

  1. POST /api/sourcing/search       — recherche AO multi-sources (sans LLM, gratuit)
  2. POST /api/sourcing/analyze      — analyse profonde d'UN AO choisi (LLM, quota)
  3. POST /api/sourcing/cotraitants  — sourcing co-traitants réels (sans LLM)
  4. POST /api/sourcing/documents    — génération du dossier (LLM, sur les choisis)
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field as PydField

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ratelimit import limiter
from app.models import User, Company, Project
from app.sourcing.base import TenderCriteria
from app.sourcing.sources.boamp import BoampSource
from app.sourcing.sources.ted import TedSource
from app.sourcing.sources.sirene import SireneSource
from app.sourcing.sources.bodacc import BodaccSource
from app.sourcing.sources.buyer import BuyerProfileSource
from app.sourcing.search import TenderSearchService, CompanySearchService
from app.sourcing.schemas import NormalizedTender
from app.services.profile import company_dict as _company_dict, criteria_dict as _criteria_dict

logger = logging.getLogger("adjugo")
router = APIRouter(prefix="/api/sourcing", tags=["Sourcing (sources officielles)"])

# Sources AO actives : BOAMP (national FR) + TED (européen, tous pays UE/EEE).
# DECP = marchés attribués → réservé à l'« intelligence marché », pas au feed d'AO ouverts.
TENDER_SOURCES = [BoampSource(), TedSource()]
COMPANY_SOURCES = [SireneSource()]


def _tender_sources(countries: list) -> list:
    """Sources à interroger selon les pays demandés. BOAMP (national FR) n'est
    pertinent que pour la France ; TED couvre tous les pays UE/EEE."""
    cc = [str(c).upper() for c in (countries or [])]
    fr_inclus = (not cc) or ("FR" in cc)
    sources = []
    if fr_inclus:
        sources.append(BoampSource())
    sources.append(TedSource())
    return sources
# Red-flag financier (procédure collective) — enrichissement parallèle, jamais bloquant.
RED_FLAG_SOURCE = BodaccSource()
BUYER_SOURCE = BuyerProfileSource()


def _company_service() -> CompanySearchService:
    return CompanySearchService(COMPANY_SOURCES, red_flag_source=RED_FLAG_SOURCE)


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
                                       Project.user_id == current_user.id,
                                       Project.deleted_at.is_(None)).first()
    if not project or not project.ai_analysis:
        raise HTTPException(404, "Projet ou analyse introuvable")

    details = (project.ai_analysis or {}).get("details", {})
    company = db.query(Company).filter(Company.user_id == current_user.id).first()
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
    limit: int = 20
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
    company = db.query(Company).filter(Company.user_id == current_user.id).first()
    company_data = _company_dict(company)
    gonogo = _criteria_dict(current_user.id, db)
    crit = TenderCriteria(query=req.query, cpv=req.cpv, departements=req.departements,
                          montant_min=req.montant_min, montant_max=req.montant_max,
                          limit=req.limit, countries=req.countries, type_marche=req.type_marche)
    result = TenderSearchService(_tender_sources(req.countries)).search(crit, company_data, gonogo)
    return {
        "count": result["count"],
        "sources_queried": result["sources_queried"],
        "errors": [e.model_dump() for e in result["errors"]],
        "tenders": [t.model_dump(exclude={"raw"}) for t in result["tenders"]],
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
    se positionner auprès de l'acheteur avant la republication. Dates estimées, sources réelles."""
    from app.core.quota import consume_analysis, refund_analysis
    from app.services.renewal import detect_renewals
    gonogo = _criteria_dict(current_user.id, db)
    deps = [d.strip()[:3] for d in (req.departements or []) if d.strip()]
    consume_analysis(current_user, db)
    from app.services.llm import tenant_scope
    try:
        with tenant_scope(current_user.id):
            res = detect_renewals(req.query or "travaux", deps, gonogo, domaines=req.domaines)
    except Exception:
        refund_analysis(current_user, db)   # rien produit → on ne débite pas
        raise
    if res.get("errors") and not res.get("renewals"):
        refund_analysis(current_user, db)   # source en panne → remboursement
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

    consume_analysis(current_user, db)  # 402 si quota atteint

    company = db.query(Company).filter(Company.user_id == current_user.id).first()
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
    analysis["source"] = tender.provenance.model_dump()
    analysis["lead_score"] = tender.score.model_dump() if tender.score else None

    # Le SCORE Go/No-Go n'est posé QU'À PARTIR D'UN VRAI DCE analysé : sur un avis
    # seul, scorer ne vaut rien. L'analyse reste préliminaire (pas de score/décision)
    # ; le score apparaît après import du DCE réel via /analyze-upload.
    if dce_available:
        score = analysis.get("match_score", 0)
        go_t = (gonogo or {}).get("go_threshold") or 65
        nogo_t = (gonogo or {}).get("nogo_threshold") or 40
        decision = "go" if score >= go_t else ("no_go" if score < nogo_t else "a_etudier")
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
        source_url=tender.provenance.source_url,
    )
    db.add(project); db.commit(); db.refresh(project)

    return {
        "project_id": project.id, "decision": decision, "score": score,
        "dce_available": dce_available,
        "confidence": tender.confidence,
        "summary": analysis.get("summary", ""),
        "details": analysis.get("details", {}),
        "source": tender.provenance.model_dump(),
    }


# ── Étape 2 bis : analyse du DCE RÉEL importé (PDF/ZIP) ──────────────────────────

@router.post("/analyze-upload")
@limiter.limit("30/hour")
async def analyze_upload(request: Request, file: UploadFile = File(...),
                         project_id: int = Form(...),
                         current_user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    from app.core.quota import consume_analysis
    from app.services.analysis import analyze_dce_text, extract_dce_text

    project = db.query(Project).filter(Project.id == project_id,
                                       Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(404, "Projet introuvable — analysez d'abord l'avis.")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, "Fichier vide.")
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(413, "Fichier trop volumineux (50 Mo max).")

    # Extraction du DCE réel — message clair si illisible/format non supporté
    try:
        dce_text = extract_dce_text(file.filename, content)
    except ValueError as e:
        raise HTTPException(422, str(e))

    consume_analysis(current_user, db)  # 402 si quota atteint

    company = db.query(Company).filter(Company.user_id == current_user.id).first()
    company_data = _company_dict(company)
    gonogo = _criteria_dict(current_user.id, db)

    from app.services.llm import tenant_scope
    with tenant_scope(current_user.id):
        analysis = analyze_dce_text(dce_text, company_data, gonogo,
                                    lang_name=_user_lang_name(current_user, db))
    analysis["dce_available"] = True
    analysis["dce_excerpt"] = (dce_text or "")[:14000]   # contexte pour le Q&A IA
    prev = project.ai_analysis or {}
    analysis["source"] = prev.get("source") or {}
    analysis["lead_score"] = prev.get("lead_score")

    score = analysis.get("match_score", 0)
    go_t = (gonogo or {}).get("go_threshold") or 65
    nogo_t = (gonogo or {}).get("nogo_threshold") or 40
    decision = "go" if score >= go_t else ("no_go" if score < nogo_t else "a_etudier")
    analysis["go_decision"] = decision

    project.match_score = score
    project.go_decision = decision
    project.ai_summary = analysis.get("summary", "")
    project.ai_analysis = analysis
    intitule = analysis.get("details", {}).get("intitule_marche")
    if intitule:
        project.name = intitule[:500]
    db.commit()

    # Archiver le DCE importé dans le dossier de l'AO (coffre-fort, dossier "DCE")
    try:
        from app.services.dossier import save_to_dossier
        save_to_dossier(db, current_user.id, project.id, "DCE",
                        file.filename or "DCE.pdf", content, file.content_type or "application/pdf")
    except Exception:
        pass

    return {
        "project_id": project.id, "decision": decision, "score": score,
        "dce_available": True,
        "summary": analysis.get("summary", ""),
        "details": analysis.get("details", {}),
        "source": analysis["source"],
    }


# ── Q&A IA sur un AO (après import du DCE réel) ──────────────────────────────────

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


@router.post("/ask")
@limiter.limit("90/hour")
def ask_ao(request: Request, req: AskRequest,
           current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.llm import complete, MODEL_FAST
    project = db.query(Project).filter(Project.id == req.project_id,
                                       Project.user_id == current_user.id).first()
    if not project or not project.ai_analysis:
        raise HTTPException(404, "Projet ou analyse introuvable")
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(400, "Question vide")
    a = project.ai_analysis or {}
    ctx = a.get("dce_excerpt") or ""
    if not ctx:
        import json as _json
        ctx = (a.get("summary", "") + "\n\nDÉTAILS:\n"
               + _json.dumps(a.get("details", {}), ensure_ascii=False))
    lang = _user_lang_name(current_user, db)
    user = (f"DCE de l'appel d'offres « {project.name} » (acheteur : {project.client or 'n/d'}) :\n"
            f"\"\"\"\n{ctx[:14000]}\n\"\"\"\n\nQUESTION : {q}\n\n"
            f"Réponds en {lang}, fondé uniquement sur le DCE ci-dessus.")
    try:
        from app.services.llm import tenant_scope, LLMUnavailable
        with tenant_scope(current_user.id):
            answer = complete(ASK_SYSTEM, user, max_tokens=700, temperature=0.1, model=MODEL_FAST)
    except LLMUnavailable as e:
        # Dégradation gracieuse : service IA saturé/en pause → 503 RETRYABLE (Retry-After).
        raise HTTPException(503, str(e), headers={"Retry-After": "30"})
    except Exception as e:
        raise HTTPException(502, f"IA momentanément indisponible : {e}")
    return {"answer": (answer or "").strip() or "—"}


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
                                       Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(404, "Projet introuvable")
    deps = [req.departement] if req.departement else []
    res = _company_service().discover(
        activity=req.activity, departement=req.departement, query=req.query,
        tender_departements=deps, need_label=req.activity)
    # Complementarity Graph : score de SYNERGIE vs l'entreprise pilote (ce que le
    # candidat APPORTE au groupement). On trie les partenaires par synergie décroissante.
    from app.sourcing.scoring import synergy_score
    lead = db.query(Company).filter(Company.user_id == current_user.id).first()
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


@router.post("/documents")
@limiter.limit("20/hour")
def generate_documents(request: Request, req: DocumentsRequest,
                       current_user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    from app.services.agents import redaction

    project = db.query(Project).filter(Project.id == req.project_id,
                                       Project.user_id == current_user.id).first()
    if not project or not project.ai_analysis:
        raise HTTPException(404, "Projet ou analyse introuvable")

    company = db.query(Company).filter(Company.user_id == current_user.id).first()
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

    from app.services.llm import tenant_scope
    with tenant_scope(current_user.id):
        dossier = redaction.build_dossier(project.ai_analysis, company_data, verified, project.id,
                                          lang_name=_user_lang_name(current_user, db),
                                          country=_user_country(current_user, db),
                                          db=db, user_id=current_user.id, estimate=project.estimate)

    # Archiver les CERFA + mémoire dans le dossier de l'AO (coffre-fort)
    try:
        import base64
        from app.services.dossier import replace_in_dossier
        for c in dossier.get("cerfas", []):
            replace_in_dossier(db, current_user.id, project.id, "CERFA",
                               c["name"], base64.b64decode(c["content_b64"]), "application/pdf")
        memo = dossier.get("memoire_markdown")
        if memo:
            replace_in_dossier(db, current_user.id, project.id, "Mémoire technique",
                               "memoire_technique.md", memo.encode("utf-8"), "text/markdown")
    except Exception:
        pass

    return {
        "cotraitants_verifies": len(verified),
        "cotraitants_rejetes": (len(req.cotraitants) - len(verified)) if req.cotraitants else 0,
        "dossier": dossier,
    }


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
