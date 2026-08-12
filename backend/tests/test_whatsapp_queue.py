import uuid

import pytest

from app.communications.whatsapp_queue import (
    AWSWhatsAppInboundQueue,
    WhatsAppQueueUnavailable,
)
from app.models import WhatsAppWebhookEvent


class FakeSqsClient:
    def __init__(self):
        self.sent = []
        self.deleted = []

    def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return {"MessageId": "message-1"}

    def receive_message(self, **_kwargs):
        return {"Messages": []}

    def delete_message(self, **kwargs):
        self.deleted.append(kwargs)


def _config():
    return {
        "WHATSAPP_AWS_SQS_QUEUE_URL": "https://sqs.sa-east-1.amazonaws.com/123/queue.fifo",
        "WHATSAPP_AWS_SQS_MAX_RECEIVE_COUNT": 5,
        "AWS_REGION": "sa-east-1",
    }


def test_fifo_queue_uses_event_id_for_deduplication_and_conversation_group(app):
    client = FakeSqsClient()
    queue = AWSWhatsAppInboundQueue(_config(), client=client)
    event = WhatsAppWebhookEvent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        correlation_id="correlation-1",
        provider_event_key="meta:wamid.1:message",
        phone_number_id="phone-1",
        provider_message_id="wamid.1",
        event_type="message",
        payload_hash="a" * 64,
        payload={"from": "5532888888888"},
    )

    queue.publish(event)

    sent = client.sent[0]
    assert sent["MessageDeduplicationId"] == str(event.id)
    assert sent["MessageGroupId"] == f"{event.tenant_id}:5532888888888"
    assert "meta:wamid.1:message" not in sent["MessageBody"]
    assert sent["MessageAttributes"]["tenantId"]["StringValue"] == str(event.tenant_id)


def test_queue_requires_https_url():
    with pytest.raises(WhatsAppQueueUnavailable):
        AWSWhatsAppInboundQueue({"WHATSAPP_AWS_SQS_QUEUE_URL": ""}, client=FakeSqsClient())
