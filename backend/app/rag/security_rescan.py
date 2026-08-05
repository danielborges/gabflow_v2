import uuid
from datetime import UTC, datetime

from flask import current_app
from sqlalchemy import delete, func, select, update

from app.attachments import AttachmentError, attachment_path
from app.extensions import db
from app.models import (
    Attachment,
    AttachmentScanStatus,
    AudioTranscriptionStatus,
    AuditLog,
    ContentSecurityAction,
    ContentSecurityStatus,
    DocumentOcrStatus,
    GlobalKnowledgeChunk,
    GlobalKnowledgeDocumentVersion,
    OutboxEvent,
    RagChunk,
    RagDocumentLifecycle,
    RagDocumentVersion,
    RagIngestionStatus,
    RagKnowledgeSource,
    RagKnowledgeSourceStatus,
    RagSecurityRescanRun,
    RagSecurityRescanScope,
    RagSecurityRescanStatus,
)
from app.rag.global_service import execute_global_ingestion
from app.rag.operational_memory import (
    AUDIO_TRANSCRIPTION_ENTITY,
    DOCUMENT_OCR_ENTITY,
    execute_operational_memory_sync,
)
from app.rag.projectors import ProjectorAction
from app.rag.service import NonRetryableRagError, execute_ingestion
from app.rag.storage import (
    NonRetryableFileError,
    global_rag_document_path,
    rag_document_path,
)
from app.security.encryption import ensure_encrypted
from app.security.malware import (
    MalwareDetectedError,
    MalwareScannerUnavailable,
    apply_malware_scan,
    require_clean_stored_file,
)

SECURITY_RESCAN_EVENT = "RevarreduraSegurancaRag"
ACTIVE_RESCAN_STATUSES = {
    RagSecurityRescanStatus.PENDENTE,
    RagSecurityRescanStatus.PROCESSANDO,
}


class SecurityRescanConflictError(RuntimeError):
    pass


def create_security_rescan(
    *,
    tenant_id: uuid.UUID | None,
    actor_id: uuid.UUID,
    scope: RagSecurityRescanScope,
    batch_size: int = 20,
) -> RagSecurityRescanRun:
    if not 1 <= batch_size <= 100:
        raise ValueError("O lote deve possuir entre 1 e 100 itens.")
    if (scope == RagSecurityRescanScope.TENANT) != (tenant_id is not None):
        raise ValueError("Escopo da revarredura incompatível com o tenant.")
    active = db.session.scalar(
        select(RagSecurityRescanRun.id).where(
            RagSecurityRescanRun.scope == scope,
            RagSecurityRescanRun.tenant_id.is_(None)
            if tenant_id is None
            else RagSecurityRescanRun.tenant_id == tenant_id,
            RagSecurityRescanRun.status.in_(ACTIVE_RESCAN_STATUSES),
        )
    )
    if active is not None:
        raise SecurityRescanConflictError("Já existe uma revarredura ativa para este escopo.")

    cutoff = datetime.now(UTC)
    if scope == RagSecurityRescanScope.TENANT:
        total = _tenant_target_count(tenant_id, cutoff)
        phase = "PRIVATE"
        _invalidate_tenant_targets(tenant_id, cutoff)
    else:
        total = _global_target_count(cutoff)
        phase = "GLOBAL"
        _invalidate_global_targets(cutoff)
    run = RagSecurityRescanRun(
        tenant_id=tenant_id,
        scope=scope,
        status=RagSecurityRescanStatus.PENDENTE,
        phase=phase,
        cutoff_at=cutoff,
        policy_version=str(current_app.config["RAG_CONTENT_SECURITY_POLICY_VERSION"]),
        batch_size=batch_size,
        total_targets=total,
        initiated_by_id=actor_id,
    )
    db.session.add(run)
    db.session.flush()
    _enqueue(run)
    db.session.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=actor_id,
            action="rag_security.rescan_requested",
            entity_type="rag_security_rescan_run",
            entity_id=str(run.id),
            after={
                "scope": scope.value,
                "policyVersion": run.policy_version,
                "totalTargets": total,
                "cutoffAt": cutoff.isoformat(),
            },
        )
    )
    return run


