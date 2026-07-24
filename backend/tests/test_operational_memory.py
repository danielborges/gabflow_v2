import uuid

from sqlalchemy import select

from app.extensions import db
from app.models import (
    AuditLog,
    LegislativeDocumentType,
    LegislativeDraft,
    LegislativeGenerationStatus,
    OutboxEvent,
    RagChunk,
    RagDocument,
    RagDocumentLifecycle,
    RagDocumentVersion,
    RagKnowledgeSource,
    RagKnowledgeSourceStatus,
    RequestStatus,
    ServiceRequest,
    User,
)
from app.outbox.service import process_batch
from app.rag.operational_memory import (
    OPERATIONAL_MEMORY_EVENT,
    enqueue_operational_memory,
)

PASSWORD = "SenhaForte123!"  # noqa: S105


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@teste.local", "password": PASSWORD},
    )
    assert response.status_code == 200
    return client.get_cookie("csrf_access_token").value


def _drain_outbox(app):
    with app.app_context():
        for index in range(6):
            result = process_batch(f"operational-memory-{index}")
            if not result.claimed:
                break


def test_request_changes_become_versioned_minimized_private_memory(app, client):
    app.config["RAG_OPERATIONAL_MEMORY_ENABLED"] = True
    csrf = _login(client)
    created = client.post(
        "/api/v1/solicitacoes",
        json={
            "origem": "WHATSAPP",
            "titulo": "Falta de iluminação na praça",
            "descricao": (
                "Moradora ana@example.com, CPF 123.456.789-00, relata três postes "
                "apagados perto do coreto."
            ),
            "endereco": "Rua Particular, 123",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert created.status_code == 201

    with app.app_context():
        assert db.session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.event_type == OPERATIONAL_MEMORY_EVENT,
                OutboxEvent.aggregate_id == created.json["id"],
            )
        )

    _drain_outbox(app)
    with app.app_context():
        source = db.session.scalar(select(RagKnowledgeSource))
        assert source.status == RagKnowledgeSourceStatus.ATIVA
        assert source.source_module == "SOLICITACOES"
        assert source.source_version >= 1
        initial_source_version = source.source_version
        document = db.session.get(RagDocument, source.document_id)
        version = db.session.get(RagDocumentVersion, source.latest_version_id)
        chunks = list(
            db.session.scalars(
                select(RagChunk).where(RagChunk.version_id == version.id)
            )
        )
        indexed_text = " ".join(chunk.content for chunk in chunks)
        assert document.active is True
        assert version.lifecycle_status == RagDocumentLifecycle.VIGENTE
        assert "ana@example.com" not in indexed_text
        assert "123.456.789-00" not in indexed_text
        assert "Rua Particular" not in indexed_text
        assert "[DADO_PESSOAL_REMOVIDO]" in indexed_text

    interaction = client.post(
        f"/api/v1/solicitacoes/{created.json['id']}/interacoes",
        json={
            "tipo": "RETORNO",
            "canal": "TELEFONE",
            "direcao": "ENTRADA",
            "conteudo": "A iluminação segue apagada; retorno pelo (32) 99999-8888.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert interaction.status_code == 201
    _drain_outbox(app)

    with app.app_context():
        source = db.session.scalar(select(RagKnowledgeSource))
        versions = list(
            db.session.scalars(
                select(RagDocumentVersion)
                .where(RagDocumentVersion.document_id == source.document_id)
                .order_by(RagDocumentVersion.version_number)
            )
        )
        assert source.source_version == initial_source_version + 1
        assert all(
            item.lifecycle_status == RagDocumentLifecycle.HISTORICO
            for item in versions[:-1]
        )
        assert versions[-1].lifecycle_status == RagDocumentLifecycle.VIGENTE
        assert "(32) 99999-8888" not in versions[-1].extracted_text
        stable_version = source.source_version
        enqueue_operational_memory(
            source.tenant_id, source.entity_type, source.entity_id
        )
        db.session.commit()
    _drain_outbox(app)
    with app.app_context():
        source = db.session.scalar(select(RagKnowledgeSource))
        assert source.source_version == stable_version


def test_ineligible_entity_is_removed_from_active_retrieval_without_auditing_content(
    app, client
):
    app.config["RAG_OPERATIONAL_MEMORY_ENABLED"] = True
    csrf = _login(client)
    created = client.post(
        "/api/v1/solicitacoes",
        json={
            "origem": "PRESENCIAL",
            "titulo": "Pedido posteriormente cancelado",
            "descricao": "Conteúdo sigiloso que não deve aparecer na auditoria.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert created.status_code == 201
    _drain_outbox(app)

    with app.app_context():
        item = db.session.get(ServiceRequest, uuid.UUID(created.json["id"]))
        item.status = RequestStatus.CANCELADA
        db.session.commit()
    _drain_outbox(app)

    with app.app_context():
        source = db.session.scalar(select(RagKnowledgeSource))
        document = db.session.get(RagDocument, source.document_id)
        audit = db.session.scalar(
            select(AuditLog)
            .where(AuditLog.action == "rag_operational_memory.ineligible")
            .order_by(AuditLog.created_at.desc())
        )
        assert source.status == RagKnowledgeSourceStatus.INELEGIVEL
        assert source.eligibility_reason == "ENTITY_CANCELLED"
        assert document.active is False
        assert "sigiloso" not in str(audit.after).lower()


def test_completed_legislative_draft_becomes_operational_memory(app):
    app.config["RAG_OPERATIONAL_MEMORY_ENABLED"] = True
    with app.app_context():
        user = db.session.scalar(
            select(User).where(User.email == "admin@teste.local")
        )
        draft = LegislativeDraft(
            tenant_id=user.tenant_id,
            document_type=LegislativeDocumentType.INDICACAO,
            generation_status=LegislativeGenerationStatus.CONCLUIDA,
            title="Indicação para iluminação eficiente",
            content="Indica a substituição de luminárias por tecnologia LED.",
            justification="A medida reduz falhas e consumo de energia.",
            legal_basis=["Lei Orgânica Municipal"],
            created_by_id=user.id,
        )
        db.session.add(draft)
        db.session.commit()
        draft_id = draft.id

    _drain_outbox(app)
    with app.app_context():
        source = db.session.scalar(
            select(RagKnowledgeSource).where(
                RagKnowledgeSource.entity_id == draft_id
            )
        )
        version = db.session.get(RagDocumentVersion, source.latest_version_id)
        assert source.source_module == "LEGISLATIVO"
        assert source.status == RagKnowledgeSourceStatus.ATIVA
        assert "tecnologia LED" in version.extracted_text
        assert version.lifecycle_status == RagDocumentLifecycle.VIGENTE
