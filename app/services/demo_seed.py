"""
Compte de DÉMONSTRATION — pré-rempli pour montrer TOUTE la valeur d'Adjugo sans inscription.

ensure_demo(db) crée (si absent) demo@adjugo.fr : une entreprise BTP réaliste, des critères,
3 appels d'offres COMPLÈTEMENT analysés (Go/No-Go déterministe via score_dce — aucun appel
LLM), avec détail du score, clauses à risque, pièces requises, source BOAMP, et un réseau de
co-traitants rattachés (dont un désamianteur sur le marché « à étudier » pour illustrer le
groupement). Idempotent ; force=True réinitialise.
La rédaction (grille « Comment vous serez noté », dossier du marché lu en entier, « Mes preuves »,
dossier de présentation déjà rédigé) est remplie par app/services/demo_redaction.py, sans IA ; le groupement
de Kerhel (dossier lu en entier, convention générée et validée par les deux membres, formulaires officiels)
par app/services/demo_groupement.py, sans IA.

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
    {"phase": "Préparation", "tache": "Installation de chantier, sécurité et protections", "profil": "Exécution / terrain", "jours": 12},
    {"phase": "Étude", "tache": "Relevés, calepinage et plans d'exécution étanchéité", "profil": "Étude / conception", "jours": 8},
    {"phase": "Production", "tache": "Dépose de la couverture existante et évacuation", "profil": "Exécution / terrain", "jours": 60},
    {"phase": "Production", "tache": "Pose de l'isolation thermique et de la membrane d'étanchéité", "profil": "Exécution / terrain", "jours": 150},
    {"phase": "Production", "tache": "Zinguerie, relevés et évacuations des eaux pluviales", "profil": "Exécution / terrain", "jours": 45},
    {"phase": "Contrôle", "tache": "Tests d'étanchéité, levée de réserves et réception", "profil": "Étude / conception", "jours": 8},
    {"phase": "Pilotage", "tache": "Encadrement, coordination et suivi de chantier", "profil": "Encadrement / direction", "jours": 40},
]

logger = logging.getLogger("adjugo")

DEMO_EMAIL = "demo@adjugo.fr"
DEMO_PASSWORD = "demo1234"


def _luhn_siret(base13: str) -> str:
    """Complète 13 chiffres par la clé de Luhn → SIRET 14 chiffres valide (réaliste)."""
    s = 0
    for i, ch in enumerate(reversed(base13)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        s += d
    return base13 + str((10 - s % 10) % 10)


# SIRET de démonstration stable et Luhn-valide (SIREN 802 456 073, établissement 0004).
DEMO_SIRET = _luhn_siret("8024560730004")

_COMPANY = {
    "name": "Bâtiment de l'Ouest", "ca_n1": 1250000, "postal_code": "44000",
    "qualifications": [
        {"name": "Qualibat 3212", "detail": "étanchéité de toiture par éléments"},
        {"name": "RGE", "detail": "reconnu garant de l'environnement"},
    ],
}
_CRITERIA = {
    "specialites": "toiture, étanchéité, gros œuvre, isolation, charpente, couverture",
    "departements": ["44", "33", "31", "69", "13", "67", "59", "35"], "budget_min": 50000, "budget_max": 2000000, "go_threshold": 75,
}


def _date_limite(details):
    """Date limite du marché (colonne Project.deadline) lue dans l'analyse (« 20/12/2026 à 17h00 ») :
    la même date que celle affichée, pour le tableau de bord, le dépôt et le coffre croisé."""
    import datetime as _dt
    import re as _re
    m = _re.search(r"(\d{2})/(\d{2})/(\d{4})", str((details or {}).get("date_limite") or ""))
    if not m:
        return None
    try:
        return _dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _analysis(details, summary, ref, pieces):
    """Reconstitue la sortie complète d'analyze_dce_text (barème déterministe, sans LLM)."""
    det = score_dce(details, _COMPANY, _CRITERIA)
    return {
        "match_score": det["score"], "go_decision": det["go_decision"], "summary": summary,
        "details": details, "score_breakdown": det["breakdown"],
        "lead_score": {"total": det["score"], "breakdown": det["breakdown"], "note": summary[:140]},
        "source": {"source": "BOAMP", "official_ref": ref, "source_url": "/static/demo/avis-boamp.html"},
        "pieces_requises": pieces, "dce_available": True, "score_deterministe": True,
    }


