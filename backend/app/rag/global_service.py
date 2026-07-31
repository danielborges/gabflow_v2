import hashlib
from datetime import UTC, datetime

from flask import current_app
from sqlalchemy import delete, select

from app.extensions import db
from app.models import (
    AuditLog,
    GlobalCatalogStatus,
    GlobalKnowledgeChunk,
    GlobalKnowledgeDocumentVersion,
    GlobalVersionStatus,
    RagIngestionStatus,
)
from app.rag.content_security import (
    ContentSecurityStatus,
    ContentSecuritySurface,
    apply_approved_review,
    apply_content_security_decision,
    assess_content_security,
)
from app.rag.service import (
    NonRetryableRagError,
    extract_document,
    rag_embedding_provider,
    split_chunks,
)
from app.rag.storage import global_rag_document_path
from app.security.malware import (
    MalwareDetectedError,
    MalwareScannerUnavailable,
    apply_malware_scan,
    require_clean_stored_file,
)

GLOBAL_RAG_INGESTION_EVENT = "IngestaoDocumentoRagGlobal"


def execute_global_ingestion(version: GlobalKnowledgeDocumentVersion) -> None:
    if version.ingestion_status == RagIngestionStatus.INDEXADO:
        return
    version.ingestion_status = RagIngestionStatus.PROCESSANDO
    version.started_at = datetime.now(UTC)
    version.error = None
    db.session.flush()

    document_path = global_rag_document_path(
        version.storage_key,
        document_id=version.document_id,
        version_id=version.id,
    )
    if not _rescan_before_parsing(version, document_path):
        return
    extracted = extract_document(document_path, version.mime_type, encryption_scope="global")
    security_decision = apply_approved_review(
        version,
        assess_content_security(
            extracted.text,
            surface=ContentSecuritySurface.DOCUMENT_BODY,
            metadata={
                "filename": version.original_name,
                "mimeType": version.mime_type,
                "sourceUrl": version.source_url,
                "documentType": version.document.document_type,
            },
        ),
    )
    apply_content_security_decision(version, security_decision)
    if security_decision.status != ContentSecurityStatus.CLEAN:
        quarantine_global_ingestion(version, security_decision)
        return
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
                "segurancaConteudo": {
                    "status": version.security_status.value,
                    "action": version.security_action.value,
                    "score": round(version.security_score, 4),
                    "policyVersion": version.security_policy_version,
                    "detectorVersion": version.security_detector_version,
                },
            },
        )
    )


def quarantine_global_ingestion(
    version: GlobalKnowledgeDocumentVersion,
    security_decision,
) -> None:
    now = datetime.now(UTC)
    db.session.execute(
        delete(GlobalKnowledgeChunk).where(GlobalKnowledgeChunk.version_id == version.id)
    )
    version.extracted_text = None
    version.page_count = None
    version.embedding_model = None
    version.chunk_count = 0
    version.indexed_at = None
    version.ingestion_status = RagIngestionStatus.FALHOU
    version.error = (
        "Conteúdo retido pela política de segurança; revisão autorizada necessária."
        if security_decision.risky
        else "Avaliação de segurança inconclusiva; reprocessamento necessário."
    )
    version.security_quarantined_at = now
    version.security_purged_at = now
    was_published = version.publication_status == GlobalVersionStatus.PUBLICADA
    if was_published:
        version.publication_status = GlobalVersionStatus.SUSPENSA
        another_published = db.session.scalar(
            select(GlobalKnowledgeDocumentVersion.id)
            .where(
                GlobalKnowledgeDocumentVersion.document.has(
                    collection_id=version.document.collection_id
                ),
                GlobalKnowledgeDocumentVersion.id != version.id,
                GlobalKnowledgeDocumentVersion.publication_status == GlobalVersionStatus.PUBLICADA,
            )
            .limit(1)
        )
        if another_published is None:
            version.document.collection.status = GlobalCatalogStatus.SUSPENSA
    db.session.add(
        AuditLog(
            tenant_id=None,
            user_id=version.created_by_id,
            action="rag_global.version_security_quarantined",
            entity_type="rag_global_document_version",
            entity_id=str(version.id),
            after={
                "documentoId": str(version.document_id),
                "status": security_decision.status.value,
                "action": security_decision.action.value,
                "score": round(security_decision.score, 4),
                "signals": list(security_decision.signals),
                "policyVersion": security_decision.policy_version,
                "contentChecksum": security_decision.content_checksum,
                "derivedArtifactsPurged": True,
            },
        )
    )


def _rescan_before_parsing(version, path) -> bool:
    try:
        scan = require_clean_stored_file(
            path,
            version.mime_type,
            version.checksum,
            encryption_scope="global",
        )
    except MalwareDetectedError:
        now = datetime.now(UTC)
        was_published = version.publication_status == GlobalVersionStatus.PUBLICADA
        version.malware_scan_status = "INFECTED"
        version.malware_scan_provider = current_app.config["MALWARE_SCANNER_PROVIDER"]
        version.malware_scan_error_code = "MALWARE_OR_INTEGRITY_DETECTED"
        version.malware_scanned_at = now
        db.session.execute(
            delete(GlobalKnowledgeChunk).where(GlobalKnowledgeChunk.version_id == version.id)
        )
        version.extracted_text = None
        version.page_count = None
        version.embedding_model = None
        version.chunk_count = 0
        version.indexed_at = None
        version.security_purged_at = now
        version.ingestion_status = RagIngestionStatus.FALHOU
        version.publication_status = GlobalVersionStatus.SUSPENSA
        if was_published:
            another_published = db.session.scalar(
                select(GlobalKnowledgeDocumentVersion.id)
                .where(
                    GlobalKnowledgeDocumentVersion.document.has(
                        collection_id=version.document.collection_id
                    ),
                    GlobalKnowledgeDocumentVersion.id != version.id,
                    GlobalKnowledgeDocumentVersion.publication_status
                    == GlobalVersionStatus.PUBLICADA,
                )
                .limit(1)
            )
            if another_published is None:
                version.document.collection.status = GlobalCatalogStatus.SUSPENSA
        version.error = "Arquivo bloqueado pela verificacao antimalware."
        db.session.add(
            AuditLog(
                tenant_id=None,
                user_id=version.created_by_id,
                action="rag_global.version_malware_quarantined",
                entity_type="rag_global_document_version",
                entity_id=str(version.id),
                after={"derivedArtifactsPurged": True, "status": "INFECTED"},
            )
        )
        return False
    except MalwareScannerUnavailable as error:
        version.malware_scan_status = "INDETERMINATE"
        version.malware_scan_provider = current_app.config["MALWARE_SCANNER_PROVIDER"]
        version.malware_scan_error_code = "MALWARE_SCANNER_UNAVAILABLE"
        version.malware_scanned_at = datetime.now(UTC)
        raise RuntimeError("Scanner antimalware indisponivel; tente novamente.") from error
    apply_malware_scan(version, scan)
    return True


def fail_global_ingestion(version: GlobalKnowledgeDocumentVersion, error_message: str) -> None:
    version.ingestion_status = RagIngestionStatus.FALHOU
    version.error = error_message[:2000]
