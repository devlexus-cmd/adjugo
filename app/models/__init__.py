"""
Adjugo — Modèles de base de données
"""
from datetime import datetime, date, timezone
from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, Boolean, Text, DateTime,
    Date, ForeignKey, JSON, Enum as SAEnum, UniqueConstraint, Index, text as sa_text, false as sa_false,
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
    # Analyses consommées pendant l'essai, sur TOUTE sa durée (jamais remis à zéro au changement de
    # mois, contrairement à analyses_used_this_month) : TRIAL_ANALYSES au total (app/core/quota.py).
    trial_analyses_used = Column(Integer, default=0)
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

    # Mesure de la décision 11 de l'étude « rédaction » (le règlement impose-t-il son propre fichier
    # de réponse ?) : posé à chaque import du dossier du marché (analyse d'un fichier réel), lu
    # seulement en agrégat (/metrics). NULL = aucun dossier importé.
    dce_importe_le = Column(DateTime, nullable=True)
    dce_fichier_impose = Column(Boolean, nullable=True)

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


# === COÛT DE L'IA (interne, jamais montré au client) ===
# Coût réel des appels à l'IA, au tarif public du fournisseur, cumulé par compte de facturation, par
# mois et selon que le compte était en essai gratuit ou non (app/services/budget_ia.py). Sert au
# budget de l'essai (vérifié AVANT chaque opération) et à l'alerte interne des forfaits payants.
# compte : « u<id> » (propriétaire de l'organisation, qui porte le forfait), « acheteur:<id> » (côté
# collectivités), « acheteur:anonyme », « plateforme » (appel mutualisé, sans client). Aucune donnée
# personnelle : un identifiant de compte, des montants et des nombres de tokens.

class UsageIA(Base):
    __tablename__ = "usage_ia"
    __table_args__ = (UniqueConstraint("compte", "periode", "essai", name="uq_usage_ia_compte_periode_essai"),)

    id = Column(Integer, primary_key=True, index=True)
    compte = Column(String(40), nullable=False, index=True)
    billing_user_id = Column(Integer, nullable=True, index=True)   # propriétaire de l'organisation (PME)
    org_id = Column(Integer, nullable=True, index=True)
    periode = Column(String(7), nullable=False)                    # « AAAA-MM » (UTC)
    # Valeurs par défaut côté base identiques à celles de la migration u5v6essaigardefou : une base
    # neuve (table créée depuis les modèles) et la production montée ont le même schéma.
    essai = Column(Boolean, default=False, nullable=False, server_default=sa_false())   # coût engagé pendant l'essai
    cout_eur = Column(Float, default=0.0, nullable=False, server_default="0")
    appels = Column(Integer, default=0, nullable=False, server_default="0")
    tokens_entree = Column(BigInteger, default=0, nullable=False, server_default="0")
    tokens_sortie = Column(BigInteger, default=0, nullable=False, server_default="0")
    alerte_le = Column(DateTime, nullable=True)   # forfait payant : seuil du mois dépassé (alerte interne)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


