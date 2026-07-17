import uuid

from sqlalchemy import select

from app.ai.provider import AIProviderUnavailable
from app.extensions import db
from app.models import AIExecution, AuditLog, RequestCategory, ServiceRequest
from app.outbox.service import process_batch

PASSWORD = "SenhaForte123!"  # noqa: S105


def login(client):
    client.post(
        "/api/v1/auth/login",
        json={
            "tenant": "gabinete-a",
            "email": "admin@teste.local",
            "password": PASSWORD,
        },
    )
    return client.get_cookie("csrf_access_token").value


def create_request(client, csrf, description):
    response = client.post(
        "/api/v1/solicitacoes",
        json={
            "origem": "WHATSAPP",
            "titulo": "Problema relatado",
            "descricao": description,
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert response.status_code == 201
    return response.json


def seed_categories(client, csrf):
    for name, sla_hours in (("Iluminação pública", 72), ("Saúde", 24)):
        response = client.post(
            "/api/v1/admin/categorias",
            json={"nome": name, "slaHoras": sla_hours},
            headers={"X-CSRF-TOKEN": csrf},
        )
        assert response.status_code == 201


def test_ai_triage_is_async_and_requires_human_acceptance(app, client):
    csrf = login(client)
    seed_categories(client, csrf)
    service_request = create_request(
        client,
        csrf,
        "Três postes estão apagados na Rua das Flores e a via está muito escura.",
    )

    requested = client.post(
        f"/api/v1/solicitacoes/{service_request['id']}/classificacao-ia",
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert requested.status_code == 202
    assert requested.json["status"] == "PENDENTE"
    assert requested.json["modelo"] == "gabflow-triage-rules-v1"
    assert requested.json["versaoPrompt"] == "triage-v1"

    with app.app_context():
        result = process_batch("ai-test-worker")
        assert result.succeeded == 2

    details = client.get(f"/api/v1/solicitacoes/{service_request['id']}")
    triage = details.json["triagemIA"]
    assert triage["status"] == "CONCLUIDA"
    assert triage["statusRevisao"] == "PENDENTE"
    assert triage["confianca"] > 0.5
    assert triage["resultado"]["categoria"] == "Iluminação pública"
    assert triage["resultado"]["revisaoHumanaObrigatoria"] is True

    reviewed = client.post(
        f"/api/v1/classificacoes-ia/{triage['id']}/revisao",
        json={"acao": "ACEITAR"},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert reviewed.status_code == 200
    assert reviewed.json["statusRevisao"] == "ACEITA"
    updated = client.get(f"/api/v1/solicitacoes/{service_request['id']}").json
    assert updated["categoria"] == "Iluminação pública"
    assert updated["prioridade"] == "MEDIA"

    with app.app_context():
        execution = db.session.execute(select(AIExecution)).scalar_one()
        assert execution.reviewed_at is not None
        assert db.session.execute(
            select(AuditLog).where(AuditLog.action == "request.ai_triage.aceita")
        ).scalar_one()


def test_ai_triage_can_be_edited_or_rejected_without_automatic_decision(app, client):
    csrf = login(client)
    seed_categories(client, csrf)
    first = create_request(client, csrf, "A comunidade solicita atendimento no bairro.")
    client.post(
        f"/api/v1/solicitacoes/{first['id']}/classificacao-ia",
        headers={"X-CSRF-TOKEN": csrf},
    )
    with app.app_context():
        process_batch("ai-test-worker")
        health_category = db.session.execute(
            select(RequestCategory).where(RequestCategory.name == "Saúde")
        ).scalar_one()
        health_category_id = str(health_category.id)

    triage = client.get(f"/api/v1/solicitacoes/{first['id']}").json["triagemIA"]
    edited = client.post(
        f"/api/v1/classificacoes-ia/{triage['id']}/revisao",
        json={
            "acao": "EDITAR",
            "valores": {
                "categoriaId": health_category_id,
                "subcategoria": "Atendimento básico",
                "prioridadeSugerida": "ALTA",
                "impacto": "ALTO",
                "urgencia": "ALTO",
            },
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert edited.status_code == 200
    assert edited.json["statusRevisao"] == "EDITADA"
    updated = client.get(f"/api/v1/solicitacoes/{first['id']}").json
    assert updated["categoria"] == "Saúde"
    assert updated["subcategoria"] == "Atendimento básico"
    assert updated["prioridade"] == "ALTA"

    second = create_request(client, csrf, "Pedido genérico sem dados suficientes.")
    client.post(
        f"/api/v1/solicitacoes/{second['id']}/classificacao-ia",
        headers={"X-CSRF-TOKEN": csrf},
    )
    with app.app_context():
        process_batch("ai-test-worker")
    rejected_triage = client.get(f"/api/v1/solicitacoes/{second['id']}").json["triagemIA"]
    rejected = client.post(
        f"/api/v1/classificacoes-ia/{rejected_triage['id']}/revisao",
        json={"acao": "REJEITAR"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert rejected.status_code == 200
    assert rejected.json["statusRevisao"] == "REJEITADA"
    unchanged = client.get(f"/api/v1/solicitacoes/{second['id']}").json
    assert unchanged["categoriaId"] is None


def test_ai_triage_flags_possible_emergency(app, client):
    csrf = login(client)
    seed_categories(client, csrf)
    service_request = create_request(
        client,
        csrf,
        "Há uma pessoa inconsciente com risco de vida na Avenida Central.",
    )
    client.post(
        f"/api/v1/solicitacoes/{service_request['id']}/classificacao-ia",
        headers={"X-CSRF-TOKEN": csrf},
    )
    with app.app_context():
        process_batch("ai-test-worker")

    triage = client.get(f"/api/v1/solicitacoes/{service_request['id']}").json["triagemIA"]
    assert triage["resultado"]["emergencia"] is True
    assert triage["resultado"]["prioridadeSugerida"] == "CRITICA"
    assert "não substitui" in triage["resultado"]["orientacaoEmergencia"]

    with app.app_context():
        stored_request = db.session.get(ServiceRequest, uuid.UUID(service_request["id"]))
        assert stored_request.priority.value == "MEDIA"


def test_ai_provider_failure_does_not_block_request_creation(app, client, monkeypatch):
    csrf = login(client)
    seed_categories(client, csrf)
    service_request = create_request(
        client,
        csrf,
        "Relato disponível para classificação manual.",
    )

    def fail_provider(_execution):
        raise RuntimeError("Provedor indisponível.")

    monkeypatch.setattr("app.outbox.handlers.execute_triage", fail_provider)
    with app.app_context():
        app.config["WORKER_MAX_ATTEMPTS"] = 1
        result = process_batch("ai-failure-worker")
        assert result.failed == 1

    details = client.get(f"/api/v1/solicitacoes/{service_request['id']}").json
    assert details["triagemIA"]["status"] == "FALHOU"
    assert details["categoriaId"] is None


def test_ollama_failure_uses_configured_local_fallback(app, client, monkeypatch):
    csrf = login(client)
    seed_categories(client, csrf)
    service_request = create_request(
        client,
        csrf,
        "Poste apagado na Rua das Flores.",
    )

    def unavailable(*_args, **_kwargs):
        raise AIProviderUnavailable("Ollama não deveria chamar a rede neste teste.")

    monkeypatch.setattr("app.ai.provider.OllamaTriageProvider._request", unavailable)
    with app.app_context():
        app.config.update(
            AI_TRIAGE_PROVIDER="ollama",
            AI_TRIAGE_MODEL="qwen2.5:3b",
            AI_TRIAGE_FALLBACK_ENABLED=True,
        )
        result = process_batch("ollama-fallback-worker")
        assert result.succeeded == 2

    triage = client.get(f"/api/v1/solicitacoes/{service_request['id']}").json["triagemIA"]
    assert triage["status"] == "CONCLUIDA"
    assert triage["provedor"] == "LOCAL_FALLBACK"
    assert triage["resultado"]["fallbackUtilizado"] is True
