import io
import uuid
from datetime import UTC, datetime

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import select

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
    ExternalAgency,
    OversightAction,
    OversightActionStatus,
    OversightEvidence,
    ServiceRequest,
    User,
)
from app.oversight.service import (
    pending_oversight_events,
    resolve_oversight_reminders,
    user_is_event_participant,
)
from app.security.encryption import read_plaintext

oversight_bp = Blueprint("oversight", __name__)


def _context() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(get_jwt()["tenant_id"]), uuid.UUID(get_jwt_identity())


@oversight_bp.get("/fiscalizacoes")
@jwt_required()
def list_actions():
    tenant_id, _ = _context()
    items = db.session.execute(
        select(OversightAction)
        .where(OversightAction.tenant_id == tenant_id)
        .order_by(OversightAction.created_at.desc())
    ).scalars()
    return jsonify(content=[action_data(item) for item in items])


@oversight_bp.get("/fiscalizacoes/pendentes-relatorio")
@jwt_required()
def list_pending_reports():
    tenant_id, user_id = _context()
    return jsonify(content=pending_oversight_events(tenant_id, user_id))


@oversight_bp.post("/fiscalizacoes")
@jwt_required()
def create_action():
    tenant_id, user_id = _context()
    payload = dict(request.get_json(silent=True) or {})
    agenda_event = None
    if payload.get("agendaEventoId"):
        agenda_event = _agenda_event_or_none(payload["agendaEventoId"], tenant_id)
        if agenda_event is None or agenda_event.event_type != AgendaEventType.FISCALIZACAO:
            return _validation_error("Compromisso de fiscalização inválido.")
        if not user_is_event_participant(agenda_event, user_id):
            return jsonify(error="resource_not_found", message="Pendência não encontrada."), 404
        if _aware(agenda_event.ends_at or agenda_event.starts_at) > datetime.now(UTC):
            return _validation_error("O compromisso ainda não foi realizado.")
        existing = db.session.execute(
            select(OversightAction).where(
                OversightAction.tenant_id == tenant_id,
                OversightAction.agenda_event_id == agenda_event.id,
            )
        ).scalar_one_or_none()
        if existing:
            return jsonify(
                error="conflict",
                message="Já existe um relatório iniciado para este compromisso.",
                fiscalizacaoId=str(existing.id),
            ), 409
        payload.setdefault("titulo", agenda_event.title)
        payload.setdefault("descricao", agenda_event.description or "")
        payload.setdefault("local", agenda_event.location or "")
        payload.setdefault("realizadaEm", agenda_event.starts_at.isoformat())
        payload.setdefault(
            "solicitacaoId", str(agenda_event.request_id) if agenda_event.request_id else None
        )
    try:
        values = _action_values(payload)
    except ValueError as error:
        return _validation_error(str(error))
    relationships = _relationships(payload, tenant_id)
    if isinstance(relationships, tuple):
        return relationships
    if values["status"] == OversightActionStatus.CONCLUIDA and not values["report"]:
        return _validation_error("Informe o relatório antes de concluir a fiscalização.")
    item = OversightAction(
        tenant_id=tenant_id,
        created_by_id=user_id,
        agenda_event_id=agenda_event.id if agenda_event else None,
        **values,
        **relationships,
    )
    db.session.add(item)
    db.session.flush()
    if agenda_event and item.status == OversightActionStatus.CONCLUIDA:
        _complete_agenda_event(agenda_event, tenant_id)
    data = action_data(item)
    add_audit(
        tenant_id,
        user_id,
        "oversight.action.created",
        "oversight_action",
        item.id,
        after=data,
    )
    db.session.commit()
    return jsonify(data), 201


