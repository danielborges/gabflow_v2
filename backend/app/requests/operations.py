import uuid
from datetime import UTC, datetime

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import select

from app.ai.ocr import enqueue_document_ocr, ocr_data, requeue_document_ocr
from app.ai.transcription import (
    enqueue_audio_transcription,
    requeue_audio_transcription,
    transcription_data,
)
from app.attachments import (
    AttachmentError,
    attachment_path,
    signed_attachment_token,
    store_attachment,
    verify_attachment_token,
)
from app.audit import add_audit
from app.extensions import db
from app.models import (
    Attachment,
    AttachmentScanStatus,
    AudioTranscription,
    AudioTranscriptionReviewStatus,
    AudioTranscriptionStatus,
    DocumentOcr,
    DocumentOcrReviewStatus,
    DocumentOcrStatus,
    DuplicateGroup,
    NotificationType,
    RequestHistory,
    RequestPriority,
    RequestTask,
    ServiceRequest,
    TaskStatus,
    User,
    UserStatus,
)
from app.notifications.service import notify_user

request_ops_bp = Blueprint("request_operations", __name__)


def _context() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(get_jwt()["tenant_id"]), uuid.UUID(get_jwt_identity())


def _service_request(request_id: uuid.UUID, tenant_id: uuid.UUID) -> ServiceRequest | None:
    return db.session.execute(
        select(ServiceRequest).where(
            ServiceRequest.id == request_id,
            ServiceRequest.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()


def task_data(task: RequestTask) -> dict:
    return {
        "id": str(task.id),
        "titulo": task.title,
        "descricao": task.description,
        "responsavelId": str(task.assignee_id) if task.assignee_id else None,
        "status": task.status.value,
        "prioridade": task.priority.value,
        "prazo": task.due_at.isoformat() if task.due_at else None,
        "concluidaEm": task.completed_at.isoformat() if task.completed_at else None,
        "criadaEm": task.created_at.isoformat(),
    }


def attachment_data(item: Attachment) -> dict:
    token = signed_attachment_token(item.id, item.tenant_id)
    return {
        "id": str(item.id),
        "nome": item.original_name,
        "mimeType": item.mime_type,
        "tamanho": item.size_bytes,
        "sha256": item.sha256,
        "statusVerificacao": item.scan_status.value,
        "downloadUrl": f"/api/v1/anexos/{item.id}/download?token={token}",
        "transcricao": transcription_data(item.transcription),
        "ocr": ocr_data(item.ocr),
        "criadoEm": item.created_at.isoformat(),
    }


@request_ops_bp.post("/solicitacoes/<uuid:request_id>/tarefas")
@jwt_required()
def create_task(request_id: uuid.UUID):
    tenant_id, user_id = _context()
    service_request = _service_request(request_id, tenant_id)
    if service_request is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("titulo", "")).strip()
    if len(title) < 3:
        return jsonify(error="validation_error", message="Informe o título da tarefa."), 422

    assignee_id = _valid_user_id(payload.get("responsavelId"), tenant_id)
    if payload.get("responsavelId") and assignee_id is None:
        return jsonify(error="validation_error", message="Responsável inválido."), 422
    try:
        priority = RequestPriority(str(payload.get("prioridade", "MEDIA")).upper())
        due_at = _parse_datetime(payload.get("prazo"))
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 422

    task = RequestTask(
        tenant_id=tenant_id,
        request_id=service_request.id,
        title=title,
        description=str(payload.get("descricao", "")).strip() or None,
        assignee_id=assignee_id,
        priority=priority,
        due_at=due_at,
        created_by_id=user_id,
    )
    db.session.add(task)
    db.session.flush()
    service_request.history.append(
        RequestHistory(
            tenant_id=tenant_id,
            user_id=user_id,
            action="task.created",
            changes={"tarefaId": {"antes": None, "depois": str(task.id)}},
        )
    )
    notify_user(
        tenant_id,
        assignee_id,
        NotificationType.TAREFA,
        "Nova tarefa atribuída",
        f"{title} na solicitação {service_request.protocol}.",
        "request_task",
        task.id,
    )
    add_audit(
        tenant_id,
        user_id,
        "task.created",
        "request_task",
        task.id,
        after=task_data(task),
    )
    db.session.commit()
    return jsonify(task_data(task)), 201


@request_ops_bp.patch("/tarefas/<uuid:task_id>")
@jwt_required()
def update_task(task_id: uuid.UUID):
    tenant_id, user_id = _context()
    task = db.session.execute(
        select(RequestTask).where(
            RequestTask.id == task_id,
            RequestTask.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if task is None:
        return jsonify(error="resource_not_found", message="Tarefa não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    before = task_data(task)
    try:
        if "status" in payload:
            task.status = TaskStatus(str(payload["status"]).upper())
            task.completed_at = datetime.now(UTC) if task.status == TaskStatus.CONCLUIDA else None
        if "prioridade" in payload:
            task.priority = RequestPriority(str(payload["prioridade"]).upper())
        if "prazo" in payload:
            task.due_at = _parse_datetime(payload["prazo"])
    except ValueError:
        return jsonify(
            error="validation_error", message="Status, prioridade ou prazo inválido."
        ), 422
    after = task_data(task)
    add_audit(tenant_id, user_id, "task.updated", "request_task", task.id, before, after)
    db.session.commit()
    return jsonify(after)


@request_ops_bp.post("/solicitacoes/agrupar-duplicadas")
@jwt_required()
def group_duplicates():
    tenant_id, user_id = _context()
    payload = request.get_json(silent=True) or {}
    ids = payload.get("solicitacaoIds") or []
    reason = str(payload.get("motivo", "")).strip()
    if len(set(ids)) < 2 or not reason:
        return (
            jsonify(
                error="validation_error",
                message="Informe ao menos duas solicitações e o motivo do agrupamento.",
            ),
            422,
        )
    try:
        request_ids = [uuid.UUID(item) for item in set(ids)]
    except (TypeError, ValueError):
        return jsonify(error="validation_error", message="Identificador inválido."), 422

    requests_found = list(
        db.session.execute(
            select(ServiceRequest).where(
                ServiceRequest.tenant_id == tenant_id,
                ServiceRequest.id.in_(request_ids),
            )
        ).scalars()
    )
    if len(requests_found) != len(request_ids):
        return jsonify(error="validation_error", message="Solicitação inválida para o tenant."), 422

    existing_groups = {
        item.duplicate_group_id for item in requests_found if item.duplicate_group_id
    }
    if len(existing_groups) > 1:
        return (
            jsonify(
                error="validation_error",
                message="As solicitações já pertencem a agrupamentos distintos.",
            ),
            422,
        )
    if existing_groups:
        group = db.session.get(DuplicateGroup, existing_groups.pop())
    else:
        group = DuplicateGroup(
            tenant_id=tenant_id,
            reason=reason,
            created_by_id=user_id,
        )
        db.session.add(group)
        db.session.flush()

    for service_request in requests_found:
        previous = service_request.duplicate_group_id
        service_request.duplicate_group_id = group.id
        service_request.history.append(
            RequestHistory(
                tenant_id=tenant_id,
                user_id=user_id,
                action="request.duplicate_grouped",
                changes={
                    "duplicate_group_id": {
                        "antes": str(previous) if previous else None,
                        "depois": str(group.id),
                    }
                },
            )
        )
    add_audit(
        tenant_id,
        user_id,
        "request.duplicates.grouped",
        "duplicate_group",
        group.id,
        after={"solicitacaoIds": [str(item.id) for item in requests_found], "motivo": reason},
    )
    db.session.commit()
    return jsonify(
        id=str(group.id),
        motivo=group.reason,
        solicitacaoIds=[str(item.id) for item in requests_found],
    ), 201


@request_ops_bp.post("/solicitacoes/<uuid:request_id>/anexos")
@jwt_required()
def upload_attachment(request_id: uuid.UUID):
    tenant_id, user_id = _context()
    service_request = _service_request(request_id, tenant_id)
    if service_request is None:
        return jsonify(error="resource_not_found", message="Solicitação não encontrada."), 404
    uploaded_file = request.files.get("arquivo")
    if uploaded_file is None:
        return jsonify(error="validation_error", message="Selecione um arquivo."), 422

    attachment_id = uuid.uuid4()
    try:
        stored = store_attachment(tenant_id, attachment_id, uploaded_file)
    except AttachmentError as error:
        return jsonify(error="validation_error", message=str(error)), 422

    item = Attachment(
        id=attachment_id,
        tenant_id=tenant_id,
        request_id=service_request.id,
        scan_status=AttachmentScanStatus.LIMPO,
        uploaded_by_id=user_id,
        **stored,
    )
    db.session.add(item)
    db.session.flush()
    enqueue_audio_transcription(item, user_id)
    enqueue_document_ocr(item, user_id)
    service_request.history.append(
        RequestHistory(
            tenant_id=tenant_id,
            user_id=user_id,
            action="attachment.created",
            changes={"anexoId": {"antes": None, "depois": str(item.id)}},
        )
    )
    add_audit(
        tenant_id,
        user_id,
        "attachment.created",
        "attachment",
        item.id,
        after={
            "nome": item.original_name,
            "mimeType": item.mime_type,
            "sha256": item.sha256,
        },
    )
    db.session.commit()
    return jsonify(attachment_data(item)), 201


@request_ops_bp.post("/transcricoes-audio/<uuid:transcription_id>/revisao")
@jwt_required()
def review_audio_transcription(transcription_id: uuid.UUID):
    tenant_id, user_id = _context()
    transcription = db.session.execute(
        select(AudioTranscription).where(
            AudioTranscription.id == transcription_id,
            AudioTranscription.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if transcription is None:
        return jsonify(error="resource_not_found", message="Transcrição não encontrada."), 404
    if (
        transcription.status != AudioTranscriptionStatus.CONCLUIDA
        or transcription.review_status != AudioTranscriptionReviewStatus.PENDENTE
    ):
        return (
            jsonify(
                error="conflict",
                message="A transcrição ainda não foi concluída ou já possui revisão.",
            ),
            409,
        )

    payload = request.get_json(silent=True) or {}
    action = str(payload.get("acao", "")).upper()
    status_by_action = {
        "ACEITAR": AudioTranscriptionReviewStatus.ACEITA,
        "EDITAR": AudioTranscriptionReviewStatus.EDITADA,
        "REJEITAR": AudioTranscriptionReviewStatus.REJEITADA,
    }
    if action not in status_by_action:
        return jsonify(error="validation_error", message="Ação de revisão inválida."), 422
    reviewed_text = None
    if action == "ACEITAR":
        reviewed_text = transcription.transcript
    elif action == "EDITAR":
        reviewed_text = str(payload.get("texto", "")).strip()
        if not reviewed_text:
            return jsonify(error="validation_error", message="Informe o texto revisado."), 422

    transcription.review_status = status_by_action[action]
    transcription.reviewed_transcript = reviewed_text
    transcription.reviewed_by_id = user_id
    transcription.reviewed_at = datetime.now(UTC)
    details = {
        "transcricaoId": str(transcription.id),
        "acao": action,
        "textoAlterado": action == "EDITAR",
    }
    db.session.add(
        RequestHistory(
            tenant_id=tenant_id,
            request_id=transcription.request_id,
            user_id=user_id,
            action=f"audio.transcription.{action.lower()}",
            changes=details,
        )
    )
    add_audit(
        tenant_id,
        user_id,
        f"audio.transcription.{action.lower()}",
        "audio_transcription",
        transcription.id,
        after=details,
    )
    db.session.commit()
    return jsonify(transcription_data(transcription))


@request_ops_bp.post("/transcricoes-audio/<uuid:transcription_id>/reprocessar")
@jwt_required()
def reprocess_audio_transcription(transcription_id: uuid.UUID):
    tenant_id, user_id = _context()
    transcription = db.session.execute(
        select(AudioTranscription).where(
            AudioTranscription.id == transcription_id,
            AudioTranscription.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if transcription is None:
        return jsonify(error="resource_not_found", message="Transcrição não encontrada."), 404
    if transcription.status != AudioTranscriptionStatus.FALHOU:
        return (
            jsonify(error="conflict", message="Somente transcrições com falha podem ser refeitas."),
            409,
        )
    requeue_audio_transcription(transcription)
    details = {"transcricaoId": str(transcription.id), "acao": "REPROCESSAR"}
    db.session.add(
        RequestHistory(
            tenant_id=tenant_id,
            request_id=transcription.request_id,
            user_id=user_id,
            action="audio.transcription.reprocessed",
            changes=details,
        )
    )
    add_audit(
        tenant_id,
        user_id,
        "audio.transcription.reprocessed",
        "audio_transcription",
        transcription.id,
        after=details,
    )
    db.session.commit()
    return jsonify(transcription_data(transcription)), 202


@request_ops_bp.post("/ocr-documentos/<uuid:ocr_id>/revisao")
@jwt_required()
def review_document_ocr(ocr_id: uuid.UUID):
    tenant_id, user_id = _context()
    ocr = db.session.execute(
        select(DocumentOcr).where(
            DocumentOcr.id == ocr_id,
            DocumentOcr.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if ocr is None:
        return jsonify(error="resource_not_found", message="OCR não encontrado."), 404
    if (
        ocr.status != DocumentOcrStatus.CONCLUIDO
        or ocr.review_status != DocumentOcrReviewStatus.PENDENTE
    ):
        return (
            jsonify(
                error="conflict",
                message="O OCR ainda não foi concluído ou já possui revisão.",
            ),
            409,
        )

    payload = request.get_json(silent=True) or {}
    action = str(payload.get("acao", "")).upper()
    status_by_action = {
        "ACEITAR": DocumentOcrReviewStatus.ACEITO,
        "EDITAR": DocumentOcrReviewStatus.EDITADO,
        "REJEITAR": DocumentOcrReviewStatus.REJEITADO,
    }
    if action not in status_by_action:
        return jsonify(error="validation_error", message="Ação de revisão inválida."), 422
    reviewed_text = None
    if action == "ACEITAR":
        reviewed_text = ocr.extracted_text
    elif action == "EDITAR":
        reviewed_text = str(payload.get("texto", "")).strip()
        if not reviewed_text:
            return jsonify(error="validation_error", message="Informe o texto revisado."), 422

    ocr.review_status = status_by_action[action]
    ocr.reviewed_text = reviewed_text
    ocr.reviewed_by_id = user_id
    ocr.reviewed_at = datetime.now(UTC)
    details = {
        "ocrId": str(ocr.id),
        "acao": action,
        "textoAlterado": action == "EDITAR",
        "confianca": ocr.confidence,
    }
    db.session.add(
        RequestHistory(
            tenant_id=tenant_id,
            request_id=ocr.request_id,
            user_id=user_id,
            action=f"document.ocr.{action.lower()}",
            changes=details,
        )
    )
    add_audit(
        tenant_id,
        user_id,
        f"document.ocr.{action.lower()}",
        "document_ocr",
        ocr.id,
        after=details,
    )
    db.session.commit()
    return jsonify(ocr_data(ocr))


@request_ops_bp.post("/ocr-documentos/<uuid:ocr_id>/reprocessar")
@jwt_required()
def reprocess_document_ocr(ocr_id: uuid.UUID):
    tenant_id, user_id = _context()
    ocr = db.session.execute(
        select(DocumentOcr).where(
            DocumentOcr.id == ocr_id,
            DocumentOcr.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if ocr is None:
        return jsonify(error="resource_not_found", message="OCR não encontrado."), 404
    if ocr.status != DocumentOcrStatus.FALHOU:
        return (
            jsonify(error="conflict", message="Somente OCRs com falha podem ser refeitos."),
            409,
        )
    requeue_document_ocr(ocr)
    details = {"ocrId": str(ocr.id), "acao": "REPROCESSAR"}
    db.session.add(
        RequestHistory(
            tenant_id=tenant_id,
            request_id=ocr.request_id,
            user_id=user_id,
            action="document.ocr.reprocessed",
            changes=details,
        )
    )
    add_audit(
        tenant_id,
        user_id,
        "document.ocr.reprocessed",
        "document_ocr",
        ocr.id,
        after=details,
    )
    db.session.commit()
    return jsonify(ocr_data(ocr)), 202


@request_ops_bp.get("/anexos/<uuid:attachment_id>/download")
@jwt_required()
def download_attachment(attachment_id: uuid.UUID):
    tenant_id, _ = _context()
    token = str(request.args.get("token", ""))
    if not verify_attachment_token(token, attachment_id, tenant_id):
        return jsonify(error="invalid_token", message="Link de download inválido ou expirado."), 403
    item = db.session.execute(
        select(Attachment).where(
            Attachment.id == attachment_id,
            Attachment.tenant_id == tenant_id,
            Attachment.scan_status == AttachmentScanStatus.LIMPO,
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Anexo não encontrado."), 404
    try:
        path = attachment_path(item.storage_key)
    except AttachmentError:
        return jsonify(error="resource_not_found", message="Arquivo não encontrado."), 404
    return send_file(
        path, mimetype=item.mime_type, as_attachment=True, download_name=item.original_name
    )


def _valid_user_id(value, tenant_id: uuid.UUID) -> uuid.UUID | None:
    if not value:
        return None
    try:
        user_id = uuid.UUID(str(value))
    except ValueError:
        return None
    user = db.session.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_id,
            User.status == UserStatus.ACTIVE,
        )
    ).scalar_one_or_none()
    return user.id if user else None


def _parse_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Prazo inválido.") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
