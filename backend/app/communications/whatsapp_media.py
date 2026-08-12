import base64
import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select

from app.ai.ocr import OCR_MIME_TYPES, ocr_provider
from app.ai.service import enqueue_triage_execution
from app.ai.transcription import AUDIO_MIME_TYPES, transcription_provider
from app.attachments import AttachmentError, attachment_path, store_attachment_bytes
from app.extensions import db
from app.models import (
    Attachment,
    AttachmentScanStatus,
    AudioTranscription,
    AudioTranscriptionReviewStatus,
    AudioTranscriptionStatus,
    DocumentOcr,
    DocumentOcrReviewStatus,
    DocumentOcrStatus,
    OutboxEvent,
    ServiceRequest,
    WhatsAppConversation,
    WhatsAppIntegration,
    WhatsAppMediaAsset,
    WhatsAppMessage,
    WhatsAppWebhookEvent,
)
from app.security.encryption import plaintext_file, read_plaintext

WHATSAPP_MEDIA_DOWNLOAD_EVENT = "DownloadWhatsappMediaRequested"
WHATSAPP_MEDIA_ANALYSIS_EVENT = "AnalyzeWhatsappMediaRequested"
MEDIA_TYPES = {"audio", "image", "document", "video", "sticker"}


class WhatsAppMediaError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class MediaDownload:
    content: bytes
    mime_type: str
    filename: str
    sha256: str | None = None


class WhatsAppMediaAdapter(Protocol):
    def download(
        self, integration: WhatsAppIntegration, provider_media_id: str
    ) -> MediaDownload: ...


class UnconfiguredWhatsAppMediaAdapter:
    def download(
        self, integration: WhatsAppIntegration, provider_media_id: str
    ) -> MediaDownload:
        del integration, provider_media_id
        raise WhatsAppMediaError(
            "MEDIA_RUNTIME_CREDENTIAL_UNAVAILABLE",
            "O resolvedor seguro de credenciais de mídia não está configurado.",
        )


def get_whatsapp_media_adapter() -> WhatsAppMediaAdapter:
    return current_app.extensions.get("whatsapp_media_adapter") or (
        UnconfiguredWhatsAppMediaAdapter()
    )


