import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.extensions import db
from app.models import (
    AuditLog,
    Citizen,
    ConsentRecord,
    PrivacyRequest,
    RetentionPolicy,
    ServiceRequest,
)


def record_consent(
    *,
    tenant_id: uuid.UUID,
    citizen_id: uuid.UUID,
    user_id: uuid.UUID,
    purpose: str,
    granted: bool,
    legal_basis: str,
    source: str = "ATENDIMENTO",
    evidence: str | None = None,
) -> ConsentRecord:
    item = ConsentRecord(
        tenant_id=tenant_id,
        citizen_id=citizen_id,
        recorded_by_id=user_id,
        purpose=purpose,
        granted=granted,
        legal_basis=legal_basis,
        source=source,
        evidence=evidence,
    )
    db.session.add(item)
    return item


def consent_data(item: ConsentRecord) -> dict:
    return {
        "id": str(item.id),
        "finalidade": item.purpose,
        "concedido": item.granted,
        "baseLegal": item.legal_basis,
        "origem": item.source,
        "evidencia": item.evidence,
        "registradoPor": item.recorded_by.name,
        "registradoEm": item.recorded_at.isoformat(),
    }


def privacy_request_data(item: PrivacyRequest) -> dict:
    now = datetime.now(UTC)
    due_at = item.due_at if item.due_at.tzinfo else item.due_at.replace(tzinfo=UTC)
    return {
        "id": str(item.id),
        "cidadaoId": str(item.citizen_id),
        "cidadao": item.citizen.name,
        "tipo": item.request_type.value,
        "status": item.status.value,
        "identidadeValidada": item.identity_validated,
        "detalhes": item.details,
        "resolucao": item.resolution,
        "prazo": item.due_at.isoformat(),
        "vencida": item.completed_at is None and due_at < now,
        "responsavelId": str(item.assigned_to_id) if item.assigned_to_id else None,
        "responsavel": item.assigned_to.name if item.assigned_to else None,
        "concluidaEm": item.completed_at.isoformat() if item.completed_at else None,
        "criadaEm": item.created_at.isoformat(),
        "atualizadaEm": item.updated_at.isoformat(),
    }


def retention_policy_data(item: RetentionPolicy) -> dict:
    return {
        "id": str(item.id),
        "tipoDado": item.data_type,
        "retencaoDias": item.retention_days,
        "acao": item.action.value,
        "ativa": item.active,
        "atualizadaEm": item.updated_at.isoformat(),
    }


def citizen_export(citizen: Citizen) -> dict:
    requests = list(
        db.session.execute(
            select(ServiceRequest)
            .where(
                ServiceRequest.tenant_id == citizen.tenant_id,
                ServiceRequest.citizen_id == citizen.id,
            )
            .order_by(ServiceRequest.created_at)
        ).scalars()
    )
    audits = list(
        db.session.execute(
            select(AuditLog)
            .where(
                AuditLog.tenant_id == citizen.tenant_id,
                AuditLog.entity_type == "citizen",
                AuditLog.entity_id == str(citizen.id),
            )
            .order_by(AuditLog.created_at)
        ).scalars()
    )
    return {
        "geradoEm": datetime.now(UTC).isoformat(),
        "titular": {
            "id": str(citizen.id),
            "nome": citizen.name,
            "nomeSocial": citizen.social_name,
            "contatos": citizen.contacts,
            "enderecos": citizen.addresses,
            "canalPreferencial": citizen.preferred_channel,
            "baseLegal": citizen.legal_basis,
            "consentimentoContato": citizen.contact_consent,
            "consentimentoDivulgacao": citizen.publication_consent,
            "flagsPrivacidade": citizen.privacy_flags,
            "criadoEm": citizen.created_at.isoformat(),
            "atualizadoEm": citizen.updated_at.isoformat(),
        },
        "consentimentos": [consent_data(item) for item in citizen.consent_records],
        "solicitacoes": [
            {
                "protocolo": item.protocol,
                "titulo": item.title,
                "descricao": item.description,
                "status": item.status.value,
                "origem": item.source.value,
                "criadaEm": item.created_at.isoformat(),
                "interacoes": [
                    {
                        "tipo": interaction.interaction_type,
                        "canal": interaction.channel,
                        "direcao": interaction.direction.value,
                        "conteudo": interaction.content,
                        "criadaEm": interaction.created_at.isoformat(),
                    }
                    for interaction in item.interactions
                    if interaction.visibility.value == "CIDADAO"
                ],
            }
            for item in requests
        ],
        "historicoCorrecoes": [
            {
                "acao": item.action,
                "antes": item.before,
                "depois": item.after,
                "criadaEm": item.created_at.isoformat(),
            }
            for item in audits
        ],
    }
