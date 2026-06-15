"""
Adjugo — Couche LLM centralisée.
Un seul endroit pour le modèle Claude et les appels JSON structurés.
Tous les agents passent par ici.
"""
import contextvars
import json
import logging
import os
import re
import threading
import time
from typing import Optional
from anthropic import Anthropic
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger("adjugo")

# Verrou des mutations d'état partagé (compteurs, disjoncteurs) : le pool de jobs et
# les requêtes concurrentes mettent à jour ces dicts ; `x += 1` n'est pas atomique.
_LOCK = threading.Lock()

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


# ── Compteurs de tokens : global (par process) + PAR TENANT ──────────────────
TOKENS = {"input": 0, "output": 0, "calls": 0}
# Plafond global de tokens cumulés par process. 0 = désactivé.
_TOKEN_HARD_CAP = int(os.getenv("LLM_TOKEN_HARD_CAP", "0"))
# Plafond PAR TENANT (anti « voisin bruyant » : un client ne peut pas épuiser le
# budget des autres). 0 = désactivé. Le tenant courant est porté par un contextvar,
# positionné au début d'un job / d'une requête (cf. tenant_scope).
_TOKEN_CAP_PER_TENANT = int(os.getenv("LLM_TOKEN_CAP_PER_TENANT", "0"))
_TENANT_TOKENS = {}          # tenant_id -> tokens cumulés (borné en nombre de tenants)
_TENANT_TOKENS_MAX = 5000
_CURRENT_TENANT = contextvars.ContextVar("adjugo_tenant", default=None)


class tenant_scope:
    """Délimite le tenant courant pour l'attribution/plafond des tokens IA.
    Usage : `with tenant_scope(user_id): ...`. Sûr en thread (contextvar)."""
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id
        self._token = None

    def __enter__(self):
        self._token = _CURRENT_TENANT.set(self.tenant_id)
        return self

    def __exit__(self, *exc):
        if self._token is not None:
            _CURRENT_TENANT.reset(self._token)
        return False


def tenant_usage(tenant_id) -> int:
    return _TENANT_TOKENS.get(tenant_id, 0)


# ── Latence des appels IA (histogramme Prometheus) ───────────────────────────
_LAT_BUCKETS = [0.5, 1, 2, 5, 10, 30]
_LAT = {"counts": {b: 0 for b in _LAT_BUCKETS}, "sum": 0.0, "count": 0}


def _record_latency(dt: float) -> None:
    """Histogramme cumulatif (le=bucket) de la durée des appels Claude réussis."""
    _LAT["sum"] += dt
    _LAT["count"] += 1
    for b in _LAT_BUCKETS:
        if dt <= b:
            _LAT["counts"][b] += 1


def latency_snapshot() -> dict:
    """Copie cohérente de l'histogramme de latence pour /metrics."""
    with _LOCK:
        return {"buckets": dict(_LAT["counts"]), "sum": _LAT["sum"], "count": _LAT["count"]}


def _track_usage(model: str, resp) -> None:
    try:
        u = getattr(resp, "usage", None)
        if not u:
            return
        used = (getattr(u, "input_tokens", 0) or 0) + (getattr(u, "output_tokens", 0) or 0)
        TOKENS["input"] += getattr(u, "input_tokens", 0) or 0
        TOKENS["output"] += getattr(u, "output_tokens", 0) or 0
        TOKENS["calls"] += 1
        tid = _CURRENT_TENANT.get()
        if tid is not None:
            if tid not in _TENANT_TOKENS and len(_TENANT_TOKENS) >= _TENANT_TOKENS_MAX:
                _TENANT_TOKENS.pop(next(iter(_TENANT_TOKENS)), None)   # éviction FIFO bornée
            _TENANT_TOKENS[tid] = _TENANT_TOKENS.get(tid, 0) + used
    except Exception:
        pass


