import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.auth.security import hash_password
from app.electoral.advanced_features import dispatch_due_report_schedules
from app.electoral.service import sync_active_mandate
from app.extensions import db
from app.models import (
    AgendaEvent,
    AgendaEventStatus,
    AgendaEventType,
    AuditLog,
    ElectoralAlertDelivery,
    ElectoralCandidacy,
    ElectoralCandidate,
    ElectoralDatasetStatus,
    ElectoralDatasetVersion,
    ElectoralElection,
    ElectoralMandateSnapshot,
    ElectoralModuleSettings,
    ElectoralOffice,
    ElectoralParty,
    ElectoralPublicCommitment,
    ElectoralReportJob,
    ElectoralReportSchedule,
    ElectoralResult,
    ElectoralTerritory,
    ElectoralTerritoryLevel,
    ElectoralUserCandidacy,
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
        db.session.add(
            ElectoralModuleSettings(
                tenant_id=tenant.id,
                privacy_threshold=10,
                feature_flags={"camadasMandato": True, "exportacoes": True},
                updated_by_id=user.id,
            )
        )
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
        db.session.add(
            AgendaEvent(
                tenant_id=tenant.id,
                event_type=AgendaEventType.VISITA,
                status=AgendaEventStatus.REALIZADO,
                title="Visita territorial",
                starts_at=created_at + timedelta(days=1),
                territory_id=territory_a.id,
                created_by_id=user.id,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        db.session.add(
            OversightAction(
                tenant_id=tenant.id,
                status=OversightActionStatus.CONCLUIDA,
                title="Fiscalização territorial",
                occurred_at=created_at + timedelta(days=2),
                request_id=requests[0].id,
                created_by_id=user.id,
                created_at=created_at,
                updated_at=created_at,
            )
        )
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


def test_overlay_briefing_and_user_alert_preferences_are_auditable(app, client):
    _, user_id, _, territory_id, suppressed_territory_id = _prepare(app)
    csrf = _login(client)
    snapshot = client.post(
        "/api/v1/electoral/mandate-snapshots",
        headers={"X-CSRF-TOKEN": csrf},
        json={"period_start": "2026-01-01", "period_end": "2026-01-31"},
    )
    assert snapshot.status_code == 201
    snapshot_id = snapshot.json["id"]

    overlay = client.get(
        f"/api/v1/electoral/territories/{territory_id}/mandate-overlay?snapshot_id={snapshot_id}"
    )
    assert overlay.status_code == 200
    assert overlay.json["territory"]["demand_count"] == 10
    assert overlay.json["linkage"]["electoral_overlay_available"] is False

    briefing = client.get(
        f"/api/v1/electoral/territories/{territory_id}/briefing?snapshot_id={snapshot_id}"
    )
    assert briefing.status_code == 200
    assert briefing.json["draft"] is True
    assert briefing.json["review_required"] is True
    assert briefing.json["facts"]
    assert "não usa desempenho eleitoral" in briefing.json["methodology_notice"].lower()

    suppressed = client.get(
        f"/api/v1/electoral/territories/{suppressed_territory_id}/briefing"
        f"?snapshot_id={snapshot_id}"
    )
    assert suppressed.status_code == 200
    assert suppressed.json["privacy"]["suppressed"] is True
    assert suppressed.json["facts"] == []

    preference = client.put(
        "/api/v1/electoral/alert-preferences",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "enabled": True,
            "channels": ["IN_APP", "EMAIL"],
            "frequency": "WEEKLY",
            "alert_types": ["SLA_OVERDUE", "COMMITMENT_OVERDUE"],
        },
    )
    assert preference.status_code == 200
    assert preference.json["channels"] == ["IN_APP", "EMAIL"]
    assert preference.json["frequency"] == "WEEKLY"

    alerts = client.get("/api/v1/electoral/alerts")
    assert alerts.status_code == 200
    assert alerts.json["snapshot_id"] == snapshot_id
    assert {item["type"] for item in alerts.json["content"]} <= {
        "SLA_OVERDUE",
        "COMMITMENT_OVERDUE",
    }

    with app.app_context():
        actions = set(
            db.session.execute(select(AuditLog.action).where(AuditLog.user_id == user_id)).scalars()
        )
        assert {
            "electoral.mandate_overlay.viewed",
            "electoral.territory_briefing.viewed",
            "electoral.alert_preferences.updated",
            "electoral.alerts.viewed",
        } <= actions


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


def test_immediate_alerts_are_persisted_once_in_delivery_history(app, client):
    _prepare(app)
    csrf = _login(client)
    preference = client.put(
        "/api/v1/electoral/alert-preferences",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "enabled": True,
            "channels": ["IN_APP"],
            "frequency": "IMMEDIATE",
            "alert_types": ["SLA_OVERDUE", "AGENDA_GAP"],
        },
    )
    assert preference.status_code == 200
    snapshot = client.post(
        "/api/v1/electoral/mandate-snapshots",
        headers={"X-CSRF-TOKEN": csrf},
        json={"period_start": "2026-01-01", "period_end": "2026-01-31"},
    )
    assert snapshot.status_code == 201

    history = client.get("/api/v1/electoral/alert-deliveries")
    assert history.status_code == 200
    assert history.json["content"]
    assert {item["status"] for item in history.json["content"]} == {"DELIVERED"}
    assert {item["channel"] for item in history.json["content"]} == {"IN_APP"}
    with app.app_context():
        count = db.session.scalar(select(func.count()).select_from(ElectoralAlertDelivery))
        assert count == len(history.json["content"])


def test_reviewed_crosswalk_adds_reproducible_vote_overlay_without_changing_ict(app, client):
    tenant_id, user_id, _, territory_id, _ = _prepare(app)
    with app.app_context():
        dataset = ElectoralDatasetVersion(
            source_name="TSE",
            source_url="https://dadosabertos.tse.jus.br/",
            source_hash="a" * 64,
            parser_version="test-1",
            coverage_key="2024-MG-13",
            election_year=2024,
            election_scope="MUNICIPAL",
            uf="MG",
            office_code="13",
            coverage={},
            source_metadata={},
            validation_manifest={},
            raw_storage_path="test.zip",
            status=ElectoralDatasetStatus.PUBLISHED,
        )
        db.session.add(dataset)
        db.session.flush()
        election = ElectoralElection(
            dataset_version_id=dataset.id,
            external_id="2024-JF",
            name="Eleições 2024",
            year=2024,
            round=1,
            scope="MUNICIPAL",
            uf="MG",
        )
        office = ElectoralOffice(code="TEST-VEREADOR", name="Vereador")
        party = ElectoralParty(
            dataset_version_id=dataset.id, number=99, acronym="TST", name="Teste"
        )
        candidate = ElectoralCandidate(
            dataset_version_id=dataset.id,
            external_id="candidate-test",
            full_name="Candidato Teste",
            ballot_name="CANDIDATO TESTE",
            normalized_name="candidato teste",
        )
        electoral_territory = ElectoralTerritory(
            dataset_version_id=dataset.id,
            level=ElectoralTerritoryLevel.ELECTORAL_ZONE,
            uf="MG",
            municipality_code="3136702",
            municipality_name="JUIZ DE FORA",
            zone=315,
        )
        db.session.add_all([election, office, party, candidate, electoral_territory])
        db.session.flush()
        candidacy = ElectoralCandidacy(
            dataset_version_id=dataset.id,
            election_id=election.id,
            office_id=office.id,
            candidate_id=candidate.id,
            party_id=party.id,
            ballot_number="99999",
        )
        db.session.add(candidacy)
        db.session.flush()
        db.session.add(
            ElectoralUserCandidacy(
                tenant_id=tenant_id,
                user_id=user_id,
                candidacy_id=candidacy.id,
                method="manual_fallback",
            )
        )
        db.session.add(
            ElectoralResult(
                dataset_version_id=dataset.id,
                election_id=election.id,
                candidacy_id=candidacy.id,
                territory_id=electoral_territory.id,
                votes=432,
                calculation_metadata={},
            )
        )
        db.session.commit()
        election_id, candidate_id, electoral_territory_id = (
            election.id,
            candidate.id,
            electoral_territory.id,
        )
    csrf = _login(client)
    linked = client.post(
        "/api/v1/electoral/territory-links",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "election_id": str(election_id),
            "territory_id": str(territory_id),
            "electoral_territory_id": str(electoral_territory_id),
            "notes": "Vínculo revisado pela equipe territorial.",
        },
    )
    assert linked.status_code == 201
    segment = client.post(
        "/api/v1/electoral/territory-segments",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "name": "Zonas prioritárias para estudo",
            "description": "Agrupamento manual de unidades eleitorais agregadas.",
            "election_id": str(election_id),
            "territory_ids": [str(electoral_territory_id)],
        },
    )
    assert segment.status_code == 201
    catalog = client.get(f"/api/v1/electoral/territory-segments?election_id={election_id}")
    assert catalog.status_code == 200
    assert catalog.json["content"][0]["territory_ids"] == [str(electoral_territory_id)]
    snapshot = client.post(
        "/api/v1/electoral/mandate-snapshots",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "election_id": str(election_id),
            "candidate_id": str(candidate_id),
        },
    )
    assert snapshot.status_code == 201
    row = next(
        item
        for item in snapshot.json["payload"]["territories"]
        if item["territory_id"] == str(territory_id)
    )
    assert row["electoral_overlay"]["votes"] == 432
    assert snapshot.json["payload"]["formula"]["electoral_performance_used"] is False
    overlay = client.get(
        f"/api/v1/electoral/territories/{territory_id}/mandate-overlay?snapshot_id={snapshot.json['id']}"
    )
    assert overlay.json["linkage"]["electoral_overlay_available"] is True


