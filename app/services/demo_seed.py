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


# Réseau de co-traitants de démonstration (rattachés à certains AO) — fiches complètes.
_COTRAITANTS = [
    dict(name="Charpentes du Léon", siret="51234567800018", code_ape="4391A", city="Landerneau",
         departement="29", specialites="Charpente bois, ossature, couverture", ca_n1=820000, effectif=9,
         forme_juridique="SARL", representant_legal="Hervé Quéméner", email="contact@charpentes-leon.fr",
         phone="02 98 85 21 40", codes_cpv="45261000, 45422000",
         qualifications="Qualibat 2392 (charpente bois), RGE", attach=[("toiture", "cotraitant", "")]),
    dict(name="Zinguerie Bigoudène", siret="48765432100027", code_ape="4391B", city="Pont-l'Abbé",
         departement="29", specialites="Couverture, zinguerie, étanchéité", ca_n1=540000, effectif=6,
         forme_juridique="SARL", representant_legal="Loïc Le Berre", email="contact@zinguerie-bigoudene.fr",
         phone="02 98 87 33 12", codes_cpv="45261000, 45261210",
         qualifications="Qualibat 3411 (zinguerie)", attach=[("toiture", "cotraitant", "")]),
    dict(name="Breizh Désamiantage", siret="53219876500011", code_ape="4399A", city="Lorient",
         departement="56", specialites="Désamiantage SS3, dépose amiante, retrait", ca_n1=2100000, effectif=18,
         forme_juridique="SAS", representant_legal="Soizic Morvan", email="contact@breizh-desamiantage.fr",
         phone="02 97 84 22 10", codes_cpv="45262660",
         qualifications="Qualification désamiantage SS3, certification amiante sous-section 3",
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
    comp.name = "Bâtiment de l'Ouest"; comp.siret = DEMO_SIRET
    comp.code_ape = "4391A"   # travaux de couverture par éléments
    comp.forme_juridique = "SARL"; comp.capital = "50 000 €"
    comp.representant_legal = "Gwénaël Le Bihan, gérant"
    comp.address = "12 rue des Chantiers, ZA de Kerlann"
    comp.city = "Quimper"; comp.postal_code = "29000"
    comp.tva_intracom = "FR" + DEMO_SIRET[:11]   # FR + clé + SIREN (format vitrine)
    comp.phone = "02 98 52 14 30"; comp.email = "contact@batiment-ouest.fr"
    comp.ca_n1 = 1250000; comp.ca_n2 = 1100000; comp.ca_n3 = 980000; comp.effectif = 14
    comp.qualifications = _COMPANY["qualifications"]
    comp.references = [
        {"intitule": "Réfection de la couverture de l'école élémentaire", "client": "Commune de Pluguffan", "montant": 96000, "annee": 2024},
        {"intitule": "Étanchéité-toiture du centre technique municipal", "client": "Quimper Bretagne Occidentale", "montant": 182000, "annee": 2023},
        {"intitule": "Rénovation thermique d'un groupe scolaire (lot couverture/isolation)", "client": "Commune de Briec", "montant": 145000, "annee": 2023},
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
                            ProjectContribution, ContributionPiece, AuditLog)
    old_ids = [p.id for p in db.query(Project).filter(Project.user_id == user.id).all()]
    if old_ids:
        # Ordre : enfants des contributions/invites d'abord, puis le reste. TOUTES les
        # tables qui référencent projects doivent être purgées sinon la FK bloque le reseed
        # (ex. project_invites créés en testant la co-traitance).
        for M in (ContributionPiece, ProjectContribution, ProjectInvite,
                  ProjectCotraitant, Document, GeneratedDoc, Invoice, AuditLog):
            db.query(M).filter(M.project_id.in_(old_ids)).delete(synchronize_session=False)
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

    # Vitrine complète : factures, coffre-fort, CERFA (dont DC4 du consortium), veille
    # amont, alertes, base de connaissances, contacts, consortium Lorient matérialisé…
    # Isolé dans sa propre transaction : un échec ici n'altère jamais le cœur de la démo.
    try:
        _seed_extras(db, user, proj_by_key, ct_by_name)
    except Exception as e:
        db.rollback()
        logger.warning("seed démo (extras) ignoré : %s", e)

    db.refresh(user)
    logger.info("Compte démo prêt (%s) — 3 AO + %d co-traitants + vitrine complète.", DEMO_EMAIL, len(_COTRAITANTS))
    return user


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
    c.drawString(25 * mm, h - 70 * mm, "Bâtiment de l'Ouest — SARL — Quimper (29)")
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawString(25 * mm, 18 * mm, "Document de démonstration — généré par Adjugo")
    c.showPage()
    c.save()
    return buf.getvalue()


def _seed_extras(db, user, proj_by_key, ct_by_name):
    """Matérialise TOUTES les fonctionnalités sur le compte démo, comme si une PME
    s'en servait réellement : factures/devis, coffre-fort (avec vrais PDF + alertes
    d'expiration), CERFA générés (dont le DC4 du consortium), veille amont, alertes
    sauvegardées, base de connaissances interrogeable, contacts CRM, espace de
    co-construction, et le consortium de Lorient entièrement instancié (invitation +
    contribution soumise + pièces). Idempotent : purge d'abord les entités démo."""
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
        if key not in existing:
            try:
                storage.save(key, _demo_pdf(title, subtitle), "application/pdf")
                existing.add(key)
            except Exception as e:
                logger.warning("fichier démo %s non stocké : %s", key, e)
        return key

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
        ("Mémoire technique — méthodologie étanchéité", DocCategory.autre, "Mémoire technique", None, toiture, "demo/memoire_methodologie.pdf"),
        ("DPGF — bordereau de décomposition des prix", DocCategory.autre, "Chiffrage", None, toiture, "demo/dpgf.pdf"),
        ("DCE — Réfection toiture groupe scolaire Jean Moulin", DocCategory.autre, "DCE", None, toiture, "demo/dce_toiture.pdf"),
    ]
    for name, cat, folder, exp, pid, key in DOCS:
        _put(key, name)
        db.add(Document(user_id=uid, name=name, category=cat, file_key=key, file_size=12000,
                        mime_type="application/pdf", folder=folder, expiration_date=exp,
                        project_id=pid, alert_30_sent=True, alert_7_sent=True, alert_day_sent=True))

    # ── Contacts (CRM) ────────────────────────────────────────────────────────
    for n, role, org, ctype, email, phone, addr, note in [
        ("Marie Le Goff", "Responsable de la commande publique", "Ville de Quimper", "maitre_ouvrage", "marches@mairie-quimper.fr", "02 98 98 89 89", "44 place Saint-Corentin, 29000 Quimper", "Interlocutrice marchés bâtiment — réactive, privilégie le dépôt dématérialisé."),
        ("Atelier Kermarrec Architectes", "Architecte mandataire (maîtrise d'œuvre)", "Atelier Kermarrec", "partenaire", "contact@kermarrec-archi.fr", "02 98 55 12 30", "9 rue du Parc, 29000 Quimper", "MOE sur plusieurs marchés scolaires — bon relais pour les visites de site."),
        ("Service comptes pro — Point P", "Responsable comptes professionnels", "Point P — Saint-Gobain Distribution", "fournisseur", "pro.quimper@pointp.fr", "02 98 90 44 10", "ZI de l'Hippodrome, 29000 Quimper", "Conditions cadre négociées sur l'étanchéité et l'isolation."),
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

    _inv("DEV-2026-0142", InvoiceType.devis, InvoiceStatus.accepte, "Ville de Quimper",
         [{"description": "Réfection toiture et étanchéité — groupe scolaire Jean Moulin (lot unique)", "qty": 1, "unit_price": 468500}],
         toiture, today - timedelta(days=20), due=today + timedelta(days=10),
         notes="Devis remis à l'appui de l'offre — réf. AO 25-114207.")
    _inv("FAC-2026-0087", InvoiceType.facture, InvoiceStatus.paye, "Commune de Pluguffan",
         [{"description": "Réfection de la couverture — école élémentaire", "qty": 1, "unit_price": 96000}],
         None, today - timedelta(days=95), due=today - timedelta(days=65), paid=today - timedelta(days=70))
    _inv("AV-2026-0009", InvoiceType.avoir, InvoiceStatus.envoye, "Commune de Pluguffan",
         [{"description": "Avoir — ajustement de métré lot zinguerie", "qty": 1, "unit_price": -2400}],
         None, today - timedelta(days=40))

    # ── Veille amont : signaux d'investissement détectés en amont des AO ───────
    for sig in [
        dict(intitule="Construction d'un pôle enfance (crèche + ALSH)", type_projet="construction",
             budget=3200000, budget_texte="3,2 M€ HT", localisation="Fouesnant (29)",
             collectivite="Commune de Fouesnant", calendrier="AO probable T4 2026",
             metiers=["gros œuvre", "toiture", "étanchéité", "isolation"],
             extrait="« …le conseil approuve l'enveloppe prévisionnelle de 3,2 M€ HT pour la construction du pôle enfance, financée par la DETR et l'autofinancement… »",
             pertinence="pertinent", pertinence_score=84, source_name="Délibération du conseil municipal de Fouesnant",
             source_url="https://www.fouesnant.bzh/deliberations", source_date="2026-05-14",
             domaine="bâtiment", phase="financement voté", echeance_ao="T4 2026",
             financement="DETR + autofinancement", maturite=78),
        dict(intitule="Rénovation thermique du groupe scolaire des Sables Blancs", type_projet="rénovation",
             budget=1400000, budget_texte="1,4 M€ HT", localisation="Concarneau (29)",
             collectivite="Concarneau Cornouaille Agglomération", calendrier="AO probable T1 2027",
             metiers=["isolation", "couverture", "menuiserie"],
             extrait="« …inscription au plan pluriannuel d'investissement de la rénovation énergétique du groupe scolaire, demande de subvention DSIL en cours… »",
             pertinence="pertinent", pertinence_score=73, source_name="PPI 2026-2028 — Concarneau Agglomération",
             source_url="https://www.concarneau-cornouaille.fr/ppi", source_date="2026-04-02",
             domaine="bâtiment", phase="programmation", echeance_ao="T1 2027",
             financement="DSIL", maturite=60),
        dict(intitule="Réhabilitation de la salle des sports municipale", type_projet="rénovation",
             budget=900000, budget_texte="≈ 900 k€ HT", localisation="Quimperlé (29)",
             collectivite="Commune de Quimperlé", calendrier="à confirmer",
             metiers=["gros œuvre", "toiture", "désamiantage"],
             extrait="« …lancement d'une étude de faisabilité pour la réhabilitation de la salle des sports, présence d'amiante à confirmer par diagnostic… »",
             pertinence="a_etudier", pertinence_score=58, source_name="Compte-rendu de la commission travaux — Quimperlé",
             source_url="https://www.quimperle.bzh/travaux", source_date="2026-03-19",
             domaine="bâtiment", phase="étude", echeance_ao="non daté",
             financement="à définir", maturite=40),
    ]:
        db.add(Signal(user_id=uid, **sig))

    # ── Alertes sauvegardées (veille AO) ──────────────────────────────────────
    db.add(SavedSearch(user_id=uid, name="Réfection toiture / étanchéité — Finistère",
                       query="toiture étanchéité couverture", cpv=["45261000", "45260000"],
                       type_marche="travaux", departements=["29", "56", "22"], countries=[],
                       frequency="quotidienne", active=True, min_score=70,
                       last_run=now - timedelta(hours=6)))
    db.add(SavedSearch(user_id=uid, name="Rénovation énergétique — bâtiments publics",
                       query="rénovation énergétique isolation thermique", cpv=["45321000"],
                       type_marche="travaux", departements=["29", "56"], countries=[],
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

    _kb("Mémoire technique — Réfection toiture école de Pluguffan (2024)", "memoire", [
        "Méthodologie d'étanchéité : dépose soignée de la couverture existante, contrôle du support, pose d'un pare-vapeur, d'une isolation thermique en polyuréthane et d'une membrane d'étanchéité bicouche soudée. Relevés et zinguerie traités en points singuliers.",
        "Sécurité et chantier en site occupé : installation de protections collectives (garde-corps périphériques, filets), phasage permettant le maintien de l'activité scolaire, nettoyage quotidien et évacuation des déchets en filière agréée.",
        "Planning d'exécution : préparation (1 semaine), dépose et reprise du support (2 semaines), isolation et étanchéité (4 semaines), zinguerie et finitions (2 semaines), réception et levée de réserves (1 semaine).",
        "Références similaires : 12 réfections de toitures scolaires conduites sur les 5 dernières années en Finistère, dont l'école élémentaire de Pluguffan (2024) et le centre technique de Quimper (2023).",
        "Engagements environnementaux : tri des déchets de chantier, valorisation des matériaux, recours à des isolants biosourcés lorsque le CCTP le permet, démarche RGE.",
    ])
    _kb("Politique RSE & clause d'insertion sociale", "rse", [
        "Insertion sociale : Bâtiment de l'Ouest conventionne des structures d'insertion par l'activité économique (SIAE) locales pour réaliser les heures d'insertion exigées dans les marchés publics. 1 040 heures réalisées en 2025.",
        "Démarche environnementale : entreprise RGE, tri et valorisation des déchets de chantier, optimisation des tournées et bilan carbone suivi annuellement.",
        "Sécurité et conditions de travail : 0 accident avec arrêt en 2025, formations régulières (travail en hauteur, désamiantage sous-section 4), encadrement QSE dédié.",
    ])

    # ── Co-construction & consortium : Lorient entièrement instancié ──────────
    if lorient:
        breizh = ct_by_name.get("Breizh Désamiantage")
        breizh_siret = (breizh.siret if breizh else "") or "53219876500011"

        invite = ProjectInvite(
            token=secrets.token_hex(24), project_id=lorient, owner_id=uid,
            recipient="contact@breizh-desamiantage.fr", company_name="Breizh Désamiantage",
            can_view_docs=True, role="cotraitant", can_contribute=True, revoked=False,
            view_count=4, last_viewed_at=now, verified_email="contact@breizh-desamiantage.fr",
            verified_at=now)
        db.add(invite); db.flush()

        contrib = ProjectContribution(
            invite_id=invite.id, project_id=lorient, owner_id=uid,
            company_name="Breizh Désamiantage", role="cotraitant",
            lot="Lot 1 — Désamiantage et retrait d'amiante (SS3)", siret=breizh_siret,
            forme_juridique="SAS", address="8 rue de l'Industrie", postal_code="56100", city="Lorient",
            references=[
                {"intitule": "Désamiantage avant démolition d'un EHPAD", "client": "Lorient Agglomération", "montant": 320000, "annee": 2024},
                {"intitule": "Retrait d'amiante en toiture d'un gymnase", "client": "Commune de Lanester", "montant": 185000, "annee": 2023},
            ],
            qualifications=["Qualification désamiantage SS3", "Certification amiante sous-section 3", "Assurance amiante"],
            chiffrage_note="Lot désamiantage estimé à 280 000 € HT : plan de retrait, confinement, traitement et évacuation en filière agréée, mesures d'empoussièrement.",
            memoire_paragraph="Breizh Désamiantage réalise le retrait d'amiante en sous-section 3 conformément au plan de retrait validé. Confinement dynamique, contrôles d'empoussièrement libératoires et traçabilité complète des déchets (BSDA).",
            contact={"nom": "Soizic Morvan", "email": "contact@breizh-desamiantage.fr", "telephone": "02 97 84 22 10"},
            status="submitted", submitted_at=now, version=1)
        db.add(contrib); db.flush()

        for pname, pkey in [("Kbis — Breizh Désamiantage", "demo/breizh_kbis.pdf"),
                            ("Attestation de qualification désamiantage SS3 — Breizh Désamiantage", "demo/breizh_ss3.pdf")]:
            _put(pkey, pname)
            db.add(ContributionPiece(contribution_id=contrib.id, project_id=lorient, owner_id=uid,
                                     name=pname, file_key=pkey, file_size=11000, mime_type="application/pdf"))

        space = CoSpace(owner_id=uid, name="Groupement — Gymnase de Lorient",
                        marche="Réhabilitation énergétique et désamiantage du gymnase municipal de Lorient",
                        warroom={"lots": [
                            {"lot": "Lot 1 — Désamiantage SS3", "attribue": "Breizh Désamiantage"},
                            {"lot": "Lot 2 — Isolation / rénovation énergétique", "attribue": "Bâtiment de l'Ouest (mandataire)"},
                            {"lot": "Lot 3 — Gros œuvre & étanchéité", "attribue": "Bâtiment de l'Ouest (mandataire)"},
                        ]})
        db.add(space); db.flush()
        db.add(CoMember(space_id=space.id, user_id=uid, role="mandataire", status="accepted",
                        company_name="Bâtiment de l'Ouest"))
        db.add(CoMember(space_id=space.id, email="contact@breizh-desamiantage.fr", role="cotraitant",
                        status="accepted", token=secrets.token_hex(16), company_name="Breizh Désamiantage"))

    # ── CERFA générés (régénérés à la volée au téléchargement) ────────────────
    def _gen(pid, types):
        for t in types:
            db.add(GeneratedDoc(project_id=pid, doc_type=t, status="pret",
                                filled_data={"company": "Bâtiment de l'Ouest", "project": str(pid)}))

    if toiture:
        _gen(toiture, ["dc1", "dc2", "honneur", "attri1"])
    if lorient:
        # DC4 = déclaration de sous-traitance/co-traitance → matérialise le consortium
        _gen(lorient, ["dc1", "dc2", "dc4", "honneur"])

    # ── Historique d'AO décidés (gagné/perdu) : peuple le tableau de bord ──────
    # Win-rate, pipeline et analytics n'ont de sens qu'avec des marchés clôturés.
    from app.models import ProjectStatus
    PAST = [
        dict(name="Réfection de toiture-terrasse — médiathèque de Douarnenez", client="Ville de Douarnenez",
             budget=212000, status=ProjectStatus.gagne, ref="24-098112",
             outcome_rank=1, awarded_amount=212000, outcome_reason="Offre la mieux-disante (valeur technique 60 %).",
             details={"intitule_marche": "Réfection de la toiture-terrasse de la médiathèque",
                      "acheteur": "Ville de Douarnenez", "type_marche": "Travaux", "budget_estime": "212 000 EUR HT",
                      "lieu_execution": "Douarnenez (29)", "qualifications_requises": ["Qualibat 3212", "RGE"],
                      "ca_minimum_requis": "CA > 800 000 EUR",
                      "criteres_attribution": [{"critere": "Valeur technique", "ponderation": "60%"}, {"critere": "Prix", "ponderation": "40%"}]},
             summary="Réfection de toiture-terrasse à Douarnenez — métier et zone alignés. Marché remporté en 2024.",
             pieces=["Attestation Qualibat 3212", "Mémoire technique", "Attestation décennale"]),
        dict(name="Couverture et zinguerie — école de Plomelin", client="Commune de Plomelin",
             budget=138000, status=ProjectStatus.gagne, ref="24-061330",
             outcome_rank=1, awarded_amount=138000, outcome_reason="Meilleur rapport valeur technique / prix.",
             details={"intitule_marche": "Réfection de la couverture et de la zinguerie de l'école",
                      "acheteur": "Commune de Plomelin", "type_marche": "Travaux", "budget_estime": "138 000 EUR HT",
                      "lieu_execution": "Plomelin (29)", "qualifications_requises": ["Qualibat 3212"],
                      "ca_minimum_requis": "CA > 500 000 EUR",
                      "criteres_attribution": [{"critere": "Valeur technique", "ponderation": "50%"}, {"critere": "Prix", "ponderation": "50%"}]},
             summary="Couverture et zinguerie d'une école à Plomelin — cœur de métier. Marché remporté en 2024.",
             pieces=["Attestation Qualibat 3212", "Mémoire technique", "Références scolaires"]),
        dict(name="Rénovation de couverture — gendarmerie de Châteaulin", client="SGAMI Ouest",
             budget=175000, status=ProjectStatus.perdu, ref="24-076550",
             outcome_rank=2, competitor_winner="SARL Couverture du Porzay",
             outcome_reason="Classé 2e — offre supérieure de 6 % au prix retenu.",
             details={"intitule_marche": "Rénovation de la couverture de la caserne de gendarmerie",
                      "acheteur": "SGAMI Ouest", "type_marche": "Travaux", "budget_estime": "175 000 EUR HT",
                      "lieu_execution": "Châteaulin (29)", "qualifications_requises": ["Qualibat 3212"],
                      "ca_minimum_requis": "CA > 600 000 EUR",
                      "criteres_attribution": [{"critere": "Prix", "ponderation": "60%"}, {"critere": "Valeur technique", "ponderation": "40%"}]},
             summary="Rénovation de couverture à Châteaulin — métier et zone alignés. Offre classée 2e (prix) en 2024.",
             pieces=["Attestation Qualibat 3212", "Mémoire technique", "Attestation décennale"]),
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
    logger.info("Vitrine démo : coffre-fort, factures, veille amont, KB, consortium Lorient + DC4, "
                "%d AO décidés (win-rate) seedés.", len(PAST))
