import io
import sys
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select

from app.ai.transcription import (
    FasterWhisperProvider,
    NoSpeechDetectedError,
    TranscriptionResult,
)
from app.extensions import db
from app.models import AuditLog
from app.outbox.service import process_batch

PASSWORD = "SenhaForte123!"  # noqa: S105


class FakeTranscriptionProvider:
    provider = "FASTER_WHISPER"
    model = "base"

    def __init__(self, error=None):
        self.error = error

    def transcribe(self, _path):
        if self.error:
            raise self.error
        return TranscriptionResult(
            text="A Rua das Flores está sem iluminação.",
            language="pt",
            language_probability=0.98,
            duration_seconds=4.2,
            segments=[
                {
                    "inicio": 0.0,
                    "fim": 4.2,
                    "texto": "A Rua das Flores está sem iluminação.",
                }
            ],
        )


def test_faster_whisper_provider_converts_pyav_duration_to_seconds(monkeypatch):
    class FakeContainer:
        duration = 4_200_000

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    fake_av = SimpleNamespace(time_base=1_000_000, open=lambda _path: FakeContainer())
    fake_model = SimpleNamespace(
        transcribe=lambda *_args, **_kwargs: (
            [SimpleNamespace(start=0, end=4.2, text=" Relato transcrito. ")],
            SimpleNamespace(language="pt", language_probability=0.99, duration=4.2),
        )
    )
    monkeypatch.setitem(sys.modules, "av", fake_av)
    provider = FasterWhisperProvider("base", "cpu", "int8", "/models", "pt", 900)
    monkeypatch.setattr(provider, "_model", lambda: fake_model)

    result = provider.transcribe(Path("audio.wav"))

    assert result.duration_seconds == 4.2
    assert result.text == "Relato transcrito."


def _login(client, tenant="gabinete-a", password=PASSWORD):
    email = "admin-b@teste.local" if tenant == "gabinete-b" else "admin@teste.local"
    client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    return client.get_cookie("csrf_access_token").value


def _request(client, csrf):
    response = client.post(
        "/api/v1/solicitacoes",
        json={
            "origem": "WHATSAPP",
            "titulo": "Relato em áudio",
            "descricao": "Áudio enviado pelo cidadão.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert response.status_code == 201
    return response.json


def _upload_audio(client, csrf, request_id):
    return client.post(
        f"/api/v1/solicitacoes/{request_id}/anexos",
        data={"arquivo": (io.BytesIO(b"audio-original-preservado"), "relato.mp3")},
        headers={"X-CSRF-TOKEN": csrf},
        content_type="multipart/form-data",
    )


def test_audio_is_transcribed_locally_and_reviewed_without_changing_original(
    app, client, monkeypatch
):
    provider = FakeTranscriptionProvider()
    monkeypatch.setattr("app.ai.transcription.transcription_provider", lambda: provider)
    csrf = _login(client)
    service_request = _request(client, csrf)

    uploaded = _upload_audio(client, csrf, service_request["id"])

    assert uploaded.status_code == 201
    assert uploaded.json["transcricao"]["status"] == "PENDENTE"
    assert uploaded.json["transcricao"]["modelo"] == "base"

    with app.app_context():
        result = process_batch("audio-transcription-worker")
        assert result.failed == 0

    details = client.get(f"/api/v1/solicitacoes/{service_request['id']}").json
    attachment = details["anexos"][0]
    transcription = attachment["transcricao"]
    assert transcription["status"] == "CONCLUIDA"
    assert transcription["textoGerado"].startswith("A Rua das Flores")
    assert transcription["idioma"] == "pt"
    assert transcription["segmentos"][0]["fim"] == 4.2

    reviewed = client.post(
        f"/api/v1/transcricoes-audio/{transcription['id']}/revisao",
        json={
            "acao": "EDITAR",
            "texto": "A Rua das Flores está totalmente sem iluminação.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert reviewed.status_code == 200
    assert reviewed.json["statusRevisao"] == "EDITADA"
    assert "totalmente" in reviewed.json["textoRevisado"]

    quality = client.get("/api/v1/ia/qualidade-triagem?dias=30")
    assert quality.json["cobertura"]["audiosTranscritos"] == 1
    assert quality.json["cobertura"]["transcricoesRevisadas"] == 1

    download = client.get(attachment["downloadUrl"])
    assert download.data == b"audio-original-preservado"
    with app.app_context():
        assert db.session.execute(
            select(AuditLog).where(AuditLog.action == "audio.transcription.editar")
        ).scalar_one()


def test_audio_transcription_failure_can_be_reprocessed(app, client, monkeypatch):
    provider = FakeTranscriptionProvider(
        NoSpeechDetectedError("Nenhuma fala reconhecível foi encontrada no áudio.")
    )
    monkeypatch.setattr("app.ai.transcription.transcription_provider", lambda: provider)
    csrf = _login(client)
    service_request = _request(client, csrf)
    _upload_audio(client, csrf, service_request["id"])

    with app.app_context():
        result = process_batch("audio-failure-worker")
        assert result.failed == 1

    details = client.get(f"/api/v1/solicitacoes/{service_request['id']}").json
    transcription = details["anexos"][0]["transcricao"]
    assert transcription["status"] == "FALHOU"
    assert "Nenhuma fala" in transcription["erro"]

    reprocessed = client.post(
        f"/api/v1/transcricoes-audio/{transcription['id']}/reprocessar",
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert reprocessed.status_code == 202
    assert reprocessed.json["status"] == "PENDENTE"


def test_audio_transcription_review_is_isolated_by_tenant(app, client, monkeypatch):
    provider = FakeTranscriptionProvider()
    monkeypatch.setattr("app.ai.transcription.transcription_provider", lambda: provider)
    csrf = _login(client)
    service_request = _request(client, csrf)
    uploaded = _upload_audio(client, csrf, service_request["id"])
    with app.app_context():
        process_batch("audio-tenant-worker")

    transcription_id = uploaded.json["transcricao"]["id"]
    other_csrf = _login(client, "gabinete-b", "OutraSenha123!")
    response = client.post(
        f"/api/v1/transcricoes-audio/{transcription_id}/revisao",
        json={"acao": "ACEITAR"},
        headers={"X-CSRF-TOKEN": other_csrf},
    )
    assert response.status_code == 404
