import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from flask import current_app

from app.attachments import attachment_path
from app.extensions import db
from app.models import (
    Attachment,
    AttachmentScanStatus,
    AudioTranscription,
    AudioTranscriptionStatus,
    AuditLog,
    NotificationType,
    OutboxEvent,
    RequestHistory,
)
from app.notifications.service import notify_user

AUDIO_TRANSCRIPTION_EVENT = "TranscricaoAudioSolicitacao"
AUDIO_MIME_TYPES = {
    "audio/mpeg",
    "audio/mp4",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
    "audio/x-wav",
}


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str | None
    language_probability: float | None
    duration_seconds: float | None
    segments: list[dict]


class TranscriptionProvider(Protocol):
    provider: str
    model: str

    def transcribe(self, path: Path) -> TranscriptionResult: ...


class AudioTranscriptionError(RuntimeError):
    pass


class NonRetryableTranscriptionError(AudioTranscriptionError):
    pass


class NoSpeechDetectedError(NonRetryableTranscriptionError):
    pass


class FasterWhisperProvider:
    provider = "FASTER_WHISPER"
    _models: dict[tuple[str, str, str, str], object] = {}

    def __init__(
        self,
        model: str,
        device: str,
        compute_type: str,
        cache_directory: str,
        language: str | None,
        maximum_duration_seconds: int,
    ) -> None:
        self.model = model
        self.device = device
        self.compute_type = compute_type
        self.cache_directory = cache_directory
        self.language = language
        self.maximum_duration_seconds = maximum_duration_seconds

    def transcribe(self, path: Path) -> TranscriptionResult:
        self._validate_duration(path)
        try:
            model = self._model()
            generated_segments, info = model.transcribe(
                str(path),
                language=self.language,
                beam_size=5,
                vad_filter=True,
                condition_on_previous_text=True,
            )
            segments = [
                {
                    "inicio": round(float(segment.start), 3),
                    "fim": round(float(segment.end), 3),
                    "texto": segment.text.strip(),
                }
                for segment in generated_segments
                if segment.text.strip()
            ]
        except Exception as error:
            raise AudioTranscriptionError("Falha ao processar o áudio localmente.") from error

        text = " ".join(item["texto"] for item in segments).strip()
        if not text:
            raise NoSpeechDetectedError("Nenhuma fala reconhecível foi encontrada no áudio.")
        return TranscriptionResult(
            text=text,
            language=str(info.language) if info.language else None,
            language_probability=_optional_float(info.language_probability),
            duration_seconds=_optional_float(info.duration),
            segments=segments,
        )

    def _validate_duration(self, path: Path) -> None:
        try:
            import av

            with av.open(str(path)) as container:
                duration = (
                    float(container.duration / av.time_base) if container.duration else None
                )
        except Exception as error:
            raise NonRetryableTranscriptionError(
                "O arquivo não contém um áudio válido."
            ) from error
        if duration is not None and duration > self.maximum_duration_seconds:
            raise NonRetryableTranscriptionError(
                "O áudio excede a duração máxima permitida para transcrição."
            )

    def _model(self):
        key = (self.model, self.device, self.compute_type, self.cache_directory)
        if key not in self._models:
            from faster_whisper import WhisperModel

            self._models[key] = WhisperModel(
                self.model,
                device=self.device,
                compute_type=self.compute_type,
                download_root=self.cache_directory,
            )
        return self._models[key]


def transcription_provider() -> TranscriptionProvider:
    provider = current_app.config["AUDIO_TRANSCRIPTION_PROVIDER"].lower()
    if provider != "faster-whisper":
        raise RuntimeError(f"Provedor de transcrição não suportado: {provider}.")
    language = current_app.config["AUDIO_TRANSCRIPTION_LANGUAGE"].strip() or None
    return FasterWhisperProvider(
        model=current_app.config["AUDIO_TRANSCRIPTION_MODEL"],
        device=current_app.config["AUDIO_TRANSCRIPTION_DEVICE"],
        compute_type=current_app.config["AUDIO_TRANSCRIPTION_COMPUTE_TYPE"],
        cache_directory=current_app.config["AUDIO_TRANSCRIPTION_CACHE_DIR"],
        language=language,
        maximum_duration_seconds=current_app.config[
            "AUDIO_TRANSCRIPTION_MAX_DURATION_SECONDS"
        ],
    )


