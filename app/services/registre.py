"""
Connexion au MONDE PROFESSIONNEL RÉEL.
Source : API publique Recherche d'entreprises (annuaire-entreprises / data.gouv.fr) —
gratuite, sans clé. https://recherche-entreprises.api.gouv.fr

  - lookup_company()       : auto-remplir un profil entreprise depuis un SIRET / nom
  - discover_cotraitants() : trouver de VRAIES entreprises par métier + département
                             pour constituer un groupement
"""
import re
import httpx
from typing import Optional

API = "https://recherche-entreprises.api.gouv.fr/search"

# Métiers du BTP → codes NAF (pour la découverte de co-traitants réels)
TRADES = [
    {"key": "electricite",  "label": "Électricité",            "naf": "43.21A", "kw": "électricité"},
    {"key": "plomberie",    "label": "Plomberie / CVC",        "naf": "43.22B", "kw": "plomberie chauffage"},
    {"key": "maconnerie",   "label": "Maçonnerie / Gros œuvre","naf": "43.99C", "kw": "maçonnerie gros œuvre"},
    {"key": "menuiserie",   "label": "Menuiserie",             "naf": "43.32A", "kw": "menuiserie"},
    {"key": "couverture",   "label": "Couverture / Toiture",   "naf": "43.91B", "kw": "couverture toiture"},
    {"key": "peinture",     "label": "Peinture / Finitions",   "naf": "43.34Z", "kw": "peinture"},
    {"key": "platrerie",    "label": "Plâtrerie / Isolation",  "naf": "43.31Z", "kw": "plâtrerie isolation"},
    {"key": "carrelage",    "label": "Carrelage / Revêtements","naf": "43.33Z", "kw": "carrelage"},
    {"key": "terrassement", "label": "Terrassement / VRD",     "naf": "43.12A", "kw": "terrassement VRD"},
    {"key": "metallerie",   "label": "Serrurerie / Métallerie","naf": "25.11Z", "kw": "serrurerie métallerie"},
    {"key": "etancheite",   "label": "Étanchéité",             "naf": "43.99A", "kw": "étanchéité"},
    {"key": "demolition",   "label": "Démolition",             "naf": "43.11Z", "kw": "démolition"},
]

# Tranches d'effectif INSEE → estimation numérique
_EFFECTIF = {
    "NN": 0, "00": 0, "01": 2, "02": 4, "03": 8, "11": 15, "12": 30,
    "21": 75, "22": 150, "31": 250, "32": 750, "41": 1500, "42": 3500, "51": 7500, "52": 12000,
}


def _client():
    return httpx.Client(timeout=12, headers={"User-Agent": "Adjugo/1.0 (+https://adjugo.fr)"})


def _normalize(e: dict) -> dict:
    """Transforme un résultat de l'API en dict entreprise Adjugo."""
    siege = e.get("siege", {}) or {}
    eff_code = e.get("tranche_effectif_salarie") or ""
    forme = e.get("nature_juridique") or ""
    return {
        "name": e.get("nom_complet") or e.get("nom_raison_sociale") or "",
        "siren": e.get("siren", ""),
        "siret": siege.get("siret", ""),
        "code_ape": (e.get("activite_principale") or "").replace(".", ""),
        "naf_label": _naf_label(e.get("activite_principale")),
        "forme_juridique": _forme_label(forme),
        "address": siege.get("adresse") or f"{siege.get('numero_voie','')} {siege.get('libelle_voie','')}".strip(),
        "postal_code": siege.get("code_postal", ""),
        "city": siege.get("libelle_commune", ""),
        "departement": (siege.get("code_postal", "") or "")[:2],
        "effectif": _EFFECTIF.get(eff_code, 0),
        "date_creation": e.get("date_creation", ""),
        "categorie": e.get("categorie_entreprise", ""),
        "etat": "actif" if (siege.get("etat_administratif") == "A" or e.get("etat_administratif") == "A") else "",
        "dirigeant": _dirigeant(e),
    }


