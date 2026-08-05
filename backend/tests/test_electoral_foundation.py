from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.auth.security import hash_password
from app.electoral.service import sync_active_mandate
from app.extensions import db
from app.models import (
    AuditLog,
    ElectoralAccessDelegation,
    ElectoralModuleSettings,
    Mandate,
    Role,
    Tenant,
    User,
)
from app.modules import DEFAULT_MODULES

PASSWORD = "SenhaForte123!"  # noqa: S105
ELECTORAL_MODULE = "inteligencia_eleitoral"


def _prepare_representative(app, *, enable_module=True, plan="premium") -> tuple:
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        tenant.plan = plan
        tenant.enabled_modules = (
            [*DEFAULT_MODULES, ELECTORAL_MODULE] if enable_module else DEFAULT_MODULES
        )
        tenant.chamber_type = "CAMARA_MUNICIPAL"
        tenant.jurisdiction_name = "Juiz de Fora/MG"
        representative = User(
            tenant_id=tenant.id,
            name="Parlamentar Titular",
            email="parlamentar-eleitoral@teste.local",
            password_hash=hash_password(PASSWORD),
            role=Role.REPRESENTATIVE,
        )
        db.session.add(representative)
        db.session.flush()
        mandate = sync_active_mandate(tenant)
        db.session.commit()
        return representative.id, mandate.id


def _login(client, email):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response


def _csrf(client):
    return client.get_cookie("csrf_access_token").value


def test_electoral_module_is_not_enabled_by_default():
    assert ELECTORAL_MODULE not in DEFAULT_MODULES


def test_creating_representative_synchronizes_active_mandate(app, client):
    _login(client, "admin@teste.local")

    response = client.post(
        "/api/v1/admin/usuarios",
        headers={"X-CSRF-TOKEN": _csrf(client)},
        json={
            "nome": "Parlamentar Sincronizada",
            "email": "parlamentar-sync@teste.local",
            "cpf": "222.333.444-05",
            "senha": PASSWORD,
            "perfil": "representative",
        },
    )

    assert response.status_code == 201
    with app.app_context():
        mandate = db.session.execute(select(Mandate)).scalar_one()
        assert str(mandate.representative_user_id) == response.json["id"]
        assert mandate.status.value == "active"


def test_representative_with_active_mandate_accesses_foundation(app, client):
    representative_id, mandate_id = _prepare_representative(app)
    login = _login(client, "parlamentar-eleitoral@teste.local")

    assert ELECTORAL_MODULE in login.json["user"]["tenant"]["modulosHabilitados"]
    response = client.get("/api/v1/electoral/disponibilidade")

    assert response.status_code == 200
    assert response.json["disponivel"] is True
    assert response.json["mandato"]["id"] == str(mandate_id)
    assert response.json["mandato"]["status"] == "active"
    assert response.json["limiarPrivacidade"] == 10
    assert response.json["funcionalidades"]["catalogo"] is True
    assert response.json["funcionalidades"]["ia"] is True
    assert "delegar_acesso" in response.json["capacidades"]
    with app.app_context():
        audit = db.session.execute(
            select(AuditLog).where(
                AuditLog.user_id == representative_id,
                AuditLog.action == "electoral.access.granted",
            )
        ).scalar_one()
        assert audit.after == {"capability": "consultar_dados_publicos"}


def test_electoral_module_requires_tenant_enablement(app, client):
    _prepare_representative(app, enable_module=False)
    _login(client, "parlamentar-eleitoral@teste.local")

    response = client.get("/api/v1/electoral/disponibilidade")

    assert response.status_code == 403
    assert response.json["error"] == "module_disabled"


def test_electoral_ai_cannot_be_disabled_by_legacy_tenant_setting(app, client):
    _prepare_representative(app)
    with app.app_context():
        tenant = db.session.execute(
            select(Tenant).where(Tenant.slug == "gabinete-a")
        ).scalar_one()
        db.session.add(
            ElectoralModuleSettings(
                tenant_id=tenant.id,
                feature_flags={"catalogo": True, "ia": False},
            )
        )
        db.session.commit()
    _login(client, "parlamentar-eleitoral@teste.local")

    availability = client.get("/api/v1/electoral/disponibilidade")
    insights = client.get("/api/v1/electoral/insights")

    assert availability.status_code == 200
    assert availability.json["funcionalidades"]["ia"] is True
    assert insights.status_code == 200


