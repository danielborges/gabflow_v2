from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.auth.security import hash_password
from app.electoral.service import sync_active_mandate
from app.extensions import db
from app.models import (
    AgendaEvent,
    AgendaEventStatus,
    AgendaEventType,
    AuditLog,
    ElectoralMandateSnapshot,
    ElectoralModuleSettings,
    OversightAction,
    OversightActionStatus,
    RequestSource,
    RequestStatus,
    Role,
    ServiceRequest,
    Tenant,
    Territory,
    User,
)
from app.modules import DEFAULT_MODULES

PASSWORD = "SenhaForte123!"  # noqa: S105


def _prepare(app):
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        tenant.plan = "premium"
        tenant.enabled_modules = [*DEFAULT_MODULES, "inteligencia_eleitoral"]
        tenant.jurisdiction_name = "Juiz de Fora/MG"
        user = User(
            tenant_id=tenant.id,
            name="Parlamentar ICT",
            email="parlamentar-ict@teste.local",
            password_hash=hash_password(PASSWORD),
            role=Role.REPRESENTATIVE,
        )
        db.session.add(user)
        db.session.flush()
        mandate = sync_active_mandate(tenant)
        db.session.add(ElectoralModuleSettings(
            tenant_id=tenant.id,
            privacy_threshold=10,
            feature_flags={"camadasMandato": True},
            updated_by_id=user.id,
        ))
        territory_a = Territory(tenant_id=tenant.id, name="Centro")
        territory_b = Territory(tenant_id=tenant.id, name="Norte")
        db.session.add_all([territory_a, territory_b])
        db.session.flush()
        created_at = datetime(2026, 1, 10, 12, tzinfo=UTC)
        requests = []
        for index in range(12):
            resolved = index < 6
            item = ServiceRequest(
                tenant_id=tenant.id,
                protocol=f"ICT-{index:03d}",
                source=RequestSource.EMAIL,
                description="Demanda usada somente em teste agregado.",
                status=RequestStatus.RESOLVIDA if resolved else RequestStatus.EM_ATENDIMENTO,
                category="Infraestrutura" if index < 10 else "Saúde",
                territory_id=territory_a.id if index < 10 else territory_b.id,
                due_at=created_at + timedelta(days=5),
                closed_at=created_at + timedelta(days=2) if resolved else None,
                closing_evidence="Protocolo de entrega" if resolved else None,
                created_by_id=user.id,
                created_at=created_at,
                updated_at=created_at,
            )
            requests.append(item)
        db.session.add_all(requests)
        db.session.flush()
        db.session.add(AgendaEvent(
            tenant_id=tenant.id,
            event_type=AgendaEventType.VISITA,
            status=AgendaEventStatus.REALIZADO,
            title="Visita territorial",
            starts_at=created_at + timedelta(days=1),
            territory_id=territory_a.id,
            created_by_id=user.id,
            created_at=created_at,
            updated_at=created_at,
        ))
        db.session.add(OversightAction(
            tenant_id=tenant.id,
            status=OversightActionStatus.CONCLUIDA,
            title="Fiscalização territorial",
            occurred_at=created_at + timedelta(days=2),
            request_id=requests[0].id,
            created_by_id=user.id,
            created_at=created_at,
            updated_at=created_at,
        ))
        db.session.commit()
        return tenant.id, user.id, mandate.id, territory_a.id, territory_b.id


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "parlamentar-ict@teste.local", "password": PASSWORD},
    )
    assert response.status_code == 200
    return client.get_cookie("csrf_access_token").value


def test_snapshot_integrates_mandate_data_and_enforces_privacy(app, client):
    _, user_id, _, territory_a_id, territory_b_id = _prepare(app)
    csrf = _login(client)

    response = client.post(
        "/api/v1/electoral/mandate-snapshots",
        headers={"X-CSRF-TOKEN": csrf},
        json={"period_start": "2026-01-01", "period_end": "2026-01-31"},
    )

    assert response.status_code == 201
    assert response.json["payload"]["formula"]["electoral_performance_used"] is False
    assert response.json["electoral_context"]["available"] is False
    mandate = response.json["payload"]["territories"][0]
    assert mandate["demand_count"] == 12
    assert mandate["metrics"]["resolved"] == 6
    assert mandate["metrics"]["agenda_realized"] == 1
    assert mandate["metrics"]["oversight_completed"] == 1
    assert mandate["metrics"]["deliveries_with_evidence"] == 6
    by_id = {item["territory_id"]: item for item in response.json["payload"]["territories"][1:]}
    assert by_id[str(territory_a_id)]["suppressed"] is False
    assert by_id[str(territory_b_id)]["suppressed"] is True
    assert by_id[str(territory_b_id)]["metrics"] is None
    assert by_id[str(territory_b_id)]["demand_count"] is None

    with app.app_context():
        snapshot = db.session.execute(select(ElectoralMandateSnapshot)).scalar_one()
        assert snapshot.config_hash == response.json["config_hash"]
        audit = db.session.execute(
            select(AuditLog).where(AuditLog.action == "electoral.mandate_snapshot.created")
        ).scalar_one()
        assert audit.user_id == user_id


def test_coverage_profile_is_versioned_and_requires_explanation(app, client):
    _prepare(app)
    csrf = _login(client)
    first = client.get("/api/v1/electoral/coverage-profile")
    assert first.status_code == 200
    assert first.json["version"] == 1

    invalid = client.post(
        "/api/v1/electoral/coverage-profile",
        headers={"X-CSRF-TOKEN": csrf},
        json={"explanation": "curta"},
    )
    assert invalid.status_code == 422

    created = client.post(
        "/api/v1/electoral/coverage-profile",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "weights": {
                "resolution": 0.4,
                "sla": 0.2,
                "agenda": 0.1,
                "actions": 0.15,
                "deliveries": 0.15,
            },
            "targets": {"agenda": 3, "actions": 2, "deliveries": 2},
            "sensitive_categories": ["saúde", "religião"],
            "explanation": "Pesos revisados para o ciclo trimestral do mandato.",
        },
    )
    assert created.status_code == 201
    assert created.json["version"] == 2
    assert created.json["weights"]["resolution"] == 0.4
