"""
Tarifs publics des modèles d'IA et coût d'un appel. Interne : jamais montré au client.

SEULE table des prix de l'application. Elle sert :
  • au coût RÉEL de chaque appel, calculé UNE fois par llm._track_usage (modèle réellement appelé,
    point d'accès réellement utilisé, cache compris, secours compris : chaque essai facturé compte),
    puis porté au même montant dans le journal de llm.cost_meter et dans le relevé du compte facturé
    (app/services/budget_ia.py : budget de l'essai gratuit, alerte des forfaits payants) ;
  • aux estimations faites AVANT une opération (garde-fou de l'essai gratuit, budget_ia.estimer*) et
    aux estimations de la documentation (llm.estimer_cout).

Tarifs relevés le 12/10/2026, en dollars par million de tokens (conversion en euros à la fin) :
  • Anthropic, API directe (platform.claude.com/docs/en/about-claude/pricing) :
      Sonnet 5.5 (`claude-sonnet-5-5`) 2 / 10, lecture du cache 0,10 (0,05 × l'entrée), écriture
      2,50 (5 minutes) ou 4 (1 heure) ; Haiku 5.5 (`claude-haiku-5-5`) 0,10 / 0,50 jusqu'à 100 000
      tokens d'entrée par requête (cache compris), puis 0,50 / 2,50 pour toute la requête ; Opus 5.5
      4 / 20 ; Sonnet 4.6 3 / 15 ; Haiku 4.5 1 / 5. Écriture du cache : 1,25 × l'entrée (5 minutes),
      2 × (1 heure) ; lecture : 0,1 × (0,05 × sur la génération 5.5).
  • Mistral, La Plateforme (docs.mistral.ai, prix publiés en $ et en €, rapport 0,85) :
      Large 4 (`mistral-large-4`, préversion publique du 06/10/2026) 1,36 / 4,18, cache lu 0,14 ;
      soldé de moitié à son lancement (0,68 / 2,09 / 0,07), « 50 % off for 2 weeks » d'après le
      journal des modifications de Mistral (vérifié le 12/10/2026) : prix soldé jusqu'au
      MISTRAL_SOLDE_JUSQU_AU inclus (2026-10-19 par défaut ; « aucun » = prix normal), prix
      surchargeables par MISTRAL_PRIX_LARGE4 et MISTRAL_PRIX_LARGE4_SOLDE (« entrée|sortie|cache »).
      Large 3 (`mistral-large-2512`) 0,50 / 1,50 / 0,05 ; Medium 3.5 1,50 / 7,50 / 0,15 ; Small 4
      0,15 / 0,60 / 0,015. Cache : les tokens relus sont signalés par
      usage.prompt_tokens_details.cached_tokens et facturés 10 % du prix d'entrée ; aucune écriture
      facturée à part. Point d'accès européen (api.eu.mistral.ai) : + MISTRAL_SURCOUT_UE (10 %) sur
      tout, appliqué selon la zone RÉELLEMENT utilisée par l'appel (resp.zone).
  • L'alias `mistral-large-latest` (Large 3 au 12/10/2026, susceptible de changer) est compté au prix
    de Large 4, le plus cher des deux. Un modèle inconnu est compté au prix d'Opus 5.5 (le plus cher
    des modèles utilisables, cache non remisé) et signalé une fois au journal : le coût n'est jamais
    sous-estimé. `connu()` permet aux journaux de dire « coût non estimé » plutôt qu'un prix deviné.
Conversion : 1 $ = AI_USD_EUR € (0,85 par défaut, rapport des deux affichages de Mistral).
"""
import datetime as _dt
import logging
import os
import threading
from typing import Optional

from app.core.config import get_settings

logger = logging.getLogger("adjugo")

