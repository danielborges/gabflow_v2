import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.ai.transcription import TranscriptionResult
from app.communications.whatsapp_flows import bootstrap_flow_definitions
from app.communications.whatsapp_media import MediaDownload
from app.communications.whatsapp_outbound import OutboundResult, TemplateSyncResult
from app.extensions import db
from app.models import (
    Citizen,
    OutboxEvent,
    ServiceRequest,
    Tenant,
    User,
    WhatsAppContact,
    WhatsAppContactOptStatus,
    WhatsAppConversation,
    WhatsAppConversationMode,
    WhatsAppConversationState,
    WhatsAppFlowDefinition,
    WhatsAppFlowSession,
    WhatsAppFlowSubmission,
    WhatsAppIntegration,
    WhatsAppIntegrationStatus,
    WhatsAppMediaAsset,
    WhatsAppMessage,
    WhatsAppMessageDirection,
    WhatsAppMessageStatus,
    WhatsAppMessageTemplate,
    WhatsAppPrivacyRecord,
    WhatsAppRequestDraft,
)
from app.outbox.service import process_batch

TEST_SECRET = "conversation-secret"  # noqa: S105
ADMIN_A_PASSWORD = "SenhaForte123!"  # noqa: S105
ADMIN_B_PASSWORD = "OutraSenha123!"  # noqa: S105


def _login(client, tenant="gabinete-a", email="admin@teste.local", password=None):
    password = password or ADMIN_A_PASSWORD
    return client.post(
        "/api/v1/auth/login",
        json={"tenant": tenant, "email": email, "password": password},
    )


def _integration(tenant, user, phone_number_id="phone-a"):
    item = WhatsAppIntegration(
        tenant_id=tenant.id,
        business_portfolio_id="portfolio-a",
        waba_id="waba-a",
        phone_number_id=phone_number_id,
        status=WhatsAppIntegrationStatus.ACTIVE,
        version=1,
        token_secret_ref="arn:aws:secretsmanager:sa-east-1:123:secret:test",  # noqa: S106
        created_by_id=user.id,
    )
    db.session.add(item)
    db.session.commit()
    return item


def _payload(content="Preciso de atendimento", message_id="wamid.conversation.1"):
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "waba-a",
            "changes": [{
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": "phone-a"},
                    "contacts": [{"wa_id": "553288880000", "profile": {"name": "Maria"}}],
                    "messages": [{
                        "id": message_id,
                        "from": "553288880000",
                        "timestamp": "1786500000",
                        "type": "text",
                        "text": {"body": content},
                    }],
                },
            }],
        }],
    }


def _flow_payload(flow_token, *, message_id="wamid.flow.1", values=None):
    response = {
        "flow_token": flow_token,
        "assunto": "Iluminacao publica",
        "descricao": "Poste apagado na rua principal.",
        "local": "Rua Principal, 10",
        "urgencia": "ALTO",
        "confirmado": True,
    }
    response.update(values or {})
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "waba-a",
            "changes": [{
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": "phone-a"},
                    "contacts": [{"wa_id": "553288880000", "profile": {"name": "Maria"}}],
                    "messages": [{
                        "id": message_id,
                        "from": "553288880000",
                        "timestamp": "1786500200",
                        "type": "interactive",
                        "interactive": {
                            "type": "nfm_reply",
                            "nfm_reply": {
                                "name": "flow",
                                "body": "Formulario concluido",
                                "response_json": json.dumps(response),
                            },
                        },
                    }],
                },
            }],
        }],
    }


def _audio_payload(*, message_id="wamid.audio.1", media_id="media-audio-1"):
    payload = _payload(message_id=message_id)
    message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    message.pop("text")
    message["type"] = "audio"
    message["audio"] = {
        "id": media_id,
        "mime_type": "audio/mpeg",
        "sha256": "Ocht0OmXTPEAJVA61Fc5T/QnHDYXToxpuiAitxZ6URU=",
    }
    return payload


def _status_payload(message_id, status):
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "waba-1",
            "changes": [{
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": "phone-a"},
                    "statuses": [{
                        "id": message_id,
                        "status": status,
                        "timestamp": "1786500300",
                    }],
                },
            }],
        }],
    }


