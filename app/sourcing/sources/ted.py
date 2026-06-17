"""
Source AO : TED (Tenders Electronic Daily) — Journal officiel des marchés
publics européens. API v3 officielle, sans clé.
https://api.ted.europa.eu/v3/notices/search

Couvre TOUS les pays de l'UE + EEE (au-dessus des seuils européens). Le périmètre
pays est paramétrable via criteria.countries (codes ISO alpha-2). Vide = toute l'UE/EEE.
"""
import logging
from typing import Optional

import httpx

from app.sourcing.base import TenderSource, TenderCriteria
from app.sourcing.schemas import NormalizedTender, Provenance

logger = logging.getLogger("adjugo")
API = "https://api.ted.europa.eu/v3/notices/search"
FIELDS = ["publication-number", "notice-title", "buyer-name", "place-of-performance",
          "deadline-date-lot", "deadline-receipt-tender-date-lot", "classification-cpv", "links"]

# UE-27 + EEE. nuts = préfixe NUTS réel (≠ alpha-2 pour la Grèce = « EL »).
EU_COUNTRIES = [
    {"a2": "FR", "a3": "FRA", "nuts": "FR", "nom": "France"},
    {"a2": "DE", "a3": "DEU", "nuts": "DE", "nom": "Allemagne"},
    {"a2": "ES", "a3": "ESP", "nuts": "ES", "nom": "Espagne"},
    {"a2": "IT", "a3": "ITA", "nuts": "IT", "nom": "Italie"},
    {"a2": "BE", "a3": "BEL", "nuts": "BE", "nom": "Belgique"},
    {"a2": "NL", "a3": "NLD", "nuts": "NL", "nom": "Pays-Bas"},
    {"a2": "LU", "a3": "LUX", "nuts": "LU", "nom": "Luxembourg"},
    {"a2": "PT", "a3": "PRT", "nuts": "PT", "nom": "Portugal"},
    {"a2": "IE", "a3": "IRL", "nuts": "IE", "nom": "Irlande"},
    {"a2": "AT", "a3": "AUT", "nuts": "AT", "nom": "Autriche"},
    {"a2": "PL", "a3": "POL", "nuts": "PL", "nom": "Pologne"},
    {"a2": "CZ", "a3": "CZE", "nuts": "CZ", "nom": "Tchéquie"},
    {"a2": "SK", "a3": "SVK", "nuts": "SK", "nom": "Slovaquie"},
    {"a2": "HU", "a3": "HUN", "nuts": "HU", "nom": "Hongrie"},
    {"a2": "RO", "a3": "ROU", "nuts": "RO", "nom": "Roumanie"},
    {"a2": "BG", "a3": "BGR", "nuts": "BG", "nom": "Bulgarie"},
    {"a2": "HR", "a3": "HRV", "nuts": "HR", "nom": "Croatie"},
    {"a2": "SI", "a3": "SVN", "nuts": "SI", "nom": "Slovénie"},
    {"a2": "GR", "a3": "GRC", "nuts": "EL", "nom": "Grèce"},
    {"a2": "DK", "a3": "DNK", "nuts": "DK", "nom": "Danemark"},
    {"a2": "SE", "a3": "SWE", "nuts": "SE", "nom": "Suède"},
    {"a2": "FI", "a3": "FIN", "nuts": "FI", "nom": "Finlande"},
    {"a2": "EE", "a3": "EST", "nuts": "EE", "nom": "Estonie"},
    {"a2": "LV", "a3": "LVA", "nuts": "LV", "nom": "Lettonie"},
    {"a2": "LT", "a3": "LTU", "nuts": "LT", "nom": "Lituanie"},
    {"a2": "CY", "a3": "CYP", "nuts": "CY", "nom": "Chypre"},
    {"a2": "MT", "a3": "MLT", "nuts": "MT", "nom": "Malte"},
    {"a2": "NO", "a3": "NOR", "nuts": "NO", "nom": "Norvège"},
    {"a2": "IS", "a3": "ISL", "nuts": "IS", "nom": "Islande"},
    {"a2": "LI", "a3": "LIE", "nuts": "LI", "nom": "Liechtenstein"},
]
_BY_A2 = {c["a2"]: c for c in EU_COUNTRIES}


