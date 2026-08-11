from datetime import datetime
from html import escape as html_escape
from io import BytesIO
from pathlib import Path

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models import AgendaEvent, AgendaEventStatus, AgendaEventType, Tenant

NAVY = colors.HexColor("#08285C")
BLUE = colors.HexColor("#176FAE")
CYAN = colors.HexColor("#24A7C7")
INK = colors.HexColor("#18324A")
MUTED = colors.HexColor("#687C90")
LINE = colors.HexColor("#DCE5ED")
SURFACE = colors.HexColor("#F4F8FB")
PURPLE = colors.HexColor("#7548A7")
PURPLE_BG = colors.HexColor("#F1EAF9")
AMBER = colors.HexColor("#A86300")
AMBER_BG = colors.HexColor("#FFF3D9")
GREEN = colors.HexColor("#16805B")
GREEN_BG = colors.HexColor("#E7F6EF")

FONT_DIR = Path(reportlab.__file__).resolve().parent / "fonts"
pdfmetrics.registerFont(TTFont("AgendaSans", str(FONT_DIR / "Vera.ttf")))
pdfmetrics.registerFont(TTFont("AgendaSans-Bold", str(FONT_DIR / "VeraBd.ttf")))

DAY_NAMES = ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")
TYPE_LABELS = {
    AgendaEventType.COMPROMISSO: "Compromisso",
    AgendaEventType.VISITA: "Visita",
    AgendaEventType.REUNIAO: "Reunião",
    AgendaEventType.AUDIENCIA: "Audiência",
    AgendaEventType.FISCALIZACAO: "Fiscalização",
}


def weekly_agenda_pdf(
    tenant: Tenant,
    events: list[AgendaEvent],
    starts_at: datetime,
    ends_at: datetime,
    generated_by: str,
) -> bytes:
    stream = BytesIO()
    styles = _styles()
    document = SimpleDocTemplate(
        stream,
        pagesize=A4,
        leftMargin=1.45 * cm,
        rightMargin=1.45 * cm,
        topMargin=1.55 * cm,
        bottomMargin=1.45 * cm,
        title="Agenda executiva semanal",
        author="GabFlow",
        subject="Compromissos semanais do gabinete",
    )
    events = sorted(events, key=lambda item: item.starts_at)
    story = []
    story.extend(_hero(tenant, starts_at, ends_at, styles))
    story.extend(_summary(events, styles))
    story.extend(_week_rhythm(events, starts_at, styles))
    story.extend(_executive_highlights(events, styles))
    story.append(PageBreak())
    story.extend(_schedule(events, starts_at, styles))

    generated_at = datetime.now(starts_at.tzinfo)

    def decorate(canvas, doc):
        canvas.saveState()
        width, height = A4
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(1.45 * cm, height - 1.05 * cm, width - 1.45 * cm, height - 1.05 * cm)
        canvas.setFont("AgendaSans-Bold", 7.5)
        canvas.setFillColor(NAVY)
        canvas.drawString(1.45 * cm, height - 0.78 * cm, "GabFlow  |  AGENDA EXECUTIVA")
        canvas.setFont("AgendaSans", 7)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(
            width - 1.45 * cm,
            height - 0.78 * cm,
            f"{_date(starts_at)} a {_date(ends_at)}",
        )
        canvas.line(1.45 * cm, 0.92 * cm, width - 1.45 * cm, 0.92 * cm)
        canvas.drawString(
            1.45 * cm,
            0.58 * cm,
            f"Gerado em {_datetime(generated_at)} por {generated_by}",
        )
        canvas.drawRightString(width - 1.45 * cm, 0.58 * cm, f"Página {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return stream.getvalue()


def _hero(tenant: Tenant, starts_at: datetime, ends_at: datetime, styles: dict) -> list:
    office = (tenant.visual_identity or {}).get("dadosInstitucionais", {}).get(
        "nomeGabinete"
    ) or tenant.name
    representative = tenant.representative_info or {}
    representative_name = representative.get("nome") or representative.get("nomeParlamentar")
    jurisdiction = tenant.jurisdiction_name or "Mandato parlamentar"
    identity = " • ".join(value for value in (representative_name, jurisdiction) if value)
    title = Paragraph("Agenda executiva<br/>da semana", styles["hero_title"])
    period = Paragraph(
        f"<b>{html_escape(_date(starts_at))}</b> a <b>{html_escape(_date(ends_at))}</b>",
        styles["hero_period"],
    )
    card = Table(
        [
            [
                title,
                [
                    Paragraph(html_escape(office), styles["office"]),
                    Paragraph(html_escape(identity), styles["identity"]),
                    Spacer(1, 0.18 * cm),
                    period,
                ],
            ]
        ],
        colWidths=[9.4 * cm, 7.0 * cm],
        rowHeights=[4.0 * cm],
    )
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, 0), 0.55 * cm),
                ("RIGHTPADDING", (0, 0), (0, 0), 0.3 * cm),
                ("LEFTPADDING", (1, 0), (1, 0), 0.55 * cm),
                ("RIGHTPADDING", (1, 0), (1, 0), 0.55 * cm),
                ("LINEBEFORE", (1, 0), (1, 0), 0.6, colors.HexColor("#42628C")),
                ("ROUNDEDCORNERS", [12]),
            ]
        )
    )
    return [Spacer(1, 0.25 * cm), card, Spacer(1, 0.55 * cm)]


