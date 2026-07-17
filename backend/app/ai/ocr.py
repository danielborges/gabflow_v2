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
    AuditLog,
    DocumentOcr,
    DocumentOcrStatus,
    NotificationType,
    OutboxEvent,
    RequestHistory,
)
from app.notifications.service import notify_user

DOCUMENT_OCR_EVENT = "OcrDocumentoSolicitacao"
OCR_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png"}


@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence: float
    page_count: int
    pages: list[dict]


class OcrProvider(Protocol):
    provider: str
    model: str
    language: str

    def extract(self, path: Path, mime_type: str) -> OcrResult: ...


class OcrError(RuntimeError):
    pass


class NonRetryableOcrError(OcrError):
    pass


class NoTextDetectedError(NonRetryableOcrError):
    pass


class TesseractOcrProvider:
    provider = "TESSERACT"

    def __init__(
        self,
        model: str,
        language: str,
        maximum_pages: int,
        maximum_pixels: int,
    ) -> None:
        self.model = model
        self.language = language
        self.maximum_pages = maximum_pages
        self.maximum_pixels = maximum_pixels

    def extract(self, path: Path, mime_type: str) -> OcrResult:
        if mime_type == "application/pdf":
            pages = self._extract_pdf(path)
        elif mime_type in {"image/jpeg", "image/png"}:
            pages = [self._extract_image(path, 1)]
        else:
            raise NonRetryableOcrError("Tipo de documento não compatível com OCR.")

        pages_with_text = [page for page in pages if page["texto"]]
        if not pages_with_text:
            raise NoTextDetectedError("Nenhum texto reconhecível foi encontrado no documento.")
        text = "\n\n".join(page["texto"] for page in pages_with_text)
        confidence = sum(page["confianca"] for page in pages_with_text) / len(pages_with_text)
        return OcrResult(
            text=text,
            confidence=round(confidence, 4),
            page_count=len(pages),
            pages=pages,
        )

    def _extract_image(self, path: Path, page_number: int) -> dict:
        try:
            from PIL import Image, ImageOps, UnidentifiedImageError

            with Image.open(path) as source:
                source.load()
                image = ImageOps.exif_transpose(source).convert("RGB")
        except (OSError, UnidentifiedImageError) as error:
            raise NonRetryableOcrError("O arquivo não contém uma imagem válida.") from error
        try:
            return self._ocr_page(image, page_number)
        finally:
            image.close()

    def _extract_pdf(self, path: Path) -> list[dict]:
        try:
            import pypdfium2 as pdfium

            document = pdfium.PdfDocument(str(path))
        except Exception as error:
            raise NonRetryableOcrError("O arquivo não contém um PDF válido.") from error
        try:
            page_count = len(document)
            if page_count == 0:
                raise NonRetryableOcrError("O PDF não possui páginas.")
            if page_count > self.maximum_pages:
                raise NonRetryableOcrError(
                    f"O PDF excede o limite de {self.maximum_pages} páginas para OCR."
                )
            results = []
            for index in range(page_count):
                page = document[index]
                try:
                    image = page.render(scale=2).to_pil().convert("RGB")
                    try:
                        results.append(self._ocr_page(image, index + 1))
                    finally:
                        image.close()
                finally:
                    page.close()
            return results
        except NonRetryableOcrError:
            raise
        except Exception as error:
            raise OcrError("Falha ao renderizar o PDF para OCR local.") from error
        finally:
            document.close()

    def _ocr_page(self, image, page_number: int) -> dict:
        width, height = image.size
        if width * height > self.maximum_pixels:
            raise NonRetryableOcrError(
                "A imagem excede o limite de resolução permitido para OCR."
            )
        try:
            import pytesseract
            from pytesseract import Output

            data = pytesseract.image_to_data(
                image,
                lang=self.language,
                config="--oem 1 --psm 6",
                output_type=Output.DICT,
            )
        except pytesseract.TesseractNotFoundError as error:
            raise OcrError("O mecanismo local de OCR não está disponível.") from error
        except pytesseract.TesseractError as error:
            raise OcrError("Falha ao executar o OCR localmente.") from error

        lines: dict[tuple[int, int, int], list[str]] = {}
        confidences: list[float] = []
        for index, raw_text in enumerate(data.get("text", [])):
            text = str(raw_text).strip()
            if not text:
                continue
            try:
                confidence = float(data["conf"][index])
            except (KeyError, TypeError, ValueError):
                confidence = -1
            if confidence >= 0:
                confidences.append(confidence)
            key = (
                int(data.get("block_num", [0])[index]),
                int(data.get("par_num", [0])[index]),
                int(data.get("line_num", [index])[index]),
            )
            lines.setdefault(key, []).append(text)
        page_text = "\n".join(" ".join(words) for words in lines.values())
        average = sum(confidences) / len(confidences) / 100 if confidences else 0.0
        return {
            "pagina": page_number,
            "texto": page_text,
            "confianca": round(average, 4),
        }


