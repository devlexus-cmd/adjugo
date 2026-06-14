"""
Libellés du DUME / ESPD traduits dans les langues des pays adaptés.
Peuplé via l'orchestration i18n (clé = chaîne française canonique → traduction).
FR (ou langue inconnue) = identité.
"""

_NAME_TO_CODE = {
    "français": "fr", "italien": "it", "polonais": "pl", "néerlandais": "nl",
    "finnois": "fi", "danois": "da", "anglais": "en", "allemand": "de",
    "portugais": "pt", "tchèque": "cs", "roumain": "ro", "slovaque": "sk",
    "bulgare": "bg", "lituanien": "lt",
}

# {code_langue: {chaine_fr: traduction}} — rempli par i18n_data.DUME.
DUME_LABELS: dict = {}

try:  # chargé si la traduction a déjà été générée
    from app.services.i18n_data import DUME as _DUME
    DUME_LABELS = _DUME or {}
except Exception:
    DUME_LABELS = {}


def dume_translator(lang_name: str = None):
    """Retourne une fonction tr(fr) -> texte traduit (identité si langue=fr/inconnue)."""
    code = _NAME_TO_CODE.get((lang_name or "").lower(), "fr")
    table = DUME_LABELS.get(code) or {}

    def tr(fr: str) -> str:
        return table.get(fr, fr)

    return tr
