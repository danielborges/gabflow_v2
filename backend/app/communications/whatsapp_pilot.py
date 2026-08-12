import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from flask import current_app
from sqlalchemy import func, select

from app.extensions import db
from app.models import (
    OutboxEvent,
    WhatsAppContact,
    WhatsAppContactOptStatus,
    WhatsAppConversationState,
    WhatsAppConversationTransition,
    WhatsAppIntegration,
    WhatsAppIntegrationStatus,
    WhatsAppMediaAsset,
    WhatsAppMessage,
    WhatsAppMessageDirection,
    WhatsAppMessageStatus,
    WhatsAppPilotControl,
    WhatsAppPilotGate,
    WhatsAppWebhookEvent,
    WhatsAppWebhookEventStatus,
)
from app.observability import percentile

PILOT_GATES = (
    ("MULTITENANT_NEGATIVE_TESTS", "Testes negativos multi-tenant"),
    ("OPT_OUT_HANDOFF_CONTINGENCY", "Opt-out, handoff e contingência sem IA"),
    ("FLOWS_TEMPLATES_PRODUCTION", "Flows e templates aprovados"),
    ("OBSERVABILITY_ALERTS_DLQ", "Dashboards, alertas e DLQ"),
    ("RUNBOOKS_INCIDENTS", "Runbooks e resposta a incidentes"),
    ("BACKUP_RESTORE", "Backup e restore testados"),
    ("OFFICE_TRAINING_SUPPORT", "Treinamento e canal de suporte"),
    ("ROLLBACK_DISCONNECT", "Rollback e desconexão validados"),
)
WHATSAPP_OUTBOX_TYPES = {
    "ProcessarWebhookWhatsApp",
    "DownloadWhatsappMediaRequested",
    "AnalyzeWhatsappMediaRequested",
    "SendWhatsappMessageRequested",
    "SyncWhatsappTemplateRequested",
    "WhatsappFlowLaunchRequested",
    "WhatsappPrivacyNoticeRequested",
    "WhatsappProtocolCreated",
}


class WhatsAppPilotError(ValueError):
    pass


