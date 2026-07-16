from sqlalchemy import select

from app.extensions import db
from app.models import AuditLog


def test_login_returns_user_scoped_to_tenant(client):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "tenant": "gabinete-a",
            "email": "admin@teste.local",
            "password": "SenhaForte123!",
        },
    )

    assert response.status_code == 200
    assert response.json["user"]["tenant"]["slug"] == "gabinete-a"
    assert "access_token_cookie=" in response.headers.getlist("Set-Cookie")[0]


def test_login_does_not_authenticate_same_email_from_another_tenant(client):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "tenant": "gabinete-b",
            "email": "admin@teste.local",
            "password": "SenhaForte123!",
        },
    )

    assert response.status_code == 401
    assert response.json["error"] == "invalid_credentials"


def test_login_creates_audit_record(app, client):
    client.post(
        "/api/v1/auth/login",
        json={
            "tenant": "gabinete-a",
            "email": "admin@teste.local",
            "password": "SenhaForte123!",
        },
    )

    with app.app_context():
        audit = db.session.execute(
            select(AuditLog).where(AuditLog.action == "auth.login")
        ).scalar_one()
        assert audit.tenant_id is not None
        assert audit.user_id is not None


def test_protected_endpoint_rejects_anonymous_access(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
