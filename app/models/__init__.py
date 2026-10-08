"""
Adjugo — Modèles de base de données
"""
from datetime import datetime, date, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, DateTime,
    Date, ForeignKey, JSON, Enum as SAEnum, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


# === ENUMS ===

class PlanType(str, enum.Enum):
    starter = "starter"
    pro = "pro"
    business = "business"


class ProjectStatus(str, enum.Enum):
    nouveau = "nouveau"
    en_cours = "en_cours"
    envoye = "envoye"
    gagne = "gagne"
    perdu = "perdu"
    abandonne = "abandonne"


class InvoiceType(str, enum.Enum):
    devis = "devis"
    facture = "facture"
    avoir = "avoir"


class InvoiceStatus(str, enum.Enum):
    brouillon = "brouillon"
    envoye = "envoye"
    accepte = "accepte"
    en_attente = "en_attente"
    paye = "paye"
    en_retard = "en_retard"


class DocCategory(str, enum.Enum):
    administratif = "administratif"
    fiscal = "fiscal"
    assurances = "assurances"
    qualifications = "qualifications"
    autre = "autre"


def utcnow():
    return datetime.now(timezone.utc)


# === USER ===

class Organization(Base):
    """Espace de travail partagé : les membres partagent projets, contacts et co-traitants."""
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    country = Column(String(2), default="FR")   # pays d'adaptation (cf. core/countries)
    # use_alter : rompt le cycle de FK mutuelles users<->organizations à la création.
    owner_id = Column(Integer, ForeignKey("users.id", use_alter=True, name="fk_org_owner"), nullable=True)
    created_at = Column(DateTime, default=utcnow)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    org_role = Column(String(20), default="membre")  # admin | membre — défaut = MOINS privilégié
    # (le propriétaire est promu 'admin' explicitement à la création de son org ; un membre
    #  invité reçoit son rôle explicitement → ce défaut ne sert que de filet anti-escalade).
    plan = Column(SAEnum(PlanType), default=PlanType.starter)
    analyses_used_this_month = Column(Integer, default=0)
    analyses_period = Column(String(7), default="")  # "AAAA-MM" pour le reset mensuel
    stripe_customer_id = Column(String(255), nullable=True)
    # Tarification à l'usage : autoriser le dépassement de quota facturé (vs 402 bloquant)
    overage_enabled = Column(Boolean, default=False)
    overage_count = Column(Integer, default=0)  # analyses hors quota ce mois
    # Essai gratuit 30 jours (sans carte) : date de fin. NULL = compte historique/démo
    # (jamais d'essai attaché → ancien comportement Découverte conservé).
    trial_ends_at = Column(DateTime, nullable=True)
    amont_alerts_enabled = Column(Boolean, default=False)  # veille amont auto (email)
    # Révocation de session : incrémenté au retrait/transfert → les JWT émis avant
    # (qui portent l'ancienne valeur) sont rejetés. Coupe immédiatement un accès.
    token_version = Column(Integer, default=0)
    email_verified = Column(Boolean, default=False)   # adresse confirmée via le lien envoyé à l'inscription
    # Réinitialisation de mot de passe par email (sha256 d'un token à usage unique).
    reset_token_hash = Column(String(64), default="")
    reset_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    # Relations
    company = relationship("Company", back_populates="user", uselist=False)
    projects = relationship("Project", back_populates="user")
    documents = relationship("Document", back_populates="user")
    invoices = relationship("Invoice", back_populates="user")
    contacts = relationship("Contact", back_populates="user")
    criteria = relationship("MatchingCriteria", back_populates="user", uselist=False)


# === COMPANY (Profil entreprise) ===

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    name = Column(String(255), nullable=False)
    siret = Column(String(20))
    code_ape = Column(String(10))
    forme_juridique = Column(String(50))
    capital = Column(String(50))
    representant_legal = Column(String(255))
    address = Column(Text)
    city = Column(String(100))
    postal_code = Column(String(10))
    tva_intracom = Column(String(30))
    phone = Column(String(20))
    email = Column(String(255))

    # Finances
    ca_n1 = Column(Float, default=0)
    ca_n2 = Column(Float, default=0)
    ca_n3 = Column(Float, default=0)
    effectif = Column(Integer, default=0)

    # Qualifications (stockées en JSON)
    qualifications = Column(JSON, default=list)
    # Ex: [{"name": "Qualibat 1312", "detail": "Gros œuvre", "expiration": "2027-07-01"}]

    references = Column(JSON, default=list)
    # Ex: [{"name": "Crèche municipale", "client": "Mairie X", "value": 64000, "year": 2025}]

    # Équipe interne (moyens humains) — alimente le mémoire technique.
    team = Column(JSON, default=list)
    # Ex: [{"nom": "Yann Tanguy", "fonction": "Conducteur de travaux", "qualifications": "BTS, 15 ans", "references": "12 toitures scolaires"}]

    # Chiffrage : tarifs journaliers par profil de prestation + majoration distance.
    day_rates = Column(JSON, default=list)
    # Ex: [{"label": "Étude / conception", "rate": 600}, {"label": "Production / édition", "rate": 400}]
    distance_threshold_km = Column(Integer, default=50)   # au-delà : majoration
    distance_surcharge_pct = Column(Float, default=0)     # ex. 10 (%)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="company")


