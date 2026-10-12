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


# ── Cache de prompt (Anthropic) ─────────────────────────────────────────────────
# Le SDK épinglé (anthropic 0.34) transmet tel quel un bloc {"type": "text", "text": …,
# "cache_control": {"type": "ephemeral"}} (clé inconnue de son type conservée) et l'API l'accepte
# sans en-tête bêta depuis la disponibilité générale du cache de prompt. Lecture du cache : 10 % du
# prix d'entrée ; écriture : 125 % ; durée 5 minutes. Longueur minimale d'un préfixe mis en cache :
# 1 024 tokens pour Sonnet 4.6, 4 096 pour Haiku 4.5 (en dessous, rien n'est mis en cache, sans
# erreur). Mistral ignore le marquage (contenu aplati). Coupure : LLM_PROMPT_CACHE=0.
PROMPT_CACHE = os.getenv("LLM_PROMPT_CACHE", "1").strip().lower() not in ("0", "false", "non", "no")


def cached_text_block(text: str) -> dict:
    """Bloc de texte marqué pour le cache de prompt (préfixe stable : consigne, règlement)."""
    blk = {"type": "text", "text": text or ""}
    if PROMPT_CACHE:
        blk["cache_control"] = {"type": "ephemeral"}
    return blk


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
    # Normaliser le motif d'arrêt façon Anthropic : Mistral renvoie "length" sur troncature
    # (max_tokens), Anthropic "max_tokens". Les garde-fous anti-troncature en aval testent
    # UNIQUEMENT "max_tokens" → sans ce mapping, un livrable Mistral coupé passerait pour complet.
    fr = choice.get("finish_reason", "stop")
    stop = "max_tokens" if fr == "length" else fr
    return _Resp(text, _Usage(u.get("prompt_tokens", 0), u.get("completion_tokens", 0)), stop)


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


# ── Limite GLOBALE d'appels IA simultanés (process unique, sans Redis) ─────────
# 4 tâches de fond × 6 sections rédigées en parallèle = jusqu'à 24 appels à la fois, plus les
# requêtes directes : de quoi saturer le fournisseur (429 en cascade, disjoncteur ouvert pour
# tous). Un sémaphore de process borne le nombre d'appels EN VOL ; les suivants attendent leur
# tour (au plus LLM_SLOT_WAIT secondes, puis LLMUnavailable → la tâche échoue et le quota est
# remboursé par le mécanisme existant). Réglable : LLM_MAX_CONCURRENT (défaut prudent : 6).
# Sans interblocage : la place n'est tenue QUE pendant l'appel HTTP au fournisseur (jamais
# pendant qu'un appelant attend d'autres appels), et un appel imbriqué dans le même fil
# (réentrance) ne redemande pas de place.
_MAX_CONCURRENT = max(1, int(os.getenv("LLM_MAX_CONCURRENT", "6")))
_SLOT_WAIT = float(os.getenv("LLM_SLOT_WAIT", "300"))
_SLOTS = threading.BoundedSemaphore(_MAX_CONCURRENT)
_SLOT_LOCAL = threading.local()
_INFLIGHT = {"now": 0, "peak": 0, "waits": 0, "timeouts": 0}


def _in_event_loop() -> bool:
    """Vrai si ce fil fait tourner la boucle asyncio du serveur : y attendre une place figerait
    TOUTES les requêtes (process unique) — on n'y attend jamais."""
    try:
        import asyncio
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


