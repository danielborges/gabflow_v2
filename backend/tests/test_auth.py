from sqlalchemy import select

from app.auth.security import hash_password
from app.extensions import db
from app.models import AuditLog, Role, User


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


def test_platform_admin_login_does_not_require_tenant(app, client):
    with app.app_context():
        db.session.add(
            User(
                tenant_id=None,
                name="Administrador Geral",
                email="platform@teste.local",
                password_hash=hash_password("SenhaForte123!"),
                role=Role.PLATFORM_ADMIN,
            )
        )
        db.session.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "platform@teste.local", "password": "SenhaForte123!"},
    )

    assert response.status_code == 200
    assert response.json["user"]["role"] == "platform_admin"
    assert response.json["user"]["tenant"] is None


def test_protected_endpoint_rejects_anonymous_access(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
