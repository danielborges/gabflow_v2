import io
import sys
from types import SimpleNamespace

import pytest
from reportlab.pdfgen import canvas
from sqlalchemy import select

from app.ai.ocr import (
    NonRetryableOcrError,
    NoTextDetectedError,
    OcrResult,
    TesseractOcrProvider,
)
from app.extensions import db
from app.models import AuditLog
from app.outbox.service import process_batch

PASSWORD = "SenhaForte123!"  # noqa: S105


class FakeOcrProvider:
    provider = "TESSERACT"
    model = "tesseract-5"
    language = "por"

    def __init__(self, error=None):
        self.error = error

    def extract(self, _path, _mime_type):
        if self.error:
            raise self.error
        return OcrResult(
            text="PREFEITURA MUNICIPAL\nComprovante de atendimento",
            confidence=0.91,
            page_count=1,
            pages=[
                {
                    "pagina": 1,
                    "texto": "PREFEITURA MUNICIPAL\nComprovante de atendimento",
                    "confianca": 0.91,
                }
            ],
        )


def test_tesseract_provider_reports_normalized_confidence(monkeypatch):
    fake_pytesseract = SimpleNamespace(
        Output=SimpleNamespace(DICT="dict"),
        image_to_data=lambda *_args, **_kwargs: {
            "text": ["GabFlow", "OCR"],
            "conf": ["80", "100"],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
        },
    )
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)
    provider = TesseractOcrProvider("tesseract-5", "por", 25, 25_000_000)
    image = SimpleNamespace(size=(100, 100))

    result = provider._ocr_page(image, 1)

    assert result == {"pagina": 1, "texto": "GabFlow OCR", "confianca": 0.9}


def test_pdf_prefers_native_text_and_uses_selective_ocr(tmp_path, monkeypatch):
    pdf_path = tmp_path / "hibrido.pdf"
    pdf_path.write_bytes(
        _pdf_bytes(
            [
                "Texto legislativo nativo suficientemente longo para evitar OCR nesta página.",
                None,
                "Outra página nativa com conteúdo suficiente para extração direta pelo PDFium.",
            ]
        )
    )
    provider = TesseractOcrProvider(
        "tesseract-5",
        "por",
        maximum_pages=500,
        maximum_pixels=25_000_000,
        native_text_minimum_chars=40,
        batch_size=2,
    )
    ocr_pages = []

    def fake_ocr(_image, page_number):
        ocr_pages.append(page_number)
        return {
            "pagina": page_number,
            "texto": "Texto reconhecido somente na página digitalizada.",
            "confianca": 0.88,
        }

    monkeypatch.setattr(provider, "_ocr_page", fake_ocr)

    result = provider.extract(pdf_path, "application/pdf")

    assert result.page_count == 3
    assert ocr_pages == [2]
    assert [page["origem"] for page in result.pages] == ["NATIVO", "OCR", "NATIVO"]
    assert result.pages[0]["confianca"] == 1.0
    assert result.pages[1]["confianca"] == 0.88
    assert "Texto legislativo nativo" in result.text
    assert "página digitalizada" in result.text


def test_native_pdf_can_exceed_previous_ocr_page_limit(tmp_path, monkeypatch):
    pdf_path = tmp_path / "documento-extenso.pdf"
    pdf_path.write_bytes(
        _pdf_bytes(
            [
                f"Página {number} com conteúdo textual nativo suficiente para leitura direta."
                for number in range(1, 31)
            ]
        )
    )
    provider = TesseractOcrProvider(
        "tesseract-5",
        "por",
        maximum_pages=500,
        maximum_pixels=25_000_000,
        native_text_minimum_chars=40,
        batch_size=8,
    )
    monkeypatch.setattr(
        provider,
        "_ocr_page",
        lambda *_args: pytest.fail("OCR não deveria ser executado para páginas nativas."),
    )

    result = provider.extract(pdf_path, "application/pdf")

    assert result.page_count == 30
    assert all(page["origem"] == "NATIVO" for page in result.pages)


def test_pdf_hard_page_limit_remains_configurable(tmp_path):
    pdf_path = tmp_path / "acima-do-teto.pdf"
    pdf_path.write_bytes(_pdf_bytes(["Página com texto."] * 3))
    provider = TesseractOcrProvider(
        "tesseract-5",
        "por",
        maximum_pages=2,
        maximum_pixels=25_000_000,
    )

    with pytest.raises(NonRetryableOcrError, match="limite operacional de 2 páginas"):
        provider.extract(pdf_path, "application/pdf")