class _llm_slot:
    """Une place parmi LLM_MAX_CONCURRENT, réentrante dans un même fil."""

    def __enter__(self):
        depth = getattr(_SLOT_LOCAL, "depth", 0)
        if depth == 0:
            if not _SLOTS.acquire(blocking=False):
                with _LOCK:
                    _INFLIGHT["waits"] += 1
                # Filet : un appel fait depuis la boucle d'événements (route async qui aurait
                # oublié run_in_threadpool) n'attend pas — il échoue tout de suite, proprement.
                if _in_event_loop():
                    with _LOCK:
                        _INFLIGHT["timeouts"] += 1
                    logger.warning("Appel IA refusé : aucune place libre, et l'appel vient de la boucle d'événements.")
                    raise LLMUnavailable("Service IA très demandé en ce moment. Réessayez dans quelques minutes.")
                if not _SLOTS.acquire(timeout=_SLOT_WAIT):
                    with _LOCK:
                        _INFLIGHT["timeouts"] += 1
                    logger.warning("Appel IA abandonné : aucune place libre après %ss (%s appels en cours).",
                                   _SLOT_WAIT, _INFLIGHT["now"])
                    raise LLMUnavailable("Service IA très demandé en ce moment. Réessayez dans quelques minutes.")
            with _LOCK:
                _INFLIGHT["now"] += 1
                _INFLIGHT["peak"] = max(_INFLIGHT["peak"], _INFLIGHT["now"])
        _SLOT_LOCAL.depth = depth + 1
        return self

    def __exit__(self, *exc):
        _SLOT_LOCAL.depth -= 1
        if _SLOT_LOCAL.depth == 0:
            with _LOCK:
                _INFLIGHT["now"] -= 1
            _SLOTS.release()
        return False


def concurrency_snapshot() -> dict:
    """Appels IA en vol / plafond / pic / attentes — pour /metrics."""
    with _LOCK:
        return dict(_INFLIGHT, max=_MAX_CONCURRENT)


# ── Noms des salariés masqués avant l'IA (doctrine : ils ne partent jamais) ────
# `with pii_scope(pseudonymiseur):` → tout appel passé dans la portée voit ses textes masqués
# (« Yann Tanguy » → « [Chef de chantier 1] ») et sa réponse remise en clair SANS IA. Voir
# app/services/pii.py. Comme tenant_scope, la portée est un contextvar : les fils d'un
# ThreadPoolExecutor ne l'héritent pas → utiliser map_in_context() ci-dessous.
_PII = contextvars.ContextVar("adjugo_pii", default=None)


class pii_scope:
    def __init__(self, pseudonymizer):
        active = pseudonymizer is not None and getattr(pseudonymizer, "active", False)
        self.pz = pseudonymizer if active else None
        self._token = None

    def __enter__(self):
        self._token = _PII.set(self.pz) if self.pz is not None else None
        return self

    def __exit__(self, *exc):
        if self._token is not None:
            _PII.reset(self._token)
        return False


def _mask_request(pz, kwargs: dict) -> dict:
    """Copie de la requête dont tous les textes (consigne + messages) sont masqués ; ajoute à la
    consigne la règle « recopie les étiquettes » dès qu'une étiquette y figure."""
    kw = dict(kwargs)
    kw["messages"] = [dict(m, content=pz.mask_content(m.get("content"))) if isinstance(m, dict) else m
                      for m in (kwargs.get("messages") or [])]
    system = pz.mask_content(kwargs.get("system") or "")
    flat = _flatten_content(system) + " " + " ".join(
        _flatten_content(m.get("content")) for m in kw["messages"] if isinstance(m, dict))
    if pz.uses_labels(flat):
        hint = pz.hint()
        system = (system + "\n\n" + hint) if isinstance(system, str) else (list(system) + [{"type": "text", "text": hint}])
    if system or "system" in kwargs:
        kw["system"] = system
    return kw


def _unmask_response(pz, resp):
    """Remet les noms en clair dans la réponse (simple remplacement, sans IA)."""
    try:
        for b in (getattr(resp, "content", None) or []):
            if isinstance(getattr(b, "text", None), str):
                b.text = pz.unmask(b.text)
        return resp
    except Exception:
        # Objet non modifiable : on ré-emballe (mêmes attributs que ceux lus par les appelants).
        text = pz.unmask("".join(getattr(b, "text", "") or "" for b in (getattr(resp, "content", None) or [])))
        return _Resp(text, getattr(resp, "usage", None) or _Usage(0, 0), getattr(resp, "stop_reason", "end_turn"))