def execute_security_rescan(run: RagSecurityRescanRun) -> None:
    if run.status == RagSecurityRescanStatus.CONCLUIDA:
        return
    now = datetime.now(UTC)
    run.status = RagSecurityRescanStatus.PROCESSANDO
    run.started_at = run.started_at or now
    run.error = None

    items = _next_batch(run)
    if not items:
        if _advance_phase(run):
            items = _next_batch(run)
        else:
            _complete(run)
            return
    for item in items:
        if run.phase == "PRIVATE":
            outcome = _rescan_private(item)
        elif run.phase == "ATTACHMENT":
            outcome = _rescan_attachment(item)
        else:
            outcome = _rescan_global(item)
        run.cursor_id = item.id
        run.processed_targets += 1
        run.clean_targets += outcome[0] == "CLEAN"
        run.quarantined_targets += outcome[0] == "QUARANTINE"
        run.error_targets += outcome[0] == "ERROR"
        run.purged_chunks += outcome[1]
        run.purged_ocr += outcome[2]
        run.purged_transcriptions += outcome[3]
        signature = outcome[4]
        if signature:
            run.signature_version = signature

    if len(items) < run.batch_size and not _advance_phase(run):
        _complete(run)
        return
    _enqueue(run)


def fail_security_rescan(run: RagSecurityRescanRun, error_message: str) -> None:
    run.status = RagSecurityRescanStatus.ERRO
    run.error = error_message[:2000]
    run.completed_at = datetime.now(UTC)
    db.session.add(
        AuditLog(
            tenant_id=run.tenant_id,
            user_id=run.initiated_by_id,
            action="rag_security.rescan_failed",
            entity_type="rag_security_rescan_run",
            entity_id=str(run.id),
            after={"error": run.error, "processedTargets": run.processed_targets},
        )
    )


def security_rescan_data(run: RagSecurityRescanRun) -> dict:
    progress = (
        round((run.processed_targets / run.total_targets) * 100, 2) if run.total_targets else 100.0
    )
    return {
        "id": str(run.id),
        "tenantId": str(run.tenant_id) if run.tenant_id else None,
        "escopo": run.scope.value,
        "estado": run.status.value,
        "fase": run.phase,
        "versaoPolitica": run.policy_version,
        "versaoAssinaturas": run.signature_version,
        "lote": run.batch_size,
        "total": run.total_targets,
        "processados": run.processed_targets,
        "limpos": run.clean_targets,
        "quarentena": run.quarantined_targets,
        "erros": run.error_targets,
        "chunksEliminados": run.purged_chunks,
        "ocrsEliminados": run.purged_ocr,
        "transcricoesEliminadas": run.purged_transcriptions,
        "progressoPercentual": progress,
        "erro": run.error,
        "corteEm": run.cutoff_at.isoformat(),
        "iniciadaEm": run.started_at.isoformat() if run.started_at else None,
        "concluidaEm": run.completed_at.isoformat() if run.completed_at else None,
        "criadaEm": run.created_at.isoformat(),
    }


def _next_batch(run):
    model = {
        "PRIVATE": RagDocumentVersion,
        "ATTACHMENT": Attachment,
        "GLOBAL": GlobalKnowledgeDocumentVersion,
    }[run.phase]
    statement = select(model).where(model.created_at <= run.cutoff_at)
    if run.phase in {"PRIVATE", "ATTACHMENT"}:
        statement = statement.where(model.tenant_id == run.tenant_id)
    if run.cursor_id:
        statement = statement.where(model.id > run.cursor_id)
    return list(db.session.scalars(statement.order_by(model.id).limit(run.batch_size)))


def _advance_phase(run) -> bool:
    if run.phase == "PRIVATE":
        run.phase = "ATTACHMENT"
        run.cursor_id = None
        return True
    run.phase = "DONE"
    run.cursor_id = None
    return False


def _rescan_private(version) -> tuple[str, int, int, int, str | None]:
    chunks_before = version.chunk_count or db.session.scalar(
        select(func.count()).select_from(RagChunk).where(RagChunk.version_id == version.id)
    )
    source = db.session.scalar(
        select(RagKnowledgeSource).where(
            RagKnowledgeSource.tenant_id == version.tenant_id,
            RagKnowledgeSource.latest_version_id == version.id,
        )
    )
    if source is not None:
        source.status = RagKnowledgeSourceStatus.PENDENTE
    version.ingestion_status = RagIngestionStatus.PENDENTE
    version.error = None
    try:
        execute_ingestion(version, send_notification=False)
    except (NonRetryableFileError, NonRetryableRagError) as error:
        _purge_private_indeterminate(version, str(error), source)
        return "ERROR", int(chunks_before or 0), 0, 0, version.malware_signature_version
    if version.malware_scan_status != "CLEAN" or version.security_status in {
        ContentSecurityStatus.SUSPICIOUS,
        ContentSecurityStatus.MALICIOUS,
    }:
        return "QUARANTINE", int(chunks_before or 0), 0, 0, version.malware_signature_version
    if version.security_status != ContentSecurityStatus.CLEAN:
        return "ERROR", int(chunks_before or 0), 0, 0, version.malware_signature_version
    metadata = ensure_encrypted(
        rag_document_path(
            version.storage_key,
            tenant_id=version.tenant_id,
            document_id=version.document_id,
            version_id=version.id,
        ),
        f"tenant:{version.tenant_id}",
    )
    for field, value in metadata.items():
        setattr(version, field, value)
    return "CLEAN", 0, 0, 0, version.malware_signature_version


