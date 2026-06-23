"""
Schémas normalisés avec PROVENANCE OBLIGATOIRE.

Règle d'or : tout champ métier absent vaut None → l'UI affiche « non disponible ».
Jamais comblé. Les champs de provenance (source, source_url, official_ref,
fetched_at) sont, eux, toujours renseignés.
"""
from datetime import datetime, timezone
from typing import Optional, Any
from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Provenance(BaseModel):
    """Traçabilité d'un enregistrement — d'où vient la donnée."""
    source: str                       # "BOAMP", "DECP", "TED", "SIRENE"…
    source_url: str                   # lien vers l'avis/la fiche officielle
    official_ref: str = ""            # idweb BOAMP, id TED, SIREN/SIRET…
    fetched_at: str = Field(default_factory=_now)


class ScoreCriterion(BaseModel):
    """Un critère du scoring, avec son verdict explicite."""
    key: str
    label: str
    points: float
    max_points: float
    status: str                       # "ok" | "partiel" | "inconnu"
    detail: str = ""


class Score(BaseModel):
    total: int                        # 0-100
    breakdown: list[ScoreCriterion] = []
    note: str = ""                    # synthèse courte (peut être produite par LLM)
    # False = l'utilisateur n'a renseigné AUCUN critère d'adéquation (métier/zone) → le
    # score ne mesure pas l'adéquation au client ; le front affiche alors « configurez
    # vos critères » au lieu d'un nombre trompeur.
    fit_assessable: bool = True


class NormalizedTender(BaseModel):
    """Un appel d'offres normalisé, quelle que soit la source."""
    objet: str
    acheteur: Optional[str] = None
    cpv: list[str] = []
    montant_estime: Optional[float] = None
    date_publication: Optional[str] = None     # ISO date
    date_limite: Optional[str] = None          # ISO date
    lieu: Optional[str] = None
    departements: list[str] = []
    procedure: Optional[str] = None
    nature: Optional[str] = None
    dce_url: Optional[str] = None              # dossier de consultation, si dispo

    provenance: Provenance
    confidence: float = 0.0                    # 0-1, complétude/fraîcheur/concordance
    score: Optional[Score] = None
    dedup_key: str = ""                        # clé de déduplication
    also_seen_in: list[Provenance] = []        # mêmes AO trouvés sur d'autres sources
    raw: dict[str, Any] = {}                   # payload brut (traçabilité)


class NormalizedCompany(BaseModel):
    """Une entreprise normalisée depuis un registre officiel."""
    nom: str
    siren: Optional[str] = None
    siret: Optional[str] = None
    siret_verified: bool = False               # SIRET confirmé auprès de la source
    naf: Optional[str] = None
    naf_label: Optional[str] = None
    forme_juridique: Optional[str] = None
    effectif: Optional[int] = None
    adresse: Optional[str] = None
    code_postal: Optional[str] = None
    ville: Optional[str] = None
    departement: Optional[str] = None
    dirigeant: Optional[str] = None
    date_creation: Optional[str] = None
    etat_administratif: Optional[str] = None   # "A" actif / "C" cessé
    date_fermeture: Optional[str] = None
    freshness_date: Optional[str] = None       # dernière mise à jour officielle

    # Signaux de fiabilité vérifiables (API recherche-entreprises)
    categorie: Optional[str] = None            # PME | ETI | GE
    nb_etablissements_ouverts: Optional[int] = None
    est_rge: Optional[bool] = None             # qualification RGE (rénovation énergétique)
    est_qualiopi: Optional[bool] = None
    convention_collective: Optional[bool] = None
    ca: Optional[float] = None                 # dernier CA publié (RNE/INPI), souvent absent
    resultat_net: Optional[float] = None

    # Historique des marchés publics RÉELLEMENT remportés (DECP, titulaire_id_1) —
    # signal de capacité déterministe : « cette entreprise a déjà gagné ce type de marché »
    past_wins: int = 0
    last_win_date: Optional[str] = None
    win_domains: list[str] = []                 # familles CPV (2 chiffres) déjà gagnées

    # Red-flag financier (BODACC) : procédure collective en cours
    procedure_collective: Optional[str] = None  # ex "liquidation judiciaire" si détectée
    red_flags: list[str] = []

    provenance: Provenance
    confidence: float = 0.0
    score: Optional[Score] = None
    synergy: Optional[dict] = None   # score de synergie vs l'entreprise pilote (Complementarity Graph)
    raw: dict[str, Any] = {}


class SourceError(BaseModel):
    """Erreur d'une source (réseau/quota/indispo) — affichée, jamais masquée."""
    source: str
    message: str