# Anthropic : (clé cherchée dans l'identifiant, en minuscules) → tarif en $. L'ordre compte : la
# première clé contenue dans l'identifiant l'emporte (identifiants Bedrock « anthropic.claude-… » et
# versions datées reconnus). facteur_tokens : tokens produits pour un même texte rapportés à l'ancien
# découpage de Claude (≈ +30 % pour la génération 4.7 et suivantes), utilisé par les ESTIMATIONS.
_ANTHROPIC = [
    ("claude-sonnet-5-5", {"entree": 2.0, "sortie": 10.0, "cache_lu": 0.10, "cache_5m": 2.50, "cache_1h": 4.00,
                           "facteur_tokens": 1.3}),
    ("claude-haiku-5-5", {"entree": 0.10, "sortie": 0.50, "cache_lu": 0.01, "cache_5m": 0.125, "cache_1h": 0.20,
                          "facteur_tokens": 1.3, "seuil_long": 100_000,
                          "long": {"entree": 0.50, "sortie": 2.50, "cache_lu": 0.05, "cache_5m": 0.625,
                                   "cache_1h": 1.00}}),
    ("claude-opus-5-5", {"entree": 4.0, "sortie": 20.0, "cache_lu": 0.20, "cache_5m": 5.00, "cache_1h": 8.00,
                         "facteur_tokens": 1.3}),
    ("claude-sonnet-4-6", {"entree": 3.0, "sortie": 15.0, "cache_lu": 0.30, "cache_5m": 3.75, "cache_1h": 6.00,
                           "facteur_tokens": 1.0}),
    ("claude-haiku-4-5", {"entree": 1.0, "sortie": 5.0, "cache_lu": 0.10, "cache_5m": 1.25, "cache_1h": 2.00,
                          "facteur_tokens": 1.0}),
]
# Mistral : (clé, prix fixe (entrée, sortie, cache lu) en $ ; None = Large 4, prix soldé ou normal).
# Découpage du français non publié : 1,3 pour les estimations (prudent, comme les plafonds de sortie).
_MISTRAL = [
    ("mistral-large-4", None),
    ("mistral-large-latest", None),          # alias : compté au prix de Large 4, le plus haut
    ("mistral-large-2512", (0.50, 1.50, 0.05)),
    ("mistral-large-3", (0.50, 1.50, 0.05)),
    ("mistral-medium", (1.50, 7.50, 0.15)),
    ("mistral-small", (0.15, 0.60, 0.015)),
]
_FACTEUR_MISTRAL = 1.3
LARGE4_NORMAL = (1.36, 4.18, 0.14)
LARGE4_SOLDE = (0.68, 2.09, 0.07)
SOLDE_JUSQU_AU_DEFAUT = "2026-10-19"         # lancement du 06/10/2026, « 50 % off for 2 weeks »
# Modèle inconnu : prix d'Opus 5.5, cache non remisé (jamais sous-estimé).
_INCONNU = {"entree": 4.0, "sortie": 20.0, "cache_lu": 4.0, "cache_5m": 5.0, "cache_1h": 8.0,
            "facteur_tokens": 1.3}
_SIGNALES = set()
_SIGNALES_LOCK = threading.Lock()


def _id(modele) -> str:
    return str(modele or "").strip().lower()


def _env_prix(nom: str, defaut: tuple) -> tuple:
    v = (os.getenv(nom) or "").strip()
    if not v:
        return defaut
    try:
        parts = tuple(float(x.strip().replace(",", ".")) for x in v.replace(";", "|").replace("/", "|").split("|"))
        if len(parts) == 3 and all(p >= 0 for p in parts):
            return parts
    except ValueError:
        pass
    logger.warning("%s illisible (attendu « entrée|sortie|cache ») : prix par défaut gardé.", nom)
    return defaut


def solde_en_cours(jour: Optional[_dt.date] = None) -> bool:
    """Prix de lancement de Mistral Large 4 en cours (jusqu'à MISTRAL_SOLDE_JUSQU_AU inclus) ?"""
    fin = (os.getenv("MISTRAL_SOLDE_JUSQU_AU") or SOLDE_JUSQU_AU_DEFAUT).strip()
    if not fin or fin.lower() in ("aucun", "non", "0"):
        return False
    try:
        return (jour or _dt.date.today()) <= _dt.date.fromisoformat(fin)
    except ValueError:
        return False


def surcout_ue() -> float:
    try:
        return max(0.0, float(os.getenv("MISTRAL_SURCOUT_UE", "0.10")))
    except ValueError:
        return 0.10


def prix_mistral(modele, jour: Optional[_dt.date] = None) -> Optional[tuple]:
    """(entrée, sortie, cache lu) en $ par million, au point d'accès mondial ; None si ce n'est pas
    un modèle Mistral au tarif connu."""
    m = _id(modele)
    for cle, fixe in _MISTRAL:
        if cle in m:
            if fixe is not None:
                return fixe
            if solde_en_cours(jour):
                return _env_prix("MISTRAL_PRIX_LARGE4_SOLDE", LARGE4_SOLDE)
            return _env_prix("MISTRAL_PRIX_LARGE4", LARGE4_NORMAL)
    return None


def _anthropic(m: str) -> Optional[dict]:
    for cle, t in _ANTHROPIC:
        if cle in m:
            return t
    return None


def connu(modele) -> bool:
    m = _id(modele)
    return _anthropic(m) is not None or prix_mistral(m) is not None


def tarif(modele, zone: str = "", jour: Optional[_dt.date] = None) -> dict:
    """Tarif du modèle ($ par million) au point d'accès donné (« ue » : Mistral + 10 %) :
    {entree, sortie, cache_lu, cache_5m, cache_1h, facteur_tokens[, seuil_long, long], mistral}."""
    m = _id(modele)
    t = _anthropic(m)
    if t is not None:
        return dict(t, mistral=False)
    pm = prix_mistral(m, jour)
    if pm is not None:
        k = 1.0 + (surcout_ue() if zone == "ue" else 0.0)
        pin, pout, pcr = (x * k for x in pm)
        return {"entree": pin, "sortie": pout, "cache_lu": pcr, "cache_5m": pin, "cache_1h": pin,
                "facteur_tokens": _FACTEUR_MISTRAL, "mistral": True}
    with _SIGNALES_LOCK:
        nouveau = m not in _SIGNALES
        if nouveau and len(_SIGNALES) < 200:
            _SIGNALES.add(m)
    if nouveau:
        logger.warning("Tarif IA inconnu pour le modèle « %s » : compté au prix du modèle le plus cher.", m or "?")
    return dict(_INCONNU, mistral=False)