class FakeMediaAdapter:
    def download(self, _integration, provider_media_id):
        return MediaDownload(
            content=b"ID3-whatsapp-audio",
            mime_type="audio/mpeg; codecs=test",
            filename=f"{provider_media_id}.mp3",
        )


class FakeWhatsAppTranscriptionProvider:
    provider = "FASTER_WHISPER"
    model = "base"

    def transcribe(self, _path):
        return TranscriptionResult(
            text="A Rua das Flores está sem iluminação.",
            language="pt",
            language_probability=0.97,
            duration_seconds=3.5,
            segments=[],
        )


class FakeOutboundAdapter:
    def __init__(self):
        self.sent = []

    def send(self, _integration, recipient, payload):
        self.sent.append((recipient, payload))
        return OutboundResult(provider_message_id=f"wamid.out.{len(self.sent)}")

    def sync_template(self, _integration, template):
        return TemplateSyncResult(
            status="APPROVED",
            provider_template_id=f"meta-{template.id}",
            components=[],
        )


def _receive(client, payload):
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(TEST_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/api/v1/webhooks/meta/whatsapp",
        data=body,
        content_type="application/json",
        headers={"X-Hub-Signature-256": f"sha256={signature}"},
    )


def _prepare(app, client, content="Preciso de atendimento"):
    app.config["META_APP_SECRET"] = TEST_SECRET
    with app.app_context():
        tenant = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-a"))
        user = db.session.scalar(select(User).where(User.tenant_id == tenant.id))
        _integration(tenant, user)
        tenant_id = tenant.id
    assert _receive(client, _payload(content)).status_code == 200
    with app.app_context():
        assert process_batch("conversation-worker").succeeded == 1
        conversation_id = db.session.scalar(select(WhatsAppConversation.id))
    return tenant_id, conversation_id


def _csrf(client):
    return {"X-CSRF-TOKEN": client.get_cookie("csrf_access_token").value}


def test_inbound_creates_contact_conversation_message_and_privacy_state(app, client):
    tenant_id, conversation_id = _prepare(app, client)
    with app.app_context():
        contact = db.session.scalar(select(WhatsAppContact))
        conversation = db.session.get(WhatsAppConversation, conversation_id)
        message = db.session.scalar(select(WhatsAppMessage))
        assert contact.tenant_id == tenant_id
        assert contact.wa_user_id == "553288880000"
        assert conversation.state == WhatsAppConversationState.PRIVACY_NOTICE
        assert conversation.mode == WhatsAppConversationMode.BOT
        assert conversation.unread_count == 1
        assert conversation.window_expires_at is not None
        assert message.conversation_id == conversation_id


def test_inbox_lists_detail_marks_read_and_handoff_pauses_bot(app, client):
    tenant_id, conversation_id = _prepare(app, client)
    assert _login(client).status_code == 200

    listing = client.get(f"/api/v1/tenants/{tenant_id}/conversations")
    assert listing.status_code == 200
    assert listing.json["content"][0]["contato"]["nome"] == "Maria"
    assert listing.json["content"][0]["contato"]["whatsappMascarado"] == "***0000"
    assert listing.json["content"][0]["naoLidas"] == 1

    detail = client.get(f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}")
    assert detail.status_code == 200
    assert detail.json["mensagens"][0]["conteudo"] == "Preciso de atendimento"
    assert detail.json["transicoes"][0]["para"] == "PRIVACY_NOTICE"

    handoff = client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/handoff",
        json={"reason": "Atendimento especializado"},
        headers=_csrf(client),
    )
    assert handoff.status_code == 200
    assert handoff.json == {"estado": "HUMAN_HANDOFF", "modo": "HUMAN"}

    read = client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/read",
        headers=_csrf(client),
    )
    assert read.status_code == 200
    assert read.json["naoLidas"] == 0

    resume = client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/resume-bot",
        json={"reason": "Retomar fluxo"},
        headers=_csrf(client),
    )
    assert resume.status_code == 200
    assert resume.json["modo"] == "BOT"
    assert resume.json["estado"] == "PRIVACY_NOTICE"


def test_citizen_human_request_enters_handoff_without_assignee(app, client):
    _, conversation_id = _prepare(app, client, content="Falar com assessor")
    with app.app_context():
        conversation = db.session.get(WhatsAppConversation, conversation_id)
        assert conversation.state == WhatsAppConversationState.HUMAN_HANDOFF
        assert conversation.mode == WhatsAppConversationMode.HUMAN
        assert conversation.assigned_user_id is None