class TedSource(TenderSource):
    name = "TED"
    supported_filters = {"query", "countries"}

    def search(self, criteria: TenderCriteria) -> list[NormalizedTender]:
        q = (criteria.query or "travaux").replace('"', " ").strip()
        wanted = [c for c in getattr(criteria, "countries", []) if c in _BY_A2] or [c["a2"] for c in EU_COUNTRIES]
        a3_list = " ".join(_BY_A2[c]["a3"] for c in wanted)
        # préfixes acceptés côté client (NUTS + alpha-3), gère la Grèce (EL)
        prefixes = tuple({_BY_A2[c]["nuts"] for c in wanted} | {_BY_A2[c]["a3"] for c in wanted})
        # filtre CPV : on extrait les chiffres (gère le format officiel '45000000-7'
        # avec clé de contrôle, qui était silencieusement écarté par c.isdigit()).
        import re as _re
        cpv = [_re.sub(r"\D", "", c) for c in getattr(criteria, "cpv", [])]
        cpv = [c for c in cpv if c]
        cpv_clause = f' AND classification-cpv IN ({" ".join(cpv)})' if cpv else ""
        lim = min(criteria.limit, 50)
        page = (max(0, getattr(criteria, "offset", 0)) // lim) + 1 if lim else 1
        body = {
            "query": f'FT~"{q}" AND notice-type IN (cn-standard cn-social) AND place-of-performance IN ({a3_list}){cpv_clause}',
            "fields": FIELDS, "limit": lim, "page": page,
            "scope": "ACTIVE", "paginationMode": "PAGE_NUMBER",
        }
        try:
            # Symétrie avec BOAMP : retry + backoff sur micro-coupure réseau.
            from app.sourcing.http import post_with_retry
            r = post_with_retry(API, json=body, timeout=15,
                                headers={"User-Agent": "AdjugoBot/1.0"})
            r.raise_for_status()
            notices = r.json().get("notices", [])
        except Exception as e:
            logger.warning("TED indisponible : %s", e)
            raise
        only_scope = bool(getattr(criteria, "countries", []))  # un pays précis est demandé
        out = []
        for n in notices:
            if not _in_scope(n.get("place-of-performance"), prefixes):
                continue
            t = self._normalize(n, prefixes, only_scope)
            if t:
                out.append(t)
        return out

    def _normalize(self, n: dict, prefixes: tuple = (), only_scope: bool = False) -> Optional[NormalizedTender]:
        pub = n.get("publication-number")
        if not pub:
            return None
        links = n.get("links", {}) or {}
        html = (links.get("html") or {}).get("FRA") or f"https://ted.europa.eu/fr/notice/-/detail/{pub}"
        pdf = (links.get("pdf") or {}).get("FRA")
        cpv = n.get("classification-cpv") or []
        place = n.get("place-of-performance") or []

        t = NormalizedTender(
            objet=(_ml(n.get("notice-title")) or "Objet non précisé")[:400],
            acheteur=_ml(n.get("buyer-name")),
            cpv=[str(c) for c in (cpv if isinstance(cpv, list) else [cpv]) if c],
            date_limite=_first(n.get("deadline-receipt-tender-date-lot") or n.get("deadline-date-lot")),
            lieu=_place_label(place, prefixes, only_scope),
            departements=[],  # TED fournit du NUTS, pas le n° de département → zone « inconnu »
            nature="Marché européen",
            dce_url=pdf,
            provenance=Provenance(source=self.name, source_url=html, official_ref=str(pub)),
            raw=n,
        )
        t.confidence = self._confidence(t)
        t.dedup_key = _dedup_key(t)
        return t

    @staticmethod
    def _confidence(t: NormalizedTender) -> float:
        keys = [t.objet and t.objet != "Objet non précisé", t.acheteur,
                t.date_limite, bool(t.cpv), t.lieu]
        return round(sum(1 for k in keys if k) / len(keys), 2)

    def fetch_dce(self, tender: NormalizedTender) -> Optional[str]:
        # TED publie l'AVIS (pas le cahier des charges complet, hébergé sur la
        # plateforme de l'acheteur). On ne prétend donc pas avoir le DCE complet.
        return None


def _ml(v):
    """Extrait une valeur d'un champ TED multilingue (fra > eng > 1re dispo)."""
    if isinstance(v, dict):
        for lang in ("fra", "eng", "FRA", "ENG"):
            if v.get(lang):
                val = v[lang]
                return (val[0] if isinstance(val, list) else val)
        for val in v.values():
            if val:
                return (val[0] if isinstance(val, list) else val)
        return None
    if isinstance(v, list):
        return v[0] if v else None
    return v or None


def _first(v):
    if isinstance(v, list):
        return (v[0] or None) if v else None
    return v or None


def _in_scope(place, prefixes: tuple) -> bool:
    """Garde l'avis si son lieu (code NUTS/alpha-3) relève d'un pays demandé."""
    if not place:
        return True  # lieu non précisé : on ne l'exclut pas
    items = place if isinstance(place, list) else [place]
    return any(str(p).upper().startswith(prefixes) for p in items)


# Préfixe (NUTS/alpha-3) → nom de pays, pour un lieu lisible.
_PREFIX_NAME = {}
for _c in EU_COUNTRIES:
    _PREFIX_NAME[_c["nuts"]] = _c["nom"]
    _PREFIX_NAME[_c["a3"]] = _c["nom"]


def _country_of(code: str) -> Optional[str]:
    s = str(code).upper()
    for pref in (s[:3], s[:2]):
        if pref in _PREFIX_NAME:
            return _PREFIX_NAME[pref]
    return None


def _place_label(place, prefixes: tuple = (), only_scope: bool = False) -> Optional[str]:
    """Libellé de lieu lisible (noms de pays). Si un pays précis est demandé
    (only_scope), on n'affiche que les lieux de ce pays — pas les autres pays
    d'un marché multi-pays (ex. « Portugal », pas « Portugal / Belgique »)."""
    items = place if isinstance(place, list) else ([place] if place else [])
    if not items:
        return None
    if only_scope and prefixes:
        scoped = [p for p in items if str(p).upper().startswith(prefixes)]
        items = scoped or items
    names = []
    for p in items:
        nom = _country_of(p) or str(p)
        if nom not in names:
            names.append(nom)
    return " / ".join(names[:3])


def _dedup_key(t: NormalizedTender) -> str:
    import re
    base = re.sub(r"[^a-z0-9]", "", (t.objet or "").lower())[:40]
    ach = re.sub(r"[^a-z0-9]", "", (t.acheteur or "").lower())[:20]
    return f"{base}|{ach}|{t.date_limite or ''}"
