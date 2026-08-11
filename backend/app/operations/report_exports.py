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
    Flowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#08285C")
BLUE = colors.HexColor("#1268A8")
TEAL = colors.HexColor("#0B8A85")
INK = colors.HexColor("#172B4D")
MUTED = colors.HexColor("#607188")
LINE = colors.HexColor("#D9E3EC")
SURFACE = colors.HexColor("#F5F8FB")
GREEN = colors.HexColor("#16845B")
GREEN_BG = colors.HexColor("#EAF8F1")
AMBER = colors.HexColor("#A36600")
AMBER_BG = colors.HexColor("#FFF6DD")
RED = colors.HexColor("#B43C3C")
RED_BG = colors.HexColor("#FFF0F0")

FONT_DIR = Path(reportlab.__file__).resolve().parent / "fonts"
pdfmetrics.registerFont(TTFont("GabFlowSans", str(FONT_DIR / "Vera.ttf")))
pdfmetrics.registerFont(TTFont("GabFlowSans-Bold", str(FONT_DIR / "VeraBd.ttf")))


def executive_report_pdf(payload: dict) -> bytes:
    stream = BytesIO()
    styles = _styles()
    story = []
    story.extend(_hero(payload, styles))
    story.extend(_summary(payload, styles))
    story.extend(_traffic_lights(payload, styles))
    story.extend(_insights(payload, styles))

    charts = payload.get("graficos") or {}
    story.extend(
        _section_heading(
            "Leitura operacional", "Volume, horários e distribuição territorial.", styles
        )
    )
    story.append(
        Table(
            [
                [
                    _chart_block(
                        "Volume no período", charts.get("volumePeriodo", []), styles, 7.35 * cm
                    ),
                    _chart_block(
                        "Horários de atendimento", _nonzero_hours(charts), styles, 7.35 * cm
                    ),
                ]
            ],
            colWidths=[8.25 * cm, 8.25 * cm],
            style=_two_column_style(),
        )
    )
    story.append(Spacer(1, 0.35 * cm))
    story.append(
        Table(
            [
                [
                    _chart_block(
                        "Regiões com maiores demandas",
                        charts.get("territorios", []),
                        styles,
                        7.35 * cm,
                    ),
                    _chart_block(
                        "Demandas mais recorrentes",
                        charts.get("demandasRecorrentes", []),
                        styles,
                        7.35 * cm,
                    ),
                ]
            ],
            colWidths=[8.25 * cm, 8.25 * cm],
            style=_two_column_style(),
        )
    )

    story.extend(
        _section_heading(
            "Performance e desdobramentos",
            "Eficiência da equipe e entregas originadas pelas demandas.",
            styles,
        )
    )
    story.extend(_efficiency_ranking(payload, styles))
    story.append(Spacer(1, 0.45 * cm))
    story.append(
        Table(
            [
                [
                    _chart_block(
                        "Produção legislativa",
                        charts.get("producaoLegislativa", []),
                        styles,
                        7.35 * cm,
                    ),
                    _chart_block(
                        "Ações geradas", charts.get("acoesGeradas", []), styles, 7.35 * cm
                    ),
                ]
            ],
            colWidths=[8.25 * cm, 8.25 * cm],
            style=_two_column_style(),
        )
    )
    story.append(Spacer(1, 0.45 * cm))
    story.extend(_citizen_ranking(payload, styles))
    story.append(Spacer(1, 0.45 * cm))
    story.extend(_methodology(payload, styles))

    document = SimpleDocTemplate(
        stream,
        pagesize=A4,
        rightMargin=1.55 * cm,
        leftMargin=1.55 * cm,
        topMargin=1.45 * cm,
        bottomMargin=1.45 * cm,
        title=payload.get("titulo", "Relatório Executivo GabFlow"),
        author="GabFlow",
        subject="Relatório executivo do mandato",
    )
    document.build(
        story,
        onFirstPage=lambda canvas, doc: _decorate_page(canvas, doc, payload),
        onLaterPages=lambda canvas, doc: _decorate_page(canvas, doc, payload),
    )
    return stream.getvalue()


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ExecutiveTitle",
            parent=base["Title"],
            fontName="GabFlowSans-Bold",
            fontSize=22,
            leading=26,
            textColor=colors.white,
            alignment=TA_LEFT,
            spaceAfter=4,
        ),
        "hero_meta": ParagraphStyle(
            "ExecutiveHeroMeta",
            parent=base["BodyText"],
            fontName="GabFlowSans",
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor("#DCEEFF"),
        ),
        "section": ParagraphStyle(
            "ExecutiveSection",
            parent=base["Heading2"],
            fontName="GabFlowSans-Bold",
            fontSize=13,
            leading=16,
            textColor=NAVY,
            spaceAfter=2,
        ),
        "section_subtitle": ParagraphStyle(
            "ExecutiveSectionSubtitle",
            parent=base["BodyText"],
            fontName="GabFlowSans",
            fontSize=8.5,
            leading=12,
            textColor=MUTED,
            spaceAfter=9,
        ),
        "body": ParagraphStyle(
            "ExecutiveBody",
            parent=base["BodyText"],
            fontName="GabFlowSans",
            fontSize=8.5,
            leading=12,
            textColor=INK,
        ),
        "small": ParagraphStyle(
            "ExecutiveSmall",
            parent=base["BodyText"],
            fontName="GabFlowSans",
            fontSize=7.3,
            leading=10,
            textColor=MUTED,
        ),
        "card_value": ParagraphStyle(
            "ExecutiveCardValue",
            parent=base["BodyText"],
            fontName="GabFlowSans-Bold",
            fontSize=17,
            leading=19,
            textColor=NAVY,
            alignment=TA_CENTER,
        ),
        "card_label": ParagraphStyle(
            "ExecutiveCardLabel",
            parent=base["BodyText"],
            fontName="GabFlowSans-Bold",
            fontSize=6.8,
            leading=9,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "chart_title": ParagraphStyle(
            "ExecutiveChartTitle",
            parent=base["BodyText"],
            fontName="GabFlowSans-Bold",
            fontSize=9,
            leading=11,
            textColor=NAVY,
        ),
        "table_header": ParagraphStyle(
            "ExecutiveTableHeader",
            parent=base["BodyText"],
            fontName="GabFlowSans-Bold",
            fontSize=7.2,
            leading=9,
            textColor=colors.white,
        ),
        "table_cell": ParagraphStyle(
            "ExecutiveTableCell",
            parent=base["BodyText"],
            fontName="GabFlowSans",
            fontSize=7.2,
            leading=9,
            textColor=INK,
        ),
    }


