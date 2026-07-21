import json

from sqlalchemy import select

from app.extensions import db
from app.models import AuditLog, ConsentRecord, PrivacyRequest, RetentionPolicy

PASSWORD_A = "SenhaForte123!"  # noqa: S105
PASSWORD_B = "OutraSenha123!"  # noqa: S105


def login(client, tenant="gabinete-a", password=PASSWORD_A):
    email = "admin-b@teste.local" if tenant == "gabinete-b" else "admin@teste.local"
    client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    return client.get_cookie("csrf_access_token").value


def create_citizen(client, csrf, name="Ana Souza"):
    return client.post(
        "/api/v1/cidadaos",
        json={
            "nome": name,
            "baseLegal": "EXECUCAO_POLITICA_PUBLICA",
            "consentimentoContato": True,
            "consentimentoDivulgacao": False,
            "contatos": [{"tipo": "EMAIL", "valor": "ana@example.com"}],
        },
        headers={"X-CSRF-TOKEN": csrf},
    ).json


def test_consent_history_is_append_only_and_correction_is_audited(app, client):
    csrf = login(client)
    citizen = create_citizen(client, csrf)

    initial = client.get(f"/api/v1/cidadaos/{citizen['id']}/consentimentos")
    assert initial.status_code == 200
    assert len(initial.json["content"]) == 2

    revoked = client.post(
        f"/api/v1/cidadaos/{citizen['id']}/consentimentos",
        json={
            "finalidade": "CONTATO",
            "concedido": False,
            "origem": "SOLICITACAO_TITULAR",
            "evidencia": "Solicitação registrada no atendimento.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert revoked.status_code == 201
    assert revoked.json["concedido"] is False

    corrected = client.patch(
        f"/api/v1/cidadaos/{citizen['id']}",
        json={"nome": "Ana Souza Lima"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert corrected.status_code == 200

    with app.app_context():
        assert len(db.session.execute(select(ConsentRecord)).scalars().all()) == 3
        actions = {
            item.action for item in db.session.execute(select(AuditLog)).scalars()
        }
        assert "citizen.consent.recorded" in actions
        assert "citizen.corrected" in actions


def test_access_request_requires_identity_and_exports_tenant_data(app, client):
    csrf = login(client)
    citizen = create_citizen(client, csrf)
    service_request = client.post(
        "/api/v1/solicitacoes",
        json={
            "origem": "EMAIL",
            "descricao": "Pedido relacionado ao titular.",
            "cidadaoId": citizen["id"],
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert service_request.status_code == 201

    privacy_request = client.post(
        "/api/v1/privacidade/solicitacoes",
        json={
            "cidadaoId": citizen["id"],
            "tipo": "ACESSO",
            "detalhes": "Titular solicitou cópia dos dados.",
            "identidadeValidada": False,
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert privacy_request.status_code == 201

    blocked = client.post(
        f"/api/v1/privacidade/solicitacoes/{privacy_request.json['id']}/exportar",
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert blocked.status_code == 422

    validated = client.patch(
        f"/api/v1/privacidade/solicitacoes/{privacy_request.json['id']}",
        json={"identidadeValidada": True, "status": "EM_ANALISE"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert validated.status_code == 200

    exported = client.post(
        f"/api/v1/privacidade/solicitacoes/{privacy_request.json['id']}/exportar",
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert exported.status_code == 200
    package = json.loads(exported.data)
    assert package["titular"]["nome"] == "Ana Souza"
    assert package["solicitacoes"][0]["protocolo"] == service_request.json["protocolo"]
    assert "attachment" in exported.headers["Content-Disposition"]

    completed = client.patch(
        f"/api/v1/privacidade/solicitacoes/{privacy_request.json['id']}",
        json={"status": "CONCLUIDA", "resolucao": "Pacote entregue ao titular."},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert completed.status_code == 200
    assert completed.json["status"] == "CONCLUIDA"

    with app.app_context():
        assert db.session.execute(select(PrivacyRequest)).scalar_one().completed_at
        assert db.session.execute(
            select(AuditLog).where(AuditLog.action == "privacy_request.exported")
        ).scalar_one()


def test_privacy_requests_and_audit_are_tenant_scoped(client):
    csrf = login(client)
    citizen = create_citizen(client, csrf)
    created = client.post(
        "/api/v1/privacidade/solicitacoes",
        json={
            "cidadaoId": citizen["id"],
            "tipo": "CORRECAO",
            "detalhes": "Correção de contato.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert created.status_code == 201

    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": csrf})
    login(client, "gabinete-b", PASSWORD_B)
    assert client.get("/api/v1/privacidade/solicitacoes").json["content"] == []
    audit = client.get("/api/v1/auditoria")
    assert all(item["entidadeId"] != citizen["id"] for item in audit.json["content"])


def test_retention_policy_is_configurable_and_audited(app, client):
    csrf = login(client)
    saved = client.put(
        "/api/v1/privacidade/retencao",
        json={
            "tipoDado": "CIDADAO",
            "retencaoDias": 1825,
            "acao": "ANONIMIZAR",
            "ativa": True,
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert saved.status_code == 200
    assert saved.json["retencaoDias"] == 1825
    assert client.get("/api/v1/privacidade/retencao").json["content"][0]["ativa"]

    with app.app_context():
        assert db.session.execute(select(RetentionPolicy)).scalar_one().action.value == "ANONIMIZAR"
        assert db.session.execute(
            select(AuditLog).where(AuditLog.action == "retention_policy.saved")
        ).scalar_one()
