"""Построитель PDF-отчётов на reportlab с кириллицей и нумерацией разделов.

Модуль даёт небольшой предметно-независимый API (h1/h2/p/table/figure/note),
который используют обе расчётные программы. Шрифт DejaVu Sans берётся из
комплекта matplotlib, поэтому отдельная установка шрифтов не требуется.
"""

from __future__ import annotations

import datetime as _dt
import os
from typing import Sequence
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from common.plotkit import FONT_BOLD_PATH, FONT_PATH

FONT = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"

_REGISTERED = False

COLOR_INK = colors.HexColor("#1a202c")
COLOR_ACCENT = colors.HexColor("#1f5fa9")
COLOR_MUTED = colors.HexColor("#4a5568")
COLOR_GRID = colors.HexColor("#cbd5e0")
COLOR_HEAD_BG = colors.HexColor("#e8eef6")
COLOR_TOTAL_BG = colors.HexColor("#f2f5f9")


def register_fonts() -> None:
    """Один раз регистрирует TTF-шрифты с кириллицей в reportlab."""
    global _REGISTERED
    if _REGISTERED:
        return
    pdfmetrics.registerFont(TTFont(FONT, FONT_PATH))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, FONT_BOLD_PATH))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD, italic=FONT, boldItalic=FONT_BOLD)
    _REGISTERED = True


def _styles() -> dict[str, ParagraphStyle]:
    register_fonts()
    return {
        "h1": ParagraphStyle("h1", fontName=FONT_BOLD, fontSize=12.5, leading=16, spaceBefore=10,
                             spaceAfter=5, textColor=COLOR_ACCENT),
        "h2": ParagraphStyle("h2", fontName=FONT_BOLD, fontSize=10.5, leading=13, spaceBefore=7,
                             spaceAfter=3, textColor=COLOR_INK),
        "body": ParagraphStyle("body", fontName=FONT, fontSize=9, leading=12.6, spaceAfter=3,
                               alignment=4, textColor=COLOR_INK),
        "small": ParagraphStyle("small", fontName=FONT, fontSize=7.8, leading=10.4,
                                textColor=COLOR_MUTED),
        "cell": ParagraphStyle("cell", fontName=FONT, fontSize=8.2, leading=10.6,
                               textColor=COLOR_INK),
        "caption": ParagraphStyle("caption", fontName=FONT, fontSize=7.8, leading=10,
                                  textColor=COLOR_MUTED, alignment=TA_CENTER),
        "subtitle": ParagraphStyle("subtitle", fontName=FONT, fontSize=9.5, leading=12.5,
                                   textColor=COLOR_MUTED),
    }

