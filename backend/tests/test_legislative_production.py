import uuid

from sqlalchemy import select

from app.extensions import db
from app.models import (
    AuditLog,
    LegislativeDocumentType,
    LegislativeDraft,
    LegislativeDraftRequest,
    LegislativeDraftStatus,
    LegislativeDraftVersion,
    LegislativeGenerationStatus,
    LegislativeTramitation,
    Tenant,
    User,
)
from app.outbox.service import process_batch

PASSWORD = "SenhaForte123!"  # noqa: S105


def _login(client, tenant="gabinete-a", password=PASSWORD):
    response = client.post(
        "/api/v1/auth/login",
        json={"tenant": tenant, "email": "admin@teste.local", "password": password},
    )
    assert response.status_code == 200
    return client.get_cookie("csrf_access_token").value


def _post(client, path, csrf, payload):
    return client.post(path, json=payload, headers={"X-CSRF-TOKEN": csrf})


def _put(client, path, csrf, payload):
    return client.put(path, json=payload, headers={"X-CSRF-TOKEN": csrf})


def _patch(client, path, csrf, payload):
    return client.patch(path, json=payload, headers={"X-CSRF-TOKEN": csrf})


def _request(client, csrf):
    response = _post(
        client,
        "/api/v1/solicitacoes",
        csrf,
        {
            "origem": "WHATSAPP",
            "titulo": "Iluminação da praça central",
            "descricao": "Moradores relatam três postes apagados na praça central.",
            "endereco": "Praça Central, Centro",
        },
    )
    assert response.status_code == 201
    return response.json


