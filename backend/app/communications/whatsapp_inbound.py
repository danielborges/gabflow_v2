import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from flask import current_app
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.audit import add_audit
from app.communications.identity import prepare_identity_review
from app.communications.whatsapp import extract_whatsapp_messages
from app.communications.whatsapp_conversations import (
    record_inbound_conversation_message,
    record_provider_message_status,
)
from app.communications.whatsapp_flows import process_flow_reply
from app.communications.whatsapp_media import register_inbound_media
from app.extensions import db
from app.models import (
    ChannelMessage,
    ChannelMessageStatus,
    OutboxEvent,
    RequestSource,
    WhatsAppContact,
    WhatsAppIntegration,
    WhatsAppIntegrationStatus,
    WhatsAppMessage,
    WhatsAppWebhookEvent,
    WhatsAppWebhookEventStatus,
)

WHATSAPP_INBOUND_EVENT = "ProcessarWebhookWhatsApp"
SUPPORTED_EVENT_TYPES = {"message", "message_status"}


@dataclass(frozen=True)
class IngestResult:
    accepted: int
    duplicated: int
    quarantined: int
    event_ids: tuple[uuid.UUID, ...]
    persisted_event_ids: tuple[uuid.UUID, ...]


def ingest_meta_webhook(payload: dict, *, correlation_id: str) -> IngestResult:
    logical_events = extract_logical_events(payload)
    accepted = duplicated = quarantined = 0
    pending_ids: list[uuid.UUID] = []
    persisted_ids: list[uuid.UUID] = []
    retention_until = datetime.now(UTC) + timedelta(
        days=current_app.config["WHATSAPP_WEBHOOK_PAYLOAD_RETENTION_DAYS"]
    )
    queue_backend = current_app.config["WHATSAPP_INBOUND_QUEUE_BACKEND"]

    for logical_event in logical_events:
        integration = resolve_active_integration(logical_event["phoneNumberId"])
        status = WhatsAppWebhookEventStatus.RECEIVED
        quarantine_reason = None
        if integration is None:
            status = WhatsAppWebhookEventStatus.QUARANTINED
            quarantine_reason = "UNKNOWN_OR_INACTIVE_PHONE_NUMBER"

        event = WhatsAppWebhookEvent(
            provider_event_key=logical_event["providerEventKey"],
            correlation_id=correlation_id,
            tenant_id=integration.tenant_id if integration else None,
            integration_id=integration.id if integration else None,
            phone_number_id=logical_event["phoneNumberId"],
            provider_message_id=logical_event.get("providerMessageId"),
            event_type=logical_event["eventType"],
            payload_hash=logical_event["payloadHash"],
            payload=logical_event["payload"],
            status=status,
            quarantine_reason=quarantine_reason,
            retention_until=retention_until,
        )
        try:
            with db.session.begin_nested():
                db.session.add(event)
                db.session.flush()
        except IntegrityError:
            duplicated += 1
            continue

        accepted += 1
        persisted_ids.append(event.id)
        if status == WhatsAppWebhookEventStatus.QUARANTINED:
            quarantined += 1
            current_app.logger.warning(
                "WhatsApp webhook quarantined",
                extra={
                    "correlation_id": correlation_id,
                    "event_id": str(event.id),
                    "reason": quarantine_reason,
                },
            )
            continue

        if queue_backend == "database":
            db.session.add(_outbox_event(event))
            event.status = WhatsAppWebhookEventStatus.QUEUED
            event.queued_at = datetime.now(UTC)
        else:
            pending_ids.append(event.id)

    db.session.commit()
    return IngestResult(
        accepted,
        duplicated,
        quarantined,
        tuple(pending_ids),
        tuple(persisted_ids),
    )


def extract_logical_events(payload: dict) -> list[dict]:
    if payload.get("object") != "whatsapp_business_account":
        return []

    result: list[dict] = []
    for message in extract_whatsapp_messages(payload):
        normalized = {
            "id": message["id"],
            "from": message.get("from"),
            "senderName": message.get("senderName"),
            "type": message.get("type") or "unknown",
            "timestamp": message.get("timestamp"),
            "content": message.get("content"),
            "phoneNumberId": str(message.get("phoneNumberId") or "").strip(),
            "displayPhoneNumber": message.get("displayPhoneNumber"),
            "flowReply": message.get("flowReply"),
            "media": message.get("media"),
        }
        result.append(
            _logical_event(
                event_type="message",
                provider_event_key=f"meta:{message['id']}:message",
                phone_number_id=normalized["phoneNumberId"],
                provider_message_id=message["id"],
                payload=normalized,
            )
        )

    for status in _extract_statuses(payload):
        timestamp = str(status.get("timestamp") or "")
        status_name = str(status.get("status") or "unknown")
        result.append(
            _logical_event(
                event_type="message_status",
                provider_event_key=(f"meta:{status['id']}:status:{status_name}:{timestamp}"),
                phone_number_id=status["phoneNumberId"],
                provider_message_id=status["id"],
                payload=status,
            )
        )
    return result