def register_inbound_media(
    *,
    webhook_event: WhatsAppWebhookEvent,
    integration: WhatsAppIntegration,
    conversation: WhatsAppConversation,
    message: WhatsAppMessage,
    media: dict,
) -> WhatsAppMediaAsset | None:
    provider_media_id = str(media.get("id") or "").strip()
    media_type = str(media.get("type") or "").strip().lower()
    if not provider_media_id or media_type not in MEDIA_TYPES:
        return None
    existing = db.session.execute(
        select(WhatsAppMediaAsset).where(
            WhatsAppMediaAsset.tenant_id == conversation.tenant_id,
            WhatsAppMediaAsset.provider_media_id == provider_media_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    asset = WhatsAppMediaAsset(
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        message_id=message.id,
        webhook_event_id=webhook_event.id,
        integration_id=integration.id,
        provider_media_id=provider_media_id,
        provider_message_id=str(webhook_event.provider_message_id),
        media_type=media_type,
        mime_type=str(media.get("mimeType") or "").strip() or None,
        original_name=str(media.get("filename") or "").strip()[:255] or None,
        caption=str(media.get("caption") or "").strip()[:1000] or None,
        provider_sha256=str(media.get("sha256") or "").strip() or None,
        status="RECEIVED",
        analysis_status="NOT_APPLICABLE",
        review_status="NOT_REQUIRED",
        created_by_id=integration.created_by_id,
        retention_until=datetime.now(UTC)
        + timedelta(days=current_app.config["WHATSAPP_MEDIA_RETENTION_DAYS"]),
    )
    db.session.add(asset)
    db.session.flush()
    db.session.add(
        OutboxEvent(
            tenant_id=asset.tenant_id,
            event_type=WHATSAPP_MEDIA_DOWNLOAD_EVENT,
            aggregate_type="whatsapp_media_asset",
            aggregate_id=str(asset.id),
            payload={"mediaAssetId": str(asset.id)},
        )
    )
    return asset


def download_media_asset(asset: WhatsAppMediaAsset) -> None:
    if asset.status == "READY":
        return
    integration = db.session.execute(
        select(WhatsAppIntegration).where(
            WhatsAppIntegration.id == asset.integration_id,
            WhatsAppIntegration.tenant_id == asset.tenant_id,
        )
    ).scalar_one_or_none()
    if integration is None:
        raise WhatsAppMediaError(
            "MEDIA_INTEGRATION_NOT_FOUND", "Integração da mídia não encontrada.", retryable=False
        )
    asset.status = "DOWNLOADING"
    db.session.flush()
    result = get_whatsapp_media_adapter().download(integration, asset.provider_media_id)
    if not isinstance(result.content, bytes):
        raise WhatsAppMediaError(
            "MEDIA_INVALID_CONTENT", "A Meta retornou conteúdo de mídia inválido.", retryable=False
        )
    digest = hashlib.sha256(result.content).hexdigest()
    expected = asset.provider_sha256 or result.sha256
    if expected and not _matches_sha256(expected, digest):
        raise WhatsAppMediaError(
            "MEDIA_INTEGRITY_MISMATCH",
            "A integridade da mídia recebida não pôde ser confirmada.",
            retryable=False,
        )
    mime_type = (result.mime_type or asset.mime_type or "application/octet-stream").split(
        ";", 1
    )[0].strip().lower()
    filename = result.filename or asset.original_name or f"whatsapp-{asset.id}"
    try:
        stored = store_attachment_bytes(
            asset.tenant_id,
            asset.id,
            filename=filename,
            mime_type=mime_type,
            content=result.content,
        )
    except AttachmentError as error:
        raise WhatsAppMediaError(
            "MEDIA_SECURITY_REJECTED", str(error), retryable=False
        ) from error
    for field, value in stored.items():
        setattr(asset, field, value)
    asset.scan_status = AttachmentScanStatus.LIMPO
    asset.status = "READY"
    asset.downloaded_at = datetime.now(UTC)
    asset.error = None
    asset.error_code = None
    if asset.mime_type in AUDIO_MIME_TYPES:
        asset.analysis_type = "TRANSCRIPTION"
    elif asset.mime_type in OCR_MIME_TYPES:
        asset.analysis_type = "OCR"
    else:
        asset.analysis_type = None
    asset.analysis_status = "PENDING" if asset.analysis_type else "NOT_APPLICABLE"
    asset.review_status = "PENDING" if asset.analysis_type else "NOT_REQUIRED"
    if asset.analysis_type:
        db.session.add(
            OutboxEvent(
                tenant_id=asset.tenant_id,
                event_type=WHATSAPP_MEDIA_ANALYSIS_EVENT,
                aggregate_type="whatsapp_media_asset",
                aggregate_id=str(asset.id),
                payload={"mediaAssetId": str(asset.id)},
            )
        )
    else:
        materialize_request_attachment(asset)


def _matches_sha256(expected: str, digest_hex: str) -> bool:
    """Accept Meta's base64 digest as well as adapters that expose hexadecimal SHA-256."""
    normalized = expected.strip()
    if hmac.compare_digest(normalized.lower(), digest_hex):
        return True
    try:
        decoded = base64.b64decode(normalized, validate=True).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(decoded, digest_hex)


def analyze_media_asset(asset: WhatsAppMediaAsset) -> None:
    if asset.analysis_status == "COMPLETED":
        return
    if asset.status != "READY" or asset.scan_status != AttachmentScanStatus.LIMPO:
        raise WhatsAppMediaError(
            "MEDIA_NOT_READY", "A mídia ainda não está segura para análise."
        )
    if not asset.storage_key or not asset.mime_type:
        raise WhatsAppMediaError(
            "MEDIA_STORAGE_MISSING", "O arquivo seguro da mídia não foi encontrado."
        )
    asset.analysis_status = "PROCESSING"
    db.session.flush()
    path = attachment_path(asset.storage_key)
    with plaintext_file(path, f"tenant:{asset.tenant_id}", suffix=path.suffix) as plain:
        if asset.analysis_type == "TRANSCRIPTION":
            provider = transcription_provider()
            result = provider.transcribe(plain)
            asset.analysis_provider = provider.provider
            asset.analysis_model = provider.model
            asset.generated_text = result.text
            asset.confidence = result.language_probability
        elif asset.analysis_type == "OCR":
            provider = ocr_provider()
            result = provider.extract(plain, asset.mime_type)
            asset.analysis_provider = provider.provider
            asset.analysis_model = provider.model
            asset.generated_text = result.text
            asset.confidence = result.confidence
        else:
            asset.analysis_status = "NOT_APPLICABLE"
            materialize_request_attachment(asset)
            return
    asset.prompt_version = "whatsapp-media-v1"
    asset.analysis_status = "COMPLETED"
    asset.review_status = "PENDING"
    asset.analyzed_at = datetime.now(UTC)
    asset.error = None
    asset.error_code = None
    materialize_request_attachment(asset)
    enqueue_media_triage(asset)


def link_conversation_media_to_request(
    conversation: WhatsAppConversation, service_request: ServiceRequest
) -> int:
    assets = list(
        db.session.scalars(
            select(WhatsAppMediaAsset).where(
                WhatsAppMediaAsset.tenant_id == conversation.tenant_id,
                WhatsAppMediaAsset.conversation_id == conversation.id,
                WhatsAppMediaAsset.request_id.is_(None),
            )
        )
    )
    should_triage = False
    for asset in assets:
        asset.request_id = service_request.id
        materialize_request_attachment(asset)
        should_triage = should_triage or asset.analysis_status == "COMPLETED"
    if should_triage:
        _enqueue_triage_without_blocking(service_request, service_request.created_by_id)
    return len(assets)


def materialize_request_attachment(asset: WhatsAppMediaAsset) -> Attachment | None:
    if asset.attachment_id is not None:
        return db.session.get(Attachment, asset.attachment_id)
    if asset.request_id is None or asset.status != "READY" or not asset.storage_key:
        return None
    if asset.analysis_status not in {"COMPLETED", "FAILED", "NOT_APPLICABLE"}:
        return None
    attachment = Attachment(
        tenant_id=asset.tenant_id,
        request_id=asset.request_id,
        storage_key=asset.storage_key,
        original_name=asset.original_name or f"whatsapp-{asset.id}",
        mime_type=asset.mime_type or "application/octet-stream",
        size_bytes=asset.size_bytes or 0,
        sha256=asset.sha256 or "",
        scan_status=asset.scan_status or AttachmentScanStatus.LIMPO,
        scan_provider=asset.scan_provider,
        scan_engine_version=asset.scan_engine_version,
        scan_signature_version=asset.scan_signature_version,
        scan_threat=asset.scan_threat,
        scan_error_code=asset.scan_error_code,
        scanned_at=asset.scanned_at,
        encryption_key_version=asset.encryption_key_version,
        encryption_algorithm=asset.encryption_algorithm,
        encrypted_at=asset.encrypted_at,
        uploaded_by_id=asset.created_by_id,
    )
    db.session.add(attachment)
    db.session.flush()
    asset.attachment_id = attachment.id
    if asset.analysis_type == "TRANSCRIPTION":
        db.session.add(
            AudioTranscription(
                tenant_id=asset.tenant_id,
                attachment_id=attachment.id,
                request_id=asset.request_id,
                status=(
                    AudioTranscriptionStatus.CONCLUIDA
                    if asset.analysis_status == "COMPLETED"
                    else AudioTranscriptionStatus.FALHOU
                ),
                review_status=AudioTranscriptionReviewStatus.PENDENTE,
                provider=asset.analysis_provider or "WHATSAPP_MEDIA",
                model=asset.analysis_model or "unavailable",
                language=None,
                language_probability=asset.confidence,
                transcript=asset.generated_text,
                requested_by_id=asset.created_by_id,
                error=asset.error,
                completed_at=asset.analyzed_at,
            )
        )
    elif asset.analysis_type == "OCR":
        db.session.add(
            DocumentOcr(
                tenant_id=asset.tenant_id,
                attachment_id=attachment.id,
                request_id=asset.request_id,
                status=(
                    DocumentOcrStatus.CONCLUIDO
                    if asset.analysis_status == "COMPLETED"
                    else DocumentOcrStatus.FALHOU
                ),
                review_status=DocumentOcrReviewStatus.PENDENTE,
                provider=asset.analysis_provider or "WHATSAPP_MEDIA",
                model=asset.analysis_model or "unavailable",
                language="por",
                confidence=asset.confidence,
                extracted_text=asset.generated_text,
                requested_by_id=asset.created_by_id,
                error=asset.error,
                completed_at=asset.analyzed_at,
            )
        )
    return attachment


def review_media_asset(
    asset: WhatsAppMediaAsset, *, actor_id: uuid.UUID, action: str, text: str | None
) -> None:
    if asset.analysis_status != "COMPLETED" or asset.review_status != "PENDING":
        raise WhatsAppMediaError(
            "MEDIA_REVIEW_CONFLICT", "A análise não está pendente de revisão.", retryable=False
        )
    action = str(action or "").upper()
    statuses = {"ACCEPT": "ACCEPTED", "EDIT": "EDITED", "REJECT": "REJECTED"}
    if action not in statuses:
        raise WhatsAppMediaError(
            "MEDIA_REVIEW_INVALID", "A decisão de revisão é inválida.", retryable=False
        )
    reviewed = asset.generated_text if action == "ACCEPT" else None
    if action == "EDIT":
        reviewed = str(text or "").strip()
        if not reviewed:
            raise WhatsAppMediaError(
                "MEDIA_REVIEW_TEXT_REQUIRED",
                "Informe o texto revisado.",
                retryable=False,
            )
    asset.review_status = statuses[action]
    asset.reviewed_text = reviewed
    asset.reviewed_by_id = actor_id
    asset.reviewed_at = datetime.now(UTC)
    if asset.attachment_id:
        if asset.analysis_type == "TRANSCRIPTION":
            derived = db.session.scalar(
                select(AudioTranscription).where(
                    AudioTranscription.attachment_id == asset.attachment_id
                )
            )
            if derived:
                derived.review_status = {
                    "ACCEPT": AudioTranscriptionReviewStatus.ACEITA,
                    "EDIT": AudioTranscriptionReviewStatus.EDITADA,
                    "REJECT": AudioTranscriptionReviewStatus.REJEITADA,
                }[action]
                derived.reviewed_transcript = reviewed
                derived.reviewed_by_id = actor_id
                derived.reviewed_at = asset.reviewed_at
        elif asset.analysis_type == "OCR":
            derived = db.session.scalar(
                select(DocumentOcr).where(DocumentOcr.attachment_id == asset.attachment_id)
            )
            if derived:
                derived.review_status = {
                    "ACCEPT": DocumentOcrReviewStatus.ACEITO,
                    "EDIT": DocumentOcrReviewStatus.EDITADO,
                    "REJECT": DocumentOcrReviewStatus.REJEITADO,
                }[action]
                derived.reviewed_text = reviewed
                derived.reviewed_by_id = actor_id
                derived.reviewed_at = asset.reviewed_at
    if action != "REJECT":
        enqueue_media_triage(asset, actor_id=actor_id)


def enqueue_media_triage(asset: WhatsAppMediaAsset, *, actor_id: uuid.UUID | None = None) -> None:
    if asset.request_id is None:
        return
    service_request = db.session.get(ServiceRequest, asset.request_id)
    if service_request is None or service_request.tenant_id != asset.tenant_id:
        return
    _enqueue_triage_without_blocking(service_request, actor_id or asset.created_by_id)


def _enqueue_triage_without_blocking(
    service_request: ServiceRequest, actor_id: uuid.UUID | None
) -> None:
    try:
        enqueue_triage_execution(service_request, actor_id)
    except RuntimeError as error:
        current_app.logger.warning(
            "whatsapp_media_assistive_ai_unavailable request_id=%s error_type=%s",
            service_request.id,
            type(error).__name__,
        )


def fail_media_asset(asset: WhatsAppMediaAsset, error: Exception, *, analysis: bool) -> None:
    code = error.code if isinstance(error, WhatsAppMediaError) else "MEDIA_PROCESSING_FAILED"
    if analysis:
        asset.analysis_status = "FAILED"
        asset.review_status = "NOT_REQUIRED"
        asset.analyzed_at = datetime.now(UTC)
        materialize_request_attachment(asset)
    else:
        asset.status = "BLOCKED" if code in {
            "MEDIA_SECURITY_REJECTED",
            "MEDIA_INTEGRITY_MISMATCH",
        } else "FAILED"
    asset.error_code = code[:80]
    asset.error = str(error)[:1000]


def media_asset_data(asset: WhatsAppMediaAsset) -> dict:
    return {
        "id": str(asset.id),
        "messageId": str(asset.message_id),
        "tipo": asset.media_type,
        "nome": asset.original_name,
        "mimeType": asset.mime_type,
        "tamanho": asset.size_bytes,
        "status": asset.status,
        "statusVerificacao": asset.scan_status.value if asset.scan_status else None,
        "analise": {
            "tipo": asset.analysis_type,
            "status": asset.analysis_status,
            "provedor": asset.analysis_provider,
            "modelo": asset.analysis_model,
            "versaoPrompt": asset.prompt_version,
            "confianca": asset.confidence,
            "textoGerado": asset.generated_text,
            "textoRevisado": asset.reviewed_text,
            "statusRevisao": asset.review_status,
            "erro": asset.error if asset.analysis_status == "FAILED" else None,
        },
        "solicitacaoId": str(asset.request_id) if asset.request_id else None,
        "downloadUrl": (
            f"/api/v1/tenants/{asset.tenant_id}/whatsapp/media/{asset.id}/download"
            f"?token={signed_media_token(asset)}"
            if asset.status == "READY"
            else None
        ),
        "erro": asset.error if asset.status in {"BLOCKED", "FAILED"} else None,
        "criadaEm": asset.created_at.isoformat(),
    }


def signed_media_token(asset: WhatsAppMediaAsset) -> str:
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="whatsapp-media")
    return serializer.dumps({"asset": str(asset.id), "tenant": str(asset.tenant_id)})


def verify_media_token(token: str, asset: WhatsAppMediaAsset) -> bool:
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="whatsapp-media")
    try:
        data = serializer.loads(token, max_age=current_app.config["ATTACHMENT_TOKEN_MAX_AGE"])
    except (BadSignature, SignatureExpired):
        return False
    return data == {"asset": str(asset.id), "tenant": str(asset.tenant_id)}


def media_plaintext(asset: WhatsAppMediaAsset) -> bytes:
    if asset.status != "READY" or not asset.storage_key:
        raise AttachmentError("Mídia não disponível.")
    return read_plaintext(attachment_path(asset.storage_key), f"tenant:{asset.tenant_id}")