def _summary(events: list[AgendaEvent], styles: dict) -> list:
    total = len(events)
    representative = sum(item.representative_presence for item in events)
    field = sum(bool(item.location) for item in events)
    participants = {
        str(participant.get("id") or participant.get("nome"))
        for event in events
        for participant in (event.participants or [])
        if isinstance(participant, dict)
    }
    cards = [
        _metric_card(str(total), "compromissos", BLUE, colors.HexColor("#E8F3FA"), styles),
        _metric_card(str(representative), "com parlamentar", PURPLE, PURPLE_BG, styles),
        _metric_card(str(field), "com local definido", AMBER, AMBER_BG, styles),
        _metric_card(str(len(participants)), "pessoas mobilizadas", GREEN, GREEN_BG, styles),
    ]
    table = Table([cards], colWidths=[4.1 * cm] * 4, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0.16 * cm),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return [
        _section_title("Visão geral", "Capacidade e presença previstas para o período.", styles),
        table,
        Spacer(1, 0.45 * cm),
    ]


def _metric_card(value: str, label: str, tone, background, styles: dict):
    table = Table(
        [
            [
                Paragraph(
                    value,
                    ParagraphStyle("MetricValue", parent=styles["metric_value"], textColor=tone),
                ),
                Paragraph(html_escape(label), styles["metric_label"]),
            ]
        ],
        colWidths=[1.25 * cm, 2.55 * cm],
        rowHeights=[1.35 * cm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, 0), 0.25 * cm),
                ("RIGHTPADDING", (0, 0), (0, 0), 0),
                ("LEFTPADDING", (1, 0), (1, 0), 0.08 * cm),
                ("RIGHTPADDING", (1, 0), (1, 0), 0.2 * cm),
                ("ROUNDEDCORNERS", [8]),
            ]
        )
    )
    return table


def _week_rhythm(events: list[AgendaEvent], starts_at: datetime, styles: dict) -> list:
    counts = []
    for index in range(7):
        day = starts_at.date().toordinal() + index
        counts.append(sum(item.starts_at.date().toordinal() == day for item in events))
    maximum = max(counts, default=0) or 1
    cells = []
    for index, count in enumerate(counts):
        bar_width = 0.22 + (count / maximum) * 1.35
        bar = Table([[""]], colWidths=[bar_width * cm], rowHeights=[0.13 * cm])
        bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CYAN if count else LINE)]))
        cells.append(
            [
                Paragraph(DAY_NAMES[index][:3].upper(), styles["day_short"]),
                Paragraph(str(count), styles["day_count"]),
                bar,
            ]
        )
    table = Table([cells], colWidths=[2.34 * cm] * 7, rowHeights=[1.25 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                ("ROUNDEDCORNERS", [8]),
            ]
        )
    )
    return [
        _section_title("Ritmo da semana", "Distribuição dos compromissos por dia.", styles),
        table,
        Spacer(1, 0.48 * cm),
    ]


