"""
Adjugo — Schémas Pydantic (validation des requêtes/réponses API)
"""
import re
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Literal
from datetime import date, datetime


# === LIENS AFFICHÉS (avis d'origine, fiches officielles…) ===
# Un lien stocké puis rendu dans un <a href> ne doit JAMAIS porter un schéma exécutable
# (« javascript: », « data: », « vbscript: »…) : l'échappement HTML ne le neutralise pas.
# Seuls passent une adresse web absolue http(s) ou un chemin interne commençant par « / »
# (pages de démo /static/…) ; « //hôte » (relatif au protocole) et « /\hôte » sont refusés.
_SAFE_LINK_RE = re.compile(r"^(?:https?://[^\s/]|/(?![/\\]))", re.IGNORECASE)
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")
URL_INVALID_MSG = ("Adresse de l'avis invalide : indiquez un lien qui commence par "
                   "http:// ou https://.")


def safe_link_url(value, max_len: int = 500) -> Optional[str]:
    """Renvoie l'URL nettoyée si elle est sûre à afficher comme lien, sinon None.
    Utilisée à l'ÉCRITURE (validation) et à la LECTURE (une ancienne valeur en base ne
    ressort jamais en « javascript: »)."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or len(s) > max_len or _CTRL_RE.search(s) or not _SAFE_LINK_RE.match(s):
        return None
    return s


# === STATUT D'UN MARCHÉ (réorganisation, vague 2a, décision 7) ===
# Un seul axe : la valeur reçue est ramenée à sa clé (« envoye », l'ancienne clé de « Déposé », devient « depose ») ;
# une valeur hors de l'axe est refusée (422) au lieu d'échouer à l'enregistrement.
STATUT_INVALIDE_MSG = ("Statut inconnu : choisissez À venir, Repéré, Décidé, En préparation, Déposé, Gagné, "
                       "Perdu ou Abandonné.")


def _validate_statut(v):
    if v is None:
        return None
    from app.models import statut_normalise
    k = statut_normalise(v)
    if k is None:
        raise ValueError(STATUT_INVALIDE_MSG)
    return k


def _validate_link(v):
    """Validateur Pydantic commun : vide → None ; lien dangereux → message clair (422)."""
    if v is None or not str(v).strip():
        return None
    s = safe_link_url(v)
    if s is None:
        raise ValueError(URL_INVALID_MSG)
    return s


# === AUTH ===

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="Au moins 8 caractères")
    full_name: str
    company_name: Optional[str] = None

    # EmailStr ne met en minuscule QUE le domaine : on normalise TOUTE l'adresse (partie locale
    # incluse) pour qu'inscription, connexion et reset utilisent la même forme canonique. Sinon
    # « Jean.Dupont@x.fr » à l'inscription et « jean.dupont@x.fr » à la connexion = comptes
    # « fantômes » inaccessibles (ni login ni mot de passe oublié ne matchaient).
    @field_validator("email")
    @classmethod
    def _norm_email(cls, v):
        return str(v).strip().lower()


class UserLogin(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def _norm_email(cls, v):
        return str(v).strip().lower()


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterOut(Token):
    """Inscription : jeton + suggestion d'interface (vague 3 : « publiez votre profil
    partenaire ») — simple affichage, aucun email n'est envoyé pour ça."""
    suggest_profile: Optional[dict] = None


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    plan: str
    analyses_used_this_month: int
    is_active: bool
    is_admin: bool = False
    email_verified: bool = True   # exposé pour la bannière « confirmez votre adresse »
    created_at: datetime

    class Config:
        from_attributes = True


# === COMPANY ===