# === PROJECT (Appel d'offres) ===

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    name = Column(String(500), nullable=False)
    client = Column(String(255))
    budget = Column(Float, default=0)
    # Taux de TVA de l'acte d'engagement. Défaut 0 % : marchés publics souvent
    # hors-champ TVA (art. 293 B CGI). Pilote l'ATTRI1 et la DPGF.
    tva_rate = Column(Float, default=0.0)
    status = Column(SAEnum(ProjectStatus), default=ProjectStatus.nouveau)
    deadline = Column(Date, nullable=True)

    # Résultats de l'analyse IA
    match_score = Column(Integer, nullable=True)  # 0-100
    go_decision = Column(String(20), nullable=True)  # "go", "no-go", "a_etudier"
    ai_summary = Column(Text, nullable=True)
    ai_analysis = Column(JSON, nullable=True)
    # Stocke le résultat complet : rse, delay, penalty, caMin, pièces requises...

    # Métadonnées
    source_url = Column(String(500), nullable=True)  # Lien BOAMP/JOUE
    dce_file_key = Column(String(500), nullable=True)  # Clé S3 du DCE uploadé

    # Workflow (checklist)
    workflow = Column(JSON, default=dict)
    # Ex: {"prise_contact": true, "collecte_docs": false, ...}

    # Chiffrage estimatif (devis) : tâches + jours + tarifs + totaux. Voir agents/chiffrage.
    estimate = Column(JSON, nullable=True)

    # ── Répondre à plusieurs (co-traitance v2) ──
    # match_score reste le score SEUL (jamais gonflé). groupement_score = score cumulé de
    # l'entreprise virtuelle « moi + partenaires retenus » (calcul déterministe, 0 LLM).
    # groupement_plan = {members:[{kind,id,invite_id,name,siret,apporte[]}], breakdown, gaps,
    #   warnings, offre:{total_ht, frozen_at, convention_id}, computed_at}.
    # L'ÉTAT du groupement n'est PAS stocké : il est DÉRIVÉ par groupement_state() (une seule
    # source de vérité, rien à resynchroniser). go_decision accepte aussi 'go_groupement'.
    groupement_score = Column(Integer, nullable=True)
    groupement_plan = Column(JSON, nullable=True)

    # Résultat (capture Gagné/Perdu pour les analytics de win-rate)
    outcome_reason = Column(String(255), nullable=True)
    outcome_rank = Column(Integer, nullable=True)        # classement obtenu
    awarded_amount = Column(Float, nullable=True)        # montant attribué au lauréat
    competitor_winner = Column(String(255), nullable=True)

    deleted_at = Column(DateTime, nullable=True, index=True)  # soft-delete (corbeille)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="projects")
    generated_docs = relationship("GeneratedDoc", back_populates="project")


# === DOCUMENT (Coffre-fort) ===

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    name = Column(String(500), nullable=False)
    category = Column(SAEnum(DocCategory), default=DocCategory.autre)
    file_key = Column(String(500), nullable=False)  # Clé S3
    file_size = Column(Integer, default=0)  # En octets
    mime_type = Column(String(100))
    expiration_date = Column(Date, nullable=True)
    version = Column(Integer, default=1)
    parent_id = Column(Integer, ForeignKey("documents.id"), nullable=True)

    # Rangement par appel d'offres (dossier organisé). project_id null = coffre-fort général.
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    folder = Column(String(60), default="")  # DCE | CERFA | Mémoire technique | Pièces administratives…

    # Alertes
    alert_30_sent = Column(Boolean, default=False)
    alert_7_sent = Column(Boolean, default=False)
    alert_day_sent = Column(Boolean, default=False)

    deleted_at = Column(DateTime, nullable=True, index=True)  # soft-delete (corbeille)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="documents")
    versions = relationship("Document", backref="parent", remote_side=[id])


# === GENERATED DOC (CERFA générés) ===

class GeneratedDoc(Base):
    __tablename__ = "generated_docs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    doc_type = Column(String(20), nullable=False)  # DC1, DC2, DC4, ATTRI1, memoire_technique
    status = Column(String(20), default="brouillon")  # brouillon, pret, signe
    file_key = Column(String(500), nullable=True)  # Clé S3 du PDF généré
    filled_data = Column(JSON, default=dict)  # Données pré-remplies
    manual_edits = Column(JSON, default=dict)  # Modifications manuelles de l'utilisateur

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="generated_docs")


# === INVOICE ===

