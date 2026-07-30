def test_health_has_security_and_correlation_headers(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json["status"] == "ok"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Request-ID"]


def test_ready_checks_database(client):
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json["database"] == "up"


def test_rag_health_and_prometheus_metrics_require_monitoring_token(client):
    assert client.get("/api/v1/health/rag").status_code == 401
    headers = {"Authorization": "Bearer test-metrics-token"}
    health = client.get("/api/v1/health/rag", headers=headers)
    assert health.status_code == 200
    assert health.json["status"] == "ok"
    assert health.json["queue"]["pending"] == 0

    metrics = client.get("/api/v1/metrics", headers=headers)
    assert metrics.status_code == 200
    assert "gabflow_rag_outbox_pending 0" in metrics.text
    assert metrics.content_type.startswith("text/plain")