def test_legislative_draft_full_human_review_flow(app, client):
    csrf = _login(client)
    service_request = _request(client, csrf)
    related_request = _request(client, csrf)
    template = _post(
        client,
        "/api/v1/legislativo/templates",
        csrf,
        {
            "tipo": "INDICACAO",
            "nome": "Indicação padrão",
            "estrutura": "Objeto; fatos; providência; justificativa",
        },
    )
    assert template.status_code == 201

    generated = _post(
        client,
        f"/api/v1/solicitacoes/{service_request['id']}/gerar-minuta",
        csrf,
        {
            "tipo": "INDICACAO",
            "templateId": template.json["id"],
            "fatosSelecionados": ["Há três postes apagados na praça central."],
            "solicitacoesRelacionadasIds": [related_request["id"]],
        },
    )
    assert generated.status_code == 202
    assert generated.json["status"] == "RASCUNHO"
    assert generated.json["statusGeracao"] == "PENDENTE"
    assert generated.json["protocoloAutomatico"] is False

    with app.app_context():
        result = process_batch("legislative-test-worker")
        assert result.succeeded >= 2

    detail = client.get(f"/api/v1/legislativo/minutas/{generated.json['id']}")
    assert detail.status_code == 200
    assert detail.json["statusGeracao"] == "CONCLUIDA"
    assert detail.json["conteudo"]
    assert detail.json["versaoAtual"] == 1
    assert len(detail.json["solicitacoes"]) == 2
    assert detail.json["solicitacoes"][0] == {
        "id": service_request["id"],
        "principal": True,
        "protocolo": service_request["protocolo"],
        "titulo": service_request["titulo"],
    }
    assert detail.json["solicitacoes"][1]["id"] == related_request["id"]
    assert detail.json["solicitacoes"][1]["principal"] is False
    assert detail.json["trechosSemFundamentacao"]
    assert detail.json["metadadosGeracao"]["protocoloAutomatico"] is False

    saved = _post(
        client,
        f"/api/v1/legislativo/minutas/{detail.json['id']}/revisao",
        csrf,
        {
            "acao": "SALVAR",
            "titulo": "Indicação para manutenção da iluminação da praça central",
            "conteudo": f"{detail.json['conteudo']}\n\nTexto revisado pelo assessor.",
            "justificativa": detail.json["justificativa"],
            "motivo": "Ajuste de clareza",
        },
    )
    assert saved.status_code == 200
    assert saved.json["versaoAtual"] == 2

    history = client.get(f"/api/v1/legislativo/minutas/{detail.json['id']}/versoes")
    assert history.status_code == 200
    assert [item["numero"] for item in history.json["content"]] == [2, 1]
    assert history.json["content"][0]["autor"] == "Admin A"

    initial_version = client.get(
        f"/api/v1/legislativo/minutas/{detail.json['id']}/versoes/1"
    )
    assert initial_version.status_code == 200
    assert initial_version.json["conteudo"] == detail.json["conteudo"]

    comparison = client.get(
        f"/api/v1/legislativo/minutas/{detail.json['id']}/comparacao?de=1&para=2"
    )
    assert comparison.status_code == 200
    assert "titulo" in comparison.json["camposAlterados"]
    assert "conteudo" in comparison.json["camposAlterados"]
    assert comparison.json["linhasAdicionadas"] > 0
    assert comparison.json["campos"]["conteudo"]["alterado"] is True

    restored = _post(
        client,
        f"/api/v1/legislativo/minutas/{detail.json['id']}/versoes/1/restaurar",
        csrf,
        {"motivo": "Retomar a redação inicial para nova revisão"},
    )
    assert restored.status_code == 200
    assert restored.json["versaoAtual"] == 3
    assert restored.json["conteudo"] == initial_version.json["conteudo"]
    assert restored.json["versoes"][0]["motivo"].startswith("Restauração da versão 1")

    restoring_current = _post(
        client,
        f"/api/v1/legislativo/minutas/{detail.json['id']}/versoes/3/restaurar",
        csrf,
        {"motivo": "Não deve restaurar"},
    )
    assert restoring_current.status_code == 409

    submitted = _post(
        client,
        f"/api/v1/legislativo/minutas/{detail.json['id']}/revisao",
        csrf,
        {
            "acao": "SUBMETER",
            "motivo": "Encaminhada para aprovação",
        },
    )
    assert submitted.status_code == 200
    assert submitted.json["status"] == "EM_REVISAO"

    blocked = _post(
        client,
        f"/api/v1/legislativo/minutas/{detail.json['id']}/revisao",
        csrf,
        {
            "acao": "APROVAR",
        },
    )
    assert blocked.status_code == 409
    assert blocked.json["error"] == "foundation_confirmation_required"

    approved = _post(
        client,
        f"/api/v1/legislativo/minutas/{detail.json['id']}/revisao",
        csrf,
        {
            "acao": "APROVAR",
            "confirmarFundamentacao": True,
        },
    )
    assert approved.status_code == 200
    assert approved.json["status"] == "APROVADA"
    assert approved.json["protocolo"] is None

    restore_after_approval = _post(
        client,
        f"/api/v1/legislativo/minutas/{detail.json['id']}/versoes/1/restaurar",
        csrf,
        {"motivo": "Não deve alterar minuta aprovada"},
    )
    assert restore_after_approval.status_code == 409

    protocolled = _post(
        client,
        f"/api/v1/legislativo/minutas/{detail.json['id']}/protocolo",
        csrf,
        {
            "protocolo": "CM-2026-001",
        },
    )
    assert protocolled.status_code == 200
    assert protocolled.json["protocolo"] == "CM-2026-001"
    assert protocolled.json["statusTramitacao"] == "PROTOCOLADA"
    assert len(protocolled.json["tramitacoes"]) == 1
    assert protocolled.json["tramitacoes"][0]["etapa"] == "Protocolo"

    movement = _post(
        client,
        f"/api/v1/legislativo/minutas/{detail.json['id']}/tramitacoes",
        csrf,
        {
            "status": "EM_COMISSAO",
            "etapa": "Comissão de Obras e Serviços Públicos",
            "destino": "Comissão permanente",
            "referenciaExterna": "MOV-2026-002",
            "observacoes": "Aguardando parecer da relatoria.",
        },
    )
    assert movement.status_code == 201
    assert movement.json["statusTramitacao"] == "EM_COMISSAO"
    assert len(movement.json["tramitacoes"]) == 2
    assert movement.json["tramitacoes"][1]["referenciaExterna"] == "MOV-2026-002"

    timeline = client.get(
        f"/api/v1/legislativo/minutas/{detail.json['id']}/tramitacoes"
    )
    assert timeline.status_code == 200
    assert [item["status"] for item in timeline.json["content"]] == [
        "PROTOCOLADA",
        "EM_COMISSAO",
    ]

    docx = client.get(f"/api/v1/legislativo/minutas/{detail.json['id']}/exportar/docx")
    pdf = client.get(f"/api/v1/legislativo/minutas/{detail.json['id']}/exportar/pdf")
    assert docx.status_code == 200
    assert docx.data.startswith(b"PK")
    assert pdf.status_code == 200
    assert pdf.data.startswith(b"%PDF")

    with app.app_context():
        draft = db.session.execute(select(LegislativeDraft)).scalar_one()
        versions = (
            db.session.execute(
                select(LegislativeDraftVersion).where(LegislativeDraftVersion.draft_id == draft.id)
            )
            .scalars()
            .all()
        )
        assert len(versions) == 4
        assert len(db.session.execute(select(LegislativeDraftRequest)).scalars().all()) == 2
        assert db.session.execute(select(LegislativeTramitation)).scalars().all()
        assert db.session.execute(
            select(AuditLog).where(AuditLog.action == "legislative_draft.protocol_registered")
        ).scalar_one()
        assert db.session.execute(
            select(AuditLog).where(AuditLog.action == "legislative_draft.tramitation_added")
        ).scalar_one()
        assert db.session.execute(
            select(AuditLog).where(AuditLog.action == "legislative_draft.version_restored")
        ).scalar_one()