def test_opt_out_is_deterministic_and_terminal(app, client):
    tenant_id, conversation_id = _prepare(app, client, content="PARAR")
    adapter = FakeOutboundAdapter()
    app.extensions["whatsapp_outbound_adapter"] = adapter
    with app.app_context():
        contact = db.session.scalar(select(WhatsAppContact))
        conversation = db.session.get(WhatsAppConversation, conversation_id)
        assert contact.opt_status == WhatsAppContactOptStatus.OPTED_OUT
        assert contact.opted_out_at is not None
        assert conversation.state == WhatsAppConversationState.OPTED_OUT
        confirmation = db.session.scalar(
            select(WhatsAppMessage).where(WhatsAppMessage.opt_out_confirmation.is_(True))
        )
        assert confirmation.status == WhatsAppMessageStatus.QUEUED
        for _ in range(3):
            process_batch("optout-confirmation-worker")
        assert confirmation.status == WhatsAppMessageStatus.SENT
        assert confirmation.policy_decision == "OPT_OUT_CONFIRMATION"
    assert _login(client).status_code == 200
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/handoff",
        json={},
        headers=_csrf(client),
    )
    assert response.status_code == 422
    blocked = client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/messages",
        json={"texto": "Nova mensagem"},
        headers={**_csrf(client), "Idempotency-Key": "blocked-after-optout"},
    )
    assert blocked.status_code == 422


def test_outbound_policy_allows_window_and_requires_approved_template_outside_it(
    app, client
):
    tenant_id, conversation_id = _prepare(app, client)
    adapter = FakeOutboundAdapter()
    app.extensions["whatsapp_outbound_adapter"] = adapter
    assert _login(client).status_code == 200
    headers = _csrf(client)

    created_template = client.post(
        f"/api/v1/tenants/{tenant_id}/whatsapp/templates",
        json={
            "nome": "status_update",
            "idioma": "pt_BR",
            "categoria": "UTILITY",
            "conteudo": "A solicitação {{1}} foi atualizada.",
            "variaveis": ["protocolo"],
        },
        headers=headers,
    )
    assert created_template.status_code == 202
    template_id = uuid.UUID(created_template.json["id"])

    free = client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/messages",
        json={"texto": "Retorno do gabinete dentro da janela."},
        headers={**headers, "Idempotency-Key": "free-window-1"},
    )
    assert free.status_code == 202
    repeated = client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/messages",
        json={"texto": "Retorno do gabinete dentro da janela."},
        headers={**headers, "Idempotency-Key": "free-window-1"},
    )
    assert repeated.status_code == 200
    assert repeated.json["id"] == free.json["id"]
    conflict = client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/messages",
        json={"texto": "Conteúdo diferente"},
        headers={**headers, "Idempotency-Key": "free-window-1"},
    )
    assert conflict.status_code == 422

    with app.app_context():
        for _ in range(3):
            process_batch("outbound-worker")
        free_message = db.session.get(WhatsAppMessage, uuid.UUID(free.json["id"]))
        assert free_message.status == WhatsAppMessageStatus.SENT
        assert free_message.provider_message_id == "wamid.out.1"
        conversation = db.session.get(WhatsAppConversation, conversation_id)
        conversation.window_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        template = db.session.get(WhatsAppMessageTemplate, template_id)
        assert template.status == "APPROVED"
        assert template.provider_template_id == f"meta-{template.id}"
        db.session.commit()

    assert _receive(client, _status_payload("wamid.out.1", "delivered")).status_code == 200
    with app.app_context():
        process_batch("outbound-status-worker")
        free_message = db.session.get(WhatsAppMessage, uuid.UUID(free.json["id"]))
        assert free_message.status == WhatsAppMessageStatus.DELIVERED
        assert free_message.delivered_at is not None

    closed = client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/messages",
        json={"texto": "Mensagem livre tardia"},
        headers={**headers, "Idempotency-Key": "free-closed-1"},
    )
    assert closed.status_code == 422
    templated = client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/messages",
        json={"templateId": str(template_id), "parametros": ["GFW-ABC123"]},
        headers={**headers, "Idempotency-Key": "template-closed-1"},
    )
    assert templated.status_code == 202
    with app.app_context():
        for _ in range(3):
            process_batch("template-outbound-worker")
        sent = db.session.scalar(
            select(WhatsAppMessage).where(
                WhatsAppMessage.direction == WhatsAppMessageDirection.OUTBOUND,
                WhatsAppMessage.idempotency_key == "template-closed-1",
            )
        )
        assert sent.status == WhatsAppMessageStatus.SENT
        assert sent.policy_decision == "APPROVED_TEMPLATE"


