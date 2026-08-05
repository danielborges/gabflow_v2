from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import (
    AgendaEvent,
    AgendaEventStatus,
    AgendaEventType,
    Attachment,
    AttachmentScanStatus,
    AudioTranscription,
    AudioTranscriptionReviewStatus,
    AudioTranscriptionStatus,
    DocumentOcr,
    DocumentOcrReviewStatus,
    DocumentOcrStatus,
    ExternalAgency,
    LegislativeDocumentType,
    LegislativeDraft,
    LegislativeDraftStatus,
    LegislativeGenerationStatus,
    LegislativeTramitation,
    LegislativeTramitationStatus,
    OversightAction,
    OversightActionStatus,
    RagDocumentVersion,
    RagKnowledgeSource,
    RagKnowledgeSourceStatus,
    RequestSource,
    ServiceRequest,
    User,
)
from app.outbox.service import process_batch
from app.rag.operational_memory import (
    AGENDA_EVENT_ENTITY,
    AUDIO_TRANSCRIPTION_ENTITY,
    DOCUMENT_OCR_ENTITY,
    LEGISLATIVE_TRAMITATION_ENTITY,
    OVERSIGHT_ACTION_ENTITY,
    THEMATIC_MEMORY_ENTITY,
)

PASSWORD = "SenhaForte123!"  # noqa: S105
OTHER_PASSWORD = "OutraSenha123!"  # noqa: S105


def _login(client, *, tenant="gabinete-a", email="admin@teste.local", password=PASSWORD):
    response = client.post(
        "/api/v1/auth/login",
        json={"tenant": tenant, "email": email, "password": password},
    )
    assert response.status_code == 200
    return client.get_cookie("csrf_access_token").value


def _drain_outbox(app):
    with app.app_context():
        for index in range(12):
            result = process_batch(f"operational-expansion-{index}")
            if not result.claimed:
                break