def test_preferences_pre_visit_map_layers_and_safe_agenda_routes(app, client):
    tenant_id, user_id, mandate_id, territory_id, _ = _prepare(app)
    with app.app_context():
        db.session.add(
            ElectoralPublicCommitment(
                tenant_id=tenant_id,
                mandate_id=mandate_id,
                territory_id=territory_id,
                title="Entrega territorial pública",
                description="Ponto público para homologação.",
                responsible_user_id=user_id,
                due_on=datetime(2026, 12, 1).date(),
                status="IN_PROGRESS",
                progress=30,
                public_location_name="Praça Central",
                latitude=-21.7619,
                longitude=-43.3496,
                location_is_public=True,
                created_by_id=user_id,
                updated_by_id=user_id,
            )
        )
        event = AgendaEvent(
            tenant_id=tenant_id,
            event_type=AgendaEventType.VISITA,
            status=AgendaEventStatus.AGENDADO,
            title="Visita à praça pública",
            location="Praça Central",
            starts_at=datetime(2026, 8, 6, 14, tzinfo=UTC),
            territory_id=territory_id,
            created_by_id=user_id,
        )
        db.session.add(event)
        db.session.commit()
        event_id = event.id
    csrf = _login(client)
    preference = client.put(
        "/api/v1/electoral/preferences",
        headers={"X-CSRF-TOKEN": csrf},
        json={"territory_level": "electoral_zone", "indicators": ["votes", "ict", "sla"]},
    )
    assert preference.status_code == 200
    assert preference.json["territory_level"] == "electoral_zone"
    snapshot = client.post(
        "/api/v1/electoral/mandate-snapshots",
        headers={"X-CSRF-TOKEN": csrf},
        json={"period_start": "2026-01-01", "period_end": "2026-01-31"},
    )
    assert snapshot.status_code == 201
    briefing = client.get(
        f"/api/v1/electoral/agenda-events/{event_id}/pre-visit-briefing?snapshot_id={snapshot.json['id']}"
    )
    assert briefing.status_code == 200
    assert briefing.json["kind"] == "PRE_VISIT"
    layers = client.get(f"/api/v1/electoral/mandate-map-layers?snapshot_id={snapshot.json['id']}")
    assert layers.status_code == 200
    assert layers.json["heatmap"][0]["public_reference_points"] == 1
    routes = client.get("/api/v1/electoral/agenda-routes?from=2026-08-05&to=2026-08-10")
    assert routes.status_code == 200
    assert routes.json["stops"][0]["agenda_event_id"] == str(event_id)
    assert "local" not in routes.json["stops"][0]