def test_normative_foundation_is_retrieved_and_only_applied_after_human_review(
    app, client
):
    csrf = _login(client)
    source = _post(
        client,
        "/api/v1/legislativo/fontes-normativas",
        csrf,
        {
            "tipo": "LEI_MUNICIPAL",
            "titulo": "Lei Municipal de Iluminação de Espaços Públicos",
            "referencia": "art. 12, inciso III",
            "trecho": (
                "Compete ao Município manter a iluminação das praças, vias e demais "
                "espaços públicos em condições adequadas de segurança."
            ),
            "jurisdicao": "Município de Teste",
            "versao": "2026",
            "url": "https://leis.example.test/iluminacao",
            "vigenteDesde": "2026-01-01",
        },
    )
    assert source.status_code == 201
    assert source.json["ativo"] is True
    assert source.json["checksum"]

    service_request = _request(client, csrf)
    generated = _post(
        client,
        f"/api/v1/solicitacoes/{service_request['id']}/gerar-minuta",
        csrf,
        {"tipo": "INDICACAO"},
    )
    assert generated.status_code == 202
    with app.app_context():
        assert process_batch("foundation-test-worker").succeeded >= 2

    detail = client.get(f"/api/v1/legislativo/minutas/{generated.json['id']}")
    assert detail.status_code == 200
    assert detail.json["fundamentacaoSugerida"]["aplicacaoAutomatica"] is False
    assert detail.json["fundamentacaoSugerida"]["revisaoHumanaObrigatoria"] is True
    assert detail.json["fundamentacaoNormativa"] == []

    retrieved = _post(
        client,
        f"/api/v1/legislativo/minutas/{generated.json['id']}/fundamentacao/recuperar",
        csrf,
        {"consulta": "iluminação de praças e espaços públicos com postes apagados"},
    )
    assert retrieved.status_code == 200
    assert retrieved.json["fontes"][0]["id"] == source.json["id"]
    assert retrieved.json["fontes"][0]["pontuacao"] >= retrieved.json["limiar"]
    assert retrieved.json["conteudoTratadoComoDado"] is True

    unknown_source = _post(
        client,
        f"/api/v1/legislativo/minutas/{generated.json['id']}/fundamentacao/aplicar",
        csrf,
        {"fonteIds": [str(uuid.uuid4())], "motivo": "Fonte não recuperada"},
    )
    assert unknown_source.status_code == 422

    applied = _post(
        client,
        f"/api/v1/legislativo/minutas/{generated.json['id']}/fundamentacao/aplicar",
        csrf,
        {
            "fonteIds": [source.json["id"]],
            "motivo": "Dispositivo pertinente ao objeto da indicação",
        },
    )
    assert applied.status_code == 200
    assert applied.json["versaoAtual"] == 2
    citation = applied.json["fundamentacaoNormativa"][0]
    assert citation["sourceId"] == source.json["id"]
    assert citation["validadaPeloUsuario"] is True
    assert citation["recuperadaVia"] == "RAG_NORMATIVO_V1"
    assert citation["checksum"] == source.json["checksum"]
    assert applied.json["fontes"][0]["sourceId"] == source.json["id"]
    assert all(
        item["trecho"] != "Fundamentação normativa"
        for item in applied.json["trechosSemFundamentacao"]
    )

    with app.app_context():
        actions = set(
            db.session.execute(
                select(AuditLog.action).where(
                    AuditLog.action.in_(
                        {
                            "normative_source.created",
                            "legislative_draft.foundation_retrieved",
                            "legislative_draft.foundation_applied",
                        }
                    )
                )
            ).scalars()
        )
        assert actions == {
            "normative_source.created",
            "legislative_draft.foundation_retrieved",
            "legislative_draft.foundation_applied",
        }

    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": csrf})
    _login(client, "gabinete-b", "OutraSenha123!")
    assert client.get("/api/v1/legislativo/fontes-normativas").json["content"] == []


