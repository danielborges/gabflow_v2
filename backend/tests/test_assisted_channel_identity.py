import uuid

from sqlalchemy import select

from app.extensions import db
from app.models import AuditLog, ChannelIdentityReview, Citizen, ServiceRequest
from tests.test_p1_operations import PASSWORD_B, login, post


def _create_citizen(client, csrf, *, name="Ana Cidadã", contact="ana@example.org"):
    response = post(
        client,
        "/api/v1/cidadaos",
        csrf,
        {
            "nome": name,
            "contatos": [{"tipo": "EMAIL", "valor": contact}],
            "baseLegal": "EXECUCAO_POLITICA_PUBLICA",
        },
    )
    assert response.status_code == 201
    return response.json


def test_assisted_channel_review_links_existing_citizen_without_automatic_creation(app, client):
    auth = login(client)
    citizen = _create_citizen(client, auth["csrf"])

    message = post(
        client,
        "/api/v1/canais/mensagens",
        auth["csrf"],
        {
            "canal": "EMAIL",
            "remetenteNome": "Ana",
            "remetenteContato": "ANA@example.org",
            "assunto": "Iluminação",
            "conteudo": "Há um poste apagado próximo à minha residência.",
            "idExterno": "email-assisted-1",
            "metadados": {"provider": "test", "raw": {"secret": "não expor"}},
        },
    )
    assert message.status_code == 201
    assert "raw" not in message.json["metadados"]

    queue = client.get("/api/v1/canais/revisoes-identidade?status=PENDENTE")
    assert queue.status_code == 200
    assert len(queue.json["content"]) == 1
    review = queue.json["content"][0]
    assert review["estadoResolucao"] == "CORRESPONDENCIA_UNICA"
    assert review["candidatos"][0]["id"] == citizen["id"]
    assert review["mensagem"]["remetenteContatoMascarado"] == "A***@example.org"

    with app.app_context():
        assert len(db.session.execute(select(Citizen)).scalars().all()) == 1

    decided = post(
        client,
        f"/api/v1/canais/revisoes-identidade/{review['id']}/decisao",
        auth["csrf"],
        {"decisao": "VINCULAR", "cidadaoId": citizen["id"]},
    )
    assert decided.status_code == 200
    assert decided.json["status"] == "VINCULADA"

    converted = post(
        client,
        f"/api/v1/canais/mensagens/{message.json['id']}/solicitacao",
        auth["csrf"],
        {
            "titulo": "Poste apagado",
            "descricao": "Há um poste apagado próximo à residência da cidadã.",
        },
    )
    assert converted.status_code == 201
    with app.app_context():
        service_request = db.session.get(ServiceRequest, uuid.UUID(converted.json["id"]))
        assert str(service_request.citizen_id) == citizen["id"]
        audit = db.session.execute(
            select(AuditLog).where(AuditLog.action == "channel.identity_review.decided")
        ).scalar_one()
        assert "conteudo" not in (audit.after or {})


def test_unmatched_message_is_queued_and_replay_is_idempotent(app, client):
    auth = login(client)
    payload = {
        "canal": "WHATSAPP",
        "remetenteNome": "Pessoa nova",
        "remetenteContato": "+55 (32) 99999-0000",
        "conteudo": "Mensagem recebida para análise humana pelo gabinete.",
        "idExterno": "whatsapp-assisted-1",
    }
    first = post(client, "/api/v1/canais/mensagens", auth["csrf"], payload)
    replay = post(client, "/api/v1/canais/mensagens", auth["csrf"], payload)
    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json["duplicado"] is True
    assert replay.json["id"] == first.json["id"]

    queue = client.get("/api/v1/canais/revisoes-identidade?status=PENDENTE")
    assert len(queue.json["content"]) == 1
    assert queue.json["content"][0]["estadoResolucao"] == "SEM_CORRESPONDENCIA"

    login(client, tenant="gabinete-b", password=PASSWORD_B)
    other_queue = client.get("/api/v1/canais/revisoes-identidade?status=PENDENTE")
    assert other_queue.status_code == 200
    assert other_queue.json["content"] == []

    with app.app_context():
        assert len(db.session.execute(select(ChannelIdentityReview)).scalars().all()) == 1


def test_review_cannot_link_citizen_from_another_tenant(app, client):
    auth = login(client)
    message = post(
        client,
        "/api/v1/canais/mensagens",
        auth["csrf"],
        {
            "canal": "EMAIL",
            "remetenteContato": "novo@example.org",
            "conteudo": "Mensagem aguardando revisão de identidade.",
        },
    )
    review = client.get("/api/v1/canais/revisoes-identidade").json["content"][0]

    other_auth = login(client, tenant="gabinete-b", password=PASSWORD_B)
    other_citizen = _create_citizen(
        client, other_auth["csrf"], name="Outro gabinete", contact="outro@example.org"
    )

    auth = login(client)
    denied = post(
        client,
        f"/api/v1/canais/revisoes-identidade/{review['id']}/decisao",
        auth["csrf"],
        {"decisao": "VINCULAR", "cidadaoId": other_citizen["id"]},
    )
    assert denied.status_code == 404
    assert message.status_code == 201
