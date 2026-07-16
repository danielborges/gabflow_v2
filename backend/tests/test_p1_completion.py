from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import AuditLog, ServiceRequest

PASSWORD = "SenhaForte123!"  # noqa: S105


def login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"tenant": "gabinete-a", "email": "admin@teste.local", "password": PASSWORD},
    )
    return response.json["user"], client.get_cookie("csrf_access_token").value


def post(client, path, csrf, payload):
    return client.post(path, json=payload, headers={"X-CSRF-TOKEN": csrf})


def patch(client, path, csrf, payload):
    return client.patch(path, json=payload, headers={"X-CSRF-TOKEN": csrf})


def test_classification_forwarding_response_and_dashboard(app, client):
    user, csrf = login(client)
    territory = post(client, "/api/v1/admin/territorios", csrf, {"nome": "Centro"})
    agency = post(
        client,
        "/api/v1/admin/orgaos",
        csrf,
        {"nome": "Secretaria de Obras", "emailContato": "obras@example.org"},
    )
    category = post(
        client,
        "/api/v1/admin/categorias",
        csrf,
        {"nome": "Infraestrutura", "slaHoras": 48},
    )
    created = post(
        client,
        "/api/v1/solicitacoes",
        csrf,
        {
            "origem": "WHATSAPP",
            "titulo": "Buraco na via",
            "descricao": "Buraco com risco para veículos.",
            "categoriaId": category.json["id"],
            "subcategoria": "Pavimentação",
            "tema": "Vias públicas",
            "territorioId": territory.json["id"],
            "orgaoId": agency.json["id"],
            "impacto": "ALTO",
            "urgencia": "CRITICO",
            "responsavelId": user["id"],
        },
    )
    assert created.status_code == 201
    assert created.json["territorioId"] == territory.json["id"]
    assert created.json["chaveAcompanhamento"]

    forwarded = post(
        client,
        f"/api/v1/solicitacoes/{created.json['id']}/encaminhamentos",
        csrf,
        {
            "orgaoId": agency.json["id"],
            "protocoloExterno": "OBRAS-123",
            "prazo": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
        },
    )
    assert forwarded.status_code == 201
    assert forwarded.json["status"] == "AGUARDANDO_RETORNO"

    answered = patch(
        client,
        f"/api/v1/encaminhamentos/{forwarded.json['id']}",
        csrf,
        {"resposta": "Equipe programada para o reparo."},
    )
    assert answered.json["status"] == "RESPONDIDO"
    detail = client.get(f"/api/v1/solicitacoes/{created.json['id']}")
    assert detail.json["interacoes"][0]["tipo"] == "RESPOSTA_ORGAO"

    dashboard = client.get("/api/v1/painel/operacional")
    assert dashboard.status_code == 200
    assert dashboard.json["indicadores"]["total"] == 1
    assert dashboard.json["porTerritorio"][0] == {"nome": "Centro", "total": 1}

    with app.app_context():
        item = db.session.execute(select(ServiceRequest)).scalar_one()
        assert item.impact == "ALTO"


def test_public_lookup_reopen_and_key_rotation_are_safe(app, client):
    _, csrf = login(client)
    created = post(
        client,
        "/api/v1/solicitacoes",
        csrf,
        {
            "origem": "EMAIL",
            "titulo": "Consulta pública",
            "descricao": "Demanda para acompanhamento.",
        },
    ).json
    public = client.get(
        f"/api/v1/publico/solicitacoes/{created['protocolo']}",
        query_string={"chave": created["chaveAcompanhamento"]},
    )
    assert public.status_code == 200
    assert "descricao" not in public.json
    assert (
        client.get(
            f"/api/v1/publico/solicitacoes/{created['protocolo']}",
            query_string={"chave": "incorreta"},
        ).status_code
        == 403
    )

    closed = patch(
        client,
        f"/api/v1/solicitacoes/{created['id']}",
        csrf,
        {
            "status": "ENCERRADA",
            "motivoEncerramento": "Atendimento concluído.",
        },
    )
    assert closed.status_code == 200
    reopened = post(
        client,
        f"/api/v1/solicitacoes/{created['id']}/reabrir",
        csrf,
        {"motivo": "Chegaram novas informações."},
    )
    assert reopened.json["status"] == "EM_ATENDIMENTO"

    rotated = post(
        client,
        f"/api/v1/solicitacoes/{created['id']}/chave-publica",
        csrf,
        {},
    )
    assert rotated.status_code == 200
    assert rotated.json["chave"] != created["chaveAcompanhamento"]
    assert (
        client.get(
            f"/api/v1/publico/solicitacoes/{created['protocolo']}",
            query_string={"chave": created["chaveAcompanhamento"]},
        ).status_code
        == 403
    )

    with app.app_context():
        assert db.session.execute(
            select(AuditLog).where(AuditLog.action == "request.reopened")
        ).scalar_one()
