import hashlib
import uuid
from datetime import date
from urllib.parse import urlsplit

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.audit import add_audit
from app.auth.permissions import roles_required
from app.extensions import db
from app.models import (
    RagAssistantQuery,
    RagDocument,
    RagDocumentAccess,
    RagDocumentLifecycle,
    RagDocumentVersion,
    RagIngestionStatus,
    RagQueryFeedbackRating,
    utc_now,
)
from app.rag.retrieval import answer_query, query_audit_payload
from app.rag.service import enqueue_ingestion, requeue_ingestion
from app.rag.storage import RagStorageError, rag_document_path, store_rag_document

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
    item = RagDocument(tenant_id=tenant_id, created_by_id=user_id, **values)
    version = RagDocumentVersion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        document=item,
        version_number=1,
        created_by_id=user_id,
        **version_values,
    )
    try:
        stored = store_rag_document(tenant_id, version.id, uploaded_file)
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
        stored = store_rag_document(tenant_id, version.id, uploaded_file)
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
    return send_file(
        rag_document_path(item.storage_key),
        mimetype=item.mime_type,
        download_name=item.original_name,
        as_attachment=True,
    )


@rag_bp.post("/assistente/consultas")
@jwt_required()
def create_assistant_query():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    try:
        answer = answer_query(
            tenant_id,
            get_jwt().get("role"),
            str(payload.get("consulta", "")),
            payload.get("limite"),
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
    return jsonify(answer)


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
        "downloadUrl": f"/api/v1/rag/documentos/{item.document_id}/versoes/{item.id}/download",
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


def _optional_text(value: object, max_length: int, label: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_length:
        raise ValueError(f"{label} deve ter no máximo {max_length} caracteres.")
    return text


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
        "avaliacao": item.feedback_rating.value if item.feedback_rating else None,
        "comentario": item.feedback_comment,
        "respostaCorrigida": item.corrected_response,
        "revisadaEm": item.reviewed_at.isoformat() if item.reviewed_at else None,
        "criadaEm": item.created_at.isoformat(),
    }