def _hero(payload, styles):
    office = payload.get("gabinete") or {}
    report_type = "Operação" if payload.get("tipo") == "OPERACIONAL" else "Insights do Mandato"
    meta = " · ".join(
        filter(
            None,
            [
                office.get("nome"),
                office.get("jurisdicao"),
                payload.get("periodo", {}).get("rotulo"),
            ],
        )
    )
    content = [
        Paragraph("GABFLOW EXECUTIVE INTELLIGENCE", styles["hero_meta"]),
        Spacer(1, 0.12 * cm),
        Paragraph(html_escape(payload.get("titulo", "Relatório Executivo")), styles["title"]),
        Paragraph(html_escape(f"{report_type} · {meta}"), styles["hero_meta"]),
    ]
    hero = Table([[content]], colWidths=[17.0 * cm])
    hero.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("BOX", (0, 0), (-1, -1), 0, NAVY),
                ("LEFTPADDING", (0, 0), (-1, -1), 18),
                ("RIGHTPADDING", (0, 0), (-1, -1), 18),
                ("TOPPADDING", (0, 0), (-1, -1), 18),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
            ]
        )
    )
    return [hero, Spacer(1, 0.5 * cm)]


def _summary(payload, styles):
    summary = payload.get("resumo") or {}
    items = [
        (summary.get("solicitacoesRecebidas", 0), "Demandas recebidas"),
        (summary.get("resolvidasOuEncerradas", 0), "Resolvidas / encerradas"),
        (f"{summary.get('taxaResolucaoPercentual', 0):.1f}%", "Taxa de resolução"),
        (f"{summary.get('cumprimentoPrazoPercentual', 0):.1f}%", "Cumprimento de prazo"),
        (summary.get("documentosLegislativos", 0), "Documentos legislativos"),
        (summary.get("acoesGeradas", 0), "Ações geradas"),
    ]
    cells = [
        [
            Paragraph(html_escape(str(value)), styles["card_value"]),
            Paragraph(label, styles["card_label"]),
        ]
        for value, label in items
    ]
    table = Table([cells[:3], cells[3:]], colWidths=[5.5 * cm] * 3, rowHeights=[1.55 * cm] * 2)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
                ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return [table, Spacer(1, 0.55 * cm)]


