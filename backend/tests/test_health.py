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