def _executive_highlights(events: list[AgendaEvent], styles: dict) -> list:
    busiest = None
    if events:
        counts = {}
        for event in events:
            counts[event.starts_at.date()] = counts.get(event.starts_at.date(), 0) + 1
        busiest = max(counts, key=counts.get)
    missing_location = sum(not item.location for item in events)
    without_participants = sum(not item.participants for item in events)
    representative = [item for item in events if item.representative_presence]
    insights = [
        (
            "PICO DA AGENDA",
            f"{_weekday_date(busiest)} concentra o maior volume."
            if busiest
            else "Semana sem compromissos registrados.",
            BLUE,
        ),
        (
            "PRESENÇA PARLAMENTAR",
            f"{len(representative)} compromisso(s) exigem atenção direta do parlamentar.",
            PURPLE,
        ),
        (
            "PREPARAÇÃO",
            f"{missing_location} sem local e {without_participants} sem participantes definidos.",
            AMBER if missing_location or without_participants else GREEN,
        ),
    ]
    cards = []
    for label, text, tone in insights:
        cards.append(
            Table(
                [
                    [
                        Paragraph(
                            label,
                            ParagraphStyle(
                                "InsightLabel", parent=styles["insight_label"], textColor=tone
                            ),
                        ),
                        Paragraph(html_escape(text), styles["insight_text"]),
                    ]
                ],
                colWidths=[4.1 * cm, 11.85 * cm],
                rowHeights=[0.85 * cm],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                        ("LINEBEFORE", (0, 0), (0, 0), 3, tone),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0.24 * cm),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0.24 * cm),
                    ]
                ),
            )
        )
        cards.append(Spacer(1, 0.12 * cm))
    return [
        _section_title("Leitura executiva", "Pontos de atenção para preparar a equipe.", styles),
        *cards,
    ]


def _schedule(events: list[AgendaEvent], starts_at: datetime, styles: dict) -> list:
    story = [
        _section_title("Programação detalhada", "Horários, locais e equipes envolvidas.", styles)
    ]
    if not events:
        story.append(
            Paragraph("Sem compromissos programados para esta semana.", styles["empty_day"])
        )
        return story
    for index in range(7):
        day_date = starts_at.date().fromordinal(starts_at.date().toordinal() + index)
        day_events = [item for item in events if item.starts_at.date() == day_date]
        if not day_events:
            continue
        day_block = [
            Table(
                [
                    [
                        Paragraph(
                            f"{DAY_NAMES[index]}  •  {day_date.strftime('%d/%m')}",
                            styles["day_heading"],
                        ),
                        Paragraph(f"{len(day_events)} compromisso(s)", styles["day_total"]),
                    ]
                ],
                colWidths=[12.6 * cm, 3.8 * cm],
                rowHeights=[0.7 * cm],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0.25 * cm),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0.25 * cm),
                        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ]
                ),
            ),
            Spacer(1, 0.12 * cm),
        ]
        for event in day_events:
            day_block.extend([_event_card(event, styles), Spacer(1, 0.12 * cm)])
        day_block.append(Spacer(1, 0.18 * cm))
        story.append(KeepTogether(day_block))
    return story


def _event_card(event: AgendaEvent, styles: dict):
    end = event.ends_at.strftime("%H:%M") if event.ends_at else "--:--"
    time = f"{event.starts_at.strftime('%H:%M')} - {end}"
    participants = (
        ", ".join(
            str(value.get("nome"))
            for value in (event.participants or [])
            if isinstance(value, dict) and value.get("nome")
        )
        or "Equipe não definida"
    )
    badges = TYPE_LABELS.get(event.event_type, event.event_type.value)
    if event.representative_presence:
        badges += "  •  PRESENÇA PARLAMENTAR"
    status_tone = GREEN if event.status == AgendaEventStatus.REALIZADO else BLUE
    content = [
        Paragraph(html_escape(event.title), styles["event_title"]),
        Paragraph(
            html_escape(f"{badges}  •  {event.status.value}"),
            ParagraphStyle("EventMeta", parent=styles["event_meta"], textColor=status_tone),
        ),
        Paragraph(
            html_escape(f"Local: {event.location or 'Não informado'}"), styles["event_detail"]
        ),
        Paragraph(html_escape(f"Equipe: {participants}"), styles["event_detail"]),
    ]
    table = Table(
        [[Paragraph(time, styles["event_time"]), content]],
        colWidths=[2.45 * cm, 13.75 * cm],
    )
    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    PURPLE_BG if event.representative_presence else colors.white,
                ),
                ("BOX", (0, 0), (-1, -1), 0.55, PURPLE if event.representative_presence else LINE),
                (
                    "LINEAFTER",
                    (0, 0),
                    (0, 0),
                    0.55,
                    PURPLE if event.representative_presence else LINE,
                ),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0.28 * cm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0.28 * cm),
                ("TOPPADDING", (0, 0), (-1, -1), 0.22 * cm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0.22 * cm),
            ]
        )
    )
    return table


