"""
Adjugo - Router d'analyse IA des DCE
Passe le profil entreprise et les criteres Go/No-Go a l'IA.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.ratelimit import limiter
from app.core.security import get_current_user
from app.core.org import data_owner_id
from app.models import User, Project, Company
from app.services.analysis import analyze_dce

router = APIRouter(prefix="/api/analysis", tags=["Analyse IA"])


@router.post("/{project_id}")
@limiter.limit("30/hour")
async def run_analysis(
    request: Request,
    project_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(
        Project.id == project_id, Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(404, "Projet introuvable")

    # Lire le fichier
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(400, "Fichier vide")
    if len(file_bytes) > 50 * 1024 * 1024:
        raise HTTPException(400, "Fichier trop volumineux (50 Mo max)")

    # Vérifier le quota d'analyses du plan (402 si atteint)
    from app.core.quota import consume_analysis
    consume_analysis(current_user, db)

    # Charger le profil entreprise
    company = db.query(Company).filter(Company.user_id == data_owner_id(current_user, db)).first()
    company_data = None
    if company:
        company_data = {}
        for k in ["name", "siret", "code_ape", "forme_juridique",
                   "representant_legal", "address", "city", "postal_code",
                   "ca_n1", "ca_n2", "ca_n3", "effectif"]:
            company_data[k] = getattr(company, k, "") or ""

    # Charger les criteres Go/No-Go
    criteria_data = None
    try:
        from app.models import MatchingCriteria
        criteria = db.query(MatchingCriteria).filter(
            MatchingCriteria.user_id == current_user.id
        ).first()
        if criteria:
            criteria_data = {}
            for k in ["budget_min", "budget_max", "max_distance_km",
                       "penalty_max", "go_threshold", "nogo_threshold",
                       "excluded_keywords"]:
                criteria_data[k] = getattr(criteria, k, None)
    except Exception:
        pass

    # Lancer l'analyse (tokens IA attribués au tenant → plafond par client)
    from app.services.llm import tenant_scope
    with tenant_scope(current_user.id):
        result = analyze_dce(file_bytes, company_data, criteria_data)

    # Sauvegarder les resultats dans le projet
    project.match_score = result.get("match_score", 0)
    project.go_decision = result.get("go_decision", "a_etudier")
    project.ai_summary = result.get("summary", "")
    project.ai_analysis = result.get("details", {})

    if not project.status or project.status == "nouveau":
        project.status = "en_cours"

    db.commit()

    return result
