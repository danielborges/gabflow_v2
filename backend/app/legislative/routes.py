import difflib
import json
import re
import uuid
from datetime import UTC, date, datetime, timedelta

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.audit import add_audit
from app.auth.permissions import is_chief_of_staff, roles_or_chief_required, roles_required
from app.extensions import db
from app.legislative.exports import draft_docx, draft_pdf
from app.legislative.foundation import (
    foundation_retriever,
    normative_source_data,
    normative_source_values,
)
from app.legislative.precedents import semantic_precedent_search
from app.legislative.service import enqueue_generation, save_version
from app.models import (
    AIExecution,
    LegislativeDocumentType,
    LegislativeDraft,
    LegislativeDraftRequest,
    LegislativeDraftStatus,
    LegislativeDraftVersion,
    LegislativeGenerationStatus,
    LegislativeTemplate,
    LegislativeTramitation,
    LegislativeTramitationStatus,
    NormativeSource,
    RequestHistory,
    ServiceRequest,
    User,
)

legislative_bp = Blueprint("legislative", __name__)


def _context() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(get_jwt()["tenant_id"]), uuid.UUID(get_jwt_identity())


@legislative_bp.get("/legislativo/minutas")
@jwt_required()
def list_drafts():
    tenant_id, _ = _context()
    statement = select(LegislativeDraft).where(LegislativeDraft.tenant_id == tenant_id)
    status = str(request.args.get("status", "")).upper()
    document_type = str(request.args.get("tipo", "")).upper()
    search = str(request.args.get("q", "")).strip()
    if status:
        try:
            statement = statement.where(LegislativeDraft.status == LegislativeDraftStatus(status))
        except ValueError:
            return jsonify(error="validation_error", message="Status de minuta inválido."), 422
    if document_type:
        try:
            statement = statement.where(
                LegislativeDraft.document_type == LegislativeDocumentType(document_type)
            )
        except ValueError:
            return jsonify(error="validation_error", message="Tipo de documento inválido."), 422
    if search:
        statement = statement.where(
            or_(
                LegislativeDraft.title.ilike(f"%{search[:100]}%"),
                LegislativeDraft.content.ilike(f"%{search[:100]}%"),
                LegislativeDraft.protocol_number.ilike(f"%{search[:100]}%"),
            )
        )
    items = (
        db.session.execute(statement.order_by(LegislativeDraft.updated_at.desc()).limit(200))
        .scalars()
        .all()
    )
    return jsonify(content=[draft_data(item, include_detail=False) for item in items])


@legislative_bp.get("/legislativo/minutas/<uuid:draft_id>")
@jwt_required()
def get_draft(draft_id: uuid.UUID):
    tenant_id, _ = _context()
    draft = _draft(tenant_id, draft_id)
    if draft is None:
        return jsonify(error="resource_not_found", message="Minuta não encontrada."), 404
    return jsonify(draft_data(draft, include_detail=True))


@legislative_bp.get("/legislativo/minutas/<uuid:draft_id>/versoes")
@jwt_required()
def list_draft_versions(draft_id: uuid.UUID):
    tenant_id, _ = _context()
    draft = _draft(tenant_id, draft_id)
    if draft is None:
        return jsonify(error="resource_not_found", message="Minuta não encontrada."), 404
    versions = _versions(draft)
    authors = _version_authors(versions)
    return jsonify(
        content=[
            version_data(item, authors.get(item.created_by_id), include_content=False)
            for item in versions
        ]
    )


@legislative_bp.get("/legislativo/minutas/<uuid:draft_id>/versoes/<int:version_number>")
@jwt_required()
def get_draft_version(draft_id: uuid.UUID, version_number: int):
    tenant_id, _ = _context()
    draft = _draft(tenant_id, draft_id)
    if draft is None:
        return jsonify(error="resource_not_found", message="Minuta não encontrada."), 404
    version = _version(draft, version_number)
    if version is None:
        return jsonify(error="resource_not_found", message="Versão não encontrada."), 404
    author = db.session.get(User, version.created_by_id)
    return jsonify(version_data(version, author.name if author else None, include_content=True))


@legislative_bp.get("/legislativo/minutas/<uuid:draft_id>/comparacao")
@jwt_required()
def compare_draft_versions(draft_id: uuid.UUID):
    tenant_id, _ = _context()
    draft = _draft(tenant_id, draft_id)
    if draft is None:
        return jsonify(error="resource_not_found", message="Minuta não encontrada."), 404
    try:
        from_number = int(request.args.get("de", ""))
        to_number = int(request.args.get("para", ""))
    except (TypeError, ValueError):
        return jsonify(
            error="validation_error", message="Informe duas versões válidas para comparação."
        ), 422
    if from_number == to_number:
        return jsonify(
            error="validation_error", message="Selecione versões diferentes para comparação."
        ), 422
    versions = {
        item.version_number: item
        for item in db.session.execute(
            select(LegislativeDraftVersion).where(
                LegislativeDraftVersion.draft_id == draft.id,
                LegislativeDraftVersion.tenant_id == draft.tenant_id,
                LegislativeDraftVersion.version_number.in_([from_number, to_number]),
            )
        )
        .scalars()
        .all()
    }
    if len(versions) != 2:
        return jsonify(error="resource_not_found", message="Versão não encontrada."), 404
    return jsonify(version_comparison(versions[from_number], versions[to_number]))


