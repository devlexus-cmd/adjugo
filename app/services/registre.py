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


def _client(timeout: float = 12):
    return httpx.Client(timeout=timeout, headers={"User-Agent": "Adjugo/1.0 (+https://adjugo.fr)"})


def _plier(s) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or "").upper())
    return re.sub(r"[^A-Z0-9]+", " ", "".join(c for c in s if not unicodedata.combining(c))).strip()


def _voie(adresse, code_postal, commune) -> str:
    """L'adresse SANS son code postal ni sa commune : l'API Recherche d'entreprises écrit `adresse` en entier
    (« 3 RUE DU PORT 29200 BREST »), en plus de `code_postal` et `libelle_commune`, qu'Adjugo garde à part (Mon
    entreprise : Adresse, Code postal, Ville) et que les formulaires officiels et la convention recollent. Sans ce
    retrait, ils écrivaient « 3 RUE DU PORT 29200 BREST 29200 BREST » (contrôle des bugs, deuxième passe). Seule une fin
    « code postal [commune…] » est retirée ; une adresse qui ne finit pas ainsi reste telle quelle."""
    a = " ".join(str(adresse or "").split())
    cp = str(code_postal or "").strip()
    if not a or not cp:
        return a
    occ = list(re.finditer(r"(?:^|\s)" + re.escape(cp) + r"(?=\s|$)", a))
    if not occ:
        return a
    voie, reste = a[:occ[-1].start()].strip(" ,"), a[occ[-1].end():].strip()
    ville = _plier(commune)
    if voie and (not reste or (ville and _plier(reste).startswith(ville))):
        return voie
    return a


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
        # Spécialité EXPLOITABLE (mots-clés métier) dérivée du NAF → pré-remplit les critères
        # et la 1re recherche à l'activation par SIRET (repli : libellé NAF).
        "specialite": _specialite(e.get("activite_principale")),
        "forme_juridique": _forme_label(forme),
        "address": (_voie(siege.get("adresse"), siege.get("code_postal"), siege.get("libelle_commune"))
                    or f"{siege.get('numero_voie','')} {siege.get('libelle_voie','')}".strip()),
        "postal_code": siege.get("code_postal", ""),
        "city": siege.get("libelle_commune", ""),
        "departement": (siege.get("code_postal", "") or "")[:2],
        "effectif": _EFFECTIF.get(eff_code, 0),
        "date_creation": e.get("date_creation", ""),
        "categorie": e.get("categorie_entreprise", ""),
        "etat": "actif" if (siege.get("etat_administratif") == "A" or e.get("etat_administratif") == "A") else "",
        "dirigeant": _dirigeant(e),
    }


def lookup_company(query: str, timeout: float = 12) -> Optional[dict]:
    """Recherche une entreprise par SIRET, SIREN, nom (France via SIRENE) ou par
    numéro de TVA intracommunautaire étranger (UE via VIES).

    L'API recherche-entreprises n'indexe pas le SIRET (14 chiffres) dans le `q`
    plein-texte → on interroge par le SIREN (9 premiers chiffres) tout en conservant
    le SIRET saisi par l'utilisateur dans le résultat.

    `timeout` : délai HTTP (12 s par défaut, inchangé) ; le réseau de partenaires passe un
    délai court (process unique : jamais d'attente longue sur l'unique worker)."""
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
        with _client(timeout) as c:
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
    params["categorie_entreprise"] = "PME"   # partenaires d'une TPE/PME : pas les grands groupes
    try:
        with _client() as c:
            r = c.get(API, params=params)
            if r.status_code != 200:
                return {"total": 0, "results": [], "error": f"HTTP {r.status_code}"}
            data = r.json()
            from app.sourcing.sources.sirene import local_etablissement
            results = []
            for e in data.get("results", []):
                x = _normalize(e)
                et = local_etablissement(e, departement)
                if et:      # l'établissement DU département, pas le siège lointain
                    x.update({"siret": et.get("siret") or x["siret"],
                              "address": _voie(et.get("adresse"), et.get("code_postal"), et.get("libelle_commune"))
                              or x["address"],
                              "postal_code": et.get("code_postal") or x["postal_code"],
                              "city": et.get("libelle_commune") or x["city"],
                              "departement": (et.get("code_postal") or "")[:2] or x["departement"]})
                results.append(x)
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

def _specialite(naf: Optional[str]) -> str:
    """Mots-clés métier depuis le code NAF : si le NAF correspond à un métier BTP connu,
    on renvoie ses mots-clés (bons pour la recherche d'AO) ; sinon le libellé NAF."""
    if not naf:
        return ""
    code = str(naf).strip().upper()
    for t in TRADES:
        if t["naf"].upper() == code:
            return t["kw"]
    # Hors métiers BTP connus : on ne renvoie PAS le code NAF brut (mauvais mot-clé de
    # recherche) — le libellé seulement s'il existe, sinon vide (l'utilisateur ajustera).
    label = _naf_label(naf)
    return label if label and label != naf else ""


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