# === ANALYSE PARTAGÉE (moins de coût d'IA, sans rien changer à la qualité) ===
# Extraction d'un dossier de consultation (document PUBLIC de l'acheteur) faite par l'IA SANS aucune
# donnée d'entreprise, gardée pour être resservie quand ce même dossier, exactement, est analysé à
# nouveau, par n'importe quelle organisation. Clé = empreinte de TOUT ce que l'IA reçoit pour
# l'extraction (consignes, modèles, version de la lecture, langue, texte et état de chaque pièce).
# AUCUNE colonne de propriétaire : rien ne relie une entrée à une organisation. Pas une donnée
# personnelle (document public de l'acheteur). Voir docs/ANALYSE_PARTAGEE.md.
class AnalysePartagee(Base):
    __tablename__ = "analyses_partagees"

    id = Column(Integer, primary_key=True, index=True)
    cle = Column(String(64), nullable=False, unique=True, index=True)
    nature = Column(String(12), nullable=False, default="dossier", server_default="dossier")   # dossier | avis
    mode = Column(String(20), nullable=False, default="", server_default="")   # integral | deux_temps | avis
    version = Column(String(40), nullable=False, default="", server_default="")
    modele = Column(String(200), nullable=False, default="", server_default="")
    extraction = Column(JSON, nullable=False)       # réponse de l'IA (faits du dossier), avant tout calcul
    rapport = Column(JSON, nullable=True)           # lecture en deux temps : ce qui a été lu, partie par partie
    parties = Column(JSON, nullable=True)           # deux temps : faits relevés par partie (clé = contenu exact)
    deroule = Column(JSON, nullable=True)           # deux temps : durées et instants de lecture (progression)
    duree_s = Column(Float, nullable=False, default=0.0, server_default="0")
    cout_eur = Column(Float, nullable=False, default=0.0, server_default="0")
    created_at = Column(DateTime, default=utcnow)
    utilise_le = Column(DateTime, default=utcnow, index=True)


# Mesure des doublons (interne, jamais montrée à un client) : une ligne par analyse d'un dossier, avec
# l'empreinte NORMALISÉE de ses pièces (triées) — jamais leur contenu —, pour compter les dossiers
# analysés par plusieurs organisations. Sans clé étrangère (comme usage_ia) ; effacée avec le compte
# (RGPD) et au-delà de la durée de mesure.
class AnalyseEmpreinte(Base):
    __tablename__ = "analyse_empreintes"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, nullable=False, index=True)        # organisation (data_owner_id)
    nature = Column(String(12), nullable=False, default="dossier", server_default="dossier")
    empreinte = Column(String(64), nullable=False, index=True)    # contenu normalisé, pièces triées
    cle = Column(String(64), nullable=True, index=True)            # clé exacte de l'extraction
    servi_du_cache = Column(Boolean, nullable=False, default=False, server_default=sa_false())
    economie_eur = Column(Float, nullable=False, default=0.0, server_default="0")
    created_at = Column(DateTime, default=utcnow, index=True)


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
    # Invitation RÉSEAU : date de la PREMIÈRE réponse positive (acceptée depuis le compte, adresse
    # prouvée par code, ou part soumise). Jamais remise à zéro (effacement du compte qui l'avait
    # acceptée, part repassée en brouillon) : l'aperçu minimal et le journal du membre ne reviennent
    # jamais en arrière (migration q1r2s3t4u5v6).
    network_accepted_at = Column(DateTime, nullable=True)
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
    # vidée en vague 1 (contenu déplacé dans note_au_mandataire), revidée en vague 4 (migration
    # q1r2s3t4u5v6) et n'est PLUS MAPPÉE. La colonne reste en base le temps qu'aucune version
    # déployable ne la mappe (expand/contract) ; sa suppression viendra dans une livraison
    # ultérieure.)
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

    # Validation de l'identité par Adjugo (décision fondateur) : la vérification SIRENE prouve
    # que l'entreprise existe et est active, PAS que le compte la représente. Une demande de
    # publication passe donc « en_attente » et un administrateur Adjugo (User.is_admin) la
    # valide ou la refuse (motif). Toute modification du SIRET remet la validation à zéro.
    # '' (jamais demandée) | en_attente | validee | refusee
    validation_status = Column(String(20), default="")
    validation_siren = Column(String(9), default="")          # SIREN pour lequel l'identité a été validée
    validation_requested_at = Column(DateTime, nullable=True)
    validation_requested_by = Column(Integer, nullable=True)  # compte qui a demandé (id, sans clé étrangère)
    validated_at = Column(DateTime, nullable=True)             # date de la décision (validation ou refus)
    validated_by = Column(Integer, nullable=True)              # administrateur Adjugo (id)
    validation_motif = Column(String(300), default="")        # motif d'un refus (affiché à l'entreprise)
    # Dernière TENTATIVE de re-vérification par le cron (verified_at = dernière réussite) :
    # le cron trie par cette date, sinon un profil que SIRENE ne confirme jamais gardait la tête.
    last_check_at = Column(DateTime, nullable=True)
    # Date du dernier recalcul de groupements_deposes (le badge l'affiche).
    groupements_checked_at = Column(DateTime, nullable=True)

    # Un seul profil PUBLIÉ par SIREN, garanti par la base (deux publications simultanées).
    __table_args__ = (
        Index("uq_partner_profiles_siren_publie", "siren", unique=True,
              sqlite_where=sa_text("visible = 1"), postgresql_where=sa_text("visible")),
    )


