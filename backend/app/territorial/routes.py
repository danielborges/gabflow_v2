import hashlib
import io
import json
import uuid
from datetime import UTC, datetime, timedelta
from math import ceil
from urllib.parse import urlparse

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import func, or_, select

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
    AgendaEvent,
    AgendaEventStatus,
    AgendaEventType,
    AttachmentScanStatus,
    NotificationType,
    Role,
    ServiceRequest,
    TerritorialAction,
    TerritorialActionAlert,
    TerritorialActionEvidence,
    TerritorialActionStatus,
    TerritorialActionType,
    TerritorialAlertStatus,
    Territory,
    User,
    UserStatus,
    utc_now,
)
from app.notifications.service import notify_user
from app.security.encryption import read_plaintext
from app.territorial.service import reset_deadline_notifications, resolve_action_alerts

territorial_operations_bp = Blueprint("territorial_operations", __name__)
OPEN_STATUSES = {TerritorialActionStatus.PENDENTE, TerritorialActionStatus.EM_ANDAMENTO}
AGENDA_TYPES = {
    TerritorialActionType.AGENDA: AgendaEventType.COMPROMISSO,
    TerritorialActionType.VISITA: AgendaEventType.VISITA,
    TerritorialActionType.ROTEIRO: AgendaEventType.VISITA,
}


def _context() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(get_jwt()["tenant_id"]), uuid.UUID(get_jwt_identity())


@territorial_operations_bp.get("/painel/territorial/acoes")
@jwt_required()
def list_actions():
    tenant_id, user_id = _context()
    permissions = _permissions(user_id)
    filters = [TerritorialAction.tenant_id == tenant_id]
    territory_id = request.args.get("territorioId", type=str)
    status = request.args.get("status", type=str)
    action_type = request.args.get("tipo", type=str)
    assignee_id = request.args.get("responsavelId", type=str)
    deadline_state = request.args.get("prazoEstado", type=str)
    search = request.args.get("q", type=str, default="").strip()
    page = max(request.args.get("page", type=int, default=1), 1)
    size = request.args.get("size", type=int, default=10)
    if size not in {10, 25, 50, 100}:
        return _validation_error("Quantidade por página inválida.")
    if not permissions["podeGerenciar"]:
        filters.append(TerritorialAction.assignee_id == user_id)
    if territory_id:
        try:
            filters.append(TerritorialAction.territory_id == uuid.UUID(territory_id))
        except ValueError:
            return _validation_error("Território inválido.")
    if status and status.upper() != "TODAS":
        try:
            if status.upper() == "ABERTAS":
                filters.append(TerritorialAction.status.in_(OPEN_STATUSES))
            else:
                filters.append(TerritorialAction.status == TerritorialActionStatus(status.upper()))
        except ValueError:
            return _validation_error("Status inválido.")
    if action_type:
        try:
            filters.append(
                TerritorialAction.action_type == TerritorialActionType(action_type.upper())
            )
        except ValueError:
            return _validation_error("Tipo de ação inválido.")
    if assignee_id:
        assignee = _tenant_entity(User, assignee_id, tenant_id)
        if assignee is None:
            return _validation_error("Responsável inválido.")
        filters.append(TerritorialAction.assignee_id == assignee.id)
    if search:
        filters.append(or_(
            TerritorialAction.title.ilike(f"%{search[:100]}%"),
            TerritorialAction.description.ilike(f"%{search[:100]}%"),
        ))
    try:
        filters.extend(_deadline_filters(deadline_state))
        ordering = _action_ordering(request.args.get("sort", "criadaEm,desc"))
    except ValueError as error:
        return _validation_error(str(error))
    total = db.session.scalar(select(func.count(TerritorialAction.id)).where(*filters)) or 0
    items = db.session.scalars(
        select(TerritorialAction)
        .where(*filters)
        .order_by(*ordering)
        .offset((page - 1) * size)
        .limit(size)
    )
    users = db.session.execute(
        select(User).where(User.tenant_id == tenant_id, User.status == UserStatus.ACTIVE)
        .order_by(User.name)
    ).scalars()
    return jsonify(
        content=[_action_data(item, user_id, permissions) for item in items],
        page=page,
        size=size,
        total=total,
        totalPages=max(ceil(total / size), 1),
        permissoes=permissions,
        responsaveis=(
            [{"id": str(item.id), "nome": item.name} for item in users]
            if permissions["podeGerenciar"]
            else []
        ),
    )