def operations_snapshot(tenant_id: uuid.UUID | None, *, window_hours: int | None = None) -> dict:
    hours = max(1, min(window_hours or current_app.config["WHATSAPP_METRICS_WINDOW_HOURS"], 720))
    now = datetime.now(UTC)
    since = now - timedelta(hours=hours)
    webhook_filters = [WhatsAppWebhookEvent.received_at >= since]
    outbox_filters = [
        OutboxEvent.event_type.in_(WHATSAPP_OUTBOX_TYPES),
        OutboxEvent.occurred_at >= since,
    ]
    message_filters = [
        WhatsAppMessage.direction == WhatsAppMessageDirection.OUTBOUND,
        WhatsAppMessage.occurred_at >= since,
    ]
    if tenant_id is not None:
        webhook_filters.append(WhatsAppWebhookEvent.tenant_id == tenant_id)
        outbox_filters.append(OutboxEvent.tenant_id == tenant_id)
        message_filters.append(WhatsAppMessage.tenant_id == tenant_id)

    webhooks = list(
        db.session.scalars(
            select(WhatsAppWebhookEvent)
            .where(*webhook_filters)
            .order_by(WhatsAppWebhookEvent.received_at.desc())
            .limit(10000)
        )
    )
    outbox = list(
        db.session.scalars(
            select(OutboxEvent)
            .where(*outbox_filters)
            .order_by(OutboxEvent.occurred_at.desc())
            .limit(10000)
        )
    )
    messages = list(
        db.session.scalars(
            select(WhatsAppMessage)
            .where(*message_filters)
            .order_by(WhatsAppMessage.occurred_at.desc())
            .limit(10000)
        )
    )
    received = len(webhooks)
    processed = sum(item.status == WhatsAppWebhookEventStatus.PROCESSED for item in webhooks)
    failed = sum(item.status == WhatsAppWebhookEventStatus.FAILED for item in webhooks)
    quarantined = sum(item.status == WhatsAppWebhookEventStatus.QUARANTINED for item in webhooks)
    ack_values = [item.ack_duration_ms for item in webhooks if item.ack_duration_ms is not None]
    processing_delays = [
        max(0, int((_utc(item.processing_started_at) - _utc(item.received_at)).total_seconds()))
        for item in webhooks
        if item.processing_started_at is not None
    ]
    within_30 = sum(value <= 30 for value in processing_delays)
    availability = _rate(processed, processed + failed)
    start_rate = _rate(within_30, len(processing_delays))
    pending = [item for item in outbox if item.published_at is None and item.failed_at is None]
    outbox_failed = sum(item.failed_at is not None for item in outbox)
    oldest_age = max(
        [max(0, int((now - _utc(item.occurred_at)).total_seconds())) for item in pending] or [0]
    )
    sent_total = len(messages)
    delivery_failed = sum(item.status == WhatsAppMessageStatus.FAILED for item in messages)
    delivered = sum(
        item.status in {WhatsAppMessageStatus.DELIVERED, WhatsAppMessageStatus.READ}
        for item in messages
    )
    media_blocked_query = select(func.count(WhatsAppMediaAsset.id)).where(
        WhatsAppMediaAsset.created_at >= since,
        WhatsAppMediaAsset.status == "BLOCKED",
    )
    opt_out_query = select(func.count(WhatsAppContact.id)).where(
        WhatsAppContact.opt_status == WhatsAppContactOptStatus.OPTED_OUT,
        WhatsAppContact.opted_out_at >= since,
    )
    handoff_query = select(func.count(WhatsAppConversationTransition.id)).where(
        WhatsAppConversationTransition.occurred_at >= since,
        WhatsAppConversationTransition.to_state == WhatsAppConversationState.HUMAN_HANDOFF,
    )
    integration_issue_query = select(func.count(WhatsAppIntegration.id)).where(
        WhatsAppIntegration.status.in_(
            {
                WhatsAppIntegrationStatus.DEGRADED,
                WhatsAppIntegrationStatus.SUSPENDED,
                WhatsAppIntegrationStatus.REVOKED,
            }
        )
    )
    if tenant_id is not None:
        media_blocked_query = media_blocked_query.where(WhatsAppMediaAsset.tenant_id == tenant_id)
        opt_out_query = opt_out_query.where(WhatsAppContact.tenant_id == tenant_id)
        handoff_query = handoff_query.where(WhatsAppConversationTransition.tenant_id == tenant_id)
        integration_issue_query = integration_issue_query.where(
            WhatsAppIntegration.tenant_id == tenant_id
        )

    integration_issues = db.session.scalar(integration_issue_query) or 0

    ack_p95 = percentile(ack_values, 0.95)
    slo = {
        "availabilityTarget": current_app.config["WHATSAPP_SLO_AVAILABILITY"],
        "ackP95TargetMs": current_app.config["WHATSAPP_SLO_ACK_P95_MS"],
        "processingStartTargetSeconds": current_app.config["WHATSAPP_SLO_PROCESSING_START_SECONDS"],
        "processingStartTargetRate": current_app.config["WHATSAPP_SLO_PROCESSING_START_RATE"],
        "outboxOldestTargetSeconds": current_app.config["WHATSAPP_SLO_OUTBOX_MAX_AGE_SECONDS"],
    }
    alerts = _alerts(
        received=received,
        failed=failed,
        quarantined=quarantined,
        availability=availability,
        ack_p95=ack_p95,
        start_rate=start_rate,
        outbox_failed=outbox_failed,
        oldest_age=oldest_age,
        delivery_failed=delivery_failed,
        integration_issues=integration_issues,
        slo=slo,
    )
    return {
        "status": "PROBLEM"
        if any(item["nivel"] == "PROBLEM" for item in alerts)
        else ("WARNING" if any(item["nivel"] == "WARNING" for item in alerts) else "GOOD"),
        "windowHours": hours,
        "generatedAt": now.isoformat(),
        "inbound": {
            "received": received,
            "processed": processed,
            "failed": failed,
            "quarantined": quarantined,
            "availability": availability,
            "ackP95Ms": ack_p95,
            "processingStartWithinTargetRate": start_rate,
        },
        "outbox": {
            "pending": len(pending),
            "failed": outbox_failed,
            "oldestAgeSeconds": oldest_age,
        },
        "outbound": {
            "total": sent_total,
            "deliveredOrRead": delivered,
            "failed": delivery_failed,
            "deliveryRate": _rate(delivered, sent_total),
        },
        "operation": {
            "optOuts": db.session.scalar(opt_out_query) or 0,
            "handoffs": db.session.scalar(handoff_query) or 0,
            "mediaBlocked": db.session.scalar(media_blocked_query) or 0,
            "integrationIssues": integration_issues,
        },
        "slo": slo,
        "alerts": alerts,
    }


