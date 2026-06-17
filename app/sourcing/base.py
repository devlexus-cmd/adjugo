"""
Interfaces communes des sources. Ajouter une plateforme = une nouvelle classe,
sans toucher au reste.
"""
from abc import ABC, abstractmethod
from typing import Optional

from app.sourcing.schemas import NormalizedTender, NormalizedCompany


class TenderCriteria:
    """Critères de recherche d'AO (poussés à l'API quand supportés)."""
    def __init__(self, query: str = "", cpv: Optional[list] = None,
                 departements: Optional[list] = None,
                 montant_min: Optional[float] = None, montant_max: Optional[float] = None,
                 limit: int = 20, countries: Optional[list] = None,
                 type_marche: str = "", offset: int = 0):
        self.query = (query or "").strip()
        self.cpv = [str(c).strip() for c in (cpv or []) if str(c).strip()]
        self.departements = departements or []
        self.montant_min = montant_min
        self.montant_max = montant_max
        self.limit = limit
        self.offset = max(0, int(offset or 0))   # pagination : décalage « charger plus »
        # Codes pays ISO alpha-2 (ex. ["FR","DE"]). Vide = tous les pays UE/EEE.
        self.countries = [c.upper() for c in (countries or []) if c]
        # Type de marché : "TRAVAUX" | "SERVICES" | "FOURNITURES" | "" (tous).
        self.type_marche = (type_marche or "").strip().upper()


class TenderSource(ABC):
    """Une plateforme de marchés publics (BOAMP, DECP, TED…)."""
    name: str = "source"
    supported_filters: set = set()    # ex. {"cpv", "departements", "query"}

    @abstractmethod
    def search(self, criteria: TenderCriteria) -> list[NormalizedTender]:
        """Recherche des AO et retourne des objets normalisés (avec provenance)."""
        ...

    def fetch_dce(self, tender: NormalizedTender) -> Optional[str]:
        """Récupère le texte du DCE réel si accessible, sinon None (jamais inventé)."""
        return None


class CompanySource(ABC):
    """Un registre d'entreprises (SIRENE/annuaire, API Entreprise, INPI…)."""
    name: str = "source"

    @abstractmethod
    def search(self, activity: str = "", departement: str = "", query: str = "",
               limit: int = 12) -> list[NormalizedCompany]:
        ...

    @abstractmethod
    def get_by_siret(self, siret: str) -> Optional[NormalizedCompany]:
        ...

    def verify_siret(self, siret: str) -> bool:
        """Confirme l'existence d'un SIRET auprès de la source."""
        return self.get_by_siret(siret) is not None
