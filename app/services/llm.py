"""
Adjugo — Couche LLM centralisée.
Un seul endroit pour le modèle Claude et les appels JSON structurés.
Tous les agents passent par ici.
"""
import json
import os
import re
import time
from typing import Optional
from anthropic import Anthropic
from app.core.config import get_settings

settings = get_settings()

# Modèles Claude courants (cf. roster Anthropic à jour).
MODEL = "claude-sonnet-4-6"        # raisonnement (analyse, stratégie)
MODEL_FAST = "claude-haiku-4-5"    # rédaction rapide (mémoire, prose)

# Délais & reprises : un appel IA ne doit pas bloquer un worker indéfiniment.
_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "180"))     # secondes par appel
_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

_client: Optional[Anthropic] = None


class LLMUnavailable(RuntimeError):
    """Service IA momentanément indisponible (circuit ouvert ou plafond atteint)."""


def client() -> Anthropic:
    """Client Anthropic paresseux (évite de planter à l'import si pas de clé)."""
    global _client
    if _client is None:
        _client = Anthropic(api_key=settings.ANTHROPIC_API_KEY,
                            timeout=_TIMEOUT, max_retries=_MAX_RETRIES)
    return _client


# ── Compteurs de tokens (par process) + PLAFOND dur optionnel ────────────────
TOKENS = {"input": 0, "output": 0, "calls": 0}
# Plafond de tokens cumulés par process. 0 = désactivé. Quand atteint, on REFUSE les
# nouveaux appels (plafonnement réel, pas qu'une alerte) — garde anti-emballement coût.
_TOKEN_HARD_CAP = int(os.getenv("LLM_TOKEN_HARD_CAP", "0"))


def _track_usage(model: str, resp) -> None:
    try:
        u = getattr(resp, "usage", None)
        if u:
            TOKENS["input"] += getattr(u, "input_tokens", 0) or 0
            TOKENS["output"] += getattr(u, "output_tokens", 0) or 0
            TOKENS["calls"] += 1
    except Exception:
        pass


# ── Disjoncteur (circuit breaker) par process ────────────────────────────────
# Après N échecs consécutifs, on OUVRE le circuit pendant un cooldown : les appels
# suivants échouent vite (LLMUnavailable) au lieu de marteler une API IA en panne et
# de saturer le pool de jobs. Un succès referme le circuit.
_CB = {"fails": 0, "open_until": 0.0}
_CB_THRESHOLD = int(os.getenv("LLM_CB_THRESHOLD", "5"))
_CB_COOLDOWN = float(os.getenv("LLM_CB_COOLDOWN", "30"))


def messages_create(**kwargs):
    """Point d'entrée CENTRAL vers Claude : disjoncteur + plafond tokens + suivi usage.
    Tous les appels (agents ET analyse DCE) doivent passer par ici."""
    now = time.monotonic()
    if _CB["open_until"] > now:
        raise LLMUnavailable("Service IA temporairement indisponible (circuit ouvert). Réessayez sous peu.")
    if _TOKEN_HARD_CAP and (TOKENS["input"] + TOKENS["output"]) >= _TOKEN_HARD_CAP:
        raise LLMUnavailable("Plafond de tokens IA atteint pour ce processus.")
    try:
        resp = client().messages.create(**kwargs)
    except Exception:
        _CB["fails"] += 1
        if _CB["fails"] >= _CB_THRESHOLD:
            _CB["open_until"] = time.monotonic() + _CB_COOLDOWN
        raise
    _CB["fails"] = 0
    _CB["open_until"] = 0.0
    _track_usage(kwargs.get("model", MODEL), resp)
    return resp


def complete(system: str, user: str, max_tokens: int = 3000, temperature: float = 0.2,
             model: Optional[str] = None) -> str:
    """Appel texte simple. Retourne le texte de la réponse."""
    resp = messages_create(
        model=model or MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text.strip()


def complete_json(system: str, user: str, max_tokens: int = 3000, temperature: float = 0.2) -> dict:
    """Appel attendant un JSON. Nettoie les fences markdown et parse robustement."""
    raw = complete(system, user, max_tokens=max_tokens, temperature=temperature)
    return parse_json(raw)


def parse_json(raw: str) -> dict:
    """Parse un JSON potentiellement entouré de ```json ... ``` ou de texte."""
    text = raw.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Dernier recours : extraire le premier objet {...} équilibré
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    raise ValueError(f"Réponse LLM non JSON: {raw[:200]}")
