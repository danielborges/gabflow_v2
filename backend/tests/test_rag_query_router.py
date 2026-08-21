import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.extensions import db
from app.models import Citizen, RagAssistantQuery, RequestStatus, ServiceRequest, Tenant, Territory
from app.rag.router import QueryMethod, classify_query

PASSWORD = "SenhaForte123!"  # noqa: S105
OTHER_PASSWORD = "OutraSenha123!"  # noqa: S105


def _login(client, tenant, email, password):
    response = client.post(
        "/api/v1/auth/login",
        json={"tenant": tenant, "email": email, "password": password},
    )
    assert response.status_code == 200
    return client.get_cookie("csrf_access_token").value


def _create_request(client, csrf, title, theme, territory_id=None):
    payload = {
        "origem": "PRESENCIAL",
        "titulo": title,
        "descricao": "Demanda usada para validar o roteamento automático.",
        "tema": theme,
    }
    if territory_id:
        payload["territorioId"] = territory_id
    response = client.post(
        "/api/v1/solicitacoes",
        json=payload,
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert response.status_code == 201
    return response.json


def test_router_classifies_documental_structured_and_hybrid_intents():
    structured = classify_query("Quantas solicitações existem por tema?")
    documentary = classify_query("Quais argumentos aparecem nos relatos sobre iluminação?")
    hybrid = classify_query("Quantas solicitações existem e quais argumentos aparecem nos relatos?")
    thematic_hybrid = classify_query("Quais temas recorrentes podem fundamentar uma indicação?")
    overdue = classify_query("Quantos encaminhamentos com prazos vencidos existem por órgão?")

    assert structured.method == QueryMethod.ESTRUTURADO
    assert structured.structured_payload == {
        "dataset": "SOLICITACOES",
        "metrica": "CONTAGEM",
        "agruparPor": "TEMA",
    }
    assert documentary.method == QueryMethod.DOCUMENTAL
    assert hybrid.method == QueryMethod.HIBRIDO
    assert thematic_hybrid.method == QueryMethod.HIBRIDO
    assert thematic_hybrid.structured_payload["agruparPor"] == "TEMA"
    assert overdue.structured_payload["dataset"] == "ENCAMINHAMENTOS"
    assert overdue.structured_payload["metrica"] == "PRAZOS_VENCIDOS"
    assert overdue.structured_payload["agruparPor"] == "ORGAO"


def test_router_understands_request_leader_by_territory():
    intent = classify_query("Qual é o território recordista de solicitações?")

    assert intent.method == QueryMethod.ESTRUTURADO
    assert intent.structured_payload == {
        "dataset": "SOLICITACOES",
        "metrica": "CONTAGEM",
        "agruparPor": "TERRITORIO",
        "ranking": "MAIOR",
    }


def test_router_understands_registered_territory_count_without_using_requests():
    intent = classify_query("Quantos territórios estão cadastrados no sistema?")

    assert intent.method == QueryMethod.ESTRUTURADO
    assert intent.structured_payload == {
        "dataset": "TERRITORIOS",
        "metrica": "CONTAGEM",
        "agruparPor": "NENHUM",
    }


def test_structured_route_counts_only_active_territories_in_tenant(app, client):
    with app.app_context():
        tenant_a = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-a"))
        tenant_b = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-b"))
        db.session.add_all(
            [
                Territory(tenant_id=tenant_a.id, name="Centro"),
                Territory(tenant_id=tenant_a.id, name="Zona Norte"),
                Territory(tenant_id=tenant_a.id, name="Inativo", active=False),
                Territory(tenant_id=tenant_b.id, name="Outro gabinete"),
            ]
        )
        db.session.commit()

    csrf = _login(client, "gabinete-a", "admin@teste.local", PASSWORD)
    response = client.post(
        "/api/v1/assistente/consultas",
        json={"consulta": "Quantos territórios estão cadastrados no sistema?"},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert response.status_code == 200
    assert response.json["resultadoEstruturado"]["dataset"] == "TERRITORIOS"
    assert response.json["resultadoEstruturado"]["total"] == 2
    assert response.json["resposta"] == "Existem 2 territórios cadastrados no sistema."


def test_unknown_quantitative_subject_does_not_default_to_requests(app, client):
    csrf = _login(client, "gabinete-a", "admin@teste.local", PASSWORD)
    response = client.post(
        "/api/v1/assistente/consultas",
        json={"consulta": "Quantos cadastros especiais existem?"},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert response.status_code == 200
    assert response.json["metodo"] == "DOCUMENTAL"
    assert response.json["resultadoEstruturado"] is None
    assert "PLANO_QUANTITATIVO_NAO_RESOLVIDO_SEM_RESPOSTA_PADRAO" in response.json[
        "motivosRoteamento"
    ]


def test_structured_route_answers_request_leader_by_territory(app, client):
    with app.app_context():
        tenant = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-a"))
        centro = Territory(tenant_id=tenant.id, name="Centro")
        norte = Territory(tenant_id=tenant.id, name="Zona Norte")
        db.session.add_all([centro, norte])
        db.session.commit()
        centro_id = str(centro.id)
        norte_id = str(norte.id)

    csrf = _login(client, "gabinete-a", "admin@teste.local", PASSWORD)
    _create_request(client, csrf, "Demanda central 1", "Mobilidade", centro_id)
    _create_request(client, csrf, "Demanda central 2", "Saúde", centro_id)
    _create_request(client, csrf, "Demanda norte", "Educação", norte_id)

    response = client.post(
        "/api/v1/assistente/consultas",
        json={"consulta": "Qual é o território recordista de solicitações?"},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert response.status_code == 200
    assert response.json["metodo"] == "ESTRUTURADO"
    assert response.json["resultadoEstruturado"]["ranking"] == "MAIOR"
    assert response.json["resultadoEstruturado"]["itens"][0] == {
        "grupo": "Centro",
        "valor": 2,
    }
    assert response.json["resposta"].startswith(
        "Centro é o território recordista, com 2 solicitações."
    )


def test_structured_route_reports_tied_territory_leaders(app, client):
    with app.app_context():
        tenant = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-a"))
        centro = Territory(tenant_id=tenant.id, name="Centro")
        norte = Territory(tenant_id=tenant.id, name="Zona Norte")
        db.session.add_all([centro, norte])
        db.session.commit()
        centro_id = str(centro.id)
        norte_id = str(norte.id)

    csrf = _login(client, "gabinete-a", "admin@teste.local", PASSWORD)
    _create_request(client, csrf, "Demanda central", "Mobilidade", centro_id)
    _create_request(client, csrf, "Demanda norte", "Educação", norte_id)

    response = client.post(
        "/api/v1/assistente/consultas",
        json={"consulta": "Qual é o território recordista de solicitações?"},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert response.status_code == 200
    assert response.json["resposta"].startswith(
        "Há empate na 1ª posição entre 2 territórios, com 1 solicitação cada: Centro, Zona Norte."
    )


def test_assistant_keeps_conversation_and_resolves_structured_follow_up(app, client):
    with app.app_context():
        tenant = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-a"))
        territories = [
            Territory(tenant_id=tenant.id, name="Centro"),
            Territory(tenant_id=tenant.id, name="Zona Norte"),
            Territory(tenant_id=tenant.id, name="Zona Sul"),
        ]
        db.session.add_all(territories)
        db.session.commit()
        territory_ids = [str(item.id) for item in territories]

    csrf = _login(client, "gabinete-a", "admin@teste.local", PASSWORD)
    for index, territory_id in enumerate(territory_ids):
        for item in range(3 - index):
            _create_request(
                client,
                csrf,
                f"Demanda {index}-{item}",
                "Atendimento",
                territory_id,
            )

    first = client.post(
        "/api/v1/assistente/consultas",
        json={"consulta": "Qual é o território recordista de solicitações?"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    second = client.post(
        "/api/v1/assistente/consultas",
        json={
            "consulta": "E qual ficou em segundo lugar?",
            "conversaId": first.json["conversaId"],
        },
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert first.status_code == 200
    assert first.json["turno"] == 1
    assert second.status_code == 200
    assert second.json["conversaId"] == first.json["conversaId"]
    assert second.json["turno"] == 2
    assert second.json["metodo"] == "ESTRUTURADO"
    assert "CONTEXTO_CONVERSACIONAL_APLICADO" in second.json["motivosRoteamento"]
    assert second.json["resposta"].startswith(
        "Na 2ª posição está Zona Norte, com 2 solicitações."
    )

    with app.app_context():
        queries = list(
            db.session.scalars(
                select(RagAssistantQuery)
                .where(
                    RagAssistantQuery.conversation_id
                    == uuid.UUID(first.json["conversaId"])
                )
                .order_by(RagAssistantQuery.turn_index)
            )
        )
        assert [item.turn_index for item in queries] == [1, 2]
        assert queries[1].context_query_ids == [str(queries[0].id)]


def test_router_understands_quantity_closed_requests_in_named_month():
    intent = classify_query(
        "Qual a quantidade de solicitações fechadas em Julho de 2026?"
    )

    assert intent.method == QueryMethod.ESTRUTURADO
    assert intent.structured_payload == {
        "dataset": "SOLICITACOES",
        "metrica": "CONTAGEM",
        "agruparPor": "NENHUM",
        "inicio": "2026-07-01",
        "fim": "2026-07-31",
        "campoData": "ENCERRAMENTO",
    }


def test_router_understands_citizen_count_filtered_by_name():
    intent = classify_query("Quantos cidadões com o nome Daniel estão cadastrados?")

    assert intent.method == QueryMethod.ESTRUTURADO
    assert intent.structured_payload == {
        "dataset": "CIDADAOS",
        "metrica": "CONTAGEM",
        "agruparPor": "NENHUM",
        "nome": "Daniel",
    }


def test_router_understands_people_registered_as_citizens():
    intent = classify_query("Quantas pessoas com o nome Adriana estão cadastradas?")

    assert intent.method == QueryMethod.ESTRUTURADO
    assert intent.structured_payload == {
        "dataset": "CIDADAOS",
        "metrica": "CONTAGEM",
        "agruparPor": "NENHUM",
        "nome": "Adriana",
    }


def test_route_applies_ai_interpretation_without_delegating_the_count(app, monkeypatch):
    from app.rag.structured_interpretation import StructuredInterpretation

    with app.app_context():
        tenant = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-a"))
        db.session.add(
            Citizen(
                tenant_id=tenant.id,
                name="Adriana Teste",
                legal_basis="EXECUCAO_POLITICA_PUBLICA",
            )
        )
        db.session.commit()
        app.config["RAG_STRUCTURED_INTERPRETATION_ENABLED"] = True
        monkeypatch.setattr(
            "app.rag.router.interpret_structured_query",
            lambda query, payload: StructuredInterpretation(
                {**payload, "dataset": "CIDADAOS", "nome": "Adriana"},
                True,
            ),
        )

        from app.rag.router import route_query

        answer = route_query(tenant.id, "admin", "Quantas pessoas chamadas Adriana existem?")

    assert answer["resultadoEstruturado"]["total"] == 1
    assert answer["filtrosAplicados"]["nome"] == "Adriana"
    assert "INTERPRETACAO_IA_APLICADA" in answer["motivosRoteamento"]


def test_structured_route_counts_only_active_citizens_with_name_in_tenant(app, client):
    with app.app_context():
        tenant_a = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-a"))
        tenant_b = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-b"))
        db.session.add_all(
            [
                Citizen(
                    tenant_id=tenant_a.id,
                    name=f"Daniel Teste {index}",
                    legal_basis="EXECUCAO_POLITICA_PUBLICA",
                )
                for index in range(5)
            ]
            + [
                Citizen(
                    tenant_id=tenant_a.id,
                    name="Daniel Anonimizado",
                    legal_basis="EXECUCAO_POLITICA_PUBLICA",
                    anonymized_at=datetime.now(UTC),
                ),
                Citizen(
                    tenant_id=tenant_a.id,
                    name="Ana Teste",
                    social_name="Daniela Teste",
                    legal_basis="EXECUCAO_POLITICA_PUBLICA",
                ),
                Citizen(
                    tenant_id=tenant_b.id,
                    name="Daniel Outro Gabinete",
                    legal_basis="EXECUCAO_POLITICA_PUBLICA",
                ),
            ]
        )
        db.session.commit()

    csrf = _login(client, "gabinete-a", "admin@teste.local", PASSWORD)
    response = client.post(
        "/api/v1/assistente/consultas",
        json={"consulta": "Quantos cidadões com o nome Daniel estão cadastrados?"},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert response.status_code == 200
    assert response.json["metodo"] == "ESTRUTURADO"
    assert response.json["resultadoEstruturado"]["dataset"] == "CIDADAOS"
    assert response.json["resultadoEstruturado"]["total"] == 5
    assert response.json["filtrosAplicados"]["nome"] == "Daniel"


def test_structured_route_counts_requests_closed_in_named_month(app, client):
    csrf = _login(client, "gabinete-a", "admin@teste.local", PASSWORD)
    closed_in_july = _create_request(client, csrf, "Fechada em julho", "Atendimento")
    closed_in_august = _create_request(client, csrf, "Fechada em agosto", "Atendimento")
    _create_request(client, csrf, "Ainda aberta", "Atendimento")

    with app.app_context():
        july_item = db.session.get(ServiceRequest, uuid.UUID(closed_in_july["id"]))
        july_item.status = RequestStatus.ENCERRADA
        july_item.closed_at = datetime(2026, 7, 15, 12, tzinfo=UTC)
        august_item = db.session.get(ServiceRequest, uuid.UUID(closed_in_august["id"]))
        august_item.status = RequestStatus.ENCERRADA
        august_item.closed_at = datetime(2026, 8, 1, 12, tzinfo=UTC)
        db.session.commit()

    response = client.post(
        "/api/v1/assistente/consultas",
        json={
            "consulta": "Qual a quantidade de solicitações fechadas em Julho de 2026?"
        },
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert response.status_code == 200
    assert response.json["metodo"] == "ESTRUTURADO"
    assert response.json["resultadoEstruturado"]["total"] == 1
    assert response.json["resultadoEstruturado"]["periodo"] == {
        "inicio": "2026-07-01",
        "fim": "2026-07-31",
    }
    assert response.json["filtrosAplicados"]["campoData"] == "ENCERRAMENTO"


def test_structured_route_skips_document_retrieval_and_persists_decision(app, client, monkeypatch):
    csrf = _login(client, "gabinete-a", "admin@teste.local", PASSWORD)
    _create_request(client, csrf, "Iluminação da praça", "Iluminação")
    _create_request(client, csrf, "Luminária apagada", "Iluminação")

    def unexpected_retrieval(*_args, **_kwargs):
        raise AssertionError("Retrieval documental não deve executar.")

    monkeypatch.setattr("app.rag.router.answer_query", unexpected_retrieval)
    response = client.post(
        "/api/v1/assistente/consultas",
        json={"consulta": "Quantas solicitações existem por tema?"},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert response.status_code == 200
    assert response.json["metodo"] == "ESTRUTURADO"
    assert response.json["resultadoEstruturado"]["total"] == 2
    assert response.json["resultadoEstruturado"]["itens"] == [{"grupo": "Iluminação", "valor": 2}]
    assert response.json["fontes"] == []
    assert response.json["modeloEmbedding"] == "NAO_APLICAVEL"
    with app.app_context():
        query = db.session.scalar(select(RagAssistantQuery))
        assert query.method == "ESTRUTURADO"
        assert query.routing_reasons == ["INDICADOR_QUANTITATIVO_OU_AGRUPAMENTO"]
        assert query.structured_result["total"] == 2
        assert query.applied_filters == {
            "status": None,
            "tema": None,
            "territorioId": None,
            "orgaoId": None,
        }


def test_hybrid_route_combines_structured_and_documentary_results(app, client):
    csrf = _login(client, "gabinete-a", "admin@teste.local", PASSWORD)
    _create_request(client, csrf, "Pavimentação da avenida", "Mobilidade")

    response = client.post(
        "/api/v1/assistente/consultas",
        json={
            "consulta": (
                "Quantas solicitações existem e quais argumentos aparecem "
                "nos relatos sobre mobilidade?"
            )
        },
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert response.status_code == 200
    assert response.json["metodo"] == "HIBRIDO"
    assert response.json["resultadoEstruturado"]["total"] == 1
    assert response.json["resposta"].startswith("Resultado estruturado")
    assert "Complemento documental:" in response.json["resposta"]
    assert response.json["recusaConclusiva"] is False


def test_automatic_structured_query_remains_tenant_scoped(app, client):
    csrf_a = _login(client, "gabinete-a", "admin@teste.local", PASSWORD)
    _create_request(client, csrf_a, "Demanda exclusiva do tenant A", "Exclusivo")

    csrf_b = _login(client, "gabinete-b", "admin-b@teste.local", OTHER_PASSWORD)
    response = client.post(
        "/api/v1/assistente/consultas",
        json={
            "consulta": "Quantas solicitações existem?",
            "filtros": {"status": "NOVA"},
        },
        headers={"X-CSRF-TOKEN": csrf_b},
    )

    assert response.status_code == 200
    assert response.json["metodo"] == "ESTRUTURADO"
    assert response.json["resultadoEstruturado"]["total"] == 0
    assert response.json["filtrosAplicados"]["status"] == "NOVA"


def test_assistant_accepts_consecutive_structured_and_documentary_queries(client):
    csrf = _login(client, "gabinete-a", "admin@teste.local", PASSWORD)

    first = client.post(
        "/api/v1/assistente/consultas",
        json={"consulta": "Quantos cidadãos estão cadastrados?"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    second = client.post(
        "/api/v1/assistente/consultas",
        json={"consulta": "Quais documentos orientam o atendimento ao cidadão?"},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json["metodo"] == "ESTRUTURADO"
    assert second.json["metodo"] == "DOCUMENTAL"
