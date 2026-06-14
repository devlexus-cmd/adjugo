"""
Pays « pleinement adaptés » : ceux pour lesquels Adjugo se comporte comme un logiciel
national. Critère = donnée entreprise complète et gratuite (nom + adresse) :
 - France via SIRENE (le plus riche),
 - pays divulguant tout via VIES (vérifié empiriquement).
Chaque pays porte sa langue (sortie IA / documents) et sa devise.

Les pays UE qui ne divulguent que la validité TVA (DE, ES…) ou non vérifiés ne sont
PAS proposés à l'adaptation : on n'offre que ce qu'on peut faire parfaitement.
"""

COUNTRIES_FULL = [
    {"code": "FR", "nom": "France",      "lang": "fr", "devise": "EUR", "registre": "SIRENE"},
    {"code": "IT", "nom": "Italie",      "lang": "it", "devise": "EUR", "registre": "VIES"},
    {"code": "PL", "nom": "Pologne",     "lang": "pl", "devise": "PLN", "registre": "VIES"},
    {"code": "NL", "nom": "Pays-Bas",    "lang": "nl", "devise": "EUR", "registre": "VIES"},
    {"code": "FI", "nom": "Finlande",    "lang": "fi", "devise": "EUR", "registre": "VIES"},
    {"code": "DK", "nom": "Danemark",    "lang": "da", "devise": "DKK", "registre": "VIES"},
    {"code": "IE", "nom": "Irlande",     "lang": "en", "devise": "EUR", "registre": "VIES"},
    {"code": "AT", "nom": "Autriche",    "lang": "de", "devise": "EUR", "registre": "VIES"},
    {"code": "PT", "nom": "Portugal",    "lang": "pt", "devise": "EUR", "registre": "VIES"},
    {"code": "LU", "nom": "Luxembourg",  "lang": "fr", "devise": "EUR", "registre": "VIES"},
    {"code": "CZ", "nom": "Tchéquie",    "lang": "cs", "devise": "CZK", "registre": "VIES"},
    {"code": "RO", "nom": "Roumanie",    "lang": "ro", "devise": "RON", "registre": "VIES"},
    {"code": "SK", "nom": "Slovaquie",   "lang": "sk", "devise": "EUR", "registre": "VIES"},
    {"code": "BG", "nom": "Bulgarie",    "lang": "bg", "devise": "BGN", "registre": "VIES"},
    {"code": "LT", "nom": "Lituanie",    "lang": "lt", "devise": "EUR", "registre": "VIES"},
]

_BY_CODE = {c["code"]: c for c in COUNTRIES_FULL}

# Nom des langues (pour instruire l'IA « réponds en … »)
LANG_NAMES = {
    "fr": "français", "it": "italien", "pl": "polonais", "nl": "néerlandais",
    "fi": "finnois", "da": "danois", "en": "anglais", "de": "allemand",
    "pt": "portugais", "cs": "tchèque", "ro": "roumain", "sk": "slovaque",
    "bg": "bulgare", "lt": "lituanien",
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
