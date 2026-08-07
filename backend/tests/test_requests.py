import uuid

from sqlalchemy import select

from app.auth.security import hash_password
from app.extensions import db
from app.models import AuditLog, OutboxEvent, RequestStatus, Role, ServiceRequest, Tenant, User

TENANT_A_PASSWORD = "SenhaForte123!"  # noqa: S105
TENANT_B_PASSWORD = "OutraSenha123!"  # noqa: S105


def login(client, tenant="gabinete-a", password=None):
    password = password or TENANT_A_PASSWORD
    email = "admin-b@teste.local" if tenant == "gabinete-b" else "admin@teste.local"
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == 200
    return client.get_cookie("csrf_access_token").value


def create_request(client, csrf, title="Iluminação pública"):
    return client.post(
        "/api/v1/solicitacoes",
        json={
            "origem": "WHATSAPP",
            "titulo": title,
            "descricao": "Três postes apagados na rua principal.",
            "endereco": "Rua das Flores, 120",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )


def login_as(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return client.get_cookie("csrf_access_token").value


def test_create_request_generates_protocol_history_audit_and_event(app, client):
    csrf = login(client)
    response = create_request(client, csrf)

    assert response.status_code == 201
    assert response.json["protocolo"] == "GF-2026-000001"
    assert response.json["titulo"] == "Iluminação pública"
    assert response.json["descricao"] == "Três postes apagados na rua principal."
    assert response.content_type == "application/json; charset=utf-8"
    assert response.json["status"] == "NOVA"
    assert response.json["historico"][0]["acao"] == "request.created"

    with app.app_context():
        event = db.session.execute(
            select(OutboxEvent).where(OutboxEvent.event_type == "SolicitacaoCriada")
        ).scalar_one()
        audit = db.session.execute(
            select(AuditLog).where(AuditLog.action == "request.created")
        ).scalar_one()
        assert event.payload["protocolo"] == response.json["protocolo"]
        assert audit.tenant_id == event.tenant_id


def test_list_is_scoped_to_authenticated_tenant(client):
    csrf = login(client)
    created = create_request(client, csrf)
    assert created.status_code == 201

    client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-TOKEN": csrf},
    )
    login(client, tenant="gabinete-b", password=TENANT_B_PASSWORD)
    response = client.get("/api/v1/solicitacoes")

    assert response.status_code == 200
    assert response.json["totalElements"] == 0
    hidden = client.get(f"/api/v1/solicitacoes/{created.json['id']}")
    assert hidden.status_code == 404


def test_protocol_is_sequential_per_tenant(client):
    csrf = login(client)
    first = create_request(client, csrf, "Primeira")
    second = create_request(client, csrf, "Segunda")

    assert first.json["protocolo"] == "GF-2026-000001"
    assert second.json["protocolo"] == "GF-2026-000002"


def test_rejects_closing_without_reason(client):
    csrf = login(client)
    created = create_request(client, csrf)

    response = client.patch(
        f"/api/v1/solicitacoes/{created.json['id']}",
        json={"status": "RESOLVIDA"},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert response.status_code == 422
    assert response.json["message"] == "Informe o motivo do encerramento."


def test_resolves_with_reason_and_evidence_and_audits(app, client):
    csrf = login(client)
    created = create_request(client, csrf)

    response = client.patch(
        f"/api/v1/solicitacoes/{created.json['id']}",
        json={
            "status": "RESOLVIDA",
            "motivoEncerramento": "Iluminação restabelecida",
            "evidenciaEncerramento": "Confirmação registrada no protocolo externo 123",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert response.status_code == 200
    assert response.json["status"] == "RESOLVIDA"
    assert response.json["encerradaEm"] is not None

    with app.app_context():
        service_request = db.session.get(ServiceRequest, uuid.UUID(response.json["id"]))
        assert service_request.status == RequestStatus.RESOLVIDA
        audits = db.session.execute(
            select(AuditLog).where(AuditLog.action == "request.updated")
        ).scalars()
        assert len(list(audits)) == 1


def test_adds_interaction_to_request(client):
    csrf = login(client)
    created = create_request(client, csrf)

    response = client.post(
        f"/api/v1/solicitacoes/{created.json['id']}/interacoes",
        json={
            "tipo": "ATUALIZACAO",
            "canal": "WHATSAPP",
            "direcao": "SAIDA",
            "conteudo": "Informamos que a demanda foi encaminhada.",
            "visibilidade": "CIDADAO",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert response.status_code == 201
    assert response.json["interacoes"][0]["direcao"] == "SAIDA"


def test_operational_users_only_see_their_queue_and_unassigned_requests(app, client):
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        staff_a = User(
            tenant_id=tenant.id,
            name="Operacional A",
            email="operacional-a@teste.local",
            password_hash=hash_password("OperacionalA123!"),
            role=Role.STAFF,
        )
        staff_b = User(
            tenant_id=tenant.id,
            name="Operacional B",
            email="operacional-b@teste.local",
            password_hash=hash_password("OperacionalB123!"),
            role=Role.STAFF,
        )
        db.session.add_all([staff_a, staff_b])
        db.session.commit()
        staff_a_id = str(staff_a.id)
        staff_b_id = str(staff_b.id)

    admin_csrf = login(client)
    unassigned = create_request(client, admin_csrf, "Fila geral")
    assigned_a = client.post(
        "/api/v1/solicitacoes",
        json={"origem": "EMAIL", "descricao": "Demanda da equipe A", "responsavelId": staff_a_id},
        headers={"X-CSRF-TOKEN": admin_csrf},
    )
    assigned_b = client.post(
        "/api/v1/solicitacoes",
        json={"origem": "EMAIL", "descricao": "Demanda da equipe B", "responsavelId": staff_b_id},
        headers={"X-CSRF-TOKEN": admin_csrf},
    )
    assert assigned_a.json["responsavel"] == "Operacional A"

    staff_csrf = login_as(client, "operacional-a@teste.local", "OperacionalA123!")
    response = client.get("/api/v1/solicitacoes")
    assert response.status_code == 200
    assert {item["id"] for item in response.json["content"]} == {
        unassigned.json["id"],
        assigned_a.json["id"],
    }
    assert client.get(f"/api/v1/solicitacoes/{assigned_b.json['id']}").status_code == 404

    forbidden = client.patch(
        f"/api/v1/solicitacoes/{unassigned.json['id']}",
        json={"responsavelId": staff_a_id},
        headers={"X-CSRF-TOKEN": staff_csrf},
    )
    assert forbidden.status_code == 403
    assert forbidden.json["message"] == "Somente a liderança pode distribuir solicitações."


def test_chief_of_staff_and_representative_can_distribute_requests(app, client):
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        chief = User(
            tenant_id=tenant.id,
            name="Chefe do Gabinete",
            email="chefe-solicitacoes@teste.local",
            password_hash=hash_password("ChefeGabinete123!"),
            role=Role.STAFF,
        )
        representative = User(
            tenant_id=tenant.id,
            name="Parlamentar",
            email="parlamentar-solicitacoes@teste.local",
            password_hash=hash_password("Parlamentar123!"),
            role=Role.REPRESENTATIVE,
        )
        operational = User(
            tenant_id=tenant.id,
            name="Responsável Operacional",
            email="responsavel-solicitacoes@teste.local",
            password_hash=hash_password("Responsavel123!"),
            role=Role.STAFF,
        )
        db.session.add_all([chief, representative, operational])
        db.session.flush()
        tenant.chief_of_staff_id = chief.id
        db.session.commit()
        operational_id = str(operational.id)

    admin_csrf = login(client)
    first = create_request(client, admin_csrf, "Distribuição pelo chefe")
    second = create_request(client, admin_csrf, "Distribuição parlamentar")

    chief_csrf = login_as(client, "chefe-solicitacoes@teste.local", "ChefeGabinete123!")
    chief_list = client.get("/api/v1/solicitacoes")
    assert chief_list.status_code == 200
    assert chief_list.json["totalElements"] == 2
    assigned_by_chief = client.patch(
        f"/api/v1/solicitacoes/{first.json['id']}",
        json={"responsavelId": operational_id},
        headers={"X-CSRF-TOKEN": chief_csrf},
    )
    assert assigned_by_chief.status_code == 200
    assert assigned_by_chief.json["responsavel"] == "Responsável Operacional"

    representative_csrf = login_as(
        client, "parlamentar-solicitacoes@teste.local", "Parlamentar123!"
    )
    assigned_by_representative = client.patch(
        f"/api/v1/solicitacoes/{second.json['id']}",
        json={"responsavelId": operational_id},
        headers={"X-CSRF-TOKEN": representative_csrf},
    )
    assert assigned_by_representative.status_code == 200
    forbidden_edit = client.patch(
        f"/api/v1/solicitacoes/{second.json['id']}",
        json={"status": "TRIAGEM"},
        headers={"X-CSRF-TOKEN": representative_csrf},
    )
    assert forbidden_edit.status_code == 403