class CompanyCreate(BaseModel):
    name: str
    siret: Optional[str] = None
    code_ape: Optional[str] = None
    forme_juridique: Optional[str] = None
    capital: Optional[str] = None
    representant_legal: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    tva_intracom: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    ca_n1: Optional[float] = Field(0, ge=0)
    ca_n2: Optional[float] = Field(0, ge=0)
    ca_n3: Optional[float] = Field(0, ge=0)
    effectif: Optional[int] = Field(0, ge=0)
    qualifications: Optional[list] = []
    references: Optional[list] = []
    team: Optional[list] = []
    day_rates: Optional[list] = []
    distance_threshold_km: Optional[int] = Field(50, ge=0)
    distance_surcharge_pct: Optional[float] = Field(0, ge=0)

    # Champ numérique laissé VIDE dans le formulaire = "" → on accepte (= None),
    # l'endpoint garde alors la valeur en place (jamais de refus d'enregistrement).
    @field_validator("ca_n1", "ca_n2", "ca_n3", "effectif",
                     "distance_threshold_km", "distance_surcharge_pct", mode="before")
    @classmethod
    def _empty_num_to_none(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, float) and v != v:   # NaN
            return None
        return v

    @field_validator("siret")
    @classmethod
    def _validate_siret(cls, v):
        # Le SIRET français = 14 chiffres. On refuse une saisie CHIFFRÉE non conforme (typo,
        # SIREN à 9, tronquée) qui serait imprimée telle quelle sur les CERFA officiels.
        # Vide accepté (optionnel) ; identifiants étrangers (avec lettres) non concernés.
        if not v:
            return v
        s = str(v).replace(" ", "").replace(".", "")
        if s.isdigit() and len(s) != 14:
            raise ValueError("Le SIRET doit comporter exactement 14 chiffres.")
        return v


class CompanyOut(CompanyCreate):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# === PROJECT ===

class ProjectCreate(BaseModel):
    name: str
    client: Optional[str] = None
    budget: Optional[float] = 0
    tva_rate: Optional[float] = Field(0, ge=0, le=100)
    deadline: Optional[date] = None
    source_url: Optional[str] = None
    # Décision 11 : une carte peut exister avant la publication (« suivi », À venir). Absent : « Repéré ».
    status: Optional[str] = None

    @field_validator("source_url")
    @classmethod
    def _check_source_url(cls, v):
        return _validate_link(v)

    @field_validator("status")
    @classmethod
    def _check_status(cls, v):
        return _validate_statut(v)


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    client: Optional[str] = None
    budget: Optional[float] = None
    tva_rate: Optional[float] = Field(None, ge=0, le=100)
    status: Optional[str] = None
    deadline: Optional[date] = None
    workflow: Optional[dict] = None
    # Capture du résultat (Gagné / Perdu)
    outcome_reason: Optional[str] = None
    outcome_rank: Optional[int] = None
    awarded_amount: Optional[float] = None
    competitor_winner: Optional[str] = None
    # Lien vers l'avis officiel : même garde de schéma qu'à la création.
    source_url: Optional[str] = None
    # Relecture de la vague 2a : un GESTE qui fait avancer le marché (« Préparer seul », un geste de Préparer, une
    # invitation, « Écarter », « Remettre ») envoie les étapes d'où il part ; l'étape ne change que si le marché y est
    # encore (une page ou une liste plus ancienne qu'un « Marquer déposé » ne le fait jamais reculer). Absent : le
    # choix « Statut », libre.
    si_statut: Optional[List[str]] = Field(None, max_length=8)

    @field_validator("source_url")
    @classmethod
    def _check_source_url(cls, v):
        return _validate_link(v)

    @field_validator("status")
    @classmethod
    def _check_status(cls, v):
        return _validate_statut(v)

    @field_validator("si_statut")
    @classmethod
    def _check_si_statut(cls, v):
        if v is None:
            return None
        if any(x is None for x in v):
            raise ValueError(STATUT_INVALIDE_MSG)
        return [_validate_statut(x) for x in v]


class ProjectOut(BaseModel):
    id: int
    name: str
    client: Optional[str]
    budget: float
    tva_rate: Optional[float] = 0
    status: str
    deadline: Optional[date]
    match_score: Optional[int]
    go_decision: Optional[str]
    # « Répondre à plusieurs ? » : score de groupement (match_score reste le score SEUL).
    groupement_score: Optional[int] = None
    ai_summary: Optional[str]
    ai_analysis: Optional[dict]
    workflow: Optional[dict]
    outcome_reason: Optional[str] = None
    outcome_rank: Optional[int] = None
    awarded_amount: Optional[float] = None
    competitor_winner: Optional[str] = None
    created_at: datetime

    @field_validator("ai_analysis")
    @classmethod
    def _safe_source_link(cls, v):
        """Règle « à la lecture » : un lien d'avis ancien en base ne ressort jamais en
        « javascript: » (copie : la valeur ORM n'est pas modifiée)."""
        if isinstance(v, dict) and isinstance(v.get("source"), dict) and "source_url" in v["source"]:
            v = dict(v)
            v["source"] = dict(v["source"])
            v["source"]["source_url"] = safe_link_url(v["source"].get("source_url"), 1000)
        return v

    class Config:
        from_attributes = True