@legislative_bp.post(
    "/legislativo/minutas/<uuid:draft_id>/versoes/<int:version_number>/restaurar"
)
@jwt_required()
def restore_draft_version(draft_id: uuid.UUID, version_number: int):
    tenant_id, user_id = _context()
    draft = _draft(tenant_id, draft_id)
    if draft is None:
        return jsonify(error="resource_not_found", message="Minuta não encontrada."), 404
    if draft.generation_status != LegislativeGenerationStatus.CONCLUIDA:
        return jsonify(error="conflict", message="A minuta ainda não está disponível."), 409
    if draft.status not in {LegislativeDraftStatus.RASCUNHO, LegislativeDraftStatus.EM_REVISAO}:
        return jsonify(error="conflict", message="A minuta não pode mais ser alterada."), 409
    version = _version(draft, version_number)
    if version is None:
        return jsonify(error="resource_not_found", message="Versão não encontrada."), 404
    if version.version_number == draft.current_version:
        return jsonify(error="conflict", message="A versão selecionada já é a atual."), 409
    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("motivo", "")).strip()
    if not reason:
        return jsonify(
            error="validation_error", message="Informe o motivo da restauração."
        ), 422

    before = {
        "versao": draft.current_version,
        "titulo": draft.title,
        "status": draft.status.value,
    }
    draft.title = version.title
    draft.content = version.content
    draft.justification = version.justification
    draft.legal_basis = list(version.legal_basis or [])
    draft.unsupported_passages = list(version.unsupported_passages or [])
    save_version(
        draft,
        user_id,
        f"Restauração da versão {version.version_number}: {reason}"[:500],
    )
    draft.reviewed_by_id = user_id
    draft.reviewed_at = datetime.now(UTC)
    add_audit(
        tenant_id,
        user_id,
        "legislative_draft.version_restored",
        "legislative_draft",
        draft.id,
        before=before,
        after={
            "versaoOrigem": version.version_number,
            "novaVersao": draft.current_version,
            "motivo": reason[:500],
            "status": draft.status.value,
        },
    )
    db.session.commit()
    return jsonify(draft_data(draft, include_detail=True))


@legislative_bp.post("/solicitacoes/<uuid:request_id>/gerar-minuta")
@jwt_required()
def generate_draft(request_id: uuid.UUID):
    tenant_id, user_id = _context()
    primary = _request(tenant_id, request_id)
    if primary is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    try:
        document_type = LegislativeDocumentType(str(payload.get("tipo", "")).upper())
    except ValueError:
        return jsonify(error="validation_error", message="Tipo de documento inválido."), 422

    related_request_ids = payload.get("solicitacoesRelacionadasIds") or []
    if not isinstance(related_request_ids, list):
        return jsonify(
            error="validation_error",
            message="As solicitações relacionadas devem ser enviadas em uma lista.",
        ), 422
    if len(related_request_ids) > 19:
        return jsonify(
            error="validation_error",
            message="Uma minuta pode possuir no máximo 20 solicitações vinculadas.",
        ), 422
    request_ids = [request_id]
    for raw_id in related_request_ids:
        try:
            candidate_id = uuid.UUID(str(raw_id))
        except (TypeError, ValueError):
            return jsonify(
                error="validation_error", message="Solicitação relacionada inválida."
            ), 422
        if candidate_id in request_ids:
            return jsonify(
                error="validation_error",
                message="Uma solicitação não pode ser vinculada mais de uma vez.",
            ), 422
        request_ids.append(candidate_id)
    requests = (
        db.session.execute(
            select(ServiceRequest).where(
                ServiceRequest.tenant_id == tenant_id,
                ServiceRequest.id.in_(request_ids),
            )
        )
        .scalars()
        .all()
    )
    if len(requests) != len(request_ids):
        return jsonify(
            error="validation_error", message="Uma solicitação relacionada não existe."
        ), 422
    requests_by_id = {item.id: item for item in requests}
    ordered_requests = [requests_by_id[item_id] for item_id in request_ids]

    template = None
    if payload.get("templateId"):
        try:
            template_id = uuid.UUID(str(payload["templateId"]))
        except ValueError:
            return jsonify(error="validation_error", message="Template inválido."), 422
        template = db.session.execute(
            select(LegislativeTemplate).where(
                LegislativeTemplate.id == template_id,
                LegislativeTemplate.tenant_id == tenant_id,
                LegislativeTemplate.active.is_(True),
                LegislativeTemplate.document_type == document_type,
            )
        ).scalar_one_or_none()
        if template is None:
            return jsonify(error="validation_error", message="Template não está disponível."), 422

    facts = [
        str(item).strip()[:1000]
        for item in payload.get("fatosSelecionados") or []
        if str(item).strip()
    ]
    sources = payload.get("fontesNormativas") or []
    if not isinstance(sources, list) or not all(isinstance(item, dict) for item in sources):
        return jsonify(error="validation_error", message="Fontes normativas inválidas."), 422
    default_title = (
        f"{document_type.value.replace('_', ' ').title()} - {primary.title or primary.protocol}"
    )
    draft = LegislativeDraft(
        tenant_id=tenant_id,
        document_type=document_type,
        title=str(payload.get("titulo") or default_title)[:240],
        template_id=template.id if template else None,
        created_by_id=user_id,
    )
    db.session.add(draft)
    db.session.flush()
    for item in ordered_requests:
        db.session.add(
            LegislativeDraftRequest(tenant_id=tenant_id, draft_id=draft.id, request_id=item.id)
        )
    parameters = {
        "minutaId": str(draft.id),
        "tipo": document_type.value,
        "fatosSelecionados": facts,
        "instrucoes": str(payload.get("instrucoes") or "").strip()[:4000],
        "fontesNormativas": sources[:20],
        "templateId": str(template.id) if template else None,
        "solicitacaoPrincipalId": str(request_id),
        "solicitacoesIds": [str(item.id) for item in ordered_requests],
    }
    execution = enqueue_generation(draft, primary, user_id, parameters)
    details = {
        "minutaId": str(draft.id),
        "execucaoId": str(execution.id),
        "tipo": document_type.value,
        "solicitacaoPrincipalId": str(request_id),
        "solicitacoesIds": [str(item.id) for item in ordered_requests],
        "rascunho": True,
        "protocoloAutomatico": False,
    }
    for item in ordered_requests:
        db.session.add(
            RequestHistory(
                tenant_id=tenant_id,
                request_id=item.id,
                user_id=user_id,
                action="request.legislative_draft.requested",
                changes=details,
            )
        )
    add_audit(
        tenant_id,
        user_id,
        "legislative_draft.requested",
        "legislative_draft",
        draft.id,
        after=details,
    )
    db.session.commit()
    return jsonify(draft_data(draft, include_detail=True)), 202