def _projects():
    P = []

    # 1) GO — toiture groupe scolaire
    d1 = {
        "intitule_marche": "Réfection de la toiture et étanchéité du groupe scolaire Jean Moulin",
        "acheteur": "Ville de Marvejac",
        "contact": {"nom": "Sabine Vidal", "fonction": "Direction de la commande publique", "email": "marches@ville-marvejac.exemple", "telephone": ""},
        "type_marche": "Travaux",
        "nature_marche": "Marché à procédure adaptée (MAPA)", "forme_prix": "Prix global et forfaitaire",
        "budget_estime": "480 000 EUR HT", "date_limite": "30/12/2026 à 12h00",
        "delai_execution": "5 mois à compter de l'ordre de service", "lieu_execution": "Marvejac (33)",
        "allotissement": "Lot unique",
        "criteres_attribution": [{"critere": "Valeur technique", "ponderation": "60%"}, {"critere": "Prix", "ponderation": "40%"}],
        "garanties_exigees": "Retenue de garantie 5%", "penalites": "1/1000 du montant HT par jour, plafonnées à 10%",
        "avance": "Avance de 10% (marché > 50 000 EUR HT)", "sous_traitance": "Autorisée — déclaration DC4 requise",
        "variantes": "Autorisées sur les matériaux d'étanchéité", "critere_rse": "Oui — clause d'insertion sociale (200 h)",
        "ca_minimum_requis": "CA annuel moyen ≥ 1 500 000 EUR (3 derniers exercices)", "qualifications_requises": ["Qualibat 3212", "RGE"],
        "assurances_requises": ["RC Professionnelle", "Garantie décennale"],
        "visite_obligatoire": "Recommandée, sur rendez-vous avant le 15/12/2026",
        "points_attention": ["Critère technique prépondérant (60%) — soigner le dossier de présentation", "Exigence de CA (1,5 M€) au-dessus de votre CA N-1 — à surveiller", "Clause d'insertion sociale de 200 h"],
        "recommandation": "Marché de réfection de toiture et d'étanchéité d'un groupe scolaire, en lot unique, pour 480 000 € HT, porté par la Ville de Marvejac. C'est une cible prioritaire : l'objet est au cœur de votre métier (couverture-étanchéité), le chantier est dans votre zone et les qualifications exigées (Qualibat 3212, RGE) sont détenues. Le seul point de recevabilité à surveiller est le chiffre d'affaires minimum demandé : 1,5 M€ par an en moyenne sur les trois derniers exercices, au-dessus de votre CA N-1. Seul, la candidature serait écartée ; avec un partenaire, les chiffres d'affaires s'additionnent (voir « Répondre à plusieurs ? »).\n\nLa mécanique d'attribution est déterminante : la valeur technique pèse 60 % contre 40 % pour le prix. Ce marché ne se gagne donc pas au moins-disant, mais sur la qualité du dossier de présentation. Il faut y détailler la méthodologie d'étanchéité (complexe retenu, traitement des relevés et des points singuliers), la gestion d'un chantier en site occupé — une école reste en activité : phasage, sécurité, propreté, limitation des nuisances — et un planning réaliste. C'est là que se creuse l'écart avec les concurrents.\n\nCôté administratif, trois clauses appellent une action : la retenue de garantie de 5 % (à remplacer par une caution bancaire de substitution, art. R2191-33, pour ne pas immobiliser votre trésorerie un an), les pénalités de retard (négocier une franchise de quelques jours ouvrés et un plafond raisonnable) et la clause d'insertion sociale de 200 h (à sécuriser en conventionnant en amont une structure d'insertion locale).\n\nEn synthèse : foncez, avec un partenaire pour le chiffre d'affaires, en investissant prioritairement le dossier de présentation. La visite de site, recommandée avant le 15/12, est vivement conseillée — elle nourrit le dossier de présentation et crédibilise l'offre auprès de l'acheteur.",
        "clauses_risque": [
            {"clause": "Retenue de garantie", "niveau": "moyen", "pourquoi": "5% retenus pendant 1 an, immobilise la trésorerie", "levier_negociation": "Caution bancaire de substitution (art. R2191-33)"},
            {"clause": "Pénalités de retard", "niveau": "moyen", "pourquoi": "1/1000 du HT par jour, plafond 10%", "levier_negociation": "Demander une franchise de 5 jours ouvrés et un plafond à 5%"},
            {"clause": "Clause d'insertion sociale", "niveau": "faible", "pourquoi": "200 h d'insertion à réaliser sur le chantier", "levier_negociation": "Conventionner une structure d'insertion locale (facilité opérationnelle)"},
        ],
    }
    P.append(dict(key="toiture", name="Réfection toiture — Groupe scolaire Jean Moulin", client="Ville de Marvejac",
                  budget=480000, status=ProjectStatus.en_cours,
                  ai=_analysis(d1, "Réfection de toiture d'un groupe scolaire à Marvejac — travaux en lot unique, 480 k€, valeur technique prépondérante (60%). Métier, zone et qualifications alignés : cible prioritaire.", "DEMO-25114207",
                               ["Certificat Qualibat 3212 (en cours de validité)", "Attestation RGE", "Mémoire technique — méthodologie étanchéité", "3 références de toitures scolaires (< 3 ans)", "Attestation d'assurance décennale"])))

    # 2) À ÉTUDIER — réhabilitation énergétique + désamiantage (groupement)
    d2 = {
        "intitule_marche": "Réhabilitation énergétique et désamiantage du gymnase municipal",
        "acheteur": "Kerhel Agglomération", "type_marche": "Travaux",
        "nature_marche": "Appel d'offres ouvert", "forme_prix": "Prix global et forfaitaire",
        "budget_estime": "1 250 000 EUR HT", "date_limite": "20/12/2026 à 17h00",
        "delai_execution": "9 mois", "lieu_execution": "Kerhel (56)",
        "allotissement": "Lot 1 : Désamiantage et retrait d'amiante ; Lot 2 : Isolation thermique et rénovation énergétique ; Lot 3 : Gros œuvre et étanchéité",
        "criteres_attribution": [{"critere": "Prix", "ponderation": "50%"}, {"critere": "Valeur technique", "ponderation": "50%"}],
        "garanties_exigees": "Retenue de garantie 5% + garantie à première demande", "penalites": "1/1000 du HT par jour",
        "sous_traitance": "Autorisée", "variantes": "Non autorisées", "critere_rse": "Oui — bilan carbone exigé",
        "ca_minimum_requis": "CA annuel moyen ≥ 3 000 000 EUR (3 derniers exercices)", "qualifications_requises": ["Qualification désamiantage SS3", "Certification amiante sous-section 3"],
        "assurances_requises": ["RC Professionnelle", "Garantie décennale", "Assurance amiante"],
        "visite_obligatoire": "Obligatoire — 05/12/2026 à 14h",
        "points_attention": ["Désamiantage : qualification SS3 exigée (non détenue)", "CA minimum exigé (3 M€) supérieur à votre CA", "Garantie à première demande"],
        "recommandation": "Réhabilitation énergétique et désamiantage d'un gymnase, pour 1,25 M€ HT, allotie en trois lots (désamiantage, isolation/énergie, gros œuvre/étanchéité), portée par Kerhel Agglomération. Le marché est en zone et sur votre cœur de métier (rénovation énergétique), ce qui en fait une opportunité réelle — mais deux verrous conditionnent la recevabilité.\n\nPremier verrou : la qualification désamiantage sous-section 3 (SS3), exigée et non détenue en interne. Deuxième verrou : le chiffre d'affaires minimum demandé (3 M€ par an en moyenne sur les trois derniers exercices), supérieur à votre CA. Répondre seul est donc impossible sur ces deux critères. S'y ajoute une garantie à première demande, appelable sans justification, qui engage lourdement la trésorerie.\n\nLa bonne stratégie est claire : répondre en GROUPEMENT conjoint avec un désamianteur certifié SS3. Il apporte la qualification manquante et, en groupement, les chiffres d'affaires se cumulent — les deux verrous sautent d'un coup. Adjugo a d'ailleurs déjà identifié un partenaire complémentaire qualifié SS3. Sur la garantie à première demande, proposer une caution bancaire classique en substitution.\n\nEn synthèse : à étudier sérieusement, mais uniquement en groupement. Seul, il est hors d'atteinte ; à plusieurs, c'est un marché à 1,25 M€ à portée de main. La visite est obligatoire (05/12) — à ne pas manquer, sous peine d'irrecevabilité.",
        "clauses_risque": [
            {"clause": "Capacité financière", "niveau": "eleve", "pourquoi": "CA exigé 3 M€ supérieur à votre CA N-1", "levier_negociation": "Répondre en groupement conjoint pour cumuler les chiffres d'affaires"},
            {"clause": "Garantie à première demande", "niveau": "eleve", "pourquoi": "Engage la trésorerie sans recours, appelable sans justification", "levier_negociation": "Proposer une caution bancaire classique en substitution"},
            {"clause": "Qualification désamiantage SS3", "niveau": "eleve", "pourquoi": "Non détenue en interne", "levier_negociation": "Groupement avec un désamianteur certifié SS3"},
        ],
    }
    P.append(dict(key="lorient", name="Réhabilitation énergétique — Gymnase de Kerhel", client="Kerhel Agglomération",
                  budget=1250000, status=ProjectStatus.nouveau,
                  ai=_analysis(d2, "Réhabilitation énergétique d'un gymnase à Kerhel — 1,25 M€. En zone et dans votre métier, mais qualification désamiantage SS3 non détenue et CA exigé élevé : candidature en GROUPEMENT à étudier.", "DEMO-25118934",
                               ["Qualification désamiantage SS3 (ou partenaire du groupement)", "Bilan carbone de l'entreprise", "Garantie à première demande", "Plan de retrait amiante", "Attestation de visite obligatoire"])))

    # 3) NO-GO — hors métier et hors zone
    d3 = {
        "intitule_marche": "Maintenance du parc informatique et infogérance du système d'information",
        "acheteur": "Métropole Cap-Aurèle", "type_marche": "Services",
        "nature_marche": "Appel d'offres ouvert", "forme_prix": "Prix unitaires (bordereau)",
        "budget_estime": "35 000 EUR HT", "date_limite": "10/12/2026 à 12h00",
        "delai_execution": "Accord-cadre 4 ans", "lieu_execution": "Cap-Aurèle (06)", "allotissement": "Lot unique",
        "criteres_attribution": [{"critere": "Prix", "ponderation": "70%"}, {"critere": "Valeur technique", "ponderation": "30%"}],
        "sous_traitance": "Autorisée", "variantes": "Non autorisées", "critere_rse": "Non",
        "ca_minimum_requis": "CA > 5 000 000 EUR", "qualifications_requises": ["Certification ITIL", "ISO 27001"],
        "assurances_requises": ["RC Professionnelle"],
        "points_attention": ["Hors métier (services informatiques)", "Hors zone d'intervention (06)", "CA exigé hors d'atteinte"],
        "recommandation": "Marché de maintenance et d'infogérance d'un système d'information, sous forme d'accord-cadre de 4 ans, porté par la Métropole Cap-Aurèle. L'analyse est sans ambiguïté : ce marché est à écarter, pour trois raisons cumulatives.\n\nD'abord, l'objet — des prestations informatiques (ITIL, ISO 27001) — n'a aucun rapport avec votre activité de bâtiment : l'adéquation métier est nulle. Ensuite, le lieu d'exécution (Cap-Aurèle, 06) est hors de votre zone d'intervention. Enfin, le chiffre d'affaires exigé (5 M€) est hors d'atteinte.\n\nLe barème le classe automatiquement parmi les marchés à écarter. L'intérêt d'Adjugo ici n'est pas de vous faire perdre du temps sur ce dossier, mais de vous montrer, en un coup d'œil, pourquoi ne PAS y aller — pour que vous concentriez votre énergie sur les marchés que vous pouvez réellement gagner. C'est aussi ça, le tri : autant d'heures économisées sur les fausses pistes.\n\nConcrètement, trois signaux auraient dû alerter dès la lecture de l'avis : un code CPV de services informatiques (72xxx) sans rapport avec vos codes travaux, un lieu d'exécution hors de vos départements, et un chiffre d'affaires plancher hors norme pour une PME du bâtiment. Chacun de ces trois critères, pris isolément, suffit à écarter le marché ; ici, les trois se cumulent.\n\nC'est précisément le rôle du tri automatique : sur les dizaines d'avis publiés chaque semaine, beaucoup ne vous concernent pas. Les écarter en un coup d'œil, avec la raison affichée noir sur blanc, vous fait gagner un temps précieux — celui que vous auriez passé à ouvrir le dossier, lire le règlement de consultation et comprendre que ce n'était pas pour vous. Ce temps, vous le réinvestissez sur les marchés réellement gagnables.",
        "clauses_risque": [
            {"clause": "Adéquation métier", "niveau": "eleve", "pourquoi": "Prestation informatique sans lien avec le BTP", "levier_negociation": "Aucun — marché hors périmètre"},
        ],
    }
    P.append(dict(key="info", name="Infogérance SI — Métropole Cap-Aurèle", client="Métropole Cap-Aurèle",
                  budget=35000, status=ProjectStatus.nouveau,
                  ai=_analysis(d3, "Marché de services d'infogérance informatique à Cap-Aurèle — hors métier BTP, hors zone, CA exigé inatteignable. Classé « à écarter » par le barème, sans IA.", "DEMO-25121650",
                               ["Certification ITIL", "ISO 27001"])))
    return P