def process_webhook_event(event_id: uuid.UUID, *, receive_count: int = 1) -> None:
    event = db.session.execute(
        select(WhatsAppWebhookEvent).where(WhatsAppWebhookEvent.id == event_id).with_for_update()
    ).scalar_one_or_none()
    if event is None:
        return
    if event.status in {
        WhatsAppWebhookEventStatus.PROCESSED,
        WhatsAppWebhookEventStatus.QUARANTINED,
    }:
        return
    if event.tenant_id is None or event.integration_id is None:
        event.status = WhatsAppWebhookEventStatus.QUARANTINED
        event.quarantine_reason = "MISSING_TENANT_ROUTE"
        event.processed_at = datetime.now(UTC)
        return

    integration = db.session.execute(
        select(WhatsAppIntegration).where(
            WhatsAppIntegration.id == event.integration_id,
            WhatsAppIntegration.tenant_id == event.tenant_id,
            WhatsAppIntegration.phone_number_id == event.phone_number_id,
            WhatsAppIntegration.status == WhatsAppIntegrationStatus.ACTIVE,
        )
    ).scalar_one_or_none()
    if integration is None:
        event.status = WhatsAppWebhookEventStatus.QUARANTINED
        event.quarantine_reason = "ROUTE_BECAME_INACTIVE"
        event.processed_at = datetime.now(UTC)
        return

    event.status = WhatsAppWebhookEventStatus.PROCESSING
    event.last_error_code = None
    event.processing_started_at = datetime.now(UTC)
    event.attempts = max(event.attempts, receive_count)
    if event.event_type == "message":
        _process_message(event, integration)
    elif event.event_type == "message_status":
        record_provider_message_status(event)
    elif event.event_type not in SUPPORTED_EVENT_TYPES:
        raise ValueError("Tipo de evento WhatsApp nao suportado.")

    event.status = WhatsAppWebhookEventStatus.PROCESSED
    event.processed_at = datetime.now(UTC)


def mark_webhook_queued(event_id: uuid.UUID) -> None:
    event = db.session.get(WhatsAppWebhookEvent, event_id)
    if event is None or event.status != WhatsAppWebhookEventStatus.RECEIVED:
        return
    event.status = WhatsAppWebhookEventStatus.QUEUED
    event.queued_at = datetime.now(UTC)


def mark_webhook_failure(event_id: uuid.UUID, *, receive_count: int, exhausted: bool) -> None:
    event = db.session.get(WhatsAppWebhookEvent, event_id)
    if event is None:
        return
    event.attempts = max(event.attempts, receive_count)
    event.last_error_code = "PROCESSING_FAILED"
    event.status = (
        WhatsAppWebhookEventStatus.FAILED if exhausted else WhatsAppWebhookEventStatus.QUEUED
    )


def pending_webhook_event_ids(limit: int) -> list[uuid.UUID]:
    return list(
        db.session.scalars(
            select(WhatsAppWebhookEvent.id)
            .where(WhatsAppWebhookEvent.status == WhatsAppWebhookEventStatus.RECEIVED)
            .order_by(WhatsAppWebhookEvent.received_at, WhatsAppWebhookEvent.id)
            .limit(limit)
        )
    )