# ── Coût IA d'un traitement complet (journalisé, pour décider plus tard du quota) ─
# `with cost_meter("dossier de réponse", tenant_id):` cumule appels et tokens de tous les appels
# passés dans la portée (fils compris, via map_in_context), puis JOURNALISE le total et une
# estimation en dollars au tarif public du fournisseur. Rien n'est montré au client.
# Tarifs Anthropic (API directe, $ par million de tokens, entrée / sortie), relevés le 12/10/2026.
_PRICES_USD_PER_MTOK = {MODEL: (3.0, 15.0), MODEL_FAST: (1.0, 5.0)}
# Cache de prompt : écriture = 1,25 × le prix d'entrée (5 min), lecture = 0,1 ×.
_CACHE_WRITE_FACTOR, _CACHE_READ_FACTOR = 1.25, 0.10
_METER = contextvars.ContextVar("adjugo_cost_meter", default=None)


class cost_meter:
    def __init__(self, label: str, tenant_id=None, log: bool = True):
        self.label = label
        self.tenant_id = tenant_id
        self.log = log
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        self.truncated = 0
        self.by_model = {}
        self.provider = "anthropic"
        self._parent = None
        self._token = None
        self._t0 = 0.0

    def add(self, model: str, tin: int, tout: int, stop_reason: str = "",
            cache_read: int = 0, cache_write: int = 0) -> None:
        """tin = tokens d'entrée hors cache ; cache_read / cache_write = tokens d'entrée lus dans
        le cache / écrits dans le cache (facturés 0,1 × et 1,25 × le prix d'entrée)."""
        self.calls += 1
        self.input_tokens += tin
        self.output_tokens += tout
        self.cache_read_tokens += cache_read
        self.cache_write_tokens += cache_write
        if stop_reason == "max_tokens":
            self.truncated += 1
        m = self.by_model.setdefault(model or "?", [0, 0, 0, 0, 0])
        m[0] += 1
        m[1] += tin
        m[2] += tout
        m[3] += cache_read
        m[4] += cache_write
        if self._parent is not None:          # un traitement inclus compte aussi dans l'englobant
            self._parent.add(model, tin, tout, stop_reason, cache_read, cache_write)

    def cost_usd(self):
        """Estimation en $ ; None si un modèle n'a pas de tarif connu (ex. Mistral)."""
        if self.provider != "anthropic":
            return None
        total = 0.0
        for model, (_n, tin, tout, cr, cw) in self.by_model.items():
            if model not in _PRICES_USD_PER_MTOK:
                return None
            pin, pout = _PRICES_USD_PER_MTOK[model]
            total += (tin + cr * _CACHE_READ_FACTOR + cw * _CACHE_WRITE_FACTOR) / 1e6 * pin + tout / 1e6 * pout
        return round(total, 5)

    def summary(self) -> dict:
        return {"traitement": self.label, "appels": self.calls, "tokens_entree": self.input_tokens,
                "tokens_sortie": self.output_tokens, "tokens_cache_lus": self.cache_read_tokens,
                "tokens_cache_ecrits": self.cache_write_tokens, "reponses_coupees": self.truncated,
                "cout_estime_usd": self.cost_usd(), "fournisseur": self.provider,
                "par_modele": {k: {"appels": v[0], "tokens_entree": v[1], "tokens_sortie": v[2],
                                   "tokens_cache_lus": v[3], "tokens_cache_ecrits": v[4]}
                               for k, v in self.by_model.items()},
                "duree_s": round(time.monotonic() - self._t0, 1) if self._t0 else None}

    def __enter__(self):
        self._parent = _METER.get()
        self._token = _METER.set(self)
        self._t0 = time.monotonic()
        try:
            self.provider = _resolve_provider()
        except Exception:
            self.provider = "?"
        return self

    def __exit__(self, exc_type, *exc):
        if self._token is not None:
            _METER.reset(self._token)
        if self.log:
            s = self.summary()
            cost = s["cout_estime_usd"]
            logger.info("Coût IA « %s » (espace %s)%s : %d appel(s), %d tokens en entrée (+ %d lus et %d écrits "
                        "dans le cache), %d en sortie, %s, %d réponse(s) coupée(s), %ss — détail %s",
                        self.label, self.tenant_id, " [échec]" if exc_type else "", s["appels"],
                        s["tokens_entree"], s["tokens_cache_lus"], s["tokens_cache_ecrits"], s["tokens_sortie"],
                        (f"environ {cost:.4f} $" if cost is not None else f"coût non estimé ({s['fournisseur']})"),
                        s["reponses_coupees"], s["duree_s"], s["par_modele"])
        return False


