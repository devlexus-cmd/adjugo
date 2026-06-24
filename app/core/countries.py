"""
Pays « pleinement adaptés » : ceux pour lesquels Adjugo se comporte comme un logiciel
national. Critère = donnée entreprise complète et gratuite (nom + adresse) :
 - France via SIRENE (le plus riche),
 - pays divulguant tout via VIES (vérifié empiriquement).
Chaque pays porte sa langue (sortie IA / documents) et sa devise.

Les pays UE qui ne divulguent que la validité TVA (DE, ES…) ou non vérifiés ne sont
PAS proposés à l'adaptation : on n'offre que ce qu'on peut faire parfaitement.
"""

# Pays adaptés volontairement RESTREINTS aux marchés cibles : France (natif), Belgique,
# Espagne, Pays-Bas. La recherche d'AO reste possible dans toute l'UE (TED) ; seule
# l'ADAPTATION du logiciel (langue d'interface, devise, registre) est limitée à ces pays.
# Belgique : interface en FRANÇAIS (marché wallon/bruxellois, qualité native). Pour viser la
# Flandre, basculer "lang" sur "nl" (le dictionnaire néerlandais est déjà complet).
COUNTRIES_FULL = [
    {"code": "FR", "nom": "France",   "lang": "fr", "devise": "EUR", "registre": "SIRENE"},
    {"code": "BE", "nom": "Belgique", "lang": "fr", "devise": "EUR", "registre": "VIES"},
    {"code": "ES", "nom": "Espagne",  "lang": "es", "devise": "EUR", "registre": "VIES"},
    {"code": "NL", "nom": "Pays-Bas", "lang": "nl", "devise": "EUR", "registre": "VIES"},
]

_BY_CODE = {c["code"]: c for c in COUNTRIES_FULL}

# Nom des langues (pour instruire l'IA « réponds en … »)
LANG_NAMES = {
    "fr": "français", "nl": "néerlandais", "es": "espagnol",
}


def is_supported(code: str) -> bool:
    return (code or "").upper() in _BY_CODE


def country_config(code: str) -> dict:
    """Config du pays (défaut France si inconnu/non adapté)."""
    return _BY_CODE.get((code or "FR").upper(), _BY_CODE["FR"])


def lang_of(code: str) -> str:
    return country_config(code)["lang"]


def lang_name(code: str) -> str:
    return LANG_NAMES.get(lang_of(code), "français")


def currency_of(code: str) -> str:
    return country_config(code)["devise"]
