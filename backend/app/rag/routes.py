import hashlib
import io
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.audit import add_audit
from app.auth.permissions import roles_required
from app.extensions import db
from app.models import (
    GlobalDistributionPolicy,
    GlobalEntitlementStatus,
    GlobalKnowledgeCollection,
    GlobalKnowledgeDocumentVersion,
    GlobalKnowledgeEntitlement,
    GlobalUpdateMode,
    GlobalVersionStatus,
    RagAssistantQuery,
    RagDocument,
    RagDocumentAccess,
    RagDocumentLifecycle,
    RagDocumentVersion,
    RagEvaluationQuestion,
    RagEvaluationRun,
    RagFeedbackStatus,
    RagIngestionStatus,
    RagKnowledgeSource,
    RagKnowledgeSourceStatus,
    RagLearningArtifact,
    RagLearningArtifactStatus,
    RagLearningArtifactType,
    RagLearningRun,
    RagLearningRunStatus,
    RagOutputValidationProfile,
    RagQueryFeedback,
    RagQueryFeedbackRating,
    RagSecurityRescanRun,
    RagSecurityRescanScope,
    RagThematicMemory,
)
from app.observability import percentile
from app.rag.analytics import rebuild_thematic_memories, structured_query
from app.rag.calibration import create_quality_calibration
from app.rag.content_security import (
    ContentSecurityAction,
    ContentSecurityReviewDecision,
    ContentSecurityStatus,
    content_security_state,
    record_content_security_review,
)
from app.rag.curation import (
    CurationConflictError,
    CurationNotFoundError,
    CurationValidationError,
    promote_feedback_to_evaluation,
    reconcile_curated_questions,
)
from app.rag.distribution import collection_access_for_tenant, entitlement_data
from app.rag.evaluation import (
    evaluation_question_data,
    evaluation_run_data,
    execute_tenant_evaluation,
)
from app.rag.feedback import (
    FeedbackConflictError,
    FeedbackNotFoundError,
    FeedbackValidationError,
    create_feedback_revision,
    feedback_data,
    moderate_feedback,
)
from app.rag.learning import (
    LearningConflictError,
    LearningValidationError,
    activate_learning_artifact,
    create_learning_run,
    evaluate_learning_artifact,
    learning_artifact_data,
    learning_run_data,
    record_learning_influence,
    rollback_learning_artifact,
)
from app.rag.operational_memory import reprocess_operational_memory
from app.rag.output_validation import (
    output_validation_profile_data,
    rollback_output_validation,
    start_output_validation_rollout,
    validate_and_apply_output,
)
from app.rag.regression import (
    RegressionNotFoundError,
    RegressionValidationError,
    capture_regression_case,
)
from app.rag.retrieval import query_audit_payload
from app.rag.router import route_query
from app.rag.security_rescan import (
    SecurityRescanConflictError,
    create_security_rescan,
    security_rescan_data,
)
from app.rag.service import enqueue_ingestion, requeue_ingestion
from app.rag.storage import (
    RagStorageError,
    rag_document_path,
    signed_rag_download_token,
    store_rag_document,
    verify_rag_download_token,
)
from app.security.encryption import read_plaintext
from app.security.malware import malware_scan_state

rag_bp = Blueprint("rag", __name__)
DOCUMENT_TYPES = {
    "LEGISLACAO",
    "ATO",
    "ATA",
    "RESPOSTA_ORGAO",
    "CONTRATO",
    "PROCESSO",
    "PROCEDIMENTO_INTERNO",
    "OUTRO",
}
OPERATIONAL_MODULE_LABELS = {
    "SOLICITACOES": "Solicitações",
    "LEGISLATIVO": "Produção legislativa",
    "AGENDA": "Agenda",
    "FISCALIZACAO": "Fiscalização",
    "ANALITICA": "Inteligência temática",
}
OPERATIONAL_ENTITY_LABELS = {
    "SERVICE_REQUEST": "Solicitação",
    "REQUEST_FORWARDING": "Encaminhamento",
    "LEGISLATIVE_DRAFT": "Minuta legislativa",
    "LEGISLATIVE_TRAMITATION": "Tramitação legislativa",
    "NORMATIVE_SOURCE": "Fonte normativa",
    "DOCUMENT_OCR": "Documento processado",
    "AUDIO_TRANSCRIPTION": "Transcrição de áudio",
    "AGENDA_EVENT": "Compromisso de agenda",
    "OVERSIGHT_ACTION": "Ação de fiscalização",
    "THEMATIC_MEMORY": "Memória temática",
}
OPERATIONAL_STATUS_LABELS = {
    "PENDENTE": "Sincronizando",
    "ATIVA": "Disponível",
    "QUARENTENA": "Requer revisão",
    "INELEGIVEL": "Não elegível",
    "EXPIRADA": "Expirada",
    "ERRO": "Falha na sincronização",
    "EXCLUIDA": "Descartada",
}
OPERATIONAL_PURPOSE_LABELS = {
    "ATENDIMENTO_E_PLANEJAMENTO_LEGISLATIVO": (
        "Apoiar o atendimento ao cidadão e o planejamento de iniciativas legislativas."
    ),
    "ACOMPANHAMENTO_DE_ENCAMINHAMENTOS_E_RESPOSTAS_OFICIAIS": (
        "Acompanhar encaminhamentos realizados pelo gabinete e as respostas oficiais recebidas."
    ),
    "ACOMPANHAMENTO_DA_TRAMITACAO_LEGISLATIVA": (
        "Acompanhar a tramitação de proposições e identificar avanços, prazos e pendências."
    ),
    "EVIDENCIA_DOCUMENTAL_REVISADA_DE_ATENDIMENTO": (
        "Disponibilizar documentos de atendimento revisados como evidências "
        "para consultas e decisões."
    ),
    "EVIDENCIA_DE_AUDIO_REVISADA_DE_ATENDIMENTO": (
        "Disponibilizar transcrições de áudio revisadas como evidências dos "
        "atendimentos realizados."
    ),
    "MEMORIA_DE_COMPROMISSOS_E_VISITAS_REALIZADOS": (
        "Registrar compromissos e visitas realizados para apoiar o acompanhamento "
        "das ações do gabinete."
    ),
    "MEMORIA_DE_FISCALIZACAO_E_CONTROLE": (
        "Apoiar o acompanhamento de fiscalizações, providências e resultados de controle."
    ),
    "PLANEJAMENTO_TEMATICO_AGREGADO": (
        "Reunir informações relacionadas por tema para apoiar o planejamento e a "
        "definição de prioridades."
    ),
    "MEMORIA_E_PRODUCAO_LEGISLATIVA": (
        "Preservar o contexto da produção legislativa para apoiar análises e novas iniciativas."
    ),
    "FUNDAMENTACAO_NORMATIVA_LEGISLATIVA": (
        "Localizar fontes normativas governadas para fundamentar a produção legislativa."
    ),
}


@rag_bp.get("/rag/fontes-operacionais")
@roles_required("admin", "manager")
def list_operational_sources():
    tenant_id, _ = _context()
    statement = select(RagKnowledgeSource).where(RagKnowledgeSource.tenant_id == tenant_id)
    status_value = str(request.args.get("estado", "")).strip().upper()
    if status_value:
        try:
            status = RagKnowledgeSourceStatus(status_value)
        except ValueError:
            return (
                jsonify(
                    error="validation_error",
                    message="Estado de fonte operacional inválido.",
                ),
                422,
            )
        statement = statement.where(RagKnowledgeSource.status == status)
    source_module = str(request.args.get("modulo", "")).strip().upper()
    if source_module:
        statement = statement.where(RagKnowledgeSource.source_module == source_module[:60])
    entity_type = str(request.args.get("entidadeTipo", "")).strip().upper()
    if entity_type:
        statement = statement.where(RagKnowledgeSource.entity_type == entity_type[:80])
    sources = db.session.scalars(
        statement.order_by(RagKnowledgeSource.updated_at.desc()).limit(300)
    )
    return jsonify(content=[operational_source_data(source) for source in sources])


@rag_bp.post("/rag/fontes-operacionais/<uuid:source_id>/reprocessar")
@roles_required("admin", "manager")
def reprocess_operational_source(source_id: uuid.UUID):
    tenant_id, _ = _context()
    source = db.session.execute(
        select(RagKnowledgeSource).where(
            RagKnowledgeSource.tenant_id == tenant_id,
            RagKnowledgeSource.id == source_id,
        )
    ).scalar_one_or_none()
    if source is None:
        return (
            jsonify(error="resource_not_found", message="Fonte não encontrada."),
            404,
        )
    try:
        reprocess_operational_memory(source)
    except ValueError as error:
        return jsonify(error="conflict", message=str(error)), 409
    db.session.commit()
    return jsonify(operational_source_data(source)), 202