class Invoice(Base):
    __tablename__ = "invoices"
    # Numérotation FAC/DEV SÉQUENTIELLE PAR UTILISATEUR → l'unicité doit être (user_id,
    # reference) et non globale (sinon le 2e user à créer « FAC-2026-001 » heurte la
    # contrainte globale → 500). Cf. migration g1h2i3j4k5l6.
    __table_args__ = (UniqueConstraint("user_id", "reference", name="uq_invoice_user_reference"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    reference = Column(String(50), nullable=False)  # FAC-2026-001 (unique par utilisateur)
    type = Column(SAEnum(InvoiceType), nullable=False)
    status = Column(SAEnum(InvoiceStatus), default=InvoiceStatus.brouillon)

    client_name = Column(String(255), nullable=False)
    client_address = Column(Text)
    client_siret = Column(String(20))

    items = Column(JSON, default=list)
    # Ex: [{"description": "Lot 1 gros œuvre", "qty": 1, "unit_price": 38400}]

    subtotal_ht = Column(Float, default=0)
    tva_rate = Column(Float, default=0.0)   # franchise de TVA par défaut (cible PME/EI, art. 293 B CGI)
    tva_amount = Column(Float, default=0)
    total_ttc = Column(Float, default=0)

    issue_date = Column(Date, default=date.today)
    due_date = Column(Date, nullable=True)
    paid_date = Column(Date, nullable=True)
    converted_invoice_id = Column(Integer, nullable=True)  # id de la facture issue de CE devis
    #  (anti double-conversion : un devis ne se convertit qu'une fois)

    # Lien optionnel vers un projet
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)

    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="invoices")


class ProcessedStripeEvent(Base):
    """Idempotence des webhooks Stripe : on enregistre chaque event_id traité pour ignorer
    un rejeu (Stripe retry ou replay d'un event signé) → pas de double-traitement."""
    __tablename__ = "processed_stripe_events"
    event_id = Column(String(255), primary_key=True)
    created_at = Column(DateTime, default=utcnow)


# === CONTACT ===

class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    name = Column(String(255), nullable=False)
    role = Column(String(255))
    organization = Column(String(255))
    contact_type = Column(String(50))  # maitre_ouvrage, sous_traitant, partenaire
    email = Column(String(255))
    phone = Column(String(30))
    address = Column(Text)
    notes = Column(Text)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="contacts")


# === MATCHING CRITERIA (Critères Go/No-Go) ===

class MatchingCriteria(Base):
    __tablename__ = "matching_criteria"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    # Compétences
    skills = Column(JSON, default=list)  # ["Gros œuvre", "Rénovation"]
    certifications = Column(JSON, default=list)  # ["Qualibat", "RGE"]

    # Finances
    budget_min = Column(Float, default=0)
    budget_max = Column(Float, default=500000)
    daily_rate_min = Column(Float, default=0)
    penalty_max = Column(Float, default=5.0)  # en %

    # Géographie
    max_distance_km = Column(Integer, default=50)
    departments = Column(JSON, default=list)  # ["69", "01", "38"]

    # Préférences
    market_types = Column(JSON, default=list)  # ["public", "semi_public"]
    lot_types = Column(JSON, default=list)  # ["unique", "alloti"]
    exclude_no_variants = Column(Boolean, default=False)
    exclude_no_rse = Column(Boolean, default=True)
    exclude_no_subcontracting = Column(Boolean, default=True)
    excluded_keywords = Column(Text, default="")

    # Seuils
    nogo_threshold = Column(Integer, default=49)  # 0 à ce seuil = NO-GO
    go_threshold = Column(Integer, default=75)  # Ce seuil à 100 = GO

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="criteria")


# === SAVED SEARCH (Veille / alertes AO programmées) ===

class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    name = Column(String(255), nullable=False)
    query = Column(String(500), default="")
    cpv = Column(JSON, default=list)
    type_marche = Column(String(40), default="")   # travaux | services | fournitures | "" (tous)
    departements = Column(JSON, default=list)
    countries = Column(JSON, default=list)   # ISO alpha-2 ; vide = toute l'UE/EEE
    montant_min = Column(Float, nullable=True)
    montant_max = Column(Float, nullable=True)

    frequency = Column(String(20), default="quotidienne")  # quotidienne | hebdomadaire | manuelle
    active = Column(Boolean, default=True)
    min_score = Column(Integer, nullable=True)  # ne notifier qu'au-dessus (défaut: seuil Go)

    last_run = Column(DateTime, nullable=True)
    last_seen_refs = Column(JSON, default=list)  # official_refs déjà notifiés (anti-doublon)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# === SIGNAL D'INVESTISSEMENT (veille amont) ===
# Projet futur détecté par l'IA dans une délibération / compte-rendu de collectivité,
# en AMONT de l'appel d'offres officiel. Source réelle (document), jamais inventé.

class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    intitule = Column(String(500), nullable=False)
    type_projet = Column(String(120), default="")        # construction, rénovation, voirie, équipement…
    budget = Column(Float, nullable=True)                # € estimé si mentionné
    budget_texte = Column(String(120), default="")       # tel que cité ("8 M€ HT")
    localisation = Column(String(255), default="")
    collectivite = Column(String(255), default="")       # mairie / interco / dept / région
    calendrier = Column(String(255), default="")         # échéance estimée ("AO probable T1 2027")
    metiers = Column(JSON, default=list)                 # métiers BTP concernés
    extrait = Column(Text, default="")                   # citation du document (traçabilité)

    pertinence = Column(String(20), default="a_etudier") # pertinent | a_etudier | faible
    pertinence_score = Column(Integer, default=0)        # 0-100 vs profil entreprise

    source_name = Column(String(255), default="")        # nom du document / source
    source_url = Column(String(700), default="")         # lien vers la délibération / document
    source_date = Column(String(40), default="")         # date de la délibération si connue
    archived = Column(Boolean, default=False)

    # Profondeur veille amont (détection enrichie)
    domaine = Column(String(80), default="")              # bâtiment, voirie/VRD, réseaux, énergie…
    phase = Column(String(40), default="")                # idée|étude|programmation|financement voté|concours|imminent
    echeance_ao = Column(String(120), default="")         # estimation de publication de l'AO
    financement = Column(String(255), default="")         # DETR, DSIL, subvention, autofinancement…
    maturite = Column(Integer, nullable=True)             # 0-100 : probabilité estimée qu'un AO suive

    created_at = Column(DateTime, default=utcnow)