def test_conversation_cannot_be_read_from_another_tenant(app, client):
    _, conversation_id = _prepare(app, client)
    with app.app_context():
        tenant_b_id = db.session.scalar(select(Tenant.id).where(Tenant.slug == "gabinete-b"))
    assert _login(
        client,
        tenant="gabinete-b",
        email="admin-b@teste.local",
        password=ADMIN_B_PASSWORD,
    ).status_code == 200
    assert (
        client.get(f"/api/v1/tenants/{tenant_b_id}/conversations/{conversation_id}").status_code
        == 404
    )


def test_privacy_citizen_and_request_flow_is_confirmed_and_idempotent(app, client):
    tenant_id, conversation_id = _prepare(app, client)
    assert _login(client).status_code == 200
    headers = _csrf(client)

    detail = client.get(f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}")
    assert detail.status_code == 200
    assert detail.json["jornada"]["privacidade"]["solicitada"] is True
    assert detail.json["jornada"]["privacidade"]["reconhecida"] is False

    privacy = client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/privacy",
        json={
            "baseLegal": "EXECUCAO_POLITICA_PUBLICA",
            "consentimentoNecessario": False,
        },
        headers=headers,
    )
    assert privacy.status_code == 200
    assert privacy.json["estado"] == "IDENTIFICATION"
    assert len(privacy.json["privacidade"]["evidenciaHash"]) == 64

    citizen = client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/citizen",
        json={"nome": "Maria da Silva", "confirmado": True},
        headers=headers,
    )
    assert citizen.status_code == 201
    citizen_id = citizen.json["cidadao"]["id"]

    draft = client.put(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/request-draft",
        json={
            "titulo": "Iluminacao publica",
            "descricao": "Poste apagado na rua principal.",
            "endereco": "Rua Principal, 10",
        },
        headers=headers,
    )
    assert draft.status_code == 200
    assert draft.json["estado"] == "REVIEW"

    confirmation_headers = {**headers, "Idempotency-Key": "wa-flow-confirmation-001"}
    confirmed = client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/request-draft/confirm",
        json={"confirmado": True},
        headers=confirmation_headers,
    )
    assert confirmed.status_code == 201
    assert confirmed.json["protocoloPublico"].startswith("GFW-")
    assert confirmed.json["chaveAcompanhamento"]

    repeated = client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/request-draft/confirm",
        json={"confirmado": True},
        headers=confirmation_headers,
    )
    assert repeated.status_code == 200
    assert repeated.json["id"] == confirmed.json["id"]
    assert repeated.json["criada"] is False

    with app.app_context():
        created_citizen = db.session.get(Citizen, uuid.UUID(citizen_id))
        assert created_citizen.cpf_ciphertext is None
        assert created_citizen.contacts[0]["tipo"] == "WHATSAPP"
        assert db.session.query(ServiceRequest).count() == 1
        assert db.session.query(WhatsAppPrivacyRecord).count() == 2
        request_draft = db.session.scalar(select(WhatsAppRequestDraft))
        assert request_draft.status == "CREATED"
        privacy_event = db.session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "WhatsappPrivacyNoticeRequested"
            )
        )
        assert privacy_event is not None
        assert "553288880000" not in str(privacy_event.payload)


def test_citizen_link_cannot_cross_tenants(app, client):
    tenant_id, conversation_id = _prepare(app, client)
    with app.app_context():
        tenant_b = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-b"))
        user_b = db.session.scalar(select(User).where(User.tenant_id == tenant_b.id))
        outsider = Citizen(
            tenant_id=tenant_b.id,
            name="Cidada de outro gabinete",
            legal_basis="EXECUCAO_POLITICA_PUBLICA",
            created_by_id=user_b.id,
        )
        db.session.add(outsider)
        db.session.commit()
        outsider_id = outsider.id
    assert _login(client).status_code == 200
    headers = _csrf(client)
    assert client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/privacy",
        json={"baseLegal": "EXECUCAO_POLITICA_PUBLICA"},
        headers=headers,
    ).status_code == 200
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/citizen",
        json={"cidadaoId": str(outsider_id), "confirmado": True},
        headers=headers,
    )
    assert response.status_code == 422
    with app.app_context():
        contact = db.session.scalar(select(WhatsAppContact))
        assert contact.citizen_id is None