def test_legislative_resources_are_tenant_scoped(app, client):
    csrf = _login(client)
    service_request = _request(client, csrf)
    generated = _post(
        client,
        f"/api/v1/solicitacoes/{service_request['id']}/gerar-minuta",
        csrf,
        {
            "tipo": "OFICIO",
        },
    )
    assert generated.status_code == 202
    draft_id = generated.json["id"]
    before_protocol = _post(
        client,
        f"/api/v1/legislativo/minutas/{draft_id}/tramitacoes",
        csrf,
        {"status": "DISTRIBUIDA", "etapa": "Distribuição"},
    )
    assert before_protocol.status_code == 409

    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": csrf})
    other_csrf = _login(client, "gabinete-b", "OutraSenha123!")
    assert client.get(f"/api/v1/legislativo/minutas/{draft_id}").status_code == 404
    assert client.get(f"/api/v1/legislativo/minutas/{draft_id}/versoes").status_code == 404
    assert (
        client.get(f"/api/v1/legislativo/minutas/{draft_id}/comparacao?de=1&para=2").status_code
        == 404
    )
    assert (
        _post(
            client,
            f"/api/v1/legislativo/minutas/{draft_id}/protocolo",
            other_csrf,
            {
                "protocolo": "INDEVIDO",
            },
        ).status_code
        == 404
    )
    assert (
        _post(
            client,
            f"/api/v1/legislativo/minutas/{draft_id}/tramitacoes",
            other_csrf,
            {"status": "DISTRIBUIDA", "etapa": "Distribuição"},
        ).status_code
        == 404
    )


