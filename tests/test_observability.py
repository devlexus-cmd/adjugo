"""
Observabilité : /metrics (Prometheus) et /api/health/ready (readiness détaillée).
Prouve l'exposition des métriques opérationnelles et la protection par jeton.
"""


def test_readiness_detaillee(client):
    r = client.get("/api/health/ready")
    assert r.status_code == 200
    j = r.json()
    assert j["ready"] is True
    assert j["db"] == "ok"
    assert j["llm_circuit"] in ("open", "closed")
    assert "jobs_pending" in j


def test_metrics_exposition_prometheus(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    # Métriques clés présentes, au format Prometheus.
    for m in ("adjugo_uptime_seconds", "adjugo_llm_calls_total",
              "adjugo_llm_circuit_open", "adjugo_jobs", "adjugo_ratelimit_shared"):
        assert m in body, f"métrique manquante : {m}"
    assert "# TYPE adjugo_uptime_seconds gauge" in body


def test_metrics_protege_par_jeton(client, monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "secret-metrics")
    assert client.get("/metrics").status_code == 401                       # sans jeton
    assert client.get("/metrics?token=mauvais").status_code == 401          # mauvais jeton
    ok = client.get("/metrics", headers={"Authorization": "Bearer secret-metrics"})
    assert ok.status_code == 200                                           # bon jeton
    assert client.get("/metrics?token=secret-metrics").status_code == 200   # via query param
