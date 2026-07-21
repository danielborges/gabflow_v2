import base64
import hashlib
import hmac
import json
import time
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


def test_resend_inbound_webhook_verifies_signature_and_deduplicates(app, client):
    secret = "whsec_" + base64.b64encode(b"test-resend-secret").decode("utf-8").rstrip("=")
    app.config["RESEND_WEBHOOK_SECRET"] = secret
    auth = login(client)
    email_integration = post(
        client,
        "/api/v1/admin/integracoes",
        auth["csrf"],
        {
            "tipo": "EMAIL",
            "status": "ATIVA",
            "nome": "Resend inbound",
            "configuracao": {"provedor": "resend"},
        },
    )
    assert email_integration.status_code == 201

    payload = {
        "type": "email.received",
        "data": {
            "email_id": "email_inbound_123",
            "message_id": "<message-123@example.org>",
            "from": "Maria <maria@example.org>",
            "to": ["gabinete@gabflow.local"],
            "subject": "Buraco na rua",
            "text": "Relato recebido por e-mail com detalhes suficientes.",
        },
    }
    raw_body, headers = _svix_headers(secret, payload)
    received = client.post(
        "/api/v1/canais/webhooks/gabinete-a/email/resend",
        data=raw_body,
        headers=headers,
        content_type="application/json",
    )
    assert received.status_code == 202

    duplicate = client.post(
        "/api/v1/canais/webhooks/gabinete-a/email/resend",
        data=raw_body,
        headers=headers,
        content_type="application/json",
    )
    assert duplicate.status_code == 200
    assert duplicate.json["duplicado"] is True

    bad_signature = client.post(
        "/api/v1/canais/webhooks/gabinete-a/email/resend",
        data=raw_body,
        headers={**headers, "svix-signature": "v1,invalida"},
        content_type="application/json",
    )
    assert bad_signature.status_code == 400

    with app.app_context():
        messages = db.session.execute(select(ChannelMessage)).scalars().all()
        assert len(messages) == 1
        assert messages[0].channel.value == "EMAIL"
        assert messages[0].external_id == "email_inbound_123"
        assert messages[0].content == "Relato recebido por e-mail com detalhes suficientes."
        assert messages[0].metadata_data["provider"] == "resend"


