import io
import uuid

from sqlalchemy import select

from app.extensions import db
from app.models import (
    Attachment,
    AttachmentScanStatus,
    AudioTranscription,
    AudioTranscriptionReviewStatus,
    AudioTranscriptionStatus,
    AuditLog,
    DocumentOcr,
    DocumentOcrReviewStatus,
    DocumentOcrStatus,
    RagChunk,
    RagDocumentVersion,
    RagSecurityRescanRun,
    RagSecurityRescanStatus,
)
from app.outbox.service import process_batch
from app.rag.security_rescan import _purge_attachment
from app.rag.storage import rag_document_path

PASSWORD = "SenhaForte123!"  # noqa: S105


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@teste.local", "password": PASSWORD},
    )
    assert response.status_code == 200
    return client.get_cookie("csrf_access_token").value


def _upload_rag(client, csrf):
    return client.post(
        "/api/v1/rag/documentos",
        headers={"X-CSRF-TOKEN": csrf},
        content_type="multipart/form-data",
        data={
            "titulo": "Lei para revarredura",
            "tipo": "LEGISLACAO",
            "nivelAcesso": "INTERNO",
            "versao": "2026.1",
            "arquivo": (
                io.BytesIO(
                    (
                        "Art. 1 O municipio manterá servicos publicos e publicará relatorios. "
                        "Art. 2 A fiscalizacao observará os principios legais aplicaveis."
                    ).encode()
                ),
                "lei.txt",
            ),
        },
    )


def test_tenant_rescan_invalidates_then_purges_tampered_derivatives(app, client):
    csrf = _login(client)
    created = _upload_rag(client, csrf)
    assert created.status_code == 202
    version_id = uuid.UUID(created.json["versoes"][0]["id"])
    with app.app_context():
        assert process_batch("initial-ingestion").succeeded == 1
        version = db.session.get(RagDocumentVersion, version_id)
        assert version.chunk_count > 0
        path = rag_document_path(
            version.storage_key,
            tenant_id=version.tenant_id,
            document_id=version.document_id,
            version_id=version.id,
        )
        path.write_bytes(b"conteudo adulterado apos a indexacao")

    requested = client.post(
        "/api/v1/rag/seguranca/revarreduras",
        json={"tamanhoLote": 10},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert requested.status_code == 202
    run_id = uuid.UUID(requested.json["id"])
    assert requested.json["total"] == 1

    with app.app_context():
        version = db.session.get(RagDocumentVersion, version_id)
        assert version.malware_scan_status == "INDETERMINATE"
        assert version.security_status.value == "INDETERMINATE"
        assert process_batch("security-rescan-private").succeeded == 1
        assert process_batch("security-rescan-finish").succeeded == 1
        db.session.expire_all()
        run = db.session.get(RagSecurityRescanRun, run_id)
        version = db.session.get(RagDocumentVersion, version_id)
        assert run.status == RagSecurityRescanStatus.CONCLUIDA
        assert run.processed_targets == 1
        assert run.quarantined_targets == 1
        assert run.purged_chunks > 0
        assert version.malware_scan_status == "INFECTED"
        assert version.chunk_count == 0
        assert version.extracted_text is None
        assert not db.session.scalars(
            select(RagChunk).where(RagChunk.version_id == version_id)
        ).all()
        actions = set(db.session.scalars(select(AuditLog.action)))
        assert {
            "rag_security.rescan_requested",
            "rag_document.malware_quarantined",
            "rag_security.rescan_completed",
        }.issubset(actions)

    detail = client.get(f"/api/v1/rag/seguranca/revarreduras/{run_id}")
    assert detail.status_code == 200
    assert detail.json["estado"] == "CONCLUIDA"
    assert detail.json["progressoPercentual"] == 100.0


def test_only_admin_can_start_tenant_rescan(app, client):
    csrf = _login(client)
    first = client.post(
        "/api/v1/rag/seguranca/revarreduras",
        headers={"X-CSRF-TOKEN": csrf},
        json={"tamanhoLote": 101},
    )
    assert first.status_code == 422

    accepted = client.post(
        "/api/v1/rag/seguranca/revarreduras",
        headers={"X-CSRF-TOKEN": csrf},
        json={"tamanhoLote": 1},
    )
    assert accepted.status_code == 202
    conflict = client.post(
        "/api/v1/rag/seguranca/revarreduras",
        headers={"X-CSRF-TOKEN": csrf},
        json={"tamanhoLote": 1},
    )
    assert conflict.status_code == 409


def test_attachment_quarantine_scrubs_ocr_and_transcription(app):
    common_id = uuid.uuid4()
    attachment = Attachment(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        storage_key="tenant/file.txt",
        original_name="file.txt",
        mime_type="text/plain",
        size_bytes=10,
        sha256="0" * 64,
        scan_status=AttachmentScanStatus.LIMPO,
        uploaded_by_id=common_id,
    )
    attachment.ocr = DocumentOcr(
        id=uuid.uuid4(),
        tenant_id=attachment.tenant_id,
        request_id=attachment.request_id,
        status=DocumentOcrStatus.CONCLUIDO,
        review_status=DocumentOcrReviewStatus.ACEITO,
        provider="test",
        model="test",
        language="pt",
        extracted_text="texto OCR",
        reviewed_text="texto revisado",
        pages=[{"pagina": 1, "texto": "texto OCR"}],
        requested_by_id=common_id,
    )
    attachment.transcription = AudioTranscription(
        id=uuid.uuid4(),
        tenant_id=attachment.tenant_id,
        request_id=attachment.request_id,
        status=AudioTranscriptionStatus.CONCLUIDA,
        review_status=AudioTranscriptionReviewStatus.ACEITA,
        provider="test",
        model="test",
        transcript="fala",
        reviewed_transcript="fala revisada",
        segments=[{"text": "fala"}],
        requested_by_id=common_id,
    )

    with app.app_context():
        chunks, ocrs, transcriptions = _purge_attachment(attachment)

    assert (chunks, ocrs, transcriptions) == (0, 1, 1)
    assert attachment.scan_status == AttachmentScanStatus.BLOQUEADO
    assert attachment.ocr.status == DocumentOcrStatus.FALHOU
    assert attachment.ocr.extracted_text is None
    assert attachment.ocr.reviewed_text is None
    assert attachment.ocr.pages is None
    assert attachment.transcription.status == AudioTranscriptionStatus.FALHOU
    assert attachment.transcription.transcript is None
    assert attachment.transcription.reviewed_transcript is None
    assert attachment.transcription.segments is None
