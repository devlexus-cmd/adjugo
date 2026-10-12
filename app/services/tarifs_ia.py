"""
Tarifs publics des modèles d'IA et coût d'un appel, en euros. Interne : jamais montré au client.

Sert à mesurer le coût RÉEL de chaque appel (llm.messages_create → budget_ia) et à estimer, avant
une opération, ce qu'elle coûtera au plus (garde-fou de l'essai gratuit).

Tarifs relevés le 12/10/2026, par million de tokens :
  • Anthropic, API directe (en dollars, platform.claude.com/docs/en/about-claude/pricing) :
      Sonnet 5.5 (`claude-sonnet-5-5`) 2 / 10, lecture du cache 0,10 (0,05 × l'entrée), écriture 2,50 ;
      Haiku 5.5 (`claude-haiku-5-5`) 0,10 / 0,50 jusqu'à 100 000 tokens d'entrée par requête, puis
      0,50 / 2,50 pour toute la requête ; Opus 5.5 4 / 20 ; Sonnet 4.6 3 / 15 ; Haiku 4.5 1 / 5.
      Cache : écriture (5 minutes) 1,25 × l'entrée ; lecture 0,1 × (0,05 × sur Sonnet 5.5 et Opus 5.5).
      Les modèles 4.7 et suivants découpent le même texte en ≈ 30 % de tokens de plus
      (`facteur_tokens`, utilisé pour les ESTIMATIONS faites à partir d'un nombre de caractères).
  • Mistral, La Plateforme (publiés en euros, docs.mistral.ai/inference/pricing) :
      Large 4 (`mistral-large-4`, préversion publique du 06/10/2026) 1,156 / 3,553, prix NORMAL retenu
      (le prix soldé de moitié n'a pas de date de fin publiée) ; Large 3 (`mistral-large-2512`)
      0,425 / 1,275 ; Medium 3.5 1,275 / 6,375 ; Small 4 0,1275 / 0,51. Point d'accès européen
      (api.eu.mistral.ai) : 1,1 × tous les prix. Le relevé de Mistral ne distingue pas le cache :
      tout le texte envoyé est compté au prix d'entrée (jamais sous-estimé).
  • L'alias `mistral-large-latest` (Large 3 au 12/10/2026, susceptible de changer) est compté au prix
    de Large 4, le plus cher des deux. Un modèle inconnu est compté au prix d'Opus 5.5 (le plus cher
    des modèles utilisables) et signalé une fois au journal : le coût n'est jamais sous-estimé.
Conversion : 1 $ = AI_USD_EUR € (0,85 par défaut, rapport des deux affichages de Mistral).
"""
import logging
import threading

from app.core.config import get_settings

logger = logging.getLogger("adjugo")

# (clé cherchée dans l'identifiant du modèle, en minuscules) → tarif. L'ordre compte : la première
# clé contenue dans l'identifiant l'emporte (les identifiants Bedrock « anthropic.claude-… » et les
# versions datées sont reconnus).
#   devise, entrée, sortie, lecture du cache, écriture du cache, facteur_tokens,
#   et pour Haiku 5.5 : seuil de la requête longue et prix au-delà.
_TARIFS = [
    ("claude-sonnet-5-5", {"devise": "USD", "entree": 2.0, "sortie": 10.0, "cache_lu": 0.10, "cache_ecrit": 2.50,
                           "facteur_tokens": 1.3}),
    ("claude-haiku-5-5", {"devise": "USD", "entree": 0.10, "sortie": 0.50, "cache_lu": 0.01, "cache_ecrit": 0.125,
                          "facteur_tokens": 1.3, "seuil_long": 100_000,
                          "long": {"entree": 0.50, "sortie": 2.50, "cache_lu": 0.05, "cache_ecrit": 0.625}}),
    ("claude-opus-5-5", {"devise": "USD", "entree": 4.0, "sortie": 20.0, "cache_lu": 0.20, "cache_ecrit": 5.0,
                         "facteur_tokens": 1.3}),
    ("claude-sonnet-4-6", {"devise": "USD", "entree": 3.0, "sortie": 15.0, "cache_lu": 0.30, "cache_ecrit": 3.75,
                           "facteur_tokens": 1.0}),
    ("claude-haiku-4-5", {"devise": "USD", "entree": 1.0, "sortie": 5.0, "cache_lu": 0.10, "cache_ecrit": 1.25,
                          "facteur_tokens": 1.0}),
    ("mistral-large-4", {"devise": "EUR", "entree": 1.156, "sortie": 3.553, "cache_lu": 1.156, "cache_ecrit": 1.156,
                         "facteur_tokens": 1.3, "mistral": True}),
    ("mistral-large-latest", {"devise": "EUR", "entree": 1.156, "sortie": 3.553, "cache_lu": 1.156,
                              "cache_ecrit": 1.156, "facteur_tokens": 1.3, "mistral": True}),
    ("mistral-large-2512", {"devise": "EUR", "entree": 0.425, "sortie": 1.275, "cache_lu": 0.425, "cache_ecrit": 0.425,
                            "facteur_tokens": 1.3, "mistral": True}),
    ("mistral-large-3", {"devise": "EUR", "entree": 0.425, "sortie": 1.275, "cache_lu": 0.425, "cache_ecrit": 0.425,
                         "facteur_tokens": 1.3, "mistral": True}),
    ("mistral-medium", {"devise": "EUR", "entree": 1.275, "sortie": 6.375, "cache_lu": 1.275, "cache_ecrit": 1.275,
                        "facteur_tokens": 1.3, "mistral": True}),
    ("mistral-small", {"devise": "EUR", "entree": 0.1275, "sortie": 0.51, "cache_lu": 0.1275, "cache_ecrit": 0.1275,
                       "facteur_tokens": 1.3, "mistral": True}),
]
# Modèle inconnu : prix d'Opus 5.5 (le plus cher des modèles que l'application peut appeler).
_INCONNU = {"devise": "USD", "entree": 4.0, "sortie": 20.0, "cache_lu": 4.0, "cache_ecrit": 5.0,
            "facteur_tokens": 1.3}
