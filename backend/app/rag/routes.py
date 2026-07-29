import hashlib
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import func, or_, select
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
    RagIngestionStatus,
    RagKnowledgeSource,
    RagKnowledgeSourceStatus,
    RagQueryFeedbackRating,
    RagThematicMemory,
    utc_now,
)
from app.observability import percentile
from app.rag.analytics import rebuild_thematic_memories, structured_query
from app.rag.distribution import collection_access_for_tenant, entitlement_data
from app.rag.evaluation import (
    evaluation_question_data,
    evaluation_run_data,
    execute_tenant_evaluation,
)
from app.rag.operational_memory import reprocess_operational_memory
from app.rag.retrieval import query_audit_payload
from app.rag.router import route_query
from app.rag.service import enqueue_ingestion, requeue_ingestion
from app.rag.storage import (
    RagStorageError,
    rag_document_path,
    signed_rag_download_token,
    store_rag_document,
    verify_rag_download_token,
)

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


@rag_bp.get("/rag/fontes-operacionais")
@roles_required("admin", "manager")
def list_operational_sources():
    tenant_id, _ = _context()
    statement = select(RagKnowledgeSource).where(
        RagKnowledgeSource.tenant_id == tenant_id
    )
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
        statement = statement.where(
            RagKnowledgeSource.source_module == source_module[:60]
        )
    entity_type = str(request.args.get("entidadeTipo", "")).strip().upper()
    if entity_type:
        statement = statement.where(
            RagKnowledgeSource.entity_type == entity_type[:80]
        )
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
    statement = select(RagDocument).where(RagDocument.tenant_id == tenant_id)
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
    requeue_ingestion(item)
    add_audit(tenant_id, user_id, "rag_document.reprocessed", "rag_document_version", item.id)
    db.session.commit()
    return jsonify(version_data(item)), 202