def _prepare_identified_conversation(app, client):
    tenant_id, conversation_id = _prepare(app, client)
    assert _login(client).status_code == 200
    headers = _csrf(client)
    assert client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/privacy",
        json={"baseLegal": "EXECUCAO_POLITICA_PUBLICA"},
        headers=headers,
    ).status_code == 200
    assert client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/citizen",
        json={"nome": "Maria da Silva", "confirmado": True},
        headers=headers,
    ).status_code == 201
    return tenant_id, conversation_id, headers


def _activate_request_flow(client, tenant_id, headers):
    created = client.post(
        f"/api/v1/tenants/{tenant_id}/whatsapp/flows/bootstrap",
        headers=headers,
    )
    assert created.status_code == 201
    definition = next(
        item for item in created.json["content"] if item["chave"] == "new_service_request"
    )
    activated = client.post(
        f"/api/v1/tenants/{tenant_id}/whatsapp/flows/{definition['id']}/activate",
        json={"metaFlowId": "meta-flow-request-v1"},
        headers=headers,
    )
    assert activated.status_code == 200
    return definition


def test_flow_definitions_are_versioned_activated_and_tenant_scoped(app, client):
    tenant_id, _, headers = _prepare_identified_conversation(app, client)
    definition = _activate_request_flow(client, tenant_id, headers)
    next_version = client.post(
        f"/api/v1/tenants/{tenant_id}/whatsapp/flows/versions",
        json={"chave": "new_service_request"},
        headers=headers,
    )
    assert next_version.status_code == 201
    assert next_version.json["versao"] == 2
    assert next_version.json["schemaHash"] != definition["schemaHash"]
    assert client.post(
        f"/api/v1/tenants/{tenant_id}/whatsapp/flows/{next_version.json['id']}/activate",
        json={"metaFlowId": "meta-flow-request-v2"},
        headers=headers,
    ).status_code == 200
    with app.app_context():
        versions = list(
            db.session.scalars(
                select(WhatsAppFlowDefinition)
                .where(WhatsAppFlowDefinition.flow_key == "new_service_request")
                .order_by(WhatsAppFlowDefinition.version)
            )
        )
        assert [item.status for item in versions] == ["RETIRED", "ACTIVE"]
        assert all(item.tenant_id == tenant_id for item in versions)


def test_flow_versions_are_independent_between_environments(app, client):
    tenant_id, _, headers = _prepare_identified_conversation(app, client)
    assert client.post(
        f"/api/v1/tenants/{tenant_id}/whatsapp/flows/bootstrap", headers=headers
    ).status_code == 201
    with app.app_context():
        user = db.session.scalar(select(User).where(User.tenant_id == tenant_id))
        staging = bootstrap_flow_definitions(tenant_id, user.id, environment="STAGING")
        db.session.commit()
        assert len(staging) == 3
        assert db.session.query(WhatsAppFlowDefinition).count() == 6


def test_launch_flow_uses_active_version_or_guided_fallback(app, client):
    tenant_id, conversation_id, headers = _prepare_identified_conversation(app, client)
    fallback = client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/flows/new_service_request/launch",
        headers=headers,
    )
    assert fallback.status_code == 200
    assert fallback.json["modo"] == "GUIDED"

    _activate_request_flow(client, tenant_id, headers)
    launched = client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/flows/new_service_request/launch",
        headers=headers,
    )
    assert launched.status_code == 202
    assert launched.json["modo"] == "FLOW"
    with app.app_context():
        session = db.session.scalar(select(WhatsAppFlowSession))
        event = db.session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "WhatsappFlowLaunchRequested"
            )
        )
        assert session.status == "PENDING"
        assert len(session.token_hash) == 64
        assert event.payload["flowToken"] not in session.token_hash


