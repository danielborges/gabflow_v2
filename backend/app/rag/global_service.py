import hashlib
from datetime import UTC, datetime

from sqlalchemy import delete

from app.extensions import db
from app.models import (
    AuditLog,
    GlobalKnowledgeChunk,
    GlobalKnowledgeDocumentVersion,
    RagIngestionStatus,
)
from app.rag.service import (
    NonRetryableRagError,
    extract_document,
    rag_embedding_provider,
    split_chunks,
)
from app.rag.storage import global_rag_document_path

GLOBAL_RAG_INGESTION_EVENT = "IngestaoDocumentoRagGlobal"


def execute_global_ingestion(version: GlobalKnowledgeDocumentVersion) -> None:
    if version.ingestion_status == RagIngestionStatus.INDEXADO:
        return
    version.ingestion_status = RagIngestionStatus.PROCESSANDO
    version.started_at = datetime.now(UTC)
    version.error = None
    db.session.flush()

    extracted = extract_document(
        global_rag_document_path(
            version.storage_key,
            document_id=version.document_id,
            version_id=version.id,
        ),
        version.mime_type,
    )
    from flask import current_app

    if len(extracted.text.strip()) < current_app.config["RAG_MIN_TEXT_CHARS"]:
        raise NonRetryableRagError("O documento global não possui texto suficiente para indexação.")
    chunks = split_chunks(
        extracted.pages,
        current_app.config["RAG_CHUNK_SIZE_CHARS"],
        current_app.config["RAG_CHUNK_OVERLAP_CHARS"],
    )
    if not chunks:
        raise NonRetryableRagError("Não foi possível gerar fragmentos do documento global.")
    provider = rag_embedding_provider()
    vectors = provider.embeddings([item["content"] for item in chunks])
    if len(vectors) != len(chunks):
        raise RuntimeError("O provedor retornou embeddings globais incompletos.")

    db.session.execute(
        delete(GlobalKnowledgeChunk).where(GlobalKnowledgeChunk.version_id == version.id)
    )
    for item, vector in zip(chunks, vectors, strict=True):
        db.session.add(
            GlobalKnowledgeChunk(
                version_id=version.id,
                position=item["position"],
                content=item["content"],
                content_checksum=hashlib.sha256(item["content"].encode("utf-8")).hexdigest(),
                page_start=item["pageStart"],
                page_end=item["pageEnd"],
                section=item["section"],
                embedding=vector,
                embedding_model=provider.model,
            )
        )
    version.extracted_text = extracted.text
    version.page_count = len(extracted.pages)
    version.embedding_model = provider.model
    version.chunk_count = len(chunks)
    version.ingestion_status = RagIngestionStatus.INDEXADO
    version.indexed_at = datetime.now(UTC)
    db.session.add(
        AuditLog(
            tenant_id=None,
            user_id=version.created_by_id,
            action="rag_global.version_indexed",
            entity_type="rag_global_document_version",
            entity_id=str(version.id),
            after={
                "documentoId": str(version.document_id),
                "checksum": version.checksum,
                "modelo": provider.model,
                "fragmentos": version.chunk_count,
            },
        )
    )


def fail_global_ingestion(version: GlobalKnowledgeDocumentVersion, error_message: str) -> None:
    version.ingestion_status = RagIngestionStatus.FALHOU
    version.error = error_message[:2000]
