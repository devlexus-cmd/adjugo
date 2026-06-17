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

# Pieces standards des marches publics.
# `help` = comment l'obtenir (passe d'« assistant » à « accompagnement »).
# `help_url` = source officielle. `required` peut être réévalué selon le marché
# (travaux → décennale, groupement → pouvoir) dans get_checklist().
PIECES_STANDARD = [
    {"id": "kbis", "name": "Extrait Kbis ou equivalent", "category": "administratif", "required": True,
     "help": "Extrait de moins de 3 mois : à commander en ligne sur MonIdenum ou Infogreffe.",
     "help_url": "https://www.infogreffe.fr/"},
    {"id": "dc1", "name": "DC1 - Lettre de candidature", "category": "cerfa", "required": True,
     "help": "Généré automatiquement par Adjugo, pré-rempli avec votre profil. À dater et signer."},
    {"id": "dc2", "name": "DC2 - Declaration du candidat", "category": "cerfa", "required": True,
     "help": "Généré automatiquement par Adjugo (CA, références, qualifications). À vérifier et signer."},
    {"id": "honneur", "name": "Declaration sur l'honneur (R2143-3)", "category": "cerfa", "required": True,
     "help": "Généré automatiquement par Adjugo. Pièce OBLIGATOIRE : son absence invalide le pli. À dater et signer."},
    {"id": "attri1", "name": "ATTRI1 - Acte d'engagement", "category": "cerfa", "required": True,
     "help": "Généré automatiquement par Adjugo à partir du chiffrage. Vérifiez le taux de TVA et le montant avant signature."},
    {"id": "attestation_fiscale", "name": "Attestation de regularite fiscale", "category": "fiscal", "required": True,
     "help": "À télécharger sur votre espace professionnel impots.gouv.fr (rubrique « Attestation fiscale »).",
     "help_url": "https://www.impots.gouv.fr/"},
    {"id": "attestation_sociale", "name": "Attestation de regularite sociale (URSSAF)", "category": "fiscal", "required": True,
     "help": "Attestation de vigilance à télécharger sur votre compte urssaf.fr (valable 6 mois).",
     "help_url": "https://www.urssaf.fr/"},
    {"id": "rc_pro", "name": "Attestation d'assurance RC professionnelle", "category": "assurances", "required": True,
     "help": "À demander à votre assureur (attestation de l'année en cours mentionnant l'activité)."},
    {"id": "rc_decennale", "name": "Attestation d'assurance decennale", "category": "assurances", "required": False,
     "help": "Obligatoire sur les marchés de TRAVAUX (bâtiment). À demander à votre assureur décennale."},
    {"id": "certif_qualibat", "name": "Certificat Qualibat / qualification", "category": "qualifications", "required": False,
     "help": "Certificat en cours de validité délivré par Qualibat/Qualifelec selon votre métier.",
     "help_url": "https://www.qualibat.com/"},
    {"id": "references", "name": "Liste des references / travaux similaires", "category": "administratif", "required": True,
     "help": "Renseignez vos références dans votre profil Adjugo : elles alimentent le mémoire et le DC2."},
    {"id": "moyens_humains", "name": "Declaration des moyens humains", "category": "administratif", "required": False,
     "help": "Effectif, organigramme, CV des intervenants clés — souvent demandé au mémoire technique."},
    {"id": "moyens_techniques", "name": "Declaration des moyens techniques", "category": "administratif", "required": False,
     "help": "Matériel, équipements, moyens logistiques — à détailler dans le mémoire technique."},
    {"id": "rib", "name": "Releve d'identite bancaire (RIB)", "category": "administratif", "required": True,
     "help": "RIB au nom de l'entreprise, à télécharger depuis votre banque en ligne."},
    {"id": "pouvoir", "name": "Pouvoir du signataire", "category": "administratif", "required": False,
     "help": "Délégation de pouvoir si le signataire n'est pas le représentant légal. OBLIGATOIRE pour le mandataire d'un groupement."},
    {"id": "dc4", "name": "DC4 - Declaration de sous-traitance", "category": "cerfa", "required": False,
     "help": "Généré par Adjugo si vous déclarez un sous-traitant. À compléter avec sa part du marché."},
    {"id": "memoire_technique", "name": "Memoire technique", "category": "technique", "required": True,
     "help": "Généré par Adjugo à partir de l'analyse du DCE. À personnaliser : c'est lui qui fait la note technique."},
    {"id": "dpgf", "name": "DPGF / Bordereau des prix", "category": "technique", "required": True,
     "help": "Générée par Adjugo depuis le chiffrage. Reprenez la trame de l'acheteur si elle est imposée dans le DCE."},
    {"id": "planning", "name": "Planning previsionnel", "category": "technique", "required": False,
     "help": "Calendrier d'exécution (Gantt). Demandé sur les marchés de travaux et certaines prestations."},
]

