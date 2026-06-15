"""
Adjugo — Modèles de base de données
"""
from datetime import datetime, date, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, DateTime,
    Date, ForeignKey, JSON, Enum as SAEnum,
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
    org_role = Column(String(20), default="admin")  # admin | membre
    plan = Column(SAEnum(PlanType), default=PlanType.starter)
    analyses_used_this_month = Column(Integer, default=0)
    analyses_period = Column(String(7), default="")  # "AAAA-MM" pour le reset mensuel
    stripe_customer_id = Column(String(255), nullable=True)
    # Tarification à l'usage : autoriser le dépassement de quota facturé (vs 402 bloquant)
    overage_enabled = Column(Boolean, default=False)
    overage_count = Column(Integer, default=0)  # analyses hors quota ce mois
    amont_alerts_enabled = Column(Boolean, default=False)  # veille amont auto (email)
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

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    reference = Column(String(50), unique=True, nullable=False)  # FAC-2026-001
    type = Column(SAEnum(InvoiceType), nullable=False)
    status = Column(SAEnum(InvoiceStatus), default=InvoiceStatus.brouillon)

    client_name = Column(String(255), nullable=False)
    client_address = Column(Text)
    client_siret = Column(String(20))

    items = Column(JSON, default=list)
    # Ex: [{"description": "Lot 1 gros œuvre", "qty": 1, "unit_price": 38400}]

    subtotal_ht = Column(Float, default=0)
    tva_rate = Column(Float, default=20.0)
    tva_amount = Column(Float, default=0)
    total_ttc = Column(Float, default=0)

    issue_date = Column(Date, default=date.today)
    due_date = Column(Date, nullable=True)
    paid_date = Column(Date, nullable=True)

    # Lien optionnel vers un projet
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)

    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="invoices")


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