# === BASE DE CONNAISSANCES (RAG à traçabilité) ===
# L'entreprise dépose ses documents bruts (mémoires techniques passés, fiches RSE,
# méthodologies, certifications…). Adjugo en construit une base interrogeable :
# chaque réponse générée par l'IA cite le chunk source exact (anti-hallucination).

class KnowledgeDoc(Base):
    __tablename__ = "knowledge_docs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    name = Column(String(300), nullable=False)           # nom du fichier / titre
    kind = Column(String(40), default="autre")           # memoire | rse | methodologie | certification | reference | autre
    text = Column(Text, default="")                      # texte intégral extrait
    char_count = Column(Integer, default=0)
    n_chunks = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True, index=True)
    doc_id = Column(Integer, ForeignKey("knowledge_docs.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    ordinal = Column(Integer, default=0)                 # position du chunk dans le doc
    text = Column(Text, default="")                      # contenu du chunk (cité comme source)
    doc_name = Column(String(300), default="")           # dénormalisé pour la traçabilité
    created_at = Column(DateTime, default=utcnow)


# === ESPACE CO-TRAITANCE PARTAGÉ (Merged Brain) ===
# Deux comptes Adjugo (ou plus) collaborent sur une réponse : leurs bases de
# connaissances sont mises en commun pour générer UN mémoire technique unifié.

class CoSpace(Base):
    __tablename__ = "co_spaces"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)  # mandataire (pilote)
    name = Column(String(255), nullable=False)        # nom de l'espace / du marché
    marche = Column(String(500), default="")          # objet du marché visé
    warroom = Column(JSON, nullable=True)             # pré-répartition des lots (War Room)
    created_at = Column(DateTime, default=utcnow)


class CoMember(Base):
    __tablename__ = "co_members"

    id = Column(Integer, primary_key=True, index=True)
    space_id = Column(Integer, ForeignKey("co_spaces.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)   # rempli à l'acceptation
    email = Column(String(255), default="")           # email invité
    role = Column(String(20), default="cotraitant")   # mandataire | cotraitant
    status = Column(String(20), default="invited")    # invited | accepted
    token = Column(String(64), default="", index=True)  # jeton d'invitation
    company_name = Column(String(255), default="")    # dénormalisé pour l'attribution des sources
    created_at = Column(DateTime, default=utcnow)


# === JOBS ASYNCHRONES (générations longues : mémoire, war room…) ===
# Les traitements IA longs (ingestion DCE, mémoire fusionné, war room) ne tiennent
# pas dans une requête HTTP synchrone. On crée un Job, on traite en tâche de fond,
# le client interroge le statut puis récupère le résultat (anti-timeout).

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    kind = Column(String(40), default="")             # memoire | merged_memoire | warroom | …
    status = Column(String(20), default="pending")    # pending | running | done | error
    label = Column(String(255), default="")           # libellé affiché au client
    result = Column(JSON, nullable=True)              # résultat (quand done)
    error = Column(Text, default="")                  # message d'erreur (quand error)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# === INVITATION CO-TRAITANT (vue bridée par jeton) ===
# Un mandataire partage UN appel d'offres avec un co-traitant externe via un lien
# secret. Le co-traitant accède à une vue LIMITÉE au seul projet partagé — sans
# compte, sans accès au reste du tenant. C'est la base de confiance pour ouvrir un
# dossier à un partenaire. Voir [[adjugo-architecture-invariants]] : la portée est
# TOUJOURS contrainte à invite.project_id côté serveur.

class ProjectInvite(Base):
    __tablename__ = "project_invites"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(64), unique=True, index=True, nullable=False)   # secret de l'URL
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)  # qui partage

    recipient = Column(String(255), default="")        # email/nom du co-traitant (info)
    company_name = Column(String(255), default="")     # entreprise co-traitante (info)
    can_view_docs = Column(Boolean, default=True)      # autorise la liste + le téléchargement des pièces
    role = Column(String(20), default="cotraitant")    # rôle de l'invité : cotraitant | sous_traitant
    can_contribute = Column(Boolean, default=True)     # autorise la CO-CONSTRUCTION (apport de sa part)
    # Compte-à-compte : si l'invité a un compte Adjugo et « réclame » le lien, l'AO
    # apparaît dans SON espace (« Partagé avec moi »). Reste null pour un invité sans compte.
    accepted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    revoked = Column(Boolean, default=False, index=True)
    # Le partenaire DÉCLINE l'invitation : traité EXACTEMENT comme revoked partout (helper
    # app.services.groupement_members.active_invites) — il sort du groupement (checklist,
    # cockpit, CERFA, convention, signatures) sans que le mandataire ait à révoquer.
    declined_at = Column(DateTime, nullable=True)
    # Provenance de l'invitation : manuel (lien créé par le mandataire) | reseau_adjugo
    # (vague 3 : recipient rempli côté serveur et JAMAIS sérialisé tant que non accepté) | sirene.
    source = Column(String(20), default="manuel")
    partner_profile_id = Column(Integer, nullable=True, index=True)   # vague 3 (réseau)
    expires_at = Column(DateTime, nullable=True)       # null = sans expiration
    view_count = Column(Integer, default=0)
    last_viewed_at = Column(DateTime, nullable=True)

    # Binding d'identité par OTP email (sécurité « industrielle ») : avant de SOUMETTRE
    # sa part, l'invité prouve qu'il contrôle l'adresse destinataire. Le secret de l'URL
    # devient alors une capacité + une identité vérifiée. Actif seulement si l'email est
    # configuré ET recipient est une adresse (sinon flux inchangé, zéro friction).
    otp_hash = Column(String(64), default="")          # sha256 du code à 6 chiffres
    otp_expires_at = Column(DateTime, nullable=True)
    otp_attempts = Column(Integer, default=0)
    verified_email = Column(String(255), default="")   # adresse prouvée
    verified_at = Column(DateTime, nullable=True)

    # Suivi d'envoi : le mandataire voit si le mail d'invitation est réellement parti,
    # et la relance automatique sait quels paliers d'échéance ont déjà été notifiés
    # (0 = aucune relance, 1 = J-3 envoyée, 2 = J-1 envoyée) — anti-spam idempotent.
    emailed_at = Column(DateTime, nullable=True)
    reminder_stage = Column(Integer, default=0)

    created_at = Column(DateTime, default=utcnow)


# === JOURNAL D'ACCÈS (RGPD) ===
# Trace immuable de qui a consulté/téléchargé quoi, et quand — y compris les invités
# externes. C'est l'argument juridique : preuve de traçabilité des accès aux pièces.
# Append-only (jamais modifié) ; un échec d'écriture ne doit jamais casser l'action.

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=utcnow, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)   # tenant propriétaire de la donnée
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)

    actor = Column(String(160), default="")        # "user:42" | nom d'entreprise du co-traitant | "invité"
    actor_kind = Column(String(20), default="")    # owner | guest
    # Invitation concernée par l'entrée → le JOURNAL MEMBRE (ce que le mandataire a vu de MA
    # part, ce que j'ai fait) est une simple projection : entrées où invite_id = le mien +
    # événements de groupement du projet. Jamais l'email/IP des autres membres.
    invite_id = Column(Integer, nullable=True, index=True)
    action = Column(String(60), default="", index=True)  # invite.created | invite.revoked | guest.view_project | guest.download_doc
    target_type = Column(String(40), default="")   # project | document | invite
    target_id = Column(Integer, nullable=True)
    detail = Column(String(255), default="")       # ex. nom du document consulté
    ip = Column(String(45), default="")            # IPv4/IPv6 de l'accès
    meta = Column(JSON, nullable=True)

    # Chaînage cryptographique (tamper-evidence). entry_hash = sha256(prev_hash + payload) ;
    # une entrée modifiée ou retirée au milieu brise la chaîne ; la disparition des DERNIÈRES
    # entrées n'est détectée que par l'ancrage quotidien (app/services/audit_anchor.py).
    prev_hash = Column(String(64), default="")
    entry_hash = Column(String(64), default="", index=True)


