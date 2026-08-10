import io
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.auth.security import hash_password
from app.extensions import db
from app.models import (
    AgendaEvent,
    AuditLog,
    Notification,
    NotificationType,
    Role,
    Tenant,
    TerritorialAction,
    TerritorialActionAlert,
    TerritorialActionEvidence,
    TerritorialActionStatus,
    TerritorialActionType,
    Territory,
    User,
)
from app.territorial.service import generate_deadline_notifications


def login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return client.get_cookie("csrf_access_token").value


def post(client, path, csrf, payload):
    return client.post(path, json=payload, headers={"X-CSRF-TOKEN": csrf})


def patch(client, path, csrf, payload):
    return client.patch(path, json=payload, headers={"X-CSRF-TOKEN": csrf})


def territory_id(app, tenant_slug="gabinete-a"):
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == tenant_slug)).scalar_one()
        territory = Territory(tenant_id=tenant.id, name=f"Centro {tenant_slug}")
        db.session.add(territory)
        db.session.commit()
        return str(territory.id)


def add_user(app, *, name, email, role=Role.STAFF):
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        user = User(
            tenant_id=tenant.id,
            name=name,
            email=email,
            password_hash=hash_password("SenhaEquipe123!"),
            role=role,
        )
        db.session.add(user)
        db.session.commit()
        return str(user.id)


def test_territorial_action_preserves_context_prevents_duplicate_and_is_tenant_scoped(app, client):
    csrf = login(client, "admin@teste.local", "SenhaForte123!")
    territory = territory_id(app)
    payload = {
        "territorioId": territory,
        "tipo": "TAREFA",
        "titulo": "Investigar demandas recorrentes",
        "descricao": "Conferir os casos que formaram o hotspot.",
        "filtros": {"territorioId": territory, "categoria": "Saúde"},
        "origem": {"tipo": "TERRITORIO", "regra": "recorrência em 30 dias"},
    }

    created = post(client, "/api/v1/painel/territorial/acoes", csrf, payload)
    assert created.status_code == 201
    assert created.json["territorio"] == "Centro gabinete-a"
    assert created.json["filtros"]["categoria"] == "Saúde"
    assert created.json["status"] == "PENDENTE"

    duplicate = post(client, "/api/v1/painel/territorial/acoes", csrf, payload)
    assert duplicate.status_code == 409
    assert duplicate.json["code"] == "TERRITORIAL_ACTION_ALREADY_OPEN"

    listed = client.get(f"/api/v1/painel/territorial/acoes?territorioId={territory}")
    assert listed.status_code == 200
    assert listed.json["content"][0]["id"] == created.json["id"]
    assert listed.json["responsaveis"][0]["nome"] == "Admin A"

    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": csrf})
    login(client, "admin-b@teste.local", "OutraSenha123!")
    other_tenant_actions = client.get(
        f"/api/v1/painel/territorial/acoes?territorioId={territory}"
    )
    assert other_tenant_actions.status_code == 200
    assert other_tenant_actions.json["content"] == []

    with app.app_context():
        assert db.session.execute(select(TerritorialAction)).scalars().one()
        assert db.session.execute(
            select(AuditLog).where(AuditLog.action == "territorial.action.created")
        ).scalar_one()


def test_visit_creates_agenda_event_and_closure_requires_result(app, client):
    csrf = login(client, "admin@teste.local", "SenhaForte123!")
    territory = territory_id(app)
    with app.app_context():
        assignee = db.session.execute(
            select(User).where(User.email == "admin@teste.local")
        ).scalar_one()
        assignee_id = str(assignee.id)
    due_at = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0).isoformat()
    created = post(
        client,
        "/api/v1/painel/territorial/acoes",
        csrf,
        {
            "territorioId": territory,
            "tipo": "VISITA",
            "titulo": "Visita técnica ao Centro",
            "responsavelId": assignee_id,
            "prazo": due_at,
            "filtros": {"territorioId": territory},
        },
    )
    assert created.status_code == 201
    assert created.json["agendaEventoId"]

    invalid = patch(
        client,
        f"/api/v1/painel/territorial/acoes/{created.json['id']}",
        csrf,
        {"status": "CONCLUIDA"},
    )
    assert invalid.status_code == 422

    completed = patch(
        client,
        f"/api/v1/painel/territorial/acoes/{created.json['id']}",
        csrf,
        {
            "status": "CONCLUIDA",
            "resultado": "Visita realizada e demandas encaminhadas.",
            "evidencias": ["Ata registrada no gabinete"],
        },
    )
    assert completed.status_code == 200
    assert completed.json["status"] == "CONCLUIDA"
    assert completed.json["concluidaEm"]

    with app.app_context():
        event = db.session.execute(select(AgendaEvent)).scalars().one()
        assert event.status.value == "REALIZADO"
        assert event.minutes == "Visita realizada e demandas encaminhadas."