# Mots-clés détectant un marché de TRAVAUX (→ décennale + planning obligatoires).
_TRAVAUX_KW = ("travaux", "batiment", "bâtiment", "construction", "rénovation", "renovation",
               "réhabilitation", "rehabilitation", "voirie", "vrd", "btp", "chantier",
               "maçonnerie", "maconnerie", "gros œuvre", "gros oeuvre", "couverture",
               "charpente", "menuiserie", "génie civil", "genie civil", "démolition",
               "demolition", "terrassement", "isolation", "toiture", "plomberie", "électricité")


def _is_travaux(project) -> bool:
    """Heuristique : le marché relève-t-il des travaux ? (intitulé + analyse IA)."""
    hay = (project.name or "").lower()
    a = project.ai_analysis if isinstance(project.ai_analysis, dict) else {}
    det = a.get("details", {}) if isinstance(a.get("details"), dict) else {}
    hay += " " + " ".join(str(det.get(k, "")) for k in ("intitule_marche", "objet", "domaine"))
    hay += " " + str(a.get("domaine", "")) + " " + str(a.get("secteur", ""))
    hay = hay.lower()
    return any(kw in hay for kw in _TRAVAUX_KW)


def _is_groupement(project, db) -> bool:
    """Le marché est-il porté en groupement ? (au moins un partenaire invité)."""
    try:
        from app.models import ProjectInvite
        return db.query(ProjectInvite).filter(
            ProjectInvite.project_id == project.id,
            ProjectInvite.revoked.is_(False)).count() > 0
    except Exception:
        return False


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

    # Contexte du marché : réévalue les pièces « conditionnelles » en obligatoires.
    is_travaux = _is_travaux(project)
    is_groupement = _is_groupement(project, db)
    contextual = {}
    if is_travaux:
        contextual["rc_decennale"] = "Marché de travaux : assurance décennale obligatoire."
        contextual["planning"] = "Marché de travaux : planning d'exécution généralement exigé."
    if is_groupement:
        contextual["pouvoir"] = "Groupement : pouvoir / habilitation du mandataire obligatoire."
        contextual["dc4"] = "Groupement avec sous-traitance : DC4 à prévoir le cas échéant."
    # DPGF/BPU imposé par l'acheteur : si une trame figure dans les pièces requises du DCE,
    # il faut la compléter telle quelle — le modèle Adjugo ne sert alors que de chiffrage.
    _pieces_txt = " ".join(
        (ap if isinstance(ap, str) else ap.get("nom", "")) for ap in ai_pieces).lower()
    if any(k in _pieces_txt for k in ("dpgf", "bordereau", "bpu", "décomposition", "decomposition")):
        contextual["dpgf"] = ("Trame DPGF/BPU imposée par l'acheteur (détectée dans le DCE) : "
                              "téléchargez-la et complétez-la — n'envoyez pas le modèle Adjugo seul.")

    # Combiner pieces standard + pieces IA
    seen_ids = set()
    all_pieces = [dict(p) for p in PIECES_STANDARD]
    for p in all_pieces:
        if p["id"] in contextual:
            p["required"] = True
            p["context_note"] = contextual[p["id"]]

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
            "help": piece.get("help"),
            "help_url": piece.get("help_url"),
            "context_note": piece.get("context_note"),
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
        "context": {"travaux": is_travaux, "groupement": is_groupement},
        "checklist": checklist,
        "stats": {
            "total": total,
            "ok": ok,
            "manquant": manquant,
            "expire": expire,
            "completion": round(ok / total * 100) if total > 0 else 0,
        }
    }
