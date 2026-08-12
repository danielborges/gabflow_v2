import json
import uuid
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from flask import current_app

from app.communications.whatsapp_inbound import (
    mark_webhook_failure,
    mark_webhook_queued,
    pending_webhook_event_ids,
    process_webhook_event,
)
from app.extensions import db
from app.models import WhatsAppWebhookEvent
from app.tenant_context import tenant_context


class WhatsAppQueueUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class QueueProcessingResult:
    received: int = 0
    succeeded: int = 0
    retried: int = 0
    discarded: int = 0


class AWSWhatsAppInboundQueue:
    def __init__(self, config: dict, client: Any | None = None):
        self.queue_url = str(config.get("WHATSAPP_AWS_SQS_QUEUE_URL") or "").strip()
        if not self.queue_url.startswith("https://"):
            raise WhatsAppQueueUnavailable("URL da fila SQS do WhatsApp nao configurada.")
        self.max_receive_count = int(config.get("WHATSAPP_AWS_SQS_MAX_RECEIVE_COUNT") or 5)
        region = str(config.get("AWS_REGION") or "sa-east-1")
        self.client = client or boto3.Session(region_name=region).client(
            "sqs",
            config=Config(
                connect_timeout=float(config.get("WHATSAPP_AWS_CONNECT_TIMEOUT_SECONDS") or 3),
                read_timeout=float(config.get("WHATSAPP_AWS_SQS_READ_TIMEOUT_SECONDS") or 25),
                retries={"total_max_attempts": 3, "mode": "standard"},
            ),
        )

    def publish(self, event: WhatsAppWebhookEvent) -> None:
        sender = str(event.payload.get("from") or event.provider_message_id or event.id)
        group_id = f"{event.tenant_id}:{sender}"[:128]
        try:
            self.client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(
                    {"schemaVersion": 1, "webhookEventId": str(event.id)},
                    separators=(",", ":"),
                ),
                MessageGroupId=group_id,
                MessageDeduplicationId=str(event.id),
                MessageAttributes={
                    "correlationId": {
                        "DataType": "String",
                        "StringValue": event.correlation_id,
                    },
                    "tenantId": {
                        "DataType": "String",
                        "StringValue": str(event.tenant_id),
                    },
                },
            )
        except (BotoCoreError, ClientError) as error:
            raise WhatsAppQueueUnavailable(
                "Nao foi possivel publicar o evento WhatsApp na fila."
            ) from error

    def receive(self, *, limit: int) -> list[dict]:
        try:
            response = self.client.receive_message(
                QueueUrl=self.queue_url,
                MaxNumberOfMessages=min(max(limit, 1), 10),
                WaitTimeSeconds=int(
                    current_app.config.get("WHATSAPP_AWS_SQS_WAIT_TIME_SECONDS", 20)
                ),
                VisibilityTimeout=int(
                    current_app.config.get("WHATSAPP_AWS_SQS_VISIBILITY_TIMEOUT_SECONDS", 120)
                ),
                AttributeNames=["ApproximateReceiveCount"],
                MessageAttributeNames=["correlationId", "tenantId"],
            )
        except (BotoCoreError, ClientError) as error:
            raise WhatsAppQueueUnavailable(
                "Nao foi possivel consultar a fila de eventos WhatsApp."
            ) from error
        return list(response.get("Messages", []))

    def delete(self, receipt_handle: str) -> None:
        try:
            self.client.delete_message(QueueUrl=self.queue_url, ReceiptHandle=receipt_handle)
        except (BotoCoreError, ClientError) as error:
            raise WhatsAppQueueUnavailable(
                "Nao foi possivel confirmar o evento WhatsApp na fila."
            ) from error


def get_aws_whatsapp_queue() -> AWSWhatsAppInboundQueue:
    configured = current_app.extensions.get("whatsapp_inbound_queue")
    if configured is None:
        configured = AWSWhatsAppInboundQueue(current_app.config)
        current_app.extensions["whatsapp_inbound_queue"] = configured
    return configured


def publish_webhook_events(event_ids: tuple[uuid.UUID, ...] | list[uuid.UUID]) -> int:
    if not event_ids:
        return 0
    queue = get_aws_whatsapp_queue()
    published = 0
    for event_id in event_ids:
        event = db.session.get(WhatsAppWebhookEvent, event_id)
        if event is None:
            continue
        queue.publish(event)
        mark_webhook_queued(event.id)
        db.session.commit()
        published += 1
    return published


def reconcile_pending_webhook_events() -> int:
    if current_app.config.get("WHATSAPP_INBOUND_QUEUE_BACKEND") != "aws-sqs":
        return 0
    event_ids = pending_webhook_event_ids(
        int(current_app.config.get("WHATSAPP_WEBHOOK_RECONCILE_BATCH_SIZE", 100))
    )
    try:
        return publish_webhook_events(event_ids)
    except WhatsAppQueueUnavailable:
        db.session.rollback()
        current_app.logger.exception("WhatsApp queue reconciliation failed")
        return 0


def process_aws_whatsapp_batch() -> QueueProcessingResult:
    if current_app.config.get("WHATSAPP_INBOUND_QUEUE_BACKEND") != "aws-sqs":
        return QueueProcessingResult()
    queue = get_aws_whatsapp_queue()
    messages = queue.receive(limit=int(current_app.config["WORKER_BATCH_SIZE"]))
    succeeded = retried = discarded = 0
    for message in messages:
        outcome = _process_sqs_message(queue, message)
        succeeded += outcome == "succeeded"
        retried += outcome == "retried"
        discarded += outcome == "discarded"
    return QueueProcessingResult(len(messages), succeeded, retried, discarded)


def _process_sqs_message(queue: AWSWhatsAppInboundQueue, message: dict) -> str:
    receipt_handle = str(message.get("ReceiptHandle") or "")
    try:
        body = json.loads(str(message.get("Body") or ""))
        event_id = uuid.UUID(str(body["webhookEventId"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        current_app.logger.error("Invalid WhatsApp SQS message discarded")
        if receipt_handle:
            queue.delete(receipt_handle)
        return "discarded"

    receive_count = int(message.get("Attributes", {}).get("ApproximateReceiveCount", "1"))
    event = db.session.get(WhatsAppWebhookEvent, event_id)
    if event is None:
        queue.delete(receipt_handle)
        return "discarded"
    tenant_id = event.tenant_id
    if tenant_id is None:
        process_webhook_event(event_id, receive_count=receive_count)
        db.session.commit()
        queue.delete(receipt_handle)
        return "discarded"
    try:
        with tenant_context(tenant_id):
            process_webhook_event(event_id, receive_count=receive_count)
            db.session.commit()
        queue.delete(receipt_handle)
        return "succeeded"
    except Exception:
        db.session.rollback()
        exhausted = receive_count >= queue.max_receive_count
        with tenant_context(tenant_id):
            mark_webhook_failure(
                event_id,
                receive_count=receive_count,
                exhausted=exhausted,
            )
            db.session.commit()
        current_app.logger.exception(
            "WhatsApp webhook processing failed",
            extra={"event_id": str(event_id), "receive_count": receive_count},
        )
        return "retried"