# Réseau de co-traitants de démonstration — fiches complètes. Seul Breizh Désamiantage est rattaché à un
# marché (Kerhel), et il y porte une invitation acceptée (part soumise) : aucune entreprise n'est rattachée
# sans accord, comme dans le produit. Les deux autres restent dans « Mes partenaires », prêtes à inviter.
_COTRAITANTS = [
    dict(name="Charpentes Arbrevieux", siret="51234567800018", code_ape="4391A", city="Tours",
         departement="37", specialites="Charpente bois, ossature, couverture", ca_n1=820000, effectif=9,
         forme_juridique="SARL", representant_legal="Hervé Quéméner", email="contact@charpentes-arbrevieux.exemple",
         phone="", codes_cpv="45261000, 45422000",
         qualifications="Qualibat 2392 (charpente bois), RGE", attach=[]),
    dict(name="Zinguerie Bigoudène", siret="48765432100027", code_ape="4391B", city="Lille",
         departement="59", specialites="Couverture, zinguerie, étanchéité", ca_n1=540000, effectif=6,
         forme_juridique="SARL", representant_legal="Loïc Le Berre", email="contact@zinguerie-bigoudene.exemple",
         phone="", codes_cpv="45261000, 45261210",
         qualifications="Qualibat 3411 (zinguerie)", attach=[]),
    dict(name="Breizh Désamiantage", siret="53219876500011", code_ape="4399A", city="Lorient",
         departement="56", specialites="Désamiantage SS3, dépose amiante, retrait", ca_n1=2100000, effectif=18,
         forme_juridique="SAS", representant_legal="Soizic Morvan", email="contact@breizh-desamiantage.exemple",
         phone="", codes_cpv="45262660",
         qualifications="Qualification désamiantage SS3, certification amiante sous-section 3",
         attach=[("lorient", "cotraitant", "")]),
]


def _marquer_espace_demo(user) -> None:
    """Dernier rempart : aucun appel à l'IA dans l'espace du compte démo (app.services.llm)."""
    try:
        from app.services.llm import marquer_tenant_demo
        marquer_tenant_demo(user.id)
    except Exception as e:      # noqa: BLE001 — jamais bloquant : les gardes de quota restent en place
        logger.warning("espace démo non inscrit auprès de l'IA : %s", type(e).__name__)


def ensure_demo(db, force: bool = False) -> User:
    user = db.query(User).filter(User.email == DEMO_EMAIL).first()
    if user is not None and user.id is not None:
        _marquer_espace_demo(user)
    if user and not force:
        # Auto-réparation : un compte démo créé AVANT la vérification d'email restait non
        # vérifié → le mur « Confirmez votre adresse email » bloquait toute la vitrine
        # (personne ne reçoit les mails de demo@adjugo.fr).
        if not user.email_verified:
            user.email_verified = True
            db.commit()
        return user

    if not user:
        user = User(email=DEMO_EMAIL, hashed_password=hash_password(DEMO_PASSWORD),
                    full_name="Compte Démo", org_role="admin", email_verified=True)
        db.add(user); db.flush()
        org = Organization(name="Bâtiment de l'Ouest (démo)", owner_id=user.id)
        db.add(org); db.flush()
        user.org_id = org.id

    user.plan = PlanType.business
    user.full_name = "Compte Démo"
    # Vitrine TOUJOURS accessible : le re-seed (force=True au démarrage) doit aussi réparer
    # un compte démo d'avant la vérification d'email, sinon le mur « Confirmez votre
    # adresse » bloque la démo (personne ne reçoit les mails de demo@adjugo.fr).
    user.email_verified = True

    comp = db.query(Company).filter(Company.user_id == user.id).first() or Company(user_id=user.id, name="x")
    if comp.id is None:
        db.add(comp)
    comp.name = "Bâtiment de l'Ouest"; comp.siret = DEMO_SIRET
    comp.code_ape = "4391A"   # travaux de couverture par éléments
    comp.forme_juridique = "SARL"; comp.capital = "50 000 €"
    comp.representant_legal = "Gwénaël Le Bihan, gérant"
    comp.address = "12 rue des Chantiers, ZA de Kerlann"
    comp.city = "Nantes"; comp.postal_code = "44000"
    comp.tva_intracom = "FR" + DEMO_SIRET[:11]   # FR + clé + SIREN (format vitrine)
    comp.phone = ""; comp.email = "contact@batiment-ouest.exemple"
    comp.ca_n1 = 1250000; comp.ca_n2 = 1100000; comp.ca_n3 = 980000; comp.effectif = 14
    comp.qualifications = _COMPANY["qualifications"]
    comp.references = [
        {"intitule": "Réfection de la couverture de l'école élémentaire", "client": "Ville de Bréhaut", "montant": 96000, "annee": 2024},
        {"intitule": "Étanchéité-toiture du centre technique municipal", "client": "Ville de Lesparrac", "montant": 182000, "annee": 2023},
        {"intitule": "Rénovation thermique d'un groupe scolaire (lot couverture/isolation)", "client": "Ville de Castelmorin", "montant": 145000, "annee": 2023},
    ]
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
    crit.certifications = ["Qualibat 3212", "RGE"]
    crit.market_types = ["public", "semi_public"]
    crit.max_distance_km = 80
    crit.budget_min = _CRITERIA["budget_min"]; crit.budget_max = _CRITERIA["budget_max"]
    crit.go_threshold = _CRITERIA["go_threshold"]; crit.nogo_threshold = 49

    # On repart propre : on supprime D'ABORD tout ce qui référence les projets démo
    # (documents, docs générés, factures, liens co-traitants) sinon la contrainte de clé
    # étrangère bloque la suppression des projets et fait échouer tout le reseed.
    from app.models import (Document, GeneratedDoc, Invoice, ProjectInvite,
                            ProjectContribution, ContributionPiece, AuditLog,
                            GroupementSimulation, GroupementConvention, GroupementSignature,
                            DossierPresentation, DossierSection, DossierSectionVersion, Preuve,
                            DossierPartBrouillon, DossierRepartition, DossierValidation, EntretienQuestion)
    old_ids = [p.id for p in db.query(Project).filter(Project.user_id == user.id).all()]
    if old_ids:
        # Ordre : enfants des contributions/invites d'abord, puis le reste. TOUTES les
        # tables qui référencent projects doivent être purgées sinon la FK bloque le reseed
        # (ex. project_invites créés en testant la co-traitance, simulations de groupement,
        # dossier de présentation de l'atelier, convention de groupement et ses accords ;
        # rédaction, vague 4 : brouillons des partenaires, « Qui écrit quoi » et validations du
        # dossier assemblé, qui pointent vers les parties et le dossier).
        from app.services.depot_lien import effacer_projets as _effacer_depots
        _effacer_depots(db, old_ids)      # la démo ne dépose rien : filet (aucune clé étrangère à ces tables)
        # Rédaction, vague 5 : l'entretien chantier (questions et réponses) pointe vers le dossier.
        for M in (EntretienQuestion, DossierPartBrouillon, DossierRepartition, DossierValidation,
                  DossierSectionVersion, DossierSection, DossierPresentation, GroupementSignature,
                  GroupementConvention, ContributionPiece, ProjectContribution, ProjectInvite,
                  GroupementSimulation, ProjectCotraitant, Document, GeneratedDoc, Invoice, AuditLog):
            db.query(M).filter(M.project_id.in_(old_ids)).delete(synchronize_session=False)
    # « Mes preuves » du compte démo : recréées par le seed de la rédaction (numéros stables F1, F2…).
    db.query(Preuve).filter(Preuve.owner_id == user.id).delete(synchronize_session=False)
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
                       ai_summary=ai["summary"], ai_analysis=ai, estimate=est,
                       deadline=_date_limite(ai.get("details")))
        db.add(proj); db.flush()
        proj_by_key[p["key"]] = proj.id

    ct_by_name = {}
    for c in _COTRAITANTS:
        ct = Cotraitant(user_id=user.id, name=c["name"], siret=c["siret"], code_ape=c["code_ape"],
                        city=c["city"], departement=c["departement"], specialites=c["specialites"],
                        ca_n1=c["ca_n1"], effectif=c["effectif"],
                        forme_juridique=c.get("forme_juridique", ""), representant_legal=c.get("representant_legal", ""),
                        email=c.get("email", ""), phone=c.get("phone", ""),
                        codes_cpv=c.get("codes_cpv", ""), qualifications=c.get("qualifications", ""))
        db.add(ct); db.flush()
        ct_by_name[c["name"]] = ct
        for key, role, lot in c["attach"]:
            if key in proj_by_key:
                db.add(ProjectCotraitant(project_id=proj_by_key[key], cotraitant_id=ct.id, role=role, lot=lot))

    db.commit()
    _marquer_espace_demo(user)      # compte enregistré : son espace ne peut plus appeler l'IA

    # Kerhel : son dossier (fictif) lu en entier, exigences et forme du groupement citées par le
    # règlement. AVANT le calcul du groupement (il lit les exigences citées). Transaction propre.
    try:
        from app.services.demo_groupement import seed_dossier
        seed_dossier(db, user, proj_by_key)
    except Exception as e:
        db.rollback()
        logger.warning("seed démo (dossier de Kerhel) ignoré : %s", e)

    # « Répondre à plusieurs ? » : verdict de groupement CALCULÉ sur Kerhel (CA 3 M€ + SS3
    # apportés par Breizh Désamiantage). Transaction propre ; skip si le service pur est absent.
    try:
        _seed_groupement(db, user, comp, proj_by_key, ct_by_name)
    except Exception as e:
        db.rollback()
        logger.warning("seed démo (groupement) ignoré : %s", e)

    # Vitrine complète : factures, coffre-fort, CERFA (dont DC4 du consortium), veille
    # amont, alertes, base de connaissances, contacts, groupement de Kerhel matérialisé…
    # Isolé dans sa propre transaction : un échec ici n'altère jamais le cœur de la démo.
    try:
        _seed_extras(db, user, proj_by_key, ct_by_name)
    except Exception as e:
        db.rollback()
        logger.warning("seed démo (extras) ignoré : %s", e)

    # Rédaction, vague 6 (F) : le carnet de notes des trois marchés décidés (notes FICTIVES, un marché perdu avec son
    # courrier lu sans IA) → « Où vous perdez des points » et « La dernière fois, l'acheteur a écrit ». Transaction propre.
    try:
        from app.services.demo_carnet import seed_carnet
        seed_carnet(db, user)
    except Exception as e:
        db.rollback()
        logger.warning("seed démo (carnet de notes) ignoré : %s", e)

    # Rédaction (vagues 1 à 3) : dossier du marché « toiture » lu en entier (grille « Comment vous serez
    # noté », couverture), « Mes preuves », dossier de présentation déjà rédigé. Sans IA ni réseau, dans sa
    # propre transaction (app/services/demo_redaction.py) : un échec laisse le reste de la vitrine intact.
    try:
        from app.services.demo_redaction import seed_redaction
        seed_redaction(db, user, proj_by_key)
    except Exception as e:
        db.rollback()
        logger.warning("seed démo (rédaction) ignoré : %s", e)

    # Rédaction, vague 6 (J) : un marché FICTIF réparti en trois lots, auquel Bâtiment de l'Ouest répond sur deux lots
    # (parties communes, parties propres à chaque lot, un fichier par lot). Sans IA ni réseau, dans sa propre
    # transaction (app/services/demo_lots.py) : un échec laisse le reste de la vitrine intact.
    try:
        from app.services.demo_lots import seed_lots
        seed_lots(db, user, proj_by_key)
    except Exception as e:
        db.rollback()
        logger.warning("seed démo (plusieurs lots) ignoré : %s", e)

    # Groupement de Kerhel jusqu'au dépôt : convention générée (offre figée) et validée par le chef de
    # file et par Breizh Désamiantage, formulaires officiels remplis après elle, journal chaîné — avec
    # le code des routes (app/services/demo_groupement.py). Transaction propre.
    try:
        from app.services.demo_groupement import seed_convention
        seed_convention(db, user, proj_by_key)
    except Exception as e:
        db.rollback()
        logger.warning("seed démo (convention de Kerhel) ignoré : %s", e)

    db.refresh(user)
    logger.info("Compte démo prêt (%s) — 3 AO + %d co-traitants + vitrine complète.", DEMO_EMAIL, len(_COTRAITANTS))
    return user