@rag_bp.get("/rag/memorias-tematicas")
@jwt_required()
def list_thematic_memories():
    tenant_id, _ = _context()
    items = db.session.scalars(
        select(RagThematicMemory)
        .where(RagThematicMemory.tenant_id == tenant_id)
        .order_by(
            RagThematicMemory.period_end.desc(),
            RagThematicMemory.request_count.desc(),
        )
        .limit(500)
    )
    return jsonify(content=[thematic_memory_data(item) for item in items])


@rag_bp.post("/rag/memorias-tematicas/reconstruir")
@roles_required("admin", "manager")
def rebuild_thematic_memory_route():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    try:
        period_end = date.fromisoformat(
            str(payload.get("fim") or datetime.now(UTC).date().isoformat())
        )
        period_start = date.fromisoformat(
            str(payload.get("inicio") or (period_end - timedelta(days=365)).isoformat())
        )
        items = rebuild_thematic_memories(
            tenant_id,
            user_id,
            period_start=period_start,
            period_end=period_end,
        )
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    add_audit(
        tenant_id,
        user_id,
        "rag_thematic_memory.rebuilt",
        "rag_thematic_memory",
        None,
        after={
            "inicio": period_start.isoformat(),
            "fim": period_end.isoformat(),
            "memorias": len(items),
        },
    )
    db.session.commit()
    return jsonify(content=[thematic_memory_data(item) for item in items]), 202


@rag_bp.post("/assistente/consultas-estruturadas")
@jwt_required()
def create_structured_query():
    tenant_id, user_id = _context()
    try:
        result = structured_query(tenant_id, request.get_json(silent=True) or {})
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    add_audit(
        tenant_id,
        user_id,
        "rag_assistant.structured_query",
        "structured_query",
        None,
        after={
            "dataset": result["dataset"],
            "metrica": result["metrica"],
            "agruparPor": result["agruparPor"],
            "filtros": result["filtros"],
            "periodo": result["periodo"],
        },
    )
    db.session.commit()
    return jsonify(result)


def _context() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(get_jwt()["tenant_id"]), uuid.UUID(get_jwt_identity())


@rag_bp.get("/rag/documentos")
@jwt_required()
def list_documents():
    tenant_id, _ = _context()
    operational_document = exists().where(
        RagKnowledgeSource.tenant_id == RagDocument.tenant_id,
        RagKnowledgeSource.document_id == RagDocument.id,
    )
    statement = select(RagDocument).where(
        RagDocument.tenant_id == tenant_id,
        ~operational_document,
    )
    if get_jwt().get("role") not in {"admin", "manager"}:
        statement = statement.where(RagDocument.access_level == RagDocumentAccess.INTERNO)
    search = str(request.args.get("q", "")).strip()
    if search:
        statement = statement.where(
            or_(
                RagDocument.title.ilike(f"%{search[:100]}%"),
                RagDocument.agency.ilike(f"%{search[:100]}%"),
                RagDocument.document_type.ilike(f"%{search[:100]}%"),
            )
        )
    items = db.session.execute(
        statement.order_by(RagDocument.updated_at.desc()).limit(300)
    ).scalars()
    return jsonify(content=[document_data(item, include_versions=False) for item in items])


@rag_bp.get("/rag/quarentena")
@roles_required("admin", "manager")
def list_security_quarantine():
    tenant_id, _ = _context()
    items = db.session.scalars(
        select(RagDocumentVersion)
        .where(
            RagDocumentVersion.tenant_id == tenant_id,
            RagDocumentVersion.security_status != ContentSecurityStatus.CLEAN,
        )
        .order_by(RagDocumentVersion.security_quarantined_at.desc(), RagDocumentVersion.created_at)
        .limit(300)
    )
    return jsonify(
        content=[
            {
                **version_data(item, include_download=False),
                "documentoId": str(item.document_id),
                "titulo": item.document.title,
            }
            for item in items
        ]
    )


@rag_bp.post("/rag/seguranca/revarreduras")
@roles_required("admin")
def create_tenant_security_rescan():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    try:
        batch_size = int(payload.get("tamanhoLote", 20))
        run = create_security_rescan(
            tenant_id=tenant_id,
            actor_id=user_id,
            scope=RagSecurityRescanScope.TENANT,
            batch_size=batch_size,
        )
    except (TypeError, ValueError) as error:
        return jsonify(error="validation_error", message=str(error)), 422
    except SecurityRescanConflictError as error:
        return jsonify(error="conflict", message=str(error)), 409
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="conflict", message="Já existe uma revarredura ativa."), 409
    return jsonify(security_rescan_data(run)), 202


@rag_bp.get("/rag/seguranca/revarreduras")
@roles_required("admin", "manager")
def list_tenant_security_rescans():
    tenant_id, _ = _context()
    runs = db.session.scalars(
        select(RagSecurityRescanRun)
        .where(RagSecurityRescanRun.tenant_id == tenant_id)
        .order_by(RagSecurityRescanRun.created_at.desc())
        .limit(100)
    )
    return jsonify(content=[security_rescan_data(run) for run in runs])


@rag_bp.get("/rag/seguranca/revarreduras/<uuid:run_id>")
@roles_required("admin", "manager")
def get_tenant_security_rescan(run_id: uuid.UUID):
    tenant_id, _ = _context()
    run = db.session.scalar(
        select(RagSecurityRescanRun).where(
            RagSecurityRescanRun.id == run_id,
            RagSecurityRescanRun.tenant_id == tenant_id,
        )
    )
    if run is None:
        return jsonify(error="resource_not_found", message="Revarredura não encontrada."), 404
    return jsonify(security_rescan_data(run))


@rag_bp.get("/rag/documentos/<uuid:document_id>")
@jwt_required()
def get_document(document_id: uuid.UUID):
    tenant_id, _ = _context()
    item = _document(tenant_id, document_id)
    if item is None or not _can_access(item):
        return jsonify(error="resource_not_found", message="Documento não encontrado."), 404
    return jsonify(document_data(item, include_versions=True))


@rag_bp.post("/rag/documentos")
@roles_required("admin", "manager")
def create_document():
    tenant_id, user_id = _context()
    try:
        values = _document_values(request.form)
        version_values = _version_values(request.form)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    uploaded_file = request.files.get("arquivo")
    if uploaded_file is None:
        return jsonify(error="validation_error", message="Envie o arquivo do documento."), 422
    item = RagDocument(id=uuid.uuid4(), tenant_id=tenant_id, created_by_id=user_id, **values)
    version = RagDocumentVersion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        document=item,
        version_number=1,
        created_by_id=user_id,
        **version_values,
    )
    try:
        stored = store_rag_document(tenant_id, item.id, version.id, uploaded_file)
    except RagStorageError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    for field, value in stored.items():
        setattr(version, field, value)
    db.session.add(item)
    enqueue_ingestion(version)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="conflict", message="Já existe um documento com esse título."), 409
    add_audit(
        tenant_id,
        user_id,
        "rag_document.created",
        "rag_document",
        item.id,
        after={"titulo": item.title, "versaoId": str(version.id), "checksum": version.checksum},
    )
    db.session.commit()
    return jsonify(document_data(item, include_versions=True)), 202


@rag_bp.post("/rag/documentos/<uuid:document_id>/versoes")
@roles_required("admin", "manager")
def create_version(document_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = _document(tenant_id, document_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Documento não encontrado."), 404
    try:
        values = _version_values(request.form)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    uploaded_file = request.files.get("arquivo")
    if uploaded_file is None:
        return jsonify(error="validation_error", message="Envie o arquivo da versão."), 422
    next_number = (
        db.session.execute(
            select(func.max(RagDocumentVersion.version_number)).where(
                RagDocumentVersion.document_id == item.id
            )
        ).scalar_one()
        or 0
    ) + 1
    version = RagDocumentVersion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        document=item,
        version_number=next_number,
        created_by_id=user_id,
        **values,
    )
    try:
        stored = store_rag_document(tenant_id, item.id, version.id, uploaded_file)
    except RagStorageError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    for field, value in stored.items():
        setattr(version, field, value)
    db.session.add(version)
    enqueue_ingestion(version)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="conflict", message="Esta versão já está cadastrada."), 409
    add_audit(
        tenant_id,
        user_id,
        "rag_document.version_created",
        "rag_document_version",
        version.id,
        after={"documentoId": str(item.id), "versao": version.version_label},
    )
    db.session.commit()
    return jsonify(version_data(version)), 202