@legislative_bp.post("/legislativo/minutas/<uuid:draft_id>/revisao")
@jwt_required()
def review_draft(draft_id: uuid.UUID):
    tenant_id, user_id = _context()
    draft = _draft(tenant_id, draft_id)
    if draft is None:
        return jsonify(error="resource_not_found", message="Minuta não encontrada."), 404
    if draft.generation_status != LegislativeGenerationStatus.CONCLUIDA:
        return jsonify(
            error="conflict", message="A geração da minuta ainda não foi concluída."
        ), 409
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("acao", "SALVAR")).upper()
    if action not in {"SALVAR", "SUBMETER", "APROVAR", "REJEITAR"}:
        return jsonify(error="validation_error", message="Ação de revisão inválida."), 422
    before = {"status": draft.status.value, "versao": draft.current_version}

    if action in {"SALVAR", "SUBMETER"}:
        if draft.status not in {LegislativeDraftStatus.RASCUNHO, LegislativeDraftStatus.EM_REVISAO}:
            return jsonify(error="conflict", message="A minuta não pode mais ser editada."), 409
        title = str(payload.get("titulo", draft.title)).strip()
        content = str(payload.get("conteudo", draft.content or "")).strip()
        if not title or not content:
            return jsonify(
                error="validation_error", message="Título e conteúdo são obrigatórios."
            ), 422
        draft.title = title[:240]
        draft.content = content[:30000]
        draft.justification = (
            str(payload.get("justificativa", draft.justification or "")).strip()[:10000] or None
        )
        if "fundamentacaoNormativa" in payload:
            basis = payload["fundamentacaoNormativa"]
            if not isinstance(basis, list) or not all(isinstance(item, dict) for item in basis):
                return jsonify(
                    error="validation_error", message="Fundamentação normativa inválida."
                ), 422
            draft.legal_basis = basis[:20]
        if payload.get("confirmarFundamentacao") is True:
            draft.unsupported_passages = []
        save_version(draft, user_id, str(payload.get("motivo") or "Revisão humana da minuta"))
        draft.reviewed_by_id = user_id
        draft.reviewed_at = datetime.now(UTC)
        if action == "SUBMETER":
            draft.status = LegislativeDraftStatus.EM_REVISAO

    elif action == "APROVAR":
        if get_jwt().get("role") not in {"admin", "manager", "representative"}:
            return jsonify(error="forbidden", message="A aprovação exige perfil gestor."), 403
        if draft.status != LegislativeDraftStatus.EM_REVISAO:
            return jsonify(
                error="conflict", message="Submeta a minuta para revisão antes de aprovar."
            ), 409
        if draft.unsupported_passages and payload.get("confirmarFundamentacao") is not True:
            return jsonify(
                error="foundation_confirmation_required",
                message="Confirme ou corrija os trechos sem fundamentação antes de aprovar.",
            ), 409
        draft.status = LegislativeDraftStatus.APROVADA
        draft.approved_by_id = user_id
        draft.approved_at = datetime.now(UTC)
    else:
        if get_jwt().get("role") not in {"admin", "manager"} and not is_chief_of_staff():
            return jsonify(error="forbidden", message="A rejeição exige perfil gestor."), 403
        reason = str(payload.get("motivo", "")).strip()
        if not reason:
            return jsonify(error="validation_error", message="Informe o motivo da rejeição."), 422
        draft.status = LegislativeDraftStatus.REJEITADA
        draft.reviewed_by_id = user_id
        draft.reviewed_at = datetime.now(UTC)

    details = {
        "acao": action,
        "status": draft.status.value,
        "versao": draft.current_version,
        "protocoloAutomatico": False,
    }
    add_audit(
        tenant_id,
        user_id,
        f"legislative_draft.{action.lower()}",
        "legislative_draft",
        draft.id,
        before=before,
        after=details,
    )
    db.session.commit()
    return jsonify(draft_data(draft, include_detail=True))


@legislative_bp.post("/legislativo/minutas/<uuid:draft_id>/protocolo")
@roles_or_chief_required("admin", "manager")
def register_protocol(draft_id: uuid.UUID):
    tenant_id, user_id = _context()
    draft = _draft(tenant_id, draft_id)
    if draft is None:
        return jsonify(error="resource_not_found", message="Minuta não encontrada."), 404
    if draft.status != LegislativeDraftStatus.APROVADA:
        return jsonify(
            error="conflict", message="Somente minutas aprovadas podem ser protocoladas."
        ), 409
    if draft.protocol_number:
        return jsonify(error="conflict", message="A minuta já possui protocolo."), 409
    payload = request.get_json(silent=True) or {}
    protocol = str(payload.get("protocolo", "")).strip()
    if not protocol or len(protocol) > 100:
        return jsonify(error="validation_error", message="Informe um protocolo válido."), 422
    draft.protocol_number = protocol
    draft.protocolled_at = datetime.now(UTC)
    draft.current_tramitation_status = LegislativeTramitationStatus.PROTOCOLADA
    db.session.add(
        LegislativeTramitation(
            tenant_id=tenant_id,
            draft_id=draft.id,
            status=LegislativeTramitationStatus.PROTOCOLADA,
            stage="Protocolo",
            destination=str(payload.get("destino") or "").strip()[:180] or None,
            external_reference=protocol,
            notes=str(payload.get("observacoes") or "").strip()[:4000] or None,
            occurred_at=draft.protocolled_at,
            created_by_id=user_id,
        )
    )
    add_audit(
        tenant_id,
        user_id,
        "legislative_draft.protocol_registered",
        "legislative_draft",
        draft.id,
        after={
            "protocolo": protocol,
            "registroAutomatico": False,
            "statusTramitacao": LegislativeTramitationStatus.PROTOCOLADA.value,
        },
    )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="conflict", message="Este protocolo já está registrado."), 409
    return jsonify(draft_data(draft, include_detail=True))


