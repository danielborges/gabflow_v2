import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from docx import Document
from flask import current_app
from sqlalchemy import delete, select, update

from app.ai.duplicates import OllamaEmbeddingProvider
from app.ai.ocr import OCR_MIME_TYPES, NonRetryableOcrError, ocr_provider
from app.extensions import db
from app.models import (
    AuditLog,
    NotificationType,
    OutboxEvent,
    RagChunk,
    RagDocumentLifecycle,
    RagDocumentVersion,
    RagIngestionStatus,
    RagKnowledgeSource,
    RagKnowledgeSourceStatus,
)
from app.notifications.service import notify_user
from app.rag.content_security import (
    ContentSecurityStatus,
    ContentSecuritySurface,
    apply_approved_review,
    apply_content_security_decision,
    assess_content_security,
)
from app.rag.isolated_parser import (
    IsolatedParserError,
    NonRetryableIsolatedParserError,
    parse_document_isolated,
)
from app.rag.storage import rag_document_path
from app.security.malware import (
    MalwareDetectedError,
    MalwareScannerUnavailable,
    apply_malware_scan,
    require_clean_stored_file,
)

RAG_INGESTION_EVENT = "IngestaoDocumentoRag"


class RagIngestionError(RuntimeError):
    pass


class NonRetryableRagError(RagIngestionError):
    pass


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    pages: list[dict]


def enqueue_ingestion(version: RagDocumentVersion) -> None:
    db.session.add(
        OutboxEvent(
            tenant_id=version.tenant_id,
            event_type=RAG_INGESTION_EVENT,
            aggregate_type="DocumentoRag",
            aggregate_id=str(version.id),
            payload={"versionId": str(version.id)},
        )
    )


def requeue_ingestion(version: RagDocumentVersion) -> None:
    version.ingestion_status = RagIngestionStatus.PENDENTE
    version.error = None
    version.started_at = None
    version.indexed_at = None
    enqueue_ingestion(version)