def test_legislative_template_visual_management_contract(app, client):
    csrf = _login(client)
    created = _post(
        client,
        "/api/v1/legislativo/templates",
        csrf,
        {
            "tipo": "REQUERIMENTO",
            "nome": "Requerimento institucional",
            "estrutura": "Ementa\nDestinatário\nPerguntas\nJustificativa",
        },
    )
    assert created.status_code == 201
    template_id = created.json["id"]
    assert created.json["ativo"] is True

    duplicate = _post(
        client,
        "/api/v1/legislativo/templates",
        csrf,
        {
            "tipo": "REQUERIMENTO",
            "nome": "requerimento institucional",
            "estrutura": "Outra estrutura",
        },
    )
    assert duplicate.status_code == 409

    updated = _put(
        client,
        f"/api/v1/legislativo/templates/{template_id}",
        csrf,
        {
            "tipo": "PEDIDO_INFORMACAO",
            "nome": "Pedido institucional",
            "estrutura": "Destinatário\nContexto\nQuestionamentos\nPrazo esperado",
        },
    )
    assert updated.status_code == 200
    assert updated.json["tipo"] == "PEDIDO_INFORMACAO"
    assert updated.json["nome"] == "Pedido institucional"

    disabled = _patch(
        client,
        f"/api/v1/legislativo/templates/{template_id}/status",
        csrf,
        {"ativo": False},
    )
    assert disabled.status_code == 200
    assert disabled.json["ativo"] is False
    assert client.get("/api/v1/legislativo/templates").json["content"] == []
    managed = client.get("/api/v1/legislativo/templates?incluirInativos=true")
    assert managed.status_code == 200
    assert managed.json["content"][0]["ativo"] is False

    service_request = _request(client, csrf)
    unavailable = _post(
        client,
        f"/api/v1/solicitacoes/{service_request['id']}/gerar-minuta",
        csrf,
        {"tipo": "PEDIDO_INFORMACAO", "templateId": template_id},
    )
    assert unavailable.status_code == 422
    assert unavailable.json["message"] == "Template não está disponível."

    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": csrf})
    other_csrf = _login(client, "gabinete-b", "OutraSenha123!")
    assert (
        _patch(
            client,
            f"/api/v1/legislativo/templates/{template_id}/status",
            other_csrf,
            {"ativo": True},
        ).status_code
        == 404
    )

    with app.app_context():
        actions = set(
            db.session.execute(
                select(AuditLog.action).where(
                    AuditLog.action.in_(
                        {
                            "legislative_template.created",
                            "legislative_template.updated",
                            "legislative_template.deactivated",
                        }
                    )
                )
            ).scalars()
        )
        assert actions == {
            "legislative_template.created",
            "legislative_template.updated",
            "legislative_template.deactivated",
        }


def test_multiple_legislative_request_links_are_validated(client):
    csrf = _login(client)
    primary = _request(client, csrf)

    not_a_list = _post(
        client,
        f"/api/v1/solicitacoes/{primary['id']}/gerar-minuta",
        csrf,
        {"tipo": "OFICIO", "solicitacoesRelacionadasIds": primary["id"]},
    )
    assert not_a_list.status_code == 422
    assert "lista" in not_a_list.json["message"]

    duplicate = _post(
        client,
        f"/api/v1/solicitacoes/{primary['id']}/gerar-minuta",
        csrf,
        {"tipo": "OFICIO", "solicitacoesRelacionadasIds": [primary["id"]]},
    )
    assert duplicate.status_code == 422
    assert "mais de uma vez" in duplicate.json["message"]

    over_limit = _post(
        client,
        f"/api/v1/solicitacoes/{primary['id']}/gerar-minuta",
        csrf,
        {
            "tipo": "OFICIO",
            "solicitacoesRelacionadasIds": [str(uuid.uuid4()) for _ in range(20)],
        },
    )
    assert over_limit.status_code == 422
    assert "máximo 20" in over_limit.json["message"]