def map_in_context(executor, fn, items) -> list:
    """executor.map qui PROPAGE les contextvars du fil appelant (espace facturé, noms masqués,
    compteur de coût) à chaque tâche. Chaque tâche reçoit sa propre copie du contexte, prise
    ici, dans le fil appelant (un même Context ne peut pas être entré par deux fils à la fois)."""
    items = list(items)
    ctxs = [contextvars.copy_context() for _ in items]
    return list(executor.map(lambda pair: pair[0].run(fn, pair[1]), zip(ctxs, items)))


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


def _int_or_zero(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _track_usage(model: str, resp) -> None:
    try:
        u = getattr(resp, "usage", None)
        if not u:
            return
        tin = getattr(u, "input_tokens", 0) or 0
        tout = getattr(u, "output_tokens", 0) or 0
        # Cache de prompt : tokens d'entrée lus / écrits dans le cache, comptés À PART de
        # input_tokens par l'API (champs absents du type Usage du SDK 0.34, lus s'ils sont là).
        cr = _int_or_zero(getattr(u, "cache_read_input_tokens", 0))
        cw = _int_or_zero(getattr(u, "cache_creation_input_tokens", 0))
        used = tin + cr + cw + tout
        TOKENS["input"] += tin + cr + cw
        TOKENS["output"] += tout
        TOKENS["calls"] += 1
        meter = _METER.get()
        if meter is not None:
            meter.add(model, tin, tout, getattr(resp, "stop_reason", "") or "", cr, cw)
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
    pz = _PII.get()
    if pz is not None:
        kwargs = _mask_request(pz, kwargs)      # aucun nom de salarié ne part au fournisseur
    t0 = time.monotonic()
    try:
        # Place limitée tenue pendant le SEUL appel au fournisseur (LLMUnavailable si aucune ne
        # se libère : levée avant d'avoir appelé, elle ne compte pas comme une panne ci-dessous).
        with _llm_slot():
            t0 = time.monotonic()
            if _use_mistral():
                resp = _mistral_create(**kwargs)            # ré-emballé en réponse façon Anthropic
            else:
                resp = client().messages.create(**kwargs)
    except LLMUnavailable:
        raise
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
    if pz is not None:
        resp = _unmask_response(pz, resp)
    return resp


def complete_ex(system: str, user: str, max_tokens: int = 3000, temperature: float = 0.2,
                model: Optional[str] = None) -> tuple:
    """Comme complete() mais renvoie (texte, stop_reason) : permet à l'appelant de détecter
    une réponse TRONQUÉE (stop_reason == "max_tokens") au lieu de la prendre pour complète."""
    resp = messages_create(
        model=model or MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text.strip(), getattr(resp, "stop_reason", "end_turn")


def complete(system: str, user: str, max_tokens: int = 3000, temperature: float = 0.2,
             model: Optional[str] = None) -> str:
    """Appel texte simple. Retourne le texte de la réponse."""
    return complete_ex(system, user, max_tokens=max_tokens, temperature=temperature, model=model)[0]


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
        # Dernier recours : décoder le PREMIER objet équilibré à partir du premier « { »
        # (raw_decode s'arrête à la fin de l'objet), au lieu d'un regex greedy `\{.*\}` qui
        # sur-capture jusqu'à la dernière accolade (et échoue dès qu'il y a du texte après).
        start = text.find("{")
        if start != -1:
            try:
                obj, _ = json.JSONDecoder().raw_decode(text[start:])
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass
    raise ValueError(f"Réponse LLM non JSON: {raw[:200]}")