def test_history_is_paginated_filtered_and_reports_deadline_state(app, client):
    csrf = login(client, "admin@teste.local", "SenhaForte123!")
    territory = territory_id(app)
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        creator = db.session.execute(
            select(User).where(User.email == "admin@teste.local")
        ).scalar_one()
        for index in range(12):
            db.session.add(TerritorialAction(
                tenant_id=tenant.id,
                territory_id=uuid.UUID(territory),
                action_type=TerritorialActionType.TAREFA,
                status=(
                    TerritorialActionStatus.CONCLUIDA
                    if index == 11
                    else TerritorialActionStatus.PENDENTE
                ),
                title=f"Ação histórica {index:02d}",
                source_key=f"history-{index}",
                source_context={},
                filters={},
                request_ids=[],
                evidence=[],
                created_by_id=creator.id,
                due_at=datetime.now(UTC) - timedelta(hours=1) if index == 0 else None,
            ))
        db.session.commit()

    first_page = client.get(
        f"/api/v1/painel/territorial/acoes?territorioId={territory}&status=TODAS&size=10"
    )
    assert first_page.status_code == 200
    assert first_page.json["total"] == 12
    assert first_page.json["totalPages"] == 2
    assert len(first_page.json["content"]) == 10
    assert first_page.json["permissoes"]["podeGerenciar"] is True

    overdue = client.get(
        f"/api/v1/painel/territorial/acoes?territorioId={territory}&prazoEstado=VENCIDA"
    )
    assert overdue.status_code == 200
    assert overdue.json["content"][0]["prazoEstado"] == "VENCIDA"
    assert client.get(
        f"/api/v1/painel/territorial/acoes?territorioId={territory}&q=histórica%2011"
    ).json["total"] == 1
    assert csrf


def test_staff_sees_and_moves_only_assigned_actions(app, client):
    staff_id = add_user(app, name="Equipe Territorial", email="territorial@teste.local")
    csrf = login(client, "admin@teste.local", "SenhaForte123!")
    territory = territory_id(app)
    created = post(client, "/api/v1/painel/territorial/acoes", csrf, {
        "territorioId": territory,
        "tipo": "TAREFA",
        "titulo": "Conferir iluminação do território",
        "responsavelId": staff_id,
        "prazo": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
    })
    assert created.status_code == 201
    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": csrf})

    staff_csrf = login(client, "territorial@teste.local", "SenhaEquipe123!")
    listed = client.get(f"/api/v1/painel/territorial/acoes?territorioId={territory}")
    assert listed.json["total"] == 1
    assert listed.json["permissoes"] == {
        "escopo": "PROPRIAS",
        "podeCriar": False,
        "podeGerenciar": False,
        "usuarioId": staff_id,
    }
    assert post(client, "/api/v1/painel/territorial/acoes", staff_csrf, {
        "territorioId": territory, "tipo": "TAREFA", "titulo": "Não permitida",
    }).status_code == 403
    assert patch(
        client,
        f"/api/v1/painel/territorial/acoes/{created.json['id']}",
        staff_csrf,
        {"prazo": (datetime.now(UTC) + timedelta(days=2)).isoformat()},
    ).status_code == 403
    started = patch(
        client,
        f"/api/v1/painel/territorial/acoes/{created.json['id']}",
        staff_csrf,
        {"status": "EM_ANDAMENTO"},
    )
    assert started.status_code == 200


def test_deadline_notifications_are_idempotent_and_escalate_to_overdue(app):
    staff_id = add_user(app, name="Equipe Prazo", email="prazo@teste.local")
    territory = territory_id(app)
    now = datetime.now(UTC).replace(microsecond=0)
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        creator = db.session.execute(
            select(User).where(User.email == "admin@teste.local")
        ).scalar_one()
        action = TerritorialAction(
            tenant_id=tenant.id,
            territory_id=uuid.UUID(territory),
            action_type=TerritorialActionType.TAREFA,
            status=TerritorialActionStatus.PENDENTE,
            title="Prazo territorial monitorado",
            assignee_id=uuid.UUID(staff_id),
            due_at=now + timedelta(hours=2),
            source_key="deadline-monitor",
            source_context={}, filters={}, request_ids=[], evidence=[],
            created_by_id=creator.id,
        )
        db.session.add(action)
        db.session.commit()

        assert generate_deadline_notifications(tenant.id, now=now) == 1
        db.session.commit()
        assert generate_deadline_notifications(tenant.id, now=now) == 0
        assert generate_deadline_notifications(tenant.id, now=now + timedelta(hours=3)) == 1
        db.session.commit()
        notifications = db.session.scalars(select(Notification).where(
            Notification.entity_id == str(action.id),
            Notification.notification_type == NotificationType.SLA,
        ).order_by(Notification.created_at)).all()
        assert [item.title for item in notifications] == [
            "Prazo territorial próximo",
            "Ação territorial vencida",
        ]