def test_recurring_report_schedule_accepts_only_internal_recipients_and_dispatches(app, client):
    tenant_id, user_id, mandate_id, _, _ = _prepare(app)
    with app.app_context():
        template = ElectoralReportJob(
            tenant_id=tenant_id,
            mandate_id=mandate_id,
            requested_by_id=user_id,
            report_type="candidate",
            format="PDF",
            purpose="Modelo recorrente de homologação.",
            filters={
                "election_id": str(uuid.uuid4()),
                "candidate_ids": [str(uuid.uuid4())],
                "level": "municipality",
            },
            source_metadata={},
        )
        db.session.add(template)
        db.session.commit()
        template_id = template.id
    csrf = _login(client)
    response = client.post(
        "/api/v1/electoral/report-schedules",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "name": "Resumo semanal",
            "frequency": "WEEKLY",
            "template_report_job_id": str(template_id),
            "recipient_ids": [str(user_id)],
            "next_run_at": "2026-08-05T10:00:00+00:00",
        },
    )
    assert response.status_code == 201
    with app.app_context():
        assert (
            dispatch_due_report_schedules(tenant_id, now=datetime(2026, 8, 5, 12, tzinfo=UTC)) == 1
        )
        schedule = db.session.execute(select(ElectoralReportSchedule)).scalar_one()
        assert schedule.last_run_at is not None
        assert db.session.scalar(select(func.count()).select_from(ElectoralReportJob)) == 2


def test_public_commitment_has_immutable_history_evidence_and_official_map(app, client):
    tenant_id, user_id, _, territory_id, _ = _prepare(app)
    with app.app_context():
        tenant = db.session.get(Tenant, tenant_id)
        tenant.jurisdiction_ibge_code = "3136702"
        tenant.jurisdiction_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"codarea": "3136702"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [-43.4, -21.8],
                                [-43.3, -21.8],
                                [-43.3, -21.7],
                                [-43.4, -21.8],
                            ]
                        ],
                    },
                }
            ],
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
