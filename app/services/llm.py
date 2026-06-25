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
import httpx
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


# ── Fournisseur IA interchangeable : Anthropic (défaut) ou Mistral (souverain) ──
# Toute l'app appelle messages_create() avec le format Anthropic (system + messages).
# Quand LLM_PROVIDER=mistral ET qu'une clé Mistral est présente, on traduit cet appel
# vers l'API Mistral (compatible OpenAI) puis on ré-emballe la réponse dans la MÊME
# forme qu'Anthropic (resp.content[0].text, resp.usage.input/output_tokens) — donc
# aucun agent en aval ne change. Repli auto sur Anthropic si la clé Mistral manque.
_PROVIDER_WARNED = {"missing_key": False}


def _resolve_provider() -> str:
    """Fournisseur effectif. Mode 'auto' (défaut) → MISTRAL dès qu'une clé est présente, sinon
    Anthropic. Donc ajouter MISTRAL_API_KEY suffit à basculer (rien d'autre à régler). Forçable
    via LLM_PROVIDER=anthropic|mistral. 'mistral' sans clé → repli sûr sur Anthropic."""
    prov = (os.getenv("LLM_PROVIDER") or settings.LLM_PROVIDER or "auto").strip().lower()
    if prov == "anthropic":
        return "anthropic"
    if prov == "mistral":
        if settings.MISTRAL_API_KEY:
            return "mistral"
        if not _PROVIDER_WARNED["missing_key"]:
            logger.warning("LLM_PROVIDER=mistral mais MISTRAL_API_KEY absente → repli sur Anthropic.")
            _PROVIDER_WARNED["missing_key"] = True
        return "anthropic"
    # auto : la clé Mistral décide.
    return "mistral" if settings.MISTRAL_API_KEY else "anthropic"


def active_provider() -> dict:
    """Fournisseur IA réellement actif (sans secret) — pour /metrics, /api/llm/info, UI."""
    if _resolve_provider() == "mistral":
        return {"provider": "mistral", "model": settings.MISTRAL_MODEL,
                "model_fast": settings.MISTRAL_MODEL_FAST,
                "label": "Mistral Large", "sovereign": True, "region": "FR/EU"}
    return {"provider": "anthropic", "model": MODEL, "model_fast": MODEL_FAST,
            "label": "Claude (Anthropic)", "sovereign": False, "region": "US"}


def _use_mistral() -> bool:
    return _resolve_provider() == "mistral"


class _Usage:
    __slots__ = ("input_tokens", "output_tokens")

    def __init__(self, i, o):
        self.input_tokens = i or 0
        self.output_tokens = o or 0


class _Block:
    __slots__ = ("type", "text")

    def __init__(self, text):
        self.type = "text"
        self.text = text or ""


class _Resp:
    """Réponse compatible Anthropic (resp.content[0].text, resp.usage.*)."""
    __slots__ = ("content", "usage", "stop_reason")

    def __init__(self, text, usage, stop_reason="end_turn"):
        self.content = [_Block(text)]
        self.usage = usage
        self.stop_reason = stop_reason


def _map_model_to_mistral(model: Optional[str]) -> str:
    m = (model or "").lower()
    if model == MODEL_FAST or "haiku" in m or "fast" in m or "small" in m:
        return settings.MISTRAL_MODEL_FAST
    return settings.MISTRAL_MODEL


def _flatten_content(content) -> str:
    """Le contenu Anthropic peut être une str ou une liste de blocs ; Mistral veut une str."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            (b.get("text", "") if isinstance(b, dict) else str(b)) for b in content
        )
    return "" if content is None else str(content)


def _to_openai_messages(system, messages) -> list:
    out = []
    if system:
        out.append({"role": "system", "content": _flatten_content(system)})
    for m in (messages or []):
        out.append({"role": m.get("role", "user"),
                    "content": _flatten_content(m.get("content"))})
    return out


def _mistral_create(model=None, max_tokens=1024, temperature=0.2,
                    system="", messages=None, **_ignored):
    """Traduit un appel façon Anthropic vers l'API Mistral et ré-emballe la réponse."""
    payload = {
        "model": _map_model_to_mistral(model),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": _to_openai_messages(system, messages),
    }
    url = settings.MISTRAL_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.MISTRAL_API_KEY}",
               "Content-Type": "application/json"}
    r = httpx.post(url, json=payload, headers=headers, timeout=_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    choice = (data.get("choices") or [{}])[0]
    text = ((choice.get("message") or {}).get("content")) or ""
    u = data.get("usage") or {}
    return _Resp(text, _Usage(u.get("prompt_tokens", 0), u.get("completion_tokens", 0)),
                 choice.get("finish_reason", "stop"))


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
        if _use_mistral():
            resp = _mistral_create(**kwargs)            # ré-emballé en réponse façon Anthropic
        else:
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