def execute_ingestion(
    version: RagDocumentVersion,
    *,
    send_notification: bool = True,
) -> None:
    if version.ingestion_status == RagIngestionStatus.INDEXADO:
        return
    operational_source = db.session.execute(
        select(RagKnowledgeSource)
        .where(
            RagKnowledgeSource.tenant_id == version.tenant_id,
            RagKnowledgeSource.latest_version_id == version.id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if (
        operational_source is not None
        and operational_source.status != RagKnowledgeSourceStatus.PENDENTE
    ):
        version.ingestion_status = RagIngestionStatus.FALHOU
        version.error = "Ingestão cancelada porque a fonte operacional não está pendente."
        return
    version.ingestion_status = RagIngestionStatus.PROCESSANDO
    version.started_at = datetime.now(UTC)
    version.error = None
    db.session.flush()

    document_path = rag_document_path(
        version.storage_key,
        tenant_id=version.tenant_id,
        document_id=version.document_id,
        version_id=version.id,
    )
    if not _rescan_before_parsing(version, document_path, operational_source):
        return
    extracted = extract_document(
        document_path,
        version.mime_type,
        encryption_scope=f"tenant:{version.tenant_id}",
    )
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
        quarantine_ingestion(
            version,
            security_decision,
            operational_source,
            send_notification=send_notification,
        )
        return
    if len(extracted.text.strip()) < current_app.config["RAG_MIN_TEXT_CHARS"]:
        raise NonRetryableRagError("O documento não possui texto suficiente para indexação.")
    chunks = split_chunks(
        extracted.pages,
        current_app.config["RAG_CHUNK_SIZE_CHARS"],
        current_app.config["RAG_CHUNK_OVERLAP_CHARS"],
    )
    if not chunks:
        raise NonRetryableRagError("Não foi possível gerar fragmentos do documento.")
    provider = rag_embedding_provider()
    vectors = provider.embeddings([item["content"] for item in chunks])
    if len(vectors) != len(chunks):
        raise RagIngestionError("O provedor retornou embeddings incompletos.")

    db.session.execute(delete(RagChunk).where(RagChunk.version_id == version.id))
    for item, vector in zip(chunks, vectors, strict=True):
        db.session.add(
            RagChunk(
                tenant_id=version.tenant_id,
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
    if operational_source is not None:
        db.session.execute(
            update(RagDocumentVersion)
            .where(
                RagDocumentVersion.tenant_id == version.tenant_id,
                RagDocumentVersion.document_id == version.document_id,
                RagDocumentVersion.id != version.id,
                RagDocumentVersion.lifecycle_status == RagDocumentLifecycle.VIGENTE,
            )
            .values(lifecycle_status=RagDocumentLifecycle.HISTORICO)
        )
        version.lifecycle_status = RagDocumentLifecycle.VIGENTE
        operational_source.status = RagKnowledgeSourceStatus.ATIVA
        operational_source.eligibility_reason = None
        operational_source.error_code = None
        operational_source.error_message = None
        operational_source.sync_attempts = 0
        operational_source.quarantined_at = None
        from app.rag.operational_memory import compact_operational_history

        compact_operational_history(operational_source)
    details = {
        "documentoId": str(version.document_id),
        "versaoId": str(version.id),
        "checksum": version.checksum,
        "modelo": provider.model,
        "paginas": version.page_count,
        "fragmentos": version.chunk_count,
        "segurancaConteudo": {
            "status": version.security_status.value,
            "action": version.security_action.value,
            "score": round(version.security_score, 4),
            "policyVersion": version.security_policy_version,
            "detectorVersion": version.security_detector_version,
        },
    }
    db.session.add(
        AuditLog(
            tenant_id=version.tenant_id,
            user_id=version.created_by_id,
            action="rag_document.indexed",
            entity_type="rag_document_version",
            entity_id=str(version.id),
            after=details,
        )
    )
    if send_notification:
        notify_user(
            version.tenant_id,
            version.created_by_id,
            NotificationType.SISTEMA,
            "Documento indexado",
            f"{version.original_name} está disponível na base documental.",
            "rag_document_version",
            version.id,
        )


def quarantine_ingestion(
    version: RagDocumentVersion,
    security_decision,
    operational_source: RagKnowledgeSource | None = None,
    *,
    send_notification: bool = True,
) -> None:
    now = datetime.now(UTC)
    db.session.execute(delete(RagChunk).where(RagChunk.version_id == version.id))
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
    if version.lifecycle_status == RagDocumentLifecycle.VIGENTE:
        version.lifecycle_status = RagDocumentLifecycle.RASCUNHO
    if operational_source is not None:
        apply_content_security_decision(operational_source, security_decision)
        operational_source.status = (
            RagKnowledgeSourceStatus.QUARENTENA
            if security_decision.risky
            else RagKnowledgeSourceStatus.ERRO
        )
        operational_source.eligibility_reason = (
            "PROMPT_INJECTION_DETECTED"
            if security_decision.risky
            else "CONTENT_SECURITY_INDETERMINATE"
        )
        operational_source.error_code = (
            "CONTENT_SECURITY_REVIEW_REQUIRED"
            if security_decision.risky
            else "CONTENT_SECURITY_RETRY_REQUIRED"
        )
        operational_source.quarantined_at = now if security_decision.risky else None
    db.session.add(
        AuditLog(
            tenant_id=version.tenant_id,
            user_id=version.created_by_id,
            action="rag_document.security_quarantined",
            entity_type="rag_document_version",
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
    if send_notification:
        notify_user(
            version.tenant_id,
            version.created_by_id,
            NotificationType.SISTEMA,
            "Documento em quarentena",
            "Uma versão foi retida pela política de segurança e requer revisão.",
            "rag_document_version",
            version.id,
        )


def _rescan_before_parsing(version, path: Path, operational_source) -> bool:
    try:
        scan = require_clean_stored_file(
            path,
            version.mime_type,
            version.checksum,
            encryption_scope=f"tenant:{version.tenant_id}",
        )
    except MalwareDetectedError:
        now = datetime.now(UTC)
        version.malware_scan_status = "INFECTED"
        version.malware_scan_provider = current_app.config["MALWARE_SCANNER_PROVIDER"]
        version.malware_scan_error_code = "MALWARE_OR_INTEGRITY_DETECTED"
        version.malware_scanned_at = now
        db.session.execute(delete(RagChunk).where(RagChunk.version_id == version.id))
        version.extracted_text = None
        version.page_count = None
        version.embedding_model = None
        version.chunk_count = 0
        version.indexed_at = None
        version.security_purged_at = now
        version.ingestion_status = RagIngestionStatus.FALHOU
        version.lifecycle_status = RagDocumentLifecycle.RASCUNHO
        version.error = "Arquivo bloqueado pela verificacao antimalware."
        if operational_source is not None:
            operational_source.status = RagKnowledgeSourceStatus.QUARENTENA
            operational_source.eligibility_reason = "MALWARE_DETECTED"
            operational_source.error_code = "MALWARE_REVIEW_REQUIRED"
            operational_source.quarantined_at = now
        db.session.add(
            AuditLog(
                tenant_id=version.tenant_id,
                user_id=version.created_by_id,
                action="rag_document.malware_quarantined",
                entity_type="rag_document_version",
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
        raise RagIngestionError("Scanner antimalware indisponivel; tente novamente.") from error
    apply_malware_scan(version, scan)
    return True


def fail_ingestion(
    version: RagDocumentVersion,
    error_message: str,
    *,
    attempts: int = 1,
) -> None:
    version.ingestion_status = RagIngestionStatus.FALHOU
    version.error = error_message[:2000]
    operational_source = db.session.execute(
        select(RagKnowledgeSource)
        .where(
            RagKnowledgeSource.tenant_id == version.tenant_id,
            RagKnowledgeSource.latest_version_id == version.id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if operational_source is None:
        return
    operational_source.status = RagKnowledgeSourceStatus.ERRO
    operational_source.eligibility_reason = "INGESTION_FAILED"
    operational_source.error_code = "RAG_INGESTION_EXHAUSTED"
    operational_source.error_message = re.sub(r"\s+", " ", str(error_message or "")).strip()[:500]
    operational_source.sync_attempts = max(1, attempts)
    db.session.add(
        AuditLog(
            tenant_id=version.tenant_id,
            user_id=None,
            action="rag_operational_memory.ingestion_failed",
            entity_type="rag_knowledge_source",
            entity_id=str(operational_source.id),
            after={
                "status": operational_source.status.value,
                "codigoErro": operational_source.error_code,
                "tentativas": operational_source.sync_attempts,
                "versaoId": str(version.id),
            },
        )
    )


def extract_document(
    path: Path,
    mime_type: str,
    *,
    encryption_scope: str | None = None,
) -> ExtractedDocument:
    if encryption_scope:
        from app.security.encryption import plaintext_file, read_plaintext

        if current_app.config["DOCUMENT_PARSER_ISOLATION_ENABLED"]:
            try:
                result = parse_document_isolated(
                    path,
                    mime_type,
                    content=read_plaintext(path, encryption_scope),
                )
            except NonRetryableIsolatedParserError as error:
                raise NonRetryableRagError(str(error)) from error
            except IsolatedParserError as error:
                raise RagIngestionError(str(error)) from error
            return ExtractedDocument(text=result.text, pages=result.pages)
        with plaintext_file(path, encryption_scope, suffix=path.suffix) as plaintext_path:
            return extract_document(plaintext_path, mime_type)
    if current_app.config["DOCUMENT_PARSER_ISOLATION_ENABLED"]:
        try:
            result = parse_document_isolated(path, mime_type)
        except NonRetryableIsolatedParserError as error:
            raise NonRetryableRagError(str(error)) from error
        except IsolatedParserError as error:
            raise RagIngestionError(str(error)) from error
        return ExtractedDocument(text=result.text, pages=result.pages)
    if mime_type == "text/plain":
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise NonRetryableRagError("O arquivo de texto deve estar em UTF-8.") from error
        return ExtractedDocument(text=text, pages=[{"pagina": 1, "texto": text}])
    if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        try:
            paragraphs = [
                item.text.strip() for item in Document(path).paragraphs if item.text.strip()
            ]
        except Exception as error:
            raise NonRetryableRagError("Não foi possível ler o documento DOCX.") from error
        text = "\n\n".join(paragraphs)
        return ExtractedDocument(text=text, pages=[{"pagina": 1, "texto": text}])
    if mime_type in OCR_MIME_TYPES:
        try:
            result = ocr_provider().extract(path, mime_type)
        except NonRetryableOcrError as error:
            raise NonRetryableRagError(str(error)) from error
        return ExtractedDocument(text=result.text, pages=result.pages)
    raise NonRetryableRagError("Tipo de documento não compatível com a ingestão.")


def split_chunks(pages: list[dict], size: int, overlap: int) -> list[dict]:
    chunks = []
    position = 0
    for page in pages:
        text = re.sub(r"[ \t]+", " ", str(page.get("texto") or "")).strip()
        if not text:
            continue
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            if end < len(text):
                boundary = text.rfind(" ", start + size // 2, end)
                if boundary > start:
                    end = boundary
            content = text[start:end].strip()
            if content:
                chunks.append(
                    {
                        "position": position,
                        "content": content,
                        "pageStart": int(page.get("pagina") or 1),
                        "pageEnd": int(page.get("pagina") or 1),
                        "section": page.get("secao"),
                    }
                )
                position += 1
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
    return chunks


class LocalHashEmbeddingProvider:
    model = "gabflow-hash-embedding-v1"

    def embeddings(self, texts: list[str]) -> list[list[float]]:
        return [_hash_embedding(text) for text in texts]


def rag_embedding_provider():
    if current_app.config["RAG_EMBEDDING_PROVIDER"].lower() == "local":
        return LocalHashEmbeddingProvider()
    return OllamaEmbeddingProvider(
        current_app.config["OLLAMA_BASE_URL"],
        current_app.config["AI_EMBEDDING_MODEL"],
        current_app.config["RAG_INGESTION_TIMEOUT_SECONDS"],
        current_app.config["AI_EMBEDDING_BATCH_SIZE"],
    )


def _hash_embedding(text: str, dimensions: int = 128) -> list[float]:
    tokens = re.findall(r"[a-zA-ZÀ-ÿ0-9]+", text.lower())
    counts = Counter(tokens)
    vector = [0.0] * dimensions
    for token, count in counts.items():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += float(count)
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 8) for value in vector]