def pilot_data(tenant_id: uuid.UUID, *, readiness: dict) -> dict:
    now = datetime.now(UTC)
    stored = {
        item.gate_key: item
        for item in db.session.scalars(
            select(WhatsAppPilotGate).where(WhatsAppPilotGate.tenant_id == tenant_id)
        )
    }
    gates = []
    for key, title in PILOT_GATES:
        item = stored.get(key)
        expired = bool(item and item.expires_at and _utc(item.expires_at) <= now)
        status = "PENDING" if item is None or expired else item.status
        gates.append(
            {
                "key": key,
                "titulo": title,
                "status": status,
                "evidenciaReferencia": item.evidence_reference if item else None,
                "evidenciaHash": item.evidence_hash if item else None,
                "observacao": item.notes if item else None,
                "revisadaEm": item.reviewed_at.isoformat() if item and item.reviewed_at else None,
                "expiraEm": item.expires_at.isoformat() if item and item.expires_at else None,
                "expirada": expired,
            }
        )
    control = db.session.scalar(
        select(WhatsAppPilotControl).where(WhatsAppPilotControl.tenant_id == tenant_id)
    )
    snapshot = operations_snapshot(tenant_id)
    internal_ready = all(item["status"] == "PASSED" for item in gates)
    operational_ready = snapshot["status"] != "PROBLEM"
    stored_status = control.status if control else "DRAFT"
    effective_status = (
        "READY"
        if stored_status == "DRAFT" and internal_ready and operational_ready
        else stored_status
    )
    return {
        "status": effective_status,
        "saidasPausadas": control.outbound_paused if control else False,
        "motivoPausa": control.pause_reason if control else None,
        "iniciadoEm": control.pilot_started_at.isoformat()
        if control and control.pilot_started_at
        else None,
        "concluidoEm": control.pilot_completed_at.isoformat()
        if control and control.pilot_completed_at
        else None,
        "prontoExterno": bool(readiness["prontoPiloto"]),
        "prontoInterno": internal_ready,
        "prontoOperacional": operational_ready,
        "podeIniciar": bool(readiness["prontoPiloto"] and internal_ready and operational_ready),
        "gates": gates,
        "operacao": snapshot,
    }


def review_gate(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    gate_key: str,
    *,
    status: str,
    evidence_reference: str | None,
    notes: str | None,
    expires_at: datetime | None,
) -> WhatsAppPilotGate:
    valid_keys = {key for key, _ in PILOT_GATES}
    clean_key = str(gate_key or "").upper()
    clean_status = str(status or "").upper()
    evidence = str(evidence_reference or "").strip()[:500] or None
    if clean_key not in valid_keys or clean_status not in {"PENDING", "PASSED", "FAILED"}:
        raise WhatsAppPilotError("Gate ou status inválido.")
    if clean_status == "PASSED" and not evidence:
        raise WhatsAppPilotError("Informe uma referência de evidência para aprovar o gate.")
    item = db.session.scalar(
        select(WhatsAppPilotGate).where(
            WhatsAppPilotGate.tenant_id == tenant_id,
            WhatsAppPilotGate.gate_key == clean_key,
        )
    )
    if item is None:
        item = WhatsAppPilotGate(
            tenant_id=tenant_id,
            gate_key=clean_key,
            reviewed_by_id=actor_id,
        )
        db.session.add(item)
    item.status = clean_status
    item.evidence_reference = evidence
    item.evidence_hash = hashlib.sha256(evidence.encode()).hexdigest() if evidence else None
    item.notes = str(notes or "").strip()[:500] or None
    item.reviewed_by_id = actor_id
    item.reviewed_at = datetime.now(UTC)
    item.expires_at = expires_at
    return item


