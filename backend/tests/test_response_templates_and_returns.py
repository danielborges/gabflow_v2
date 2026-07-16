from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.communications.email import EmailDelivery, EmailDeliveryError
from app.extensions import db
from app.models import (
    AuditLog,
    ContactAttempt,
    Notification,
    RequestInteraction,
    ScheduledReturn,
)

PASSWORD = "SenhaForte123!"  # noqa: S105


def login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"tenant": "gabinete-a", "email": "admin@teste.local", "password": PASSWORD},
    )
    return response.json["user"], client.get_cookie("csrf_access_token").value


def create_request_with_citizen(client, csrf):
    citizen = client.post(
        "/api/v1/cidadaos",
        json={"nome": "Ana Souza", "baseLegal": "EXECUCAO_POLITICA_PUBLICA"},
        headers={"X-CSRF-TOKEN": csrf},
    ).json
    return client.post(
        "/api/v1/solicitacoes",
        json={
            "origem": "WHATSAPP",
            "titulo": "Pedido de informação",
            "descricao": "Acompanhamento solicitado.",
            "cidadaoId": citizen["id"],
        },
        headers={"X-CSRF-TOKEN": csrf},
    ).json


def test_template_preview_and_edited_response_are_audited(app, client):
    _, csrf = login(client)
    service_request = create_request_with_citizen(client, csrf)

    invalid = client.post(
        "/api/v1/admin/templates-resposta",
        json={
            "nome": "Template inseguro",
            "canal": "WHATSAPP",
            "conteudo": "Use {{senha}}.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert invalid.status_code == 422
    assert "senha" in invalid.json["message"]

    created = client.post(
        "/api/v1/admin/templates-resposta",
        json={
            "nome": "Atualização ao cidadão",
            "canal": "WHATSAPP",
            "conteudo": "Olá, {{cidadao}}. {{protocolo}} está {{status}}.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert created.status_code == 201

    preview = client.post(
        f"/api/v1/solicitacoes/{service_request['id']}/respostas/preview",
        json={"templateId": created.json["id"]},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert preview.status_code == 200
    assert "Ana Souza" in preview.json["conteudo"]
    assert service_request["protocolo"] in preview.json["conteudo"]

    sent = client.post(
        f"/api/v1/solicitacoes/{service_request['id']}/respostas",
        json={
            "templateId": created.json["id"],
            "canal": "WHATSAPP",
            "conteudo": f"{preview.json['conteudo']} Retornaremos em breve.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert sent.status_code == 201

    detail = client.get(f"/api/v1/solicitacoes/{service_request['id']}")
    interaction = detail.json["interacoes"][-1]
    assert interaction["direcao"] == "SAIDA"
    assert interaction["visibilidade"] == "CIDADAO"
    assert interaction["conteudo"].endswith("Retornaremos em breve.")

    with app.app_context():
        interactions = db.session.execute(select(RequestInteraction)).scalars().all()
        assert interactions[-1].channel == "WHATSAPP"
        assert db.session.execute(
            select(AuditLog).where(AuditLog.action == "request.response.sent")
        ).scalar_one()


def test_scheduled_return_lifecycle_and_idempotent_reminder(app, client):
    user, csrf = login(client)
    service_request = create_request_with_citizen(client, csrf)
    scheduled_at = datetime.now(UTC) + timedelta(minutes=30)

    created = client.post(
        f"/api/v1/solicitacoes/{service_request['id']}/retornos",
        json={
            "agendadoPara": scheduled_at.isoformat(),
            "responsavelId": user["id"],
            "observacoes": "Confirmar resposta.",
            "lembreteHabilitado": True,
            "lembreteMinutos": 60,
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert created.status_code == 201
    assert created.json["status"] == "AGENDADO"

    first_notifications = client.get("/api/v1/notificacoes")
    second_notifications = client.get("/api/v1/notificacoes")
    assert first_notifications.json["naoLidas"] == 1
    assert second_notifications.json["naoLidas"] == 1
    assert first_notifications.json["content"][0]["tipo"] == "RETORNO"

    rescheduled_at = datetime.now(UTC) + timedelta(days=2)
    rescheduled = client.patch(
        f"/api/v1/retornos/{created.json['id']}",
        json={"agendadoPara": rescheduled_at.isoformat(), "lembreteMinutos": 120},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert rescheduled.status_code == 200
    assert rescheduled.json["status"] == "AGENDADO"
    assert rescheduled.json["lembreteEnviadoEm"] is None

    completed = client.patch(
        f"/api/v1/retornos/{created.json['id']}",
        json={"status": "CONCLUIDO"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert completed.status_code == 200
    assert completed.json["concluidoEm"] is not None

    dashboard = client.get("/api/v1/painel/operacional")
    assert dashboard.json["indicadores"]["retornosVencidos"] == 0
    assert dashboard.json["indicadores"]["retornosProximos"] == 0

    with app.app_context():
        assert len(db.session.execute(select(Notification)).scalars().all()) == 1
        assert db.session.execute(select(ScheduledReturn)).scalar_one().status.value == "CONCLUIDO"
        actions = {
            item.action
            for item in db.session.execute(
                select(AuditLog).where(AuditLog.entity_type == "scheduled_return")
            ).scalars()
        }
        assert "request.return.scheduled" in actions
        assert "request.return.rescheduled" in actions
        assert "request.return.concluido" in actions


def test_email_response_uses_resend_and_records_delivery(app, client, monkeypatch):
    _, csrf = login(client)
    citizen = client.post(
        "/api/v1/cidadaos",
        json={
            "nome": "Joana Lima",
            "baseLegal": "EXECUCAO_POLITICA_PUBLICA",
            "contatos": [{"tipo": "EMAIL", "valor": "joana@example.com"}],
        },
        headers={"X-CSRF-TOKEN": csrf},
    ).json
    service_request = client.post(
        "/api/v1/solicitacoes",
        json={
            "origem": "EMAIL",
            "descricao": "Solicitação recebida por e-mail.",
            "cidadaoId": citizen["id"],
        },
        headers={"X-CSRF-TOKEN": csrf},
    ).json
    sent = {}

    def fake_send_email(**values):
        sent.update(values)
        return EmailDelivery(provider="RESEND", message_id="email_123")

    monkeypatch.setattr("app.communications.routes.send_email", fake_send_email)
    response = client.post(
        f"/api/v1/solicitacoes/{service_request['id']}/respostas",
        json={
            "canal": "EMAIL",
            "assunto": "Atualização do atendimento",
            "conteudo": "Sua solicitação está em atendimento.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert response.status_code == 201
    assert response.json["provedor"] == "RESEND"
    assert response.json["mensagemExternaId"] == "email_123"
    assert sent["recipient"] == "joana@example.com"
    assert sent["subject"] == "Atualização do atendimento"

    with app.app_context():
        attempt = db.session.execute(select(ContactAttempt)).scalar_one()
        assert attempt.outcome.value == "REALIZADO"
        assert "email_123" in attempt.notes


def test_email_provider_failure_is_preserved_without_outgoing_interaction(
    app, client, monkeypatch
):
    _, csrf = login(client)
    citizen = client.post(
        "/api/v1/cidadaos",
        json={
            "nome": "Joana Lima",
            "baseLegal": "EXECUCAO_POLITICA_PUBLICA",
            "contatos": [{"tipo": "EMAIL", "valor": "joana@example.com"}],
        },
        headers={"X-CSRF-TOKEN": csrf},
    ).json
    service_request = client.post(
        "/api/v1/solicitacoes",
        json={
            "origem": "EMAIL",
            "descricao": "Solicitação recebida por e-mail.",
            "cidadaoId": citizen["id"],
        },
        headers={"X-CSRF-TOKEN": csrf},
    ).json

    def fail_send_email(**_values):
        raise EmailDeliveryError("O provedor recusou o envio do e-mail.")

    monkeypatch.setattr("app.communications.routes.send_email", fail_send_email)
    response = client.post(
        f"/api/v1/solicitacoes/{service_request['id']}/respostas",
        json={
            "canal": "EMAIL",
            "assunto": "Atualização do atendimento",
            "conteudo": "Mensagem não entregue.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert response.status_code == 502
    with app.app_context():
        attempt = db.session.execute(select(ContactAttempt)).scalar_one()
        assert attempt.outcome.value == "FALHOU"
        assert db.session.execute(select(RequestInteraction)).scalars().all() == []
        assert db.session.execute(
            select(AuditLog).where(AuditLog.action == "request.response.failed")
        ).scalar_one()