# === CONTRIBUTION CO-TRAITANT (co-construction cloisonnée — cœur CaaS) ===
# Chaque PME invitée apporte SA part au dossier commun : références, qualifications,
# chiffrage de son lot, paragraphe de mémoire. Le réseau Adjugo : ensemble sur des
# marchés trop gros pour une seule entreprise. CLOISONNEMENT STRICT : une contribution
# est liée à UNE invitation (invite_id unique). Un invité ne lit/écrit JAMAIS que la
# sienne ; il ne voit jamais les données des autres co-traitants. Le mandataire (owner
# du projet) voit tout et assemble. L'IA fusionne les contributions soumises.

class ProjectContribution(Base):
    __tablename__ = "project_contributions"

    id = Column(Integer, primary_key=True, index=True)
    invite_id = Column(Integer, ForeignKey("project_invites.id"), nullable=False, unique=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)  # mandataire (tenant)

    company_name = Column(String(255), default="")     # entreprise contributrice
    role = Column(String(20), default="cotraitant")    # cotraitant | sous_traitant
    lot = Column(String(255), default="")              # lot / périmètre couvert par cette PME
    # Identité juridique du membre → alimente les DC1/DC2 multi-membres du groupement.
    siret = Column(String(20), default="")
    forme_juridique = Column(String(80), default="")
    address = Column(String(255), default="")
    postal_code = Column(String(10), default="")
    city = Column(String(120), default="")

    references = Column(JSON, default=list)            # [{intitule, client, montant, annee}]
    qualifications = Column(JSON, default=list)        # ["Qualibat 1234", "RGE", "ISO 9001"]
    # (chiffrage_note — l'ancienne « approche prix » en clair, visible du mandataire — a été
    # vidée en vague 1 (contenu déplacé dans note_au_mandataire) puis SUPPRIMÉE en vague 4 :
    # migration q1r2s3t4u5v6.)
    # ── DOCTRINE DE VISIBILITÉ ──
    # prix_lot_ht = PRIX DE VENTE du lot : le SEUL montant que voit le mandataire (il en a
    # besoin pour consolider l'offre commune et remplir l'ATTRI1).
    prix_lot_ht = Column(Float, nullable=True)
    # detail_chiffre = décomposition / coûts / marges / méthode : ENVELOPPE CHIFFRÉE dans le
    # navigateur du membre (AES-256-GCM, clé dérivée d'un code de récupération par PBKDF2,
    # jamais transmise). {ciphertext, iv, alg:'A256GCM', kdf:'PBKDF2-SHA256', kdf_salt,
    # kdf_iter, key_fingerprint, updated_at}. Le serveur n'en vérifie que la forme ; ni le
    # mandataire, ni Adjugo, ni le LLM ne peuvent le lire.
    detail_chiffre = Column(JSON, nullable=True)
    # Signataire du membre (DC2 / annexe de la convention, vague 2).
    representant_legal = Column(String(255), default="")
    signataire_qualite = Column(String(120), default="")
    # Capacités DÉCLARÉES PAR LE PARTENAIRE LUI-MÊME ({ca_n1, effectif, declared_at}) →
    # alimentent le score de groupement avec capacites_source='contribution' (plus fiable que
    # ce que le mandataire a saisi sur son partenaire dans l'annuaire).
    capacites = Column(JSON, nullable=True)
    memoire_paragraph = Column(Text, default="")       # son paragraphe de mémoire technique
    contact = Column(JSON, nullable=True)              # {nom, email, telephone}
    note_au_mandataire = Column(Text, default="")      # message libre du partenaire au chef de file

    status = Column(String(20), default="draft")       # draft | submitted
    submitted_at = Column(DateTime, nullable=True)
    # Verrouillage optimiste : incrémenté à chaque sauvegarde. Le client renvoie la
    # version qu'il a chargée ; si elle a changé entre-temps (édition concurrente), on
    # refuse (409) au lieu d'écraser silencieusement la saisie de l'autre.
    version = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# === PIÈCES ADMINISTRATIVES DU CO-TRAITANT ===
