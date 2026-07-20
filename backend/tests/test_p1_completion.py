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
    public_response = post(
        client,
        f"/api/v1/solicitacoes/{created.json['id']}/interacoes",
        csrf,
        {
            "tipo": "RESPOSTA_CIDADAO",
            "canal": "WHATSAPP",
            "direcao": "SAIDA",
            "visibilidade": "CIDADAO",
            "conteudo": "Recebemos sua demanda e vamos acompanhar o reparo.",
        },
    )
    assert public_response.status_code == 201

    dashboard = client.get("/api/v1/painel/operacional")
    assert dashboard.status_code == 200
    assert dashboard.json["indicadores"]["total"] == 1
    assert dashboard.json["porTerritorio"][0] == {"nome": "Centro", "total": 1}
    assert dashboard.json["territorial"]["geocodificadas"] == 0
    assert dashboard.json["territorial"]["semCoordenadas"] == 1
    metrics = dashboard.json["metricasOperacionais"]
    assert metrics["primeirasRespostasRegistradas"] == 1
    assert metrics["encaminhamentosRegistrados"] == 1
    assert metrics["tempoMedioPrimeiraRespostaHoras"] is not None
    assert metrics["tempoMedioPrimeiroEncaminhamentoHoras"] is not None

    geocoded = post(client, "/api/v1/painel/territorial/geocodificar", csrf, {})
    assert geocoded.status_code == 200
    assert geocoded.json["geocodificadas"] == 1
    assert geocoded.json["metodo"] == "LOCAL_APROXIMADO"

    territorial = client.get("/api/v1/painel/operacional").json["territorial"]
    assert territorial["geocodificadas"] == 1
    assert territorial["coberturaPercentual"] == 100
    assert territorial["pontos"][0]["protocolo"] == created.json["protocolo"]
    assert territorial["pontos"][0]["territorio"] == "Centro"
    assert territorial["hotspots"][0]["nome"] == "Centro"
    assert territorial["metodo"] == "LOCAL_APROXIMADO"
    assert territorial["heatmap"][0]["territorio"] == "Centro"

    with app.app_context():
        item = db.session.execute(select(ServiceRequest)).scalar_one()
        assert item.latitude is not None
        assert item.longitude is not None
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
    closed_dashboard = client.get("/api/v1/painel/operacional")
    closed_metrics = closed_dashboard.json["metricasOperacionais"]
    assert closed_metrics["encerramentosRegistrados"] == 1
    assert closed_metrics["tempoMedioEncerramentoHoras"] is not None
    reopened = post(
        client,
        f"/api/v1/solicitacoes/{created['id']}/reabrir",
        csrf,
        {"motivo": "Chegaram novas informações."},
    )
    assert reopened.json["status"] == "EM_ATENDIMENTO"
    reopened_metrics = client.get("/api/v1/painel/operacional").json["metricasOperacionais"]
    assert reopened_metrics["reaberturas"] == 1
    assert reopened_metrics["encerramentosRegistrados"] == 1

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
