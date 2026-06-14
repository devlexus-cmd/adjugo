"""
Source entreprises : Recherche d'entreprises (annuaire-entreprises / data.gouv).
https://recherche-entreprises.api.gouv.fr — base officielle SIRENE, sans clé.
Chaque fiche a un SIRET officiel (donc vérifié) et un lien annuaire-entreprises.
"""
import logging
from typing import Optional

import httpx

from app.sourcing.base import CompanySource
from app.sourcing.schemas import NormalizedCompany, Provenance

logger = logging.getLogger("adjugo")
API = "https://recherche-entreprises.api.gouv.fr/search"
ANNUAIRE = "https://annuaire-entreprises.data.gouv.fr/entreprise/"

# Métiers BTP → codes NAF
TRADES = [
    {"key": "electricite", "label": "Électricité", "naf": "43.21A"},
    {"key": "plomberie", "label": "Plomberie / CVC", "naf": "43.22B"},
    {"key": "maconnerie", "label": "Maçonnerie / Gros œuvre", "naf": "43.99C"},
    {"key": "menuiserie", "label": "Menuiserie", "naf": "43.32A"},
    {"key": "couverture", "label": "Couverture / Toiture", "naf": "43.91B"},
    {"key": "peinture", "label": "Peinture / Finitions", "naf": "43.34Z"},
    {"key": "platrerie", "label": "Plâtrerie / Isolation", "naf": "43.31Z"},
    {"key": "carrelage", "label": "Carrelage / Revêtements", "naf": "43.33Z"},
    {"key": "terrassement", "label": "Terrassement / VRD", "naf": "43.12A"},
    {"key": "metallerie", "label": "Serrurerie / Métallerie", "naf": "25.11Z"},
    {"key": "etancheite", "label": "Étanchéité", "naf": "43.99A"},
    {"key": "demolition", "label": "Démolition", "naf": "43.11Z"},
]
_EFFECTIF = {"NN": None, "00": 0, "01": 2, "02": 4, "03": 8, "11": 15, "12": 30,
             "21": 75, "22": 150, "31": 250, "32": 750, "41": 1500, "42": 3500,
             "51": 7500, "52": 12000}


class SireneSource(CompanySource):
    name = "SIRENE"

    def _get(self, params: dict) -> list[dict]:
        with httpx.Client(timeout=12, headers={"User-Agent": "AdjugoBot/1.0"}) as c:
            r = c.get(API, params=params)
            r.raise_for_status()
            return r.json().get("results", [])

    def search(self, activity: str = "", departement: str = "", query: str = "",
               limit: int = 12) -> list[NormalizedCompany]:
        trade = next((t for t in TRADES if t["key"] == activity), None)
        params = {"per_page": min(limit, 25), "page": 1, "etat_administratif": "A"}
        kw = trade["label"] if trade else activity
        if trade:
            params["activite_principale"] = trade["naf"]
        q = (query or kw).strip()
        if q:
            params["q"] = q
        if departement:
            params["departement"] = departement
        try:
            rows = self._get(params)
        except Exception as e:
            logger.warning("SIRENE indisponible : %s", e)
            raise
        out = [self._normalize(e) for e in rows]
        return [c for c in out if c.nom]

    def get_by_siret(self, siret: str) -> Optional[NormalizedCompany]:
        if not siret:
            return None
        import re
        digits = re.sub(r"\D", "", siret)
        # L'API n'indexe pas le SIRET (14) dans `q` → on interroge par le SIREN (9).
        search = digits[:9] if len(digits) in (9, 14) else siret
        try:
            rows = self._get({"q": search, "per_page": 1, "page": 1})
        except Exception:
            return None
        for e in rows:
            c = self._normalize(e)
            if c.siren and digits.startswith(c.siren):
                c.siret_verified = True
                if len(digits) == 14:
                    c.siret = digits  # conserver l'établissement exact saisi
                return c
        return None

    def _normalize(self, e: dict) -> NormalizedCompany:
        siege = e.get("siege", {}) or {}
        comp = e.get("complements", {}) or {}
        fin = e.get("finances", {}) or {}
        siren = e.get("siren", "")
        eff = _EFFECTIF.get(e.get("tranche_effectif_salarie") or "", None)
        etat = siege.get("etat_administratif") or e.get("etat_administratif")
        ca, rn = _last_finances(fin)
        c = NormalizedCompany(
            nom=e.get("nom_complet") or e.get("nom_raison_sociale") or "",
            siren=siren or None,
            siret=siege.get("siret") or None,
            siret_verified=bool(siege.get("siret")),  # vient du registre officiel
            naf=e.get("activite_principale") or None,
            naf_label=_naf_label(e.get("activite_principale")),
            forme_juridique=None,
            effectif=eff,
            adresse=siege.get("adresse") or None,
            code_postal=siege.get("code_postal") or None,
            ville=siege.get("libelle_commune") or None,
            departement=(siege.get("code_postal") or "")[:2] or None,
            dirigeant=_dirigeant(e),
            date_creation=e.get("date_creation") or None,
            etat_administratif=etat,
            date_fermeture=e.get("date_fermeture") or None,
            freshness_date=e.get("date_mise_a_jour") or None,
            categorie=e.get("categorie_entreprise") or None,
            nb_etablissements_ouverts=e.get("nombre_etablissements_ouverts"),
            est_rge=comp.get("est_rge"),
            est_qualiopi=comp.get("est_qualiopi"),
            convention_collective=comp.get("convention_collective_renseignee"),
            ca=ca, resultat_net=rn,
            provenance=Provenance(source=self.name,
                                  source_url=ANNUAIRE + (siren or ""),
                                  official_ref=siege.get("siret") or siren or ""),
            raw=e,
        )
        c.confidence = _confidence(c)
        return c


def _naf_label(naf: Optional[str]) -> Optional[str]:
    if not naf:
        return None
    code = naf.replace(".", "")
    for t in TRADES:
        if t["naf"].replace(".", "") == code:
            return t["label"]
    return naf


def _dirigeant(e: dict) -> Optional[str]:
    dirs = e.get("dirigeants") or []
    if dirs:
        d = dirs[0]
        nom = " ".join(x for x in [d.get("prenoms", ""), d.get("nom", "")] if x).strip()
        return nom or d.get("denomination") or None
    return None


def _last_finances(fin: dict):
    """Dernier CA / résultat net publié (RNE/INPI), souvent absent."""
    if not isinstance(fin, dict) or not fin:
        return None, None
    try:
        year = max(fin.keys())
        d = fin.get(year) or {}
        return d.get("ca"), d.get("resultat_net")
    except Exception:
        return None, None


def _confidence(c: NormalizedCompany) -> float:
    keys = [c.nom, c.siret_verified, c.naf, c.effectif is not None, c.ville,
            c.etat_administratif == "A"]
    return round(sum(1 for k in keys if k) / len(keys), 2)