def test_structured_evidence_and_execution_metrics(app, client):
    csrf = login(client, "admin@teste.local", "SenhaForte123!")
    territory = territory_id(app)
    created = post(client, "/api/v1/painel/territorial/acoes", csrf, {
        "territorioId": territory,
        "tipo": "TAREFA",
        "titulo": "Documentar entrega territorial",
    })
    evidence = post(
        client,
        f"/api/v1/painel/territorial/acoes/{created.json['id']}/evidencias",
        csrf,
        {
            "tipo": "COMPROVANTE",
            "titulo": "Publicação da entrega",
            "descricao": "Página pública que comprova a execução.",
            "url": "https://example.test/entrega",
            "data": datetime.now(UTC).isoformat(),
        },
    )
    assert evidence.status_code == 201
    assert evidence.json["tipo"] == "COMPROVANTE"
    assert evidence.json["url"] == "https://example.test/entrega"

    uploaded = client.post(
        f"/api/v1/painel/territorial/acoes/{created.json['id']}/evidencias",
        data={
            "tipo": "DOCUMENTO",
            "titulo": "Relatório de execução",
            "arquivo": (io.BytesIO(b"evidencia territorial validada"), "relatorio.txt"),
        },
        content_type="multipart/form-data",
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert uploaded.status_code == 201
    assert uploaded.json["nomeArquivo"] == "relatorio.txt"
    assert uploaded.json["statusVerificacao"] == "LIMPO"
    assert uploaded.json["downloadUrl"]

    listed = client.get(f"/api/v1/painel/territorial/acoes?territorioId={territory}")
    evidence_titles = {
        item["titulo"] for item in listed.json["content"][0]["evidenciasEstruturadas"]
    }
    assert evidence_titles == {"Publicação da entrega", "Relatório de execução"}
    metrics = client.get(
        f"/api/v1/painel/territorial/metricas-execucao?territorioId={territory}"
    )
    assert metrics.status_code == 200
    assert metrics.json["total"] == 1
    assert metrics.json["comEvidencias"] == 1
    assert metrics.json["coberturaEvidenciasPercentual"] == 100
    with app.app_context():
        assert db.session.scalar(select(func.count(TerritorialActionEvidence.id))) == 2


def test_alert_lifecycle_is_audited_and_closure_resolves_open_alerts(app, client):
    csrf = login(client, "admin@teste.local", "SenhaForte123!")
    territory = territory_id(app)
    with app.app_context():
        assignee = db.session.execute(
            select(User).where(User.email == "admin@teste.local")
        ).scalar_one()
        assignee_id = str(assignee.id)
    created = post(client, "/api/v1/painel/territorial/acoes", csrf, {
        "territorioId": territory,
        "tipo": "TAREFA",
        "titulo": "Tratar alerta territorial",
        "responsavelId": assignee_id,
        "prazo": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
    })
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        assert generate_deadline_notifications(tenant.id) == 1
        db.session.commit()

    alerts = client.get(
        f"/api/v1/painel/territorial/alertas?territorioId={territory}&status=ABERTOS"
    )
    assert alerts.status_code == 200
    assert alerts.json["content"][0]["status"] == "ATIVO"
    alert_id = alerts.json["content"][0]["id"]
    acknowledged = patch(
        client,
        f"/api/v1/painel/territorial/alertas/{alert_id}",
        csrf,
        {"status": "RECONHECIDO"},
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json["status"] == "RECONHECIDO"

    completed = patch(
        client,
        f"/api/v1/painel/territorial/acoes/{created.json['id']}",
        csrf,
        {"status": "CONCLUIDA", "resultado": "Pendência atendida."},
    )
    assert completed.status_code == 200
    with app.app_context():
        alert = db.session.execute(select(TerritorialActionAlert)).scalar_one()
        assert alert.status.value == "RESOLVIDO"
        assert alert.resolution_note == "Ação encerrada"
        assert db.session.execute(select(AuditLog).where(
            AuditLog.action == "territorial.action.alert.updated"
        )).scalar_one()
