import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.extensions import db
from app.models import (
    RagChunk,
    RagDocument,
    RagDocumentAccess,
    RagDocumentLifecycle,
    RagDocumentVersion,
    RagIngestionStatus,
    Role,
    Tenant,
    User,
)
from app.rag.content_security import ContentSecurityAction, ContentSecurityStatus
from app.rag.hybrid_search import postgres_hybrid_candidates
from app.tenant_context import tenant_context

pytestmark = pytest.mark.postgres
TEST_PASSWORD_HASH = "integration-test-only"  # noqa: S105


def test_postgres_hybrid_search_fuses_fts_and_pgvector_without_crossing_tenants(
    postgres_app,
):
    with postgres_app.app_context():
        tenant_a, user_a = _tenant("Busca híbrida A")
        tenant_b, user_b = _tenant("Busca híbrida B")
        db.session.commit()

        query_vector = [1.0] + ([0.0] * 127)
        irrelevant_vector = [0.0, 1.0] + ([0.0] * 126)
        old_relevant = _chunk(
            tenant_a,
            user_a,
            "Plano histórico de iluminação",
            (
                "A manutenção preventiva da iluminação pública deve priorizar "
                "segurança e eficiência energética nos bairros."
            ),
            query_vector,
            indexed_at=datetime.now(UTC) - timedelta(days=900),
        )
        _chunk(
            tenant_a,
            user_a,
            "Comunicado recente",
            "O almoxarifado recebeu uniformes e materiais de escritório.",
            irrelevant_vector,
            indexed_at=datetime.now(UTC),
        )
        foreign = _chunk(
            tenant_b,
            user_b,
            "Fonte de outro tenant",
            "Manutenção preventiva da iluminação pública com segurança.",
            query_vector,
            indexed_at=datetime.now(UTC),
        )
        db.session.commit()

        stored = (
            db.session.execute(
                text(
                    """
                SELECT
                    vector_dims(embedding_vector) AS dimensions,
                    search_vector @@
                        websearch_to_tsquery('portuguese', :query) AS lexical_match
                FROM rag_chunks
                WHERE id = CAST(:chunk_id AS uuid)
                """
                ),
                {
                    "chunk_id": str(old_relevant.id),
                    "query": "manutenção preventiva iluminação pública",
                },
            )
            .mappings()
            .one()
        )
        assert stored == {"dimensions": 128, "lexical_match": True}

        with tenant_context(tenant_a.id):
            candidates = postgres_hybrid_candidates(
                tenant_a.id,
                "admin",
                "manutenção preventiva iluminação pública segurança",
                query_vector,
                "test-hybrid-128",
                limit=10,
            )

        assert candidates is not None
        assert candidates[0].chunk.id == old_relevant.id
        assert set(candidates[0].channels) == {"FTS", "PGVECTOR"}
        assert candidates[0].database_semantic_score == pytest.approx(1.0)
        assert all(candidate.chunk.id != foreign.id for candidate in candidates)


def test_postgres_hybrid_search_applies_documentary_filters_before_ranking(
    postgres_app,
):
    with postgres_app.app_context():
        tenant, user = _tenant("Filtros documentais")
        query_vector = [1.0] + ([0.0] * 127)
        decree = _chunk(
            tenant,
            user,
            "Decreto de mobilidade urbana",
            "O decreto regulamenta transporte coletivo e circulação urbana.",
            query_vector,
            indexed_at=datetime.now(UTC),
            document_type="DECRETO",
            agency="Secretaria de Mobilidade",
        )
        _chunk(
            tenant,
            user,
            "Instrução tributária",
            "A instrução trata de imposto e arrecadação municipal.",
            query_vector,
            indexed_at=datetime.now(UTC),
            document_type="INSTRUCAO",
            agency="Secretaria de Finanças",
        )
        db.session.commit()

        with tenant_context(tenant.id):
            candidates = postgres_hybrid_candidates(
                tenant.id,
                "admin",
                "regulamentação municipal",
                query_vector,
                "test-hybrid-128",
                limit=10,
                filters={
                    "tipoDocumento": "DECRETO",
                    "orgao": "Mobilidade",
                    "temaBusca": "transporte OR circulacao",
                },
            )

        assert candidates is not None
        assert [candidate.chunk.id for candidate in candidates] == [decree.id]


def _tenant(label):
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant(name=label, slug=f"hybrid-{suffix}")
    db.session.add(tenant)
    db.session.flush()
    user = User(
        tenant_id=tenant.id,
        name=f"Admin {label}",
        email=f"hybrid-{suffix}@test.local",
        password_hash=TEST_PASSWORD_HASH,
        role=Role.ADMIN,
    )
    db.session.add(user)
    db.session.flush()
    return tenant, user


def _chunk(
    tenant,
    user,
    title,
    content,
    embedding,
    *,
    indexed_at,
    document_type="LEGISLACAO",
    agency=None,
):
    document = RagDocument(
        tenant_id=tenant.id,
        title=title,
        document_type=document_type,
        agency=agency,
        access_level=RagDocumentAccess.INTERNO,
        active=True,
        created_by_id=user.id,
    )
    db.session.add(document)
    db.session.flush()
    version_id = uuid.uuid4()
    version = RagDocumentVersion(
        id=version_id,
        tenant_id=tenant.id,
        document_id=document.id,
        version_number=1,
        version_label="1",
        lifecycle_status=RagDocumentLifecycle.VIGENTE,
        ingestion_status=RagIngestionStatus.INDEXADO,
        malware_scan_status="CLEAN",
        security_status=ContentSecurityStatus.CLEAN,
        security_action=ContentSecurityAction.ALLOW,
        storage_key=(f"tenants/{tenant.id}/rag/{document.id}/{version_id}/documento.txt"),
        original_name="documento.txt",
        mime_type="text/plain",
        size_bytes=len(content.encode()),
        checksum=hashlib.sha256(content.encode()).hexdigest(),
        extracted_text=content,
        page_count=1,
        embedding_model="test-hybrid-128",
        chunk_count=1,
        indexed_at=indexed_at,
        created_by_id=user.id,
    )
    db.session.add(version)
    db.session.flush()
    chunk = RagChunk(
        tenant_id=tenant.id,
        version_id=version.id,
        position=0,
        content=content,
        content_checksum=hashlib.sha256(content.encode()).hexdigest(),
        page_start=1,
        page_end=1,
        embedding=embedding,
        embedding_model="test-hybrid-128",
    )
    db.session.add(chunk)
    return chunk