# === DOSSIER DE PRÉSENTATION (rédaction, vague 2 — l'atelier) ===
# Le « mémoire technique » de l'acheteur, rédigé section par section. UN dossier par marché et par
# entreprise (UNIQUE(project_id, owner_id) ; owner_id = data_owner_id de l'organisation). Modèle
# défini une fois pour l'entreprise seule (vague 2) et pour le groupement (vague 4) :
#   • chaque section a un AUTEUR : aujourd'hui l'organisation propriétaire (author_kind
#     'organisation') ; en vague 4, un membre du groupement (author_kind 'invitation' +
#     author_invite_id). La matière PRIVÉE d'une section (sources, extraits, faits à relire,
#     brouillons) n'est lue que par son auteur (app/services/atelier.can_see_private) ;
#   • une génération ou une modification ne DÉTRUIT jamais rien : chaque texte est une nouvelle
#     version (table dossier_section_versions, en ajout seul) ; une section validée puis modifiée
#     repasse « à revalider ».
# Rien ici n'est envoyé à l'acheteur tel quel : l'export (app/services/atelier_export.py) retire
# les renvois internes et refuse un dossier troué sauf dérogation enregistrée au journal chaîné.

class DossierPresentation(Base):
    __tablename__ = "dossiers_presentation"
    __table_args__ = (UniqueConstraint("project_id", "owner_id", name="uq_dossier_presentation_projet_owner"),)

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)   # tenant (data_owner_id)
    created_by_user_id = Column(Integer, nullable=True)

    # Plan : 'grille' (critères retrouvés dans le règlement), 'cadre' (questions du cadre de
    # réponse imposé, dans leur ordre et leurs numéros) ou 'libre' (plan simple, sans IA).
    plan_source = Column(String(10), default="libre")
    plan_meta = Column(JSON, nullable=True)       # {message, criteres_hors_dossier[], fichier_impose, …}
    # Texte du dossier de l'acheteur LU pour la rédaction (C0) : règlement et cadre EN ENTIER, puis
    # le reste borné. Lecture faite une fois, sans IA ; jamais montré à un tiers.
    dce_lu = Column(JSON, nullable=True)

    # Quota (décision 6a) : le dossier complet compte pour 1 analyse (débitée à la 1re action IA),
    # refaire une section est gratuit jusqu'à ATELIER_REGEN_GRATUITES fois par dossier.
    analyse_debitee = Column(Boolean, default=False)
    regenerations = Column(Integer, default=0)
    regenerations_payantes = Column(Integer, default=0)
    # Premières rédactions comprises dans l'analyse du dossier : au plus une par partie du plan
    # (au plus le nombre de parties actives) ; au-delà — partie ajoutée, plan reconstruit — une
    # rédaction compte comme une refonte. Le plafond ne se contourne donc pas en changeant de plan.
    premieres_incluses = Column(Integer, default=0)
    # Tâche qui porte l'analyse du dossier (1re action de l'IA) : tant qu'elle tourne, aucune autre
    # action de l'IA ne démarre (si elle tombe en panne, l'analyse est rendue, sans passager clandestin).
    job_analyse_id = Column(Integer, nullable=True)

    # Dernière dérogation à l'export (décision 2b), valable pour UN état du texte (etat_hash) :
    # {etat_hash, raisons[], raison, texte, par, le, avertissement}. Aussi au journal chaîné.
    derogation = Column(JSON, nullable=True)
    # Compteur (pages estimées) mis en cache pour un état du texte : {etat_hash, …}.
    compteur = Column(JSON, nullable=True)
    dernier_export = Column(JSON, nullable=True)  # {le, par, format, nom, empreinte, ia}
    options_export = Column(JSON, nullable=True)  # {page_garde, sommaire}
    # Coût IA réel cumulé (cost_meter) : interne, jamais montré au client (décision 6a).
    cout_ia = Column(JSON, nullable=True)

    version = Column(Integer, default=0, nullable=False)   # verrou optimiste (plan)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class DossierSection(Base):
    __tablename__ = "dossier_sections"

    id = Column(Integer, primary_key=True, index=True)
    dossier_id = Column(Integer, ForeignKey("dossiers_presentation.id"), nullable=False, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    owner_id = Column(Integer, nullable=False, index=True)

    ordre = Column(Integer, default=0)
    numero = Column(String(20), default="")        # numéro du cadre (« 2.1 ») ou rang dans le plan
    intitule = Column(String(300), default="")
    niveau = Column(Integer, default=1)
    parents = Column(JSON, nullable=True)          # [{numero, intitule}] (titres du cadre au-dessus)
    question = Column(Text, default="")            # texte de la question du cadre / phrase du critère
    # D'où vient la section : grille | cadre | libre (plan simple d'Adjugo) | utilisateur (ajoutée)
    source_plan = Column(String(12), default="libre")
    critere = Column(String(300), default="")      # critère de la grille, tel que retrouvé
    critere_id = Column(String(20), default="")
    poids = Column(String(40), default="")         # poids retenu dans « Comment vous serez noté », sinon ''
    # D'où vient ce poids : 'reglement' (écrit dans le règlement) | 'utilisateur' (lu et saisi par
    # vous en confirmant la ligne) | '' (aucun poids). Dit tel quel à l'écran et à l'IA.
    poids_source = Column(String(20), default="")
    partie_de_critere = Column(Boolean, default=False)   # partie d'un critère découpé par Adjugo
    lot = Column(String(120), default="")          # vague 6 (plusieurs lots), vide aujourd'hui
    limite = Column(JSON, nullable=True)           # limite applicable : {type, valeur, objet, phrase, source}

    # Auteur (vague 4 : un membre du groupement par son invitation). Aujourd'hui : l'organisation.
    author_kind = Column(String(12), default="organisation")    # organisation | invitation
    author_invite_id = Column(Integer, nullable=True, index=True)

    # a_ecrire | brouillon | relu | valide | a_revalider
    statut = Column(String(12), default="a_ecrire")
    current_version_id = Column(Integer, nullable=True)
    validated_version_id = Column(Integer, nullable=True)
    validated_hash = Column(String(64), default="")
    validated_at = Column(DateTime, nullable=True)
    validated_by = Column(Integer, nullable=True)
    job_id = Column(Integer, nullable=True)        # rédaction en cours (tâche de fond)
    retiree_at = Column(DateTime, nullable=True)   # section retirée du plan (ses versions restent)
    lock_version = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class DossierSectionVersion(Base):
    __tablename__ = "dossier_section_versions"

    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey("dossier_sections.id"), nullable=False, index=True)
    dossier_id = Column(Integer, nullable=False, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    owner_id = Column(Integer, nullable=False, index=True)

    numero = Column(Integer, default=1)            # 1, 2, 3… dans la section
    texte = Column(Text, default="")
    origine = Column(String(12), default="utilisateur")   # ia | utilisateur | raccourci
    # Préparé avec l'aide de l'IA (texte de l'IA, ou texte modifié à partir d'un texte de l'IA) :
    # décide la mention « préparé avec assistance IA » des propriétés du fichier (décision 9a).
    ia = Column(Boolean, default=False)
    sources = Column(JSON, nullable=True)          # PRIVÉ : extraits cités [{ref, doc_name, chunk_id, extrait}]
    faits = Column(JSON, nullable=True)            # PRIVÉ : faits « à relire » (A0)
    empreinte = Column(String(64), default="")     # sha256 du texte
    coupe = Column(Boolean, default=False)         # texte interrompu par la limite de longueur de l'IA
    base_version_id = Column(Integer, nullable=True)
    restaure_de = Column(Integer, nullable=True)
    author_kind = Column(String(12), default="organisation")
    author_invite_id = Column(Integer, nullable=True)
    auteur_user_id = Column(Integer, nullable=True)   # compte qui a écrit / lancé la rédaction
    job_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utcnow)


