from sqlalchemy import select

from app.auth.security import hash_password
from app.extensions import db
from app.models import (
    ContractStatus,
    PlatformContractEvent,
    RequestSource,
    Role,
    ServiceRequest,
    Tenant,
    User,
)

PASSWORD = "SenhaForte123!"  # noqa: S105


def _csrf_from_cookie(client):
    return client.get_cookie("csrf_access_token").value


def _login_platform(app, client):
    with app.app_context():
        db.session.add(
            User(
                tenant_id=None,
                name="Administrador Geral",
                email="platform@teste.local",
                password_hash=hash_password(PASSWORD),
                role=Role.PLATFORM_ADMIN,
            )
        )
        db.session.commit()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "platform@teste.local", "password": PASSWORD},
    )
    assert response.status_code == 200
    return _csrf_from_cookie(client)


def _login_tenant_admin(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"tenant": "gabinete-a", "email": "admin@teste.local", "password": PASSWORD},
    )
    assert response.status_code == 200
    return _csrf_from_cookie(client)


def test_tenant_admin_cannot_access_platform_admin(client):
    _login_tenant_admin(client)

    response = client.get("/api/v1/platform/overview")

    assert response.status_code == 403


def test_platform_admin_creates_and_updates_tenant(app, client):
    csrf = _login_platform(app, client)

    created = client.post(
        "/api/v1/platform/gabinetes",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "nome": "Gabinete Plataforma",
            "slug": "gabinete-plataforma",
            "plano": "professional",
            "limiteUsuarios": 12,
            "limiteArmazenamentoMb": 4096,
            "modulosHabilitados": ["solicitacoes", "canais", "privacidade"],
        },
    )

    assert created.status_code == 201
    assert created.json["slug"] == "gabinete-plataforma"
    assert created.json["plano"] == "professional"
    assert created.json["limiteUsuarios"] == 12

    missing_reason = client.patch(
        f"/api/v1/platform/gabinetes/{created.json['id']}",
        headers={"X-CSRF-TOKEN": csrf},
        json={"contrato": "suspended", "limiteUsuarios": 20},
    )
    assert missing_reason.status_code == 422

    updated = client.post(
        f"/api/v1/platform/gabinetes/{created.json['id']}/contrato",
        headers={"X-CSRF-TOKEN": csrf},
        json={"contrato": "suspended", "motivo": "Inadimplencia formalizada"},
    )

    assert updated.status_code == 200
    assert updated.json["tenant"]["contrato"] == "suspended"
    assert updated.json["tenant"]["status"] == "suspended"
    assert updated.json["evento"]["motivo"] == "Inadimplencia formalizada"

    with app.app_context():
        event = db.session.execute(select(PlatformContractEvent)).scalar_one()
        assert event.new_status == ContractStatus.SUSPENDED


def test_platform_usage_is_aggregated_without_internal_content(app, client):
    csrf = _login_platform(app, client)
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        admin = db.session.execute(
            select(User).where(User.tenant_id == tenant.id, User.email == "admin@teste.local")
        ).scalar_one()
        db.session.add(
            ServiceRequest(
                tenant_id=tenant.id,
                protocol="GF-TEST-001",
                source=RequestSource.PRESENCIAL,
                title="Conteudo privado nao deve aparecer",
                description="Detalhe interno sensivel",
                created_by_id=admin.id,
            )
        )
        db.session.commit()
        tenant_id = str(tenant.id)

    usage = client.get(f"/api/v1/platform/gabinetes/{tenant_id}/consumo")
    overview = client.get("/api/v1/platform/overview")

    assert usage.status_code == 200
    assert usage.json["consumo"]["solicitacoes"] == 1
    assert "Conteudo privado" not in usage.get_data(as_text=True)
    assert "Detalhe interno" not in overview.get_data(as_text=True)

    support = client.post(
        "/api/v1/platform/suporte",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "tenantId": tenant_id,
            "solicitadoPor": "Admin do gabinete",
            "autorizadoPor": "Chefia",
            "motivo": "Chamado formal de suporte",
            "escopo": "Validar configuracao de webhook",
        },
    )

    assert support.status_code == 201
    assert support.json["escopo"] == "Validar configuracao de webhook"


def test_disabled_module_blocks_tenant_endpoint(app, client):
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        tenant.enabled_modules = ["solicitacoes"]
        db.session.commit()

    _login_tenant_admin(client)

    allowed = client.get("/api/v1/solicitacoes")
    blocked = client.get("/api/v1/agenda/compromissos")

    assert allowed.status_code == 200
    assert blocked.status_code == 403
    assert blocked.json["error"] == "module_disabled"
    assert blocked.json["module"] == "agenda"


def test_contract_suspension_blocks_login(app, client):
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        tenant.contract_status = ContractStatus.SUSPENDED
        db.session.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={"tenant": "gabinete-a", "email": "admin@teste.local", "password": PASSWORD},
    )

    assert response.status_code == 401