def _traffic_lights(payload, styles):
    rows = []
    for item in payload.get("semaforo") or []:
        color, background, label = _traffic_palette(item.get("nivel"))
        badge = Table([[Paragraph(label, styles["table_cell"])]], colWidths=[1.9 * cm])
        badge.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), background),
                    ("TEXTCOLOR", (0, 0), (-1, -1), color),
                    ("BOX", (0, 0), (-1, -1), 0.5, color),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        rows.append(
            [
                badge,
                Paragraph(
                    f"<b>{html_escape(item.get('titulo', ''))}</b><br/>"
                    f"{html_escape(item.get('descricao', ''))}",
                    styles["body"],
                ),
                Paragraph(f"<b>{html_escape(str(item.get('valor', '')))}</b>", styles["body"]),
            ]
        )
    table = Table(
        rows or [["", Paragraph("Sem ocorrências classificadas.", styles["body"]), ""]],
        colWidths=[2.2 * cm, 12.3 * cm, 2.0 * cm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return [
        *_section_heading(
            "Semáforo executivo", "Problemas, avisos e resultados positivos do período.", styles
        ),
        table,
        Spacer(1, 0.5 * cm),
    ]


def _insights(payload, styles):
    cards = []
    for item in payload.get("destaques") or []:
        cards.append(
            [
                Paragraph(html_escape(item.get("titulo", "Insight")), styles["chart_title"]),
                Paragraph(html_escape(item.get("descricao", "")), styles["body"]),
            ]
        )
    if not cards:
        return []
    table = Table(cards, colWidths=[4.0 * cm, 12.5 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7FBFE")),
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#CFE2F2")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDEAF4")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return [
        *_section_heading(
            "Insights do período",
            "Sinais para orientar comunicação, prioridades e decisão do mandato.",
            styles,
        ),
        table,
        Spacer(1, 0.5 * cm),
    ]


def _efficiency_ranking(payload, styles):
    items = payload.get("rankings", {}).get("eficienciaEquipe") or []
    header = ["#", "Equipe", "Score", "Demandas", "Resolvidas", "No prazo", "Interações", "Tarefas"]
    rows = [[Paragraph(value, styles["table_header"]) for value in header]]
    for index, item in enumerate(items, 1):
        rows.append(
            [
                str(index),
                Paragraph(html_escape(item.get("nome", "Equipe")), styles["table_cell"]),
                f"{item.get('score', 0):.1f}",
                str(item.get("demandas", 0)),
                str(item.get("resolvidas", 0)),
                f"{item.get('cumprimentoPrazoPercentual', 0):.1f}%",
                str(item.get("interacoes", 0)),
                str(item.get("tarefasConcluidas", 0)),
            ]
        )
    if len(rows) == 1:
        rows.append(
            [
                "-",
                Paragraph("Sem atividade suficiente para compor ranking.", styles["table_cell"]),
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
            ]
        )
    table = Table(
        rows,
        repeatRows=1,
        colWidths=[0.6 * cm, 4.4 * cm, 1.35 * cm, 1.7 * cm, 1.7 * cm, 1.7 * cm, 1.5 * cm, 1.5 * cm],
    )
    table.setStyle(_data_table_style())
    return [
        Paragraph("Ranking de eficiência da equipe", styles["chart_title"]),
        Spacer(1, 0.15 * cm),
        table,
    ]


def _citizen_ranking(payload, styles):
    items = payload.get("rankings", {}).get("cidadaosAtuantes") or []
    if not items:
        return [
            Paragraph("Participação cidadã", styles["chart_title"]),
            Paragraph(
                "Sem recorrência suficiente para destacar cidadãos no período.", styles["small"]
            ),
        ]
    rows = [
        [
            Paragraph("Cidadãos mais atuantes", styles["table_header"]),
            Paragraph("Demandas", styles["table_header"]),
        ]
    ]
    rows.extend(
        [
            [
                Paragraph(html_escape(item.get("nome", "Cidadão")), styles["table_cell"]),
                str(item.get("total", 0)),
            ]
            for item in items[:8]
        ]
    )
    table = Table(rows, colWidths=[14.4 * cm, 2.1 * cm], repeatRows=1)
    table.setStyle(_data_table_style())
    return [table]


def _methodology(payload, styles):
    generated = payload.get("geradoEm", "")
    text = (
        "Indicadores calculados a partir das demandas recebidas ou movimentadas no período. "
        "O score de eficiência combina resolução (50%), cumprimento de prazo (30%) e atividade "
        "registrada (20%). Rankings devem apoiar gestão e desenvolvimento, "
        "não decisões disciplinares "
        "isoladas. Recortes pequenos podem ser suprimidos por privacidade."
    )
    box = Table(
        [
            [
                Paragraph("Metodologia e governança", styles["chart_title"]),
                Paragraph(text, styles["small"]),
            ],
            ["", Paragraph(f"Gerado pelo GabFlow em {html_escape(generated)}.", styles["small"])],
        ],
        colWidths=[4.2 * cm, 12.3 * cm],
    )
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("SPAN", (0, 0), (0, 1)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return [box]


def _section_heading(title, subtitle, styles):
    return [Paragraph(title, styles["section"]), Paragraph(subtitle, styles["section_subtitle"])]


def _chart_block(title, items, styles, width):
    content = [Paragraph(title, styles["chart_title"]), Spacer(1, 0.15 * cm)]
    if items:
        content.append(HorizontalBars(items[:8], width=width, height=3.35 * cm))
    else:
        content.append(Paragraph("Sem dados suficientes para este recorte.", styles["small"]))
        content.append(Spacer(1, 2.7 * cm))
    return content


def _nonzero_hours(charts):
    return [item for item in charts.get("horariosAtendimento", []) if item.get("total")]


def _two_column_style():
    return TableStyle(
        [
            ("BOX", (0, 0), (-1, -1), 0.7, LINE),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]
    )


def _data_table_style():
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SURFACE]),
            ("BOX", (0, 0), (-1, -1), 0.6, LINE),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (2, 1), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
    )


def _traffic_palette(level):
    if level == "problema":
        return RED, RED_BG, "PROBLEMA"
    if level == "aviso":
        return AMBER, AMBER_BG, "AVISO"
    return GREEN, GREEN_BG, "POSITIVO"


def _decorate_page(canvas, document, payload):
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(1.55 * cm, 1.05 * cm, width - 1.55 * cm, 1.05 * cm)
    canvas.setFillColor(MUTED)
    canvas.setFont("GabFlowSans", 7)
    canvas.drawString(1.55 * cm, 0.7 * cm, "GabFlow · Inteligência executiva para mandatos")
    canvas.drawRightString(width - 1.55 * cm, 0.7 * cm, f"Página {document.page}")
    if document.page > 1:
        canvas.setFillColor(NAVY)
        canvas.rect(0, height - 0.18 * cm, width, 0.18 * cm, stroke=0, fill=1)
    canvas.restoreState()


class HorizontalBars(Flowable):
    def __init__(self, items, width, height):
        super().__init__()
        self.items = items
        self.width = width
        self.height = height

    def draw(self):
        maximum = max((float(item.get("total", 0)) for item in self.items), default=1) or 1
        row_height = self.height / max(len(self.items), 1)
        label_width = self.width * 0.42
        bar_width = self.width - label_width - 0.7 * cm
        for index, item in enumerate(self.items):
            y = self.height - ((index + 1) * row_height) + row_height * 0.3
            label = str(item.get("nome") or item.get("rotulo") or "-")
            label = _truncate(label, label_width - 4, 7)
            value = float(item.get("total", 0))
            self.canv.setFont("GabFlowSans", 7)
            self.canv.setFillColor(INK)
            self.canv.drawString(0, y + 2, label)
            self.canv.setFillColor(colors.HexColor("#E7EEF5"))
            self.canv.roundRect(label_width, y, bar_width, 7, 3.5, stroke=0, fill=1)
            self.canv.setFillColor(TEAL)
            filled = max((value / maximum) * bar_width, 2 if value else 0)
            self.canv.roundRect(label_width, y, filled, 7, 3.5, stroke=0, fill=1)
            self.canv.setFillColor(NAVY)
            self.canv.setFont("GabFlowSans-Bold", 7)
            self.canv.drawRightString(self.width, y + 1.5, f"{value:g}")


def _truncate(value, width, font_size):
    if pdfmetrics.stringWidth(value, "GabFlowSans", font_size) <= width:
        return value
    shortened = value
    while (
        shortened
        and pdfmetrics.stringWidth(shortened + "...", "GabFlowSans", font_size) > width
    ):
        shortened = shortened[:-1]
    return shortened.rstrip() + "..."
