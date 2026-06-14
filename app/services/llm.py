"""
Adjugo — Couche LLM centralisée.
Un seul endroit pour le modèle Claude et les appels JSON structurés.
Tous les agents passent par ici.
"""
import json
import re
from typing import Optional
from anthropic import Anthropic
from app.core.config import get_settings

settings = get_settings()

# Modèles Claude courants (cf. roster Anthropic à jour).
MODEL = "claude-sonnet-4-6"        # raisonnement (analyse, stratégie)
MODEL_FAST = "claude-haiku-4-5"    # rédaction rapide (mémoire, prose)

_client: Optional[Anthropic] = None


def client() -> Anthropic:
    """Client Anthropic paresseux (évite de planter à l'import si pas de clé)."""
    global _client
    if _client is None:
        _client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def complete(system: str, user: str, max_tokens: int = 3000, temperature: float = 0.2,
             model: Optional[str] = None) -> str:
    """Appel texte simple. Retourne le texte de la réponse."""
    resp = client().messages.create(
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
