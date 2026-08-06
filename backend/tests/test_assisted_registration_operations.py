from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import ChannelIdentityReview, ChannelMessage, Citizen
from tests.test_p1_operations import login, post


def _create_unmatched_review(client, csrf):
    message = post(
        client,
        "/api/v1/canais/mensagens",
        csrf,
        {
            "canal": "EMAIL",
            "remetenteNome": "Pessoa Assistida",
            "remetenteContato": "assistida@example.org",
            "conteudo": "Solicito atendimento do gabinete para uma demanda local.",
            "idExterno": "assisted-registration-1",
        },
    )
    assert message.status_code == 201
    queue = client.get("/api/v1/canais/revisoes-identidade").json
    return message.json, queue["content"][0], queue


def test_assisted_registration_requires_configuration_and_field_confirmation(app, client):
    auth = login(client)
    message, review, queue = _create_unmatched_review(client, auth["csrf"])
    assert queue["resumo"]["pendentes"] == 1
    assert queue["responsaveis"]
    assert review["prazoEm"] is not None

    blocked = post(
        client,
        f"/api/v1/canais/revisoes-identidade/{review['id']}/preparar-cadastro",
        auth["csrf"],
        {},
    )
    assert blocked.status_code == 409
    assert blocked.json["code"] == "BASE_LEGAL_PADRAO_OBRIGATORIA"

    configured = client.put(
        "/api/v1/canais/configuracao-cadastro-assistido",
        json={
            "baseLegalPadrao": "EXECUCAO_POLITICA_PUBLICA",
            "slaHoras": 12,
            "retencaoDias": 30,
        },
        headers={"X-CSRF-TOKEN": auth["csrf"]},
    )
    assert configured.status_code == 200

    prepared = post(
        client,
        f"/api/v1/canais/revisoes-identidade/{review['id']}/preparar-cadastro",
        auth["csrf"],
        {},
    )
    assert prepared.status_code == 200
    assert prepared.json["preenchimento"]["email"] == "assistida@example.org"
    assert prepared.json["preenchimento"]["baseLegal"] == "EXECUCAO_POLITICA_PUBLICA"

    base_payload = {
        "nome": prepared.json["preenchimento"]["nome"],
        "contatos": [{"tipo": "EMAIL", "valor": prepared.json["preenchimento"]["email"]}],
        "baseLegal": prepared.json["preenchimento"]["baseLegal"],
        "revisaoCanalId": review["id"],
    }
    missing_confirmation = post(client, "/api/v1/cidadaos", auth["csrf"], base_payload)
    assert missing_confirmation.status_code == 422
    with app.app_context():
        assert db.session.execute(select(Citizen)).scalars().all() == []

    created = post(
        client,
        "/api/v1/cidadaos",
        auth["csrf"],
        {
            **base_payload,
            "confirmacoesCadastroAssistido": ["nome", "contato", "baseLegal"],
        },
    )
    assert created.status_code == 201
    completed = client.get("/api/v1/canais/revisoes-identidade?status=VINCULADA").json
    assert completed["content"][0]["tipoDecisao"] == "CADASTRO_MANUAL"
    assert completed["content"][0]["cidadaoSelecionadoId"] == created.json["id"]
    assert completed["content"][0]["mensagem"]["id"] == message["id"]

    metrics = client.get("/api/v1/canais/revisoes-identidade/metricas")
    assert metrics.status_code == 200
    assert metrics.json["cadastrosManuais"] == 1


def test_assignment_reopening_and_retention_are_tenant_scoped(app, client):
    auth = login(client)
    _message, review, queue = _create_unmatched_review(client, auth["csrf"])
    user_id = queue["responsaveis"][0]["id"]
    assigned = client.put(
        f"/api/v1/canais/revisoes-identidade/{review['id']}/atribuicao",
        json={"responsavelId": user_id},
        headers={"X-CSRF-TOKEN": auth["csrf"]},
    )
    assert assigned.status_code == 200
    assert assigned.json["responsavelId"] == user_id

    discarded = post(
        client,
        f"/api/v1/canais/revisoes-identidade/{review['id']}/decisao",
        auth["csrf"],
        {"decisao": "DESCARTAR"},
    )
    assert discarded.status_code == 200
    reopened = post(
        client,
        f"/api/v1/canais/revisoes-identidade/{review['id']}/reabrir",
        auth["csrf"],
        {"justificativa": "Novo dado recebido para conferência."},
    )
    assert reopened.status_code == 200
    assert reopened.json["status"] == "PENDENTE"
    assert reopened.json["reaberturas"] == 1

    post(
        client,
        f"/api/v1/canais/revisoes-identidade/{review['id']}/decisao",
        auth["csrf"],
        {"decisao": "DESCARTAR"},
    )
    client.put(
        "/api/v1/canais/configuracao-cadastro-assistido",
        json={
            "baseLegalPadrao": "EXECUCAO_POLITICA_PUBLICA",
            "slaHoras": 24,
            "retencaoDias": 30,
        },
        headers={"X-CSRF-TOKEN": auth["csrf"]},
    )
    with app.app_context():
        item = db.session.execute(select(ChannelIdentityReview)).scalar_one()
        item.reviewed_at = datetime.now(UTC) - timedelta(days=31)
        db.session.commit()
    retention = post(
        client,
        "/api/v1/canais/revisoes-identidade/retencao/executar",
        auth["csrf"],
        {},
    )
    assert retention.status_code == 200
    assert retention.json["processadas"] == 1
    with app.app_context():
        message = db.session.execute(select(ChannelMessage)).scalar_one()
        assert message.sender_contact is None
        assert message.redacted_at is not None