def test_nfm_reply_creates_one_request_and_rejects_replay(app, client):
    tenant_id, conversation_id, headers = _prepare_identified_conversation(app, client)
    _activate_request_flow(client, tenant_id, headers)
    assert client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/flows/new_service_request/launch",
        headers=headers,
    ).status_code == 202
    with app.app_context():
        launch_event = db.session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "WhatsappFlowLaunchRequested"
            )
        )
        flow_token = launch_event.payload["flowToken"]

    assert _receive(client, _flow_payload(flow_token)).status_code == 200
    with app.app_context():
        for _ in range(4):
            process_batch("flow-worker")
        submission = db.session.scalar(select(WhatsAppFlowSubmission))
        request_item = db.session.scalar(select(ServiceRequest))
        assert submission.status == "APPLIED"
        assert submission.values == {
            "fieldNames": ["assunto", "confirmado", "descricao", "local", "urgencia"],
            "redacted": True,
        }
        assert submission.request_id == request_item.id
        assert request_item.public_protocol.startswith("GFW-")
        assert request_item.urgency == "ALTO"
        assert db.session.query(ServiceRequest).count() == 1

    assert _receive(client, _flow_payload(flow_token)).status_code == 200
    with app.app_context():
        for _ in range(2):
            process_batch("flow-worker-replay")
        assert db.session.query(ServiceRequest).count() == 1
        assert db.session.query(WhatsAppFlowSubmission).count() == 1


def test_flow_submission_with_unknown_field_is_rejected_without_retry(app, client):
    tenant_id, conversation_id, headers = _prepare_identified_conversation(app, client)
    _activate_request_flow(client, tenant_id, headers)
    assert client.post(
        f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}/flows/new_service_request/launch",
        headers=headers,
    ).status_code == 202
    with app.app_context():
        flow_token = db.session.scalar(
            select(OutboxEvent.payload).where(
                OutboxEvent.event_type == "WhatsappFlowLaunchRequested"
            )
        )["flowToken"]
    payload = _flow_payload(flow_token, values={"campo_injetado": "nao permitido"})
    assert _receive(client, payload).status_code == 200
    with app.app_context():
        for _ in range(4):
            process_batch("flow-invalid-worker")
        submission = db.session.scalar(select(WhatsAppFlowSubmission))
        assert submission.status == "REJECTED"
        assert submission.error_code == "FLOW_UNKNOWN_FIELD"
        assert submission.values["redacted"] is True
        assert "campo_injetado" in submission.values["fieldNames"]
        assert db.session.query(ServiceRequest).count() == 0


def test_whatsapp_audio_is_downloaded_scanned_transcribed_and_reviewable(
    app, client, monkeypatch
):
    tenant_id, conversation_id = _prepare(app, client)
    app.extensions["whatsapp_media_adapter"] = FakeMediaAdapter()
    monkeypatch.setattr(
        "app.communications.whatsapp_media.transcription_provider",
        lambda: FakeWhatsAppTranscriptionProvider(),
    )

    assert _receive(client, _audio_payload()).status_code == 200
    assert _receive(client, _audio_payload()).status_code == 200
    with app.app_context():
        for _ in range(4):
            process_batch("whatsapp-media-worker")
        asset = db.session.scalar(select(WhatsAppMediaAsset))
        assert db.session.query(WhatsAppMediaAsset).count() == 1
        assert asset.tenant_id == tenant_id
        assert asset.conversation_id == conversation_id
        assert asset.status == "READY"
        assert asset.analysis_status == "COMPLETED"
        assert asset.review_status == "PENDING"
        assert asset.generated_text.startswith("A Rua das Flores")
        assert asset.confidence == 0.97
        assert asset.storage_key
        asset_id = asset.id

    assert _login(client).status_code == 200
    detail = client.get(f"/api/v1/tenants/{tenant_id}/conversations/{conversation_id}")
    assert detail.status_code == 200
    assert detail.json["midias"][0]["analise"]["status"] == "COMPLETED"
    reviewed = client.post(
        f"/api/v1/tenants/{tenant_id}/whatsapp/media/{asset_id}/review",
        json={"acao": "EDIT", "texto": "A Rua das Flores está totalmente sem iluminação."},
        headers=_csrf(client),
    )
    assert reviewed.status_code == 200
    assert reviewed.json["analise"]["statusRevisao"] == "EDITED"