def test_remaining_operational_modules_publish_only_approved_content(app):
    app.config["RAG_OPERATIONAL_MEMORY_ENABLED"] = True
    now = datetime.now(UTC)
    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == "admin@teste.local"))
        service_request = ServiceRequest(
            tenant_id=user.tenant_id,
            protocol="GF-2026-EXP001",
            source=RequestSource.PRESENCIAL,
            title="Demanda com evidências revisadas",
            description="Registro operacional da demanda.",
            created_by_id=user.id,
        )
        agency = ExternalAgency(
            tenant_id=user.tenant_id,
            name="Secretaria de Infraestrutura",
            active=True,
        )
        draft = LegislativeDraft(
            tenant_id=user.tenant_id,
            document_type=LegislativeDocumentType.INDICACAO,
            status=LegislativeDraftStatus.APROVADA,
            generation_status=LegislativeGenerationStatus.CONCLUIDA,
            title="Indicação para melhoria viária",
            content="Propõe melhoria viária no município.",
            protocol_number="LEG-2026-10",
            protocolled_at=now,
            current_tramitation_status=LegislativeTramitationStatus.EM_COMISSAO,
            created_by_id=user.id,
        )
        db.session.add_all([service_request, agency, draft])
        db.session.flush()
        tramitation = LegislativeTramitation(
            tenant_id=user.tenant_id,
            draft_id=draft.id,
            status=LegislativeTramitationStatus.EM_COMISSAO,
            stage="Comissão de Obras",
            destination="Comissão Permanente",
            external_reference="PAUTA-44",
            notes="Parecer técnico solicitado.",
            occurred_at=now,
            created_by_id=user.id,
        )
        audio_attachment = Attachment(
            tenant_id=user.tenant_id,
            request_id=service_request.id,
            storage_key="tenant/audio-evidence.ogg",
            original_name="reuniao.ogg",
            mime_type="audio/ogg",
            size_bytes=100,
            sha256="a" * 64,
            scan_status=AttachmentScanStatus.LIMPO,
            uploaded_by_id=user.id,
        )
        ocr_attachment = Attachment(
            tenant_id=user.tenant_id,
            request_id=service_request.id,
            storage_key="tenant/document-evidence.pdf",
            original_name="oficio.pdf",
            mime_type="application/pdf",
            size_bytes=200,
            sha256="b" * 64,
            scan_status=AttachmentScanStatus.LIMPO,
            uploaded_by_id=user.id,
        )
        db.session.add_all([tramitation, audio_attachment, ocr_attachment])
        db.session.flush()
        transcription = AudioTranscription(
            tenant_id=user.tenant_id,
            attachment_id=audio_attachment.id,
            request_id=service_request.id,
            status=AudioTranscriptionStatus.CONCLUIDA,
            review_status=AudioTranscriptionReviewStatus.EDITADA,
            provider="test",
            model="test",
            language="pt",
            transcript="Texto bruto que não deve ser utilizado.",
            reviewed_transcript=("Relato revisado sobre a necessidade de manutenção viária."),
            requested_by_id=user.id,
            reviewed_by_id=user.id,
            reviewed_at=now,
        )
        ocr = DocumentOcr(
            tenant_id=user.tenant_id,
            attachment_id=ocr_attachment.id,
            request_id=service_request.id,
            status=DocumentOcrStatus.CONCLUIDO,
            review_status=DocumentOcrReviewStatus.ACEITO,
            provider="test",
            model="test",
            language="por",
            extracted_text="Ofício bruto.",
            reviewed_text="Ofício revisado confirma o cronograma de manutenção.",
            requested_by_id=user.id,
            reviewed_by_id=user.id,
            reviewed_at=now,
        )
        agenda = AgendaEvent(
            tenant_id=user.tenant_id,
            event_type=AgendaEventType.REUNIAO,
            status=AgendaEventStatus.REALIZADO,
            title="Reunião comunitária de infraestrutura",
            description="Discussão temática.",
            starts_at=now,
            minutes="A comunidade priorizou iluminação e pavimentação.",
            participants=["Pessoa que não deve integrar a memória"],
            photos=["foto-privada.jpg"],
            pending_items=["Solicitar cronograma à secretaria"],
            created_by_id=user.id,
        )
        oversight = OversightAction(
            tenant_id=user.tenant_id,
            status=OversightActionStatus.CONCLUIDA,
            title="Fiscalização de obra viária",
            description="Vistoria do contrato de pavimentação.",
            occurred_at=now,
            agency_id=agency.id,
            findings=["Trecho com execução incompleta"],
            responsible_parties=["Nome que deve ser omitido"],
            photos=["fiscalizacao-privada.jpg"],
            report="Relatório conclui pela necessidade de correção do trecho.",
            follow_up_actions=["Requisitar plano de correção"],
            created_by_id=user.id,
        )
        db.session.add_all([transcription, ocr, agenda, oversight])
        db.session.commit()

    _drain_outbox(app)
    expected_types = {
        LEGISLATIVE_TRAMITATION_ENTITY,
        DOCUMENT_OCR_ENTITY,
        AUDIO_TRANSCRIPTION_ENTITY,
        AGENDA_EVENT_ENTITY,
        OVERSIGHT_ACTION_ENTITY,
    }
    with app.app_context():
        sources = {
            item.entity_type: item
            for item in db.session.scalars(
                select(RagKnowledgeSource).where(RagKnowledgeSource.entity_type.in_(expected_types))
            )
        }
        assert set(sources) == expected_types
        assert all(item.status == RagKnowledgeSourceStatus.ATIVA for item in sources.values())
        texts = {}
        for entity_type, source in sources.items():
            version = db.session.get(RagDocumentVersion, source.latest_version_id)
            texts[entity_type] = version.extracted_text
        assert "Comissão de Obras" in texts[LEGISLATIVE_TRAMITATION_ENTITY]
        assert "Ofício revisado" in texts[DOCUMENT_OCR_ENTITY]
        assert "Ofício bruto" not in texts[DOCUMENT_OCR_ENTITY]
        assert "Relato revisado" in texts[AUDIO_TRANSCRIPTION_ENTITY]
        assert "Texto bruto" not in texts[AUDIO_TRANSCRIPTION_ENTITY]
        assert "priorizou iluminação" in texts[AGENDA_EVENT_ENTITY]
        assert "Pessoa que não deve" not in texts[AGENDA_EVENT_ENTITY]
        assert "necessidade de correção" in texts[OVERSIGHT_ACTION_ENTITY]
        assert "Nome que deve" not in texts[OVERSIGHT_ACTION_ENTITY]


