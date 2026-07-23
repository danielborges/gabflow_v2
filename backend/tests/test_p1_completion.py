from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import AuditLog, ServiceRequest, Tenant

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
    assert dashboard.json["porTerritorio"] == []
    assert dashboard.json["porCategoria"] == []
    assert dashboard.json["porCanal"] == []
    assert dashboard.json["porOrgao"] == []
    assert dashboard.json["porPeriodo"] == []
    assert dashboard.json["privacidadeAgregacao"]["minimoPorGrupo"] == 3
    assert dashboard.json["privacidadeAgregacao"]["gruposSuprimidos"] >= 1
    assert dashboard.json["filtros"]["opcoes"]["categorias"] == ["Infraestrutura"]
    assert dashboard.json["filtros"]["opcoes"]["orgaos"][0]["nome"] == "Secretaria de Obras"
    assert dashboard.json["territorial"]["geocodificadas"] == 0
    assert dashboard.json["territorial"]["semCoordenadas"] == 1
    metrics = dashboard.json["metricasOperacionais"]
    assert metrics["primeirasRespostasRegistradas"] == 1
    assert metrics["encaminhamentosRegistrados"] == 1
    assert metrics["tempoMedioPrimeiraRespostaHoras"] is not None
    assert metrics["tempoMedioPrimeiroEncaminhamentoHoras"] is not None
    report = client.get(
        "/api/v1/painel/relatorio-mensal",
        query_string={"ano": datetime.now(UTC).year, "mes": datetime.now(UTC).month},
    )
    assert report.status_code == 200
    assert report.json["periodo"]["rotulo"] == datetime.now(UTC).strftime("%m/%Y")
    assert report.json["resumo"]["solicitacoesRecebidas"] == 1
    assert report.json["resumo"]["encaminhadas"] == 1
    assert report.json["privacidadeAgregacao"]["minimoPorGrupo"] == 3
    assert report.json["indicadores"]["porCategoria"] == []
    assert report.json["evidencias"][0]["protocolo"] == created.json["protocolo"]
    assert {event["tipo"] for event in report.json["evidencias"][0]["eventos"]} >= {
        "encaminhamento",
        "resposta_orgao",
        "comunicacao_cidadao",
    }

    filtered = client.get(
        "/api/v1/painel/operacional",
        query_string={
            "categoria": "Infraestrutura",
            "canal": "WHATSAPP",
            "territorioId": territory.json["id"],
            "orgaoId": agency.json["id"],
            "granularidade": "mes",
        },
    )
    assert filtered.status_code == 200
    assert filtered.json["indicadores"]["total"] == 1
    assert filtered.json["filtros"]["selecionados"]["granularidade"] == "mes"
    assert filtered.json["porPeriodo"] == []

    empty = client.get(
        "/api/v1/painel/operacional",
        query_string={"canal": "EMAIL"},
    )
    assert empty.json["indicadores"]["total"] == 0

    geocoded = post(client, "/api/v1/painel/territorial/geocodificar", csrf, {})
    assert geocoded.status_code == 200
    assert geocoded.json["geocodificadas"] == 1
    assert geocoded.json["metodo"] == "LOCAL_APROXIMADO"

    territorial = client.get("/api/v1/painel/operacional").json["territorial"]
    assert territorial["geocodificadas"] == 1
    assert territorial["coberturaPercentual"] == 100
    assert territorial["pontos"] == []
    assert territorial["hotspots"] == []
    assert territorial["privacidade"]["pontosSuprimidos"] == 1
    assert territorial["metodo"] == "LOCAL_APROXIMADO"
    assert territorial["heatmap"] == []

    with app.app_context():
        item = db.session.execute(select(ServiceRequest)).scalar_one()
        assert item.latitude is not None
        assert item.longitude is not None
        assert item.impact == "ALTO"