def test_whatsapp_business_webhook_verifies_meta_signature_and_deduplicates(app, client):
    app_secret = "meta-" + "app-secret"
    verify_token = "verify-" + "token"
    app.config["META_APP_SECRET"] = app_secret
    app.config["WHATSAPP_WEBHOOK_VERIFY_TOKEN"] = verify_token
    auth = login(client)
    whatsapp = post(
        client,
        "/api/v1/admin/integracoes",
        auth["csrf"],
        {
            "tipo": "WHATSAPP",
            "status": "ATIVA",
            "nome": "WhatsApp Business Cloud API",
            "configuracao": {
                "phoneNumberId": "123456789",
                "displayPhoneNumber": "+5532999999999",
                "accessToken": "segredo",
            },
        },
    )
    assert whatsapp.status_code == 201
    assert whatsapp.json["segredosConfigurados"] is True

    verification = client.get(
        "/api/v1/canais/webhooks/gabinete-a/whatsapp/meta",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": verify_token,
            "hub.challenge": "challenge-123",
        },
    )
    assert verification.status_code == 200
    assert verification.text == "challenge-123"

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "5532999999999",
                                "phone_number_id": "123456789",
                            },
                            "contacts": [
                                {"profile": {"name": "Joao Silva"}, "wa_id": "553288888888"}
                            ],
                            "messages": [
                                {
                                    "from": "553288888888",
                                    "id": "wamid.HBgMNTUzMgAB",
                                    "timestamp": "1710000000",
                                    "text": {"body": "Preciso avisar sobre uma arvore caída."},
                                    "type": "text",
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    raw_body, headers = _meta_headers(app_secret, payload)
    received = client.post(
        "/api/v1/canais/webhooks/gabinete-a/whatsapp/meta",
        data=raw_body,
        headers=headers,
        content_type="application/json",
    )
    assert received.status_code == 202
    assert received.json == {"duplicadas": 0, "recebidas": 1}

    duplicate = client.post(
        "/api/v1/canais/webhooks/gabinete-a/whatsapp/meta",
        data=raw_body,
        headers=headers,
        content_type="application/json",
    )
    assert duplicate.status_code == 202
    assert duplicate.json == {"duplicadas": 1, "recebidas": 0}

    bad_signature = client.post(
        "/api/v1/canais/webhooks/gabinete-a/whatsapp/meta",
        data=raw_body,
        headers={"X-Hub-Signature-256": "sha256=invalida"},
        content_type="application/json",
    )
    assert bad_signature.status_code == 400

    with app.app_context():
        messages = db.session.execute(select(ChannelMessage)).scalars().all()
        assert len(messages) == 1
        assert messages[0].channel.value == "WHATSAPP"
        assert messages[0].sender_name == "Joao Silva"
        assert messages[0].sender_contact == "553288888888"
        assert messages[0].external_id == "wamid.HBgMNTUzMgAB"
        assert messages[0].content == "Preciso avisar sobre uma arvore caída."
        assert messages[0].metadata_data["provider"] == "meta_whatsapp_cloud_api"


def test_meta_social_webhook_receives_facebook_and_instagram_events(app, client):
    app_secret = "meta-" + "social-secret"
    verify_token = "meta-" + "verify-token"
    app.config["META_APP_SECRET"] = app_secret
    app.config["META_WEBHOOK_VERIFY_TOKEN"] = verify_token
    auth = login(client)
    social = post(
        client,
        "/api/v1/admin/integracoes",
        auth["csrf"],
        {
            "tipo": "REDE_SOCIAL",
            "status": "ATIVA",
            "nome": "Meta Social",
            "configuracao": {
                "plataformas": ["FACEBOOK", "INSTAGRAM"],
                "pageAccessToken": "segredo",
            },
        },
    )
    assert social.status_code == 201
    assert social.json["segredosConfigurados"] is True

    verification = client.get(
        "/api/v1/canais/webhooks/gabinete-a/redes-sociais/meta",
        query_string={
            "hub.mode": "subscribe",
            "hub.verify_token": verify_token,
            "hub.challenge": "social-challenge",
        },
    )
    assert verification.status_code == 200
    assert verification.text == "social-challenge"

    facebook_payload = {
        "object": "page",
        "entry": [
            {
                "id": "page-1",
                "time": 1710000010,
                "messaging": [
                    {
                        "sender": {"id": "user-facebook-1"},
                        "recipient": {"id": "page-1"},
                        "timestamp": 1710000010,
                        "message": {
                            "mid": "mid.facebook.1",
                            "text": "Mensagem enviada pelo Facebook Messenger.",
                        },
                    }
                ],
            }
        ],
    }
    raw_body, headers = _meta_headers(app_secret, facebook_payload)
    facebook = client.post(
        "/api/v1/canais/webhooks/gabinete-a/redes-sociais/meta",
        data=raw_body,
        headers=headers,
        content_type="application/json",
    )
    assert facebook.status_code == 202
    assert facebook.json == {"duplicadas": 0, "recebidas": 1}

    instagram_payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "ig-1",
                "time": 1710000020,
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "comment_id": "ig-comment-1",
                            "text": "Comentario publico recebido no Instagram.",
                            "from": {"id": "ig-user-1", "username": "cidadao_ig"},
                            "media_id": "media-1",
                            "created_time": 1710000020,
                        },
                    }
                ],
            }
        ],
    }
    raw_body, headers = _meta_headers(app_secret, instagram_payload)
    instagram = client.post(
        "/api/v1/canais/webhooks/gabinete-a/redes-sociais/meta",
        data=raw_body,
        headers=headers,
        content_type="application/json",
    )
    assert instagram.status_code == 202
    assert instagram.json == {"duplicadas": 0, "recebidas": 1}

    duplicate = client.post(
        "/api/v1/canais/webhooks/gabinete-a/redes-sociais/meta",
        data=raw_body,
        headers=headers,
        content_type="application/json",
    )
    assert duplicate.status_code == 202
    assert duplicate.json == {"duplicadas": 1, "recebidas": 0}

    bad_signature = client.post(
        "/api/v1/canais/webhooks/gabinete-a/redes-sociais/meta",
        data=raw_body,
        headers={"X-Hub-Signature-256": "sha256=invalida"},
        content_type="application/json",
    )
    assert bad_signature.status_code == 400

    with app.app_context():
        messages = db.session.execute(
            select(ChannelMessage).order_by(ChannelMessage.subject)
        ).scalars().all()
        assert len(messages) == 2
        assert {item.channel.value for item in messages} == {"REDE_SOCIAL"}
        assert {item.metadata_data["platform"] for item in messages} == {
            "FACEBOOK",
            "INSTAGRAM",
        }
        assert {item.external_id for item in messages} == {
            "meta:facebook:mid.facebook.1",
            "meta:instagram:ig-comment-1",
        }


def test_global_search_returns_tenant_scoped_results(app, client):
    auth = login(client)
    create_service_request(client, auth["csrf"], titulo="Iluminacao da Praca Azul")
    created = post(
        client,
        "/api/v1/fiscalizacoes",
        auth["csrf"],
        {
            "titulo": "Vistoria da Praca Azul",
            "local": "Praca Azul",
            "achados": ["Lampadas queimadas"],
        },
    )
    assert created.status_code == 201

    response = client.get("/api/v1/busca?q=Praca%20Azul")
    assert response.status_code == 200
    result_types = {item["tipo"] for item in response.json["content"]}
    assert "SOLICITACAO" in result_types
    assert "FISCALIZACAO" in result_types
    assert all(item["view"] in {"requests", "oversight"} for item in response.json["content"])


def _svix_headers(secret: str, payload: dict):
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    message_id = "msg_test"
    timestamp = str(int(time.time()))
    secret_value = secret.removeprefix("whsec_")
    key = base64.b64decode(secret_value + "=" * (-len(secret_value) % 4))
    signed_content = b".".join(
        [message_id.encode("utf-8"), timestamp.encode("utf-8"), raw_body]
    )
    signature = base64.b64encode(
        hmac.new(key, signed_content, hashlib.sha256).digest()
    ).decode("utf-8")
    return raw_body, {
        "svix-id": message_id,
        "svix-timestamp": timestamp,
        "svix-signature": f"v1,{signature}",
    }


def _meta_headers(app_secret: str, payload: dict):
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return raw_body, {"X-Hub-Signature-256": f"sha256={signature}"}
