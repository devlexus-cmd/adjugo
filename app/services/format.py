"""Formatage partagé (montants) — un seul endroit pour la mise en forme des euros, au lieu
de dupliquer la même fonction dans dce_export / dce_redaction / dce_avis."""


def format_eur(v, suffix: str = " € HT", fallback: str = "") -> str:
    """Montant en euros à la française (espaces comme séparateurs de milliers), arrondi à
    l'entier. `suffix` = unité affichée ; `fallback` = valeur si `v` n'est pas un nombre."""
    try:
        return f"{int(round(float(v))):,}".replace(",", " ") + suffix
    except (ValueError, TypeError):
        return fallback