_SIGNALES = set()
_SIGNALES_LOCK = threading.Lock()


def tarif(modele) -> dict:
    """Tarif du modèle (identifiant tel qu'envoyé au fournisseur ou renvoyé par lui)."""
    m = str(modele or "").strip().lower()
    for cle, t in _TARIFS:
        if cle in m:
            return t
    with _SIGNALES_LOCK:
        nouveau = m not in _SIGNALES
        if nouveau and len(_SIGNALES) < 200:
            _SIGNALES.add(m)
    if nouveau:
        logger.warning("Tarif IA inconnu pour le modèle « %s » : compté au prix du modèle le plus cher.", m or "?")
    return _INCONNU


def connu(modele) -> bool:
    m = str(modele or "").strip().lower()
    return any(cle in m for cle, _t in _TARIFS)


def taux_usd_eur() -> float:
    try:
        v = float(get_settings().AI_USD_EUR or 0)
        return v if v > 0 else 0.85
    except (TypeError, ValueError):
        return 0.85


def _majoration(t: dict) -> float:
    """Point d'accès européen de Mistral : 1,1 × tous les prix."""
    if t.get("mistral"):
        base = str(getattr(get_settings(), "MISTRAL_BASE_URL", "") or "").lower()
        if "api.eu.mistral.ai" in base:
            return 1.1
    return 1.0


def _cout_devise(t: dict, tin: int, tout: int, cache_lus: int, cache_ecrits: int) -> float:
    p = t
    if t.get("seuil_long") and (tin + cache_lus + cache_ecrits) > t["seuil_long"]:
        p = dict(t, **t["long"])
    return ((tin * p["entree"] + tout * p["sortie"] + cache_lus * p["cache_lu"] + cache_ecrits * p["cache_ecrit"])
            / 1_000_000 * _majoration(t))


def cout_eur(modele, tokens_entree: int = 0, tokens_sortie: int = 0, cache_lus: int = 0,
             cache_ecrits: int = 0) -> float:
    """Coût d'UN appel en euros. tokens_entree : tokens d'entrée HORS cache ; cache_lus / cache_ecrits :
    tokens d'entrée lus dans le cache / écrits dans le cache (champs séparés du relevé Anthropic)."""
    t = tarif(modele)
    c = _cout_devise(t, max(0, int(tokens_entree or 0)), max(0, int(tokens_sortie or 0)),
                     max(0, int(cache_lus or 0)), max(0, int(cache_ecrits or 0)))
    return round(c * (taux_usd_eur() if t["devise"] == "USD" else 1.0), 6)


def cout_usd(modele, tokens_entree: int = 0, tokens_sortie: int = 0, cache_lus: int = 0,
             cache_ecrits: int = 0) -> float:
    """Même coût, en dollars (journal de llm.cost_meter)."""
    t = tarif(modele)
    c = _cout_devise(t, max(0, int(tokens_entree or 0)), max(0, int(tokens_sortie or 0)),
                     max(0, int(cache_lus or 0)), max(0, int(cache_ecrits or 0)))
    return c if t["devise"] == "USD" else c / taux_usd_eur()


# ── Estimation AVANT une opération (à partir d'un nombre de caractères) ──────────────────
# 3,0 caractères par token (français chiffré : 3,0 à 3,6 ; hypothèse prudente, comme la lecture
# intégrale), multipliés par le facteur de découpage du modèle.
CARACTERES_PAR_TOKEN = 3.0


def tokens_de(modele, caracteres: int) -> int:
    return int(max(0, int(caracteres or 0)) / CARACTERES_PAR_TOKEN * tarif(modele).get("facteur_tokens", 1.0)) + 1


def estimer_eur(modele, caracteres_entree: int = 0, tokens_sortie: int = 0, caracteres_cache_ecrits: int = 0,
                caracteres_cache_lus: int = 0) -> float:
    """Coût estimé d'un appel à partir de la taille de ce qui part (caractères) et de la sortie
    maximale (tokens, multipliée par le facteur de découpage du modèle)."""
    f = tarif(modele).get("facteur_tokens", 1.0)
    return cout_eur(modele, tokens_de(modele, caracteres_entree), int(max(0, tokens_sortie) * f) + 1,
                    cache_lus=tokens_de(modele, caracteres_cache_lus) if caracteres_cache_lus else 0,
                    cache_ecrits=tokens_de(modele, caracteres_cache_ecrits) if caracteres_cache_ecrits else 0)
