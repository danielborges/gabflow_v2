import io
import uuid
from datetime import date
from urllib.parse import urlsplit

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.audit import add_audit
from app.auth.permissions import global_knowledge_admin_required
from app.extensions import db
from app.models import (
    GlobalCatalogStatus,
    GlobalDistributionPolicy,
    GlobalEntitlementStatus,
    GlobalKnowledgeCollection,
    GlobalKnowledgeDocument,
    GlobalKnowledgeDocumentVersion,
    GlobalKnowledgeEntitlement,
    GlobalUpdateMode,
    GlobalVersionStatus,
    OutboxEvent,
    RagIngestionStatus,
    RagSecurityRescanRun,
    RagSecurityRescanScope,
    Tenant,
    utc_now,
)
from app.rag.content_security import (
    ContentSecurityAction,
    ContentSecurityReviewDecision,
    ContentSecurityStatus,
    content_security_state,
    record_content_security_review,
)
from app.rag.distribution import entitlement_data
from app.rag.global_service import GLOBAL_RAG_INGESTION_EVENT
from app.rag.security_rescan import (
    SecurityRescanConflictError,
    create_security_rescan,
    security_rescan_data,
)
from app.rag.storage import (
    RagStorageError,
    global_rag_document_path,
    signed_global_rag_download_token,
    store_global_rag_document,
    verify_global_rag_download_token,
)
from app.security.encryption import read_plaintext
from app.security.malware import malware_scan_state
from app.tenant_context import activate_global_knowledge_context

global_rag_bp = Blueprint("global_rag", __name__)


def _actor_id() -> uuid.UUID:
    return uuid.UUID(get_jwt_identity())


@global_rag_bp.get("/colecoes")
@global_knowledge_admin_required
def list_collections():
    search = str(request.args.get("q", "")).strip()
    statement = select(GlobalKnowledgeCollection)
    if search:
        statement = statement.where(
            or_(
                GlobalKnowledgeCollection.name.ilike(f"%{search[:100]}%"),
                GlobalKnowledgeCollection.description.ilike(f"%{search[:100]}%"),
            )
        )
    items = db.session.execute(
        statement.order_by(GlobalKnowledgeCollection.updated_at.desc()).limit(300)
    ).scalars()
    return jsonify(content=[collection_data(item, include_documents=False) for item in items])


@global_rag_bp.get("/quarentena")
@global_knowledge_admin_required
def list_security_quarantine():
    items = db.session.scalars(
        select(GlobalKnowledgeDocumentVersion)
        .where(GlobalKnowledgeDocumentVersion.security_status != ContentSecurityStatus.CLEAN)
        .order_by(
            GlobalKnowledgeDocumentVersion.security_quarantined_at.desc(),
            GlobalKnowledgeDocumentVersion.created_at,
        )
        .limit(300)
    )
    return jsonify(
        content=[
            {
                **version_data(item, include_download=False),
                "colecaoId": str(item.document.collection_id),
                "titulo": item.document.title,
            }
            for item in items
        ]
    )