@oversight_bp.patch("/fiscalizacoes/<uuid:action_id>")
@jwt_required()
def update_action(action_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = _action_or_none(action_id, tenant_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Fiscalização não encontrada."), 404
    payload = request.get_json(silent=True) or {}
    before = action_data(item)
    if "status" in payload:
        try:
            item.status = OversightActionStatus(str(payload["status"]).upper())
        except ValueError:
            return _validation_error("Status inválido.")
    for field_name, attr in (
        ("titulo", "title"),
        ("descricao", "description"),
        ("local", "location"),
        ("relatorio", "report"),
    ):
        if field_name in payload:
            setattr(item, attr, str(payload[field_name]).strip() or None)
    if "realizadaEm" in payload:
        try:
            item.occurred_at = _optional_datetime(payload["realizadaEm"])
        except ValueError as error:
            return _validation_error(str(error))
    for field_name, attr in (
        ("achados", "findings"),
        ("fotos", "photos"),
        ("responsaveis", "responsible_parties"),
        ("providencias", "follow_up_actions"),
    ):
        if field_name in payload:
            try:
                setattr(item, attr, _list_value(payload[field_name], field_name))
            except ValueError as error:
                return _validation_error(str(error))
    if "orgaoId" in payload or "solicitacaoId" in payload:
        relationships = _relationships(
            {
                "orgaoId": payload.get("orgaoId", str(item.agency_id) if item.agency_id else None),
                "solicitacaoId": payload.get(
                    "solicitacaoId", str(item.request_id) if item.request_id else None
                ),
            },
            tenant_id,
        )
        if isinstance(relationships, tuple):
            return relationships
        item.agency_id = relationships["agency_id"]
        item.request_id = relationships["request_id"]
    if item.status == OversightActionStatus.CONCLUIDA and not item.report:
        return _validation_error("Informe o relatório antes de concluir a fiscalização.")
    if item.agenda_event_id and item.status == OversightActionStatus.CONCLUIDA:
        agenda_event = _agenda_event_or_none(item.agenda_event_id, tenant_id)
        if agenda_event:
            _complete_agenda_event(agenda_event, tenant_id)
    after = action_data(item)
    add_audit(
        tenant_id,
        user_id,
        "oversight.action.updated",
        "oversight_action",
        item.id,
        before,
        after,
    )
    db.session.commit()
    return jsonify(after)


@oversight_bp.post("/fiscalizacoes/<uuid:action_id>/evidencias")
@jwt_required()
def create_evidence(action_id: uuid.UUID):
    tenant_id, user_id = _context()
    action = _action_or_none(action_id, tenant_id)
    if action is None:
        return jsonify(error="resource_not_found", message="Fiscalização não encontrada."), 404
    uploaded_file = request.files.get("arquivo")
    if uploaded_file is None:
        return _validation_error("Selecione uma foto ou documento.")
    evidence_type = str(request.form.get("tipo", "DOCUMENTO")).upper()
    if evidence_type not in {"FOTO", "DOCUMENTO"}:
        return _validation_error("Tipo de evidência inválido.")
    evidence_id = uuid.uuid4()
    try:
        stored = store_attachment(tenant_id, evidence_id, uploaded_file)
    except AttachmentError as error:
        return _validation_error(str(error))
    stored["scan_status"] = AttachmentScanStatus.LIMPO
    item = OversightEvidence(
        id=evidence_id,
        tenant_id=tenant_id,
        oversight_action_id=action.id,
        evidence_type=evidence_type,
        observation=str(request.form.get("observacao", "")).strip()[:3000] or None,
        created_by_id=user_id,
        **stored,
    )
    db.session.add(item)
    db.session.flush()
    data = evidence_data(item)
    add_audit(
        tenant_id,
        user_id,
        "oversight.evidence.created",
        "oversight_evidence",
        item.id,
        after=data,
    )
    db.session.commit()
    return jsonify(data), 201


@oversight_bp.patch("/fiscalizacoes/evidencias/<uuid:evidence_id>")
@jwt_required()
def update_evidence(evidence_id: uuid.UUID):
    tenant_id, user_id = _context()
    item = _evidence_or_none(evidence_id, tenant_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Evidência não encontrada."), 404
    before = evidence_data(item)
    payload = request.get_json(silent=True) or {}
    if "observacao" not in payload:
        return _validation_error("Informe a observação da evidência.")
    item.observation = str(payload.get("observacao", "")).strip()[:3000] or None
    after = evidence_data(item)
    add_audit(
        tenant_id,
        user_id,
        "oversight.evidence.updated",
        "oversight_evidence",
        item.id,
        before,
        after,
    )
    db.session.commit()
    return jsonify(after)


@oversight_bp.get("/fiscalizacoes/evidencias/<uuid:evidence_id>/download")
@jwt_required()
def download_evidence(evidence_id: uuid.UUID):
    tenant_id, _ = _context()
    token = str(request.args.get("token", ""))
    if not verify_attachment_token(token, evidence_id, tenant_id):
        return jsonify(error="invalid_token", message="Link de download inválido ou expirado."), 403
    item = _evidence_or_none(evidence_id, tenant_id)
    if item is None or item.scan_status != AttachmentScanStatus.LIMPO:
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


@oversight_bp.get("/fiscalizacoes/<uuid:action_id>/relatorio")
@jwt_required()
def action_report(action_id: uuid.UUID):
    tenant_id, _ = _context()
    item = _action_or_none(action_id, tenant_id)
    if item is None:
        return jsonify(error="resource_not_found", message="Fiscalização não encontrada."), 404
    return jsonify(
        titulo=item.title,
        status=item.status.value,
        local=item.location,
        realizadaEm=item.occurred_at.isoformat() if item.occurred_at else None,
        relatorio=item.report or _generated_report(item),
        achados=item.findings,
        responsaveis=item.responsible_parties,
        providencias=item.follow_up_actions,
        evidencias=_evidence_list(item),
    )


def action_data(item: OversightAction) -> dict:
    service_request = db.session.get(ServiceRequest, item.request_id) if item.request_id else None
    agenda_event = (
        db.session.get(AgendaEvent, item.agenda_event_id) if item.agenda_event_id else None
    )
    return {
        "id": str(item.id),
        "status": item.status.value,
        "titulo": item.title,
        "descricao": item.description,
        "local": item.location,
        "realizadaEm": item.occurred_at.isoformat() if item.occurred_at else None,
        "orgaoId": str(item.agency_id) if item.agency_id else None,
        "solicitacaoId": str(item.request_id) if item.request_id else None,
        "solicitacao": (
            {
                "id": str(service_request.id),
                "protocolo": service_request.protocol,
                "titulo": service_request.title,
            }
            if service_request
            else None
        ),
        "agendaEventoId": str(item.agenda_event_id) if item.agenda_event_id else None,
        "agenda": (
            {
                "inicio": agenda_event.starts_at.isoformat(),
                "participantes": agenda_event.participants,
            }
            if agenda_event
            else None
        ),
        "achados": item.findings,
        "fotos": item.photos,
        "responsaveis": item.responsible_parties,
        "relatorio": item.report,
        "providencias": item.follow_up_actions,
        "evidencias": _evidence_list(item),
        "criadaEm": item.created_at.isoformat(),
    }


def evidence_data(item: OversightEvidence) -> dict:
    author = db.session.get(User, item.created_by_id)
    token = signed_attachment_token(item.id, item.tenant_id)
    return {
        "id": str(item.id),
        "tipo": item.evidence_type,
        "observacao": item.observation,
        "nomeArquivo": item.original_name,
        "mimeType": item.mime_type,
        "tamanho": item.size_bytes,
        "sha256": item.sha256,
        "statusVerificacao": item.scan_status.value,
        "downloadUrl": f"/api/v1/fiscalizacoes/evidencias/{item.id}/download?token={token}",
        "autor": author.name if author else "Usuário removido",
        "criadaEm": item.created_at.isoformat(),
    }


def _evidence_list(action: OversightAction) -> list[dict]:
    items = db.session.execute(
        select(OversightEvidence)
        .where(
            OversightEvidence.tenant_id == action.tenant_id,
            OversightEvidence.oversight_action_id == action.id,
        )
        .order_by(OversightEvidence.created_at.desc())
    ).scalars()
    return [evidence_data(item) for item in items]


def _action_values(payload: dict) -> dict:
    title = str(payload.get("titulo", "")).strip()
    if len(title) < 3:
        raise ValueError("Informe o título da fiscalização.")
    try:
        status = OversightActionStatus(str(payload.get("status", "PLANEJADA")).upper())
    except ValueError as error:
        raise ValueError("Status inválido.") from error
    return {
        "status": status,
        "title": title,
        "description": str(payload.get("descricao", "")).strip() or None,
        "location": str(payload.get("local", "")).strip() or None,
        "occurred_at": _optional_datetime(payload.get("realizadaEm")),
        "findings": _list_value(payload.get("achados", []), "achados"),
        "photos": _list_value(payload.get("fotos", []), "fotos"),
        "responsible_parties": _list_value(payload.get("responsaveis", []), "responsaveis"),
        "report": str(payload.get("relatorio", "")).strip() or None,
        "follow_up_actions": _list_value(payload.get("providencias", []), "providencias"),
    }


def _relationships(payload: dict, tenant_id: uuid.UUID):
    agency = _tenant_entity(ExternalAgency, payload.get("orgaoId"), tenant_id)
    service_request = _tenant_entity(ServiceRequest, payload.get("solicitacaoId"), tenant_id)
    if payload.get("orgaoId") and agency is None:
        return _validation_error("Órgão inválido.")
    if payload.get("solicitacaoId") and service_request is None:
        return _validation_error("Solicitação inválida.")
    return {
        "agency_id": agency.id if agency else None,
        "request_id": service_request.id if service_request else None,
    }


def _complete_agenda_event(event: AgendaEvent, tenant_id: uuid.UUID) -> None:
    event.status = AgendaEventStatus.REALIZADO
    resolve_oversight_reminders(tenant_id, event.id)


def _action_or_none(action_id: uuid.UUID, tenant_id: uuid.UUID) -> OversightAction | None:
    return db.session.execute(
        select(OversightAction).where(
            OversightAction.id == action_id,
            OversightAction.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()


def _evidence_or_none(evidence_id: uuid.UUID, tenant_id: uuid.UUID) -> OversightEvidence | None:
    return db.session.execute(
        select(OversightEvidence).where(
            OversightEvidence.id == evidence_id,
            OversightEvidence.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()


def _agenda_event_or_none(value, tenant_id: uuid.UUID) -> AgendaEvent | None:
    return _tenant_entity(AgendaEvent, value, tenant_id)


def _tenant_entity(model, value, tenant_id: uuid.UUID):
    if not value:
        return None
    try:
        entity_id = uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None
    return db.session.execute(
        select(model).where(
            model.id == entity_id,
            model.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()


def _optional_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Data inválida.") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _list_value(value, label: str) -> list:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError(f"{label} deve ser uma lista.")
    return value


def _validation_error(message: str):
    return jsonify(error="validation_error", message=message), 422


def _generated_report(item: OversightAction) -> str:
    lines = [item.title]
    if item.location:
        lines.append(f"Local: {item.location}")
    if item.findings:
        lines.append("Achados: " + "; ".join(str(value) for value in item.findings))
    if item.follow_up_actions:
        lines.append("Providências: " + "; ".join(str(value) for value in item.follow_up_actions))
    return "\n".join(lines)