# === DOCUMENT ===

class DocumentOut(BaseModel):
    id: int
    name: str
    category: str
    file_size: int
    mime_type: Optional[str]
    expiration_date: Optional[date]
    version: int
    created_at: datetime

    class Config:
        from_attributes = True


# === INVOICE ===

class InvoiceCreate(BaseModel):
    type: Literal["devis", "facture", "avoir"] = "devis"  # borné : un type inconnu ne devient plus un AVO silencieux
    client_name: str = Field(..., min_length=1)            # pas de pièce officielle sans destinataire
    client_address: Optional[str] = None
    client_siret: Optional[str] = None
    items: List[dict] = []
    tva_rate: Optional[float] = Field(0.0, ge=0, le=100)  # cible PME/EI en franchise (293 B CGI)
    due_date: Optional[date] = None
    project_id: Optional[int] = None

    @field_validator("client_name")
    @classmethod
    def _name_not_blank(cls, v):
        if not (v or "").strip():
            raise ValueError("Le nom du client est requis.")
        return v.strip()

    @field_validator("items")
    @classmethod
    def _items_non_negative(cls, v):
        # Quantité/prix négatifs → total HT/TTC négatif imprimé sur un document comptable.
        for it in (v or []):
            try:
                if float(it.get("qty") or 0) < 0 or float(it.get("unit_price") or 0) < 0:
                    raise ValueError("Quantité et prix unitaire doivent être positifs.")
            except (TypeError, ValueError) as e:
                raise ValueError("Ligne de facture invalide : " + str(e))
        return v
    notes: Optional[str] = None


class InvoiceUpdate(BaseModel):
    status: Optional[str] = None
    items: Optional[List[dict]] = None
    tva_rate: Optional[float] = Field(None, ge=0, le=100)
    due_date: Optional[date] = None
    paid_date: Optional[date] = None
    notes: Optional[str] = None


class InvoiceOut(BaseModel):
    id: int
    reference: str
    type: str
    status: str
    client_name: str
    items: list
    subtotal_ht: float
    tva_rate: float
    tva_amount: float
    total_ttc: float
    issue_date: date
    due_date: Optional[date]
    paid_date: Optional[date]
    project_id: Optional[int]
    converted_invoice_id: Optional[int] = None   # devis déjà converti → cache le bouton « Facturer »
    created_at: datetime

    class Config:
        from_attributes = True


# === CONTACT ===

class ContactCreate(BaseModel):
    name: str
    role: Optional[str] = None
    organization: Optional[str] = None
    contact_type: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    organization: Optional[str] = None
    contact_type: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None


class ContactOut(ContactCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# === MATCHING CRITERIA ===

class CriteriaUpdate(BaseModel):
    skills: Optional[List[str]] = None
    certifications: Optional[List[str]] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    daily_rate_min: Optional[float] = None
    penalty_max: Optional[float] = None
    max_distance_km: Optional[int] = None
    departments: Optional[List[str]] = None
    market_types: Optional[List[str]] = None
    lot_types: Optional[List[str]] = None
    exclude_no_variants: Optional[bool] = None
    exclude_no_rse: Optional[bool] = None
    exclude_no_subcontracting: Optional[bool] = None
    excluded_keywords: Optional[str] = None
    nogo_threshold: Optional[int] = None
    go_threshold: Optional[int] = None


class CriteriaOut(CriteriaUpdate):
    id: int

    class Config:
        from_attributes = True


# === ANALYSE IA ===

class AnalysisRequest(BaseModel):
    project_id: int
    criteria_override: Optional[CriteriaUpdate] = None


class AnalysisResult(BaseModel):
    match_score: int
    go_decision: str
    summary: str
    details: dict