def ocr_provider() -> OcrProvider:
    provider = current_app.config["DOCUMENT_OCR_PROVIDER"].lower()
    if provider != "tesseract":
        raise RuntimeError(f"Provedor de OCR não suportado: {provider}.")
    return TesseractOcrProvider(
        model=current_app.config["DOCUMENT_OCR_MODEL"],
        language=current_app.config["DOCUMENT_OCR_LANGUAGE"],
        maximum_pages=current_app.config["DOCUMENT_OCR_MAX_PAGES"],
        maximum_pixels=current_app.config["DOCUMENT_OCR_MAX_PIXELS"],
    )


def enqueue_document_ocr(
    attachment: Attachment,
    requested_by_id: uuid.UUID,
) -> DocumentOcr | None:
    if attachment.mime_type not in OCR_MIME_TYPES:
        return None
    provider = ocr_provider()
    ocr = DocumentOcr(
        tenant_id=attachment.tenant_id,
        attachment_id=attachment.id,
        request_id=attachment.request_id,
        provider=provider.provider,
        model=provider.model,
        language=provider.language,
        requested_by_id=requested_by_id,
    )
    db.session.add(ocr)
    db.session.flush()
    db.session.add(
        OutboxEvent(
            tenant_id=attachment.tenant_id,
            event_type=DOCUMENT_OCR_EVENT,
            aggregate_type="OcrDocumento",
            aggregate_id=str(ocr.id),
            payload={"ocrId": str(ocr.id)},
        )
    )
    return ocr


def requeue_document_ocr(ocr: DocumentOcr) -> None:
    ocr.status = DocumentOcrStatus.PENDENTE
    ocr.error = None
    ocr.started_at = None
    ocr.completed_at = None
    db.session.add(
        OutboxEvent(
            tenant_id=ocr.tenant_id,
            event_type=DOCUMENT_OCR_EVENT,
            aggregate_type="OcrDocumento",
            aggregate_id=str(ocr.id),
            payload={"ocrId": str(ocr.id)},
        )
    )


def execute_document_ocr(ocr: DocumentOcr) -> None:
    attachment = db.session.get(Attachment, ocr.attachment_id)
    if (
        attachment is None
        or attachment.tenant_id != ocr.tenant_id
        or attachment.scan_status != AttachmentScanStatus.LIMPO
        or attachment.mime_type not in OCR_MIME_TYPES
    ):
        raise OcrError("Anexo válido para OCR não foi encontrado.")

    ocr.status = DocumentOcrStatus.PROCESSANDO
    ocr.started_at = datetime.now(UTC)
    db.session.flush()
    result = ocr_provider().extract(
        attachment_path(attachment.storage_key), attachment.mime_type
    )
    ocr.extracted_text = result.text
    ocr.confidence = result.confidence
    ocr.page_count = result.page_count
    ocr.pages = result.pages
    ocr.status = DocumentOcrStatus.CONCLUIDO
    ocr.completed_at = datetime.now(UTC)
    ocr.error = None
    details = {
        "ocrId": str(ocr.id),
        "anexoId": str(attachment.id),
        "modelo": ocr.model,
        "confianca": ocr.confidence,
        "paginas": ocr.page_count,
    }
    db.session.add(
        RequestHistory(
            tenant_id=ocr.tenant_id,
            request_id=ocr.request_id,
            user_id=ocr.requested_by_id,
            action="document.ocr.completed",
            changes=details,
        )
    )
    db.session.add(
        AuditLog(
            tenant_id=ocr.tenant_id,
            user_id=ocr.requested_by_id,
            action="document.ocr.completed",
            entity_type="document_ocr",
            entity_id=str(ocr.id),
            after=details,
        )
    )
    db.session.add(
        OutboxEvent(
            tenant_id=ocr.tenant_id,
            event_type="OcrDocumentoConcluido",
            aggregate_type="Solicitacao",
            aggregate_id=str(ocr.request_id),
            payload=details,
        )
    )
    notify_user(
        ocr.tenant_id,
        ocr.requested_by_id,
        NotificationType.SISTEMA,
        "OCR de documento concluído",
        f"O texto de {attachment.original_name} está pronto para revisão.",
        "document_ocr",
        ocr.id,
    )


def ocr_data(ocr: DocumentOcr | None) -> dict | None:
    if ocr is None:
        return None
    return {
        "id": str(ocr.id),
        "status": ocr.status.value,
        "statusRevisao": ocr.review_status.value,
        "provedor": ocr.provider,
        "modelo": ocr.model,
        "idioma": ocr.language,
        "confianca": ocr.confidence,
        "paginas": ocr.page_count,
        "textoGerado": ocr.extracted_text,
        "textoRevisado": ocr.reviewed_text,
        "detalhesPaginas": ocr.pages or [],
        "erro": ocr.error,
        "criadoEm": ocr.created_at.isoformat(),
        "concluidoEm": ocr.completed_at.isoformat() if ocr.completed_at else None,
        "revisadoEm": ocr.reviewed_at.isoformat() if ocr.reviewed_at else None,
    }
