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


def test_public_commitment_has_immutable_history_evidence_and_official_map(app, client):
    tenant_id, user_id, _, territory_id, _ = _prepare(app)
    with app.app_context():
        tenant = db.session.get(Tenant, tenant_id)
        tenant.jurisdiction_ibge_code = "3136702"
        tenant.jurisdiction_geojson = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {"codarea": "3136702"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-43.4, -21.8],
                        [-43.3, -21.8],
                        [-43.3, -21.7],
                        [-43.4, -21.8],
                    ]],
                },
            }],
        }
        db.session.commit()
    csrf = _login(client)

    created = client.post(
        "/api/v1/electoral/public-commitments",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "title": "Requalificar praça pública",
            "description": "Acompanhar a entrega e publicar a comprovação.",
            "territory_id": str(territory_id),
            "responsible_user_id": str(user_id),
            "due_on": "2026-12-20",
            "public_location_name": "Praça Central",
            "latitude": -21.7619,
            "longitude": -43.3496,
            "location_is_public": True,
        },
    )
    assert created.status_code == 201
    commitment_id = created.json["id"]
    assert created.json["status"] == "PLANNED"
    assert created.json["history"][0]["action"] == "CREATED"

    updated = client.patch(
        f"/api/v1/electoral/public-commitments/{commitment_id}",
        headers={"X-CSRF-TOKEN": csrf},
        json={"status": "IN_PROGRESS", "progress": 45},
    )
    assert updated.status_code == 200
    assert updated.json["progress"] == 45

    evidenced = client.post(
        f"/api/v1/electoral/public-commitments/{commitment_id}/evidence",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "title": "Relatório público de execução",
            "public_url": "https://example.gov.br/evidencias/praca-central",
            "evidence_date": "2026-08-04",
        },
    )
    assert evidenced.status_code == 201
    assert len(evidenced.json["evidence"]) == 1
    assert [entry["action"] for entry in evidenced.json["history"]] == [
        "EVIDENCE_ADDED",
        "UPDATED",
        "CREATED",
    ]

    map_response = client.get("/api/v1/electoral/operational-map")
    assert map_response.status_code == 200
    assert map_response.json["geometry_available"] is True
    assert map_response.json["source"]["official"] is True
    assert map_response.json["features"][0]["id"] == commitment_id
    assert "nenhum polígono" in map_response.json["warnings"][0]

    snapshot = client.post(
        "/api/v1/electoral/mandate-snapshots",
        headers={"X-CSRF-TOKEN": csrf},
        json={"period_start": "2026-08-01", "period_end": "2026-08-31"},
    )
    assert snapshot.status_code == 201
    mandate_row = snapshot.json["payload"]["territories"][0]
    assert mandate_row["suppressed"] is True
    assert mandate_row["public_commitments"]["total"] == 1


def test_commitment_map_rejects_unconfirmed_private_location(app, client):
    _, user_id, _, territory_id, _ = _prepare(app)
    csrf = _login(client)
    response = client.post(
        "/api/v1/electoral/public-commitments",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "title": "Compromisso com ponto inválido",
            "description": "O mapa não deve aceitar endereço residencial.",
            "territory_id": str(territory_id),
            "responsible_user_id": str(user_id),
            "due_on": "2026-12-20",
            "public_location_name": "Endereço não confirmado",
            "latitude": -21.7619,
            "longitude": -43.3496,
            "location_is_public": False,
        },
    )
    assert response.status_code == 422
    assert "local público" in response.json["message"]