@legislative_bp.get("/legislativo/minutas/<uuid:draft_id>/tramitacoes")
@jwt_required()
def list_tramitations(draft_id: uuid.UUID):
    tenant_id, _ = _context()
    draft = _draft(tenant_id, draft_id)
    if draft is None:
        return jsonify(error="resource_not_found", message="Minuta não encontrada."), 404
    return jsonify(content=_tramitations(draft))


@legislative_bp.post("/legislativo/minutas/<uuid:draft_id>/tramitacoes")
@roles_or_chief_required("admin", "manager")
def add_tramitation(draft_id: uuid.UUID):
    tenant_id, user_id = _context()
    draft = _draft(tenant_id, draft_id)
    if draft is None:
        return jsonify(error="resource_not_found", message="Minuta não encontrada."), 404
    if draft.status != LegislativeDraftStatus.APROVADA or not draft.protocol_number:
        return jsonify(
            error="conflict",
            message="A tramitação exige uma minuta aprovada e protocolada.",
        ), 409

    payload = request.get_json(silent=True) or {}
    try:
        status = LegislativeTramitationStatus(str(payload.get("status", "")).upper())
    except ValueError:
        return jsonify(error="validation_error", message="Status de tramitação inválido."), 422
    if status == LegislativeTramitationStatus.PROTOCOLADA:
        return jsonify(
            error="validation_error",
            message="O protocolo inicial já foi registrado e não pode ser repetido.",
        ), 422

    stage = str(payload.get("etapa", "")).strip()
    if not stage or len(stage) > 160:
        return jsonify(error="validation_error", message="Informe uma etapa válida."), 422
    try:
        occurred_at = _parse_occurred_at(payload.get("ocorridaEm"))
    except ValueError:
        return jsonify(
            error="validation_error",
            message="Informe uma data de ocorrência válida.",
        ), 422
    protocolled_at = _as_utc(draft.protocolled_at)
    latest_occurred_at = db.session.execute(
        select(LegislativeTramitation.occurred_at)
        .where(
            LegislativeTramitation.draft_id == draft.id,
            LegislativeTramitation.tenant_id == tenant_id,
        )
        .order_by(LegislativeTramitation.occurred_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    latest_occurred_at = _as_utc(latest_occurred_at) if latest_occurred_at else protocolled_at
    if occurred_at < protocolled_at:
        return jsonify(
            error="validation_error",
            message="A ocorrência não pode ser anterior ao protocolo.",
        ), 422
    if occurred_at < latest_occurred_at:
        return jsonify(
            error="validation_error",
            message="A ocorrência não pode ser anterior ao último andamento.",
        ), 422
    if occurred_at > datetime.now(UTC) + timedelta(minutes=5):
        return jsonify(
            error="validation_error",
            message="A ocorrência não pode estar no futuro.",
        ), 422

    item = LegislativeTramitation(
        tenant_id=tenant_id,
        draft_id=draft.id,
        status=status,
        stage=stage,
        destination=str(payload.get("destino") or "").strip()[:180] or None,
        external_reference=(
            str(payload.get("referenciaExterna") or "").strip()[:180] or None
        ),
        notes=str(payload.get("observacoes") or "").strip()[:4000] or None,
        occurred_at=occurred_at,
        created_by_id=user_id,
    )
    draft.current_tramitation_status = status
    db.session.add(item)
    db.session.flush()
    add_audit(
        tenant_id,
        user_id,
        "legislative_draft.tramitation_added",
        "legislative_draft",
        draft.id,
        after=tramitation_data(item),
    )
    db.session.commit()
    return jsonify(draft_data(draft, include_detail=True)), 201


@legislative_bp.get("/legislativo/precedentes")
@jwt_required()
def precedents():
    tenant_id, _ = _context()
    query = str(request.args.get("q", "")).strip()
    if len(query) < 3:
        return jsonify(error="validation_error", message="Informe ao menos três caracteres."), 422
    try:
        document_type = (
            LegislativeDocumentType(str(request.args["tipo"]).upper())
            if request.args.get("tipo")
            else None
        )
        status = (
            LegislativeDraftStatus(str(request.args["status"]).upper())
            if request.args.get("status")
            else None
        )
        exclude_id = (
            uuid.UUID(str(request.args["excluirMinutaId"]))
            if request.args.get("excluirMinutaId")
            else None
        )
        limit = min(max(int(request.args.get("limite", "10")), 1), 20)
    except (TypeError, ValueError):
        return jsonify(error="validation_error", message="Filtros de precedentes inválidos."), 422
    return jsonify(
        semantic_precedent_search(
            tenant_id,
            query,
            document_type=document_type,
            status=status,
            exclude_id=exclude_id,
            limit=limit,
        )
    )


@legislative_bp.get("/legislativo/fontes-normativas")
@jwt_required()
def list_normative_sources():
    tenant_id, _ = _context()
    include_inactive = str(request.args.get("incluirInativas", "")).lower() == "true"
    if include_inactive and get_jwt().get("role") not in {"admin", "manager"}:
        return jsonify(error="forbidden", message="A gestão da base exige perfil gestor."), 403
    statement = select(NormativeSource).where(NormativeSource.tenant_id == tenant_id)
    if not include_inactive:
        statement = statement.where(NormativeSource.active.is_(True))
    search = str(request.args.get("q", "")).strip()
    if search:
        statement = statement.where(
            or_(
                NormativeSource.title.ilike(f"%{search[:100]}%"),
                NormativeSource.reference.ilike(f"%{search[:100]}%"),
                NormativeSource.excerpt.ilike(f"%{search[:100]}%"),
            )
        )
    items = db.session.execute(
        statement.order_by(NormativeSource.updated_at.desc()).limit(300)
    ).scalars()
    return jsonify(content=[normative_source_data(item) for item in items])


@legislative_bp.post("/legislativo/fontes-normativas")
@roles_required("admin", "manager")
def create_normative_source():
    tenant_id, user_id = _context()
    try:
        values = normative_source_values(request.get_json(silent=True) or {})
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    item = NormativeSource(tenant_id=tenant_id, created_by_id=user_id, **values)
    db.session.add(item)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify(
            error="conflict", message="Esta versão da fonte normativa já está cadastrada."
        ), 409
    data = normative_source_data(item)
    add_audit(
        tenant_id,
        user_id,
        "normative_source.created",
        "normative_source",
        item.id,
        after=data,
    )
    db.session.commit()
    return jsonify(data), 201


@legislative_bp.put("/legislativo/fontes-normativas/<uuid:source_id>")
@roles_required("admin", "manager")
def update_normative_source(source_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = _normative_source(tenant_id, source_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Fonte normativa não encontrada."), 404
    try:
        values = normative_source_values(request.get_json(silent=True) or {})
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    before = normative_source_data(item)
    for field, value in values.items():
        setattr(item, field, value)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify(
            error="conflict", message="Esta versão da fonte normativa já está cadastrada."
        ), 409
    after = normative_source_data(item)
    add_audit(
        tenant_id,
        user_id,
        "normative_source.updated",
        "normative_source",
        item.id,
        before=before,
        after=after,
    )
    db.session.commit()
    return jsonify(after)


@legislative_bp.patch("/legislativo/fontes-normativas/<uuid:source_id>/status")
@roles_required("admin", "manager")
def change_normative_source_status(source_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = _normative_source(tenant_id, source_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Fonte normativa não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload.get("ativo"), bool):
        return jsonify(error="validation_error", message="Status inválido."), 422
    before = {"ativo": item.active}
    item.active = payload["ativo"]
    add_audit(
        tenant_id,
        user_id,
        "normative_source.activated" if item.active else "normative_source.deactivated",
        "normative_source",
        item.id,
        before=before,
        after={"ativo": item.active},
    )
    db.session.commit()
    return jsonify(normative_source_data(item))


@legislative_bp.post("/legislativo/minutas/<uuid:draft_id>/fundamentacao/recuperar")
@jwt_required()
def retrieve_draft_foundation(draft_id: uuid.UUID):
    tenant_id, user_id = _context()
    draft = _draft(tenant_id, draft_id)
    if draft is None:
        return jsonify(error="resource_not_found", message="Minuta não encontrada."), 404
    if draft.generation_status != LegislativeGenerationStatus.CONCLUIDA:
        return jsonify(error="conflict", message="A minuta ainda não está disponível."), 409
    payload = request.get_json(silent=True) or {}
    query = str(payload.get("consulta") or _foundation_query(draft)).strip()
    if len(query) < 3:
        return jsonify(error="validation_error", message="Consulta normativa inválida."), 422
    recovery = foundation_retriever().retrieve(
        tenant_id, query[:30000], current_app.config["AI_FOUNDATION_MAX_RESULTS"]
    )
    draft.generation_metadata = {
        **(draft.generation_metadata or {}),
        "recuperacaoFundamentacao": recovery,
    }
    add_audit(
        tenant_id,
        user_id,
        "legislative_draft.foundation_retrieved",
        "legislative_draft",
        draft.id,
        after={
            "modelo": recovery["modelo"],
            "fallbackUtilizado": recovery["fallbackUtilizado"],
            "fonteIds": [item["id"] for item in recovery["fontes"]],
            "aplicacaoAutomatica": False,
        },
    )
    db.session.commit()
    return jsonify(recovery)


@legislative_bp.post("/legislativo/minutas/<uuid:draft_id>/fundamentacao/aplicar")
@jwt_required()
def apply_draft_foundation(draft_id: uuid.UUID):
    tenant_id, user_id = _context()
    draft = _draft(tenant_id, draft_id)
    if draft is None:
        return jsonify(error="resource_not_found", message="Minuta não encontrada."), 404
    if draft.status not in {LegislativeDraftStatus.RASCUNHO, LegislativeDraftStatus.EM_REVISAO}:
        return jsonify(error="conflict", message="A minuta não pode mais ser alterada."), 409
    payload = request.get_json(silent=True) or {}
    raw_ids = payload.get("fonteIds")
    reason = str(payload.get("motivo", "")).strip()
    if not isinstance(raw_ids, list) or not raw_ids or len(raw_ids) > 10 or not reason:
        return jsonify(
            error="validation_error",
            message="Selecione as fontes e informe o motivo da fundamentação.",
        ), 422
    try:
        source_ids = [uuid.UUID(str(value)) for value in raw_ids]
    except (TypeError, ValueError):
        return jsonify(error="validation_error", message="Fonte normativa inválida."), 422
    if len(set(source_ids)) != len(source_ids):
        return jsonify(error="validation_error", message="Fonte normativa repetida."), 422
    recovery = (draft.generation_metadata or {}).get("recuperacaoFundamentacao") or {}
    suggested_ids = {str(item.get("id")) for item in recovery.get("fontes") or []}
    if not all(str(source_id) in suggested_ids for source_id in source_ids):
        return jsonify(
            error="validation_error",
            message="Aplique somente fontes recuperadas para esta minuta.",
        ), 422
    today = date.today()
    sources = list(
        db.session.execute(
            select(NormativeSource).where(
                NormativeSource.tenant_id == tenant_id,
                NormativeSource.id.in_(source_ids),
                NormativeSource.active.is_(True),
                or_(NormativeSource.valid_from.is_(None), NormativeSource.valid_from <= today),
                or_(NormativeSource.valid_until.is_(None), NormativeSource.valid_until >= today),
            )
        ).scalars()
    )
    if len(sources) != len(source_ids):
        return jsonify(error="validation_error", message="Fonte normativa indisponível."), 422
    sources_by_id = {item.id: item for item in sources}
    ordered_sources = [sources_by_id[source_id] for source_id in source_ids]
    selected_basis = [_foundation_citation(item) for item in ordered_sources]
    selected_ids = {str(value) for value in source_ids}
    existing_basis = [
        item
        for item in (draft.legal_basis or [])
        if str(item.get("sourceId") or "") not in selected_ids
    ]
    existing_sources = [
        item
        for item in (draft.sources or [])
        if str(item.get("sourceId") or "") not in selected_ids
    ]
    draft.legal_basis = [*existing_basis, *selected_basis][:20]
    draft.sources = [*existing_sources, *selected_basis][:20]
    draft.unsupported_passages = [
        item
        for item in (draft.unsupported_passages or [])
        if item.get("trecho") != "Fundamentação normativa"
    ]
    save_version(draft, user_id, f"Fundamentação recuperada: {reason}"[:500])
    draft.reviewed_by_id = user_id
    draft.reviewed_at = datetime.now(UTC)
    add_audit(
        tenant_id,
        user_id,
        "legislative_draft.foundation_applied",
        "legislative_draft",
        draft.id,
        after={
            "fonteIds": [str(item.id) for item in ordered_sources],
            "novaVersao": draft.current_version,
            "motivo": reason[:500],
            "confirmacaoHumana": True,
        },
    )
    db.session.commit()
    return jsonify(draft_data(draft, include_detail=True))


@legislative_bp.get("/legislativo/templates")
@jwt_required()
def list_templates():
    tenant_id, _ = _context()
    include_inactive = str(request.args.get("incluirInativos", "")).lower() == "true"
    if include_inactive and get_jwt().get("role") not in {"admin", "manager"}:
        return jsonify(error="forbidden", message="A gestão de templates exige perfil gestor."), 403
    statement = select(LegislativeTemplate).where(LegislativeTemplate.tenant_id == tenant_id)
    if not include_inactive:
        statement = statement.where(LegislativeTemplate.active.is_(True))
    items = (
        db.session.execute(
            statement.order_by(
                LegislativeTemplate.document_type,
                LegislativeTemplate.active.desc(),
                LegislativeTemplate.name,
            )
        )
        .scalars()
        .all()
    )
    return jsonify(content=[template_data(item) for item in items])


@legislative_bp.post("/legislativo/templates")
@roles_required("admin", "manager")
def create_template():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    try:
        document_type, name, structure = _template_fields(payload)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    if _template_name_exists(tenant_id, name):
        return jsonify(error="conflict", message="Já existe um template com esse nome."), 409
    item = LegislativeTemplate(
        tenant_id=tenant_id,
        document_type=document_type,
        name=name,
        structure=structure,
        created_by_id=user_id,
    )
    db.session.add(item)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="conflict", message="Já existe um template com esse nome."), 409
    add_audit(
        tenant_id,
        user_id,
        "legislative_template.created",
        "legislative_template",
        item.id,
        after=template_data(item),
    )
    db.session.commit()
    return jsonify(template_data(item)), 201


@legislative_bp.put("/legislativo/templates/<uuid:template_id>")
@roles_required("admin", "manager")
def update_template(template_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = _template(tenant_id, template_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Template não encontrado."), 404
    payload = request.get_json(silent=True) or {}
    try:
        document_type, name, structure = _template_fields(payload)
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422
    if _template_name_exists(tenant_id, name, excluding_id=item.id):
        return jsonify(error="conflict", message="Já existe um template com esse nome."), 409
    before = template_data(item)
    item.document_type = document_type
    item.name = name
    item.structure = structure
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="conflict", message="Já existe um template com esse nome."), 409
    add_audit(
        tenant_id,
        user_id,
        "legislative_template.updated",
        "legislative_template",
        item.id,
        before=before,
        after=template_data(item),
    )
    db.session.commit()
    return jsonify(template_data(item))


@legislative_bp.patch("/legislativo/templates/<uuid:template_id>/status")
@roles_required("admin", "manager")
def change_template_status(template_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = _template(tenant_id, template_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Template não encontrado."), 404
    active = (request.get_json(silent=True) or {}).get("ativo")
    if not isinstance(active, bool):
        return jsonify(error="validation_error", message="Informe um status válido."), 422
    before = template_data(item)
    item.active = active
    db.session.flush()
    add_audit(
        tenant_id,
        user_id,
        "legislative_template.activated" if active else "legislative_template.deactivated",
        "legislative_template",
        item.id,
        before=before,
        after=template_data(item),
    )
    db.session.commit()
    return jsonify(template_data(item))


@legislative_bp.get("/legislativo/minutas/<uuid:draft_id>/exportar/<format_name>")
@jwt_required()
def export_draft(draft_id: uuid.UUID, format_name: str):
    tenant_id, _ = _context()
    draft = _draft(tenant_id, draft_id)
    if draft is None:
        return jsonify(error="resource_not_found", message="Minuta não encontrada."), 404
    if draft.generation_status != LegislativeGenerationStatus.CONCLUIDA:
        return jsonify(error="conflict", message="A minuta ainda não está disponível."), 409
    safe_title = re.sub(r"[^a-zA-Z0-9_-]+", "-", draft.title).strip("-")[:80] or "minuta"
    if format_name == "docx":
        return send_file(
            draft_docx(draft),
            as_attachment=True,
            download_name=f"{safe_title}.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    if format_name == "pdf":
        return send_file(
            draft_pdf(draft),
            as_attachment=True,
            download_name=f"{safe_title}.pdf",
            mimetype="application/pdf",
        )
    return jsonify(error="validation_error", message="Formato de exportação inválido."), 422


def draft_data(draft: LegislativeDraft, include_detail: bool) -> dict:
    data = {
        "id": str(draft.id),
        "tipo": draft.document_type.value,
        "status": draft.status.value,
        "statusGeracao": draft.generation_status.value,
        "titulo": draft.title,
        "versaoAtual": draft.current_version,
        "protocolo": draft.protocol_number,
        "protocoladaEm": draft.protocolled_at.isoformat() if draft.protocolled_at else None,
        "statusTramitacao": (
            draft.current_tramitation_status.value
            if draft.current_tramitation_status
            else None
        ),
        "criadaEm": draft.created_at.isoformat(),
        "atualizadaEm": draft.updated_at.isoformat(),
        "erro": draft.error,
        "protocoloAutomatico": False,
    }
    if not include_detail:
        return data
    links = (
        db.session.execute(
            select(LegislativeDraftRequest).where(
                LegislativeDraftRequest.draft_id == draft.id,
                LegislativeDraftRequest.tenant_id == draft.tenant_id,
            )
        )
        .scalars()
        .all()
    )
    requests = (
        db.session.execute(
            select(ServiceRequest).where(ServiceRequest.id.in_([link.request_id for link in links]))
        )
        .scalars()
        .all()
        if links
        else []
    )
    versions = _versions(draft)
    version_authors = _version_authors(versions)
    execution = (
        db.session.get(AIExecution, draft.ai_execution_id) if draft.ai_execution_id else None
    )
    request_order = list((draft.generation_metadata or {}).get("solicitacoesIds") or [])
    if not request_order and execution:
        request_order = list(
            ((execution.output or {}).get("parametros") or {}).get("solicitacoesIds") or []
        )
    requests_by_id = {str(item.id): item for item in requests}
    ordered_requests = [
        requests_by_id[item_id] for item_id in request_order if item_id in requests_by_id
    ]
    ordered_ids = {item.id for item in ordered_requests}
    ordered_requests.extend(item for item in requests if item.id not in ordered_ids)
    primary_id = request_order[0] if request_order else None
    data.update(
        {
            "conteudo": draft.content,
            "justificativa": draft.justification,
            "fundamentacaoNormativa": draft.legal_basis,
            "fontes": draft.sources,
            "trechosSemFundamentacao": draft.unsupported_passages,
            "proposicoesSemelhantes": draft.similar_proposals,
            "metadadosGeracao": draft.generation_metadata,
            "fundamentacaoSugerida": (draft.generation_metadata or {}).get(
                "recuperacaoFundamentacao"
            ),
            "solicitacoes": [
                {
                    "id": str(item.id),
                    "protocolo": item.protocol,
                    "titulo": item.title,
                    "principal": str(item.id) == primary_id,
                }
                for item in ordered_requests
            ],
            "versoes": [
                version_data(
                    item,
                    version_authors.get(item.created_by_id),
                    include_content=False,
                )
                for item in versions
            ],
            "execucaoIA": str(execution.id) if execution else None,
            "tramitacoes": _tramitations(draft),
        }
    )
    return data


def _versions(draft: LegislativeDraft) -> list[LegislativeDraftVersion]:
    return (
        db.session.execute(
            select(LegislativeDraftVersion)
            .where(
                LegislativeDraftVersion.draft_id == draft.id,
                LegislativeDraftVersion.tenant_id == draft.tenant_id,
            )
            .order_by(LegislativeDraftVersion.version_number.desc())
        )
        .scalars()
        .all()
    )


def _version(draft: LegislativeDraft, version_number: int) -> LegislativeDraftVersion | None:
    if version_number < 1:
        return None
    return db.session.execute(
        select(LegislativeDraftVersion).where(
            LegislativeDraftVersion.draft_id == draft.id,
            LegislativeDraftVersion.tenant_id == draft.tenant_id,
            LegislativeDraftVersion.version_number == version_number,
        )
    ).scalar_one_or_none()


def _version_authors(versions: list[LegislativeDraftVersion]) -> dict[uuid.UUID, str]:
    author_ids = {item.created_by_id for item in versions}
    if not author_ids:
        return {}
    return {
        item.id: item.name
        for item in db.session.execute(select(User).where(User.id.in_(author_ids))).scalars().all()
    }


def version_data(
    item: LegislativeDraftVersion, author_name: str | None, include_content: bool
) -> dict:
    data = {
        "id": str(item.id),
        "numero": item.version_number,
        "motivo": item.change_reason,
        "autor": author_name or "Usuário removido",
        "criadaEm": item.created_at.isoformat(),
    }
    if include_content:
        data.update(
            {
                "titulo": item.title,
                "conteudo": item.content,
                "justificativa": item.justification,
                "fundamentacaoNormativa": item.legal_basis,
                "trechosSemFundamentacao": item.unsupported_passages,
            }
        )
    return data


def version_comparison(
    from_version: LegislativeDraftVersion, to_version: LegislativeDraftVersion
) -> dict:
    values = {
        "titulo": (from_version.title, to_version.title),
        "conteudo": (from_version.content, to_version.content),
        "justificativa": (from_version.justification or "", to_version.justification or ""),
        "fundamentacaoNormativa": (
            json.dumps(from_version.legal_basis or [], ensure_ascii=False, indent=2),
            json.dumps(to_version.legal_basis or [], ensure_ascii=False, indent=2),
        ),
        "trechosSemFundamentacao": (
            json.dumps(from_version.unsupported_passages or [], ensure_ascii=False, indent=2),
            json.dumps(to_version.unsupported_passages or [], ensure_ascii=False, indent=2),
        ),
    }
    fields = {}
    total_added = 0
    total_removed = 0
    for name, (before, after) in values.items():
        changes = []
        added = 0
        removed = 0
        for line in difflib.ndiff(before.splitlines(), after.splitlines()):
            if line.startswith("? "):
                continue
            change_type = "IGUAL"
            if line.startswith("+ "):
                change_type = "ADICIONADA"
                added += 1
            elif line.startswith("- "):
                change_type = "REMOVIDA"
                removed += 1
            changes.append({"tipo": change_type, "texto": line[2:]})
        fields[name] = {
            "alterado": before != after,
            "anterior": before,
            "posterior": after,
            "linhasAdicionadas": added,
            "linhasRemovidas": removed,
            "diferencas": changes,
        }
        total_added += added
        total_removed += removed
    return {
        "de": from_version.version_number,
        "para": to_version.version_number,
        "camposAlterados": [name for name, value in fields.items() if value["alterado"]],
        "linhasAdicionadas": total_added,
        "linhasRemovidas": total_removed,
        "campos": fields,
    }


def tramitation_data(item: LegislativeTramitation) -> dict:
    return {
        "id": str(item.id),
        "status": item.status.value,
        "etapa": item.stage,
        "destino": item.destination,
        "referenciaExterna": item.external_reference,
        "observacoes": item.notes,
        "ocorridaEm": item.occurred_at.isoformat(),
        "registradaEm": item.created_at.isoformat(),
    }


def _tramitations(draft: LegislativeDraft) -> list[dict]:
    items = (
        db.session.execute(
            select(LegislativeTramitation)
            .where(
                LegislativeTramitation.draft_id == draft.id,
                LegislativeTramitation.tenant_id == draft.tenant_id,
            )
            .order_by(
                LegislativeTramitation.occurred_at.asc(),
                LegislativeTramitation.created_at.asc(),
            )
        )
        .scalars()
        .all()
    )
    return [tramitation_data(item) for item in items]


def _parse_occurred_at(value) -> datetime:
    if value in (None, ""):
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def template_data(item: LegislativeTemplate) -> dict:
    return {
        "id": str(item.id),
        "tipo": item.document_type.value,
        "nome": item.name,
        "estrutura": item.structure,
        "ativo": item.active,
        "criadoEm": item.created_at.isoformat(),
        "atualizadoEm": item.updated_at.isoformat(),
    }


def _template_fields(payload: dict) -> tuple[LegislativeDocumentType, str, str]:
    try:
        document_type = LegislativeDocumentType(str(payload.get("tipo", "")).upper())
    except ValueError as error:
        raise ValueError("Tipo de documento inválido.") from error
    name = str(payload.get("nome", "")).strip()
    structure = str(payload.get("estrutura", "")).strip()
    if not name or not structure:
        raise ValueError("Nome e estrutura são obrigatórios.")
    if len(name) > 160:
        raise ValueError("O nome deve possuir no máximo 160 caracteres.")
    if len(structure) > 20000:
        raise ValueError("A estrutura deve possuir no máximo 20.000 caracteres.")
    return document_type, name, structure


def _template(tenant_id: uuid.UUID, template_id: uuid.UUID) -> LegislativeTemplate | None:
    return db.session.execute(
        select(LegislativeTemplate).where(
            LegislativeTemplate.id == template_id,
            LegislativeTemplate.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()


def _normative_source(
    tenant_id: uuid.UUID, source_id: uuid.UUID
) -> NormativeSource | None:
    return db.session.execute(
        select(NormativeSource).where(
            NormativeSource.id == source_id,
            NormativeSource.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()


def _foundation_query(draft: LegislativeDraft) -> str:
    return "\n".join(
        value
        for value in (draft.title, draft.content, draft.justification)
        if value
    )


def _foundation_citation(item: NormativeSource) -> dict:
    return {
        "sourceId": str(item.id),
        "titulo": item.title,
        "referencia": item.reference,
        "trecho": item.excerpt,
        "url": item.source_url,
        "versaoFonte": item.version,
        "checksum": item.checksum,
        "validadaPeloUsuario": True,
        "recuperadaVia": "RAG_NORMATIVO_V1",
    }


def _template_name_exists(
    tenant_id: uuid.UUID,
    name: str,
    excluding_id: uuid.UUID | None = None,
) -> bool:
    statement = select(LegislativeTemplate.id).where(
        LegislativeTemplate.tenant_id == tenant_id,
        func.lower(LegislativeTemplate.name) == name.lower(),
    )
    if excluding_id:
        statement = statement.where(LegislativeTemplate.id != excluding_id)
    return db.session.execute(statement.limit(1)).scalar_one_or_none() is not None


def _draft(tenant_id: uuid.UUID, draft_id: uuid.UUID) -> LegislativeDraft | None:
    return db.session.execute(
        select(LegislativeDraft).where(
            LegislativeDraft.id == draft_id,
            LegislativeDraft.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()


def _request(tenant_id: uuid.UUID, request_id: uuid.UUID) -> ServiceRequest | None:
    return db.session.execute(
        select(ServiceRequest).where(
            ServiceRequest.id == request_id,
            ServiceRequest.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
