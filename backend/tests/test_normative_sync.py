from app.legislative.normative_sync import ExternalNormativeRecord

PASSWORD = "SenhaForte123!"  # noqa: S105


def _login(client, email="admin@teste.local", password=PASSWORD):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return client.get_cookie("csrf_access_token").value


def _post(client, path, csrf, payload=None):
    return client.post(path, json=payload or {}, headers={"X-CSRF-TOKEN": csrf})


def test_external_norms_enter_review_before_becoming_active(app, client, monkeypatch):
    csrf = _login(client)
    connector = _post(
        client,
        "/api/v1/legislativo/fontes-normativas/integracoes",
        csrf,
        {
            "provedor": "LEXML",
            "nome": "LexML municipal",
            "consulta": "urn.lex.localidade Campinas",
            "jurisdicao": "Campinas - SP",
            "frequenciaHoras": 24,
        },
    )
    assert connector.status_code == 201
    assert connector.json["ultimoStatus"] == "NUNCA_EXECUTADA"

    records = [
        ExternalNormativeRecord(
                external_id="urn:lex:br;sao.paulo;campinas:municipal:lei:2026-01-10;1234",
                source_type="LEI_MUNICIPAL",
                title="Lei Municipal nº 1.234, de 10 de janeiro de 2026",
                reference="Lei Municipal nº 1.234/2026",
                excerpt=(
                    "Dispõe sobre a iluminação e a conservação das praças e vias públicas "
                    "no Município de Campinas."
                ),
                jurisdiction="Campinas - SP",
                source_url="https://www.lexml.gov.br/urn/lei-1234",
                version="2026-01-10",
        )
    ]
    monkeypatch.setattr(
        "app.legislative.normative_sync._fetch_records", lambda _connector: records
    )
    synchronized = _post(
        client,
        f"/api/v1/legislativo/fontes-normativas/integracoes/{connector.json['id']}/sincronizar",
        csrf,
    )
    assert synchronized.status_code == 200
    assert synchronized.json["novosCandidatos"] == 1
    assert client.get("/api/v1/legislativo/fontes-normativas").json["content"] == []

    candidates = client.get(
        "/api/v1/legislativo/fontes-normativas/candidatas?status=PENDENTE"
    )
    assert candidates.status_code == 200
    candidate = candidates.json["content"][0]
    assert candidate["provedor"] == "LEXML"
    assert candidate["fonteExistenteId"] is None

    approved = _post(
        client,
        f"/api/v1/legislativo/fontes-normativas/candidatas/{candidate['id']}/decisao",
        csrf,
        {"decisao": "APROVAR", "motivo": "Texto e origem oficial conferidos."},
    )
    assert approved.status_code == 200
    assert approved.json["candidata"]["status"] == "APROVADA"
    assert approved.json["fonte"]["origem"] == "SINCRONIZADA"
    assert approved.json["fonte"]["provedor"] == "LEXML"
    assert approved.json["fonte"]["urlOficial"].startswith("https://")

    dashboard = client.get("/api/v1/legislativo/fontes-normativas/painel")
    assert dashboard.json["ativas"] == 1
    assert dashboard.json["sincronizadas"] == 1
    assert dashboard.json["pendentes"] == 0

    first_source_id = approved.json["fonte"]["id"]
    records[0] = ExternalNormativeRecord(
        external_id=records[0].external_id,
        source_type="LEI_MUNICIPAL",
        title=records[0].title,
        reference=records[0].reference,
        excerpt=(
            "Dispõe sobre iluminação eficiente, acessível e segura das praças e vias "
            "públicas no Município de Campinas, com manutenção preventiva periódica."
        ),
        jurisdiction="Campinas - SP",
        source_url=records[0].source_url,
        version="2026-08-18",
    )
    second_sync = _post(
        client,
        f"/api/v1/legislativo/fontes-normativas/integracoes/{connector.json['id']}/sincronizar",
        csrf,
    )
    assert second_sync.json["novosCandidatos"] == 1
    update = client.get(
        "/api/v1/legislativo/fontes-normativas/candidatas?status=PENDENTE"
    ).json["content"][0]
    assert update["fonteExistenteId"] == first_source_id
    updated = _post(
        client,
        f"/api/v1/legislativo/fontes-normativas/candidatas/{update['id']}/decisao",
        csrf,
        {"decisao": "APROVAR", "motivo": "Alteração oficial conferida e vigente."},
    )
    assert updated.json["fonte"]["substituiFonteId"] == first_source_id
    history = client.get(
        "/api/v1/legislativo/fontes-normativas?incluirInativas=true"
    ).json["content"]
    assert len(history) == 2
    assert sum(item["ativo"] for item in history) == 1


def test_rejected_external_norm_is_tenant_scoped_and_not_published(app, client, monkeypatch):
    csrf = _login(client)
    connector = _post(
        client,
        "/api/v1/legislativo/fontes-normativas/integracoes",
        csrf,
        {"nome": "LexML teste", "consulta": "norma municipal", "frequenciaHoras": 168},
    )
    monkeypatch.setattr(
        "app.legislative.normative_sync._fetch_records",
        lambda _connector: [
            ExternalNormativeRecord(
                external_id="urn:lex:teste:invalida",
                source_type="OUTRO",
                title="Ato normativo para conferência",
                reference="Ato nº 9/2026",
                excerpt="Conteúdo recebido que ainda exige confirmação da autoridade emissora.",
                jurisdiction=None,
                source_url="https://www.lexml.gov.br/urn/ato-9",
                version="2026",
            )
        ],
    )
    _post(
        client,
        f"/api/v1/legislativo/fontes-normativas/integracoes/{connector.json['id']}/sincronizar",
        csrf,
    )
    candidate = client.get(
        "/api/v1/legislativo/fontes-normativas/candidatas?status=PENDENTE"
    ).json["content"][0]
    rejected = _post(
        client,
        f"/api/v1/legislativo/fontes-normativas/candidatas/{candidate['id']}/decisao",
        csrf,
        {"decisao": "REJEITAR", "motivo": "Origem ainda não confirmada."},
    )
    assert rejected.status_code == 200
    assert rejected.json["fonte"] is None

    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": csrf})
    _login(client, "admin-b@teste.local", "OutraSenha123!")
    assert client.get(
        "/api/v1/legislativo/fontes-normativas/candidatas?status=PENDENTE"
    ).json["content"] == []
    assert client.get("/api/v1/legislativo/fontes-normativas").json["content"] == []
