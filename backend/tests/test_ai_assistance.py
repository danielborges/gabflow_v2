import uuid

from sqlalchemy import select

from app.extensions import db
from app.models import AIExecution, AuditLog, RequestInteraction
from app.outbox.service import process_batch

PASSWORD = "SenhaForte123!"  # noqa: S105


def _login(client):
    client.post(
        "/api/v1/auth/login",
        json={
            "tenant": "gabinete-a",
            "email": "admin@teste.local",
            "password": PASSWORD,
        },
    )
    return client.get_cookie("csrf_access_token").value


def _request(client, csrf):
    response = client.post(
        "/api/v1/solicitacoes",
        json={
            "origem": "WHATSAPP",
            "titulo": "Falta de vacinas no centro médico",
            "descricao": "O centro médico está sem vacinas e há crianças aguardando.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert response.status_code == 201
    return response.json


def test_assistance_generates_all_suggestions_without_sending(app, client):
    csrf = _login(client)
    service_request = _request(client, csrf)

    requested = client.post(
        f"/api/v1/solicitacoes/{service_request['id']}/assistencia-ia",
        json={"canal": "EMAIL", "tom": "ACOLHEDOR"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert requested.status_code == 202
    assert requested.json["status"] == "PENDENTE"
    assert requested.json["resultado"]["envioAutomatico"] is False

    with app.app_context():
        result = process_batch("assistance-worker")
        assert result.succeeded >= 2

    details = client.get(f"/api/v1/solicitacoes/{service_request['id']}").json
    assistance = details["assistenciaIA"]
    output = assistance["resultado"]
    assert assistance["status"] == "CONCLUIDA"
    assert output["resumoHistorico"]
    assert output["perguntasFaltantes"]
    assert output["documentosNecessarios"]
    assert output["proximosPassos"]
    assert output["respostaSugerida"]["canal"] == "EMAIL"
    assert output["respostaSugerida"]["assunto"]
    assert output["revisaoHumanaObrigatoria"] is True
    assert output["envioAutomatico"] is False
    assert output["guardrailsAplicados"]
    assert all(output["guardrailsAplicados"])

    with app.app_context():
        assert db.session.execute(select(RequestInteraction)).scalars().all() == []


def test_using_edited_draft_is_audited_but_does_not_send(app, client):
    csrf = _login(client)
    service_request = _request(client, csrf)
    client.post(
        f"/api/v1/solicitacoes/{service_request['id']}/assistencia-ia",
        json={"canal": "WHATSAPP", "tom": "OBJETIVO"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    with app.app_context():
        process_batch("assistance-review-worker")
    assistance = client.get(f"/api/v1/solicitacoes/{service_request['id']}").json["assistenciaIA"]

    reviewed = client.post(
        f"/api/v1/assistencias-ia/{assistance['id']}/revisao",
        json={
            "acao": "EDITAR",
            "valores": {
                "canal": "WHATSAPP",
                "conteudo": "Texto revisado pelo atendente.",
            },
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert reviewed.status_code == 200
    assert reviewed.json["statusRevisao"] == "EDITADA"
    assert reviewed.json["resultado"]["revisao"]["enviada"] is False
    assert reviewed.json["resultado"]["respostaSugerida"]["conteudo"] == (
        "Texto revisado pelo atendente."
    )

    with app.app_context():
        execution = db.session.execute(
            select(AIExecution).where(AIExecution.id == uuid.UUID(assistance["id"]))
        ).scalar_one()
        assert execution.output["envioAutomatico"] is False
        assert db.session.execute(select(RequestInteraction)).scalars().all() == []
        assert db.session.execute(
            select(AuditLog).where(AuditLog.action == "request.ai_assistance.editada")
        ).scalar_one()


def test_assistance_validates_channel_and_tone(client):
    csrf = _login(client)
    service_request = _request(client, csrf)
    response = client.post(
        f"/api/v1/solicitacoes/{service_request['id']}/assistencia-ia",
        json={"canal": "FAX", "tom": "CRIATIVO"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert response.status_code == 422