def _seed_groupement(db, user, comp, proj_by_key, ct_by_name):
    """« Répondre à plusieurs ? » sur la vitrine. Le marché de Kerhel exige un CA de 3 M€ et la
    qualification désamiantage SS3 que Bâtiment de l'Ouest n'a pas ; Breizh Désamiantage les
    apporte. Tout est CALCULÉ par le service pur (score_groupement) — jamais un chiffre codé en
    dur — puis matérialisé : simulation retenue, plan, score et verdict « Bon potentiel en
    groupement ». Les critères v2 du compte démo sont alignés sur _CRITERIA pour que les routes
    (besoins / simulate) recalculent exactement la même chose à l'exécution."""
    from app.models import GroupementSimulation
    from app.routers.criteria_v2 import MatchingCriteriaExt
    from app.services.groupement_verdict import (lead_member, member_from_cotraitant,
                                                  plan_members, scoring_module,
                                                  with_declare_warning)
    from app.services.profile import company_dict
    gs = scoring_module()
    lorient_id = proj_by_key.get("lorient")
    breizh = ct_by_name.get("Breizh Désamiantage")
    if gs is None or not lorient_id or breizh is None:
        return

    ext = db.query(MatchingCriteriaExt).filter(MatchingCriteriaExt.user_id == user.id).first()
    if ext is None:
        ext = MatchingCriteriaExt(user_id=user.id)
        db.add(ext)
    ext.specialites = _CRITERIA["specialites"]
    ext.departements = ", ".join(_CRITERIA["departements"])
    ext.budget_min = _CRITERIA["budget_min"]; ext.budget_max = _CRITERIA["budget_max"]
    ext.go_threshold = _CRITERIA["go_threshold"]
    ext.nogo_threshold = 40   # défaut de score_dce → mêmes verdicts que _analysis()
    db.flush()
    criteria = {col.name: getattr(ext, col.name) for col in ext.__table__.columns}

    lorient = db.query(Project).filter(Project.id == lorient_id).first()
    details = (lorient.ai_analysis or {}).get("details") or {}
    lead = lead_member(company_dict(comp), criteria)
    partner = member_from_cotraitant(breizh, "attached")
    res = gs.score_groupement(details, lead, criteria, [lead, partner]) or {}
    breakdown = res.get("breakdown") or []
    warnings = with_declare_warning([partner], list(res.get("warnings") or []))

    sim = GroupementSimulation(
        project_id=lorient.id, owner_id=user.id, created_by_user_id=user.id,
        members=[lead, partner], score_seul=res.get("score_seul"),
        score_groupement=res.get("score_groupement"), decision=res.get("decision") or "",
        breakdown=breakdown, cumul=res.get("cumul"), gaps=res.get("gaps"),
        warnings=warnings, retained=True)
    db.add(sim); db.flush()

    members = plan_members([partner], breakdown, res.get("gaps_combles"))
    link = db.query(ProjectCotraitant).filter(ProjectCotraitant.project_id == lorient.id,
                                              ProjectCotraitant.cotraitant_id == breizh.id).first()
    if link:
        link.source = "simulation"
        members[0]["link_id"] = link.id
    import datetime as _dt
    lorient.groupement_plan = {
        "members": members, "breakdown": breakdown, "gaps": res.get("gaps") or [],
        "gaps_combles": res.get("gaps_combles") or [], "warnings": warnings,
        "auto": False, "computed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "score_seul": res.get("score_seul"), "score_groupement": res.get("score_groupement"),
        "simulation_id": sim.id,
    }
    lorient.groupement_score = res.get("score_groupement")
    if res.get("decision") == "go_groupement":
        lorient.go_decision = "go_groupement"   # match_score reste le score SEUL
    db.commit()
    logger.info("Vitrine démo : groupement Kerhel calculé — seul %s → avec Breizh %s (%s).",
                res.get("score_seul"), res.get("score_groupement"), res.get("decision"))


def _demo_pdf(title: str, subtitle: str = "") -> bytes:
    """Petit PDF réaliste (titre + mention démo) — pour que les téléchargements du
    coffre-fort et des pièces co-traitant fonctionnent vraiment."""
    from io import BytesIO
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _w, h = A4
    c.setFont("Helvetica-Bold", 15)
    c.drawString(25 * mm, h - 40 * mm, title[:80])
    if subtitle:
        c.setFont("Helvetica", 11)
        c.drawString(25 * mm, h - 50 * mm, subtitle[:95])
    c.setFont("Helvetica", 10)
    c.drawString(25 * mm, h - 70 * mm, "Bâtiment de l'Ouest — SARL — Nantes (44)")
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawString(25 * mm, 18 * mm, "Document de démonstration — généré par Adjugo")
    c.showPage()
    c.save()
    return buf.getvalue()