@territorial_operations_bp.post("/painel/territorial/acoes")
@jwt_required()
def create_action():
    tenant_id, user_id = _context()
    if not _permissions(user_id)["podeCriar"]:
        return _forbidden("Somente gestores podem criar ações territoriais.")
    payload = request.get_json(silent=True) or {}
    try:
        values = _creation_values(payload, tenant_id)
    except ValueError as error:
        return _validation_error(str(error))

    duplicate = db.session.execute(
        select(TerritorialAction).where(
            TerritorialAction.tenant_id == tenant_id,
            TerritorialAction.source_key == values["source_key"],
            TerritorialAction.status.in_(OPEN_STATUSES),
        )
    ).scalar_one_or_none()
    if duplicate:
        return jsonify(
            error="conflict",
            code="TERRITORIAL_ACTION_ALREADY_OPEN",
            message="Já existe uma ação aberta para este recorte e tipo.",
            acao=_action_data(duplicate),
        ), 409

    action = TerritorialAction(tenant_id=tenant_id, created_by_id=user_id, **values)
    db.session.add(action)
    db.session.flush()
    if action.action_type in AGENDA_TYPES:
        event = AgendaEvent(
            tenant_id=tenant_id,
            event_type=AGENDA_TYPES[action.action_type],
            title=action.title,
            description=action.description,
            location=action.source_context.get("territorioNome"),
            starts_at=action.due_at,
            territory_id=action.territory_id,
            participants=[],
            pending_items=[],
            photos=[],
            created_by_id=user_id,
        )
        db.session.add(event)
        db.session.flush()
        action.agenda_event_id = event.id
    _notify_assignment(action, user_id)
    data = _action_data(action)
    add_audit(
        tenant_id, user_id, "territorial.action.created", "territorial_action", action.id,
        after=data,
    )
    db.session.commit()
    return jsonify(data), 201