def _section_title(title: str, subtitle: str, styles: dict):
    return Table(
        [
            [
                Paragraph(html_escape(title), styles["section_title"]),
                Paragraph(html_escape(subtitle), styles["section_subtitle"]),
            ]
        ],
        colWidths=[5.0 * cm, 11.4 * cm],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0.12 * cm),
                ("LINEBELOW", (0, 0), (-1, -1), 0.65, LINE),
            ]
        ),
    )


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "hero_title": ParagraphStyle(
            "HeroTitle",
            parent=base["Title"],
            fontName="AgendaSans-Bold",
            fontSize=23,
            leading=27,
            textColor=colors.white,
            alignment=TA_LEFT,
        ),
        "hero_period": ParagraphStyle(
            "HeroPeriod",
            parent=base["BodyText"],
            fontName="AgendaSans",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#DCEBFA"),
        ),
        "office": ParagraphStyle(
            "Office",
            parent=base["BodyText"],
            fontName="AgendaSans-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.white,
        ),
        "identity": ParagraphStyle(
            "Identity",
            parent=base["BodyText"],
            fontName="AgendaSans",
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#BCD0E6"),
        ),
        "section_title": ParagraphStyle(
            "SectionTitle",
            parent=base["Heading2"],
            fontName="AgendaSans-Bold",
            fontSize=11,
            leading=14,
            textColor=NAVY,
        ),
        "section_subtitle": ParagraphStyle(
            "SectionSubtitle",
            parent=base["BodyText"],
            fontName="AgendaSans",
            fontSize=7,
            leading=10,
            textColor=MUTED,
            alignment=TA_LEFT,
        ),
        "metric_value": ParagraphStyle(
            "MetricValueBase",
            parent=base["BodyText"],
            fontName="AgendaSans-Bold",
            fontSize=19,
            leading=21,
        ),
        "metric_label": ParagraphStyle(
            "MetricLabel",
            parent=base["BodyText"],
            fontName="AgendaSans",
            fontSize=6.6,
            leading=8.5,
            textColor=INK,
        ),
        "day_short": ParagraphStyle(
            "DayShort",
            parent=base["BodyText"],
            fontName="AgendaSans-Bold",
            fontSize=6.4,
            leading=8,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "day_count": ParagraphStyle(
            "DayCount",
            parent=base["BodyText"],
            fontName="AgendaSans-Bold",
            fontSize=13,
            leading=15,
            textColor=NAVY,
            alignment=TA_CENTER,
        ),
        "insight_label": ParagraphStyle(
            "InsightLabelBase",
            parent=base["BodyText"],
            fontName="AgendaSans-Bold",
            fontSize=6.1,
            leading=8,
        ),
        "insight_text": ParagraphStyle(
            "InsightText",
            parent=base["BodyText"],
            fontName="AgendaSans",
            fontSize=7.2,
            leading=10,
            textColor=INK,
        ),
        "day_heading": ParagraphStyle(
            "DayHeading",
            parent=base["BodyText"],
            fontName="AgendaSans-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.white,
        ),
        "day_total": ParagraphStyle(
            "DayTotal",
            parent=base["BodyText"],
            fontName="AgendaSans",
            fontSize=6.8,
            leading=9,
            textColor=colors.HexColor("#D7E5F3"),
            alignment=TA_CENTER,
        ),
        "empty_day": ParagraphStyle(
            "EmptyDay",
            parent=base["BodyText"],
            fontName="AgendaSans",
            fontSize=7.4,
            leading=11,
            textColor=MUTED,
            leftIndent=0.25 * cm,
            spaceAfter=0.1 * cm,
        ),
        "event_time": ParagraphStyle(
            "EventTime",
            parent=base["BodyText"],
            fontName="AgendaSans-Bold",
            fontSize=9,
            leading=12,
            textColor=NAVY,
            alignment=TA_CENTER,
        ),
        "event_title": ParagraphStyle(
            "EventTitle",
            parent=base["BodyText"],
            fontName="AgendaSans-Bold",
            fontSize=8.2,
            leading=11,
            textColor=INK,
        ),
        "event_meta": ParagraphStyle(
            "EventMetaBase",
            parent=base["BodyText"],
            fontName="AgendaSans-Bold",
            fontSize=5.8,
            leading=8,
            spaceBefore=2,
        ),
        "event_detail": ParagraphStyle(
            "EventDetail",
            parent=base["BodyText"],
            fontName="AgendaSans",
            fontSize=6.8,
            leading=9.5,
            textColor=MUTED,
            spaceBefore=1,
        ),
        "event_description": ParagraphStyle(
            "EventDescription",
            parent=base["BodyText"],
            fontName="AgendaSans",
            fontSize=6.6,
            leading=9.3,
            textColor=INK,
            spaceBefore=3,
        ),
    }


def _date(value) -> str:
    return value.strftime("%d/%m/%Y")


def _datetime(value) -> str:
    return value.strftime("%d/%m/%Y às %H:%M")


def _weekday_date(value) -> str:
    if value is None:
        return "A semana"
    return f"{DAY_NAMES[value.weekday()]}, {value.strftime('%d/%m')}"