# === MES PREUVES (rédaction, vague 3 — socle commun de A, I et E1) ===
# Les faits de l'entreprise, chacun avec SA source typée (doctrine § 7, règles 1 à 3 : un fait ne
# vient jamais de l'IA ; on dit où on l'a trouvé, jamais « vérifié »). Contrat :
# docs/REDACTION_V3_PREUVES.md ; règles : app/services/preuves.py (seul point d'écriture).
#   • owner_id = data_owner_id de l'organisation (tenant, comme l'atelier) ;
#   • proprietaire_kind / proprietaire_invite_id : le membre du groupement qui DÉTIENT le fait
#     (vague 4 : 'invitation' + id de l'invitation ; aujourd'hui toujours 'organisation' / 0).
#     Jamais exposé par l'API ; un fait d'une invitation n'est jamais lu par le chef de file ;
#   • numero : identifiant STABLE dans la portée (owner_id, proprietaire_invite_id) → « F3 ».
#     Jamais réutilisé : une suppression efface le contenu et garde la ligne (statut interne
#     'supprimee'), pour qu'un ancien renvoi [F3] ne désigne jamais un autre fait ;
#   • source_doc_id / source_document_id : SANS clé étrangère (supprimer un document de « Mon
#     savoir-faire » ou du coffre-fort ne doit jamais échouer) ; contrôlés à chaque lecture.
class Preuve(Base):
    __tablename__ = "preuves"
    __table_args__ = (UniqueConstraint("owner_id", "proprietaire_invite_id", "numero",
                                       name="uq_preuves_owner_proprietaire_numero"),)

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)   # tenant (data_owner_id)
    proprietaire_kind = Column(String(12), nullable=False, default="organisation", server_default="organisation")
    proprietaire_invite_id = Column(Integer, nullable=False, default=0, server_default="0", index=True)
    numero = Column(Integer, nullable=False)
    # reference | qualification | salarie | materiel | chiffre_cle
    nature = Column(String(20), nullable=False)
    valeur = Column(JSON, nullable=True)            # champs structurés de la nature (liste fermée)
    # documents (dans vos documents) | declare (déclaré par vous) | public (source publique) |
    # estimation (votre estimation)
    type_source = Column(String(12), nullable=False, default="declare", server_default="declare")
    source = Column(JSON, nullable=True)            # détail de la source (passage exact, URL datée…)
    source_doc_id = Column(Integer, nullable=True, index=True)        # KnowledgeDoc (« Mon savoir-faire »)
    source_document_id = Column(Integer, nullable=True, index=True)   # Document (justificatif déposé)
    date_source = Column(Date, nullable=True)       # date du document d'origine, ou de consultation
    date_fin_validite = Column(Date, nullable=True)
    # proposee | acceptee | retiree (+ 'supprimee' : interne, contenu effacé, jamais listé)
    statut = Column(String(12), nullable=False, default="proposee", server_default="proposee")
    # saisie | import_document (I) | import_public (E2) | profil | chiffrage
    origine = Column(String(20), nullable=False, default="saisie", server_default="saisie")
    empreinte = Column(String(64), nullable=False, default="", server_default="", index=True)
    cree_par = Column(Integer, nullable=True)
    accepte_par = Column(Integer, nullable=True)
    accepte_le = Column(DateTime, nullable=True)
    retire_le = Column(DateTime, nullable=True)
    version = Column(Integer, nullable=False, default=0, server_default="0")   # verrou optimiste
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