def test_dashboard_detects_recurrent_and_anomalous_demands(client):
    _, csrf = login(client)
    territory = post(client, "/api/v1/admin/territorios", csrf, {"nome": "Benfica"})
    category = post(
        client,
        "/api/v1/admin/categorias",
        csrf,
        {"nome": "Mobilidade urbana", "slaHoras": 72},
    )

    for index in range(3):
        created = post(
            client,
            "/api/v1/solicitacoes",
            csrf,
            {
                "origem": "WHATSAPP",
                "titulo": f"Falta de ônibus recorrente {index + 1}",
                "descricao": "Moradores relatam falta de ônibus no bairro.",
                "categoriaId": category.json["id"],
                "territorioId": territory.json["id"],
                "latitude": -21.762,
                "longitude": -43.315,
            },
        )
        assert created.status_code == 201

    dashboard = client.get("/api/v1/painel/operacional")
    assert dashboard.json["porCategoria"][0] == {"nome": "Mobilidade urbana", "total": 3}
    assert dashboard.json["porCanal"][0] == {"nome": "WHATSAPP", "total": 3}
    assert dashboard.json["porTerritorio"][0] == {"nome": "Benfica", "total": 3}
    alerts = dashboard.json["alertasDemanda"]

    recurrence = alerts["reincidencias"][0]
    assert recurrence["categoria"] == "Mobilidade urbana"
    assert recurrence["territorio"] == "Benfica"
    assert recurrence["total"] == 3
    assert recurrence["abertas"] == 3
    assert "30 dias" in recurrence["regra"]
    assert len(recurrence["exemplos"]) == 3

    anomaly = alerts["crescimentosAnormais"][0]
    assert anomaly["categoria"] == "Mobilidade urbana"
    assert anomaly["territorio"] == "Benfica"
    assert anomaly["atual"] == 3
    assert anomaly["baseSemanal"] == 0
    assert anomaly["fatorCrescimento"] is None
    assert alerts["regras"]["reincidencia"]["minimoDemandas"] == 3


def test_tenant_jurisdiction_can_be_configured_and_feeds_dashboard(app, client, monkeypatch):
    _, csrf = login(client)
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-43.68, -21.82],
                        [-43.18, -21.82],
                        [-43.18, -21.52],
                        [-43.68, -21.52],
                        [-43.68, -21.82],
                    ]],
                },
                "properties": {"codarea": "3136702"},
            }
        ],
    }
    payload = {
        "tipoCasa": "CAMARA_MUNICIPAL",
        "nome": "Juiz de Fora/MG",
        "municipio": "Juiz de Fora",
        "uf": "MG",
        "codigoIbge": "3136702",
        "centro": {"latitude": -21.7619, "longitude": -43.3496},
        "limites": {
            "minLatitude": -21.92,
            "maxLatitude": -21.58,
            "minLongitude": -43.58,
            "maxLongitude": -43.17,
        },
    }

    locked = patch(client, "/api/v1/admin/jurisdicao", csrf, payload)
    assert locked.status_code == 403

    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        tenant.chamber_type = payload["tipoCasa"]
        tenant.jurisdiction_name = payload["nome"]
        tenant.jurisdiction_city = payload["municipio"]
        tenant.jurisdiction_state = payload["uf"]
        tenant.jurisdiction_ibge_code = payload["codigoIbge"]
        tenant.jurisdiction_center_latitude = payload["centro"]["latitude"]
        tenant.jurisdiction_center_longitude = payload["centro"]["longitude"]
        tenant.jurisdiction_bounds = payload["limites"]
        db.session.commit()

    current = client.get("/api/v1/admin/jurisdicao")
    assert current.status_code == 200
    assert current.json["nome"] == "Juiz de Fora/MG"
    assert current.json["uf"] == "MG"
    assert current.json["codigoIbge"] == "3136702"
    assert current.json["limites"]["minLatitude"] == -21.92

    monkeypatch.setattr("app.admin.routes._fetch_ibge_geojson", lambda scope, code: geojson)
    imported = post(
        client,
        "/api/v1/admin/jurisdicao/ibge",
        csrf,
        {"tipoCasa": "CAMARA_MUNICIPAL", "codigoIbge": "3136702"},
    )
    assert imported.status_code == 200
    assert imported.json["geojson"]["features"][0]["properties"]["codarea"] == "3136702"
    assert imported.json["limites"]["minLongitude"] == -43.68

    dashboard = client.get("/api/v1/painel/operacional")
    jurisdiction = dashboard.json["territorial"]["jurisdicao"]
    assert jurisdiction["nome"] == "Juiz de Fora/MG"
    assert jurisdiction["tipoCasa"] == "CAMARA_MUNICIPAL"
    assert jurisdiction["geojson"]["features"][0]["geometry"]["type"] == "Polygon"

    with app.app_context():
        actions = db.session.execute(select(AuditLog.action)).scalars().all()
        assert "tenant.jurisdiction.ibge_imported" in actions


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