@global_rag_bp.post("/seguranca/revarreduras")
@global_knowledge_admin_required
def create_global_security_rescan():
    activate_global_knowledge_context()
    payload = request.get_json(silent=True) or {}
    try:
        batch_size = int(payload.get("tamanhoLote", 20))
        run = create_security_rescan(
            tenant_id=None,
            actor_id=_actor_id(),
            scope=RagSecurityRescanScope.GLOBAL,
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
        return jsonify(error="conflict", message="Já existe uma revarredura global ativa."), 409
    return jsonify(security_rescan_data(run)), 202


@global_rag_bp.get("/seguranca/revarreduras")
@global_knowledge_admin_required
def list_global_security_rescans():
    activate_global_knowledge_context()
    runs = db.session.scalars(
        select(RagSecurityRescanRun)
        .where(RagSecurityRescanRun.tenant_id.is_(None))
        .order_by(RagSecurityRescanRun.created_at.desc())
        .limit(100)
    )
    return jsonify(content=[security_rescan_data(run) for run in runs])


@global_rag_bp.get("/seguranca/revarreduras/<uuid:run_id>")
@global_knowledge_admin_required
def get_global_security_rescan(run_id: uuid.UUID):
    activate_global_knowledge_context()
    run = db.session.scalar(
        select(RagSecurityRescanRun).where(
            RagSecurityRescanRun.id == run_id,
            RagSecurityRescanRun.tenant_id.is_(None),
        )
    )
    if run is None:
        return jsonify(error="resource_not_found", message="Revarredura não encontrada."), 404
    return jsonify(security_rescan_data(run))


@global_rag_bp.post("/colecoes")
@global_knowledge_admin_required
def create_collection():
    payload = request.get_json(silent=True) or {}
    try:
        values = _collection_values(payload)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    item = GlobalKnowledgeCollection(id=uuid.uuid4(), created_by_id=_actor_id(), **values)
    db.session.add(item)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="conflict", message="Já existe uma coleção com esse nome."), 409
    add_audit(
        None,
        _actor_id(),
        "rag_global.collection_created",
        "rag_global_collection",
        item.id,
        after={
            "nome": item.name,
            "politicaDistribuicao": item.distribution_policy.value,
        },
    )
    db.session.commit()
    return jsonify(collection_data(item, include_documents=True)), 201