def enqueue_audio_transcription(
    attachment: Attachment,
    requested_by_id: uuid.UUID,
) -> AudioTranscription | None:
    if attachment.mime_type not in AUDIO_MIME_TYPES:
        return None
    provider = transcription_provider()
    transcription = AudioTranscription(
        tenant_id=attachment.tenant_id,
        attachment_id=attachment.id,
        request_id=attachment.request_id,
        provider=provider.provider,
        model=provider.model,
        requested_by_id=requested_by_id,
    )
    db.session.add(transcription)
    db.session.flush()
    db.session.add(
        OutboxEvent(
            tenant_id=attachment.tenant_id,
            event_type=AUDIO_TRANSCRIPTION_EVENT,
            aggregate_type="TranscricaoAudio",
            aggregate_id=str(transcription.id),
            payload={"transcriptionId": str(transcription.id)},
        )
    )
    return transcription


def requeue_audio_transcription(transcription: AudioTranscription) -> None:
    transcription.status = AudioTranscriptionStatus.PENDENTE
    transcription.error = None
    transcription.started_at = None
    transcription.completed_at = None
    db.session.add(
        OutboxEvent(
            tenant_id=transcription.tenant_id,
            event_type=AUDIO_TRANSCRIPTION_EVENT,
            aggregate_type="TranscricaoAudio",
            aggregate_id=str(transcription.id),
            payload={"transcriptionId": str(transcription.id)},
        )
    )


def execute_audio_transcription(transcription: AudioTranscription) -> None:
    attachment = db.session.get(Attachment, transcription.attachment_id)
    if (
        attachment is None
        or attachment.tenant_id != transcription.tenant_id
        or attachment.scan_status != AttachmentScanStatus.LIMPO
        or attachment.mime_type not in AUDIO_MIME_TYPES
    ):
        raise AudioTranscriptionError("Anexo de áudio válido não foi encontrado.")

    transcription.status = AudioTranscriptionStatus.PROCESSANDO
    transcription.started_at = datetime.now(UTC)
    db.session.flush()
    result = transcription_provider().transcribe(attachment_path(attachment.storage_key))
    transcription.transcript = result.text
    transcription.language = result.language
    transcription.language_probability = result.language_probability
    transcription.duration_seconds = result.duration_seconds
    transcription.segments = result.segments
    transcription.status = AudioTranscriptionStatus.CONCLUIDA
    transcription.completed_at = datetime.now(UTC)
    transcription.error = None
    details = {
        "transcricaoId": str(transcription.id),
        "anexoId": str(attachment.id),
        "modelo": transcription.model,
        "idioma": transcription.language,
        "duracaoSegundos": transcription.duration_seconds,
    }
    db.session.add(
        RequestHistory(
            tenant_id=transcription.tenant_id,
            request_id=transcription.request_id,
            user_id=transcription.requested_by_id,
            action="audio.transcription.completed",
            changes=details,
        )
    )
    db.session.add(
        AuditLog(
            tenant_id=transcription.tenant_id,
            user_id=transcription.requested_by_id,
            action="audio.transcription.completed",
            entity_type="audio_transcription",
            entity_id=str(transcription.id),
            after=details,
        )
    )
    db.session.add(
        OutboxEvent(
            tenant_id=transcription.tenant_id,
            event_type="TranscricaoAudioConcluida",
            aggregate_type="Solicitacao",
            aggregate_id=str(transcription.request_id),
            payload=details,
        )
    )
    notify_user(
        transcription.tenant_id,
        transcription.requested_by_id,
        NotificationType.SISTEMA,
        "Transcrição de áudio concluída",
        f"O áudio {attachment.original_name} está pronto para revisão.",
        "audio_transcription",
        transcription.id,
    )


def transcription_data(transcription: AudioTranscription | None) -> dict | None:
    if transcription is None:
        return None
    return {
        "id": str(transcription.id),
        "status": transcription.status.value,
        "statusRevisao": transcription.review_status.value,
        "provedor": transcription.provider,
        "modelo": transcription.model,
        "idioma": transcription.language,
        "confiancaIdioma": transcription.language_probability,
        "duracaoSegundos": transcription.duration_seconds,
        "textoGerado": transcription.transcript,
        "textoRevisado": transcription.reviewed_transcript,
        "segmentos": transcription.segments or [],
        "erro": transcription.error,
        "criadaEm": transcription.created_at.isoformat(),
        "concluidaEm": (
            transcription.completed_at.isoformat() if transcription.completed_at else None
        ),
        "revisadaEm": (
            transcription.reviewed_at.isoformat() if transcription.reviewed_at else None
        ),
    }


def _optional_float(value: object) -> float | None:
    return round(float(value), 4) if value is not None else None