# ── Disjoncteur (circuit breaker) GLOBAL + PAR TENANT ────────────────────────
# Global : après N échecs consécutifs (panne API), on ouvre le circuit pendant un
# cooldown → échec rapide pour tous. Un succès (de n'importe quel tenant) le referme.
# Par tenant : un client dont LES appels échouent (entrées pathologiques) voit SON
# circuit s'ouvrir, sans pénaliser les autres — isolation « voisin bruyant » au niveau
# résilience, pas seulement coût.
_CB = {"fails": 0, "open_until": 0.0}
_CB_THRESHOLD = int(os.getenv("LLM_CB_THRESHOLD", "5"))
_CB_COOLDOWN = float(os.getenv("LLM_CB_COOLDOWN", "30"))
_TENANT_CB = {}          # tenant_id -> {"fails": int, "open_until": float}  (borné)
_TENANT_CB_MAX = 5000
_TCB_THRESHOLD = int(os.getenv("LLM_TENANT_CB_THRESHOLD", "4"))


def _tenant_cb(tid):
    cb = _TENANT_CB.get(tid)
    if cb is None:
        if len(_TENANT_CB) >= _TENANT_CB_MAX:
            _TENANT_CB.pop(next(iter(_TENANT_CB)), None)
        cb = _TENANT_CB[tid] = {"fails": 0, "open_until": 0.0}
    return cb


def messages_create(**kwargs):
    """Point d'entrée CENTRAL vers Claude : disjoncteur (global + tenant) + plafonds
    (global ET par tenant) + suivi usage. Tous les appels passent par ici."""
    now = time.monotonic()
    tid = _CURRENT_TENANT.get()
    if _CB["open_until"] > now:
        raise LLMUnavailable("Service IA temporairement indisponible (circuit global ouvert). Réessayez sous peu.")
    if tid is not None and _TENANT_CB.get(tid, {}).get("open_until", 0.0) > now:
        raise LLMUnavailable("Service IA momentanément indisponible pour votre espace. Réessayez sous peu.")
    if _TOKEN_HARD_CAP and (TOKENS["input"] + TOKENS["output"]) >= _TOKEN_HARD_CAP:
        logger.error("Plafond de tokens IA GLOBAL atteint (%s) — appels refusés.", _TOKEN_HARD_CAP)
        raise LLMUnavailable("Plafond de tokens IA atteint pour ce processus.")
    if _TOKEN_CAP_PER_TENANT and tid is not None and _TENANT_TOKENS.get(tid, 0) >= _TOKEN_CAP_PER_TENANT:
        logger.warning("Plafond de tokens IA atteint pour le tenant %s (%s) — appel refusé.",
                       tid, _TOKEN_CAP_PER_TENANT)
        raise LLMUnavailable("Plafond de tokens IA atteint pour votre espace. Réessayez plus tard.")
    t0 = time.monotonic()
    try:
        resp = client().messages.create(**kwargs)
    except Exception:
        with _LOCK:
            _CB["fails"] += 1
            if _CB["fails"] >= _CB_THRESHOLD and _CB["open_until"] <= now:
                _CB["open_until"] = time.monotonic() + _CB_COOLDOWN
                logger.error("Disjoncteur IA GLOBAL ouvert après %s échecs — pause %ss.", _CB["fails"], _CB_COOLDOWN)
            if tid is not None:
                tcb = _tenant_cb(tid)
                tcb["fails"] += 1
                if tcb["fails"] >= _TCB_THRESHOLD and tcb["open_until"] <= now:
                    tcb["open_until"] = time.monotonic() + _CB_COOLDOWN
                    logger.warning("Disjoncteur IA ouvert pour le tenant %s après %s échecs.", tid, tcb["fails"])
        raise
    dt = time.monotonic() - t0
    with _LOCK:
        if _CB["fails"]:
            logger.info("Disjoncteur IA global refermé (appel réussi après %s échecs).", _CB["fails"])
        _CB["fails"] = 0
        _CB["open_until"] = 0.0
        if tid is not None and tid in _TENANT_CB:
            _TENANT_CB[tid]["fails"] = 0
            _TENANT_CB[tid]["open_until"] = 0.0
        _record_latency(dt)
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