# Pour déposer un dossier de GROUPEMENT, chaque membre fournit SES pièces (DC2,
# attestations fiscales/sociales, Kbis, assurance…). Le co-traitant les téléverse via
# son lien bridé ; le mandataire les rassemble dans le dossier commun. Cloisonnement :
# une pièce est liée à UNE contribution (donc à UNE invitation) — l'invité ne voit/
# supprime que les siennes. Stockées dans le tenant du mandataire (owner_id).

class ContributionPiece(Base):
    __tablename__ = "contribution_pieces"

    id = Column(Integer, primary_key=True, index=True)
    contribution_id = Column(Integer, ForeignKey("project_contributions.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)  # tenant mandataire

    name = Column(String(500), nullable=False)
    file_key = Column(String(500), nullable=False)     # clé de stockage (préfixe owner)
    file_size = Column(Integer, default=0)
    mime_type = Column(String(100), default="")
    # ── Coffre-fort croisé (E) ── statut des attestations visible par TOUS les membres
    # (présent / valide jusqu'au / expire avant la date limite / manquant) SANS jamais exposer
    # le fichier (téléchargeable uniquement par son déposant et par le mandataire, audité).
    piece_type = Column(String(20), default="")        # kibs|fiscale|sociale|assurance|rib|qualification|autre
    expiration_date = Column(Date, nullable=True)      # saisie par le déposant ou copiée du Document source
    # « Joindre depuis mon coffre-fort » : Document.id du coffre PERSONNEL du partenaire (son
    # tenant) — le fichier est COPIÉ dans le tenant mandataire, l'original n'est jamais exposé.
    source_document_id = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=utcnow)


# === SIMULATIONS DE GROUPEMENT (A — « Répondre à plusieurs ? ») ===
# Chaque what-if « seul 54 % → avec X 81 % » est conservé : historique « pourquoi GO en
# groupement », membres pré-remplis de la convention (vague 2), journal. Pour un membre de
# kind 'sirene', le serveur ne conserve que le SIRET et RE-FETCH les capacités (anti-fausse
# provenance) ; 'saisi' = étiqueté « déclaré par vous le … ».

class GroupementSimulation(Base):
    __tablename__ = "groupement_simulations"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)   # = data_owner_id
    created_by_user_id = Column(Integer, nullable=True)

    # [{kind:'lead'|'attached'|'annuaire'|'reseau'|'sirene'|'saisi', id, name, siret, source, as_of}]
    members = Column(JSON, default=list)
    score_seul = Column(Integer, nullable=True)
    score_groupement = Column(Integer, nullable=True)
    decision = Column(String(20), default="")          # go_groupement | a_etudier | no_go
    breakdown = Column(JSON, nullable=True)            # 6 critères × {points,status,detail,apporte_par[]}
    cumul = Column(JSON, nullable=True)                # capacités cumulées de l'entreprise virtuelle
    gaps = Column(JSON, nullable=True)                 # ce que le marché exige et qui manque encore
    warnings = Column(JSON, nullable=True)             # ex. « verdict fondé sur vos propres déclarations »
    retained = Column(Boolean, default=False)          # composition retenue (→ groupement_plan)
    created_at = Column(DateTime, default=utcnow)