def change_pilot_status(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    *,
    action: str,
    reason: str | None,
    readiness: dict,
) -> WhatsAppPilotControl:
    clean_action = str(action or "").upper()
    control = db.session.scalar(
        select(WhatsAppPilotControl).where(WhatsAppPilotControl.tenant_id == tenant_id)
    )
    if control is None:
        control = WhatsAppPilotControl(tenant_id=tenant_id, updated_by_id=actor_id)
        db.session.add(control)
        db.session.flush()
    if clean_action in {"START", "RESUME"}:
        state = pilot_data(tenant_id, readiness=readiness)
        if not state["podeIniciar"]:
            raise WhatsAppPilotError(
                "Os gates externos, internos e operacionais devem estar aprovados."
            )
        control.status = "RUNNING"
        control.outbound_paused = False
        control.pause_reason = None
        control.pilot_started_at = control.pilot_started_at or datetime.now(UTC)
    elif clean_action == "PAUSE":
        clean_reason = str(reason or "").strip()
        if not clean_reason:
            raise WhatsAppPilotError("Informe o motivo da pausa operacional.")
        control.status = "PAUSED"
        control.outbound_paused = True
        control.pause_reason = clean_reason[:500]
    elif clean_action == "COMPLETE":
        if control.status != "RUNNING":
            raise WhatsAppPilotError("Somente um piloto em execução pode ser concluído.")
        control.status = "COMPLETED"
        control.outbound_paused = True
        control.pause_reason = "Piloto concluído; saída aguardando decisão de rollout."
        control.pilot_completed_at = datetime.now(UTC)
    else:
        raise WhatsAppPilotError("Ação de piloto inválida.")
    control.updated_by_id = actor_id
    return control


def outbound_is_paused(tenant_id: uuid.UUID) -> bool:
    return bool(
        db.session.scalar(
            select(WhatsAppPilotControl.outbound_paused).where(
                WhatsAppPilotControl.tenant_id == tenant_id
            )
        )
    )


def _alerts(**values) -> list[dict]:
    alerts = []
    slo = values["slo"]
    if values["failed"] or values["outbox_failed"]:
        alerts.append(
            {
                "nivel": "PROBLEM",
                "codigo": "PROCESSING_FAILURE",
                "titulo": "Falhas exigem tratamento",
                "valor": values["failed"] + values["outbox_failed"],
            }
        )
    if values["integration_issues"]:
        alerts.append(
            {
                "nivel": "PROBLEM",
                "codigo": "INTEGRATION_DEGRADED",
                "titulo": "Integração suspensa, revogada ou degradada",
                "valor": values["integration_issues"],
            }
        )
    if values["oldest_age"] > slo["outboxOldestTargetSeconds"]:
        alerts.append(
            {
                "nivel": "PROBLEM",
                "codigo": "OUTBOX_DELAY",
                "titulo": "Fila acima do tempo-alvo",
                "valor": values["oldest_age"],
            }
        )
    if values["availability"] is not None and values["availability"] < slo["availabilityTarget"]:
        alerts.append(
            {
                "nivel": "WARNING",
                "codigo": "AVAILABILITY_SLO",
                "titulo": "Disponibilidade abaixo do SLO",
                "valor": values["availability"],
            }
        )
    if values["ack_p95"] is not None and values["ack_p95"] >= slo["ackP95TargetMs"]:
        alerts.append(
            {
                "nivel": "WARNING",
                "codigo": "ACK_LATENCY",
                "titulo": "ACK p95 próximo ou acima do limite",
                "valor": values["ack_p95"],
            }
        )
    if values["start_rate"] is not None and values["start_rate"] < slo["processingStartTargetRate"]:
        alerts.append(
            {
                "nivel": "WARNING",
                "codigo": "PROCESSING_START_SLO",
                "titulo": "Início do processamento abaixo do alvo",
                "valor": values["start_rate"],
            }
        )
    if values["quarantined"]:
        alerts.append(
            {
                "nivel": "WARNING",
                "codigo": "QUARANTINED_EVENTS",
                "titulo": "Eventos em quarentena",
                "valor": values["quarantined"],
            }
        )
    if values["delivery_failed"]:
        alerts.append(
            {
                "nivel": "WARNING",
                "codigo": "DELIVERY_FAILURE",
                "titulo": "Falhas de entrega",
                "valor": values["delivery_failed"],
            }
        )
    if not alerts:
        alerts.append(
            {
                "nivel": "GOOD",
                "codigo": "PIPELINE_HEALTHY",
                "titulo": "Pipeline dentro dos limites observados",
                "valor": values["received"],
            }
        )
    return alerts


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