def redact_expired_webhook_payloads(*, limit: int = 500) -> int:
    now = datetime.now(UTC)
    events = list(
        db.session.scalars(
            select(WhatsAppWebhookEvent)
            .where(
                WhatsAppWebhookEvent.retention_until <= now,
                WhatsAppWebhookEvent.payload_redacted_at.is_(None),
            )
            .order_by(WhatsAppWebhookEvent.retention_until, WhatsAppWebhookEvent.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    for event in events:
        event.payload = {}
        event.payload_redacted_at = now
    return len(events)


def resolve_active_integration(phone_number_id: str) -> WhatsAppIntegration | None:
    if not phone_number_id:
        return None
    return db.session.execute(
        select(WhatsAppIntegration).where(
            WhatsAppIntegration.phone_number_id == phone_number_id,
            WhatsAppIntegration.status == WhatsAppIntegrationStatus.ACTIVE,
        )
    ).scalar_one_or_none()


def _process_message(event: WhatsAppWebhookEvent, integration: WhatsAppIntegration) -> None:
    existing = db.session.execute(
        select(ChannelMessage).where(
            ChannelMessage.tenant_id == event.tenant_id,
            ChannelMessage.channel == RequestSource.WHATSAPP,
            ChannelMessage.external_id == event.provider_message_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    payload = event.payload
    message = ChannelMessage(
        tenant_id=event.tenant_id,
        channel=RequestSource.WHATSAPP,
        status=ChannelMessageStatus.RECEBIDA,
        sender_name=payload.get("senderName"),
        sender_contact=payload.get("from"),
        subject="WhatsApp Business",
        content=str(payload.get("content") or ""),
        external_id=event.provider_message_id,
        metadata_data={
            "provider": "meta_whatsapp_cloud_api",
            "messageType": payload.get("type"),
            "phoneNumberId": event.phone_number_id,
            "displayPhoneNumber": payload.get("displayPhoneNumber"),
            "timestamp": payload.get("timestamp"),
            "webhookEventId": str(event.id),
            "correlationId": event.correlation_id,
        },
    )
    db.session.add(message)
    db.session.flush()
    prepare_identity_review(message)
    conversation = record_inbound_conversation_message(
        webhook_event=event,
        integration=integration,
        channel_message=message,
    )
    if isinstance(payload.get("media"), dict):
        db.session.flush()
        whatsapp_message = db.session.execute(
            select(WhatsAppMessage).where(
                WhatsAppMessage.tenant_id == event.tenant_id,
                WhatsAppMessage.provider_message_id == event.provider_message_id,
            )
        ).scalar_one()
        register_inbound_media(
            webhook_event=event,
            integration=integration,
            conversation=conversation,
            message=whatsapp_message,
            media=payload["media"],
        )
    if isinstance(payload.get("flowReply"), dict):
        contact = db.session.execute(
            select(WhatsAppContact).where(
                WhatsAppContact.tenant_id == event.tenant_id,
                WhatsAppContact.id == conversation.contact_id,
            )
        ).scalar_one()
        process_flow_reply(
            webhook_event=event,
            conversation=conversation,
            contact=contact,
            flow_reply=payload["flowReply"],
            actor_id=integration.created_by_id,
        )
    add_audit(
        event.tenant_id,
        None,
        "channel.whatsapp.meta.received",
        "channel_message",
        message.id,
        after={
            "canal": RequestSource.WHATSAPP.value,
            "idExterno": message.external_id,
            "webhookEventId": str(event.id),
        },
    )


def _logical_event(
    *,
    event_type: str,
    provider_event_key: str,
    phone_number_id: str,
    provider_message_id: str,
    payload: dict,
) -> dict:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {
        "eventType": event_type,
        "providerEventKey": provider_event_key,
        "phoneNumberId": phone_number_id,
        "providerMessageId": provider_message_id,
        "payload": payload,
        "payloadHash": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
    }


def _extract_statuses(payload: dict) -> list[dict]:
    statuses: list[dict] = []
    for entry in payload.get("entry", []):
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes", []):
            if not isinstance(change, dict):
                continue
            value = change.get("value") if isinstance(change.get("value"), dict) else {}
            metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
            phone_number_id = str(metadata.get("phone_number_id") or "").strip()
            for status in value.get("statuses", []):
                if not isinstance(status, dict) or not status.get("id"):
                    continue
                statuses.append(
                    {
                        "id": str(status["id"]),
                        "status": str(status.get("status") or "unknown"),
                        "timestamp": status.get("timestamp"),
                        "recipientId": status.get("recipient_id"),
                        "phoneNumberId": phone_number_id,
                        "errorCodes": [
                            str(error.get("code"))
                            for error in status.get("errors", [])
                            if isinstance(error, dict) and error.get("code") is not None
                        ],
                    }
                )
    return statuses


def _outbox_event(event: WhatsAppWebhookEvent) -> OutboxEvent:
    return OutboxEvent(
        tenant_id=event.tenant_id,
        event_type=WHATSAPP_INBOUND_EVENT,
        aggregate_type="whatsapp_webhook_event",
        aggregate_id=str(event.id),
        payload={"webhookEventId": str(event.id), "correlationId": event.correlation_id},
    )
