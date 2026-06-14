"""
Adjugo - Checklist intelligente
Compare les pieces requises (extraites par l'IA) avec les documents du coffre-fort.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User, Project, Document

router = APIRouter(prefix="/api/checklist", tags=["Checklist intelligente"])

# Pieces standards des marches publics
PIECES_STANDARD = [
    {"id": "kbis", "name": "Extrait Kbis ou equivalent", "category": "administratif", "required": True},
    {"id": "dc1", "name": "DC1 - Lettre de candidature", "category": "cerfa", "required": True},
    {"id": "dc2", "name": "DC2 - Declaration du candidat", "category": "cerfa", "required": True},
    {"id": "attri1", "name": "ATTRI1 - Acte d'engagement", "category": "cerfa", "required": True},
    {"id": "attestation_fiscale", "name": "Attestation de regularite fiscale", "category": "fiscal", "required": True},
    {"id": "attestation_sociale", "name": "Attestation de regularite sociale (URSSAF)", "category": "fiscal", "required": True},
    {"id": "rc_pro", "name": "Attestation d'assurance RC professionnelle", "category": "assurances", "required": True},
    {"id": "rc_decennale", "name": "Attestation d'assurance decennale", "category": "assurances", "required": False},
    {"id": "certif_qualibat", "name": "Certificat Qualibat / qualification", "category": "qualifications", "required": False},
    {"id": "references", "name": "Liste des references / travaux similaires", "category": "administratif", "required": True},
    {"id": "moyens_humains", "name": "Declaration des moyens humains", "category": "administratif", "required": False},
    {"id": "moyens_techniques", "name": "Declaration des moyens techniques", "category": "administratif", "required": False},
    {"id": "rib", "name": "Releve d'identite bancaire (RIB)", "category": "administratif", "required": True},
    {"id": "pouvoir", "name": "Pouvoir du signataire", "category": "administratif", "required": False},
    {"id": "dc4", "name": "DC4 - Declaration de sous-traitance", "category": "cerfa", "required": False},
    {"id": "memoire_technique", "name": "Memoire technique", "category": "technique", "required": True},
    {"id": "dpgf", "name": "DPGF / Bordereau des prix", "category": "technique", "required": True},
    {"id": "planning", "name": "Planning previsionnel", "category": "technique", "required": False},
]


def match_document(piece_name, documents):
    """Verifie si un document du coffre-fort correspond a la piece demandee."""
    piece_lower = piece_name.lower()
    keywords = {
        "kbis": ["kbis", "extrait k", "registre commerce"],
        "dc1": ["dc1", "lettre de candidature"],
        "dc2": ["dc2", "declaration du candidat"],
        "dc4": ["dc4", "sous-traitance"],
        "attri1": ["attri1", "acte d'engagement", "acte engagement"],
        "attestation_fiscale": ["fiscal", "impot", "dgfip", "regularite fiscale"],
        "attestation_sociale": ["urssaf", "social", "cotisation", "regularite sociale"],
        "rc_pro": ["rc pro", "responsabilite civile", "assurance pro"],
        "rc_decennale": ["decennale", "garantie decennale"],
        "certif_qualibat": ["qualibat", "qualification", "certification", "qualif"],
        "references": ["reference", "travaux similaires", "experience"],
        "moyens_humains": ["moyens humains", "effectif", "personnel", "organigramme"],
        "moyens_techniques": ["moyens techniques", "materiel", "equipement"],
        "rib": ["rib", "bancaire", "iban", "identite bancaire"],
        "pouvoir": ["pouvoir", "habilitation", "delegation"],
        "memoire_technique": ["memoire technique", "offre technique", "methodologie"],
        "dpgf": ["dpgf", "bordereau", "prix unitaire", "decomposition"],
        "planning": ["planning", "calendrier", "delai", "gantt"],
    }

    for doc in documents:
        doc_name = (doc.name or "").lower()
        doc_cat = (doc.category or "").lower()

        # Chercher par mots-cles
        for key, terms in keywords.items():
            if key in piece_lower or any(t in piece_lower for t in terms):
                if any(t in doc_name or t in doc_cat for t in terms):
                    return {
                        "found": True,
                        "document_id": doc.id,
                        "document_name": doc.name,
                        "expired": hasattr(doc, 'days_until_expiration') and doc.days_until_expiration is not None and doc.days_until_expiration < 0,
                    }

    return {"found": False}


@router.get("/{project_id}")
def get_checklist(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(
        Project.id == project_id, Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(404, "Projet introuvable")

    # Recuperer les documents du coffre-fort
    documents = db.query(Document).filter(
        Document.user_id == current_user.id
    ).all()

    # Construire la checklist
    checklist = []

    # Pieces extraites par l'IA (si analyse faite)
    ai_pieces = []
    if project.ai_analysis and isinstance(project.ai_analysis, dict):
        ai_pieces = project.ai_analysis.get("pieces_requises", [])

    # Combiner pieces standard + pieces IA
    seen_ids = set()
    all_pieces = list(PIECES_STANDARD)

    # Ajouter les pieces IA qui ne sont pas dans la liste standard
    for ap in ai_pieces:
        name = ap if isinstance(ap, str) else ap.get("nom", "")
        if name and not any(name.lower() in p["name"].lower() for p in all_pieces):
            all_pieces.append({
                "id": "ia_" + str(len(all_pieces)),
                "name": name,
                "category": "ia",
                "required": True,
                "from_ia": True,
            })

    for piece in all_pieces:
        match = match_document(piece["name"], documents)
        item = {
            "id": piece["id"],
            "name": piece["name"],
            "category": piece.get("category", "autre"),
            "required": piece.get("required", False),
            "from_ia": piece.get("from_ia", False),
            "status": "ok" if match["found"] else "manquant",
            "document_name": match.get("document_name"),
            "document_id": match.get("document_id"),
            "expired": match.get("expired", False),
        }

        if item["expired"]:
            item["status"] = "expire"

        # Les CERFA sont toujours "ok" car generables
        if piece["category"] == "cerfa":
            item["status"] = "generable"

        checklist.append(item)

    # Stats
    total = len(checklist)
    ok = len([c for c in checklist if c["status"] in ("ok", "generable")])
    manquant = len([c for c in checklist if c["status"] == "manquant"])
    expire = len([c for c in checklist if c["status"] == "expire"])

    return {
        "project_id": project_id,
        "project_name": project.name,
        "checklist": checklist,
        "stats": {
            "total": total,
            "ok": ok,
            "manquant": manquant,
            "expire": expire,
            "completion": round(ok / total * 100) if total > 0 else 0,
        }
    }