@global_rag_bp.get("/colecoes/<uuid:collection_id>")
@global_knowledge_admin_required
def get_collection(collection_id: uuid.UUID):
    item = db.session.get(GlobalKnowledgeCollection, collection_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Coleção global não encontrada."), 404
    return jsonify(collection_data(item, include_documents=True))


@global_rag_bp.patch("/colecoes/<uuid:collection_id>")
@global_knowledge_admin_required
def update_collection(collection_id: uuid.UUID):
    item = db.session.get(GlobalKnowledgeCollection, collection_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Coleção global não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    merged = {
        "nome": payload.get("nome", item.name),
        "descricao": payload.get("descricao", item.description),
        "politicaDistribuicao": payload.get("politicaDistribuicao", item.distribution_policy.value),
        "jurisdicao": payload.get("jurisdicao", item.jurisdiction),
    }
    try:
        values = _collection_values(merged)
        new_status = (
            GlobalCatalogStatus(str(payload["estado"]).upper())
            if "estado" in payload
            else item.status
        )
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    if "estado" in payload and new_status not in {
        GlobalCatalogStatus.SUSPENSA,
        GlobalCatalogStatus.ARQUIVADA,
    }:
        return (
            jsonify(
                error="validation_error",
                message=(
                    "A publicação da coleção é derivada de uma versão indexada; "
                    "somente suspensão ou arquivamento são manuais."
                ),
            ),
            422,
        )
    before = {
        "nome": item.name,
        "politicaDistribuicao": item.distribution_policy.value,
        "estado": item.status.value,
    }
    for key, value in values.items():
        setattr(item, key, value)
    item.status = new_status
    if new_status == GlobalCatalogStatus.PUBLICADA and item.published_at is None:
        item.published_at = utc_now()
    add_audit(
        None,
        _actor_id(),
        "rag_global.collection_updated",
        "rag_global_collection",
        item.id,
        before=before,
        after={
            "nome": item.name,
            "politicaDistribuicao": item.distribution_policy.value,
            "estado": item.status.value,
        },
    )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="conflict", message="Já existe uma coleção com esse nome."), 409
    return jsonify(collection_data(item, include_documents=True))


@global_rag_bp.post("/colecoes/<uuid:collection_id>/documentos")
@global_knowledge_admin_required
def create_document(collection_id: uuid.UUID):
    collection = db.session.get(GlobalKnowledgeCollection, collection_id)
    if collection is None:
        return jsonify(error="resource_not_found", message="Coleção global não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    try:
        values = _document_values(payload)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    item = GlobalKnowledgeDocument(
        id=uuid.uuid4(),
        collection_id=collection.id,
        created_by_id=_actor_id(),
        **values,
    )
    db.session.add(item)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify(
            error="conflict",
            message="Já existe um documento com esse título na coleção.",
        ), 409
    add_audit(
        None,
        _actor_id(),
        "rag_global.document_created",
        "rag_global_document",
        item.id,
        after={"colecaoId": str(collection.id), "titulo": item.title},
    )
    db.session.commit()
    return jsonify(document_data(item, include_versions=True)), 201


@global_rag_bp.get("/colecoes/<uuid:collection_id>/documentos/<uuid:document_id>")
@global_knowledge_admin_required
def get_document(collection_id: uuid.UUID, document_id: uuid.UUID):
    item = _document(collection_id, document_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Documento global não encontrado."), 404
    return jsonify(document_data(item, include_versions=True))


@global_rag_bp.post("/colecoes/<uuid:collection_id>/documentos/<uuid:document_id>/versoes")
@global_knowledge_admin_required
def create_version(collection_id: uuid.UUID, document_id: uuid.UUID):
    item = _document(collection_id, document_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Documento global não encontrado."), 404
    try:
        values = _version_values(request.form)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    uploaded_file = request.files.get("arquivo")
    if uploaded_file is None:
        return jsonify(error="validation_error", message="Envie o arquivo da versão."), 422
    next_number = (
        db.session.scalar(
            select(func.max(GlobalKnowledgeDocumentVersion.version_number)).where(
                GlobalKnowledgeDocumentVersion.document_id == item.id
            )
        )
        or 0
    ) + 1
    version = GlobalKnowledgeDocumentVersion(
        id=uuid.uuid4(),
        document_id=item.id,
        version_number=next_number,
        created_by_id=_actor_id(),
        **values,
    )
    try:
        stored = store_global_rag_document(item.id, version.id, uploaded_file)
    except RagStorageError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    for field, value in stored.items():
        setattr(version, field, value)
    db.session.add(version)
    db.session.add(
        OutboxEvent(
            tenant_id=None,
            event_type=GLOBAL_RAG_INGESTION_EVENT,
            aggregate_type="DocumentoRagGlobal",
            aggregate_id=str(version.id),
            payload={"versionId": str(version.id)},
        )
    )
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="conflict", message="Esta versão global já existe."), 409
    add_audit(
        None,
        _actor_id(),
        "rag_global.version_created",
        "rag_global_document_version",
        version.id,
        after={
            "documentoId": str(item.id),
            "versao": version.version_label,
            "checksum": version.checksum,
        },
    )
    db.session.commit()
    return jsonify(version_data(version)), 202


@global_rag_bp.patch(
    "/colecoes/<uuid:collection_id>/documentos/<uuid:document_id>/versoes/<uuid:version_id>/estado"
)
@global_knowledge_admin_required
def change_version_status(
    collection_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
):
    version = _version(collection_id, document_id, version_id)
    if version is None:
        return jsonify(error="resource_not_found", message="Versão global não encontrada."), 404
    try:
        target = GlobalVersionStatus(
            str((request.get_json(silent=True) or {}).get("estado", "")).upper()
        )
    except ValueError:
        return jsonify(error="validation_error", message="Estado global inválido."), 422
    if target in {GlobalVersionStatus.RASCUNHO, GlobalVersionStatus.SUBSTITUIDA}:
        return jsonify(
            error="validation_error",
            message="Esse estado não pode ser atribuído manualmente.",
        ), 422
    if version.publication_status == GlobalVersionStatus.REVOGADA:
        return (
            jsonify(
                error="conflict",
                message="Uma versão revogada não pode voltar ao ciclo de publicação.",
            ),
            409,
        )
    allowed_transitions = {
        GlobalVersionStatus.RASCUNHO: {GlobalVersionStatus.PUBLICADA},
        GlobalVersionStatus.PUBLICADA: {
            GlobalVersionStatus.SUSPENSA,
            GlobalVersionStatus.REVOGADA,
        },
        GlobalVersionStatus.SUSPENSA: {
            GlobalVersionStatus.PUBLICADA,
            GlobalVersionStatus.REVOGADA,
        },
        GlobalVersionStatus.SUBSTITUIDA: {GlobalVersionStatus.REVOGADA},
        GlobalVersionStatus.REVOGADA: set(),
    }
    if target not in allowed_transitions[version.publication_status]:
        return (
            jsonify(
                error="conflict",
                message=(
                    f"Transição de {version.publication_status.value} "
                    f"para {target.value} não permitida."
                ),
            ),
            409,
        )
    if (
        target == GlobalVersionStatus.PUBLICADA
        and version.ingestion_status != RagIngestionStatus.INDEXADO
    ):
        return jsonify(
            error="conflict",
            message="Somente versões globais indexadas podem ser publicadas.",
        ), 409
    if target == GlobalVersionStatus.PUBLICADA and (
        version.security_status != ContentSecurityStatus.CLEAN
        or version.security_action != ContentSecurityAction.ALLOW
        or version.malware_scan_status != "CLEAN"
    ):
        return jsonify(
            error="content_security_blocked",
            message="Somente versões globais CLEAN/ALLOW e sem malware podem ser publicadas.",
        ), 409
    before = version.publication_status.value
    if target == GlobalVersionStatus.PUBLICADA:
        published = db.session.execute(
            select(GlobalKnowledgeDocumentVersion).where(
                GlobalKnowledgeDocumentVersion.document_id == document_id,
                GlobalKnowledgeDocumentVersion.id != version.id,
                GlobalKnowledgeDocumentVersion.publication_status == GlobalVersionStatus.PUBLICADA,
            )
        ).scalars()
        for previous in published:
            previous.publication_status = GlobalVersionStatus.SUBSTITUIDA
        version.published_at = utc_now()
        version.published_by_id = _actor_id()
        version.document.collection.status = GlobalCatalogStatus.PUBLICADA
        if version.document.collection.published_at is None:
            version.document.collection.published_at = version.published_at
    version.publication_status = target
    if target in {GlobalVersionStatus.SUSPENSA, GlobalVersionStatus.REVOGADA}:
        another_published = db.session.scalar(
            select(GlobalKnowledgeDocumentVersion.id)
            .join(GlobalKnowledgeDocument)
            .where(
                GlobalKnowledgeDocument.collection_id == collection_id,
                GlobalKnowledgeDocumentVersion.id != version.id,
                GlobalKnowledgeDocumentVersion.publication_status == GlobalVersionStatus.PUBLICADA,
            )
            .limit(1)
        )
        if another_published is None:
            version.document.collection.status = GlobalCatalogStatus.SUSPENSA
    add_audit(
        None,
        _actor_id(),
        f"rag_global.version_{target.value.lower()}",
        "rag_global_document_version",
        version.id,
        before={"estado": before},
        after={
            "estado": target.value,
            "documentoId": str(document_id),
            "checksum": version.checksum,
        },
    )
    db.session.commit()
    return jsonify(version_data(version))


@global_rag_bp.post(
    "/colecoes/<uuid:collection_id>/documentos/<uuid:document_id>"
    "/versoes/<uuid:version_id>/reprocessar"
)
@global_knowledge_admin_required
def reprocess_version(
    collection_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
):
    version = _version(collection_id, document_id, version_id)
    if version is None:
        return jsonify(error="resource_not_found", message="Versão global não encontrada."), 404
    if version.ingestion_status not in {
        RagIngestionStatus.FALHOU,
        RagIngestionStatus.INDEXADO,
    }:
        return (
            jsonify(
                error="conflict",
                message="A versão global já está na fila de processamento.",
            ),
            409,
        )
    if version.publication_status != GlobalVersionStatus.RASCUNHO and not (
        version.publication_status == GlobalVersionStatus.SUSPENSA
        and version.security_status != ContentSecurityStatus.CLEAN
    ):
        return (
            jsonify(
                error="conflict",
                message="Somente versões globais em rascunho podem ser reprocessadas.",
            ),
            409,
        )
    if version.security_status in {
        ContentSecurityStatus.SUSPICIOUS,
        ContentSecurityStatus.MALICIOUS,
    } and (
        version.security_review_decision != ContentSecurityReviewDecision.APPROVED
        or version.security_review_checksum != version.security_content_checksum
    ):
        return (
            jsonify(
                error="content_security_review_required",
                message="A versão global em quarentena precisa de aprovação vinculada ao checksum.",
            ),
            409,
        )
    version.ingestion_status = RagIngestionStatus.PENDENTE
    version.error = None
    version.started_at = None
    version.indexed_at = None
    db.session.add(
        OutboxEvent(
            tenant_id=None,
            event_type=GLOBAL_RAG_INGESTION_EVENT,
            aggregate_type="DocumentoRagGlobal",
            aggregate_id=str(version.id),
            payload={"versionId": str(version.id)},
        )
    )
    add_audit(
        None,
        _actor_id(),
        "rag_global.version_reprocessed",
        "rag_global_document_version",
        version.id,
    )
    db.session.commit()
    return jsonify(version_data(version)), 202


@global_rag_bp.patch(
    "/colecoes/<uuid:collection_id>/documentos/<uuid:document_id>"
    "/versoes/<uuid:version_id>/seguranca"
)
@global_knowledge_admin_required
def review_version_security(
    collection_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
):
    version = _version(collection_id, document_id, version_id)
    if version is None:
        return jsonify(error="resource_not_found", message="Versão global não encontrada."), 404
    if version.security_status not in {
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
    before = content_security_state(version)
    actor_id = _actor_id()
    record_content_security_review(
        version,
        decision,
        reviewer_id=actor_id,
        reason=reason,
    )
    add_audit(
        None,
        actor_id,
        "rag_global.version_security_reviewed",
        "rag_global_document_version",
        version.id,
        before={
            "status": before["status"],
            "reviewDecision": before["review"]["decision"],
        },
        after={
            "status": version.security_status.value,
            "reviewDecision": decision.value,
            "contentChecksum": version.security_review_checksum,
        },
    )
    db.session.commit()
    return jsonify(version_data(version))


@global_rag_bp.put("/colecoes/<uuid:collection_id>/concessoes/<uuid:tenant_id>")
@global_knowledge_admin_required
def upsert_targeted_entitlement(
    collection_id: uuid.UUID,
    tenant_id: uuid.UUID,
):
    activate_global_knowledge_context()
    collection = db.session.get(GlobalKnowledgeCollection, collection_id)
    tenant = db.session.get(Tenant, tenant_id)
    if collection is None or tenant is None:
        return (
            jsonify(
                error="resource_not_found",
                message="Coleção global ou gabinete não encontrado.",
            ),
            404,
        )
    if collection.distribution_policy != GlobalDistributionPolicy.DIRECIONADA:
        return (
            jsonify(
                error="conflict",
                message="Concessão global explícita exige política DIRECIONADA.",
            ),
            409,
        )
    payload = request.get_json(silent=True) or {}
    justification = str(payload.get("justificativa", "")).strip()
    if not justification or len(justification) > 2000:
        return (
            jsonify(
                error="validation_error",
                message="Informe uma justificativa de até 2000 caracteres.",
            ),
            422,
        )
    try:
        status = GlobalEntitlementStatus(str(payload.get("estado", "ATIVA")).upper())
        valid_from = (
            date.fromisoformat(str(payload["vigenteDesde"]))
            if payload.get("vigenteDesde")
            else None
        )
        valid_until = (
            date.fromisoformat(str(payload["vigenteAte"])) if payload.get("vigenteAte") else None
        )
    except ValueError:
        return (
            jsonify(
                error="validation_error",
                message="Estado ou período da concessão inválido.",
            ),
            422,
        )
    if valid_from and valid_until and valid_until < valid_from:
        return (
            jsonify(
                error="validation_error",
                message="A vigência final não pode anteceder a inicial.",
            ),
            422,
        )
    entitlement = db.session.execute(
        select(GlobalKnowledgeEntitlement).where(
            GlobalKnowledgeEntitlement.tenant_id == tenant_id,
            GlobalKnowledgeEntitlement.collection_id == collection_id,
        )
    ).scalar_one_or_none()
    before = entitlement_data(entitlement)
    if entitlement is None:
        entitlement = GlobalKnowledgeEntitlement(
            tenant_id=tenant_id,
            collection_id=collection_id,
            granted_by_id=_actor_id(),
            grant_source="GLOBAL_GRANT",
        )
        db.session.add(entitlement)
    entitlement.status = status
    entitlement.update_mode = GlobalUpdateMode.AUTOMATICA
    entitlement.pinned_version_id = None
    entitlement.grant_source = "GLOBAL_GRANT"
    entitlement.justification = justification
    entitlement.valid_from = valid_from
    entitlement.valid_until = valid_until
    entitlement.granted_by_id = _actor_id()
    db.session.flush()
    add_audit(
        None,
        _actor_id(),
        "rag_global.entitlement_updated",
        "rag_global_entitlement",
        entitlement.id,
        before=before,
        after={
            **(entitlement_data(entitlement) or {}),
            "tenantId": str(tenant_id),
            "colecaoId": str(collection_id),
        },
    )
    db.session.commit()
    return jsonify(
        tenantId=str(tenant_id),
        colecaoId=str(collection_id),
        concessao=entitlement_data(entitlement),
    )


@global_rag_bp.get(
    "/colecoes/<uuid:collection_id>/documentos/<uuid:document_id>"
    "/versoes/<uuid:version_id>/download"
)
@global_knowledge_admin_required
def download_version(
    collection_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
):
    version = _version(collection_id, document_id, version_id)
    if version is None:
        return jsonify(error="resource_not_found", message="Versão global não encontrada."), 404
    if not verify_global_rag_download_token(
        str(request.args.get("token", "")), document_id, version_id
    ):
        return jsonify(error="invalid_download_token", message="Link inválido ou expirado."), 403
    path = global_rag_document_path(
            version.storage_key,
            document_id=document_id,
            version_id=version_id,
        )
    return send_file(
        io.BytesIO(read_plaintext(path, "global")),
        mimetype=version.mime_type,
        download_name=version.original_name,
        as_attachment=True,
    )


def collection_data(item: GlobalKnowledgeCollection, *, include_documents: bool) -> dict:
    data = {
        "id": str(item.id),
        "nome": item.name,
        "descricao": item.description,
        "politicaDistribuicao": item.distribution_policy.value,
        "jurisdicao": item.jurisdiction,
        "estado": item.status.value,
        "publicadaEm": item.published_at.isoformat() if item.published_at else None,
        "quantidadeDocumentos": len(item.documents),
        "criadaEm": item.created_at.isoformat(),
        "atualizadaEm": item.updated_at.isoformat(),
    }
    if include_documents:
        data["documentos"] = [
            document_data(document, include_versions=False)
            for document in sorted(item.documents, key=lambda value: value.updated_at, reverse=True)
        ]
    return data


def document_data(item: GlobalKnowledgeDocument, *, include_versions: bool) -> dict:
    versions = sorted(item.versions, key=lambda value: value.version_number, reverse=True)
    data = {
        "id": str(item.id),
        "colecaoId": str(item.collection_id),
        "titulo": item.title,
        "tipo": item.document_type,
        "orgao": item.agency,
        "jurisdicao": item.jurisdiction,
        "proveniencia": item.provenance,
        "nivelConfianca": item.confidence_level,
        "ativo": item.active,
        "quantidadeVersoes": len(versions),
        "ultimaVersao": version_data(versions[0]) if versions else None,
        "criadoEm": item.created_at.isoformat(),
        "atualizadoEm": item.updated_at.isoformat(),
    }
    if include_versions:
        data["versoes"] = [version_data(version) for version in versions]
    return data


def version_data(
    item: GlobalKnowledgeDocumentVersion,
    *,
    include_download: bool = True,
) -> dict:
    data = {
        "id": str(item.id),
        "documentoId": str(item.document_id),
        "numero": item.version_number,
        "versao": item.version_label,
        "statusIngestao": item.ingestion_status.value,
        "estadoPublicacao": item.publication_status.value,
        "vigenteDesde": item.valid_from.isoformat() if item.valid_from else None,
        "vigenteAte": item.valid_until.isoformat() if item.valid_until else None,
        "urlFonte": item.source_url,
        "arquivo": item.original_name,
        "mimeType": item.mime_type,
        "tamanhoBytes": item.size_bytes,
        "checksum": item.checksum,
        "modeloEmbedding": item.embedding_model,
        "paginas": item.page_count,
        "fragmentos": item.chunk_count,
        "erro": item.error,
        "segurancaConteudo": content_security_state(item),
        "verificacaoMalware": malware_scan_state(item),
        "criadaEm": item.created_at.isoformat(),
        "indexadaEm": item.indexed_at.isoformat() if item.indexed_at else None,
        "publicadaEm": item.published_at.isoformat() if item.published_at else None,
    }
    if include_download:
        data["downloadUrl"] = (
            f"/api/v1/platform/rag-global/colecoes/{item.document.collection_id}"
            f"/documentos/{item.document_id}/versoes/{item.id}/download"
            f"?token={signed_global_rag_download_token(item.document_id, item.id)}"
        )
    return data


def _collection_values(payload: dict) -> dict:
    name = str(payload.get("nome", "")).strip()
    description = str(payload.get("descricao", "")).strip() or None
    if not name or len(name) > 180:
        raise ValueError("Informe um nome válido para a coleção.")
    if description and len(description) > 5000:
        raise ValueError("Descrição deve ter no máximo 5000 caracteres.")
    try:
        policy = GlobalDistributionPolicy(str(payload.get("politicaDistribuicao", "")).upper())
    except ValueError as error:
        raise ValueError("Política de distribuição inválida.") from error
    jurisdiction = payload.get("jurisdicao") or {}
    if not isinstance(jurisdiction, dict):
        raise ValueError("Jurisdição deve ser um objeto.")
    return {
        "name": name,
        "description": description,
        "distribution_policy": policy,
        "jurisdiction": jurisdiction,
    }


def _document_values(payload: dict) -> dict:
    title = str(payload.get("titulo", "")).strip()
    document_type = str(payload.get("tipo", "")).strip().upper()
    agency = str(payload.get("orgao", "")).strip() or None
    provenance = str(payload.get("proveniencia", "")).strip()
    jurisdiction = payload.get("jurisdicao") or {}
    if not title or len(title) > 240:
        raise ValueError("Informe um título válido.")
    if not document_type or len(document_type) > 80:
        raise ValueError("Informe um tipo documental válido.")
    if agency and len(agency) > 180:
        raise ValueError("Órgão inválido.")
    if not provenance or len(provenance) > 5000:
        raise ValueError("Informe uma proveniência válida.")
    if not isinstance(jurisdiction, dict):
        raise ValueError("Jurisdição deve ser um objeto.")
    confidence = payload.get("nivelConfianca")
    if confidence is not None:
        try:
            confidence = float(confidence)
        except (TypeError, ValueError) as error:
            raise ValueError("Nível de confiança inválido.") from error
        if confidence < 0 or confidence > 1:
            raise ValueError("Nível de confiança deve estar entre 0 e 1.")
    return {
        "title": title,
        "document_type": document_type,
        "agency": agency,
        "jurisdiction": jurisdiction,
        "provenance": provenance,
        "confidence_level": confidence,
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


def _document(collection_id: uuid.UUID, document_id: uuid.UUID) -> GlobalKnowledgeDocument | None:
    return db.session.execute(
        select(GlobalKnowledgeDocument).where(
            GlobalKnowledgeDocument.id == document_id,
            GlobalKnowledgeDocument.collection_id == collection_id,
        )
    ).scalar_one_or_none()


def _version(
    collection_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
) -> GlobalKnowledgeDocumentVersion | None:
    return db.session.execute(
        select(GlobalKnowledgeDocumentVersion)
        .join(GlobalKnowledgeDocument)
        .where(
            GlobalKnowledgeDocumentVersion.id == version_id,
            GlobalKnowledgeDocumentVersion.document_id == document_id,
            GlobalKnowledgeDocument.collection_id == collection_id,
        )
    ).scalar_one_or_none()
