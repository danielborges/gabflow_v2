import uuid

import pytest
from botocore.exceptions import ClientError

from app.communications.aws_secret_store import AWSSecretsManagerWhatsAppStore
from app.communications.whatsapp_onboarding import SecretBackendUnavailable


class FakeSecretsManagerClient:
    class exceptions:
        class ResourceNotFoundException(Exception):
            pass

    def __init__(self):
        self.created = []
        self.deleted = []
        self.failure = None

    def create_secret(self, **kwargs):
        if self.failure:
            raise self.failure
        self.created.append(kwargs)
        return {
            "ARN": (
                "arn:aws:secretsmanager:sa-east-1:123456789012:secret:"
                f"{kwargs['Name']}-a1b2c3"
            )
        }

    def delete_secret(self, **kwargs):
        if self.failure:
            raise self.failure
        self.deleted.append(kwargs)
        return {"ARN": kwargs["SecretId"]}



def store_config(**overrides):
    config = {
        "APP_ENV": "production",
        "AWS_REGION": "sa-east-1",
        "WHATSAPP_AWS_SECRET_PREFIX": "gabflow/production/whatsapp",
        "WHATSAPP_AWS_KMS_KEY_ID": (
            "arn:aws:kms:sa-east-1:123456789012:key/"
            "11111111-2222-3333-4444-555555555555"
        ),
        "WHATSAPP_AWS_SECRET_RECOVERY_WINDOW_DAYS": 30,
    }
    config.update(overrides)
    return config


def test_aws_store_creates_tenant_scoped_secret_and_returns_only_arn():
    client = FakeSecretsManagerClient()
    store = AWSSecretsManagerWhatsAppStore(store_config(), client=client)
    tenant_id = uuid.uuid4()
    integration_id = uuid.uuid4()

    reference = store.put(
        tenant_id=tenant_id,
        integration_id=integration_id,
        value='{"access_token":"sensitive","two_step_pin":"123456"}',
    )

    created = client.created[0]
    assert created["Name"] == f"gabflow/production/whatsapp/{tenant_id}/{integration_id}"
    assert created["ClientRequestToken"] == str(integration_id)
    assert created["KmsKeyId"] == store_config()["WHATSAPP_AWS_KMS_KEY_ID"]
    assert reference.startswith("arn:aws:secretsmanager:sa-east-1:")
    assert "sensitive" not in reference
    assert {tag["Key"]: tag["Value"] for tag in created["Tags"]} == {
        "application": "gabflow",
        "environment": "production",
        "purpose": "whatsapp-integration",
        "tenant-id": str(tenant_id),
        "integration-id": str(integration_id),
        "managed-by": "gabflow-api",
    }


def test_aws_store_schedules_recoverable_deletion():
    client = FakeSecretsManagerClient()
    store = AWSSecretsManagerWhatsAppStore(store_config(), client=client)
    reference = "arn:aws:secretsmanager:sa-east-1:123456789012:secret:gabflow/test-a1b2c3"

    store.delete(reference)

    assert client.deleted == [{"SecretId": reference, "RecoveryWindowInDays": 30}]


def test_aws_store_rejects_missing_kms_key_before_calling_aws():
    with pytest.raises(SecretBackendUnavailable, match="KMS"):
        AWSSecretsManagerWhatsAppStore(
            store_config(WHATSAPP_AWS_KMS_KEY_ID=""),
            client=FakeSecretsManagerClient(),
        )


def test_aws_store_maps_sdk_error_without_leaking_secret():
    client = FakeSecretsManagerClient()
    client.failure = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
        "CreateSecret",
    )
    store = AWSSecretsManagerWhatsAppStore(store_config(), client=client)
    sensitive = "meta-token-that-must-not-leak"

    with pytest.raises(SecretBackendUnavailable) as raised:
        store.put(tenant_id=uuid.uuid4(), integration_id=uuid.uuid4(), value=sensitive)

    assert sensitive not in str(raised.value)