# === CONVENTION DE GROUPEMENT (C — vague 2 « Monter le groupement ») ===
# UNE convention par marché (project_id UNIQUE), générée par un modèle paramétré DÉTERMINISTE
# (0 LLM). Le texte figé (content_md) inclut l'annexe de répartition (nom, lot, rôle, prix de
# vente du lot de chaque membre, total) — JAMAIS la décomposition chiffrée. Un seul
# content_hash (sha256 du texte) pour tous les signataires. « Figer l'offre » est fusionné avec
# la génération : total_offre_ht figé et révélé aux membres. Toute part / prix / composition
# modifiée ensuite ⇒ status 'perimee'. L'option « masquer la répartition » (params) n'existe
# qu'en brouillon. Ce n'est PAS un conseil juridique : modèle à faire relire par un conseil.

class GroupementConvention(Base):
    __tablename__ = "groupement_conventions"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, unique=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)   # tenant (tenant_owner_id)

    forme = Column(String(12), default="")                 # '' | conjoint | solidaire
    mandataire_solidaire = Column(Boolean, default=False)  # en conjoint : le mandataire répond des autres
    # Ce que le règlement impose : non_verifie | non_specifie | libre | conjoint | solidaire.
    forme_imposee = Column(String(16), default="non_verifie")
    # Citation du DCE passée par citation_guard (sous-chaîne du texte intégral), sinon ''.
    forme_imposee_extrait = Column(Text, default="")
    habilitation = Column(JSON, nullable=True)             # {representer, signer_candidature_offre, …}
    # decision, delai_reponse_jours, defaillance, sortie_preavis_jours, confidentialite_annees,
    # pi, penalites, assurances_travaux, litiges (+ part_mandataire_ht, lot_mandataire,
    # mandataire_qualite, membres_hors_ligne, masquer_repartition — brouillon seulement).
    params = Column(JSON, nullable=True)
    status = Column(String(12), default="draft")           # draft | a_signer | signee | perimee
    content_md = Column(Text, nullable=True)               # texte FIGÉ (annexe de répartition incluse)
    content_hash = Column(String(64), nullable=True, unique=True)   # sha256(content_md), un seul pour tous
    total_offre_ht = Column(Float, nullable=True)
    version = Column(Integer, default=0)
    frozen_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# Accord de chaque membre sur LE texte (même content_hash). Ce n'est pas une signature
