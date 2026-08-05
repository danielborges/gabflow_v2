# ruff: noqa: E501

import csv
import hashlib
import io
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from html import escape as html_escape
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select

from app.audit import add_audit
from app.electoral.analytics import candidate_results, compare_candidates
from app.extensions import db
from app.models import (
    ElectoralGeneratedReport,
    ElectoralReportJob,
    OutboxEvent,
    User,
)
from app.security.encryption import read_plaintext, write_encrypted

REPORT_EVENT = "electoral.report.requested"
REPORT_COMPLETED_EVENT = "electoral.report.completed"
MIME_TYPES = {
    "PDF": "application/pdf",
    "CSV": "text/csv; charset=utf-8",
    "XLSX": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class NonRetryableReportError(RuntimeError):
    pass


def execute_report(job: ElectoralReportJob) -> None:
    if job.status == "REVOKED":
        raise NonRetryableReportError("A exportacao foi revogada.")
    job.status = "PROCESSING"
    job.started_at = datetime.now(UTC)
    job.error = None
    db.session.flush()

    payload = _report_payload(job)
    content = {
        "PDF": _build_pdf,
        "CSV": _build_csv,
        "XLSX": _build_xlsx,
    }[job.format](payload)
    now = datetime.now(UTC)
    report_id = uuid.uuid4()
    extension = job.format.lower()
    filename = f"inteligencia-eleitoral-{job.report_type}-{job.id}.{extension}"
    relative_key = Path("reports") / str(job.tenant_id) / f"{report_id}.{extension}.enc"
    target = _report_path(relative_key.as_posix(), require_file=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    encryption = write_encrypted(target, content, f"tenant:{job.tenant_id}:electoral-report")

    existing = db.session.execute(
        select(ElectoralGeneratedReport).where(ElectoralGeneratedReport.report_job_id == job.id)
    ).scalar_one_or_none()
    if existing is None:
        existing = ElectoralGeneratedReport(
            id=report_id,
            tenant_id=job.tenant_id,
            report_job_id=job.id,
            storage_key=relative_key.as_posix(),
            filename=filename,
            mime_type=MIME_TYPES[job.format],
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            expires_at=now + timedelta(days=current_app.config["ELECTORAL_REPORT_RETENTION_DAYS"]),
            **encryption,
        )
        db.session.add(existing)
    else:
        existing.storage_key = relative_key.as_posix()
        existing.filename = filename
        existing.mime_type = MIME_TYPES[job.format]
        existing.size_bytes = len(content)
        existing.sha256 = hashlib.sha256(content).hexdigest()
        existing.expires_at = now + timedelta(
            days=current_app.config["ELECTORAL_REPORT_RETENTION_DAYS"]
        )
        existing.revoked_at = None
        for key, value in encryption.items():
            setattr(existing, key, value)

    job.source_metadata = payload["source_metadata"]
    job.status = "COMPLETED"
    job.completed_at = now
    db.session.add(
        OutboxEvent(
            tenant_id=job.tenant_id,
            event_type=REPORT_COMPLETED_EVENT,
            aggregate_type="electoral_report_job",
            aggregate_id=str(job.id),
            payload={
                "jobId": str(job.id),
                "reportId": str(existing.id),
                "requestedById": str(job.requested_by_id),
                "schemaVersion": 1,
                "idempotencyKey": f"{job.id}:completed",
            },
        )
    )
    add_audit(
        job.tenant_id,
        job.requested_by_id,
        "electoral.report.generated",
        "electoral_report_job",
        job.id,
        after={
            "format": job.format,
            "reportType": job.report_type,
            "datasetVersion": payload["source_metadata"].get("dataset_version"),
            "sha256": existing.sha256,
        },
    )


def fail_report(job: ElectoralReportJob, error_message: str) -> None:
    if job.status != "REVOKED":
        job.status = "FAILED"
        job.error = error_message[:2000]
        job.completed_at = datetime.now(UTC)


def report_bytes(report: ElectoralGeneratedReport) -> bytes:
    path = _report_path(report.storage_key)
    return read_plaintext(path, f"tenant:{report.tenant_id}:electoral-report")


def signed_report_token(report: ElectoralGeneratedReport) -> str:
    return _download_serializer().dumps(
        {
            "report_id": str(report.id),
            "tenant_id": str(report.tenant_id),
            "purpose": "electoral-report-download",
        }
    )


def verify_report_token(token: str, report_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
    try:
        data = _download_serializer().loads(
            token,
            max_age=current_app.config["ELECTORAL_REPORT_LINK_MAX_AGE_SECONDS"],
        )
    except (BadSignature, SignatureExpired):
        return False
    return data == {
        "report_id": str(report_id),
        "tenant_id": str(tenant_id),
        "purpose": "electoral-report-download",
    }


def cleanup_expired_reports(tenant_id: uuid.UUID) -> int:
    now = datetime.now(UTC)
    reports = list(
        db.session.scalars(
            select(ElectoralGeneratedReport).where(
                ElectoralGeneratedReport.tenant_id == tenant_id,
                ElectoralGeneratedReport.expires_at <= now,
                ElectoralGeneratedReport.revoked_at.is_(None),
            )
        )
    )
    for report in reports:
        report.revoked_at = now
        try:
            _report_path(report.storage_key).unlink()
        except FileNotFoundError:
            pass
        job = db.session.get(ElectoralReportJob, report.report_job_id)
        if job and job.status != "REVOKED":
            job.status = "REVOKED"
            job.revoked_at = now
            add_audit(
                tenant_id,
                job.requested_by_id,
                "electoral.report.expired",
                "electoral_report_job",
                job.id,
                after={"retentionDays": current_app.config["ELECTORAL_REPORT_RETENTION_DAYS"]},
            )
    return len(reports)


def _report_payload(job: ElectoralReportJob) -> dict:
    filters = job.filters
    try:
        election_id = uuid.UUID(filters["election_id"])
        candidate_ids = [uuid.UUID(value) for value in filters["candidate_ids"]]
    except (KeyError, TypeError, ValueError) as error:
        raise NonRetryableReportError("Filtros persistidos da exportacao sao invalidos.") from error
    level = filters.get("level", "municipality")
    municipality_code = filters.get("municipality_code")
    requester = db.session.get(User, job.requested_by_id)
    if requester is None or requester.tenant_id != job.tenant_id:
        raise NonRetryableReportError("Autor da exportacao nao encontrado.")

    if job.report_type == "candidate":
        result = candidate_results(
            candidate_ids[0],
            election_id,
            level,
            municipality_code=municipality_code,
            page=1,
            per_page=current_app.config["ELECTORAL_REPORT_MAX_ROWS"],
            sort="name",
            order="asc",
        )
        if result is None:
            raise NonRetryableReportError("Candidatura publicada nao encontrada.")
        candidate = result["candidate"]
        columns = ["Territorio", "Codigo", "Votos", "Participacao", "Posicao", "Denominador"]
        rows = [
            [
                item["territory_name"],
                item["territory_code"],
                item["votes"],
                item["share"],
                item["rank"],
                item["denominator_value"],
            ]
            for item in result["items"]
        ]
        title = f"Resultado eleitoral - {candidate['ballot_name']}"
        source_metadata = {
            "source": result["source"],
            "source_hash": result["source_hash"],
            "dataset_version": result["dataset_version"],
            "denominator": result["denominator"],
            "candidate_ids": [str(candidate_ids[0])],
        }
    else:
        result, error = compare_candidates(
            candidate_ids,
            election_id,
            level,
            municipality_code=municipality_code,
        )
        if result is None:
            raise NonRetryableReportError(error or "Comparacao publicada nao encontrada.")
        names = {item["id"]: item["ballot_name"] for item in result["candidates"]}
        columns = [
            "Territorio",
            "Codigo",
            "Candidato",
            "Votos",
            "Participacao",
            "Posicao",
            "Denominador",
        ]
        rows = []
        for territory in result["items"]:
            for series in territory["series"]:
                rows.append(
                    [
                        territory["territory_name"],
                        territory["territory_code"],
                        names[series["candidate_id"]],
                        series["votes"],
                        series["share"],
                        series["rank"],
                        territory["denominator_value"],
                    ]
                )
        title = "Comparacao eleitoral - " + ", ".join(
            candidate["ballot_name"] for candidate in result["candidates"]
        )
        source_metadata = {
            "source": result["source"],
            "dataset_version": result["dataset_version"],
            "denominator": result["denominator"],
            "candidate_ids": [str(value) for value in candidate_ids],
        }
    if len(rows) > current_app.config["ELECTORAL_REPORT_MAX_ROWS"]:
        raise NonRetryableReportError("A exportacao excede o limite de linhas permitido.")
    return {
        "title": title,
        "author": requester.name,
        "generated_at": datetime.now(UTC),
        "purpose": job.purpose,
        "filters": filters,
        "source_metadata": source_metadata,
        "columns": columns,
        "rows": rows,
    }


def _build_csv(payload: dict) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(["Relatorio", payload["title"]])
    writer.writerow(["Autor", payload["author"]])
    writer.writerow(["Gerado em UTC", payload["generated_at"].isoformat()])
    writer.writerow(["Finalidade", payload["purpose"]])
    writer.writerow(["Fonte", payload["source_metadata"].get("source", "")])
    writer.writerow(["Versao do dataset", payload["source_metadata"].get("dataset_version", "")])
    writer.writerow([])
    writer.writerow(payload["columns"])
    writer.writerows(payload["rows"])
    return b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")


def _build_pdf(payload: dict) -> bytes:
    stream = io.BytesIO()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ElectoralTitle",
        parent=styles["Title"],
        textColor=colors.HexColor("#123B5D"),
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
    )
    body = styles["BodyText"]
    table_header = ParagraphStyle(
        "ElectoralTableHeader",
        parent=body,
        textColor=colors.white,
        fontName="Helvetica-Bold",
    )
    story = [
        Paragraph(html_escape(payload["title"]), title_style),
        Spacer(1, 0.35 * cm),
        Paragraph(f"<b>Autor:</b> {html_escape(payload['author'])}", body),
        Paragraph(f"<b>Data/hora UTC:</b> {payload['generated_at'].isoformat()}", body),
        Paragraph(f"<b>Finalidade:</b> {html_escape(payload['purpose'])}", body),
        Paragraph(
            f"<b>Fonte:</b> {html_escape(payload['source_metadata'].get('source', ''))}", body
        ),
        Paragraph(
            "<b>Versão do dataset:</b> "
            + html_escape(payload["source_metadata"].get("dataset_version", "")),
            body,
        ),
        Spacer(1, 0.25 * cm),
        Paragraph(
            "<b>Metodologia:</b> dados oficiais agregados. Percentuais reproduzem o "
            "denominador registrado no catálogo; a exportação não permite inferir voto individual.",
            body,
        ),
        Spacer(1, 0.35 * cm),
    ]
    table_data = [
        [Paragraph(html_escape(str(value)), table_header) for value in payload["columns"]]
    ]
    for row in payload["rows"]:
        formatted = []
        for index, value in enumerate(row):
            if payload["columns"][index] == "Participacao":
                value = f"{float(value) * 100:.2f}%"
            formatted.append(Paragraph(html_escape(str(value)), body))
        table_data.append(formatted)
    table = Table(table_data, repeatRows=1, hAlign="CENTER")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#123B5D")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F6F8")]),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor("#123B5D")),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)

    def decorate(canvas, document):
        canvas.saveState()
        width, height = landscape(A4)
        canvas.setFillColor(colors.Color(0.2, 0.35, 0.45, alpha=0.09))
        canvas.setFont("Helvetica-Bold", 42)
        canvas.translate(width / 2, height / 2)
        canvas.rotate(28)
        canvas.drawCentredString(0, 0, "USO INTERNO - GABFLOW")
        canvas.rotate(-28)
        canvas.translate(-width / 2, -height / 2)
        canvas.setFillColor(colors.HexColor("#52616B"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(1.4 * cm, 0.8 * cm, "Inteligência Eleitoral - dados agregados")
        canvas.drawRightString(width - 1.4 * cm, 0.8 * cm, f"Página {document.page}")
        canvas.restoreState()

    SimpleDocTemplate(
        stream,
        pagesize=landscape(A4),
        rightMargin=1.4 * cm,
        leftMargin=1.4 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
        title=payload["title"],
        author=payload["author"],
    ).build(story, onFirstPage=decorate, onLaterPages=decorate)
    return stream.getvalue()


def _build_xlsx(payload: dict) -> bytes:
    rows = [
        [payload["title"]],
        ["Autor", payload["author"]],
        ["Gerado em UTC", payload["generated_at"].isoformat()],
        ["Finalidade", payload["purpose"]],
        ["Fonte", payload["source_metadata"].get("source", "")],
        ["Versao do dataset", payload["source_metadata"].get("dataset_version", "")],
        [],
        payload["columns"],
        *payload["rows"],
    ]
    sheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            reference = f"{_column_name(column_index)}{row_index}"
            style = (
                1
                if row_index == 1
                else 2
                if row_index <= 6 and column_index == 1
                else 3
                if row_index == 8
                else 0
            )
            if row_index > 8 and payload["columns"][column_index - 1] == "Participacao":
                style = 5
            elif row_index > 8 and isinstance(value, int | float):
                style = 4
            if isinstance(value, int | float) and not isinstance(value, bool):
                cells.append(f'<c r="{reference}" s="{style}"><v>{value}</v></c>')
            else:
                cells.append(
                    f'<c r="{reference}" t="inlineStr" s="{style}"><is><t xml:space="preserve">'
                    f"{xml_escape(str(value))}</t></is></c>"
                )
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    max_column = max(len(row) for row in rows)
    auto_filter = (
        f'<autoFilter ref="A8:{_column_name(max_column)}{len(rows)}"/>' if len(rows) > 8 else ""
    )
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView showGridLines="0" workbookViewId="0">'
        '<pane ySplit="8" topLeftCell="A9" activePane="bottomLeft" state="frozen"/>'
        "</sheetView></sheetViews>"
        f'<dimension ref="A1:{_column_name(max_column)}{len(rows)}"/>'
        '<cols><col min="1" max="1" width="28" customWidth="1"/>'
        f'<col min="2" max="{max_column}" width="20" customWidth="1"/></cols>'
        f"<sheetData>{''.join(sheet_rows)}</sheetData>{auto_filter}</worksheet>"
    )
    files = {
        "[Content_Types].xml": _XLSX_CONTENT_TYPES,
        "_rels/.rels": _XLSX_ROOT_RELS,
        "docProps/app.xml": _XLSX_APP,
        "docProps/core.xml": _xlsx_core(payload),
        "xl/workbook.xml": _XLSX_WORKBOOK,
        "xl/_rels/workbook.xml.rels": _XLSX_WORKBOOK_RELS,
        "xl/styles.xml": _XLSX_STYLES,
        "xl/worksheets/sheet1.xml": worksheet,
    }
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return stream.getvalue()


def _report_path(storage_key: str, *, require_file: bool = True) -> Path:
    root = (Path(current_app.config["ELECTORAL_STORAGE_PATH"]) / "private").resolve()
    target = (root / storage_key).resolve()
    if root not in target.parents:
        raise NonRetryableReportError("Destino de relatorio invalido.")
    if require_file and not target.is_file():
        raise NonRetryableReportError("Arquivo do relatorio nao encontrado.")
    return target


def _download_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="electoral-report")


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _xlsx_core(payload: dict) -> str:
    timestamp = payload["generated_at"].strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{xml_escape(payload['title'])}</dc:title>"
        f"<dc:creator>{xml_escape(payload['author'])}</dc:creator>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:created>'
        "</cp:coreProperties>"
    )


_XLSX_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""
_XLSX_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""
_XLSX_APP = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>GabFlow</Application></Properties>"""
_XLSX_WORKBOOK = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Relatorio" sheetId="1" r:id="rId1"/></sheets></workbook>"""
_XLSX_WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""
_XLSX_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="3"><font><sz val="11"/><name val="Aptos"/></font><font><b/><color rgb="FF123B5D"/><sz val="16"/><name val="Aptos Display"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Aptos"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF123B5D"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="2"><border/><border><bottom style="thin"><color rgb="FFD6E0E6"/></bottom></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="6"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyFont="1"><alignment wrapText="1"/></xf><xf numFmtId="0" fontId="2" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1"/><xf numFmtId="3" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1"/><xf numFmtId="10" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1"/></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""