@rag_bp.patch("/rag/documentos/<uuid:document_id>/versoes/<uuid:version_id>/estado")
@roles_required("admin", "manager")
def change_lifecycle(document_id: uuid.UUID, version_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = _version(tenant_id, document_id, version_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Versão não encontrada."), 404
    try:
        lifecycle = RagDocumentLifecycle(
            str((request.get_json(silent=True) or {}).get("estado", ""))
        )
    except ValueError:
        return jsonify(error="validation_error", message="Estado documental inválido."), 422
    if (
        lifecycle == RagDocumentLifecycle.VIGENTE
        and item.ingestion_status != RagIngestionStatus.INDEXADO
    ):
        return jsonify(
            error="conflict", message="Somente versões indexadas podem ser publicadas."
        ), 409
    if lifecycle == RagDocumentLifecycle.VIGENTE and (
        item.security_status != ContentSecurityStatus.CLEAN
        or item.security_action != ContentSecurityAction.ALLOW
    ):
        return jsonify(
            error="content_security_blocked",
            message="Somente versões CLEAN/ALLOW podem ser publicadas.",
        ), 409
    before = item.lifecycle_status.value
    if lifecycle == RagDocumentLifecycle.VIGENTE:
        current = db.session.execute(
            select(RagDocumentVersion).where(
                RagDocumentVersion.document_id == document_id,
                RagDocumentVersion.id != version_id,
                RagDocumentVersion.lifecycle_status == RagDocumentLifecycle.VIGENTE,
            )
        ).scalars()
        for previous in current:
            previous.lifecycle_status = RagDocumentLifecycle.HISTORICO
    item.lifecycle_status = lifecycle
    add_audit(
        tenant_id,
        user_id,
        "rag_document.lifecycle_changed",
        "rag_document_version",
        item.id,
        before={"estado": before},
        after={"estado": lifecycle.value},
    )
    db.session.commit()
    return jsonify(version_data(item))


@rag_bp.post("/rag/documentos/<uuid:document_id>/versoes/<uuid:version_id>/reprocessar")
@roles_required("admin", "manager")
def reprocess_version(document_id: uuid.UUID, version_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = _version(tenant_id, document_id, version_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Versão não encontrada."), 404
    if item.ingestion_status not in {RagIngestionStatus.FALHOU, RagIngestionStatus.INDEXADO}:
        return jsonify(error="conflict", message="A versão já está na fila de processamento."), 409
    if item.security_status in {
        ContentSecurityStatus.SUSPICIOUS,
        ContentSecurityStatus.MALICIOUS,
    } and (
        item.security_review_decision != ContentSecurityReviewDecision.APPROVED
        or item.security_review_checksum != item.security_content_checksum
    ):
        return jsonify(
            error="content_security_review_required",
            message="A versão em quarentena precisa de aprovação vinculada ao checksum.",
        ), 409
    requeue_ingestion(item)
    add_audit(tenant_id, user_id, "rag_document.reprocessed", "rag_document_version", item.id)
    db.session.commit()
    return jsonify(version_data(item)), 202


@rag_bp.patch("/rag/documentos/<uuid:document_id>/versoes/<uuid:version_id>/seguranca")
@roles_required("admin", "manager")
def review_version_security(document_id: uuid.UUID, version_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = _version(tenant_id, document_id, version_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Versão não encontrada."), 404
    if item.security_status not in {
        ContentSecurityStatus.SUSPICIOUS,
        ContentSecurityStatus.MALICIOUS,
    }:
        return jsonify(
            error="conflict",
            message="Somente conteúdo suspeito ou malicioso pode ser revisado.",
        ), 409
    payload = request.get_json(silent=True) or {}
    decisions = {
        "APROVAR": ContentSecurityReviewDecision.APPROVED,
        "REJEITAR": ContentSecurityReviewDecision.REJECTED,
    }
    decision = decisions.get(str(payload.get("decisao", "")).upper())
    reason = str(payload.get("justificativa", "")).strip()
    if decision is None or len(reason) < 10 or len(reason) > 2000:
        return jsonify(
            error="validation_error",
            message="Informe APROVAR ou REJEITAR e justificativa entre 10 e 2000 caracteres.",
        ), 422
    before = content_security_state(item)
    record_content_security_review(
        item,
        decision,
        reviewer_id=user_id,
        reason=reason,
    )
    add_audit(
        tenant_id,
        user_id,
        "rag_document.security_reviewed",
        "rag_document_version",
        item.id,
        before={
            "status": before["status"],
            "reviewDecision": before["review"]["decision"],
        },
        after={
            "status": item.security_status.value,
            "reviewDecision": decision.value,
            "contentChecksum": item.security_review_checksum,
        },
    )
    db.session.commit()
    return jsonify(version_data(item))


@rag_bp.get("/rag/documentos/<uuid:document_id>/versoes/<uuid:version_id>/download")
@jwt_required()
def download_version(document_id: uuid.UUID, version_id: uuid.UUID):
    tenant_id, _ = _context()
    item = _version(tenant_id, document_id, version_id)
    if item is None or not _can_access(item.document):
        return jsonify(error="resource_not_found", message="Versão não encontrada."), 404
    if item.security_status != ContentSecurityStatus.CLEAN and get_jwt().get("role") not in {
        "admin",
        "manager",
    }:
        return jsonify(
            error="content_security_restricted",
            message="Conteúdo em quarentena requer perfil autorizado.",
        ), 403
    if not verify_rag_download_token(
        str(request.args.get("token", "")),
        tenant_id,
        document_id,
        version_id,
    ):
        return jsonify(error="invalid_download_token", message="Link inválido ou expirado."), 403
    path = rag_document_path(
            item.storage_key,
            tenant_id=tenant_id,
            document_id=document_id,
            version_id=version_id,
        )
    return send_file(
        io.BytesIO(read_plaintext(path, f"tenant:{tenant_id}")),
        mimetype=item.mime_type,
        download_name=item.original_name,
        as_attachment=True,
    )


@rag_bp.post("/assistente/consultas")
@jwt_required()
def create_assistant_query():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    started = time.perf_counter()
    try:
        answer = route_query(
            tenant_id,
            get_jwt().get("role"),
            str(payload.get("consulta", "")),
            limit=payload.get("limite"),
            explicit_filters=payload.get("filtros"),
            canary_key=str(user_id),
        )
    except (TypeError, ValueError) as error:
        return jsonify(error="validation_error", message=str(error)), 422
    output_validation = validate_and_apply_output(
        tenant_id,
        answer["consulta"],
        answer,
    )
    query = RagAssistantQuery(
        tenant_id=tenant_id,
        user_id=user_id,
        query_text=answer["consulta"],
        query_hash=hashlib.sha256(answer["consulta"].encode("utf-8")).hexdigest(),
        response=answer["resposta"],
        sources=answer["fontes"],
        safety_flags={
            **answer["seguranca"],
            "recuperacao": answer["recuperacao"],
            "geracao": answer.get("geracao"),
        },
        grounded=answer["fundamentada"],
        refused=answer["recusaConclusiva"],
        evidence_threshold=answer["limiarEvidencia"],
        embedding_model=answer["modeloEmbedding"],
        fallback_used=answer["fallbackUtilizado"],
        latency_ms=max(1, round((time.perf_counter() - started) * 1000)),
        method=answer["metodo"],
        routing_reasons=answer["motivosRoteamento"],
        applied_filters=answer["filtrosAplicados"],
        structured_result=answer["resultadoEstruturado"],
        learning_artifacts=answer.get("artefatosAprendizado", []),
        output_validation=output_validation,
        output_validation_enforced=bool(output_validation["enforced"]),
    )
    db.session.add(query)
    db.session.flush()
    record_learning_influence(
        tenant_id,
        query.learning_artifacts,
        answer=answer,
    )
    answer["id"] = str(query.id)
    answer["avaliacao"] = None
    add_audit(
        tenant_id,
        user_id,
        "rag_assistant.queried",
        "rag_assistant_query",
        query.id,
        after=query_audit_payload(answer),
    )
    db.session.commit()
    current_app.logger.info(
        "RAG query completed grounded=%s refused=%s fallback=%s sources=%s",
        query.grounded,
        query.refused,
        query.fallback_used,
        len(query.sources),
        extra={"duration_ms": query.latency_ms},
    )
    return jsonify(answer)


@rag_bp.get("/assistente/metricas")
@roles_required("admin", "manager")
def assistant_metrics():
    tenant_id, _ = _context()
    since = datetime.now(UTC) - timedelta(hours=current_app.config["RAG_METRICS_WINDOW_HOURS"])
    items = list(
        db.session.scalars(
            select(RagAssistantQuery).where(
                RagAssistantQuery.tenant_id == tenant_id,
                RagAssistantQuery.created_at >= since,
            )
        )
    )
    total = len(items)
    latencies = [item.latency_ms for item in items if item.latency_ms is not None]
    p95 = percentile(latencies, 0.95)
    target = current_app.config["RAG_SLO_QUERY_P95_MS"]
    neural_rerank_applied = sum(
        bool(
            (item.safety_flags or {})
            .get("recuperacao", {})
            .get("rerankingNeural", {})
            .get("aplicado")
        )
        for item in items
    )
    neural_rerank_fallback = sum(
        bool(
            (item.safety_flags or {})
            .get("recuperacao", {})
            .get("rerankingNeural", {})
            .get("fallbackUtilizado")
        )
        for item in items
    )
    expanded_queries = sum(
        bool((item.safety_flags or {}).get("recuperacao", {}).get("expansaoConsultaAplicada"))
        for item in items
    )
    documentary_filters = sum(
        bool(
            (
                (item.safety_flags or {}).get("recuperacao", {}).get("entendimentoConsulta") or {}
            ).get("filtrosDocumentais")
        )
        for item in items
    )
    generated_answers = sum(
        bool(((item.safety_flags or {}).get("geracao") or {}).get("aplicada")) for item in items
    )
    generation_fallbacks = sum(
        bool(((item.safety_flags or {}).get("geracao") or {}).get("fallbackUtilizado"))
        for item in items
    )
    citation_validation_rejections = sum(
        bool(
            ((item.safety_flags or {}).get("geracao") or {}).get("habilitada")
            and not (
                ((item.safety_flags or {}).get("geracao") or {})
                .get("validacaoCruzada", {})
                .get("valida")
            )
            and ((item.safety_flags or {}).get("geracao") or {}).get("fallbackUtilizado")
        )
        for item in items
    )
    entailment_applied = sum(
        bool(
            ((item.safety_flags or {}).get("geracao") or {})
            .get("validacaoCruzada", {})
            .get("entailmentSemantico", {})
            .get("aplicado")
        )
        for item in items
    )
    entailment_fallbacks = sum(
        bool(
            ((item.safety_flags or {}).get("geracao") or {})
            .get("validacaoCruzada", {})
            .get("entailmentSemantico", {})
            .get("fallbackUtilizado")
        )
        for item in items
    )
    entailment_rejections = sum(
        bool(
            (
                ((item.safety_flags or {}).get("geracao") or {})
                .get("validacaoCruzada", {})
                .get("entailmentSemantico", {})
                .get("habilitado")
            )
            and not (
                ((item.safety_flags or {}).get("geracao") or {})
                .get("validacaoCruzada", {})
                .get("entailmentSemantico", {})
                .get("valida")
            )
        )
        for item in items
    )
    output_validated = sum(bool(item.output_validation) for item in items)
    output_blocked = sum(
        (item.output_validation or {}).get("status") == "BLOCKED" for item in items
    )
    output_enforced = sum(item.output_validation_enforced for item in items)
    output_signals: dict[str, int] = {}
    for item in items:
        for signal in (item.output_validation or {}).get("signals", []):
            output_signals[signal] = output_signals.get(signal, 0) + 1
    return jsonify(
        janelaHoras=current_app.config["RAG_METRICS_WINDOW_HOURS"],
        consultas=total,
        fundamentadas=sum(item.grounded for item in items),
        recusadas=sum(item.refused for item in items),
        fallback=sum(item.fallback_used for item in items),
        rerankingNeuralAplicado=neural_rerank_applied,
        fallbackRerankingNeural=neural_rerank_fallback,
        consultasComExpansao=expanded_queries,
        consultasComFiltrosDocumentais=documentary_filters,
        respostasGeradas=generated_answers,
        fallbackGeracao=generation_fallbacks,
        rejeicoesValidacaoCitacoes=citation_validation_rejections,
        entailmentAplicado=entailment_applied,
        fallbackEntailment=entailment_fallbacks,
        rejeicoesEntailment=entailment_rejections,
        validacaoSaida={
            "validadas": output_validated,
            "bloqueadas": output_blocked,
            "bloqueiosAplicados": output_enforced,
            "somenteMonitoradas": max(0, output_blocked - output_enforced),
            "taxaBloqueio": round(output_blocked / output_validated, 6)
            if output_validated
            else 0.0,
            "sinais": output_signals,
        },
        feedbackPositivo=sum(
            item.feedback_rating == RagQueryFeedbackRating.POSITIVA for item in items
        ),
        feedbackNegativo=sum(
            item.feedback_rating == RagQueryFeedbackRating.NEGATIVA for item in items
        ),
        latenciaP95Ms=p95,
        sloLatenciaMs=target,
        sloAtendido=p95 is None or p95 <= target,
    )


@rag_bp.get("/assistente/seguranca/validacao-saida/rollout")
@roles_required("admin", "manager")
def get_output_validation_rollout():
    tenant_id, _ = _context()
    profile = db.session.get(RagOutputValidationProfile, tenant_id)
    return jsonify(output_validation_profile_data(profile))


@rag_bp.post("/assistente/seguranca/validacao-saida/rollout")
@roles_required("admin")
def create_output_validation_rollout():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    try:
        profile = start_output_validation_rollout(
            tenant_id,
            user_id,
            stages=payload.get("etapas"),
            minimum_samples=payload.get("amostraMinima"),
            maximum_block_rate=payload.get("taxaBloqueioMaxima"),
        )
        db.session.commit()
    except (TypeError, ValueError) as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    return jsonify(output_validation_profile_data(profile)), 201


@rag_bp.post("/assistente/seguranca/validacao-saida/rollback")
@roles_required("admin")
def rollback_output_validation_rollout():
    tenant_id, user_id = _context()
    profile = db.session.get(RagOutputValidationProfile, tenant_id)
    if profile is None:
        return jsonify(error="resource_not_found", message="Rollout nao iniciado."), 404
    try:
        rollback_output_validation(
            profile,
            user_id,
            reason=str((request.get_json(silent=True) or {}).get("motivo", "")),
        )
        db.session.commit()
    except ValueError as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    return jsonify(output_validation_profile_data(profile))


@rag_bp.get("/assistente/avaliacoes/perguntas")
@roles_required("admin", "manager")
def list_evaluation_questions():
    tenant_id, user_id = _context()
    if reconcile_curated_questions(tenant_id, user_id):
        db.session.commit()
    statement = select(RagEvaluationQuestion).where(RagEvaluationQuestion.tenant_id == tenant_id)
    origin = request.args.get("origem")
    if origin:
        origin = origin.strip().upper()
        if origin not in {"MANUAL", "FEEDBACK", "REGRESSAO"}:
            return jsonify(error="validation_error", message="Origem inválida."), 422
        statement = statement.where(RagEvaluationQuestion.case_origin == origin)
    severity = request.args.get("severidade")
    if severity:
        severity = severity.strip().upper()
        if severity not in {"BAIXA", "MEDIA", "ALTA", "CRITICA"}:
            return jsonify(error="validation_error", message="Severidade inválida."), 422
        statement = statement.where(RagEvaluationQuestion.severity == severity)
    active = request.args.get("ativa")
    if active is not None:
        normalized_active = active.strip().lower()
        if normalized_active not in {"true", "false"}:
            return jsonify(error="validation_error", message="ativa inválida."), 422
        statement = statement.where(RagEvaluationQuestion.active.is_(normalized_active == "true"))
    items = db.session.scalars(statement.order_by(RagEvaluationQuestion.created_at.desc()))
    return jsonify(content=[evaluation_question_data(item) for item in items])


@rag_bp.post("/assistente/avaliacoes/perguntas")
@roles_required("admin", "manager")
def create_evaluation_question():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    try:
        values = _evaluation_question_values(payload, tenant_id)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    item = RagEvaluationQuestion(
        tenant_id=tenant_id,
        created_by_id=user_id,
        **values,
    )
    db.session.add(item)
    db.session.flush()
    add_audit(
        tenant_id,
        user_id,
        "rag_evaluation.question_created",
        "rag_evaluation_question",
        item.id,
        after={
            "documentosEsperados": len(item.expected_document_ids),
            "esperaRecusa": item.expected_refusal,
            "ativa": item.active,
        },
    )
    db.session.commit()
    return jsonify(evaluation_question_data(item)), 201


@rag_bp.post("/assistente/avaliacoes/casos-regressao")
@roles_required("admin", "manager")
def create_regression_case():
    tenant_id, user_id = _context()
    try:
        item, created = capture_regression_case(
            tenant_id,
            user_id,
            request.get_json(silent=True) or {},
        )
        db.session.commit()
    except RegressionNotFoundError as error:
        db.session.rollback()
        return jsonify(error="resource_not_found", message=str(error)), 404
    except RegressionValidationError as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    except IntegrityError:
        db.session.rollback()
        return (
            jsonify(
                error="conflict",
                message="A consulta foi registrada simultaneamente.",
            ),
            409,
        )
    return jsonify(evaluation_question_data(item)), 201 if created else 200


@rag_bp.patch("/assistente/avaliacoes/perguntas/<uuid:question_id>")
@roles_required("admin", "manager")
def update_evaluation_question(question_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(
        select(RagEvaluationQuestion).where(
            RagEvaluationQuestion.id == question_id,
            RagEvaluationQuestion.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Pergunta não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    if item.source_feedback_id or item.case_origin == "REGRESSAO":
        unsupported = set(payload) - {"observacoes", "ativa"}
        if unsupported:
            return (
                jsonify(
                    error="conflict",
                    message="Caso curado preserva os sinais e o baseline de origem.",
                ),
                409,
            )
        if item.source_feedback_id and payload.get("ativa") is True and not item.active:
            return (
                jsonify(
                    error="conflict",
                    message=(
                        "Caso curado desativado deve ser promovido novamente "
                        "a partir de feedback válido."
                    ),
                ),
                409,
            )
        try:
            notes = _optional_text(
                payload.get("observacoes", item.notes),
                2000,
                "Observações",
            )
        except ValueError as error:
            return jsonify(error="validation_error", message=str(error)), 422
        active = payload.get("ativa", item.active)
        if not isinstance(active, bool):
            return (
                jsonify(
                    error="validation_error",
                    message="ativa deve ser booleano.",
                ),
                422,
            )
        before = {"ativa": item.active, "possuiObservacoes": bool(item.notes)}
        item.notes = notes
        item.active = active
        if not active:
            item.deactivation_reason = "DESATIVACAO_MANUAL"
        add_audit(
            tenant_id,
            user_id,
            "rag_evaluation.question_updated",
            "rag_evaluation_question",
            item.id,
            before=before,
            after={"ativa": item.active, "possuiObservacoes": bool(item.notes)},
        )
        db.session.commit()
        return jsonify(evaluation_question_data(item))
    merged = {
        "pergunta": payload.get("pergunta", item.question),
        "documentosEsperados": payload.get("documentosEsperados", item.expected_document_ids),
        "esperaRecusa": payload.get("esperaRecusa", item.expected_refusal),
        "observacoes": payload.get("observacoes", item.notes),
        "ativa": payload.get("ativa", item.active),
    }
    try:
        values = _evaluation_question_values(merged, tenant_id)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    before = {
        "documentosEsperados": len(item.expected_document_ids),
        "esperaRecusa": item.expected_refusal,
        "ativa": item.active,
    }
    for field, value in values.items():
        setattr(item, field, value)
    add_audit(
        tenant_id,
        user_id,
        "rag_evaluation.question_updated",
        "rag_evaluation_question",
        item.id,
        before=before,
        after={
            "documentosEsperados": len(item.expected_document_ids),
            "esperaRecusa": item.expected_refusal,
            "ativa": item.active,
        },
    )
    db.session.commit()
    return jsonify(evaluation_question_data(item))


@rag_bp.post("/assistente/avaliacoes/executar")
@roles_required("admin", "manager")
def execute_evaluation():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    if reconcile_curated_questions(tenant_id, user_id):
        db.session.commit()
    try:
        run = execute_tenant_evaluation(
            tenant_id,
            user_id,
            get_jwt().get("role"),
            k=int(payload.get("k", current_app.config["RAG_RETRIEVAL_MAX_RESULTS"])),
        )
    except (TypeError, ValueError) as error:
        return jsonify(error="validation_error", message=str(error)), 422
    add_audit(
        tenant_id,
        user_id,
        "rag_evaluation.executed",
        "rag_evaluation_run",
        run.id,
        after={
            "k": run.k,
            "perguntas": run.question_count,
            "precisionAtK": run.precision_at_k,
            "recallAtK": run.recall_at_k,
            "groundedness": run.groundedness,
            "precisaoCitacoes": run.citation_precision,
            "taxaFontesDesconexas": run.disconnected_source_rate,
            "acuraciaRecusa": run.refusal_accuracy,
            "acuraciaRoteamento": run.routing_accuracy,
            "acuraciaFiltros": run.filter_accuracy,
            "taxaHardNegatives": run.hard_negative_rate,
        },
    )
    db.session.commit()
    return jsonify(evaluation_run_data(run)), 201


@rag_bp.get("/assistente/avaliacoes/execucoes")
@roles_required("admin", "manager")
def list_evaluation_runs():
    tenant_id, _ = _context()
    items = db.session.scalars(
        select(RagEvaluationRun)
        .where(RagEvaluationRun.tenant_id == tenant_id)
        .order_by(RagEvaluationRun.created_at.desc())
        .limit(100)
    )
    return jsonify(content=[evaluation_run_data(item, include_results=False) for item in items])


@rag_bp.patch("/assistente/consultas/<uuid:query_id>/avaliacao")
@jwt_required()
def review_assistant_query(query_id: uuid.UUID):
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    try:
        result = create_feedback_revision(
            tenant_id,
            user_id,
            query_id,
            payload,
            role=str(get_jwt().get("role", "")),
            strict=False,
        )
    except FeedbackNotFoundError as error:
        db.session.rollback()
        return jsonify(error="resource_not_found", message=str(error)), 404
    except FeedbackConflictError as error:
        db.session.rollback()
        return jsonify(error="conflict", message=str(error)), 409
    except FeedbackValidationError as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    item = _assistant_query(tenant_id, query_id)
    add_audit(
        tenant_id,
        user_id,
        "rag_assistant.feedback_recorded",
        "rag_assistant_query",
        item.id,
        after={
            "feedbackId": str(result.feedback.id),
            "revisao": result.feedback.revision,
            "avaliacao": result.feedback.rating.value,
            "estado": result.feedback.status.value,
        },
    )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return (
            jsonify(
                error="conflict",
                message="Outra revisão de feedback foi registrada simultaneamente.",
            ),
            409,
        )
    return jsonify(assistant_query_data(item))


@rag_bp.post("/assistente/consultas/<uuid:query_id>/feedback")
@jwt_required()
def create_assistant_feedback(query_id: uuid.UUID):
    tenant_id, user_id = _context()
    try:
        result = create_feedback_revision(
            tenant_id,
            user_id,
            query_id,
            request.get_json(silent=True) or {},
            role=str(get_jwt().get("role", "")),
        )
        db.session.commit()
    except FeedbackNotFoundError as error:
        db.session.rollback()
        return jsonify(error="resource_not_found", message=str(error)), 404
    except FeedbackConflictError as error:
        db.session.rollback()
        return jsonify(error="conflict", message=str(error)), 409
    except FeedbackValidationError as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    except IntegrityError:
        db.session.rollback()
        return (
            jsonify(
                error="conflict",
                message="Outra revisão de feedback foi registrada simultaneamente.",
            ),
            409,
        )
    return jsonify(feedback_data(result.feedback)), 201 if result.created else 200


@rag_bp.get("/assistente/consultas/<uuid:query_id>/feedback")
@jwt_required()
def list_assistant_query_feedback(query_id: uuid.UUID):
    tenant_id, _ = _context()
    if _assistant_query(tenant_id, query_id) is None:
        return jsonify(error="resource_not_found", message="Consulta RAG não encontrada."), 404
    items = db.session.scalars(
        select(RagQueryFeedback)
        .where(
            RagQueryFeedback.tenant_id == tenant_id,
            RagQueryFeedback.query_id == query_id,
        )
        .order_by(RagQueryFeedback.revision.desc())
    )
    return jsonify(content=[feedback_data(item) for item in items])


@rag_bp.get("/assistente/feedback")
@roles_required("admin", "manager")
def list_assistant_feedback():
    tenant_id, _ = _context()
    statement = select(RagQueryFeedback).where(RagQueryFeedback.tenant_id == tenant_id)
    status_value = str(request.args.get("estado", "")).strip().upper()
    if status_value:
        try:
            status = RagFeedbackStatus(status_value)
        except ValueError:
            return (
                jsonify(error="validation_error", message="Estado de feedback inválido."),
                422,
            )
        statement = statement.where(RagQueryFeedback.status == status)
    items = db.session.scalars(statement.order_by(RagQueryFeedback.created_at.desc()).limit(300))
    return jsonify(content=[feedback_data(item) for item in items])


@rag_bp.patch("/assistente/feedback/<uuid:feedback_id>/moderacao")
@roles_required("admin", "manager")
def moderate_assistant_feedback(feedback_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = _feedback(tenant_id, feedback_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Feedback não encontrado."), 404
    payload = request.get_json(silent=True) or {}
    try:
        moderate_feedback(
            item,
            user_id,
            str(payload.get("decisao", "")),
            payload.get("justificativa"),
        )
        db.session.commit()
    except FeedbackConflictError as error:
        db.session.rollback()
        return jsonify(error="conflict", message=str(error)), 409
    except FeedbackValidationError as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    return jsonify(feedback_data(item))


@rag_bp.post("/assistente/feedback/<uuid:feedback_id>/promover-avaliacao")
@roles_required("admin", "manager")
def promote_assistant_feedback(feedback_id: uuid.UUID):
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return (
            jsonify(error="validation_error", message="O corpo deve ser um objeto."),
            422,
        )
    try:
        item, created = promote_feedback_to_evaluation(
            tenant_id,
            user_id,
            feedback_id,
            notes=payload.get("observacoes"),
        )
        db.session.commit()
    except CurationNotFoundError as error:
        db.session.rollback()
        return jsonify(error="resource_not_found", message=str(error)), 404
    except CurationConflictError as error:
        db.session.rollback()
        return jsonify(error="conflict", message=str(error)), 409
    except CurationValidationError as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    except IntegrityError:
        db.session.rollback()
        return (
            jsonify(
                error="conflict",
                message="O feedback já foi promovido simultaneamente.",
            ),
            409,
        )
    return jsonify(evaluation_question_data(item)), 201 if created else 200


@rag_bp.post("/assistente/aprendizado/execucoes")
@roles_required("admin", "manager")
def create_assistant_learning_run():
    tenant_id, user_id = _context()
    try:
        item, created = create_learning_run(
            tenant_id,
            user_id,
            request.get_json(silent=True) or {},
        )
        db.session.commit()
    except LearningValidationError as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    except IntegrityError:
        db.session.rollback()
        return (
            jsonify(
                error="conflict",
                message="Uma compilação idêntica foi criada simultaneamente.",
            ),
            409,
        )
    return jsonify(learning_run_data(item)), 202 if created else 200


@rag_bp.post("/assistente/calibracoes")
@roles_required("admin")
def create_assistant_quality_calibration():
    tenant_id, user_id = _context()
    try:
        artifact = create_quality_calibration(
            tenant_id,
            user_id,
            str(get_jwt().get("role", "")),
            request.get_json(silent=True) or {},
        )
        db.session.commit()
    except LearningValidationError as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    except IntegrityError:
        db.session.rollback()
        return (
            jsonify(
                error="conflict",
                message="Uma calibração concorrente gerou a mesma versão.",
            ),
            409,
        )
    response = learning_artifact_data(artifact, include_payload=True)
    response["aprovada"] = None
    response["motivos"] = ["AVALIACAO_AGENDADA"]
    return jsonify(response), 202


@rag_bp.get("/assistente/calibracoes")
@roles_required("admin", "manager")
def list_assistant_quality_calibrations():
    tenant_id, _ = _context()
    items = db.session.scalars(
        select(RagLearningArtifact)
        .where(
            RagLearningArtifact.tenant_id == tenant_id,
            RagLearningArtifact.artifact_type == RagLearningArtifactType.QUALITY_PROFILE,
        )
        .order_by(RagLearningArtifact.created_at.desc())
        .limit(100)
    )
    content = [learning_artifact_data(item, include_payload=True) for item in items]
    return jsonify(
        content=content,
        perfilAtivo=next(
            (item for item in content if item["estado"] == "ATIVO"),
            None,
        ),
    )


@rag_bp.get("/assistente/aprendizado/execucoes")
@roles_required("admin", "manager")
def list_assistant_learning_runs():
    tenant_id, _ = _context()
    statement = select(RagLearningRun).where(RagLearningRun.tenant_id == tenant_id)
    status_value = str(request.args.get("estado", "")).strip().upper()
    if status_value:
        try:
            status = RagLearningRunStatus(status_value)
        except ValueError:
            return (
                jsonify(
                    error="validation_error",
                    message="Estado de compilação inválido.",
                ),
                422,
            )
        statement = statement.where(RagLearningRun.status == status)
    items = db.session.scalars(statement.order_by(RagLearningRun.created_at.desc()).limit(300))
    return jsonify(content=[learning_run_data(item) for item in items])


@rag_bp.get("/assistente/aprendizado/artefatos")
@roles_required("admin", "manager")
def list_assistant_learning_artifacts():
    tenant_id, _ = _context()
    statement = select(RagLearningArtifact).where(RagLearningArtifact.tenant_id == tenant_id)
    type_value = str(request.args.get("tipo", "")).strip().upper()
    if type_value:
        try:
            artifact_type = RagLearningArtifactType(type_value)
        except ValueError:
            return (
                jsonify(error="validation_error", message="Tipo de artefato inválido."),
                422,
            )
        statement = statement.where(RagLearningArtifact.artifact_type == artifact_type)
    status_value = str(request.args.get("estado", "")).strip().upper()
    if status_value:
        try:
            status = RagLearningArtifactStatus(status_value)
        except ValueError:
            return (
                jsonify(
                    error="validation_error",
                    message="Estado de artefato inválido.",
                ),
                422,
            )
        statement = statement.where(RagLearningArtifact.status == status)
    items = db.session.scalars(statement.order_by(RagLearningArtifact.created_at.desc()).limit(500))
    return jsonify(content=[learning_artifact_data(item) for item in items])


@rag_bp.get("/assistente/aprendizado/artefatos/<uuid:artifact_id>")
@roles_required("admin", "manager")
def get_assistant_learning_artifact(artifact_id: uuid.UUID):
    tenant_id, _ = _context()
    item = db.session.scalar(
        select(RagLearningArtifact).where(
            RagLearningArtifact.tenant_id == tenant_id,
            RagLearningArtifact.id == artifact_id,
        )
    )
    if item is None:
        return (
            jsonify(error="resource_not_found", message="Artefato não encontrado."),
            404,
        )
    return jsonify(learning_artifact_data(item, include_payload=True))


@rag_bp.post("/assistente/aprendizado/artefatos/<uuid:artifact_id>/avaliacao")
@roles_required("admin")
def evaluate_assistant_learning_artifact(artifact_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = _learning_artifact(tenant_id, artifact_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Artefato não encontrado."), 404
    try:
        approved, reasons = evaluate_learning_artifact(
            item,
            user_id,
            str(get_jwt().get("role", "")),
            request.get_json(silent=True) or {},
        )
        db.session.commit()
    except LearningConflictError as error:
        db.session.rollback()
        return jsonify(error="conflict", message=str(error)), 409
    except (LearningValidationError, ValueError) as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    response = learning_artifact_data(item, include_payload=True)
    if not approved:
        response["motivosRejeicao"] = reasons
        return jsonify(response), 409
    return jsonify(response)


@rag_bp.post("/assistente/aprendizado/artefatos/<uuid:artifact_id>/ativacao")
@roles_required("admin")
def activate_assistant_learning_artifact(artifact_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = _learning_artifact(tenant_id, artifact_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Artefato não encontrado."), 404
    try:
        activate_learning_artifact(
            item,
            user_id,
            request.get_json(silent=True) or {},
        )
        db.session.commit()
    except LearningConflictError as error:
        db.session.rollback()
        return jsonify(error="conflict", message=str(error)), 409
    except LearningValidationError as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    return jsonify(learning_artifact_data(item, include_payload=True))


@rag_bp.post("/assistente/aprendizado/artefatos/<uuid:artifact_id>/rollback")
@roles_required("admin")
def rollback_assistant_learning_artifact(artifact_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = _learning_artifact(tenant_id, artifact_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Artefato não encontrado."), 404
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict) or set(payload) - {"motivo"}:
        return (
            jsonify(error="validation_error", message="O corpo do rollback é inválido."),
            422,
        )
    try:
        restored = rollback_learning_artifact(
            item,
            user_id,
            payload.get("motivo"),
        )
        db.session.commit()
    except LearningConflictError as error:
        db.session.rollback()
        return jsonify(error="conflict", message=str(error)), 409
    except LearningValidationError as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 422
    return jsonify(
        artefatoRevogado=learning_artifact_data(item),
        artefatoRestaurado=learning_artifact_data(restored) if restored else None,
    )


@rag_bp.get("/rag/catalogo-global")
@jwt_required()
def list_global_catalog():
    tenant_id, _ = _context()
    content = []
    for access in collection_access_for_tenant(tenant_id):
        policy = access.collection.distribution_policy
        if access.reason in {"PLATFORM_PRIVATE", "JURISDICTION_MISMATCH"}:
            continue
        if policy == GlobalDistributionPolicy.DIRECIONADA and not access.enabled:
            continue
        content.append(
            {
                "id": str(access.collection.id),
                "nome": access.collection.name,
                "descricao": access.collection.description,
                "politicaDistribuicao": policy.value,
                "jurisdicao": access.collection.jurisdiction,
                "habilitada": access.enabled,
                "motivoAcesso": access.reason,
                "concessao": entitlement_data(access.entitlement),
            }
        )
    return jsonify(content=content)


@rag_bp.patch("/rag/catalogo-global/colecoes/<uuid:collection_id>/adesao")
@roles_required("admin", "manager")
def update_global_catalog_subscription(collection_id: uuid.UUID):
    tenant_id, user_id = _context()
    collection = db.session.get(GlobalKnowledgeCollection, collection_id)
    if collection is None:
        return jsonify(error="resource_not_found", message="Coleção global não encontrada."), 404
    policy = collection.distribution_policy
    entitlement = db.session.execute(
        select(GlobalKnowledgeEntitlement).where(
            GlobalKnowledgeEntitlement.tenant_id == tenant_id,
            GlobalKnowledgeEntitlement.collection_id == collection_id,
        )
    ).scalar_one_or_none()
    if policy == GlobalDistributionPolicy.PRIVADA_PLATAFORMA:
        return (
            jsonify(
                error="forbidden",
                message="Esta coleção não aceita adesão direta do gabinete.",
            ),
            403,
        )
    payload = request.get_json(silent=True) or {}
    enabled = payload.get("habilitada")
    if not isinstance(enabled, bool):
        return jsonify(error="validation_error", message="Informe habilitada como booleano."), 422
    if policy == GlobalDistributionPolicy.DIRECIONADA and not (
        entitlement
        and entitlement.grant_source == "GLOBAL_GRANT"
        and entitlement.status == GlobalEntitlementStatus.ATIVA
    ):
        return (
            jsonify(
                error="forbidden",
                message="Esta coleção exige concessão ativa do curador global.",
            ),
            403,
        )
    if policy == GlobalDistributionPolicy.DIRECIONADA and not enabled:
        return (
            jsonify(
                error="conflict",
                message="O gabinete não pode revogar uma concessão direcionada.",
            ),
            409,
        )
    if not enabled and policy in {
        GlobalDistributionPolicy.OBRIGATORIA,
        GlobalDistributionPolicy.RESTRITA_JURISDICAO,
    }:
        return (
            jsonify(
                error="conflict",
                message="A política desta coleção não permite desativação pelo gabinete.",
            ),
            409,
        )
    try:
        update_mode = GlobalUpdateMode(str(payload.get("modoAtualizacao", "AUTOMATICA")).upper())
        pinned_version_id = (
            uuid.UUID(str(payload["versaoFixadaId"])) if payload.get("versaoFixadaId") else None
        )
    except (TypeError, ValueError):
        return jsonify(error="validation_error", message="Modo ou versão fixada inválida."), 422
    if update_mode == GlobalUpdateMode.FIXADA and pinned_version_id is None:
        return (
            jsonify(
                error="validation_error",
                message="Informe a versão global que deve permanecer fixada.",
            ),
            422,
        )
    if update_mode == GlobalUpdateMode.AUTOMATICA:
        pinned_version_id = None
    if pinned_version_id and not _valid_global_pinned_version(collection_id, pinned_version_id):
        return (
            jsonify(
                error="validation_error",
                message="A versão fixada não pertence à coleção ou não foi publicada.",
            ),
            422,
        )
    before = entitlement_data(entitlement)
    if entitlement is None:
        entitlement = GlobalKnowledgeEntitlement(
            tenant_id=tenant_id,
            collection_id=collection_id,
            granted_by_id=user_id,
            grant_source="TENANT_ADESAO",
        )
        db.session.add(entitlement)
    if entitlement.grant_source != "GLOBAL_GRANT":
        entitlement.status = (
            GlobalEntitlementStatus.ATIVA if enabled else GlobalEntitlementStatus.DESATIVADA
        )
    entitlement.update_mode = update_mode
    entitlement.pinned_version_id = pinned_version_id
    if entitlement.grant_source != "GLOBAL_GRANT":
        entitlement.justification = str(payload.get("justificativa", "")).strip() or None
    db.session.flush()
    add_audit(
        tenant_id,
        user_id,
        "rag_global.subscription_updated",
        "rag_global_entitlement",
        entitlement.id,
        before=before,
        after=entitlement_data(entitlement),
    )
    db.session.commit()
    return jsonify(
        colecaoId=str(collection_id),
        habilitada=enabled,
        concessao=entitlement_data(entitlement),
    )


def operational_source_data(source: RagKnowledgeSource) -> dict:
    document = db.session.get(RagDocument, source.document_id) if source.document_id else None
    title = document.title if document is not None else None
    if title and title.startswith("[Memória] "):
        title = title[len("[Memória] ") :]
    if title and title.endswith(")") and " (" in title:
        title = title.rsplit(" (", 1)[0]
    available = (
        source.status == RagKnowledgeSourceStatus.ATIVA
        and (source.retention_until is None or source.retention_until >= date.today())
        and bool(document and document.active)
    )
    return {
        "id": str(source.id),
        "titulo": title or OPERATIONAL_ENTITY_LABELS.get(source.entity_type, "Memória automática"),
        "origem": {
            "sistema": "GabFlow",
            "modulo": source.source_module,
            "moduloNome": OPERATIONAL_MODULE_LABELS.get(
                source.source_module, source.source_module.replace("_", " ").title()
            ),
            "entidade": source.entity_type,
            "entidadeNome": OPERATIONAL_ENTITY_LABELS.get(
                source.entity_type, source.entity_type.replace("_", " ").title()
            ),
            "entidadeId": str(source.entity_id),
        },
        "modulo": source.source_module,
        "entidadeTipo": source.entity_type,
        "entidadeId": str(source.entity_id),
        "versaoProjetor": source.projector_version,
        "revisaoOrigem": source.source_revision,
        "estado": source.status.value,
        "estadoNome": OPERATIONAL_STATUS_LABELS[source.status.value],
        "disponivelParaInteligencia": available,
        "motivoElegibilidade": source.eligibility_reason,
        "finalidade": source.purpose,
        "finalidadeNome": OPERATIONAL_PURPOSE_LABELS.get(
            source.purpose,
            "Apoiar a inteligência e o trabalho diário do gabinete.",
        ),
        "baseLegal": source.legal_basis,
        "nivelAcesso": source.access_level.value,
        "retencaoAte": (source.retention_until.isoformat() if source.retention_until else None),
        "hashConteudo": source.content_hash,
        "versaoLogica": source.source_version,
        "documentoId": str(source.document_id) if source.document_id else None,
        "versaoAtualId": (str(source.latest_version_id) if source.latest_version_id else None),
        "codigoErro": source.error_code,
        "erro": source.error_message,
        "tentativas": source.sync_attempts,
        "ultimaProjecaoEm": (
            source.last_projected_at.isoformat() if source.last_projected_at else None
        ),
        "quarentenaEm": (source.quarantined_at.isoformat() if source.quarantined_at else None),
        "excluidaEm": (source.deleted_at.isoformat() if source.deleted_at else None),
        "purgeConcluidoEm": (
            source.purge_completed_at.isoformat() if source.purge_completed_at else None
        ),
        "tombstoneHash": source.tombstone_hash,
        "segurancaConteudo": content_security_state(source),
        "criadaEm": source.created_at.isoformat(),
        "atualizadaEm": source.updated_at.isoformat(),
    }


def thematic_memory_data(item: RagThematicMemory) -> dict:
    return {
        "id": str(item.id),
        "tema": item.theme,
        "territorio": item.territory or None,
        "periodo": {
            "inicio": item.period_start.isoformat(),
            "fim": item.period_end.isoformat(),
        },
        "solicitacoes": item.request_count,
        "resolvidas": item.resolved_count,
        "prioridadeAlta": item.high_priority_count,
        "sintese": item.summary,
        "geradaEm": item.generated_at.isoformat(),
    }


def document_data(item: RagDocument, include_versions: bool) -> dict:
    versions = sorted(item.versions, key=lambda value: value.version_number, reverse=True)
    data = {
        "id": str(item.id),
        "titulo": item.title,
        "tipo": item.document_type,
        "orgao": item.agency,
        "nivelAcesso": item.access_level.value,
        "ativo": item.active,
        "quantidadeVersoes": len(versions),
        "ultimaVersao": version_data(versions[0]) if versions else None,
        "criadoEm": item.created_at.isoformat(),
        "atualizadoEm": item.updated_at.isoformat(),
    }
    if include_versions:
        data["versoes"] = [version_data(value) for value in versions]
    return data


def version_data(item: RagDocumentVersion, *, include_download: bool = True) -> dict:
    data = {
        "id": str(item.id),
        "numero": item.version_number,
        "versao": item.version_label,
        "estado": item.lifecycle_status.value,
        "statusIngestao": item.ingestion_status.value,
        "vigenteDesde": item.valid_from.isoformat() if item.valid_from else None,
        "vigenteAte": item.valid_until.isoformat() if item.valid_until else None,
        "urlFonte": item.source_url,
        "arquivo": item.original_name,
        "mimeType": item.mime_type,
        "tamanhoBytes": item.size_bytes,
        "checksum": item.checksum,
        "idioma": item.language,
        "modeloEmbedding": item.embedding_model,
        "paginas": item.page_count,
        "fragmentos": item.chunk_count,
        "erro": item.error,
        "segurancaConteudo": content_security_state(item),
        "verificacaoMalware": malware_scan_state(item),
        "criadaEm": item.created_at.isoformat(),
        "indexadaEm": item.indexed_at.isoformat() if item.indexed_at else None,
        "conteudoDisponivel": item.retention_purged_at is None,
        "conteudoDescartadoEm": (
            item.retention_purged_at.isoformat() if item.retention_purged_at else None
        ),
    }
    if include_download and item.retention_purged_at is None:
        data["downloadUrl"] = (
            f"/api/v1/rag/documentos/{item.document_id}/versoes/{item.id}/download"
            f"?token={signed_rag_download_token(item.tenant_id, item.document_id, item.id)}"
        )
    return data


def _document_values(form) -> dict:
    title = str(form.get("titulo", "")).strip()
    document_type = str(form.get("tipo", "")).strip().upper()
    agency = str(form.get("orgao", "")).strip() or None
    try:
        access = RagDocumentAccess(str(form.get("nivelAcesso", "INTERNO")).upper())
    except ValueError as error:
        raise ValueError("Nível de acesso inválido.") from error
    if not title or len(title) > 240:
        raise ValueError("Informe um título válido.")
    if document_type not in DOCUMENT_TYPES:
        raise ValueError("Tipo documental inválido.")
    if agency and len(agency) > 180:
        raise ValueError("Órgão inválido.")
    return {
        "title": title,
        "document_type": document_type,
        "agency": agency,
        "access_level": access,
    }


def _version_values(form) -> dict:
    label = str(form.get("versao", "1")).strip() or "1"
    source_url = str(form.get("urlFonte", "")).strip() or None
    if len(label) > 80:
        raise ValueError("Versão inválida.")
    if source_url:
        parsed = urlsplit(source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("A URL da fonte deve utilizar HTTP ou HTTPS.")
    try:
        valid_from = date.fromisoformat(form["vigenteDesde"]) if form.get("vigenteDesde") else None
        valid_until = date.fromisoformat(form["vigenteAte"]) if form.get("vigenteAte") else None
    except ValueError as error:
        raise ValueError("Período de vigência inválido.") from error
    if valid_from and valid_until and valid_until < valid_from:
        raise ValueError("A vigência final não pode anteceder a inicial.")
    return {
        "version_label": label,
        "source_url": source_url,
        "valid_from": valid_from,
        "valid_until": valid_until,
    }


def _document(tenant_id: uuid.UUID, document_id: uuid.UUID) -> RagDocument | None:
    return db.session.execute(
        select(RagDocument).where(RagDocument.id == document_id, RagDocument.tenant_id == tenant_id)
    ).scalar_one_or_none()


def _version(
    tenant_id: uuid.UUID, document_id: uuid.UUID, version_id: uuid.UUID
) -> RagDocumentVersion | None:
    return db.session.execute(
        select(RagDocumentVersion).where(
            RagDocumentVersion.id == version_id,
            RagDocumentVersion.document_id == document_id,
            RagDocumentVersion.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()


def _can_access(item: RagDocument) -> bool:
    return item.access_level == RagDocumentAccess.INTERNO or get_jwt().get("role") in {
        "admin",
        "manager",
    }


def _assistant_query(tenant_id: uuid.UUID, query_id: uuid.UUID) -> RagAssistantQuery | None:
    return db.session.execute(
        select(RagAssistantQuery).where(
            RagAssistantQuery.id == query_id,
            RagAssistantQuery.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()


def _feedback(
    tenant_id: uuid.UUID,
    feedback_id: uuid.UUID,
) -> RagQueryFeedback | None:
    return db.session.execute(
        select(RagQueryFeedback).where(
            RagQueryFeedback.id == feedback_id,
            RagQueryFeedback.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()


def _valid_global_pinned_version(collection_id: uuid.UUID, version_id: uuid.UUID) -> bool:
    return (
        db.session.execute(
            select(GlobalKnowledgeDocumentVersion.id)
            .join(GlobalKnowledgeDocumentVersion.document)
            .where(
                GlobalKnowledgeDocumentVersion.id == version_id,
                GlobalKnowledgeDocumentVersion.publication_status.in_(
                    {
                        GlobalVersionStatus.PUBLICADA,
                        GlobalVersionStatus.SUBSTITUIDA,
                    }
                ),
                GlobalKnowledgeDocumentVersion.document.has(collection_id=collection_id),
            )
        ).scalar_one_or_none()
        is not None
    )


def _optional_text(value: object, max_length: int, label: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_length:
        raise ValueError(f"{label} deve ter no máximo {max_length} caracteres.")
    return text


def _evaluation_question_values(payload: dict, tenant_id: uuid.UUID) -> dict:
    question = str(payload.get("pergunta", "")).strip()
    if len(question) < 3 or len(question) > 2000:
        raise ValueError("A pergunta deve possuir entre 3 e 2000 caracteres.")
    expected_values = payload.get("documentosEsperados", [])
    if not isinstance(expected_values, list) or len(expected_values) > 20:
        raise ValueError("Documentos esperados deve ser uma lista com até 20 itens.")
    try:
        expected_ids = list(dict.fromkeys(str(uuid.UUID(str(value))) for value in expected_values))
    except (TypeError, ValueError) as error:
        raise ValueError("Documento esperado inválido.") from error
    if expected_ids:
        found = {
            str(value)
            for value in db.session.scalars(
                select(RagDocument.id).where(
                    RagDocument.tenant_id == tenant_id,
                    RagDocument.id.in_([uuid.UUID(value) for value in expected_ids]),
                )
            )
        }
        if found != set(expected_ids):
            raise ValueError("Documento esperado não pertence ao tenant.")
    expected_refusal = payload.get("esperaRecusa", False)
    active = payload.get("ativa", True)
    if not isinstance(expected_refusal, bool) or not isinstance(active, bool):
        raise ValueError("esperaRecusa e ativa devem ser booleanos.")
    if expected_refusal and expected_ids:
        raise ValueError("Uma pergunta de recusa não deve declarar documentos esperados.")
    if not expected_refusal and not expected_ids:
        raise ValueError("Informe documentos esperados ou marque a pergunta como recusa.")
    return {
        "question": question,
        "expected_document_ids": expected_ids,
        "expected_refusal": expected_refusal,
        "notes": _optional_text(payload.get("observacoes"), 2000, "Observações"),
        "case_origin": "MANUAL",
        "active": active,
    }


def assistant_query_data(item: RagAssistantQuery) -> dict:
    return {
        "id": str(item.id),
        "consulta": item.query_text,
        "resposta": item.response,
        "fontes": item.sources,
        "seguranca": item.safety_flags,
        "fundamentada": item.grounded,
        "recusaConclusiva": item.refused,
        "limiarEvidencia": item.evidence_threshold,
        "modeloEmbedding": item.embedding_model,
        "fallbackUtilizado": item.fallback_used,
        "metodo": item.method,
        "motivosRoteamento": item.routing_reasons,
        "filtrosAplicados": item.applied_filters,
        "resultadoEstruturado": item.structured_result,
        "artefatosAprendizado": item.learning_artifacts,
        "validacaoSaida": item.output_validation,
        "bloqueioValidacaoSaida": item.output_validation_enforced,
        "avaliacao": item.feedback_rating.value if item.feedback_rating else None,
        "comentario": item.feedback_comment,
        "respostaCorrigida": item.corrected_response,
        "revisadaEm": item.reviewed_at.isoformat() if item.reviewed_at else None,
        "criadaEm": item.created_at.isoformat(),
    }


def _learning_artifact(
    tenant_id: uuid.UUID,
    artifact_id: uuid.UUID,
) -> RagLearningArtifact | None:
    return db.session.scalar(
        select(RagLearningArtifact).where(
            RagLearningArtifact.tenant_id == tenant_id,
            RagLearningArtifact.id == artifact_id,
        )
    )