# électronique qualifiée : c'est un « accord enregistré » depuis l'espace du membre, avec le
# niveau d'identité réellement prouvé (imprimé dans le PDF). invite_id NULL ET
# cotraitant_link_id NULL = le mandataire ; cotraitant_link_id = membre rattaché sans
# invitation (accord 'hors_ligne' coché par le mandataire).
class GroupementSignature(Base):
    __tablename__ = "groupement_signatures"
    __table_args__ = (
        UniqueConstraint("convention_id", "invite_id", name="uq_gsig_convention_invite"),
        UniqueConstraint("convention_id", "cotraitant_link_id", name="uq_gsig_convention_link"),
    )

    id = Column(Integer, primary_key=True, index=True)
    convention_id = Column(Integer, ForeignKey("groupement_conventions.id"), nullable=False, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    owner_id = Column(Integer, nullable=False, index=True)
    invite_id = Column(Integer, ForeignKey("project_invites.id"), nullable=True)
    cotraitant_link_id = Column(Integer, ForeignKey("project_cotraitants.id"), nullable=True)
    user_id = Column(Integer, nullable=True)               # compte qui a enregistré l'accord
    company_name = Column(String(255), default="")
    siret = Column(String(20), default="")
    signataire_nom = Column(String(255), default="")
    signataire_qualite = Column(String(120), default="")
    content_hash = Column(String(64), default="")          # = convention.content_hash approuvé
    # compte_verifie | email_verifie | lien_seul ('' = accord hors ligne déclaré par le mandataire)
    identity_level = Column(String(20), default="")
    status = Column(String(12), default="pending")         # pending | signed | perimee | hors_ligne
    verified_email = Column(String(255), default="")
    signed_at = Column(DateTime, nullable=True)
    ip = Column(String(45), default="")


# === PROFIL PARTENAIRE DU RÉSEAU ADJUGO (B — vague 3 « vrai réseau ») ===
# UN profil par organisation (user_id = data_owner_id, UNIQUE). OPT-IN : visible=False par
# défaut ; publié seulement par un admin, SIRET à 14 chiffres, entreprise active vérifiée dans
# SIRENE il y a moins de 30 jours. Confiance UNIQUEMENT vérifiable : SIRENE, BODACC, DECP et
# dépôts réels sur Adjugo — jamais de note, d'avis ni d'étoile. None = « non vérifié ».
# Fiche publique = SOUS-ENSEMBLE STRICT : jamais email, téléphone, CA, effectif exact,
# documents ni résultats ; les références seulement si le partenaire les a choisies.
# is_demo : colonne conservée (schéma), AUCUN profil de démonstration n'est créé et toutes
# les requêtes du réseau les excluent.
class PartnerProfile(Base):
    __tablename__ = "partner_profiles"

    id = Column(Integer, primary_key=True, index=True)
    # Identifiant OPAQUE exposé dans l'API (jamais l'id séquentiel : anti-énumération).
    public_id = Column(String(32), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)   # = data_owner_id
    visible = Column(Boolean, default=False, nullable=False)    # opt-in : jamais publié par défaut

    # Identité : nom OFFICIEL (SIRENE) dès la vérification, sinon nom du profil entreprise.
    name = Column(String(255), default="")
    siren = Column(String(9), default="", index=True)
    siret = Column(String(14), default="")
    postal_code = Column(String(10), default="")
    city = Column(String(120), default="")
    departement = Column(String(3), default="")

    # Capacités DÉCLARÉES par l'entreprise (étiquetées « déclaré par l'entreprise le … »).
    metiers = Column(JSON, default=list)            # clés TRADES (app.sourcing.sources.sirene)
    codes_cpv = Column(JSON, default=list)
    departements = Column(JSON, default=list)       # zones d'intervention
    roles_acceptes = Column(JSON, default=list)     # cotraitant | sous_traitant | mandataire
    disponibilite = Column(String(20), default="")  # disponible | limitee | complet
    dispo_jusqua = Column(Date, nullable=True)
    lot_max_eur = Column(Float, nullable=True)      # taille de lot maximale acceptée (HT)
    presentation = Column(String(300), default="")  # UI : « présentation en une phrase »
    # Références rendues PUBLIQUES par le partenaire lui-même (choisies) : [{intitule, client, annee}].
    references_publiques = Column(JSON, default=list)
    declared_at = Column(DateTime, nullable=True)   # dernière mise à jour des capacités déclarées
    # SIREN à qui ce profil est masqué — appliqué DANS LES DEUX SENS (ni vu, ni ne voit).
    hidden_from_sirens = Column(JSON, default=list)

    # Vérifications (registres publics), datées. None = « non vérifié ».
    verified_sirene = Column(JSON, nullable=True)   # {etat, date_creation, categorie, est_rge, est_qualiopi, est_personne_physique, checked_at, source}
    verified_bodacc = Column(JSON, nullable=True)   # {found, ongoing, nature, date, url, checked_at}
    verified_decp = Column(JSON, nullable=True)     # {count, last_date, checked_at} → « au moins N »
    verified_at = Column(DateTime, nullable=True)   # dernière vérification SIRENE réussie

    # Dépôts réels sur Adjugo : COUNT recalculé, jamais saisi.
    groupements_deposes = Column(Integer, default=0)
    last_groupement_at = Column(DateTime, nullable=True)
    # Compteur ANONYME d'apparitions dans les recherches (mensuel) : jamais QUI a cherché.
    appearances_count = Column(Integer, default=0)
    appearances_period = Column(String(7), default="")   # « AAAA-MM »

    published_at = Column(DateTime, nullable=True)
    is_demo = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# === FEEDBACK (beta) ===
# Retours des utilisateurs (bouton « Signaler / Idée ») — précieux en phase de test PME.
class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    email = Column(String(255), default="")
    kind = Column(String(20), default="idee")          # bug | idee | autre
    message = Column(Text, default="")
    page = Column(String(120), default="")             # vue/contexte d'où vient le retour
    created_at = Column(DateTime, default=utcnow)


# === ACHETEUR (produit collectivités — Pilier acheteur) ===
# CLOISONNEMENT à 2 faces : les acheteurs publics vivent dans une TABLE SÉPARÉE des `users`
# (PME). Un JWT acheteur porte `typ:"acheteur"` et ne peut jamais charger un User (et
# inversement, l'auth PME rejette tout token portant `typ`). Aucune donnée PME ici.
class Acheteur(Base):
    __tablename__ = "acheteurs"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    nom_collectivite = Column(String(255), default="")
    is_active = Column(Boolean, default=True)
    token_version = Column(Integer, default=0)   # révocation de session (même logique que User)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# DCE sauvegardés par un acheteur (le DCE complet généré, en JSON, pour rechargement).
class AcheteurDce(Base):
    __tablename__ = "acheteur_dces"

    id = Column(Integer, primary_key=True, index=True)
    acheteur_id = Column(Integer, ForeignKey("acheteurs.id"), nullable=False, index=True)
    objet = Column(String(500), default="")
    payload = Column(JSON, nullable=False)       # le DCE complet (sortie de generer_dce)
    # Pilotage du cycle de vie de la consultation.
    statut = Column(String(20), default="preparation")   # preparation|publie|analyse|attribue|infructueux
    date_limite = Column(DateTime, nullable=True)         # date limite de remise des offres
    # Diffusion au réseau PME Adjugo (flywheel à deux faces).
    date_diffusion = Column(DateTime, nullable=True)
    nb_pme_diffusion = Column(Integer, nullable=True)     # nb de PME capables touchées (sourcing)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