def _pdf_bytes(page_texts):
    stream = io.BytesIO()
    document = canvas.Canvas(stream)
    for text in page_texts:
        if text:
            document.drawString(72, 760, text)
        document.showPage()
    document.save()
    return stream.getvalue()


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
            "origem": "PRESENCIAL",
            "titulo": "Documento para OCR",
            "descricao": "Documento entregue pelo cidadão.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert response.status_code == 201
    return response.json


def _upload_image(client, csrf, request_id):
    return client.post(
        f"/api/v1/solicitacoes/{request_id}/anexos",
        data={
            "arquivo": (
                io.BytesIO(b"\x89PNG\r\n\x1a\nimagem-original-preservada"),
                "documento.png",
            )
        },
        headers={"X-CSRF-TOKEN": csrf},
        content_type="multipart/form-data",
    )


def test_document_is_processed_reviewed_and_original_is_preserved(app, client, monkeypatch):
    provider = FakeOcrProvider()
    monkeypatch.setattr("app.ai.ocr.ocr_provider", lambda: provider)
    csrf = _login(client)
    service_request = _request(client, csrf)

    uploaded = _upload_image(client, csrf, service_request["id"])

    assert uploaded.status_code == 201
    assert uploaded.json["ocr"]["status"] == "PENDENTE"
    assert uploaded.json["ocr"]["modelo"] == "tesseract-5"

    with app.app_context():
        result = process_batch("document-ocr-worker")
        assert result.failed == 0

    details = client.get(f"/api/v1/solicitacoes/{service_request['id']}").json
    attachment = details["anexos"][0]
    ocr = attachment["ocr"]
    assert ocr["status"] == "CONCLUIDO"
    assert ocr["confianca"] == 0.91
    assert ocr["paginas"] == 1
    assert "PREFEITURA" in ocr["textoGerado"]

    reviewed = client.post(
        f"/api/v1/ocr-documentos/{ocr['id']}/revisao",
        json={"acao": "EDITAR", "texto": "Prefeitura Municipal - comprovante."},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert reviewed.status_code == 200
    assert reviewed.json["statusRevisao"] == "EDITADO"
    assert reviewed.json["textoRevisado"].endswith("comprovante.")

    quality = client.get("/api/v1/ia/qualidade-triagem?dias=30")
    assert quality.json["cobertura"]["documentosProcessadosOcr"] == 1
    assert quality.json["cobertura"]["ocrRevisados"] == 1
    assert quality.json["cobertura"]["confiancaMediaOcr"] == 0.91

    download = client.get(attachment["downloadUrl"])
    assert download.data == b"\x89PNG\r\n\x1a\nimagem-original-preservada"
    with app.app_context():
        assert db.session.execute(
            select(AuditLog).where(AuditLog.action == "document.ocr.editar")
        ).scalar_one()


def test_failed_ocr_can_be_reprocessed(app, client, monkeypatch):
    provider = FakeOcrProvider(NoTextDetectedError("Nenhum texto reconhecível."))
    monkeypatch.setattr("app.ai.ocr.ocr_provider", lambda: provider)
    csrf = _login(client)
    service_request = _request(client, csrf)
    _upload_image(client, csrf, service_request["id"])

    with app.app_context():
        result = process_batch("document-ocr-failure-worker")
        assert result.failed == 1

    details = client.get(f"/api/v1/solicitacoes/{service_request['id']}").json
    ocr = details["anexos"][0]["ocr"]
    assert ocr["status"] == "FALHOU"
    assert "Nenhum texto" in ocr["erro"]

    reprocessed = client.post(
        f"/api/v1/ocr-documentos/{ocr['id']}/reprocessar",
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert reprocessed.status_code == 202
    assert reprocessed.json["status"] == "PENDENTE"


def test_ocr_review_is_isolated_by_tenant(app, client, monkeypatch):
    provider = FakeOcrProvider()
    monkeypatch.setattr("app.ai.ocr.ocr_provider", lambda: provider)
    csrf = _login(client)
    service_request = _request(client, csrf)
    uploaded = _upload_image(client, csrf, service_request["id"])
    with app.app_context():
        process_batch("document-ocr-tenant-worker")

    other_csrf = _login(client, "gabinete-b", "OutraSenha123!")
    response = client.post(
        f"/api/v1/ocr-documentos/{uploaded.json['ocr']['id']}/revisao",
        json={"acao": "ACEITAR"},
        headers={"X-CSRF-TOKEN": other_csrf},
    )
    assert response.status_code == 404