def test_semantic_precedent_search_ranks_filters_and_isolates_tenant(
    app, client, monkeypatch
):
    _login(client)
    with app.app_context():
        tenant_a = db.session.execute(
            select(Tenant).where(Tenant.slug == "gabinete-a")
        ).scalar_one()
        tenant_b = db.session.execute(
            select(Tenant).where(Tenant.slug == "gabinete-b")
        ).scalar_one()
        user_a = db.session.execute(
            select(User).where(User.tenant_id == tenant_a.id)
        ).scalar_one()
        user_b = db.session.execute(
            select(User).where(User.tenant_id == tenant_b.id)
        ).scalar_one()
        related = LegislativeDraft(
            tenant_id=tenant_a.id,
            document_type=LegislativeDocumentType.INDICACAO,
            status=LegislativeDraftStatus.APROVADA,
            generation_status=LegislativeGenerationStatus.CONCLUIDA,
            title="Iluminação e segurança nas praças",
            content="Instala luminárias para permitir o uso seguro dos espaços públicos.",
            justification="A medida protege moradores que circulam à noite.",
            protocol_number="CM-2026-SEM-01",
            created_by_id=user_a.id,
        )
        unrelated = LegislativeDraft(
            tenant_id=tenant_a.id,
            document_type=LegislativeDocumentType.REQUERIMENTO,
            status=LegislativeDraftStatus.RASCUNHO,
            generation_status=LegislativeGenerationStatus.CONCLUIDA,
            title="Aquisição de vacinas",
            content="Solicita informações sobre o estoque da rede municipal de saúde.",
            created_by_id=user_a.id,
        )
        other_tenant = LegislativeDraft(
            tenant_id=tenant_b.id,
            document_type=LegislativeDocumentType.INDICACAO,
            status=LegislativeDraftStatus.APROVADA,
            generation_status=LegislativeGenerationStatus.CONCLUIDA,
            title="Iluminação segura em praças de outro gabinete",
            content="Amplia a iluminação dos espaços públicos.",
            created_by_id=user_b.id,
        )
        db.session.add_all([related, unrelated, other_tenant])
        db.session.commit()
        related_id = str(related.id)
        other_tenant_id = str(other_tenant.id)

    class SemanticProvider:
        model = "nomic-embed-text-test"

        def similarities(self, _source, candidates):
            return [0.94 if "luminárias" in item else 0.08 for item in candidates]

    monkeypatch.setattr(
        "app.legislative.precedents._precedent_provider", lambda: SemanticProvider()
    )
    response = client.get(
        "/api/v1/legislativo/precedentes"
        "?q=garantir%20seguran%C3%A7a%20noturna%20em%20espa%C3%A7os%20p%C3%BAblicos"
        "&tipo=INDICACAO&status=APROVADA"
    )

    assert response.status_code == 200
    assert response.json["modelo"] == "nomic-embed-text-test"
    assert response.json["fallbackUtilizado"] is False
    assert response.json["totalCandidatos"] == 1
    assert [item["id"] for item in response.json["content"]] == [related_id]
    assert response.json["content"][0]["similaridadeSemantica"] == 0.94
    assert "Proposição aprovada" in response.json["content"][0]["justificativas"]
    assert other_tenant_id not in {item["id"] for item in response.json["content"]}

    class UnavailableProvider:
        model = "unavailable"

        def similarities(self, _source, _candidates):
            from app.ai.duplicates import EmbeddingProviderError

            raise EmbeddingProviderError("Ollama indisponível no teste")

    monkeypatch.setattr(
        "app.legislative.precedents._precedent_provider", lambda: UnavailableProvider()
    )
    fallback = client.get(
        "/api/v1/legislativo/precedentes?q=ilumina%C3%A7%C3%A3o%20segura%20pra%C3%A7as"
    )
    assert fallback.status_code == 200
    assert fallback.json["fallbackUtilizado"] is True
    assert fallback.json["modelo"] == "gabflow-token-similarity-v1"
    assert related_id in {item["id"] for item in fallback.json["content"]}

    invalid_filter = client.get("/api/v1/legislativo/precedentes?q=tema&tipo=INVALIDO")
    assert invalid_filter.status_code == 422
