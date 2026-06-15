"""
Compte de DÉMONSTRATION — pré-rempli pour montrer TOUTE la valeur d'Adjugo sans inscription.

ensure_demo(db) crée (si absent) demo@adjugo.fr : une entreprise BTP réaliste, des critères,
3 appels d'offres COMPLÈTEMENT analysés (Go/No-Go déterministe via score_dce — aucun appel
LLM), avec détail du score, clauses à risque, pièces requises, source BOAMP, et un réseau de
co-traitants rattachés (dont un désamianteur sur le marché « à étudier » pour illustrer le
groupement). Idempotent ; force=True réinitialise.

Branché au démarrage (main.py) et accessible via /api/auth/demo (connexion sans mot de passe).
"""
import logging

from app.core.security import hash_password
from app.models import (Company, MatchingCriteria, Organization, PlanType,
                        Project, ProjectStatus, User)
from app.routers.cotraitants import Cotraitant, ProjectCotraitant
from app.services.agents.chiffrage import compute_estimate
from app.services.dce_scoring import score_dce

_DAY_RATES = [
    {"label": "Étude / conception", "rate": 650},
    {"label": "Encadrement / direction", "rate": 850},
    {"label": "Exécution / terrain", "rate": 400},
]
# Estimation pré-calculée (déterministe) pour l'AO toiture — vitrine du chiffrage.
_TOITURE_TASKS = [
    {"phase": "Préparation", "tache": "Installation de chantier, sécurité et protections", "profil": "Exécution / terrain", "jours": 4},
    {"phase": "Étude", "tache": "Relevés, calepinage et plans d'exécution étanchéité", "profil": "Étude / conception", "jours": 5},
    {"phase": "Production", "tache": "Dépose de la couverture existante et évacuation", "profil": "Exécution / terrain", "jours": 12},
    {"phase": "Production", "tache": "Pose de l'isolation thermique et de la membrane d'étanchéité", "profil": "Exécution / terrain", "jours": 22},
    {"phase": "Production", "tache": "Zinguerie, relevés et évacuations des eaux pluviales", "profil": "Exécution / terrain", "jours": 8},
    {"phase": "Contrôle", "tache": "Tests d'étanchéité, levée de réserves et réception", "profil": "Étude / conception", "jours": 4},
    {"phase": "Pilotage", "tache": "Encadrement, coordination et suivi de chantier", "profil": "Encadrement / direction", "jours": 10},
]

logger = logging.getLogger("adjugo")

DEMO_EMAIL = "demo@adjugo.fr"
DEMO_PASSWORD = "demo1234"

_COMPANY = {
    "name": "Bâtiment de l'Ouest", "ca_n1": 1250000, "postal_code": "29000",
    "qualifications": [
        {"name": "Qualibat 3212", "detail": "étanchéité de toiture par éléments"},
        {"name": "RGE", "detail": "reconnu garant de l'environnement"},
    ],
}
_CRITERIA = {
    "specialites": "toiture, étanchéité, gros œuvre, isolation, charpente, couverture",
    "departements": ["29", "56", "22"], "budget_min": 50000, "budget_max": 2000000, "go_threshold": 75,
}


def _analysis(details, summary, ref, pieces):
    """Reconstitue la sortie complète d'analyze_dce_text (barème déterministe, sans LLM)."""
    det = score_dce(details, _COMPANY, _CRITERIA)
    return {
        "match_score": det["score"], "go_decision": det["go_decision"], "summary": summary,
        "details": details, "score_breakdown": det["breakdown"],
        "lead_score": {"total": det["score"], "breakdown": det["breakdown"], "note": summary[:140]},
        "source": {"source": "BOAMP", "official_ref": ref, "source_url": "https://www.boamp.fr"},
        "pieces_requises": pieces, "dce_available": True, "score_deterministe": True,
    }


