from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import AgendaEvent, ChannelMessage, IntegrationSetting, OversightAction
from tests.test_p1_operations import PASSWORD_B, create_service_request, login, patch, post


def test_agenda_visit_records_minutes_and_creates_request(app, client):
    auth = login(client)
    territory = post(client, "/api/v1/admin/territorios", auth["csrf"], {"nome": "Centro"})
    assert territory.status_code == 201
    create_service_request(
        client,
        auth["csrf"],
        titulo="Demanda aberta no Centro",
        territorioId=territory.json["id"],
        prioridade="ALTA",
    )
    starts_at = (datetime.now(UTC) + timedelta(days=1)).isoformat()

    created = post(
        client,
        "/api/v1/agenda/compromissos",
        auth["csrf"],
        {
            "tipo": "VISITA",
            "titulo": "Visita ao Centro",
            "descricao": "Agenda externa para ouvir moradores.",
            "local": "Praça Central",
            "inicio": starts_at,
            "territorioId": territory.json["id"],
            "participantes": ["Equipe do gabinete"],
        },
    )
    assert created.status_code == 201
    assert created.json["tipo"] == "VISITA"
    assert created.json["territorioId"] == territory.json["id"]

    recorded = post(
        client,
        f"/api/v1/agenda/compromissos/{created.json['id']}/registro",
        auth["csrf"],
        {
            "ata": "Moradores relataram problemas de iluminação em três ruas.",
            "fotos": [{"nome": "foto-1.jpg"}],
            "pendencias": ["Abrir solicitação para iluminação"],
        },
    )
    assert recorded.status_code == 200
    assert recorded.json["status"] == "REALIZADO"
    assert recorded.json["pendencias"] == ["Abrir solicitação para iluminação"]

    service_request = post(
        client,
        f"/api/v1/agenda/compromissos/{created.json['id']}/solicitacoes",
        auth["csrf"],
        {
            "titulo": "Iluminação precária no Centro",
            "descricao": "Demanda registrada durante visita ao Centro.",
        },
    )
    assert service_request.status_code == 201
    assert service_request.json["protocolo"].startswith("GF-")
    routes = client.get("/api/v1/agenda/roteiros-visita")
    assert routes.status_code == 200
    assert routes.json["content"][0]["territorio"] == "Centro"
    assert routes.json["content"][0]["totalDemandas"] >= 1

    with app.app_context():
        event = db.session.execute(select(AgendaEvent)).scalars().one()
        assert event.request_id is not None


def test_oversight_action_report_and_tenant_isolation(app, client):
    auth = login(client)
    request_item = create_service_request(client, auth["csrf"])
    created = post(
        client,
        "/api/v1/fiscalizacoes",
        auth["csrf"],
        {
            "titulo": "Fiscalização da obra da UBS",
            "local": "Bairro Norte",
            "solicitacaoId": request_item["id"],
            "achados": ["Obra sem placa de prazo"],
            "responsaveis": ["Secretaria de Obras"],
            "providencias": ["Solicitar cronograma atualizado"],
        },
    )
    assert created.status_code == 201
    assert created.json["status"] == "PLANEJADA"

    updated = patch(
        client,
        f"/api/v1/fiscalizacoes/{created.json['id']}",
        auth["csrf"],
        {"status": "CONCLUIDA", "relatorio": "Relatório consolidado da vistoria."},
    )
    assert updated.status_code == 200
    assert updated.json["status"] == "CONCLUIDA"

    report = client.get(f"/api/v1/fiscalizacoes/{created.json['id']}/relatorio")
    assert report.status_code == 200
    assert report.json["relatorio"] == "Relatório consolidado da vistoria."

    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": auth["csrf"]})
    other = login(client, tenant="gabinete-b", password=PASSWORD_B)
    forbidden = client.get(f"/api/v1/fiscalizacoes/{created.json['id']}/relatorio")
    assert forbidden.status_code == 404

    with app.app_context():
        assert db.session.execute(select(OversightAction)).scalars().one().request_id is not None
        assert other["user"]["tenant"]["slug"] == "gabinete-b"


def test_admin_integration_upsert_sanitizes_secret(app, client):
    auth = login(client)
    created = post(
        client,
        "/api/v1/admin/integracoes",
        auth["csrf"],
        {
            "tipo": "WHATSAPP",
            "status": "ATIVA",
            "nome": "WhatsApp Business",
            "configuracao": {"numero": "+5532999999999", "token": "segredo"},
        },
    )
    assert created.status_code == 201
    assert created.json["segredosConfigurados"] is True
    assert "token" not in created.json["configuracao"]

    updated = post(
        client,
        "/api/v1/admin/integracoes",
        auth["csrf"],
        {
            "tipo": "WHATSAPP",
            "status": "INATIVA",
            "nome": "WhatsApp pausado",
            "configuracao": {"numero": "+5532888888888"},
        },
    )
    assert updated.status_code == 200
    assert updated.json["status"] == "INATIVA"
    assert updated.json["segredosConfigurados"] is True

    listed = client.get("/api/v1/admin/integracoes")
    assert listed.status_code == 200
    assert listed.json["content"][0]["nome"] == "WhatsApp pausado"

    with app.app_context():
        assert db.session.execute(select(IntegrationSetting)).scalars().one().config == {
            "numero": "+5532888888888"
        }


def test_channel_inbox_webhook_conversion_and_public_form(app, client):
    auth = login(client)
    whatsapp = post(
        client,
        "/api/v1/admin/integracoes",
        auth["csrf"],
        {
            "tipo": "WHATSAPP",
            "status": "ATIVA",
            "nome": "WhatsApp",
            "configuracao": {"numero": "+5532999999999"},
        },
    )
    assert whatsapp.status_code == 201
    public_form = post(
        client,
        "/api/v1/admin/integracoes",
        auth["csrf"],
        {
            "tipo": "FORMULARIO_PUBLICO",
            "status": "ATIVA",
            "nome": "Formulário público",
            "configuracao": {"slug": "gabinete-a"},
        },
    )
    assert public_form.status_code == 201

    webhook = client.post(
        "/api/v1/canais/webhooks/gabinete-a/whatsapp",
        json={
            "remetenteNome": "João",
            "remetenteContato": "+553200000000",
            "conteudo": "Preciso informar um problema de poda de árvore.",
            "idExterno": "wpp-1",
        },
    )
    assert webhook.status_code == 202

    inbox = client.get("/api/v1/canais/mensagens")
    assert inbox.status_code == 200
    assert inbox.json["content"][0]["canal"] == "WHATSAPP"

    converted = post(
        client,
        f"/api/v1/canais/mensagens/{inbox.json['content'][0]['id']}/solicitacao",
        auth["csrf"],
        {"titulo": "Poda de árvore", "descricao": "Problema informado via WhatsApp."},
    )
    assert converted.status_code == 201

    config = client.get("/api/v1/publico/formularios/gabinete-a")
    assert config.status_code == 200
    assert config.json["ativo"] is True

    submitted = client.post(
        "/api/v1/publico/formularios/gabinete-a/solicitacoes",
        json={
            "nome": "Maria",
            "contato": "maria@example.org",
            "titulo": "Demanda enviada pelo formulário",
            "descricao": "Relato público com informações suficientes para triagem.",
            "endereco": "Rua Pública, 100",
        },
    )
    assert submitted.status_code == 201
    assert submitted.json["protocolo"].startswith("GF-")

    with app.app_context():
        messages = db.session.execute(select(ChannelMessage)).scalars().all()
        assert {item.channel.value for item in messages} == {"WHATSAPP", "FORMULARIO"}
        assert any(item.request_id for item in messages)
