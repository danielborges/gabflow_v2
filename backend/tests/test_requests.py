import uuid

from sqlalchemy import select

from app.extensions import db
from app.models import AuditLog, OutboxEvent, RequestStatus, ServiceRequest

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
