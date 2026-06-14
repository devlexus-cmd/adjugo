"""
Spécifications des formulaires nationaux de candidature (PL, PT, IT, NL, RO),
récupérées via l'orchestration et rendues par cerfa.generate_national_form.
Adjugo génère un BROUILLON pré-rempli fidèle, à reporter sur le modèle officiel.
"""
NATIONAL_FORMS: dict = {}

try:
    from app.services.national_forms_data import FORMS as _F
    NATIONAL_FORMS = _F or {}
except Exception:
    NATIONAL_FORMS = {}


def form_spec(country: str):
    """Spec du formulaire national d'un pays, ou None s'il n'y en a pas."""
    return NATIONAL_FORMS.get((country or "").upper())