def _rescan_global(version) -> tuple[str, int, int, int, str | None]:
    chunks_before = version.chunk_count or db.session.scalar(
        select(func.count())
        .select_from(GlobalKnowledgeChunk)
        .where(GlobalKnowledgeChunk.version_id == version.id)
    )
    version.ingestion_status = RagIngestionStatus.PENDENTE
    version.error = None
    try:
        execute_global_ingestion(version)
    except (NonRetryableFileError, NonRetryableRagError) as error:
        _purge_global_indeterminate(version, str(error))
        return "ERROR", int(chunks_before or 0), 0, 0, version.malware_signature_version
    if version.malware_scan_status != "CLEAN" or version.security_status in {
        ContentSecurityStatus.SUSPICIOUS,
        ContentSecurityStatus.MALICIOUS,
    }:
        return "QUARANTINE", int(chunks_before or 0), 0, 0, version.malware_signature_version
    if version.security_status != ContentSecurityStatus.CLEAN:
        return "ERROR", int(chunks_before or 0), 0, 0, version.malware_signature_version
    metadata = ensure_encrypted(
        global_rag_document_path(
            version.storage_key,
            document_id=version.document_id,
            version_id=version.id,
        ),
        "global",
    )
    for field, value in metadata.items():
        setattr(version, field, value)
    return "CLEAN", 0, 0, 0, version.malware_signature_version


def _rescan_attachment(item) -> tuple[str, int, int, int, str | None]:
    try:
        path = attachment_path(item.storage_key)
        scan = require_clean_stored_file(
            path,
            item.mime_type,
            item.sha256,
            encryption_scope=f"tenant:{item.tenant_id}",
        )
    except MalwareScannerUnavailable:
        raise
    except (AttachmentError, MalwareDetectedError):
        chunk_count, ocr_count, transcription_count = _purge_attachment(item)
        return "QUARANTINE", chunk_count, ocr_count, transcription_count, None
    apply_malware_scan(item, scan)
    item.scan_status = AttachmentScanStatus.LIMPO
    item.scan_error_code = None
    metadata = ensure_encrypted(path, f"tenant:{item.tenant_id}")
    for field, value in metadata.items():
        setattr(item, field, value)
    return "CLEAN", 0, 0, 0, scan.signature_version


def _purge_private_indeterminate(version, message: str, source) -> None:
    now = datetime.now(UTC)
    db.session.execute(delete(RagChunk).where(RagChunk.version_id == version.id))
    version.extracted_text = None
    version.page_count = None
    version.embedding_model = None
    version.chunk_count = 0
    version.indexed_at = None
    version.ingestion_status = RagIngestionStatus.FALHOU
    version.lifecycle_status = RagDocumentLifecycle.RASCUNHO
    version.security_status = ContentSecurityStatus.INDETERMINATE
    version.security_action = ContentSecurityAction.RETRY
    version.security_error_code = "SECURITY_RESCAN_PARSE_REJECTED"
    version.security_purged_at = now
    version.error = message[:2000]
    if source is not None:
        source.status = RagKnowledgeSourceStatus.ERRO
        source.error_code = "SECURITY_RESCAN_PARSE_REJECTED"
        source.error_message = message[:2000]


def _purge_global_indeterminate(version, message: str) -> None:
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
    version.security_status = ContentSecurityStatus.INDETERMINATE
    version.security_action = ContentSecurityAction.RETRY
    version.security_error_code = "SECURITY_RESCAN_PARSE_REJECTED"
    version.security_purged_at = now
    version.error = message[:2000]


def _purge_attachment(item) -> tuple[int, int, int]:
    now = datetime.now(UTC)
    item.scan_status = AttachmentScanStatus.BLOQUEADO
    item.scan_provider = str(current_app.config["MALWARE_SCANNER_PROVIDER"])
    item.scan_error_code = "MALWARE_OR_INTEGRITY_DETECTED"
    item.scanned_at = now
    purged_chunks = 0
    ocr_count = 0
    if item.ocr is not None:
        ocr_count = 1
        purged_chunks = _purge_operational_derivative(
            item.tenant_id,
            DOCUMENT_OCR_ENTITY,
            item.ocr.id,
        )
        item.ocr.status = DocumentOcrStatus.FALHOU
        item.ocr.extracted_text = None
        item.ocr.reviewed_text = None
        item.ocr.pages = None
        item.ocr.page_count = None
        item.ocr.confidence = None
        item.ocr.error = "Derivados eliminados pela revarredura de segurança."
    transcription_count = 0
    if item.transcription is not None:
        transcription_count = 1
        purged_chunks += _purge_operational_derivative(
            item.tenant_id,
            AUDIO_TRANSCRIPTION_ENTITY,
            item.transcription.id,
        )
        item.transcription.status = AudioTranscriptionStatus.FALHOU
        item.transcription.transcript = None
        item.transcription.reviewed_transcript = None
        item.transcription.segments = None
        item.transcription.error = "Derivados eliminados pela revarredura de segurança."
    db.session.add(
        AuditLog(
            tenant_id=item.tenant_id,
            user_id=item.uploaded_by_id,
            action="attachment.security_rescan_quarantined",
            entity_type="attachment",
            entity_id=str(item.id),
            after={
                "status": "BLOCKED",
                "ocrPurged": bool(ocr_count),
                "transcriptionPurged": bool(transcription_count),
            },
        )
    )
    return purged_chunks, ocr_count, transcription_count