def prix_modele(modele, zone: str = "") -> Optional[dict]:
    """Prix en $ par million {entree, sortie, cache_lu, cache_ecrit_5m, cache_ecrit_1h} ; None si
    le modèle n'a pas de tarif connu."""
    if not connu(modele):
        return None
    t = tarif(modele, zone)
    return {"entree": t["entree"], "sortie": t["sortie"], "cache_lu": t["cache_lu"],
            "cache_ecrit_5m": t["cache_5m"], "cache_ecrit_1h": t["cache_1h"]}


def taux_usd_eur() -> float:
    try:
        v = float(get_settings().AI_USD_EUR or 0)
        return v if v > 0 else 0.85
    except (TypeError, ValueError):
        return 0.85


def cout_usd(modele, tokens_entree: int = 0, tokens_sortie: int = 0, cache_lus: int = 0, cache_ecrits: int = 0,
             cache_ecrits_1h: int = 0, zone: str = "", jour: Optional[_dt.date] = None) -> float:
    """Coût d'UN appel en dollars. tokens_entree : entrée HORS cache ; cache_lus / cache_ecrits :
    tokens d'entrée lus dans le cache / écrits dans le cache (TOUS, dont cache_ecrits_1h pour une
    heure) ; zone : point d'accès réellement utilisé (« ue » : Mistral + 10 %). Jamais None : un
    modèle inconnu est compté au prix du plus cher."""
    t = tarif(modele, zone, jour)
    tin, tout = max(0, int(tokens_entree or 0)), max(0, int(tokens_sortie or 0))
    cr, cw = max(0, int(cache_lus or 0)), max(0, int(cache_ecrits or 0))
    w1 = min(max(0, int(cache_ecrits_1h or 0)), cw)
    p = t
    if t.get("seuil_long") and (tin + cr + cw) > t["seuil_long"]:
        p = dict(t, **t["long"])
    return (tin * p["entree"] + tout * p["sortie"] + cr * p["cache_lu"] + (cw - w1) * p["cache_5m"]
            + w1 * p["cache_1h"]) / 1_000_000


def cout_eur(modele, tokens_entree: int = 0, tokens_sortie: int = 0, cache_lus: int = 0, cache_ecrits: int = 0,
             cache_ecrits_1h: int = 0, zone: str = "", jour: Optional[_dt.date] = None) -> float:
    """Même coût, en euros (relevé du budget de l'essai et de l'alerte des forfaits payants)."""
    return round(cout_usd(modele, tokens_entree, tokens_sortie, cache_lus, cache_ecrits, cache_ecrits_1h, zone, jour)
                 * taux_usd_eur(), 6)


# ── Estimation AVANT une opération (à partir d'un nombre de caractères) ──────────────────
# 3,0 caractères par token (français chiffré : 3,0 à 3,6 ; hypothèse prudente, comme la lecture
# intégrale), multipliés par le facteur de découpage du modèle.
CARACTERES_PAR_TOKEN = 3.0


def facteur_tokens(modele) -> float:
    return float(tarif(modele).get("facteur_tokens", 1.0))


def tokens_de(modele, caracteres: int) -> int:
    return int(max(0, int(caracteres or 0)) / CARACTERES_PAR_TOKEN * facteur_tokens(modele)) + 1


def estimer_eur(modele, caracteres_entree: int = 0, tokens_sortie: int = 0, caracteres_cache_ecrits: int = 0,
                caracteres_cache_lus: int = 0, zone: str = "", ttl: str = "5m", sortie_envoyee: bool = False) -> float:
    """Coût estimé (€) d'un appel à partir de la taille de ce qui part (caractères) et de la sortie
    maximale : `tokens_sortie` au découpage de Sonnet 4.6 (multiplié par le facteur du modèle), ou,
    si `sortie_envoyee`, le plafond tel qu'envoyé au fournisseur (réflexion comprise). ttl : durée du
    cache écrit (« 1h » : 2 × l'entrée chez Anthropic)."""
    f = facteur_tokens(modele)
    sortie = int(max(0, int(tokens_sortie or 0)) * (1.0 if sortie_envoyee else f)) + 1
    ecrits = tokens_de(modele, caracteres_cache_ecrits) if caracteres_cache_ecrits else 0
    return cout_eur(modele, tokens_de(modele, caracteres_entree), sortie,
                    cache_lus=tokens_de(modele, caracteres_cache_lus) if caracteres_cache_lus else 0,
                    cache_ecrits=ecrits, cache_ecrits_1h=ecrits if ttl == "1h" else 0, zone=zone)