def test_electoral_module_requires_plan_entitlement(app, client):
    _prepare_representative(app, plan="starter")
    login = _login(client, "parlamentar-eleitoral@teste.local")

    assert ELECTORAL_MODULE not in login.json["user"]["tenant"]["modulosHabilitados"]
    response = client.get("/api/v1/electoral/disponibilidade")

    assert response.status_code == 403
    assert response.json["error"] == "module_not_in_plan"


def test_tenant_admin_has_no_implicit_electoral_access(app, client):
    _prepare_representative(app)
    _login(client, "admin@teste.local")

    response = client.get("/api/v1/electoral/disponibilidade")

    assert response.status_code == 403
    assert response.json["error"] == "capability_required"
    with app.app_context():
        audit = db.session.execute(
            select(AuditLog).where(AuditLog.action == "electoral.access.denied")
        ).scalar_one()
        assert audit.after["reason"] == "capability_required"


def test_temporary_delegation_grants_only_explicit_capability(app, client):
    representative_id, mandate_id = _prepare_representative(app)
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        staff = User(
            tenant_id=tenant.id,
            name="Assessora Delegada",
            email="assessora-eleitoral@teste.local",
            password_hash=hash_password(PASSWORD),
            role=Role.STAFF,
        )
        db.session.add(staff)
        db.session.flush()
        db.session.add(
            ElectoralAccessDelegation(
                tenant_id=tenant.id,
                mandate_id=mandate_id,
                grantor_user_id=representative_id,
                grantee_user_id=staff.id,
                capabilities=["consultar_dados_publicos"],
                reason="Preparar comparativo interno",
                valid_from=datetime.now(UTC) - timedelta(minutes=1),
                valid_until=datetime.now(UTC) + timedelta(days=7),
            )
        )
        db.session.commit()

    _login(client, "assessora-eleitoral@teste.local")
    response = client.get("/api/v1/electoral/disponibilidade")

    assert response.status_code == 200
    assert response.json["capacidades"] == ["consultar_dados_publicos"]


def test_active_mandate_is_required_even_for_representative(app, client):
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        tenant.plan = "premium"
        tenant.enabled_modules = [*DEFAULT_MODULES, ELECTORAL_MODULE]
        db.session.add(
            User(
                tenant_id=tenant.id,
                name="Parlamentar sem mandato",
                email="sem-mandato@teste.local",
                password_hash=hash_password(PASSWORD),
                role=Role.REPRESENTATIVE,
            )
        )
        db.session.commit()

    _login(client, "sem-mandato@teste.local")
    response = client.get("/api/v1/electoral/disponibilidade")

    assert response.status_code == 403
    assert response.json["error"] == "active_mandate_required"
    with app.app_context():
        assert db.session.scalar(select(Mandate.id)) is None


def test_representative_grants_and_revokes_granular_delegation(app, client):
    _prepare_representative(app)
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        staff = User(
            tenant_id=tenant.id,
            name="Assessora para delegacao",
            email="assessora-api@teste.local",
            password_hash=hash_password(PASSWORD),
            role=Role.STAFF,
        )
        db.session.add(staff)
        db.session.flush()
        staff_id = staff.id
        db.session.add(
            ElectoralModuleSettings(
                tenant_id=tenant.id,
                feature_flags={"catalogo": True, "exportacoes": True, "delegacao": True},
            )
        )
        db.session.commit()

    _login(client, "parlamentar-eleitoral@teste.local")
    created = client.post(
        "/api/v1/electoral/delegations",
        headers={"X-CSRF-TOKEN": _csrf(client)},
        json={
            "grantee_user_id": str(staff_id),
            "capabilities": ["consultar_dados_publicos"],
            "valid_days": 7,
            "reason": "Preparar analises publicas para revisao parlamentar",
        },
    )
    assert created.status_code == 201
    assert created.json["active"] is True

    staff_client = app.test_client()
    _login(staff_client, "assessora-api@teste.local")
    assert staff_client.get("/api/v1/electoral/disponibilidade").status_code == 200
    denied_export = staff_client.get("/api/v1/electoral/report-jobs")
    assert denied_export.status_code == 403
    assert denied_export.json["error"] == "capability_required"

    revoked = client.delete(
        f"/api/v1/electoral/delegations/{created.json['id']}",
        headers={"X-CSRF-TOKEN": _csrf(client)},
    )
    assert revoked.status_code == 204
    assert staff_client.get("/api/v1/electoral/disponibilidade").status_code == 403
    with app.app_context():
        actions = set(db.session.scalars(select(AuditLog.action)))
        assert "electoral.delegation.granted" in actions
        assert "electoral.delegation.revoked" in actions