def lookup_company(query: str) -> Optional[dict]:
    """Recherche une entreprise par SIRET, SIREN, nom (France via SIRENE) ou par
    numéro de TVA intracommunautaire étranger (UE via VIES).

    L'API recherche-entreprises n'indexe pas le SIRET (14 chiffres) dans le `q`
    plein-texte → on interroge par le SIREN (9 premiers chiffres) tout en conservant
    le SIRET saisi par l'utilisateur dans le résultat."""
    if not query:
        return None
    raw = query.strip()

    # TVA intracommunautaire d'un autre pays UE (préfixe pays ≠ FR) → VIES
    m = re.match(r"^\s*([A-Z]{2})\s*([0-9A-Z][0-9A-Z ]{5,})$", raw.upper())
    if m and m.group(1) != "FR":
        return _lookup_vies(raw)
    digits = re.sub(r"\D", "", raw)
    siret_saisi = digits if len(digits) == 14 else ""
    search = digits[:9] if len(digits) in (9, 14) else raw  # SIREN/SIRET → SIREN ; sinon nom
    try:
        with _client() as c:
            r = c.get(API, params={"q": search, "per_page": 1, "page": 1})
            if r.status_code != 200:
                return None
            results = r.json().get("results", [])
            if not results:
                return None
            top = results[0]
            # SÉCURITÉ EXACTITUDE : l'API `q` est un best-match plein-texte. Pour une recherche
            # par SIREN/SIRET, on EXIGE que le SIREN renvoyé soit EXACTEMENT celui saisi — sinon
            # on renverrait l'identité d'une AUTRE entreprise, et coller le SIRET saisi dessus
            # (ligne ci-dessous) produirait une fiche/CERFA totalement faux. → introuvable.
            if len(digits) in (9, 14):
                api_siren = re.sub(r"\D", "", str(top.get("siren", "")))
                if api_siren != digits[:9]:
                    return None
            data = _normalize(top)
            if siret_saisi:  # garder l'établissement exact que l'utilisateur a renseigné
                data["siret"] = siret_saisi
            return data
    except Exception:
        return None


def discover_cotraitants(activity: str = "", departement: str = "",
                         query: str = "", limit: int = 12) -> dict:
    """
    Découvre de vraies entreprises pour la co-traitance.
    activity   : clé métier (ex 'electricite') OU texte libre.
    departement: '29', '56'… (filtre l'implantation).
    """
    trade = next((t for t in TRADES if t["key"] == activity), None)
    params = {"per_page": min(limit, 25), "page": 1, "etat_administratif": "A"}
    if trade:
        params["activite_principale"] = trade["naf"]
        kw = trade["kw"]
    else:
        kw = activity or query
    # On combine NAF + mot-clé géographique pour des résultats pertinents
    q = " ".join(x for x in [query or kw, ""] if x).strip()
    if q:
        params["q"] = q
    if departement:
        params["departement"] = departement
    try:
        with _client() as c:
            r = c.get(API, params=params)
            if r.status_code != 200:
                return {"total": 0, "results": [], "error": f"HTTP {r.status_code}"}
            data = r.json()
            results = [_normalize(e) for e in data.get("results", [])]
            # filtre de cohérence : entreprises avec une dénomination
            results = [x for x in results if x["name"]]
            return {"total": data.get("total_results", len(results)),
                    "trade": trade["label"] if trade else (activity or query),
                    "results": results[:limit]}
    except Exception as ex:
        return {"total": 0, "results": [], "error": str(ex)}


# ── Vérification entreprise UE (VIES) ──

def _lookup_vies(raw: str) -> Optional[dict]:
    """Auto-remplissage via VIES pour une entreprise hors France. Renvoie un dict
    au même format que SIRENE ; nom/adresse vides si le pays ne les communique pas."""
    from app.sourcing.sources.vies import VatVerifier
    v = VatVerifier().check(raw)
    if not v:
        return None
    return {
        "name": v.get("name") or "",
        # PAS de SIRET hors France : le n° de TVA va dans tva_intracom (ci-dessous), JAMAIS
        # dans siret (sinon un n° de TVA s'imprimait à la place du SIRET sur les CERFA).
        "siren": "", "siret": "",
        "code_ape": "", "naf_label": "",
        "forme_juridique": "",
        "address": v.get("address") or "",
        "postal_code": v.get("postal_code") or "",
        "city": v.get("city") or "",
        "departement": "",
        "effectif": 0,
        "date_creation": "",
        "categorie": "",
        "tva_intracom": v.get("vat") or "",
        "etat": "actif" if v.get("valid") else "",
        "dirigeant": "",
        "country": v.get("country"),
        "vat_valid": v.get("valid"),
        "name_disclosed": v.get("name_disclosed"),
        "source": "VIES",
    }


# ── Helpers ──

def _naf_label(naf: Optional[str]) -> str:
    if not naf:
        return ""
    code = naf.replace(".", "")
    for t in TRADES:
        if t["naf"].replace(".", "") == code:
            return t["label"]
    return naf


def _forme_label(code: str) -> str:
    m = {"5710": "SAS", "5499": "SARL", "5720": "SASU", "5498": "EURL",
         "5202": "SNC", "1000": "Entrepreneur individuel", "5460": "SARL"}
    return m.get(str(code), "")


def _dirigeant(e: dict) -> str:
    dirs = e.get("dirigeants") or []
    if dirs:
        d = dirs[0]
        nom = " ".join(x for x in [d.get("prenoms", ""), d.get("nom", "")] if x).strip()
        return nom or d.get("denomination", "")
    return ""