class Report:
    """Документ отчёта: разделы, таблицы параметров, рисунки, примечания."""

    def __init__(self, title: str, program: str, subtitle: str = "", doc_no: str = "") -> None:
        self.title = title
        self.program = program
        self.subtitle = subtitle
        self.doc_no = doc_no or f"РР-{_dt.date.today():%Y%m%d}"
        self.st = _styles()
        self.story: list = []
        self._section = 0
        self._figure_no = 0
        self._table_no = 0
        self._add_title_block()

    # ---------------------------------------------------------------- служебное
    def _add_title_block(self) -> None:
        meta_style = ParagraphStyle("meta", fontName=FONT, fontSize=7.6, leading=10,
                                    textColor=COLOR_MUTED, alignment=TA_RIGHT)
        title_style = ParagraphStyle("ttl", fontName=FONT_BOLD, fontSize=14.5, leading=19,
                                     textColor=COLOR_INK)
        header = Table(
            [[Paragraph(escape(self.title), title_style),
              Paragraph(f"<b>Документ</b> {escape(self.doc_no)}<br/>"
                        f"<b>Дата</b> {_dt.date.today():%d.%m.%Y}<br/>"
                        f"<b>Модуль</b> {escape(self.program)}", meta_style)]],
            colWidths=[118 * mm, 57 * mm],
        )
        header.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 1.1, COLOR_ACCENT),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        self.story.append(header)
        if self.subtitle:
            self.story.append(Paragraph(escape(self.subtitle), self.st["subtitle"]))
        self.story.append(Spacer(1, 4))

    # ------------------------------------------------------------------ разметка
    def h1(self, text: str) -> None:
        self._section += 1
        self.story.append(Paragraph(f"{self._section}. {escape(text)}", self.st["h1"]))

    def h2(self, text: str) -> None:
        self.story.append(Paragraph(escape(text), self.st["h2"]))

    def p(self, text: str, style: str = "body") -> None:
        self.story.append(Paragraph(escape(text), self.st[style]))

    def bullet(self, items: Sequence[str]) -> None:
        for item in items:
            self.story.append(Paragraph(f"•&nbsp;&nbsp;{escape(item)}", self.st["body"]))

    def note(self, text: str) -> None:
        tbl = Table([[Paragraph(escape(text), self.st["small"])]], colWidths=[175 * mm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_TOTAL_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_GRID),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        self.story.append(Spacer(1, 3))
        self.story.append(tbl)
        self.story.append(Spacer(1, 3))

    def spacer(self, height_mm: float = 3) -> None:
        self.story.append(Spacer(1, height_mm * mm))



    # ------------------------------------------------------------------- таблицы
    def table(
        self,
        header: Sequence[str],
        rows: Sequence[Sequence[str]],
        widths_mm: Sequence[float] | None = None,
        aligns: Sequence[str] | None = None,
        caption: str = "",
        total_last: bool = False,
    ) -> None:
        """Таблица с шапкой. aligns: 'l' | 'c' | 'r' для каждого столбца."""
        st = self.st
        aligns = list(aligns or ["l"] * len(header))
        amap = {"l": TA_LEFT, "c": TA_CENTER, "r": TA_RIGHT}

        def make_cell(text: str, col: int, bold: bool = False) -> Paragraph:
            style = ParagraphStyle(
                f"c{col}{int(bold)}", parent=st["cell"],
                alignment=amap.get(aligns[col], TA_LEFT),
                fontName=FONT_BOLD if bold else FONT,
            )
            return Paragraph(text if text.startswith("<") else escape(text), style)

        data = [[make_cell(str(h), i, bold=True) for i, h in enumerate(header)]]
        for r_index, row in enumerate(rows):
            is_total = total_last and r_index == len(rows) - 1
            data.append([make_cell(str(v), i, bold=is_total) for i, v in enumerate(row)])

        if widths_mm is None:
            widths_mm = [175 / len(header)] * len(header)

        tbl = Table(data, colWidths=[w * mm for w in widths_mm], repeatRows=1)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEAD_BG),
            ("GRID", (0, 0), (-1, -1), 0.4, COLOR_GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]
        if total_last:
            style.append(("BACKGROUND", (0, len(data) - 1), (-1, -1), COLOR_TOTAL_BG))
        tbl.setStyle(TableStyle(style))

        block: list = []
        if caption:
            self._table_no += 1
            block.append(Paragraph(f"Таблица {self._table_no}. {escape(caption)}", st["caption"]))
            block.append(Spacer(1, 1.5))
        block.append(tbl)
        block.append(Spacer(1, 4))
        if len(rows) <= 14:
            self.story.append(KeepTogether(block))
        else:
            self.story.extend(block)

    def params(self, rows: Sequence[tuple[str, str, str]], caption: str = "") -> None:
        """Таблица «параметр — обозначение — значение»."""
        self.table(["Параметр", "Обозн.", "Значение"], list(rows),
                   widths_mm=[88, 26, 61], aligns=["l", "c", "r"], caption=caption)

    def figure(self, png_path: str, caption: str = "", width_mm: float = 172) -> None:
        """Вставка рисунка с сохранением пропорций."""
        w_px, h_px = ImageReader(png_path).getSize()
        width = width_mm * mm
        height = width * h_px / w_px
        if height > 150 * mm:
            height = 150 * mm
            width = height * w_px / h_px
        block: list = [Image(png_path, width=width, height=height)]
        if caption:
            self._figure_no += 1
            block.append(Paragraph(f"Рисунок {self._figure_no}. {escape(caption)}",
                                   self.st["caption"]))
        block.append(Spacer(1, 5))
        self.story.append(KeepTogether(block))

    # -------------------------------------------------------------------- вывод
    def save(self, path: str) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        doc = SimpleDocTemplate(
            path,
            pagesize=A4,
            leftMargin=17 * mm,
            rightMargin=17 * mm,
            topMargin=15 * mm,
            bottomMargin=16 * mm,
            title=self.title,
            author=self.program,
        )
        program, doc_no = self.program, self.doc_no

        def on_page(canvas, doc_obj):
            width, _ = A4
            canvas.saveState()
            canvas.setFont(FONT, 7.2)
            canvas.setFillColor(COLOR_MUTED)
            canvas.setStrokeColor(COLOR_GRID)
            canvas.setLineWidth(0.6)
            canvas.line(17 * mm, 12 * mm, width - 17 * mm, 12 * mm)
            canvas.drawString(17 * mm, 8.2 * mm, f"{program} · {doc_no}")
            canvas.drawRightString(width - 17 * mm, 8.2 * mm, f"стр. {doc_obj.page}")
            canvas.restoreState()

        doc.build(self.story, onFirstPage=on_page, onLaterPages=on_page)
        return path