@rag_bp.get("/rag/documentos/<uuid:document_id>/versoes/<uuid:version_id>/download")
@jwt_required()
def download_version(document_id: uuid.UUID, version_id: uuid.UUID):
    tenant_id, _ = _context()
    item = _version(tenant_id, document_id, version_id)
    if item is None or not _can_access(item.document):
        return jsonify(error="resource_not_found", message="Versão não encontrada."), 404
    if not verify_rag_download_token(
        str(request.args.get("token", "")),
        tenant_id,
        document_id,
        version_id,
    ):
        return jsonify(error="invalid_download_token", message="Link inválido ou expirado."), 403
    return send_file(
        rag_document_path(
            item.storage_key,
            tenant_id=tenant_id,
            document_id=document_id,
            version_id=version_id,
        ),
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
        )
    except (TypeError, ValueError) as error:
        return jsonify(error="validation_error", message=str(error)), 422
    query = RagAssistantQuery(
        tenant_id=tenant_id,
        user_id=user_id,
        query_text=answer["consulta"],
        query_hash=hashlib.sha256(answer["consulta"].encode("utf-8")).hexdigest(),
        response=answer["resposta"],
        sources=answer["fontes"],
        safety_flags=answer["seguranca"],
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
    )
    db.session.add(query)
    db.session.flush()
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
    since = datetime.now(UTC) - timedelta(
        hours=current_app.config["RAG_METRICS_WINDOW_HOURS"]
    )
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
    return jsonify(
        janelaHoras=current_app.config["RAG_METRICS_WINDOW_HOURS"],
        consultas=total,
        fundamentadas=sum(item.grounded for item in items),
        recusadas=sum(item.refused for item in items),
        fallback=sum(item.fallback_used for item in items),
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


@rag_bp.get("/assistente/avaliacoes/perguntas")
@roles_required("admin", "manager")
def list_evaluation_questions():
    tenant_id, _ = _context()
    items = db.session.scalars(
        select(RagEvaluationQuestion)
        .where(RagEvaluationQuestion.tenant_id == tenant_id)
        .order_by(RagEvaluationQuestion.created_at.desc())
    )
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
    merged = {
        "pergunta": payload.get("pergunta", item.question),
        "documentosEsperados": payload.get(
            "documentosEsperados", item.expected_document_ids
        ),
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
    return jsonify(
        content=[
            evaluation_run_data(item, include_results=False) for item in items
        ]
    )


@rag_bp.patch("/assistente/consultas/<uuid:query_id>/avaliacao")
@jwt_required()
def review_assistant_query(query_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = _assistant_query(tenant_id, query_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Consulta RAG não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    try:
        rating = RagQueryFeedbackRating(str(payload.get("avaliacao", "")).upper())
        comment = _optional_text(payload.get("comentario"), 2000, "Comentário")
        corrected_response = _optional_text(
            payload.get("respostaCorrigida"), 10000, "Resposta corrigida"
        )
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    if rating == RagQueryFeedbackRating.CORRIGIDA and not corrected_response:
        return jsonify(
            error="validation_error",
            message="Informe a resposta corrigida para uma avaliação corrigida.",
        ), 422
    before = {
        "avaliacao": item.feedback_rating.value if item.feedback_rating else None,
        "comentario": item.feedback_comment,
        "possuiCorrecao": bool(item.corrected_response),
    }
    item.feedback_rating = rating
    item.feedback_comment = comment
    item.corrected_response = corrected_response
    item.reviewed_by_id = user_id
    item.reviewed_at = utc_now()
    after = {
        "avaliacao": item.feedback_rating.value,
        "comentario": item.feedback_comment,
        "possuiCorrecao": bool(item.corrected_response),
    }
    add_audit(
        tenant_id,
        user_id,
        "rag_assistant.feedback_recorded",
        "rag_assistant_query",
        item.id,
        before=before,
        after=after,
    )
    db.session.commit()
    return jsonify(assistant_query_data(item))


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
    return {
        "id": str(source.id),
        "modulo": source.source_module,
        "entidadeTipo": source.entity_type,
        "entidadeId": str(source.entity_id),
        "versaoProjetor": source.projector_version,
        "revisaoOrigem": source.source_revision,
        "estado": source.status.value,
        "motivoElegibilidade": source.eligibility_reason,
        "finalidade": source.purpose,
        "baseLegal": source.legal_basis,
        "nivelAcesso": source.access_level.value,
        "retencaoAte": (
            source.retention_until.isoformat()
            if source.retention_until
            else None
        ),
        "hashConteudo": source.content_hash,
        "versaoLogica": source.source_version,
        "documentoId": str(source.document_id) if source.document_id else None,
        "versaoAtualId": (
            str(source.latest_version_id) if source.latest_version_id else None
        ),
        "codigoErro": source.error_code,
        "erro": source.error_message,
        "tentativas": source.sync_attempts,
        "ultimaProjecaoEm": (
            source.last_projected_at.isoformat()
            if source.last_projected_at
            else None
        ),
        "quarentenaEm": (
            source.quarantined_at.isoformat()
            if source.quarantined_at
            else None
        ),
        "excluidaEm": (
            source.deleted_at.isoformat() if source.deleted_at else None
        ),
        "purgeConcluidoEm": (
            source.purge_completed_at.isoformat()
            if source.purge_completed_at
            else None
        ),
        "tombstoneHash": source.tombstone_hash,
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


def version_data(item: RagDocumentVersion) -> dict:
    return {
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
        "criadaEm": item.created_at.isoformat(),
        "indexadaEm": item.indexed_at.isoformat() if item.indexed_at else None,
        "downloadUrl": (
            f"/api/v1/rag/documentos/{item.document_id}/versoes/{item.id}/download"
            f"?token={signed_rag_download_token(item.tenant_id, item.document_id, item.id)}"
        ),
    }


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
        expected_ids = list(
            dict.fromkeys(str(uuid.UUID(str(value))) for value in expected_values)
        )
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
        raise ValueError(
            "Informe documentos esperados ou marque a pergunta como recusa."
        )
    return {
        "question": question,
        "expected_document_ids": expected_ids,
        "expected_refusal": expected_refusal,
        "notes": _optional_text(payload.get("observacoes"), 2000, "Observações"),
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
        "avaliacao": item.feedback_rating.value if item.feedback_rating else None,
        "comentario": item.feedback_comment,
        "respostaCorrigida": item.corrected_response,
        "revisadaEm": item.reviewed_at.isoformat() if item.reviewed_at else None,
        "criadaEm": item.created_at.isoformat(),
    }
