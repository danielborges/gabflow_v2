from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import ContactAttempt, Notification, NotificationPreference

PASSWORD_A = "SenhaForte123!"  # noqa: S105
PASSWORD_B = "OutraSenha123!"  # noqa: S105


def login(client, tenant="gabinete-a", password=PASSWORD_A):
    response = client.post(
        "/api/v1/auth/login",
        json={"tenant": tenant, "email": "admin@teste.local", "password": password},
    )
    return response.json["user"], client.get_cookie("csrf_access_token").value


def test_notification_preferences_disable_selected_events(app, client):
    user, csrf = login(client)
    preferences = client.get("/api/v1/notificacoes/preferencias")
    assert preferences.status_code == 200
    assert all(item["habilitada"] for item in preferences.json["content"])

    updated = client.put(
        "/api/v1/notificacoes/preferencias",
        json={"preferencias": [{"tipo": "ATRIBUICAO", "habilitada": False}]},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert updated.status_code == 200

    created = client.post(
        "/api/v1/solicitacoes",
        json={
            "origem": "EMAIL",
            "descricao": "Demanda atribuída sem alerta.",
            "responsavelId": user["id"],
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert created.status_code == 201
    assert client.get("/api/v1/notificacoes").json["naoLidas"] == 0

    with app.app_context():
        assert db.session.execute(select(NotificationPreference)).scalar_one().enabled is False
        assert db.session.execute(select(Notification)).scalars().all() == []


def test_contact_attempt_uses_preferred_channel_and_requires_override(app, client):
    _, csrf = login(client)
    citizen = client.post(
        "/api/v1/cidadaos",
        json={
            "nome": "Ana Souza",
            "baseLegal": "EXECUCAO_POLITICA_PUBLICA",
            "canalPreferencial": "WHATSAPP",
            "contatos": [{"tipo": "WHATSAPP", "valor": "32999990000"}],
        },
        headers={"X-CSRF-TOKEN": csrf},
    ).json
    service_request = client.post(
        "/api/v1/solicitacoes",
        json={
            "origem": "PRESENCIAL",
            "descricao": "Solicitação com retorno ao cidadão.",
            "cidadaoId": citizen["id"],
        },
        headers={"X-CSRF-TOKEN": csrf},
    ).json

    next_attempt = datetime.now(UTC) + timedelta(days=1)
    attempt = client.post(
        f"/api/v1/solicitacoes/{service_request['id']}/tentativas-contato",
        json={
            "resultado": "AGENDADO",
            "proximaTentativaEm": next_attempt.isoformat(),
            "observacoes": "Mensagem enviada; aguardando retorno.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert attempt.status_code == 201
    assert attempt.json["canal"] == "WHATSAPP"
    assert attempt.json["destino"] == "32999990000"

    rejected = client.post(
        f"/api/v1/solicitacoes/{service_request['id']}/tentativas-contato",
        json={
            "canal": "EMAIL",
            "destino": "ana@example.org",
            "resultado": "REALIZADO",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert rejected.status_code == 422
    assert "justificativa" in rejected.json["message"]

    accepted = client.post(
        f"/api/v1/solicitacoes/{service_request['id']}/tentativas-contato",
        json={
            "canal": "EMAIL",
            "destino": "ana@example.org",
            "resultado": "REALIZADO",
            "justificativaCanal": "Cidadã solicitou resposta excepcional por e-mail.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert accepted.status_code == 201

    detail = client.get(f"/api/v1/solicitacoes/{service_request['id']}")
    assert detail.json["status"] == "AGUARDANDO_CIDADAO"
    assert len(detail.json["tentativasContato"]) == 2
    assert any(item["tipo"] == "TENTATIVA_CONTATO" for item in detail.json["interacoes"])

    with app.app_context():
        assert len(db.session.execute(select(ContactAttempt)).scalars().all()) == 2

    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": csrf})
    _, other_csrf = login(client, "gabinete-b", PASSWORD_B)
    hidden = client.post(
        f"/api/v1/solicitacoes/{service_request['id']}/tentativas-contato",
        json={"canal": "TELEFONE", "destino": "123", "resultado": "FALHOU"},
        headers={"X-CSRF-TOKEN": other_csrf},
    )
    assert hidden.status_code == 404
