import io
from datetime import datetime

from sqlalchemy import select

from app.extensions import db
from app.models import Citizen, Notification, RequestCategory

PASSWORD_A = "SenhaForte123!"  # noqa: S105
PASSWORD_B = "OutraSenha123!"  # noqa: S105


def login(client, tenant="gabinete-a", password=PASSWORD_A):
    email = "admin-b@teste.local" if tenant == "gabinete-b" else "admin@teste.local"
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return {
        "csrf": client.get_cookie("csrf_access_token").value,
        "user": response.json["user"],
    }


def post(client, path, csrf, payload):
    return client.post(path, json=payload, headers={"X-CSRF-TOKEN": csrf})


def patch(client, path, csrf, payload):
    return client.patch(path, json=payload, headers={"X-CSRF-TOKEN": csrf})


def create_service_request(client, csrf, **extra):
    payload = {
        "origem": "WHATSAPP",
        "titulo": "Demanda de teste",
        "descricao": "Descrição válida para a demanda.",
        **extra,
    }
    response = post(client, "/api/v1/solicitacoes", csrf, payload)
    assert response.status_code == 201
    return response.json


def test_citizen_contacts_consents_and_history_are_tenant_scoped(app, client):
    auth = login(client)
    response = post(
        client,
        "/api/v1/cidadaos",
        auth["csrf"],
        {
            "nome": "Maria da Silva",
            "contatos": [{"tipo": "TELEFONE", "valor": "32999999999"}],
            "enderecos": [{"logradouro": "Rua A", "numero": "10"}],
            "canalPreferencial": "WHATSAPP",
            "consentimentoContato": True,
            "consentimentoDivulgacao": False,
            "baseLegal": "EXECUCAO_POLITICA_PUBLICA",
        },
    )
    assert response.status_code == 201
    citizen = response.json
    assert citizen["consentimentoContato"] is True
    assert citizen["consentimentoDivulgacao"] is False

    created = create_service_request(client, auth["csrf"], cidadaoId=citizen["id"])
    detail = client.get(f"/api/v1/cidadaos/{citizen['id']}")
    assert detail.status_code == 200
    assert detail.json["solicitacoes"][0]["protocolo"] == created["protocolo"]

    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": auth["csrf"]})
    login(client, tenant="gabinete-b", password=PASSWORD_B)
    assert client.get(f"/api/v1/cidadaos/{citizen['id']}").status_code == 404

    with app.app_context():
        assert db.session.execute(select(Citizen)).scalars().one().legal_basis


def test_organization_create_and_update(client):
    auth = login(client)
    created = post(
        client,
        "/api/v1/organizacoes",
        auth["csrf"],
        {
            "tipo": "ASSOCIACAO",
            "nome": "Associação do Bairro",
            "contatos": [{"tipo": "EMAIL", "valor": "contato@example.org"}],
            "territorio": "Centro",
        },
    )
    assert created.status_code == 201
    updated = patch(
        client,
        f"/api/v1/organizacoes/{created.json['id']}",
        auth["csrf"],
        {"territorio": "Centro e Zona Norte"},
    )
    assert updated.status_code == 200
    assert updated.json["territorio"] == "Centro e Zona Norte"


def test_category_applies_sla_to_request(app, client):
    auth = login(client)
    category = post(
        client,
        "/api/v1/admin/categorias",
        auth["csrf"],
        {"nome": "Urgência de saúde", "slaHoras": 12},
    )
    assert category.status_code == 201

    created = create_service_request(
        client,
        auth["csrf"],
        categoriaId=category.json["id"],
    )
    assert created["categoria"] == "Urgência de saúde"
    assert created["situacaoSla"] == "PROXIMO_DO_PRAZO"
    due_at = datetime.fromisoformat(created["prazo"])
    created_at = datetime.fromisoformat(created["criadaEm"])
    assert round((due_at - created_at).total_seconds() / 3600) == 12

    with app.app_context():
        assert db.session.execute(select(RequestCategory)).scalars().one().sla_hours == 12


def test_assignment_task_and_notifications(app, client):
    auth = login(client)
    created = create_service_request(
        client,
        auth["csrf"],
        responsavelId=auth["user"]["id"],
    )
    task = post(
        client,
        f"/api/v1/solicitacoes/{created['id']}/tarefas",
        auth["csrf"],
        {
            "titulo": "Verificar demanda no local",
            "responsavelId": auth["user"]["id"],
            "prioridade": "ALTA",
        },
    )
    assert task.status_code == 201
    assert task.json["status"] == "PENDENTE"

    completed = patch(
        client,
        f"/api/v1/tarefas/{task.json['id']}",
        auth["csrf"],
        {"status": "CONCLUIDA"},
    )
    assert completed.json["concluidaEm"] is not None

    notifications = client.get("/api/v1/notificacoes")
    assert notifications.status_code == 200
    assert notifications.json["naoLidas"] == 2

    with app.app_context():
        assert len(db.session.execute(select(Notification)).scalars().all()) == 2


def test_duplicate_group_keeps_individual_protocols(client):
    auth = login(client)
    first = create_service_request(client, auth["csrf"], titulo="Buraco na Rua A")
    second = create_service_request(client, auth["csrf"], titulo="Mesmo buraco na Rua A")

    grouped = post(
        client,
        "/api/v1/solicitacoes/agrupar-duplicadas",
        auth["csrf"],
        {
            "solicitacaoIds": [first["id"], second["id"]],
            "motivo": "Mesmo local e ocorrência",
        },
    )
    assert grouped.status_code == 201

    detail = client.get(f"/api/v1/solicitacoes/{first['id']}")
    assert detail.json["protocolo"] == first["protocolo"]
    assert detail.json["duplicidades"][0]["protocolo"] == second["protocolo"]


def test_attachment_upload_signed_download_and_malware_block(client):
    auth = login(client)
    created = create_service_request(client, auth["csrf"])

    uploaded = client.post(
        f"/api/v1/solicitacoes/{created['id']}/anexos",
        data={"arquivo": (io.BytesIO(b"conteudo seguro"), "evidencia.txt")},
        headers={"X-CSRF-TOKEN": auth["csrf"]},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 201
    assert uploaded.json["statusVerificacao"] == "LIMPO"
    download = client.get(uploaded.json["downloadUrl"])
    assert download.status_code == 200
    assert download.data == b"conteudo seguro"

    blocked = client.post(
        f"/api/v1/solicitacoes/{created['id']}/anexos",
        data={
            "arquivo": (
                io.BytesIO(b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR"),
                "suspeito.txt",
            )
        },
        headers={"X-CSRF-TOKEN": auth["csrf"]},
        content_type="multipart/form-data",
    )
    assert blocked.status_code == 422
    assert "bloqueado" in blocked.json["message"]


def test_notification_cannot_be_read_by_another_tenant(client):
    auth = login(client)
    create_service_request(client, auth["csrf"], responsavelId=auth["user"]["id"])
    item = client.get("/api/v1/notificacoes").json["content"][0]
    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": auth["csrf"]})
    other = login(client, tenant="gabinete-b", password=PASSWORD_B)
    response = patch(
        client,
        f"/api/v1/notificacoes/{item['id']}/lida",
        other["csrf"],
        {},
    )
    assert response.status_code == 404