def test_thematic_structured_analytics_and_tenant_evaluation(app, client, monkeypatch):
    app.config["RAG_OPERATIONAL_MEMORY_ENABLED"] = True
    app.config["RAG_THEMATIC_MIN_GROUP_SIZE"] = 2
    csrf = _login(client)
    for index in range(3):
        response = client.post(
            "/api/v1/solicitacoes",
            json={
                "origem": "PRESENCIAL",
                "titulo": f"Iluminação pública {index}",
                "descricao": "Demanda sobre manutenção de luminárias.",
                "tema": "Iluminação pública",
                "prioridade": "ALTA" if index == 0 else "MEDIA",
            },
            headers={"X-CSRF-TOKEN": csrf},
        )
        assert response.status_code == 201
    structured = client.post(
        "/api/v1/assistente/consultas-estruturadas",
        json={
            "dataset": "SOLICITACOES",
            "metrica": "CONTAGEM",
            "agruparPor": "TEMA",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert structured.status_code == 200
    assert structured.json["metodo"] == "ESTRUTURADO"
    assert structured.json["tenantScoped"] is True
    assert structured.json["total"] == 3
    assert structured.json["itens"] == [{"grupo": "Iluminação pública", "valor": 3}]

    today = datetime.now(UTC).date()
    rebuilt = client.post(
        "/api/v1/rag/memorias-tematicas/reconstruir",
        json={
            "inicio": (today - timedelta(days=30)).isoformat(),
            "fim": today.isoformat(),
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert rebuilt.status_code == 202
    assert rebuilt.json["content"][0]["solicitacoes"] == 3
    assert "3 solicitações" in rebuilt.json["content"][0]["sintese"]
    _drain_outbox(app)

    with app.app_context():
        thematic_source = db.session.scalar(
            select(RagKnowledgeSource).where(
                RagKnowledgeSource.entity_type == THEMATIC_MEMORY_ENTITY
            )
        )
        assert thematic_source.status == RagKnowledgeSourceStatus.ATIVA
        expected_document_id = str(thematic_source.document_id)

    evidence_question = client.post(
        "/api/v1/assistente/avaliacoes/perguntas",
        json={
            "pergunta": "Quais temas aparecem nas demandas de iluminação?",
            "documentosEsperados": [expected_document_id],
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert evidence_question.status_code == 201
    refusal_question = client.post(
        "/api/v1/assistente/avaliacoes/perguntas",
        json={
            "pergunta": "Pergunta real sem resposta na base",
            "esperaRecusa": True,
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert refusal_question.status_code == 201

    def fake_answer(_tenant_id, _role, query, _limit):
        refusal = "sem resposta" in query
        return {
            "fontes": [] if refusal else [{"documentoId": expected_document_id}],
            "fundamentada": not refusal,
            "recusaConclusiva": refusal,
        }

    monkeypatch.setattr("app.rag.evaluation.answer_query", fake_answer)
    execution = client.post(
        "/api/v1/assistente/avaliacoes/executar",
        json={"k": 5},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert execution.status_code == 201
    assert execution.json["perguntas"] == 2
    assert execution.json["precisionAtK"] == 1
    assert execution.json["recallAtK"] == 1
    assert execution.json["groundedness"] == 0.5
    assert execution.json["precisaoCitacoes"] == 1
    assert execution.json["taxaFontesDesconexas"] == 0
    assert execution.json["acuraciaRecusa"] == 1

    other_csrf = _login(
        client,
        tenant="gabinete-b",
        email="admin-b@teste.local",
        password=OTHER_PASSWORD,
    )
    cross_tenant = client.post(
        "/api/v1/assistente/avaliacoes/perguntas",
        json={
            "pergunta": "Pergunta tentando referenciar outro tenant",
            "documentosEsperados": [expected_document_id],
        },
        headers={"X-CSRF-TOKEN": other_csrf},
    )
    assert cross_tenant.status_code == 422
    assert "não pertence ao tenant" in cross_tenant.json["message"]