def _purge_operational_derivative(tenant_id, entity_type: str, entity_id) -> int:
    source = db.session.scalar(
        select(RagKnowledgeSource).where(
            RagKnowledgeSource.tenant_id == tenant_id,
            RagKnowledgeSource.entity_type == entity_type,
            RagKnowledgeSource.entity_id == entity_id,
        )
    )
    if source is None:
        return 0
    chunks = 0
    if source.latest_version_id:
        chunks = int(
            db.session.scalar(
                select(func.count())
                .select_from(RagChunk)
                .where(RagChunk.version_id == source.latest_version_id)
            )
            or 0
        )
    execute_operational_memory_sync(
        tenant_id,
        entity_type,
        entity_id,
        action=ProjectorAction.DELETE,
        revision=source.source_revision + 1,
        source_module=source.source_module,
    )
    return chunks


def _complete(run) -> None:
    run.status = RagSecurityRescanStatus.CONCLUIDA
    run.phase = "DONE"
    run.completed_at = datetime.now(UTC)
    db.session.add(
        AuditLog(
            tenant_id=run.tenant_id,
            user_id=run.initiated_by_id,
            action="rag_security.rescan_completed",
            entity_type="rag_security_rescan_run",
            entity_id=str(run.id),
            after=security_rescan_data(run),
        )
    )


def _enqueue(run) -> None:
    db.session.add(
        OutboxEvent(
            tenant_id=run.tenant_id,
            event_type=SECURITY_RESCAN_EVENT,
            aggregate_type="RagSecurityRescanRun",
            aggregate_id=str(run.id),
            payload={"runId": str(run.id)},
        )
    )


def _tenant_target_count(tenant_id, cutoff) -> int:
    versions = db.session.scalar(
        select(func.count())
        .select_from(RagDocumentVersion)
        .where(
            RagDocumentVersion.tenant_id == tenant_id,
            RagDocumentVersion.created_at <= cutoff,
        )
    )
    attachments = db.session.scalar(
        select(func.count())
        .select_from(Attachment)
        .where(
            Attachment.tenant_id == tenant_id,
            Attachment.created_at <= cutoff,
        )
    )
    return int(versions or 0) + int(attachments or 0)


def _global_target_count(cutoff) -> int:
    return int(
        db.session.scalar(
            select(func.count())
            .select_from(GlobalKnowledgeDocumentVersion)
            .where(GlobalKnowledgeDocumentVersion.created_at <= cutoff)
        )
        or 0
    )


def _invalidate_tenant_targets(tenant_id, cutoff) -> None:
    db.session.execute(
        update(RagDocumentVersion)
        .where(RagDocumentVersion.tenant_id == tenant_id, RagDocumentVersion.created_at <= cutoff)
        .values(
            malware_scan_status="INDETERMINATE",
            malware_scan_error_code="SECURITY_RESCAN_PENDING",
            security_status=ContentSecurityStatus.INDETERMINATE,
            security_action=ContentSecurityAction.RETRY,
            security_error_code="SECURITY_RESCAN_PENDING",
        )
    )
    db.session.execute(
        update(Attachment)
        .where(Attachment.tenant_id == tenant_id, Attachment.created_at <= cutoff)
        .values(
            scan_status=AttachmentScanStatus.PENDENTE, scan_error_code="SECURITY_RESCAN_PENDING"
        )
    )


def _invalidate_global_targets(cutoff) -> None:
    db.session.execute(
        update(GlobalKnowledgeDocumentVersion)
        .where(GlobalKnowledgeDocumentVersion.created_at <= cutoff)
        .values(
            malware_scan_status="INDETERMINATE",
            malware_scan_error_code="SECURITY_RESCAN_PENDING",
            security_status=ContentSecurityStatus.INDETERMINATE,
            security_action=ContentSecurityAction.RETRY,
            security_error_code="SECURITY_RESCAN_PENDING",
        )
    )
