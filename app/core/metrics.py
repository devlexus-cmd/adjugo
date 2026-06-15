"""
Observabilité — métriques opérationnelles au format Prometheus, SANS dépendance.

Exposées via GET /metrics (protégé par un jeton si METRICS_TOKEN ou CRON_SECRET est
défini). On n'expose QUE des agrégats opérationnels — aucune donnée tenant identifiable.
Scrapables par Prometheus / Datadog / Grafana Agent sans rien installer côté app.

C'est le levier que l'audit a désigné comme bloquant partagé d'Architecture et de
Solidité : passer des compteurs en mémoire à des métriques exportables.
"""
import time

_START = time.monotonic()


def uptime_seconds() -> float:
    return time.monotonic() - _START


def _fmt(name: str, value, labels: dict = None) -> str:
    if labels:
        lbl = ",".join(f'{k}="{v}"' for k, v in labels.items())
        return f"{name}{{{lbl}}} {value}"
    return f"{name} {value}"


def render() -> str:
    """Rend l'exposition Prometheus (texte). Robuste : une sous-section qui échoue
    n'empêche pas les autres de sortir."""
    out = [
        "# HELP adjugo_uptime_seconds Temps écoulé depuis le démarrage du process.",
        "# TYPE adjugo_uptime_seconds gauge",
        _fmt("adjugo_uptime_seconds", f"{uptime_seconds():.0f}"),
    ]

    # ── LLM : tokens, appels, disjoncteur, tenants suivis ────────────────────
    try:
        from app.services import llm
        now = time.monotonic()
        out += [
            "# TYPE adjugo_llm_tokens_total counter",
            _fmt("adjugo_llm_tokens_total", llm.TOKENS["input"], {"direction": "input"}),
            _fmt("adjugo_llm_tokens_total", llm.TOKENS["output"], {"direction": "output"}),
            "# TYPE adjugo_llm_calls_total counter",
            _fmt("adjugo_llm_calls_total", llm.TOKENS["calls"]),
            "# HELP adjugo_llm_circuit_open Disjoncteur IA ouvert (1) ou fermé (0).",
            "# TYPE adjugo_llm_circuit_open gauge",
            _fmt("adjugo_llm_circuit_open", 1 if llm._CB["open_until"] > now else 0),
            "# TYPE adjugo_llm_consecutive_failures gauge",
            _fmt("adjugo_llm_consecutive_failures", llm._CB["fails"]),
            "# HELP adjugo_llm_tracked_tenants Nombre de tenants avec consommation IA suivie.",
            "# TYPE adjugo_llm_tracked_tenants gauge",
            _fmt("adjugo_llm_tracked_tenants", len(llm._TENANT_TOKENS)),
        ]
        # Histogramme de latence des appels IA (→ p50/p95/p99 via histogram_quantile).
        lat = llm.latency_snapshot()
        out += ["# HELP adjugo_llm_call_duration_seconds Durée des appels Claude réussis.",
                "# TYPE adjugo_llm_call_duration_seconds histogram"]
        cumulative = lat["buckets"]
        for b in sorted(cumulative):
            out.append(_fmt("adjugo_llm_call_duration_seconds_bucket", cumulative[b], {"le": str(b)}))
        out += [
            _fmt("adjugo_llm_call_duration_seconds_bucket", lat["count"], {"le": "+Inf"}),
            _fmt("adjugo_llm_call_duration_seconds_sum", round(lat["sum"], 3)),
            _fmt("adjugo_llm_call_duration_seconds_count", lat["count"]),
        ]
    except Exception:
        pass

    # ── RAG : taille du cache d'index ────────────────────────────────────────
    try:
        from app.services import rag
        out += [
            "# HELP adjugo_rag_cache_tenants Tenants avec index RAG en cache mémoire.",
            "# TYPE adjugo_rag_cache_tenants gauge",
            _fmt("adjugo_rag_cache_tenants", len(rag._IDX_CACHE)),
        ]
    except Exception:
        pass

    # ── Jobs par statut (agrégat) ────────────────────────────────────────────
    try:
        from app.core.database import SessionLocal
        from app.models import Job
        from sqlalchemy import func
        db = SessionLocal()
        try:
            rows = db.query(Job.status, func.count(Job.id)).group_by(Job.status).all()
        finally:
            db.close()
        out.append("# HELP adjugo_jobs Nombre de jobs par statut.")
        out.append("# TYPE adjugo_jobs gauge")
        for status, n in rows:
            out.append(_fmt("adjugo_jobs", n, {"status": str(status)}))
    except Exception:
        pass

    # ── Configuration (rate-limit partagé ?) ─────────────────────────────────
    try:
        from app.core.config import get_settings
        s = get_settings()
        shared = 1 if s.RATELIMIT_STORAGE_URI.startswith(("redis://", "rediss://")) else 0
        out += [
            "# HELP adjugo_ratelimit_shared Store de rate-limit partagé (1=redis, 0=mémoire).",
            "# TYPE adjugo_ratelimit_shared gauge",
            _fmt("adjugo_ratelimit_shared", shared),
            "# HELP adjugo_build_info Métadonnées de build.",
            "# TYPE adjugo_build_info gauge",
            _fmt("adjugo_build_info", 1, {"version": s.APP_VERSION}),
        ]
    except Exception:
        pass

    return "\n".join(out) + "\n"


def readiness() -> dict:
    """État de préparation détaillé (pour /api/health/ready) : sous-systèmes + verdict.
    `ready` est False uniquement si un sous-système CRITIQUE (la base) est en panne ;
    le disjoncteur ouvert est signalé mais ne rend pas l'instance « not ready »
    (l'API reste utile : auth, lecture, etc.)."""
    import time as _t
    detail = {"db": "unknown", "llm_circuit": "closed", "jobs_pending": None}
    ready = True

    from app.core.database import SessionLocal
    from sqlalchemy import text as _sqltext
    db = SessionLocal()
    try:
        db.execute(_sqltext("SELECT 1"))
        detail["db"] = "ok"
    except Exception:
        detail["db"] = "unreachable"
        ready = False
    finally:
        db.close()

    try:
        from app.services import llm
        detail["llm_circuit"] = "open" if llm._CB["open_until"] > _t.monotonic() else "closed"
    except Exception:
        pass

    try:
        from app.core.database import SessionLocal as _SL
        from app.models import Job
        d2 = _SL()
        try:
            detail["jobs_pending"] = d2.query(Job).filter(Job.status.in_(["pending", "running"])).count()
        finally:
            d2.close()
    except Exception:
        pass

    return {"ready": ready, "uptime_s": round(uptime_seconds()), **detail}
