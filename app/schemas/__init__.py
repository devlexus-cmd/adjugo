"""
Adjugo — Schémas Pydantic (validation des requêtes/réponses API)
"""
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import date, datetime


# === AUTH ===

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="Au moins 8 caractères")
    full_name: str
    company_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    plan: str
    analyses_used_this_month: int
    is_active: bool
    is_admin: bool = False
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
    ai_summary: Optional[str]
    ai_analysis: Optional[dict]
    workflow: Optional[dict]
    outcome_reason: Optional[str] = None
    outcome_rank: Optional[int] = None
    awarded_amount: Optional[float] = None
    competitor_winner: Optional[str] = None
    created_at: datetime

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
    type: str  # devis, facture, avoir
    client_name: str
    client_address: Optional[str] = None
    client_siret: Optional[str] = None
    items: List[dict] = []
    tva_rate: Optional[float] = Field(20.0, ge=0, le=100)
    due_date: Optional[date] = None
    project_id: Optional[int] = None
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
