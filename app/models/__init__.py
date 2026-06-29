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

    actor = Column(String(160), default="")        # "user:42" | email du co-traitant | "invité"
    actor_kind = Column(String(20), default="")    # owner | guest
    action = Column(String(60), default="", index=True)  # invite.created | invite.revoked | guest.view_project | guest.download_doc
    target_type = Column(String(40), default="")   # project | document | invite
    target_id = Column(Integer, nullable=True)
    detail = Column(String(255), default="")       # ex. nom du document consulté
    ip = Column(String(45), default="")            # IPv4/IPv6 de l'accès
    meta = Column(JSON, nullable=True)

    # Chaînage cryptographique (tamper-evidence). entry_hash = sha256(prev_hash + payload) ;
    # toute modification/suppression d'une entrée brise la chaîne et est détectable.
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
    chiffrage_note = Column(Text, default="")          # approche / estimation prix de son lot
    memoire_paragraph = Column(Text, default="")       # son paragraphe de mémoire technique
    contact = Column(JSON, nullable=True)              # {nom, email, telephone}

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

    created_at = Column(DateTime, default=utcnow)


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
