"""
Compte de DÉMONSTRATION — pré-rempli pour montrer la valeur d'Adjugo sans inscription.

ensure_demo(db) crée (si absent) le compte demo@adjugo.fr : une entreprise BTP réaliste,
des critères, et 3 appels d'offres DÉJÀ analysés (Go/No-Go déterministe via score_dce —
aucun appel LLM, donc instantané et gratuit). Idempotent ; force=True réinitialise.

Branché au démarrage (main.py) et accessible via /api/auth/demo (connexion sans mot de passe).
"""
import logging

from app.core.security import hash_password
from app.models import (Company, MatchingCriteria, Organization, PlanType,
                        Project, ProjectStatus, User)
from app.services.dce_scoring import score_dce

logger = logging.getLogger("adjugo")

DEMO_EMAIL = "demo@adjugo.fr"
DEMO_PASSWORD = "demo1234"

# Profil entreprise (clés attendues par score_dce pour le calcul du barème).
_COMPANY = {
    "name": "Bâtiment de l'Ouest",
    "ca_n1": 1250000,
    "postal_code": "29000",
    "qualifications": [
        {"name": "Qualibat 3212", "detail": "étanchéité de toiture par éléments"},
        {"name": "RGE", "detail": "reconnu garant de l'environnement"},
    ],
}
_CRITERIA = {
    "specialites": "toiture, étanchéité, gros œuvre, isolation, charpente, couverture",
    "departements": ["29", "56", "22"],
    "budget_min": 50000, "budget_max": 2000000, "go_threshold": 75,
}


def _analysis(details: dict, summary: str):
    """Reconstitue EXACTEMENT la sortie de analyze_dce_text (barème déterministe)."""
    det = score_dce(details, _COMPANY, _CRITERIA)
    return {
        "match_score": det["score"], "go_decision": det["go_decision"], "summary": summary,
        "details": details, "score_breakdown": det["breakdown"],
        "score_deterministe": True, "dce_available": True,
    }, det


def _demo_projects():
    P = []

    # 1) GO — métier/zone/qualifs alignés
    d1 = {
        "intitule_marche": "Réfection de la toiture et étanchéité du groupe scolaire Jean Moulin",
        "acheteur": "Ville de Quimper", "type_marche": "Travaux",
        "nature_marche": "Marché à procédure adaptée (MAPA)", "forme_prix": "Prix global et forfaitaire",
        "budget_estime": "480 000 EUR HT", "date_limite": "30/12/2026 à 12h00",
        "delai_execution": "5 mois", "lieu_execution": "Quimper (29)", "allotissement": "Lot unique",
        "criteres_attribution": [{"critere": "Valeur technique", "ponderation": "60%"}, {"critere": "Prix", "ponderation": "40%"}],
        "garanties_exigees": "Retenue de garantie 5%", "penalites": "1/1000 du HT par jour, plafond 10%",
        "ca_minimum_requis": "CA > 1 500 000 EUR sur 3 ans", "qualifications_requises": ["Qualibat 3212", "RGE"],
        "points_attention": ["Critère technique prépondérant (60%)", "Exigence de CA (1,5 M€) légèrement au-dessus de votre CA N-1 — à surveiller"],
        "recommandation": "Très bonne cible : métier, zone et qualifications alignés. Soigner le mémoire technique (60% de la note). Surveiller l'exigence de CA et proposer une caution de substitution à la retenue de garantie.",
        "clauses_risque": [{"clause": "Retenue de garantie", "niveau": "moyen", "pourquoi": "5% retenus pendant 1 an, immobilise la trésorerie", "levier_negociation": "Caution bancaire de substitution (art. R2191-33)"}],
    }
    a1, _ = _analysis(d1, "Réfection de toiture d'un groupe scolaire à Quimper — travaux en lot unique, 480 k€, critère technique prépondérant (60%). Métier, zone et qualifications alignés.")
    P.append(dict(name="Réfection toiture — Groupe scolaire Jean Moulin", client="Ville de Quimper",
                  budget=480000, status=ProjectStatus.en_cours, ai=a1, url="https://www.boamp.fr"))

    # 2) À ÉTUDIER — bonne zone mais qualif manquante + exigence de CA élevée
    d2 = {
        "intitule_marche": "Réhabilitation énergétique et désamiantage du gymnase municipal",
        "acheteur": "Lorient Agglomération", "type_marche": "Travaux",
        "nature_marche": "Appel d'offres ouvert", "forme_prix": "Prix global et forfaitaire",
        "budget_estime": "1 250 000 EUR HT", "date_limite": "20/12/2026 à 17h00",
        "delai_execution": "9 mois", "lieu_execution": "Lorient (56)", "allotissement": "Lot unique",
        "criteres_attribution": [{"critere": "Prix", "ponderation": "50%"}, {"critere": "Valeur technique", "ponderation": "50%"}],
        "ca_minimum_requis": "CA > 3 000 000 EUR sur 3 ans", "qualifications_requises": ["Qualification désamiantage SS3", "Certification amiante sous-section 3"],
        "points_attention": ["Désamiantage : qualification SS3 exigée (non détenue)", "CA minimum exigé supérieur à votre CA"],
        "recommandation": "Marché en zone, mais deux verrous : le désamiantage (SS3) et l'exigence de CA. À envisager en GROUPEMENT avec un désamianteur qualifié — Adjugo peut détecter un co-traitant complémentaire.",
        "clauses_risque": [{"clause": "Capacité financière", "niveau": "eleve", "pourquoi": "CA exigé 3 M€ > votre CA", "levier_negociation": "Répondre en groupement pour mutualiser les CA"}],
    }
    a2, _ = _analysis(d2, "Réhabilitation énergétique d'un gymnase à Lorient — 1,25 M€. En zone mais qualification désamiantage SS3 non détenue et CA exigé élevé : candidature en groupement à étudier.")
    P.append(dict(name="Réhabilitation énergétique — Gymnase de Lorient", client="Lorient Agglomération",
                  budget=1250000, status=ProjectStatus.nouveau, ai=a2, url="https://www.boamp.fr"))

    # 3) NO-GO — hors métier et hors zone
    d3 = {
        "intitule_marche": "Maintenance du parc informatique et infogérance du SI",
        "acheteur": "Conseil départemental d'Ille-et-Vilaine", "type_marche": "Services",
        "nature_marche": "Appel d'offres ouvert", "forme_prix": "Prix unitaires (bordereau)",
        "budget_estime": "35 000 EUR HT", "date_limite": "10/12/2026 à 12h00",
        "delai_execution": "Accord-cadre 4 ans", "lieu_execution": "Rennes (35)", "allotissement": "Lot unique",
        "criteres_attribution": [{"critere": "Prix", "ponderation": "70%"}, {"critere": "Valeur technique", "ponderation": "30%"}],
        "ca_minimum_requis": "CA > 5 000 000 EUR", "qualifications_requises": ["Certification ITIL", "ISO 27001"],
        "points_attention": ["Hors métier (informatique)", "Hors zone d'intervention (35)"],
        "recommandation": "À écarter : marché de services informatiques, sans rapport avec votre activité BTP, et hors de votre zone. Le score déterministe le classe automatiquement en No-Go.",
        "clauses_risque": [],
    }
    a3, _ = _analysis(d3, "Marché de services d'infogérance informatique à Rennes — hors métier BTP et hors zone. Classé No-Go par le barème déterministe.")
    P.append(dict(name="Infogérance SI — CD Ille-et-Vilaine", client="Conseil départemental 35",
                  budget=35000, status=ProjectStatus.nouveau, ai=a3, url="https://www.boamp.fr"))

    return P