@territorial_operations_bp.patch("/painel/territorial/acoes/<uuid:action_id>")
@jwt_required()
def update_action(action_id: uuid.UUID):
    tenant_id, user_id = _context()
    permissions = _permissions(user_id)
    action = _action_or_none(action_id, tenant_id)
    if action is None or (
        not permissions["podeGerenciar"] and action.assignee_id != user_id
    ):
        return jsonify(error="resource_not_found", message="Ação territorial não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    if not permissions["podeGerenciar"]:
        forbidden_fields = set(payload) - {"status", "resultado", "evidencias"}
        if forbidden_fields or str(payload.get("status", "")).upper() == "CANCELADA":
            return _forbidden("Você pode movimentar somente ações atribuídas a você.")
    before = _action_data(action)
    previous_assignee_id = action.assignee_id
    try:
        _apply_update(action, payload, tenant_id)
    except ValueError as error:
        return _validation_error(str(error))
    _synchronize_agenda(action)
    if action.status in {TerritorialActionStatus.CONCLUIDA, TerritorialActionStatus.CANCELADA}:
        resolve_action_alerts(action, actor_id=user_id)
    if action.assignee_id != previous_assignee_id:
        _notify_assignment(action, user_id)
    after = _action_data(action)
    add_audit(
        tenant_id, user_id, "territorial.action.updated", "territorial_action", action.id,
        before=before, after=after,
    )
    db.session.commit()
    return jsonify(after)


@territorial_operations_bp.get("/painel/territorial/metricas-execucao")
@jwt_required()
def execution_metrics():
    tenant_id, user_id = _context()
    permissions = _permissions(user_id)
    filters = [TerritorialAction.tenant_id == tenant_id]
    territory_id = request.args.get("territorioId", type=str)
    if territory_id:
        try:
            filters.append(TerritorialAction.territory_id == uuid.UUID(territory_id))
        except ValueError:
            return _validation_error("Território inválido.")
    if not permissions["podeGerenciar"]:
        filters.append(TerritorialAction.assignee_id == user_id)
    actions = db.session.scalars(select(TerritorialAction).where(*filters)).all()
    action_ids = [item.id for item in actions]
    evidence_action_ids = set()
    active_alerts = 0
    if action_ids:
        evidence_action_ids = set(db.session.scalars(select(
            TerritorialActionEvidence.action_id
        ).where(
            TerritorialActionEvidence.tenant_id == tenant_id,
            TerritorialActionEvidence.action_id.in_(action_ids),
        )).all())
        active_alerts = db.session.scalar(select(func.count(TerritorialActionAlert.id)).where(
            TerritorialActionAlert.tenant_id == tenant_id,
            TerritorialActionAlert.action_id.in_(action_ids),
            TerritorialActionAlert.status != TerritorialAlertStatus.RESOLVIDO,
        )) or 0
    now = datetime.now(UTC)
    completed = [item for item in actions if item.status == TerritorialActionStatus.CONCLUIDA]
    durations = [
        (_aware(item.completed_at) - _aware(item.created_at)).total_seconds() / 3600
        for item in completed if item.completed_at
    ]
    completed_with_due = [item for item in completed if item.due_at and item.completed_at]
    completed_on_time = sum(
        _aware(item.completed_at) <= _aware(item.due_at) for item in completed_with_due
    )
    by_status = {status.value: 0 for status in TerritorialActionStatus}
    for item in actions:
        by_status[item.status.value] += 1
    return jsonify(
        total=len(actions),
        abertas=sum(item.status in OPEN_STATUSES for item in actions),
        concluidas=len(completed),
        canceladas=by_status[TerritorialActionStatus.CANCELADA.value],
        vencidas=sum(
            item.status in OPEN_STATUSES
            and item.due_at is not None
            and _aware(item.due_at) < now
            for item in actions
        ),
        alertasAtivos=active_alerts,
        comEvidencias=len(evidence_action_ids),
        coberturaEvidenciasPercentual=round(len(evidence_action_ids) * 100 / len(actions), 1)
        if actions else 0,
        taxaConclusaoPercentual=round(len(completed) * 100 / len(actions), 1) if actions else 0,
        cumprimentoPrazoPercentual=round(completed_on_time * 100 / len(completed_with_due), 1)
        if completed_with_due else None,
        tempoMedioConclusaoHoras=round(sum(durations) / len(durations), 1) if durations else None,
        porStatus=by_status,
    )


@territorial_operations_bp.post("/painel/territorial/acoes/<uuid:action_id>/evidencias")
@jwt_required()
def create_evidence(action_id: uuid.UUID):
    tenant_id, user_id = _context()
    action = _action_or_none(action_id, tenant_id)
    permissions = _permissions(user_id)
    if action is None or (not permissions["podeGerenciar"] and action.assignee_id != user_id):
        return jsonify(error="resource_not_found", message="Ação territorial não encontrada."), 404
    payload = request.form if request.files else (request.get_json(silent=True) or {})
    uploaded_file = request.files.get("arquivo")
    evidence_type = str(payload.get("tipo", "DOCUMENTO")).upper()
    if evidence_type not in {"DOCUMENTO", "FOTO", "LINK", "ATA", "COMPROVANTE", "OUTRO"}:
        return _validation_error("Tipo de evidência inválido.")
    title = str(payload.get("titulo", "")).strip() or (
        uploaded_file.filename if uploaded_file else ""
    )
    if len(title) < 3:
        return _validation_error("Informe um título para a evidência.")
    external_url = str(payload.get("url", "")).strip() or None
    if external_url and urlparse(external_url).scheme not in {"http", "https"}:
        return _validation_error("Informe uma URL HTTP ou HTTPS válida.")
    if uploaded_file is None and external_url is None:
        return _validation_error("Envie um arquivo ou informe uma URL.")
    evidence_id = uuid.uuid4()
    stored = {}
    if uploaded_file is not None:
        try:
            stored = store_attachment(tenant_id, evidence_id, uploaded_file)
        except AttachmentError as error:
            return _validation_error(str(error))
        stored["scan_status"] = AttachmentScanStatus.LIMPO
    try:
        occurred_at = _optional_datetime(payload.get("data"))
    except ValueError as error:
        return _validation_error(str(error))
    item = TerritorialActionEvidence(
        id=evidence_id,
        tenant_id=tenant_id,
        action_id=action.id,
        evidence_type=evidence_type,
        title=title[:180],
        description=str(payload.get("descricao", "")).strip()[:2000] or None,
        occurred_at=occurred_at,
        external_url=external_url,
        created_by_id=user_id,
        **stored,
    )
    db.session.add(item)
    db.session.flush()
    data = _evidence_data(item)
    add_audit(
        tenant_id, user_id, "territorial.action.evidence.created",
        "territorial_action_evidence", item.id, after=data,
    )
    db.session.commit()
    return jsonify(data), 201


@territorial_operations_bp.get("/painel/territorial/evidencias/<uuid:evidence_id>/download")
@jwt_required()
def download_evidence(evidence_id: uuid.UUID):
    tenant_id, user_id = _context()
    token = str(request.args.get("token", ""))
    if not verify_attachment_token(token, evidence_id, tenant_id):
        return jsonify(error="invalid_token", message="Link de download inválido ou expirado."), 403
    item = db.session.execute(select(TerritorialActionEvidence).where(
        TerritorialActionEvidence.id == evidence_id,
        TerritorialActionEvidence.tenant_id == tenant_id,
        TerritorialActionEvidence.scan_status == AttachmentScanStatus.LIMPO,
    )).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Evidência não encontrada."), 404
    action = _action_or_none(item.action_id, tenant_id)
    if action is None or (
        not _permissions(user_id)["podeGerenciar"] and action.assignee_id != user_id
    ):
        return jsonify(error="resource_not_found", message="Evidência não encontrada."), 404
    try:
        path = attachment_path(item.storage_key)
    except AttachmentError:
        return jsonify(error="resource_not_found", message="Arquivo não encontrado."), 404
    return send_file(
        io.BytesIO(read_plaintext(path, f"tenant:{tenant_id}")),
        mimetype=item.mime_type,
        as_attachment=True,
        download_name=item.original_name,
    )


@territorial_operations_bp.get("/painel/territorial/alertas")
@jwt_required()
def list_alerts():
    tenant_id, user_id = _context()
    permissions = _permissions(user_id)
    filters = [TerritorialActionAlert.tenant_id == tenant_id]
    status = request.args.get("status", "ABERTOS").upper()
    if status == "ABERTOS":
        filters.append(TerritorialActionAlert.status != TerritorialAlertStatus.RESOLVIDO)
    elif status != "TODOS":
        try:
            filters.append(TerritorialActionAlert.status == TerritorialAlertStatus(status))
        except ValueError:
            return _validation_error("Status de alerta inválido.")
    territory_id = request.args.get("territorioId", type=str)
    action_filters = [TerritorialAction.tenant_id == tenant_id]
    if territory_id:
        try:
            action_filters.append(TerritorialAction.territory_id == uuid.UUID(territory_id))
        except ValueError:
            return _validation_error("Território inválido.")
    if not permissions["podeGerenciar"]:
        action_filters.append(TerritorialAction.assignee_id == user_id)
    allowed_actions = select(TerritorialAction.id).where(*action_filters)
    filters.append(TerritorialActionAlert.action_id.in_(allowed_actions))
    alerts = db.session.scalars(select(TerritorialActionAlert).where(*filters).order_by(
        TerritorialActionAlert.triggered_at.desc()
    ).limit(100)).all()
    return jsonify(content=[_alert_data(item) for item in alerts], total=len(alerts))


@territorial_operations_bp.patch("/painel/territorial/alertas/<uuid:alert_id>")
@jwt_required()
def update_alert(alert_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = db.session.execute(select(TerritorialActionAlert).where(
        TerritorialActionAlert.id == alert_id,
        TerritorialActionAlert.tenant_id == tenant_id,
    )).scalar_one_or_none()
    if item is None:
        return jsonify(error="resource_not_found", message="Alerta não encontrado."), 404
    action = _action_or_none(item.action_id, tenant_id)
    permissions = _permissions(user_id)
    if action is None or (not permissions["podeGerenciar"] and action.assignee_id != user_id):
        return jsonify(error="resource_not_found", message="Alerta não encontrado."), 404
    payload = request.get_json(silent=True) or {}
    try:
        status = TerritorialAlertStatus(str(payload.get("status", "")).upper())
    except ValueError:
        return _validation_error("Status de alerta inválido.")
    if status == TerritorialAlertStatus.ATIVO:
        return _validation_error("Um alerta processado não pode voltar ao estado ativo.")
    before = _alert_data(item)
    now = datetime.now(UTC)
    if status == TerritorialAlertStatus.RECONHECIDO:
        item.status = status
        item.acknowledged_at = now
        item.acknowledged_by_id = user_id
    else:
        note = str(payload.get("justificativa", "")).strip()
        if len(note) < 3:
            return _validation_error("Informe como o alerta foi resolvido.")
        item.status = status
        item.resolved_at = now
        item.resolved_by_id = user_id
        item.resolution_note = note[:500]
    after = _alert_data(item)
    add_audit(
        tenant_id, user_id, "territorial.action.alert.updated",
        "territorial_action_alert", item.id, before=before, after=after,
    )
    db.session.commit()
    return jsonify(after)


def _creation_values(payload: dict, tenant_id: uuid.UUID) -> dict:
    territory = _tenant_entity(Territory, payload.get("territorioId"), tenant_id)
    if territory is None:
        raise ValueError("Selecione um território válido.")
    try:
        action_type = TerritorialActionType(str(payload.get("tipo", "")).upper())
    except ValueError as error:
        raise ValueError("Tipo de ação inválido.") from error
    title = str(payload.get("titulo", "")).strip()
    if len(title) < 3:
        raise ValueError("Informe um título com pelo menos 3 caracteres.")
    assignee = _tenant_entity(User, payload.get("responsavelId"), tenant_id)
    if payload.get("responsavelId") and assignee is None:
        raise ValueError("Responsável inválido.")
    due_at = _optional_datetime(payload.get("prazo"))
    if action_type in AGENDA_TYPES and due_at is None:
        raise ValueError("Informe data e hora para agenda, visita ou roteiro.")
    filters = payload.get("filtros") if isinstance(payload.get("filtros"), dict) else {}
    request_ids = _request_ids(payload.get("solicitacaoIds"), tenant_id)
    source_context = payload.get("origem") if isinstance(payload.get("origem"), dict) else {}
    source_context = {**source_context, "territorioNome": territory.name}
    source_key = _source_key(territory.id, action_type, filters, source_context)
    return {
        "territory_id": territory.id,
        "action_type": action_type,
        "title": title,
        "description": str(payload.get("descricao", "")).strip() or None,
        "assignee_id": assignee.id if assignee else None,
        "due_at": due_at,
        "source_key": source_key,
        "source_context": source_context,
        "filters": filters,
        "request_ids": request_ids,
        "evidence": [],
    }


def _apply_update(action: TerritorialAction, payload: dict, tenant_id: uuid.UUID) -> None:
    if "responsavelId" in payload:
        assignee = _tenant_entity(User, payload.get("responsavelId"), tenant_id)
        if payload.get("responsavelId") and assignee is None:
            raise ValueError("Responsável inválido.")
        action.assignee_id = assignee.id if assignee else None
    if "prazo" in payload:
        action.due_at = _optional_datetime(payload.get("prazo"))
        reset_deadline_notifications(action)
    if "evidencias" in payload:
        evidence = payload.get("evidencias")
        if not isinstance(evidence, list) or len(evidence) > 20:
            raise ValueError("Evidências inválidas.")
        action.evidence = [str(item).strip()[:500] for item in evidence if str(item).strip()]
    if "status" not in payload:
        return
    try:
        status = TerritorialActionStatus(str(payload["status"]).upper())
    except ValueError as error:
        raise ValueError("Status inválido.") from error
    result = str(payload.get("resultado", "")).strip()
    closing_statuses = {
        TerritorialActionStatus.CONCLUIDA,
        TerritorialActionStatus.CANCELADA,
    }
    if status in closing_statuses and len(result) < 3:
        raise ValueError("Informe o resultado ou a justificativa para encerrar a ação.")
    action.status = status
    if result:
        action.result = result
    action.completed_at = utc_now() if status in closing_statuses else None


def _synchronize_agenda(action: TerritorialAction) -> None:
    if not action.agenda_event_id:
        return
    event = db.session.get(AgendaEvent, action.agenda_event_id)
    if event is None or event.tenant_id != action.tenant_id:
        return
    event.starts_at = action.due_at or event.starts_at
    if action.status == TerritorialActionStatus.CONCLUIDA:
        event.status = AgendaEventStatus.REALIZADO
        event.minutes = action.result
    elif action.status == TerritorialActionStatus.CANCELADA:
        event.status = AgendaEventStatus.CANCELADO


def _request_ids(values, tenant_id: uuid.UUID) -> list[str]:
    if values in (None, ""):
        return []
    if not isinstance(values, list) or len(values) > 100:
        raise ValueError("A lista de solicitações deve conter no máximo 100 itens.")
    try:
        ids = list(dict.fromkeys(uuid.UUID(str(value)) for value in values))
    except ValueError as error:
        raise ValueError("Solicitação inválida.") from error
    found = set(db.session.execute(
        select(ServiceRequest.id).where(
            ServiceRequest.tenant_id == tenant_id, ServiceRequest.id.in_(ids)
        )
    ).scalars())
    if found != set(ids):
        raise ValueError("Uma ou mais solicitações não pertencem ao gabinete.")
    return [str(value) for value in ids]


def _source_key(territory_id, action_type, filters: dict, context: dict) -> str:
    semantic_source = {
        "territorioId": str(territory_id),
        "tipo": action_type.value,
        "filtros": filters,
        "alerta": context.get("alertaChave"),
    }
    digest = hashlib.sha256(
        json.dumps(semantic_source, sort_keys=True, ensure_ascii=True).encode()
    ).hexdigest()[:24]
    return f"territory:{territory_id}:{action_type.value}:{digest}"


def _action_data(
    item: TerritorialAction,
    actor_id: uuid.UUID | None = None,
    permissions: dict | None = None,
) -> dict:
    territory = db.session.get(Territory, item.territory_id)
    assignee = db.session.get(User, item.assignee_id) if item.assignee_id else None
    base_permissions = permissions or {"podeGerenciar": True, "podeCriar": True}
    can_move = base_permissions["podeGerenciar"] or item.assignee_id == actor_id
    evidence = db.session.scalars(select(TerritorialActionEvidence).where(
        TerritorialActionEvidence.tenant_id == item.tenant_id,
        TerritorialActionEvidence.action_id == item.id,
    ).order_by(TerritorialActionEvidence.created_at.desc())).all()
    return {
        "id": str(item.id),
        "territorioId": str(item.territory_id),
        "territorio": territory.name if territory else "Território removido",
        "tipo": item.action_type.value,
        "status": item.status.value,
        "titulo": item.title,
        "descricao": item.description,
        "responsavelId": str(item.assignee_id) if item.assignee_id else None,
        "responsavel": assignee.name if assignee else "Não atribuído",
        "prazo": item.due_at.isoformat() if item.due_at else None,
        "prazoEstado": _deadline_state(item),
        "origem": item.source_context,
        "filtros": item.filters,
        "solicitacaoIds": item.request_ids,
        "resultado": item.result,
        "evidencias": item.evidence,
        "evidenciasEstruturadas": [_evidence_data(value) for value in evidence],
        "agendaEventoId": str(item.agenda_event_id) if item.agenda_event_id else None,
        "concluidaEm": item.completed_at.isoformat() if item.completed_at else None,
        "criadaEm": item.created_at.isoformat(),
        "atualizadaEm": item.updated_at.isoformat(),
        "permissoes": {
            "podeMovimentar": can_move,
            "podeReatribuir": base_permissions["podeGerenciar"],
            "podeAlterarPrazo": base_permissions["podeGerenciar"],
            "podeCancelar": base_permissions["podeGerenciar"],
        },
    }


def _permissions(user_id: uuid.UUID) -> dict:
    claims = get_jwt()
    role = claims.get("role")
    can_manage = role in {
        Role.ADMIN.value,
        Role.MANAGER.value,
        Role.REPRESENTATIVE.value,
    } or claims.get("is_chief_of_staff") is True
    return {
        "podeCriar": can_manage,
        "podeGerenciar": can_manage,
        "escopo": "GABINETE" if can_manage else "PROPRIAS",
        "usuarioId": str(user_id),
    }


def _deadline_state(item: TerritorialAction) -> str:
    if item.status not in OPEN_STATUSES:
        return "ENCERRADA"
    if item.due_at is None:
        return "SEM_PRAZO"
    due_at = item.due_at if item.due_at.tzinfo else item.due_at.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    if due_at < now:
        return "VENCIDA"
    if due_at <= now + timedelta(hours=24):
        return "PROXIMA"
    return "NO_PRAZO"


def _evidence_data(item: TerritorialActionEvidence) -> dict:
    author = db.session.get(User, item.created_by_id)
    download_url = None
    if item.storage_key:
        token = signed_attachment_token(item.id, item.tenant_id)
        download_url = f"/api/v1/painel/territorial/evidencias/{item.id}/download?token={token}"
    return {
        "id": str(item.id),
        "tipo": item.evidence_type,
        "titulo": item.title,
        "descricao": item.description,
        "data": item.occurred_at.isoformat() if item.occurred_at else None,
        "url": item.external_url,
        "nomeArquivo": item.original_name,
        "mimeType": item.mime_type,
        "tamanho": item.size_bytes,
        "sha256": item.sha256,
        "statusVerificacao": item.scan_status.value if item.scan_status else None,
        "downloadUrl": download_url,
        "autor": author.name if author else "Usuário removido",
        "criadaEm": item.created_at.isoformat(),
    }


def _alert_data(item: TerritorialActionAlert) -> dict:
    action = db.session.get(TerritorialAction, item.action_id)
    territory = db.session.get(Territory, action.territory_id) if action else None
    return {
        "id": str(item.id),
        "acaoId": str(item.action_id),
        "acaoTitulo": action.title if action else "Ação removida",
        "territorio": territory.name if territory else "Território removido",
        "tipo": item.alert_type,
        "status": item.status.value,
        "titulo": item.title,
        "mensagem": item.message,
        "disparadoEm": item.triggered_at.isoformat(),
        "reconhecidoEm": item.acknowledged_at.isoformat() if item.acknowledged_at else None,
        "resolvidoEm": item.resolved_at.isoformat() if item.resolved_at else None,
        "justificativa": item.resolution_note,
    }


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _deadline_filters(value: str | None) -> list:
    if not value:
        return []
    state = value.upper()
    now = datetime.now(UTC)
    if state == "VENCIDA":
        return [TerritorialAction.status.in_(OPEN_STATUSES), TerritorialAction.due_at < now]
    if state == "PROXIMA":
        return [
            TerritorialAction.status.in_(OPEN_STATUSES),
            TerritorialAction.due_at >= now,
            TerritorialAction.due_at <= now + timedelta(hours=24),
        ]
    if state == "NO_PRAZO":
        return [
            TerritorialAction.status.in_(OPEN_STATUSES),
            TerritorialAction.due_at > now + timedelta(hours=24),
        ]
    if state == "SEM_PRAZO":
        return [
            TerritorialAction.status.in_(OPEN_STATUSES),
            TerritorialAction.due_at.is_(None),
        ]
    if state == "ENCERRADA":
        return [TerritorialAction.status.not_in(OPEN_STATUSES)]
    raise ValueError("Estado de prazo inválido.")


def _action_ordering(value: str) -> list:
    field, _, direction = value.partition(",")
    columns = {
        "criadaEm": TerritorialAction.created_at,
        "prazo": TerritorialAction.due_at,
        "titulo": TerritorialAction.title,
        "status": TerritorialAction.status,
    }
    column = columns.get(field)
    if column is None or direction.lower() not in {"asc", "desc"}:
        raise ValueError("Ordenação inválida.")
    ordered = column.asc() if direction.lower() == "asc" else column.desc()
    return [ordered.nulls_last(), TerritorialAction.created_at.desc()]


def _notify_assignment(action: TerritorialAction, actor_id: uuid.UUID) -> None:
    if action.assignee_id is None or action.assignee_id == actor_id:
        return
    territory_name = action.source_context.get("territorioNome", "território")
    notify_user(
        action.tenant_id,
        action.assignee_id,
        NotificationType.ATRIBUICAO,
        "Nova ação territorial",
        f'Você recebeu a ação "{action.title}" em {territory_name}.',
        "territorial_action",
        action.id,
    )


def _action_or_none(action_id: uuid.UUID, tenant_id: uuid.UUID):
    return db.session.execute(select(TerritorialAction).where(
        TerritorialAction.id == action_id, TerritorialAction.tenant_id == tenant_id,
    )).scalar_one_or_none()


def _tenant_entity(model, value, tenant_id: uuid.UUID):
    if not value:
        return None
    try:
        entity_id = uuid.UUID(str(value))
    except ValueError:
        return None
    return db.session.execute(
        select(model).where(model.id == entity_id, model.tenant_id == tenant_id)
    ).scalar_one_or_none()


def _optional_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Data inválida.") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _validation_error(message: str):
    return jsonify(error="validation_error", message=message), 422


def _forbidden(message: str):
    return jsonify(error="forbidden", message=message), 403