def _seed_extras(db, user, proj_by_key, ct_by_name):
    """Matérialise TOUTES les fonctionnalités sur le compte démo, comme si une PME
    s'en servait réellement : factures/devis, coffre-fort (avec vrais PDF + alertes
    d'expiration), CERFA générés, veille amont, alertes sauvegardées, base de connaissances
    interrogeable, contacts CRM, espace de co-construction, et le groupement de Kerhel
    instancié (invitation + part soumise + pièces ; la convention et les formulaires du
    groupement viennent ensuite, app/services/demo_groupement.py). Idempotent : purge d'abord
    les entités démo."""
    import datetime
    import secrets
    from datetime import timedelta
    from app.models import (Document, GeneratedDoc, Invoice, Contact, Signal,
                            SavedSearch, KnowledgeDoc, KnowledgeChunk, CoSpace,
                            CoMember, ProjectInvite, ProjectContribution,
                            ContributionPiece, DocCategory, InvoiceType, InvoiceStatus)
    from app.services.storage import get_storage

    uid = user.id
    today = datetime.date.today()
    now = datetime.datetime.now(datetime.timezone.utc)
    toiture = proj_by_key.get("toiture")
    lorient = proj_by_key.get("lorient")

    # ── Idempotence : purge des entités démo de cet utilisateur ──────────────
    for M in (KnowledgeChunk, KnowledgeDoc, Signal, SavedSearch, Invoice, Contact, Document):
        db.query(M).filter(M.user_id == uid).delete(synchronize_session=False)
    space_ids = [s.id for s in db.query(CoSpace).filter(CoSpace.owner_id == uid).all()]
    if space_ids:
        db.query(CoMember).filter(CoMember.space_id.in_(space_ids)).delete(synchronize_session=False)
    db.query(CoSpace).filter(CoSpace.owner_id == uid).delete(synchronize_session=False)
    db.flush()

    # ── Coffre-fort : vrais PDF à clés stables (uploadés une fois, réutilisés) ──
    storage = get_storage()
    try:
        existing = set(storage.list_keys("demo/"))
    except Exception:
        existing = set()

    def _put(key, title, subtitle=""):
        """Range le PDF de démonstration et renvoie SA clé, liée à son titre (demo/kbis_<empreinte>.pdf). Une clé
        déjà stockée n'est jamais réécrite (stockage persistant en production) : sans l'empreinte, un nom de pièce
        changé dans ce fichier laissait le PDF déjà rangé avec l'ancien titre (« Mémoire technique — … » lu
        pendant un pitch). Relancer le seed ne crée aucun fichier tant que les titres ne changent pas."""
        import hashlib
        empreinte = hashlib.sha256((title + "\0" + subtitle).encode("utf-8")).hexdigest()[:12]
        base, ext = key.rsplit(".", 1)
        k = f"{base}_{empreinte}.{ext}"
        if k not in existing:
            try:
                storage.save(k, _demo_pdf(title, subtitle), "application/pdf")
                existing.add(k)
            except Exception as e:
                logger.warning("fichier démo %s non stocké : %s", k, e)
        return k

    # (nom, catégorie, dossier, expiration, project_id, clé)
    DOCS = [
        ("Extrait Kbis — Bâtiment de l'Ouest", DocCategory.administratif, "Pièces administratives", None, None, "demo/kbis.pdf"),
        ("Attestation de régularité fiscale (DGFiP)", DocCategory.fiscal, "Pièces administratives", today + timedelta(days=80), None, "demo/attestation_fiscale.pdf"),
        ("Attestation de vigilance URSSAF", DocCategory.fiscal, "Pièces administratives", today + timedelta(days=22), None, "demo/urssaf.pdf"),
        ("Attestation d'assurance RC professionnelle", DocCategory.assurances, "Pièces administratives", today + timedelta(days=210), None, "demo/rc_pro.pdf"),
        ("Attestation d'assurance décennale", DocCategory.assurances, "Pièces administratives", today + timedelta(days=230), None, "demo/decennale.pdf"),
        ("Certificat Qualibat 3212 — étanchéité de toiture", DocCategory.qualifications, "Pièces administratives", today + timedelta(days=26), None, "demo/qualibat.pdf"),
        ("Attestation RGE", DocCategory.qualifications, "Pièces administratives", today + timedelta(days=240), None, "demo/rge.pdf"),
        ("RIB — Bâtiment de l'Ouest", DocCategory.administratif, "Pièces administratives", None, None, "demo/rib.pdf"),
        ("Liste de références — travaux similaires (< 3 ans)", DocCategory.administratif, "Pièces administratives", None, None, "demo/references.pdf"),
        # Pièces de réponse de l'entreprise fictive (réorganisation, vague 1 : noms sans « Mémoire » ni « DPGF », la
        # carte « Dossier du marché » de la page Toiture les montre pendant un pitch). Le PDF suit le nom : _put
        # range chaque pièce sous une clé liée à son titre.
        ("Dossier de présentation — méthodologie étanchéité", DocCategory.autre, "Mémoire technique", None, toiture, "demo/dossier_presentation_methodologie.pdf"),
        ("Tableau de prix — décomposition du prix global et forfaitaire", DocCategory.autre, "Chiffrage", None, toiture, "demo/tableau_de_prix.pdf"),
        ("DCE — Réfection toiture groupe scolaire Jean Moulin", DocCategory.autre, "DCE", None, toiture, "demo/dce_toiture.pdf"),
    ]
    for name, cat, folder, exp, pid, key in DOCS:
        key = _put(key, name)
        db.add(Document(user_id=uid, name=name, category=cat, file_key=key, file_size=12000,
                        mime_type="application/pdf", folder=folder, expiration_date=exp,
                        project_id=pid, alert_30_sent=True, alert_7_sent=True, alert_day_sent=True))

    # ── Contacts (CRM) ────────────────────────────────────────────────────────
    for n, role, org, ctype, email, phone, addr, note in [
        ("Sabine Vidal", "Responsable de la commande publique", "Ville de Marvejac", "maitre_ouvrage", "marches@ville-marvejac.exemple", "", "Hôtel de ville, Marvejac (33)", "Interlocutrice marchés bâtiment — réactive, privilégie le dépôt dématérialisé."),
        ("Atelier Lumenval Architectes", "Architecte chef de file (maîtrise d'œuvre)", "Atelier Lumenval", "partenaire", "contact@atelier-lumenval.exemple", "", "Lyon (69)", "MOE sur plusieurs marchés scolaires — bon relais pour les visites de site."),
        # Fournisseur FICTIF (jamais une vraie enseigne avec un contact inventé).
        ("Service comptes pro — Négoce des Matériaux de l'Ouest", "Responsable comptes professionnels", "Négoce des Matériaux de l'Ouest (fictif)", "fournisseur", "pro@negoce-materiaux-ouest.exemple", "", "ZA de la Lande, 44000 Nantes", "Conditions cadre négociées sur l'étanchéité et l'isolation."),
    ]:
        db.add(Contact(user_id=uid, name=n, role=role, organization=org, contact_type=ctype, email=email, phone=phone, address=addr, notes=note))

    # ── Devis & factures ──────────────────────────────────────────────────────
    def _inv(ref, itype, status, client, items, project_id, issue, due=None, paid=None, notes=""):
        sub = sum(it["qty"] * it["unit_price"] for it in items)
        tva = round(sub * 20.0 / 100, 2)
        db.add(Invoice(user_id=uid, reference=ref, type=itype, status=status, client_name=client,
                       items=items, subtotal_ht=sub, tva_rate=20.0, tva_amount=tva,
                       total_ttc=round(sub + tva, 2), issue_date=issue, due_date=due,
                       paid_date=paid, project_id=project_id, notes=notes))

    _inv("DEV-2026-0142", InvoiceType.devis, InvoiceStatus.brouillon, "Ville de Marvejac",
         [{"description": "Réfection toiture et étanchéité — groupe scolaire Jean Moulin (lot unique)", "qty": 1, "unit_price": 468500}],
         toiture, today - timedelta(days=20), due=today + timedelta(days=10),
         notes="Devis préparé pour l'offre (à joindre au dépôt) — réf. marché DEMO-25114207.")
    _inv("FAC-2026-0087", InvoiceType.facture, InvoiceStatus.paye, "Ville de Bréhaut",
         [{"description": "Réfection de la couverture — école élémentaire", "qty": 1, "unit_price": 96000}],
         None, today - timedelta(days=95), due=today - timedelta(days=65), paid=today - timedelta(days=70))
    _inv("AV-2026-0009", InvoiceType.avoir, InvoiceStatus.envoye, "Ville de Bréhaut",
         [{"description": "Avoir — ajustement de métré lot zinguerie", "qty": 1, "unit_price": -2400}],
         None, today - timedelta(days=40))

    # ── Veille amont : signaux d'investissement détectés en amont des AO ───────
    signaux_demo = [
        dict(intitule="Construction d'un pôle enfance (crèche + ALSH)", type_projet="construction",
             budget=3200000, budget_texte="3,2 M€ HT", localisation="Villebrune (28)",
             collectivite="Ville de Villebrune", calendrier="Appel d'offres probable T4 2026",
             metiers=["gros œuvre", "toiture", "étanchéité", "isolation"],
             extrait="« …le conseil approuve l'enveloppe prévisionnelle de 3,2 M€ HT pour la construction du pôle enfance, financée par la DETR et l'autofinancement… »",
             pertinence="pertinent", pertinence_score=84, source_name="Délibération du conseil municipal de Villebrune",
             source_url="/static/demo/deliberation.html", source_date="2026-05-14",
             domaine="bâtiment", phase="financement voté", echeance_ao="T4 2026",
             financement="DETR + autofinancement", maturite=78),
        dict(intitule="Rénovation thermique du groupe scolaire des Sables Blancs", type_projet="rénovation",
             budget=1400000, budget_texte="1,4 M€ HT", localisation="Valdôme (63)",
             collectivite="Agglomération de Valdôme", calendrier="Appel d'offres probable T1 2027",
             metiers=["isolation", "couverture", "menuiserie"],
             extrait="« …inscription au plan pluriannuel d'investissement de la rénovation énergétique du groupe scolaire, demande de subvention DSIL en cours… »",
             pertinence="pertinent", pertinence_score=73, source_name="PPI 2026-2028 — Agglomération de Valdôme",
             source_url="/static/demo/deliberation.html", source_date="2026-04-02",
             domaine="bâtiment", phase="programmation", echeance_ao="T1 2027",
             financement="DSIL", maturite=60),
        dict(intitule="Réhabilitation de la salle des sports municipale", type_projet="rénovation",
             budget=900000, budget_texte="≈ 900 k€ HT", localisation="Larzagues (12)",
             collectivite="Commune de Larzagues", calendrier="à confirmer",
             metiers=["gros œuvre", "toiture", "désamiantage"],
             extrait="« …lancement d'une étude de faisabilité pour la réhabilitation de la salle des sports, présence d'amiante à confirmer par diagnostic… »",
             pertinence="a_etudier", pertinence_score=58, source_name="Compte-rendu de la commission travaux — Larzagues",
             source_url="/static/demo/deliberation.html", source_date="2026-03-19",
             domaine="bâtiment", phase="étude", echeance_ao="",
             financement="à définir", maturite=40),
    ]
    # « Projets à venir » masqué (PROJETS_A_VENIR=0) jusqu'à la vague 1 de l'étude veille : la vitrine
    # ne les montre plus (la purge ci-dessus a retiré ceux d'avant). Exemples gardés pour la refonte.
    from app.core.interrupteurs import projets_a_venir_actif
    for sig in (signaux_demo if projets_a_venir_actif() else []):
        db.add(Signal(user_id=uid, **sig))

    # ── Alertes sauvegardées (veille AO) ──────────────────────────────────────
    db.add(SavedSearch(user_id=uid, name="Réfection toiture / étanchéité — France",
                       query="toiture étanchéité couverture", cpv=["45261000", "45260000"],
                       type_marche="travaux", departements=["44", "33", "31", "69", "13"], countries=[],
                       frequency="quotidienne", active=True, min_score=70,
                       last_run=now - timedelta(hours=6)))
    db.add(SavedSearch(user_id=uid, name="Rénovation énergétique — bâtiments publics",
                       query="rénovation énergétique isolation thermique", cpv=["45321000"],
                       type_marche="travaux", departements=["67", "59", "35"], countries=[],
                       frequency="hebdomadaire", active=True, min_score=65,
                       last_run=now - timedelta(days=2)))

    # ── Base de connaissances (RAG cité) : mémoires & RSE chunkés, interrogeables ──
    def _kb(name, kind, chunks):
        full = "\n\n".join(chunks)
        kd = KnowledgeDoc(user_id=uid, name=name, kind=kind, text=full,
                          char_count=len(full), n_chunks=len(chunks))
        db.add(kd); db.flush()
        for i, ch in enumerate(chunks):
            db.add(KnowledgeChunk(doc_id=kd.id, user_id=uid, ordinal=i, text=ch, doc_name=name))

    _kb("Mémoire technique — Réfection toiture école de Bréhaut (2024)", "memoire", [
        "Méthodologie d'étanchéité : dépose soignée de la couverture existante, contrôle du support, pose d'un pare-vapeur, d'une isolation thermique en polyuréthane et d'une membrane d'étanchéité bicouche soudée. Relevés et zinguerie traités en points singuliers.",
        "Sécurité et chantier en site occupé : installation de protections collectives (garde-corps périphériques, filets), phasage permettant le maintien de l'activité scolaire, nettoyage quotidien et évacuation des déchets en filière agréée.",
        "Planning d'exécution : préparation (1 semaine), dépose et reprise du support (2 semaines), isolation et étanchéité (4 semaines), zinguerie et finitions (2 semaines), réception et levée de réserves (1 semaine).",
        "Références similaires : 12 réfections de toitures scolaires conduites sur les 5 dernières années partout en France, dont l'école élémentaire de Bréhaut (2024) et le centre technique de Lesparrac (2023).",
        "Engagements environnementaux : tri des déchets de chantier, valorisation des matériaux, recours à des isolants biosourcés lorsque le CCTP le permet, démarche RGE.",
    ])
    _kb("Politique RSE & clause d'insertion sociale", "rse", [
        "Insertion sociale : Bâtiment de l'Ouest conventionne des structures d'insertion par l'activité économique (SIAE) locales pour réaliser les heures d'insertion exigées dans les marchés publics. 1 040 heures réalisées en 2025.",
        "Démarche environnementale : entreprise RGE, tri et valorisation des déchets de chantier, optimisation des tournées et bilan carbone suivi annuellement.",
        "Sécurité et conditions de travail : 0 accident avec arrêt en 2025, formations régulières (travail en hauteur, désamiantage sous-section 4), encadrement QSE dédié.",
    ])

    # ── Co-construction et groupement : Kerhel entièrement instancié ──────────
    invite_ids = None
    if lorient:
        breizh = ct_by_name.get("Breizh Désamiantage")
        breizh_siret = (breizh.siret if breizh else "") or "53219876500011"

        invite = ProjectInvite(
            token=secrets.token_hex(24), project_id=lorient, owner_id=uid,
            recipient="contact@breizh-desamiantage.exemple", company_name="Breizh Désamiantage",
            can_view_docs=True, role="cotraitant", can_contribute=True, revoked=False,
            view_count=4, last_viewed_at=now)
        # Aucune adresse « vérifiée par code » : la démo n'en envoie aucun. L'accord du partenaire
        # porte donc le niveau d'identité réellement prouvé par le lien (identité non vérifiée).
        db.add(invite); db.flush()
        # Le partenaire rattaché au marché EST celui qui a été invité (comme après une invitation
        # depuis le réseau) : sans ce lien, « Monter le groupement » le disait « ni invité ni ajouté
        # hors ligne » et le comptait à part.
        if breizh is not None:
            lk = (db.query(ProjectCotraitant).filter(ProjectCotraitant.project_id == lorient,
                                                     ProjectCotraitant.cotraitant_id == breizh.id).first())
            if lk is not None:
                lk.invite_id = invite.id

        contrib = ProjectContribution(
            invite_id=invite.id, project_id=lorient, owner_id=uid,
            company_name="Breizh Désamiantage", role="cotraitant",
            lot="Lot 1 — Désamiantage et retrait d'amiante (SS3)", siret=breizh_siret,
            forme_juridique="SAS", address="8 rue de l'Industrie", postal_code="56100", city="Lorient",
            references=[
                {"intitule": "Désamiantage avant démolition d'un EHPAD", "client": "Kerhel Agglomération", "montant": 320000, "annee": 2024},
                {"intitule": "Retrait d'amiante en toiture d'un gymnase", "client": "Commune de Plouvarec", "montant": 185000, "annee": 2023},
            ],
            qualifications=["Qualification désamiantage SS3", "Certification amiante sous-section 3", "Assurance amiante"],
            # Doctrine de visibilité : le mandataire ne voit que le PRIX DE VENTE du lot ;
            # la décomposition (detail_chiffre) serait chiffrée dans le navigateur du membre.
            prix_lot_ht=280000.0,
            # Mêmes capacités que sa fiche dans « Mes partenaires » (comme après _sync_annuaire_capacites).
            capacites={"ca_n1": 2100000, "effectif": 18, "declared_at": now.isoformat()},
            representant_legal="Soizic Morvan", signataire_qualite="Présidente",
            memoire_paragraph="Breizh Désamiantage réalise le retrait d'amiante en sous-section 3 conformément au plan de retrait validé. Confinement dynamique, contrôles d'empoussièrement libératoires et traçabilité complète des déchets (BSDA).",
            contact={"nom": "Soizic Morvan", "email": "contact@breizh-desamiantage.exemple", "telephone": ""},
            status="submitted", submitted_at=now, version=1)
        db.add(contrib); db.flush()
        invite_ids = (invite.id, contrib.id)

        for pname, pkey, ptype, pexp in [
                ("Kbis — Breizh Désamiantage", "demo/breizh_kbis.pdf", "kbis",
                 today + timedelta(days=75)),
                ("Attestation de qualification désamiantage SS3 — Breizh Désamiantage", "demo/breizh_ss3.pdf",
                 "qualification", today + timedelta(days=400)),
                # Coffre croisé (vague 4) : les attestations attendues de chaque membre pour le dépôt.
                ("Attestation de régularité fiscale — Breizh Désamiantage", "demo/breizh_fiscale.pdf",
                 "fiscale", today + timedelta(days=150)),
                ("Attestation de vigilance URSSAF — Breizh Désamiantage", "demo/breizh_urssaf.pdf",
                 "sociale", today + timedelta(days=95)),
                ("Attestation d'assurance RC et décennale — Breizh Désamiantage", "demo/breizh_assurance.pdf",
                 "assurance", today + timedelta(days=320)),
                ("RIB — Breizh Désamiantage", "demo/breizh_rib.pdf", "rib", None)]:
            pkey = _put(pkey, pname)
            db.add(ContributionPiece(contribution_id=contrib.id, project_id=lorient, owner_id=uid,
                                     name=pname, file_key=pkey, file_size=11000, mime_type="application/pdf",
                                     piece_type=ptype, expiration_date=pexp))

        space = CoSpace(owner_id=uid, name="Groupement — Gymnase de Kerhel",
                        marche="Réhabilitation énergétique et désamiantage du gymnase municipal de Kerhel",
                        warroom={"lots": [
                            {"lot": "Lot 1 — Désamiantage SS3", "attribue": "Breizh Désamiantage"},
                            {"lot": "Lot 2 — Isolation / rénovation énergétique", "attribue": "Bâtiment de l'Ouest (chef de file)"},
                            {"lot": "Lot 3 — Gros œuvre & étanchéité", "attribue": "Bâtiment de l'Ouest (chef de file)"},
                        ]})
        db.add(space); db.flush()
        db.add(CoMember(space_id=space.id, user_id=uid, role="mandataire", status="accepted",
                        company_name="Bâtiment de l'Ouest"))
        db.add(CoMember(space_id=space.id, email="contact@breizh-desamiantage.exemple", role="cotraitant",
                        status="accepted", token=secrets.token_hex(16), company_name="Breizh Désamiantage"))

    # ── CERFA générés (régénérés à la volée au téléchargement) ────────────────
    def _gen(pid, types):
        for t in types:
            db.add(GeneratedDoc(project_id=pid, doc_type=t, status="pret",
                                filled_data={"company": "Bâtiment de l'Ouest", "project": str(pid)}))

    if toiture:
        _gen(toiture, ["dc1", "dc2", "honneur", "attri1"])
    if lorient:
        # Déclaration sur l'honneur ; DC1, DC2 et ATTRI1 du groupement sont remplis APRÈS la convention
        # (demo_groupement.seed_convention). Pas de DC4 : Breizh Désamiantage est co-traitant, pas
        # sous-traitant. Ceux-ci restent si la convention de la vitrine ne se fait pas.
        _gen(lorient, ["dc1", "dc2", "honneur"])

    # ── Historique d'AO décidés (gagné/perdu) : peuple le tableau de bord ──────
    # Win-rate, pipeline et analytics n'ont de sens qu'avec des marchés clôturés.
    from app.models import ProjectStatus
    PAST = [
        dict(name="Réfection de toiture-terrasse — médiathèque d'Anjoumont", client="Ville d'Anjoumont",
             budget=212000, status=ProjectStatus.gagne, ref="DEMO-24098112",
             outcome_rank=1, awarded_amount=212000, outcome_reason="Offre la mieux-disante (valeur technique 60 %).",
             details={"intitule_marche": "Réfection de la toiture-terrasse d'étanchéité de la médiathèque municipale",
                      "acheteur": "Ville d'Anjoumont",
                      "contact": {"nom": "Christophe Marchand", "fonction": "Direction des bâtiments", "email": "marches@ville-anjoumont.exemple", "telephone": ""},
                      "type_marche": "Travaux", "nature_marche": "Marché à procédure adaptée (MAPA)", "forme_prix": "Prix global et forfaitaire",
                      "budget_estime": "212 000 EUR HT",
                      "delai_execution": "4 mois à compter de l'ordre de service", "lieu_execution": "Anjoumont (49)", "allotissement": "Lot unique",
                      "criteres_attribution": [{"critere": "Valeur technique", "ponderation": "60%"}, {"critere": "Prix", "ponderation": "40%"}],
                      "garanties_exigees": "Retenue de garantie 5%", "penalites": "1/1000 du montant HT par jour, plafonnées à 8%",
                      "avance": "Avance de 10% (marché > 50 000 EUR HT)", "sous_traitance": "Autorisée — déclaration DC4",
                      "variantes": "Autorisées sur le complexe d'étanchéité", "critere_rse": "Oui — valorisation des déchets de chantier",
                      "ca_minimum_requis": "CA > 800 000 EUR sur 3 ans", "qualifications_requises": ["Qualibat 3212", "RGE"],
                      "assurances_requises": ["RC Professionnelle", "Garantie décennale"],
                      "visite_obligatoire": "Recommandée, sur rendez-vous",
                      "points_attention": ["Site occupé (médiathèque ouverte au public) — phasage et sécurité", "Critère technique prépondérant (60%)", "Étanchéité de toiture-terrasse : soigner le complexe et les relevés"],
                      "recommandation": "Réfection de la toiture-terrasse d'étanchéité de la médiathèque municipale d'Anjoumont, en lot unique pour 212 000 € HT. Cible idéale sur le papier : étanchéité de toiture-terrasse, cœur de métier, zone couverte, qualifications détenues (Qualibat 3212, RGE), budget dans votre fourchette.\n\nLe marché s'est joué sur la valeur technique (60 %). L'offre a mis l'accent sur la méthodologie d'étanchéité (complexe et relevés), sur la gestion d'un équipement recevant du public maintenu en activité (phasage, sécurité) et sur un planning maîtrisé. La retenue de garantie a été neutralisée par une caution de substitution.\n\nRésultat : marché remporté comme offre la mieux-disante. À conserver comme référence type pour les prochains marchés d'étanchéité de bâtiments publics — un dossier de présentation soigné fait la décision quand la technique pèse plus lourd que le prix.\n\nEn retour d'expérience, deux facteurs ont pesé. D'abord, la visite de site en amont : elle a permis d'identifier les contraintes d'accès et l'état réel des relevés existants, puis de les traiter explicitement dans le dossier de présentation — un signal de sérieux pour l'acheteur. Ensuite, la clarté du phasage proposé pour maintenir la médiathèque ouverte pendant les travaux, qui a rassuré sur la maîtrise des nuisances et de la sécurité du public.\n\nCe marché constitue désormais une référence solide à citer sur les prochains appels d'offres d'étanchéité de bâtiments recevant du public : même typologie de chantier, même exigence de valeur technique, même logique de site occupé. C'est ce type de référence réutilisable qui renforce, marché après marché, la crédibilité de vos futures candidatures.",
                      "clauses_risque": [
                          {"clause": "Retenue de garantie", "niveau": "faible", "pourquoi": "5% retenus pendant 1 an", "levier_negociation": "Caution bancaire de substitution (art. R2191-33)"},
                          {"clause": "Site occupé", "niveau": "moyen", "pourquoi": "Médiathèque ouverte au public pendant les travaux", "levier_negociation": "Proposer un phasage et des protections dans le dossier de présentation"},
                          {"clause": "Pénalités de retard", "niveau": "faible", "pourquoi": "1/1000 du HT par jour, plafond 8%", "levier_negociation": "Demander une franchise de 5 jours ouvrés"},
                      ]},
             summary="Réfection de toiture-terrasse à Anjoumont — métier et zone alignés. Marché remporté en 2024.",
             pieces=["Attestation Qualibat 3212 (en cours de validité)", "Attestation RGE", "Mémoire technique — méthodologie étanchéité toiture-terrasse", "3 références de toitures-terrasses (< 3 ans)", "Attestation d'assurance décennale", "DC1, DC2 et attestations fiscales et sociales à jour"]),
        dict(name="Couverture et zinguerie — école de Riquebach", client="Ville de Riquebach",
             budget=138000, status=ProjectStatus.gagne, ref="DEMO-24061330",
             outcome_rank=1, awarded_amount=138000, outcome_reason="Meilleur rapport valeur technique / prix.",
             details={"intitule_marche": "Réfection de la couverture et de la zinguerie du groupe scolaire",
                      "acheteur": "Ville de Riquebach",
                      "contact": {"nom": "Sylvie Muller", "fonction": "Service de la commande publique", "email": "marches@ville-riquebach.exemple", "telephone": ""},
                      "type_marche": "Travaux", "nature_marche": "Marché à procédure adaptée (MAPA)", "forme_prix": "Prix global et forfaitaire",
                      "budget_estime": "138 000 EUR HT",
                      "delai_execution": "3 mois — travaux hors période scolaire", "lieu_execution": "Riquebach (68)", "allotissement": "Lot unique",
                      "criteres_attribution": [{"critere": "Valeur technique", "ponderation": "50%"}, {"critere": "Prix", "ponderation": "50%"}],
                      "garanties_exigees": "Retenue de garantie 5%", "penalites": "1/1000 du montant HT par jour, plafonnées à 10%",
                      "avance": "Avance de 10%", "sous_traitance": "Autorisée — déclaration DC4",
                      "variantes": "Non autorisées", "critere_rse": "Oui — clause d'insertion sociale (100 h)",
                      "ca_minimum_requis": "CA > 500 000 EUR sur 3 ans", "qualifications_requises": ["Qualibat 3212"],
                      "assurances_requises": ["RC Professionnelle", "Garantie décennale"],
                      "visite_obligatoire": "Recommandée",
                      "points_attention": ["Site scolaire — travaux impérativement pendant les vacances", "Zinguerie et raccords soignés (bâtiment ancien)", "Prix et technique à parité (50/50)"],
                      "recommandation": "Réfection de la couverture et de la zinguerie du groupe scolaire de Riquebach, en lot unique pour 138 000 € HT. Couverture/zinguerie en plein cœur de métier, budget aligné, qualification Qualibat 3212 détenue.\n\nLa contrainte structurante était le calendrier : bâtiment scolaire, les travaux devaient impérativement être réalisés hors présence des élèves, sur les périodes de vacances. L'offre a donc mis en avant un planning verrouillé et un approvisionnement anticipé, en plus du soin apporté à la zinguerie et aux raccords d'un bâtiment ancien. Les 100 h d'insertion ont été sécurisées via une structure locale.\n\nAvec des critères prix et technique à parité (50/50), c'est le meilleur rapport valeur technique/prix qui l'a emporté : marché remporté. Enseignement : sur les chantiers scolaires, la maîtrise du calendrier est un argument différenciant à part entière.\n\nLe point différenciant a été la crédibilité du planning. Sur un marché scolaire, l'acheteur redoute avant tout un chantier qui déborde sur la rentrée : montrer, jalons et chiffres à l'appui, que les travaux tiennent dans les fenêtres de vacances — avec une marge et un approvisionnement sécurisé en amont — vaut souvent plus qu'un écart de quelques points sur le prix.\n\nÀ retenir pour les prochains marchés de couverture en site scolaire : construire l'offre autour de la contrainte de calendrier plutôt que de la subir. Un rétroplanning détaillé, une commande de matériaux anticipée et une équipe dédiée sur la période sont des arguments concrets, faciles à vérifier par l'acheteur, et difficiles à égaler pour un concurrent qui n'aurait pas anticipé.",
                      "clauses_risque": [
                          {"clause": "Délai contraint (vacances scolaires)", "niveau": "moyen", "pourquoi": "Travaux à caler impérativement hors période scolaire", "levier_negociation": "Sécuriser le planning et l'approvisionnement en amont"},
                          {"clause": "Retenue de garantie", "niveau": "faible", "pourquoi": "5% retenus pendant 1 an", "levier_negociation": "Caution bancaire de substitution"},
                          {"clause": "Clause d'insertion sociale", "niveau": "faible", "pourquoi": "100 h d'insertion à réaliser", "levier_negociation": "Conventionner une structure d'insertion locale"},
                      ]},
             summary="Couverture et zinguerie d'une école à Riquebach — cœur de métier. Marché remporté en 2024.",
             pieces=["Attestation Qualibat 3212", "Mémoire technique — couverture et zinguerie", "3 références de couvertures scolaires (< 3 ans)", "Attestation d'assurance décennale", "Planning prévisionnel (travaux hors période scolaire)", "DC1, DC2 et attestations à jour"]),
        dict(name="Rénovation de couverture — gendarmerie de Limauzac", client="Ville de Limauzac",
             budget=175000, status=ProjectStatus.perdu, ref="DEMO-24076550",
             outcome_rank=2, competitor_winner="SARL Couvertures du Val de Limauzac",
             outcome_reason="Classé 2e — offre supérieure de 6 % au prix retenu.",
             details={"intitule_marche": "Rénovation de la couverture de la caserne de gendarmerie",
                      "acheteur": "Ville de Limauzac",
                      "contact": {"nom": "Service de la commande publique", "fonction": "Marchés bâtiment", "email": "marches@ville-limauzac.exemple", "telephone": ""},
                      "type_marche": "Travaux", "nature_marche": "Appel d'offres ouvert", "forme_prix": "Prix global et forfaitaire",
                      "budget_estime": "175 000 EUR HT",
                      "delai_execution": "4 mois", "lieu_execution": "Limauzac (87)", "allotissement": "Lot unique",
                      "criteres_attribution": [{"critere": "Prix", "ponderation": "60%"}, {"critere": "Valeur technique", "ponderation": "40%"}],
                      "garanties_exigees": "Retenue de garantie 5% + garantie décennale", "penalites": "1/1000 du montant HT par jour",
                      "avance": "Avance de 5%", "sous_traitance": "Autorisée",
                      "variantes": "Non autorisées", "critere_rse": "Non",
                      "ca_minimum_requis": "CA > 600 000 EUR sur 3 ans", "qualifications_requises": ["Qualibat 3212"],
                      "assurances_requises": ["RC Professionnelle", "Garantie décennale"],
                      "visite_obligatoire": "Obligatoire (site sensible — attestation exigée)",
                      "points_attention": ["Critère PRIX prépondérant (60%) — marché très concurrentiel", "Site sensible (gendarmerie) : contrôles d'accès et habilitations", "Faible marge de manœuvre sur le prix face aux acteurs locaux"],
                      "recommandation": "Rénovation de la couverture de la caserne de gendarmerie de Limauzac, pour 175 000 € HT, portée par la Ville de Limauzac, propriétaire du bâtiment. Métier et zone alignés, mais un profil de marché défavorable : le critère prix pesait 60 %, sur un secteur où des acteurs locaux sont très compétitifs.\n\nDeux spécificités : un site sensible (contrôles d'accès, habilitations du personnel) et une visite obligatoire sous peine d'irrecevabilité — deux points bien traités dans l'offre. Le dossier de présentation était solide, mais sur un marché à dominante prix, il ne suffit pas à compenser un écart tarifaire.\n\nRésultat : offre classée 2e, à 6 % du prix retenu. L'enseignement est net : sur ce type de marché où le prix prime, il faut viser un tarif plus agressif — en optimisant les coûts (approvisionnement, phasage, sous-traitance) plutôt que la marge. Défaite instructive, à capitaliser pour les prochains marchés à dominante prix.\n\nAu-delà du prix, l'analyse a posteriori montre que le marché était structurellement difficile : dominante prix, forte densité d'acteurs locaux déjà implantés et faible différenciation possible sur une rénovation de couverture standard. Sur ce profil, la marge de manœuvre technique est limitée — l'écart se joue à quelques pour-cent près sur le prix.\n\nL'enseignement opérationnel est double. D'une part, sur les marchés à dominante prix, il faut décider tôt si l'on est prêt à comprimer la marge, ou renoncer et réserver son énergie à des marchés où la valeur technique compte davantage. D'autre part, une deuxième place à 6 % du prix retenu reste une candidature crédible : elle mérite d'être analysée finement pour ajuster le curseur tarifaire sur les prochaines consultations de même nature.",
                      "clauses_risque": [
                          {"clause": "Critère prix prépondérant (60%)", "niveau": "eleve", "pourquoi": "Marché attribué quasiment au moins-disant, forte concurrence locale", "levier_negociation": "Optimiser les coûts (approvisionnement, phasage) plutôt que la marge"},
                          {"clause": "Site sensible", "niveau": "moyen", "pourquoi": "Contrôles d'accès et habilitations du personnel", "levier_negociation": "Anticiper les demandes d'habilitation dès la notification"},
                          {"clause": "Visite obligatoire", "niveau": "faible", "pourquoi": "Attestation de visite exigée sous peine d'irrecevabilité", "levier_negociation": "Planifier la visite dès la parution de l'avis"},
                      ]},
             summary="Rénovation de couverture à Limauzac — métier et zone alignés. Offre classée 2e (prix) en 2024.",
             pieces=["Attestation Qualibat 3212", "Mémoire technique — rénovation de couverture", "Attestation de visite obligatoire", "Attestation d'assurance décennale", "DC1, DC2 et attestations fiscales et sociales", "Références de chantiers en site occupé / sensible"]),
    ]
    for p in PAST:
        ai = _analysis(p["details"], p["summary"], p["ref"], p["pieces"])
        db.add(Project(user_id=uid, name=p["name"], client=p["client"], budget=p["budget"],
                       status=p["status"], source_url=ai["source"]["source_url"],
                       match_score=ai["match_score"], go_decision=ai["go_decision"],
                       ai_summary=ai["summary"], ai_analysis=ai,
                       outcome_rank=p.get("outcome_rank"), awarded_amount=p.get("awarded_amount"),
                       outcome_reason=p.get("outcome_reason"), competitor_winner=p.get("competitor_winner")))

    db.commit()
    # Journal chaîné du groupement (après le commit, comme les routes) : invitation créée par le chef
    # de file, part soumise par le partenaire. Best-effort (audit.record n'échoue jamais).
    if lorient and invite_ids:
        from app.services import audit
        inv_id, contrib_id = invite_ids
        audit.record(db, action="invite.created", owner_id=uid, project_id=lorient, actor=f"user:{uid}",
                     actor_kind="owner", target_type="invite", target_id=inv_id, invite_id=inv_id,
                     detail="Breizh Désamiantage")
        audit.record(db, action="guest.submit_contribution", owner_id=uid, project_id=lorient,
                     actor="Breizh Désamiantage", actor_kind="guest", target_type="contribution",
                     target_id=contrib_id, invite_id=inv_id, detail="Breizh Désamiantage")
    logger.info("Vitrine démo : coffre-fort, factures, veille amont, KB, groupement Kerhel, "
                "%d AO décidés (win-rate) seedés.", len(PAST))
