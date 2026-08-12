import re
import uuid
from collections.abc import Mapping
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.communications.whatsapp_onboarding import SecretBackendUnavailable

AWS_SECRETS_MANAGER_BACKEND = "aws-secrets-manager"
SECRET_PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9/_+=.@-]{1,300}$")
KMS_KEY_PATTERN = re.compile(r"^(arn:aws[a-z-]*:kms:|alias/)[A-Za-z0-9:/_+=.@-]+$")


class AWSSecretsManagerWhatsAppStore:
    def __init__(self, config: Mapping, client: Any | None = None):
        self.region = str(config.get("AWS_REGION") or "sa-east-1").strip()
        self.prefix = str(
            config.get("WHATSAPP_AWS_SECRET_PREFIX")
            or f"gabflow/{str(config.get('APP_ENV') or 'development').lower()}/whatsapp"
        ).strip("/")
        self.kms_key_id = str(config.get("WHATSAPP_AWS_KMS_KEY_ID") or "").strip()
        self.recovery_window_days = int(
            config.get("WHATSAPP_AWS_SECRET_RECOVERY_WINDOW_DAYS") or 30
        )
        self._validate_configuration()
        self.client = client or boto3.Session(region_name=self.region).client(
            "secretsmanager",
            config=Config(
                connect_timeout=float(config.get("WHATSAPP_AWS_CONNECT_TIMEOUT_SECONDS") or 3),
                read_timeout=float(config.get("WHATSAPP_AWS_READ_TIMEOUT_SECONDS") or 8),
                retries={"total_max_attempts": 3, "mode": "standard"},
            ),
        )

    def put(self, *, tenant_id: uuid.UUID, integration_id: uuid.UUID, value: str) -> str:
        if not value:
            raise SecretBackendUnavailable("O valor do segredo WhatsApp esta vazio.")
        name = self._secret_name(tenant_id, integration_id)
        try:
            response = self.client.create_secret(
                Name=name,
                ClientRequestToken=str(integration_id),
                Description="Credenciais WhatsApp do gabinete gerenciadas pelo GabFlow",
                KmsKeyId=self.kms_key_id,
                SecretString=value,
                Tags=[
                    {"Key": "application", "Value": "gabflow"},
                    {"Key": "environment", "Value": self._environment_from_prefix()},
                    {"Key": "purpose", "Value": "whatsapp-integration"},
                    {"Key": "tenant-id", "Value": str(tenant_id)},
                    {"Key": "integration-id", "Value": str(integration_id)},
                    {"Key": "managed-by", "Value": "gabflow-api"},
                ],
            )
        except (BotoCoreError, ClientError) as exc:
            raise SecretBackendUnavailable(
                "Nao foi possivel armazenar a credencial no AWS Secrets Manager."
            ) from exc
        reference = str(response.get("ARN") or "")
        if not reference.startswith("arn:"):
            raise SecretBackendUnavailable(
                "O AWS Secrets Manager nao retornou uma referencia valida."
            )
        return reference

    def delete(self, reference: str) -> None:
        if not reference.startswith("arn:") or ":secretsmanager:" not in reference:
            raise SecretBackendUnavailable("Referencia de segredo AWS invalida.")
        try:
            self.client.delete_secret(
                SecretId=reference,
                RecoveryWindowInDays=self.recovery_window_days,
            )
        except self.client.exceptions.ResourceNotFoundException:
            return
        except (BotoCoreError, ClientError) as exc:
            raise SecretBackendUnavailable(
                "Nao foi possivel agendar a exclusao da credencial no AWS Secrets Manager."
            ) from exc

    def _secret_name(self, tenant_id: uuid.UUID, integration_id: uuid.UUID) -> str:
        return f"{self.prefix}/{tenant_id}/{integration_id}"

    def _environment_from_prefix(self) -> str:
        parts = self.prefix.split("/")
        return parts[1] if len(parts) > 1 else "unknown"

    def _validate_configuration(self) -> None:
        if not SECRET_PREFIX_PATTERN.fullmatch(self.prefix):
            raise SecretBackendUnavailable("Prefixo do AWS Secrets Manager invalido.")
        if not KMS_KEY_PATTERN.fullmatch(self.kms_key_id):
            raise SecretBackendUnavailable("Chave KMS do AWS Secrets Manager nao configurada.")
        if not 7 <= self.recovery_window_days <= 30:
            raise SecretBackendUnavailable(
                "A janela de recuperacao do segredo deve estar entre 7 e 30 dias."
            )