def ensure_demo(db, force: bool = False) -> User:
    """Crée le compte démo s'il n'existe pas (ou le réinitialise si force=True)."""
    user = db.query(User).filter(User.email == DEMO_EMAIL).first()
    if user and not force:
        return user

    if not user:
        user = User(email=DEMO_EMAIL, hashed_password=hash_password(DEMO_PASSWORD),
                    full_name="Compte Démo", org_role="admin")
        db.add(user)
        db.flush()
        org = Organization(name="Bâtiment de l'Ouest (démo)", owner_id=user.id)
        db.add(org)
        db.flush()
        user.org_id = org.id

    user.plan = PlanType.business      # toutes les fonctionnalités visibles en démo
    user.full_name = "Compte Démo"

    # Profil entreprise
    comp = db.query(Company).filter(Company.user_id == user.id).first()
    if not comp:
        comp = Company(user_id=user.id, name="Bâtiment de l'Ouest")
        db.add(comp)
    comp.name = "Bâtiment de l'Ouest"
    comp.siret = "00000000000000"
    comp.city = "Quimper"; comp.postal_code = "29000"
    comp.forme_juridique = "SARL"; comp.ca_n1 = 1250000; comp.ca_n2 = 1100000; comp.ca_n3 = 980000
    comp.effectif = 14
    comp.qualifications = _COMPANY["qualifications"]

    # Critères
    crit = db.query(MatchingCriteria).filter(MatchingCriteria.user_id == user.id).first()
    if not crit:
        crit = MatchingCriteria(user_id=user.id)
        db.add(crit)
    crit.departments = _CRITERIA["departements"]
    crit.skills = ["toiture", "étanchéité", "gros œuvre", "isolation", "charpente"]
    crit.budget_min = _CRITERIA["budget_min"]; crit.budget_max = _CRITERIA["budget_max"]
    crit.go_threshold = _CRITERIA["go_threshold"]

    # Projets : on repart propre
    db.query(Project).filter(Project.user_id == user.id).delete()
    db.flush()
    for p in _demo_projects():
        ai, _ = p["ai"], None
        proj = Project(user_id=user.id, name=p["name"], client=p["client"], budget=p["budget"],
                       status=p["status"], source_url=p["url"],
                       match_score=ai["match_score"], go_decision=ai["go_decision"],
                       ai_summary=ai["summary"], ai_analysis=ai)
        db.add(proj)

    db.commit()
    db.refresh(user)
    logger.info("Compte démo prêt (%s).", DEMO_EMAIL)
    return user
