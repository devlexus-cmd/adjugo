"""Formatage partagé (montants, dates et heures) — un seul endroit pour la mise en forme, au
lieu de dupliquer la même fonction dans dce_export / dce_redaction / dce_avis (montants) ou dans
journal_membre / groupement_convention (heures des PDF de co-traitance)."""
from datetime import timezone
from functools import lru_cache


def format_eur(v, suffix: str = " € HT", fallback: str = "") -> str:
    """Montant en euros à la française (espaces comme séparateurs de milliers), arrondi à
    l'entier. `suffix` = unité affichée ; `fallback` = valeur si `v` n'est pas un nombre."""
    try:
        return f"{int(round(float(v))):,}".replace(",", " ") + suffix
    except (ValueError, TypeError):
        return fallback


# ── Heures lisibles (documents remis aux entreprises) ──────────────────────────────────
# Les dates en base sont en UTC « naïf » (un datetime sans fuseau = UTC). Les documents lus par
# une TPE (PDF du journal, accords de la convention) les affichent à l'heure de Paris, comme
# l'écran. AFFICHAGE SEULEMENT : ce qui est haché ou vérifié (champ `at` du journal, empreinte
# de la convention) reste en UTC et n'appelle jamais ces fonctions.
FUSEAU_PARIS = "Europe/Paris"


@lru_cache(maxsize=1)
def _tz_paris():
    """Fuseau de Paris, ou None si la base des fuseaux est introuvable. L'image de production
    (python:3.12-slim) n'a pas de base système : elle vient du paquet tzdata (requirements.lock)."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(FUSEAU_PARIS)
    except Exception:
        return None


def libelle_fuseau() -> str:
    """« heure de Paris », ou « UTC » en repli (base des fuseaux absente)."""
    return "heure de Paris" if _tz_paris() is not None else "UTC"


def date_heure_fr(dt, suffixe: bool = True) -> str:
    """« 11/10/2026 à 22:28 (heure de Paris) » ; sans `suffixe` : « 11/10/2026 à 22:28 » (le
    fuseau est alors dit ailleurs, par exemple dans l'en-tête d'une colonne : libelle_fuseau()).
    Datetime naïf = UTC. Repli sans base des fuseaux : l'heure UTC, dite « (UTC) ». '' si vide."""
    if not dt:
        return ""
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        tz = _tz_paris()
        local = dt.astimezone(tz if tz is not None else timezone.utc)
        out = local.strftime("%d/%m/%Y à %H:%M")
        return f"{out} ({libelle_fuseau()})" if suffixe else out
    except Exception:
        return str(dt)