def _projects():
    P = []

    # 1) GO — toiture groupe scolaire
    d1 = {
        "intitule_marche": "Réfection de la toiture et étanchéité du groupe scolaire Jean Moulin",
        "acheteur": "Ville de Quimper",
        "contact": {"nom": "Marie Le Goff", "fonction": "Service de la commande publique", "email": "marches@mairie-quimper.fr", "telephone": "02 98 98 89 89"},
        "type_marche": "Travaux",
        "nature_marche": "Marché à procédure adaptée (MAPA)", "forme_prix": "Prix global et forfaitaire",
        "budget_estime": "480 000 EUR HT", "date_limite": "30/12/2026 à 12h00",
        "delai_execution": "5 mois à compter de l'ordre de service", "lieu_execution": "Quimper (29)",
        "allotissement": "Lot unique",
        "criteres_attribution": [{"critere": "Valeur technique", "ponderation": "60%"}, {"critere": "Prix", "ponderation": "40%"}],
        "garanties_exigees": "Retenue de garantie 5%", "penalites": "1/1000 du montant HT par jour, plafonnées à 10%",
        "avance": "Avance de 10% (marché > 50 000 EUR HT)", "sous_traitance": "Autorisée — déclaration DC4 requise",
        "variantes": "Autorisées sur les matériaux d'étanchéité", "critere_rse": "Oui — clause d'insertion sociale (200 h)",
        "ca_minimum_requis": "CA > 1 500 000 EUR sur 3 ans", "qualifications_requises": ["Qualibat 3212", "RGE"],
        "assurances_requises": ["RC Professionnelle", "Garantie décennale"],
        "visite_obligatoire": "Recommandée, sur rendez-vous avant le 15/12/2026",
        "points_attention": ["Critère technique prépondérant (60%) — soigner le mémoire", "Exigence de CA (1,5 M€) au-dessus de votre CA N-1 — à surveiller", "Clause d'insertion sociale de 200 h"],
        "recommandation": "Très bonne cible : métier, zone et qualifications alignés. La valeur technique pèse 60% — investir le mémoire (méthodologie d'étanchéité, gestion du site occupé). Proposer une caution en substitution de la retenue de garantie et mobiliser une structure d'insertion locale pour la clause sociale.",
        "clauses_risque": [
            {"clause": "Retenue de garantie", "niveau": "moyen", "pourquoi": "5% retenus pendant 1 an, immobilise la trésorerie", "levier_negociation": "Caution bancaire de substitution (art. R2191-33)"},
            {"clause": "Pénalités de retard", "niveau": "moyen", "pourquoi": "1/1000 du HT par jour, plafond 10%", "levier_negociation": "Demander une franchise de 5 jours ouvrés et un plafond à 5%"},
            {"clause": "Clause d'insertion sociale", "niveau": "faible", "pourquoi": "200 h d'insertion à réaliser sur le chantier", "levier_negociation": "Conventionner une structure d'insertion locale (facilité opérationnelle)"},
        ],
    }
    P.append(dict(key="toiture", name="Réfection toiture — Groupe scolaire Jean Moulin", client="Ville de Quimper",
                  budget=480000, status=ProjectStatus.en_cours,
                  ai=_analysis(d1, "Réfection de toiture d'un groupe scolaire à Quimper — travaux en lot unique, 480 k€, valeur technique prépondérante (60%). Métier, zone et qualifications alignés : cible prioritaire.", "25-114207",
                               ["Certificat Qualibat 3212 (en cours de validité)", "Attestation RGE", "Mémoire technique — méthodologie étanchéité", "3 références de toitures scolaires (< 3 ans)", "Attestation d'assurance décennale"])))

    # 2) À ÉTUDIER — réhabilitation énergétique + désamiantage (groupement)
    d2 = {
        "intitule_marche": "Réhabilitation énergétique et désamiantage du gymnase municipal",
        "acheteur": "Lorient Agglomération", "type_marche": "Travaux",
        "nature_marche": "Appel d'offres ouvert", "forme_prix": "Prix global et forfaitaire",
        "budget_estime": "1 250 000 EUR HT", "date_limite": "20/12/2026 à 17h00",
        "delai_execution": "9 mois", "lieu_execution": "Lorient (56)",
        "allotissement": "Lot 1 : Désamiantage et retrait d'amiante ; Lot 2 : Isolation thermique et rénovation énergétique ; Lot 3 : Gros œuvre et étanchéité",
        "criteres_attribution": [{"critere": "Prix", "ponderation": "50%"}, {"critere": "Valeur technique", "ponderation": "50%"}],
        "garanties_exigees": "Retenue de garantie 5% + garantie à première demande", "penalites": "1/1000 du HT par jour",
        "sous_traitance": "Autorisée", "variantes": "Non autorisées", "critere_rse": "Oui — bilan carbone exigé",
        "ca_minimum_requis": "CA > 3 000 000 EUR sur 3 ans", "qualifications_requises": ["Qualification désamiantage SS3", "Certification amiante sous-section 3"],
        "assurances_requises": ["RC Professionnelle", "Garantie décennale", "Assurance amiante"],
        "visite_obligatoire": "Obligatoire — 05/12/2026 à 14h",
        "points_attention": ["Désamiantage : qualification SS3 exigée (non détenue)", "CA minimum exigé (3 M€) supérieur à votre CA", "Garantie à première demande"],
        "recommandation": "Marché en zone et dans votre cœur de métier (rénovation énergétique), mais deux verrous : la qualification désamiantage SS3 et l'exigence de CA. La bonne stratégie est un GROUPEMENT avec un désamianteur qualifié — qui mutualise aussi les CA. Adjugo a identifié un partenaire complémentaire (voir co-traitance).",
        "clauses_risque": [
            {"clause": "Capacité financière", "niveau": "eleve", "pourquoi": "CA exigé 3 M€ supérieur à votre CA N-1", "levier_negociation": "Répondre en groupement conjoint pour cumuler les chiffres d'affaires"},
            {"clause": "Garantie à première demande", "niveau": "eleve", "pourquoi": "Engage la trésorerie sans recours, appelable sans justification", "levier_negociation": "Proposer une caution bancaire classique en substitution"},
            {"clause": "Qualification désamiantage SS3", "niveau": "eleve", "pourquoi": "Non détenue en interne", "levier_negociation": "Co-traitance avec un désamianteur certifié SS3"},
        ],
    }
    P.append(dict(key="lorient", name="Réhabilitation énergétique — Gymnase de Lorient", client="Lorient Agglomération",
                  budget=1250000, status=ProjectStatus.nouveau,
                  ai=_analysis(d2, "Réhabilitation énergétique d'un gymnase à Lorient — 1,25 M€. En zone et dans votre métier, mais qualification désamiantage SS3 non détenue et CA exigé élevé : candidature en GROUPEMENT à étudier.", "25-118934",
                               ["Qualification désamiantage SS3 (ou co-traitant)", "Bilan carbone de l'entreprise", "Garantie à première demande", "Plan de retrait amiante", "Attestation de visite obligatoire"])))

    # 3) NO-GO — hors métier et hors zone
    d3 = {
        "intitule_marche": "Maintenance du parc informatique et infogérance du système d'information",
        "acheteur": "Conseil départemental d'Ille-et-Vilaine", "type_marche": "Services",
        "nature_marche": "Appel d'offres ouvert", "forme_prix": "Prix unitaires (bordereau)",
        "budget_estime": "35 000 EUR HT", "date_limite": "10/12/2026 à 12h00",
        "delai_execution": "Accord-cadre 4 ans", "lieu_execution": "Rennes (35)", "allotissement": "Lot unique",
        "criteres_attribution": [{"critere": "Prix", "ponderation": "70%"}, {"critere": "Valeur technique", "ponderation": "30%"}],
        "sous_traitance": "Autorisée", "variantes": "Non autorisées", "critere_rse": "Non",
        "ca_minimum_requis": "CA > 5 000 000 EUR", "qualifications_requises": ["Certification ITIL", "ISO 27001"],
        "assurances_requises": ["RC Professionnelle"],
        "points_attention": ["Hors métier (services informatiques)", "Hors zone d'intervention (35)", "CA exigé hors d'atteinte"],
        "recommandation": "À écarter : marché de services informatiques, sans rapport avec votre activité BTP, hors de votre zone, et avec un CA exigé inatteignable. Le barème déterministe le classe automatiquement en No-Go — vous économisez le temps d'une lecture inutile.",
        "clauses_risque": [
            {"clause": "Adéquation métier", "niveau": "eleve", "pourquoi": "Prestation informatique sans lien avec le BTP", "levier_negociation": "Aucun — marché hors périmètre"},
        ],
    }
    P.append(dict(key="info", name="Infogérance SI — CD Ille-et-Vilaine", client="Conseil départemental 35",
                  budget=35000, status=ProjectStatus.nouveau,
                  ai=_analysis(d3, "Marché de services d'infogérance informatique à Rennes — hors métier BTP, hors zone, CA exigé inatteignable. Classé No-Go par le barème déterministe.", "25-121650",
                               ["Certification ITIL", "ISO 27001"])))
    return P


