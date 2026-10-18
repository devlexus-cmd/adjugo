"""
Interfaces communes des sources. Ajouter une plateforme = une nouvelle classe,
sans toucher au reste.
"""
import functools
import re
from abc import ABC, abstractmethod
from typing import Optional

from app.schemas import safe_link_url
from app.sourcing.schemas import NormalizedTender, NormalizedCompany

# Les liens d'avis peuvent être longs (paramètres de plateforme) : plafond large ici, le
# stockage en base (Project.source_url) applique ensuite sa propre limite.
_MAX_LINK_LEN = 2000


def sanitize_tender_links(tender):
    """Neutralise tout lien NON web (javascript:, data:…) d'un AO normalisé avant qu'il
    n'atteigne l'interface (« Voir l'avis ↗ ») ou la base (Project.source_url). Un lien
    invalide devient vide — l'UI n'affiche alors simplement pas de lien (jamais inventé)."""
    try:
        provs = [tender.provenance] + list(getattr(tender, "also_seen_in", None) or [])
        for prov in provs:
            if prov is not None and prov.source_url:
                prov.source_url = safe_link_url(prov.source_url, _MAX_LINK_LEN) or ""
        if getattr(tender, "dce_url", None):
            tender.dce_url = safe_link_url(tender.dce_url, _MAX_LINK_LEN)
    except Exception:
        pass
    return tender

# Un département FR valide : 2 chiffres (01-95), 3 chiffres DOM (971-976) ou Corse 2A/2B.
_DEPT_RE = re.compile(r"^(?:[0-9]{2,3}|2[AB])$", re.IGNORECASE)


def _un_chiffre(d: str) -> str:
    return d.zfill(2) if (len(d) == 1 and d.isdigit()) else d


class SourceIndisponible(Exception):
    """Source volontairement non interrogée (refus de la plateforme, pause) : affichée comme
    indisponible avec son message, SANS compter comme une panne pour le disjoncteur (aucune
    alerte répétée dans le journal, aucune nouvelle requête)."""


class TenderCriteria:
    """Critères de recherche d'AO (poussés à l'API quand supportés)."""
    def __init__(self, query: str = "", cpv: Optional[list] = None,
                 departements: Optional[list] = None,
                 montant_min: Optional[float] = None, montant_max: Optional[float] = None,
                 limit: int = 20, countries: Optional[list] = None,
                 type_marche: str = "", offset: int = 0):
        self.query = (query or "").strip()
        self.cpv = [str(c).strip() for c in (cpv or []) if str(c).strip()]
        # Départements ASSAINIS au format attendu : garde-fou CENTRAL contre l'injection
        # (un département interpolé brut dans une requête ODSQL/API ssource pouvait la casser)
        # ET normalise (majuscule Corse). Couvre BOAMP, TED, ATEXO… d'un seul point.
        # « 6 » saisi seul devient « 06 » (forme unique d'Adjugo ; le BOAMP est interrogé sous
        # les deux formes, cf. sources/boamp.py).
        self.departements = [d for d in
                             (_un_chiffre(str(x).strip().upper()) for x in (departements or []))
                             if _DEPT_RE.match(d)]
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

    def __init_subclass__(cls, **kwargs):
        """Garde CENTRALE des liens : toute source (actuelle ou future) voit les résultats
        de sa `search` passer par `sanitize_tender_links`, sans rien avoir à faire."""
        super().__init_subclass__(**kwargs)
        fn = cls.__dict__.get("search")
        if fn is None or getattr(fn, "_links_guarded", False) or getattr(fn, "__isabstractmethod__", False):
            return

        @functools.wraps(fn)
        def search(self, *args, **kw):
            res = fn(self, *args, **kw)
            if isinstance(res, list):
                return [sanitize_tender_links(t) for t in res]
            return res

        search._links_guarded = True
        cls.search = search

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
