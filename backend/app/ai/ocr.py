import re
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
        native_text_minimum_chars: int = 40,
        batch_size: int = 8,
    ) -> None:
        self.model = model
        self.language = language
        self.maximum_pages = maximum_pages
        self.maximum_pixels = maximum_pixels
        self.native_text_minimum_chars = max(1, native_text_minimum_chars)
        self.batch_size = max(1, batch_size)

    def extract(self, path: Path, mime_type: str) -> OcrResult:
        if mime_type == "application/pdf":
            pages = self._extract_pdf(path)
        elif mime_type in {"image/jpeg", "image/png"}:
            page = self._extract_image(path, 1)
            page["origem"] = "OCR"
            pages = [page]
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
                    f"O PDF excede o limite operacional de {self.maximum_pages} páginas."
                )

            results: list[dict | None] = [None] * page_count
            fallback_indexes = []
            for index in range(page_count):
                page = document[index]
                try:
                    native_text = self._extract_native_text(page)
                finally:
                    page.close()
                if self._has_useful_native_text(native_text):
                    results[index] = {
                        "pagina": index + 1,
                        "texto": native_text,
                        "confianca": 1.0,
                        "origem": "NATIVO",
                    }
                else:
                    fallback_indexes.append(index)

            for batch_start in range(0, len(fallback_indexes), self.batch_size):
                batch = fallback_indexes[batch_start : batch_start + self.batch_size]
                for index in batch:
                    page = document[index]
                    try:
                        image = page.render(scale=2).to_pil().convert("RGB")
                        try:
                            result = self._ocr_page(image, index + 1)
                            result["origem"] = "OCR"
                            results[index] = result
                        finally:
                            image.close()
                    finally:
                        page.close()
            return [result for result in results if result is not None]
        except NonRetryableOcrError:
            raise
        except Exception as error:
            raise OcrError("Falha ao extrair texto ou renderizar o PDF.") from error
        finally:
            document.close()

    def _extract_native_text(self, page) -> str:
        text_page = None
        try:
            text_page = page.get_textpage()
            return self._normalize_native_text(text_page.get_text_bounded())
        except Exception:
            return ""
        finally:
            if text_page is not None:
                text_page.close()

    def _has_useful_native_text(self, text: str) -> bool:
        compact = re.sub(r"\s+", "", text)
        return len(compact) >= self.native_text_minimum_chars

    @staticmethod
    def _normalize_native_text(text: str) -> str:
        lines = [
            re.sub(r"[ \t]+", " ", line).strip() for line in str(text).splitlines()
        ]
        return "\n".join(line for line in lines if line).strip()

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
        native_text_minimum_chars=current_app.config["DOCUMENT_OCR_NATIVE_MIN_CHARS"],
        batch_size=current_app.config["DOCUMENT_OCR_BATCH_SIZE"],
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