# Réseau de co-traitants de démonstration (rattachés à certains AO).
_COTRAITANTS = [
    dict(name="Charpentes du Léon", siret="51234567800018", code_ape="4391A", city="Landerneau",
         departement="29", specialites="Charpente bois, ossature, couverture", ca_n1=820000, effectif=9,
         attach=[("toiture", "cotraitant", "")]),
    dict(name="Zinguerie Bigoudène", siret="48765432100027", code_ape="4391B", city="Pont-l'Abbé",
         departement="29", specialites="Couverture, zinguerie, étanchéité", ca_n1=540000, effectif=6,
         attach=[("toiture", "cotraitant", "")]),
    dict(name="Breizh Désamiantage", siret="53219876500011", code_ape="4399A", city="Lorient",
         departement="56", specialites="Désamiantage SS3, dépose amiante, retrait", ca_n1=2100000, effectif=18,
         attach=[("lorient", "cotraitant", "")]),
]


def ensure_demo(db, force: bool = False) -> User:
    user = db.query(User).filter(User.email == DEMO_EMAIL).first()
    if user and not force:
        return user

    if not user:
        user = User(email=DEMO_EMAIL, hashed_password=hash_password(DEMO_PASSWORD),
                    full_name="Compte Démo", org_role="admin")
        db.add(user); db.flush()
        org = Organization(name="Bâtiment de l'Ouest (démo)", owner_id=user.id)
        db.add(org); db.flush()
        user.org_id = org.id

    user.plan = PlanType.business
    user.full_name = "Compte Démo"

    comp = db.query(Company).filter(Company.user_id == user.id).first() or Company(user_id=user.id, name="x")
    if comp.id is None:
        db.add(comp)
    comp.name = "Bâtiment de l'Ouest"; comp.siret = "00000000000000"
    comp.city = "Quimper"; comp.postal_code = "29000"; comp.forme_juridique = "SARL"
    comp.ca_n1 = 1250000; comp.ca_n2 = 1100000; comp.ca_n3 = 980000; comp.effectif = 14
    comp.qualifications = _COMPANY["qualifications"]
    comp.team = [
        {"nom": "Yann Tanguy", "fonction": "Conducteur de travaux", "qualifications": "BTS Bâtiment, 18 ans d'expérience", "references": "Chef de chantier sur 12 réfections de toiture scolaire"},
        {"nom": "Sophie Hénaff", "fonction": "Responsable QSE / RSE", "qualifications": "Ingénieure, certifiée RGE", "references": "Pilote des clauses d'insertion sur 8 marchés publics"},
        {"nom": "Erwan Le Bris", "fonction": "Chef d'équipe étanchéité", "qualifications": "BP Couverture, 12 ans", "references": "Pose de membrane sur 20 000 m² de toitures-terrasses"},
    ]
    comp.day_rates = _DAY_RATES
    comp.distance_threshold_km = 50
    comp.distance_surcharge_pct = 12

    crit = db.query(MatchingCriteria).filter(MatchingCriteria.user_id == user.id).first() or MatchingCriteria(user_id=user.id)
    if crit.id is None:
        db.add(crit)
    crit.departments = _CRITERIA["departements"] if "departements" in _CRITERIA else _CRITERIA["departements"]
    crit.skills = ["toiture", "étanchéité", "gros œuvre", "isolation", "charpente"]
    crit.budget_min = _CRITERIA["budget_min"]; crit.budget_max = _CRITERIA["budget_max"]; crit.go_threshold = _CRITERIA["go_threshold"]

    # On repart propre : liens, co-traitants, projets de la démo.
    old_ids = [p.id for p in db.query(Project).filter(Project.user_id == user.id).all()]
    if old_ids:
        db.query(ProjectCotraitant).filter(ProjectCotraitant.project_id.in_(old_ids)).delete(synchronize_session=False)
    db.query(Cotraitant).filter(Cotraitant.user_id == user.id).delete(synchronize_session=False)
    db.query(Project).filter(Project.user_id == user.id).delete(synchronize_session=False)
    db.flush()
    db.expire_all()   # vide l'identity map après suppression en masse

    proj_by_key = {}
    for p in _projects():
        ai = p["ai"]
        est = compute_estimate(_TOITURE_TASKS, _DAY_RATES, 0, 50, 12) if p["key"] == "toiture" else None
        if est:
            est["rates_used"] = _DAY_RATES
            est["review"] = {"status": "valide", "by": "Compte Démo",
                             "note": "Chiffrage cohérent avec le DCE — bon à déposer.",
                             "at": "2026-06-16T09:00:00"}
        proj = Project(user_id=user.id, name=p["name"], client=p["client"], budget=p["budget"],
                       status=p["status"], source_url=ai["source"]["source_url"],
                       match_score=ai["match_score"], go_decision=ai["go_decision"],
                       ai_summary=ai["summary"], ai_analysis=ai, estimate=est)
        db.add(proj); db.flush()
        proj_by_key[p["key"]] = proj.id

    for c in _COTRAITANTS:
        ct = Cotraitant(user_id=user.id, name=c["name"], siret=c["siret"], code_ape=c["code_ape"],
                        city=c["city"], departement=c["departement"], specialites=c["specialites"],
                        ca_n1=c["ca_n1"], effectif=c["effectif"])
        db.add(ct); db.flush()
        for key, role, lot in c["attach"]:
            if key in proj_by_key:
                db.add(ProjectCotraitant(project_id=proj_by_key[key], cotraitant_id=ct.id, role=role, lot=lot))

    db.commit()
    db.refresh(user)
    logger.info("Compte démo prêt (%s) — 3 AO + %d co-traitants.", DEMO_EMAIL, len(_COTRAITANTS))
    return user
