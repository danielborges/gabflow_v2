import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import (
    Citizen,
    NotificationType,
    ResponseTemplate,
    ScheduledReturn,
    ScheduledReturnStatus,
)
from app.notifications.service import notify_user

ALLOWED_CHANNELS = {
    "WHATSAPP",
    "TELEFONE",
    "EMAIL",
    "PRESENCIAL",
    "INTERNO",
    "FORMULARIO",
    "REDE_SOCIAL",
}
ALLOWED_VARIABLES = {"cidadao", "protocolo", "status"}
VARIABLE_PATTERN = re.compile(r"{{\s*([^{}]+?)\s*}}")


class CommunicationValidationError(ValueError):
    pass


def validate_template_body(body: str) -> None:
    variables = {match.strip().lower() for match in VARIABLE_PATTERN.findall(body)}
    invalid = variables - ALLOWED_VARIABLES
    if invalid:
        names = ", ".join(sorted(invalid))
        raise CommunicationValidationError(f"Variáveis não permitidas: {names}.")


def render_template(template: ResponseTemplate, service_request) -> str:
    validate_template_body(template.body)
    citizen = (
        db.session.get(Citizen, service_request.citizen_id)
        if service_request.citizen_id
        else None
    )
    values = {
        "cidadao": citizen.name if citizen else "Cidadão",
        "protocolo": service_request.protocol,
        "status": service_request.status.value.replace("_", " ").title(),
    }

    def replace(match: re.Match) -> str:
        return values[match.group(1).strip().lower()]

    return VARIABLE_PATTERN.sub(replace, template.body)


def generate_return_reminders(tenant_id: uuid.UUID, user_id: uuid.UUID) -> int:
    return generate_due_return_reminders(tenant_id=tenant_id, user_id=user_id)


def generate_due_return_reminders(
    *,
    tenant_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    limit: int = 100,
) -> int:
    now = datetime.now(UTC)
    statement = (
        select(ScheduledReturn)
        .where(
            ScheduledReturn.status == ScheduledReturnStatus.AGENDADO,
            ScheduledReturn.reminder_enabled.is_(True),
            ScheduledReturn.reminder_sent_at.is_(None),
        )
        .order_by(ScheduledReturn.scheduled_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    if tenant_id is not None:
        statement = statement.where(ScheduledReturn.tenant_id == tenant_id)
    if user_id is not None:
        statement = statement.where(ScheduledReturn.assignee_id == user_id)
    returns = db.session.execute(statement).scalars()
    generated = 0
    for item in returns:
        scheduled_at = (
            item.scheduled_at
            if item.scheduled_at.tzinfo
            else item.scheduled_at.replace(tzinfo=UTC)
        )
        if now < scheduled_at - timedelta(minutes=item.reminder_minutes):
            continue
        notify_user(
            item.tenant_id,
            item.assignee_id,
            NotificationType.RETORNO,
            "Retorno pendente",
            f"O retorno da solicitação {item.request.protocol} está próximo ou vencido.",
            "scheduled_return",
            item.id,
        )
        item.reminder_sent_at = now
        generated += 1
    return generated


def template_data(item: ResponseTemplate) -> dict:
    return {
        "id": str(item.id),
        "nome": item.name,
        "canal": item.channel,
        "categoriaId": str(item.category_id) if item.category_id else None,
        "categoria": item.category.name if item.category else None,
        "assunto": item.subject,
        "conteudo": item.body,
        "ativa": item.active,
        "versao": item.version,
        "criadaEm": item.created_at.isoformat(),
        "atualizadaEm": item.updated_at.isoformat(),
    }


def scheduled_return_data(item: ScheduledReturn) -> dict:
    return {
        "id": str(item.id),
        "solicitacaoId": str(item.request_id),
        "responsavelId": str(item.assignee_id),
        "responsavel": item.assignee.name,
        "agendadoPara": item.scheduled_at.isoformat(),
        "status": item.status.value,
        "observacoes": item.notes,
        "lembreteHabilitado": item.reminder_enabled,
        "lembreteMinutos": item.reminder_minutes,
        "lembreteEnviadoEm": (
            item.reminder_sent_at.isoformat() if item.reminder_sent_at else None
        ),
        "concluidoEm": item.completed_at.isoformat() if item.completed_at else None,
        "criadoEm": item.created_at.isoformat(),
        "atualizadoEm": item.updated_at.isoformat(),
    }
