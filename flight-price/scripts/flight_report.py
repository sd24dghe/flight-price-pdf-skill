#!/usr/bin/env python3
"""Create compact PDF/DOCX/XLSX summaries from flight-price JSON."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

try:  # optional legacy-report deps; run_flight_pdf.py needs none of these
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False
try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    HAS_XLSX = True
except ImportError:
    HAS_XLSX = False
try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    HAS_PDF = True
except ImportError:
    HAS_PDF = False


COLUMNS = [
    ("rank", "排名"),
    ("origin", "出发地"),
    ("dest", "目的地"),
    ("date", "去程日期"),
    ("return_date", "回程日期"),
    ("stay_nights", "晚数"),
    ("price", "票价"),
    ("currency", "币种"),
    ("price_basis", "总价口径"),
    ("stops", "中转"),
    ("baggage", "行李"),
    ("refund_change", "退改规则"),
    ("provider", "出票方"),
    ("airline", "航司"),
    ("outbound_flights", "去程航班"),
    ("outbound_route", "去程路线"),
    ("depart_time", "去程出发"),
    ("outbound_duration", "去程时长"),
    ("return_flights", "返程航班"),
    ("aircraft", "机型"),
    ("notes", "备注"),
]

if HAS_XLSX:
    HEADER_FILL = PatternFill("solid", fgColor="17324D")
    HEADER_FONT = Font(color="FFFFFF", bold=True)
    THIN_GRAY = Side(style="thin", color="D8E0E8")
    ROW_FILLS = [PatternFill("solid", fgColor="F6F8FA"), PatternFill("solid", fgColor="FFFFFF")]
    TOP_FILL = PatternFill("solid", fgColor="EAF3F1")
_PDF_FONTS: tuple[str, str] | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="flight-price JSON file")
    parser.add_argument("--pdf", help="PDF output path; defaults to <input>_summary.pdf")
    parser.add_argument("--xlsx", help="optional XLSX output path")
    parser.add_argument("--docx", help="optional DOCX output path")
    parser.add_argument("--no-pdf", action="store_true", help="do not create the default PDF")
    parser.add_argument("--top", type=int, default=10, help="rows in the executive summary")
    parser.add_argument("--title", default="机票查询汇总", help="report title")
    parser.add_argument("--source", default="Trip.com / flight-price", help="data source label")
    parser.add_argument(
        "--source-url",
        default="https://tw.trip.com/chinaflights/",
        help="source URL shown in reports",
    )
    return parser.parse_args()


def load_input(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("input must be a flight-price JSON object")
    return data


def collect_candidates(data: dict[str, Any]) -> list[dict[str, Any]]:
    origin = str(data.get("origin") or "")
    dest = str(data.get("dest") or "")
    candidates: list[dict[str, Any]] = []

    top_level = data.get("flights")
    if isinstance(top_level, list) and top_level:
        candidates.extend(item for item in top_level if isinstance(item, dict))
    else:
        for result in data.get("results") or []:
            if not isinstance(result, dict):
                continue
            for option in result.get("options") or []:
                if not isinstance(option, dict):
                    continue
                merged = dict(option)
                merged.setdefault("date", result.get("date"))
                merged.setdefault("return_date", result.get("return_date"))
                merged.setdefault("stay_nights", result.get("stay_nights"))
                candidates.append(merged)

    rows: list[dict[str, Any]] = []
    for item in candidates:
        price = as_number(item.get("price"))
        if price is None:
            continue
        segments = item.get("segments") or []
        if not isinstance(segments, list):
            segments = []

        outbound_flights = item.get("flight_nos") or []
        if not isinstance(outbound_flights, list):
            outbound_flights = [str(outbound_flights)]

        route = itinerary_route(segments)
        aircraft = itinerary_aircraft(item, segments)
        baggage = first_value(
            item,
            "baggage",
            "baggage_allowance",
            "checked_baggage",
            "free_checked_baggage",
        )
        price_basis = first_value(item, "price_basis", "fare_basis") or "含税总价"
        refund_change = first_value(
            item,
            "refund_change",
            "refund_change_rule",
            "change_rule",
        ) or "见出票页"
        provider = first_value(
            item,
            "ticketing_provider",
            "provider",
            "seller",
        ) or "Trip.com（出票方见详情）"
        return_flights = item.get("return_flights") or []
        return_numbers = [
            str(entry.get("flight_no") or "")
            for entry in return_flights
            if isinstance(entry, dict)
        ]

        stops = item.get("stops")
        if stops is None:
            stops = max(0, len(segments) - 1)

        row = {
            "origin": item.get("origin") or origin,
            "dest": item.get("dest") or dest,
            "date": item.get("date") or "",
            "return_date": item.get("return_date") or "",
            "stay_nights": item.get("stay_nights"),
            "price": price,
            "currency": item.get("currency") or data.get("currency") or "CNY",
            "price_basis": price_basis,
            "refund_change": refund_change,
            "provider": provider,
            "airline": item.get("airline") or "",
            "outbound_flights": " / ".join(filter(None, outbound_flights)),
            "outbound_route": route,
            "depart_time": item.get("depart_time") or "",
            "outbound_duration": minutes_to_text(item.get("total_duration_min")),
            "stops": stops,
            "return_flights": " / ".join(filter(None, return_numbers)),
            "aircraft": aircraft,
            "baggage": baggage,
            "notes": "",
        }
        row["notes"] = row_note(row, item)
        rows.append(row)

    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = (
            row["origin"],
            row["dest"],
            row["date"],
            row["return_date"],
            row["airline"],
            row["outbound_flights"],
            row["return_flights"],
            row["price"],
        )
        deduped.setdefault(key, row)

    ordered = sorted(
        deduped.values(),
        key=lambda row: (
            row["price"],
            str(row["date"]),
            str(row["airline"]),
        ),
    )
    for index, row in enumerate(ordered, start=1):
        row["rank"] = index
    return ordered


def as_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def first_value(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", [], {}):
            if isinstance(value, (dict, list)):
                return json.dumps(value, ensure_ascii=False)
            return str(value)
    return ""


def itinerary_route(segments: Iterable[dict[str, Any]]) -> str:
    segments = list(segments)
    if not segments:
        return ""
    airports = [segments[0].get("depart_airport") or ""]
    airports.extend(segment.get("arrive_airport") or "" for segment in segments)
    return " - ".join(part for part in airports if part)


def itinerary_aircraft(item: dict[str, Any], segments: Iterable[dict[str, Any]]) -> str:
    names: list[str] = []
    possible_item_keys = ("aircraft", "aircraft_type", "equipment")
    for key in possible_item_keys:
        value = item.get(key)
        if isinstance(value, str) and value:
            names.append(value)
        elif isinstance(value, list):
            names.extend(str(entry) for entry in value if entry)

    for segment in segments:
        for key in possible_item_keys:
            value = segment.get(key)
            if isinstance(value, str) and value:
                names.append(value)
        craft = segment.get("craftInfo") or segment.get("craft_info")
        if isinstance(craft, dict):
            value = craft.get("name") or craft.get("shortName") or craft.get("craftType")
            if value:
                names.append(str(value))

    return " / ".join(dict.fromkeys(names))


def minutes_to_text(value: Any) -> str:
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return ""
    hours, remainder = divmod(minutes, 60)
    return f"{hours}h{remainder:02d}m"


def row_note(row: dict[str, Any], item: dict[str, Any]) -> str:
    labels = []
    if row["stops"] == 0:
        labels.append("直飞")
    elif row["stops"] > 0:
        labels.append(f"中转 {row['stops']} 次")
    if item.get("direct") is True:
        labels.append("去程直飞")
    return "；".join(labels)


def default_output(input_path: Path, suffix: str) -> Path:
    return input_path.with_name(f"{input_path.stem}_summary{suffix}")


def resolve_outputs(
    args: argparse.Namespace,
    input_path: Path,
) -> tuple[Path | None, Path | None, Path | None]:
    pdf = None if args.no_pdf else (Path(args.pdf) if args.pdf else default_output(input_path, ".pdf"))
    xlsx = Path(args.xlsx) if args.xlsx else None
    docx = Path(args.docx) if args.docx else None
    if pdf is None and xlsx is None and docx is None:
        raise ValueError("at least one output format is required")
    return pdf, xlsx, docx


def write_xlsx(
    path: Path,
    rows: list[dict[str, Any]],
    data: dict[str, Any],
    top: int,
    title: str,
    source: str,
    source_url: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not HAS_XLSX:
        raise SystemExit("openpyxl missing — use run_flight_pdf.py or pip install openpyxl")
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Summary"
    all_results = workbook.create_sheet("All results")
    meta = workbook.create_sheet("Meta")

    for sheet, sheet_rows, sheet_title in (
        (summary, rows[:top], "Executive summary"),
        (all_results, rows, "All results"),
    ):
        populate_sheet(sheet, sheet_rows, sheet_title, data, title, source, source_url)

    meta_rows = [
        ("Title", title),
        ("Source", source),
        ("Source URL", source_url),
        ("Generated", datetime.now().astimezone().isoformat(timespec="seconds")),
        ("Origin", data.get("origin") or ""),
        ("Destination", data.get("dest") or ""),
        ("Mode", data.get("mode") or ""),
        ("Currency", data.get("currency") or "CNY"),
        ("Adults", data.get("adults") or ""),
        ("Rows", len(rows)),
    ]
    for row_index, (key, value) in enumerate(meta_rows, start=1):
        meta.cell(row=row_index, column=1, value=key).font = Font(bold=True)
        meta.cell(row=row_index, column=2, value=value)
    meta.column_dimensions["A"].width = 18
    meta.column_dimensions["B"].width = 60

    workbook.save(path)


def populate_sheet(
    sheet: Any,
    rows: list[dict[str, Any]],
    sheet_title: str,
    data: dict[str, Any],
    title: str,
    source: str,
    source_url: str,
) -> None:
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(COLUMNS))
    heading = sheet.cell(row=1, column=1, value=title)
    heading.font = Font(size=16, bold=True, color="17324D")
    heading.alignment = Alignment(horizontal="center")
    sheet.row_dimensions[1].height = 26

    subtitle = (
        f"{sheet_title} | {data.get('origin') or ''} -> {data.get('dest') or ''} | "
        f"{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M')} | {source} | {source_url}"
    )
    sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(COLUMNS))
    meta_cell = sheet.cell(row=2, column=1, value=subtitle)
    meta_cell.font = Font(size=9, color="5B6B7A")
    meta_cell.alignment = Alignment(horizontal="center")

    header_row = 4
    for column_index, (_, label) in enumerate(COLUMNS, start=1):
        cell = sheet.cell(row=header_row, column=column_index, value=label)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(bottom=THIN_GRAY)

    for row_index, row in enumerate(rows, start=header_row + 1):
        fill = TOP_FILL if row_index <= header_row + 3 else ROW_FILLS[(row_index - header_row) % 2]
        for column_index, (key, _) in enumerate(COLUMNS, start=1):
            value = row.get(key, "")
            cell = sheet.cell(row=row_index, column=column_index, value=value)
            cell.fill = fill
            cell.border = Border(bottom=THIN_GRAY)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if key == "price":
                cell.number_format = '#,##0'

    sheet.freeze_panes = f"A{header_row + 1}"
    sheet.auto_filter.ref = f"A{header_row}:{get_column_letter(len(COLUMNS))}{header_row + max(len(rows), 1)}"
    widths = [7, 10, 10, 13, 13, 8, 12, 8, 14, 10, 20, 28, 32, 8, 22, 24, 18, 12, 22, 24, 20]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.sheet_view.showGridLines = False
    sheet.row_dimensions[header_row].height = 28


def register_pdf_fonts() -> tuple[str, str]:
    global _PDF_FONTS
    if _PDF_FONTS is not None:
        return _PDF_FONTS

    font_path = Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
    try:
        if not font_path.exists():
            raise FileNotFoundError(font_path)
        pdfmetrics.registerFont(TTFont("FlightCN", str(font_path)))
        pdfmetrics.registerFont(TTFont("FlightCNBold", str(font_path)))
        pdfmetrics.registerFontFamily(
            "FlightCN",
            normal="FlightCN",
            bold="FlightCNBold",
            italic="FlightCN",
            boldItalic="FlightCNBold",
        )
        _PDF_FONTS = ("FlightCN", "FlightCNBold")
    except Exception:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        pdfmetrics.registerFontFamily(
            "STSong-Light",
            normal="STSong-Light",
            bold="STSong-Light",
            italic="STSong-Light",
            boldItalic="STSong-Light",
        )
        _PDF_FONTS = ("STSong-Light", "STSong-Light")
    return _PDF_FONTS


def build_pdf_advice(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    best = rows[0]
    if best["stops"] == 0:
        return "最低价方案本身为直飞。"
    direct = next((row for row in rows[1:] if row["stops"] == 0), None)
    if direct is None:
        return "当前候选未找到直飞方案，比较时优先看总旅行时间。"
    price_delta = direct["price"] - best["price"]
    price_ratio = price_delta / best["price"] if best["price"] else 0
    if price_ratio <= 0.25:
        return (
            f"最低价方案为中转；第 {direct['rank']} 名是直飞，"
            f"贵 {direct['currency']} {price_delta:,.0f}（{price_ratio:.0%}），值得一起比较。"
        )
    return (
        f"最低价方案为中转；第 {direct['rank']} 名直飞，"
        f"贵 {direct['currency']} {price_delta:,.0f}，预算优先时再选最低价。"
    )


def write_pdf(
    path: Path,
    rows: list[dict[str, Any]],
    data: dict[str, Any],
    top: int,
    title: str,
    source: str,
    source_url: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not HAS_PDF:
        raise SystemExit("reportlab missing — use run_flight_pdf.py (Playwright PDF) or pip install reportlab")
    regular_font, bold_font = register_pdf_fonts()
    styles = getSampleStyleSheet()
    page_size = landscape(A4)
    title_style = ParagraphStyle(
        "FlightTitle",
        parent=styles["Title"],
        fontName=bold_font,
        fontSize=18,
        leading=23,
        textColor=colors.HexColor("#17324D"),
        alignment=TA_CENTER,
        spaceAfter=3 * mm,
    )
    subtitle_style = ParagraphStyle(
        "FlightSubtitle",
        parent=styles["Normal"],
        fontName=regular_font,
        fontSize=8.2,
        leading=12,
        textColor=colors.HexColor("#5B6B7A"),
        alignment=TA_CENTER,
        spaceAfter=3 * mm,
    )
    body_style = ParagraphStyle(
        "FlightBody",
        parent=styles["BodyText"],
        fontName=regular_font,
        fontSize=8.2,
        leading=12,
        textColor=colors.HexColor("#273746"),
        alignment=TA_LEFT,
        spaceAfter=1.4 * mm,
    )
    small_style = ParagraphStyle(
        "FlightSmall",
        parent=body_style,
        fontSize=6.5,
        leading=9.2,
        textColor=colors.HexColor("#5B6B7A"),
    )
    callout_style = ParagraphStyle(
        "FlightCallout",
        parent=body_style,
        fontSize=9,
        leading=13.5,
    )

    def paragraph(text: str, style: ParagraphStyle = body_style) -> Paragraph:
        return Paragraph(text, style)

    generated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    currency = data.get("currency") or "CNY"
    story = [
        paragraph(title, title_style),
        paragraph(
            f"{data.get('origin') or ''} -> {data.get('dest') or ''} | "
            f"{data.get('mode') or ''} | {data.get('adults') or 1} adult(s) | "
            f"{currency} | 查询时间 {generated}<br/>"
            f"数据来源：{source} | {source_url}",
            subtitle_style,
        ),
    ]

    top_rows = rows[:top]
    summary_lines = []
    for row in top_rows[:3]:
        transfer_text = "直飞" if row["stops"] == 0 else f"中转 {row['stops']} 次"
        summary_lines.append(
            f"<b>{row['rank']}.</b> {row['currency']} {row['price']:,.0f} | "
            f"{row['date']} -> {row['return_date'] or '单程'} | "
            f"{row['airline']} {row['outbound_flights']} | "
            f"{transfer_text}"
        )
    summary_lines.append(f"<b>比价提示：</b>{build_pdf_advice(rows)}")
    summary_lines.append(
        f"<b>价格口径：</b>{top_rows[0]['price_basis']}；"
        "退改与出票方以出票页为准。"
    )
    callout = Table(
        [[paragraph("<b>核心结果</b><br/>" + "<br/>".join(summary_lines), callout_style)]],
        colWidths=[263 * mm],
        hAlign="LEFT",
    )
    callout.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EAF3F1")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#84B7AA")),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story += [callout, Spacer(1, 3 * mm)]
    story.append(paragraph(f"前 {len(top_rows)} 个方案", ParagraphStyle(
        "FlightSection",
        parent=styles["Heading2"],
        fontName=bold_font,
        fontSize=11.5,
        leading=16,
        textColor=colors.HexColor("#17324D"),
        spaceBefore=0,
        spaceAfter=1.5 * mm,
    )))

    headers = ["排名", "去程", "回程", "票价 / 口径", "中转", "行李", "退改", "出票方", "航班", "路线", "机型", "备注"]
    table_rows: list[list[Paragraph]] = [
        [paragraph(f"<b>{header}</b>", small_style) for header in headers]
    ]
    for row in top_rows:
        transfer = "直飞" if row["stops"] == 0 else f"{row['stops']} 次"
        table_rows.append(
            [
                paragraph(str(row["rank"]), small_style),
                paragraph(str(row["date"]), small_style),
                paragraph(str(row["return_date"] or "单程"), small_style),
                paragraph(f"{row['currency']} {row['price']:,.0f}<br/>{row['price_basis']}", small_style),
                paragraph(transfer, small_style),
                paragraph(str(row["baggage"] or "-"), small_style),
                paragraph(str(row["refund_change"] or "见出票页"), small_style),
                paragraph(str(row["provider"] or "Trip.com（见详情）"), small_style),
                paragraph(str(row["outbound_flights"]), small_style),
                paragraph(str(row["outbound_route"]), small_style),
                paragraph(str(row["aircraft"] or "-"), small_style),
                paragraph(str(row["notes"] or "-"), small_style),
            ]
        )

    table = Table(
        table_rows,
        colWidths=[8 * mm, 20 * mm, 20 * mm, 26 * mm, 9 * mm, 18 * mm, 27 * mm, 29 * mm, 40 * mm, 25 * mm, 23 * mm, 18 * mm],
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D8E0E8")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F8FA")]),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 3.5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
            ]
        )
    )
    story += [
        table,
        Spacer(1, 3 * mm),
        paragraph(
            "说明：价格与余票来自查询时点，出票前必须重新核价。"
            "行李、退改和机型字段没有可靠数据时保持空白或标注“见出票页”，不作推测。",
            small_style,
        ),
        paragraph(
            "完整字段和全部候选行可使用 --xlsx 生成 Excel；需要可编辑文字时使用 --docx。",
            small_style,
        ),
    ]

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont(regular_font, 7)
        canvas.setFillColor(colors.HexColor("#7A8794"))
        canvas.drawCentredString(
            page_size[0] / 2,
            8 * mm,
            f"仅比价、不出票 | {source} | 第 {doc.page} 页",
        )
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(path),
        pagesize=page_size,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
        title=title,
        author="Codex",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)


def write_docx(
    path: Path,
    rows: list[dict[str, Any]],
    data: dict[str, Any],
    top: int,
    title: str,
    source: str,
    source_url: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not HAS_DOCX:
        raise SystemExit("python-docx missing — pip install python-docx")
    document = Document()
    section = document.sections[0]
    section.top_margin = Cm(1.6)
    section.bottom_margin = Cm(1.6)
    section.left_margin = Cm(1.8)
    section.right_margin = Cm(1.8)
    configure_document_styles(document)

    document.core_properties.title = title
    document.core_properties.author = "Codex"
    document.core_properties.subject = "Flight price and itinerary summary"

    heading = document.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = heading.add_run(title)
    run.bold = True
    run.font.size = Pt(19)
    run.font.color.rgb = RGBColor(0x17, 0x32, 0x4D)

    subtitle = document.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle_run = subtitle.add_run(
        f"{data.get('origin') or ''} -> {data.get('dest') or ''} | "
        f"{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M')} | "
        f"{data.get('currency') or 'CNY'} | {source} | {source_url}"
    )
    subtitle_run.font.size = Pt(9)
    subtitle_run.font.color.rgb = RGBColor(0x5B, 0x6B, 0x7A)

    document.add_paragraph()
    section_heading = document.add_paragraph()
    section_run = section_heading.add_run("核心结果")
    section_run.bold = True
    section_run.font.size = Pt(13)
    section_run.font.color.rgb = RGBColor(0x17, 0x32, 0x4D)

    summary_rows = rows[: min(3, len(rows))]
    for row in summary_rows:
        paragraph = document.add_paragraph(style="List Bullet")
        paragraph.add_run(
            f"第 {row['rank']} 名：{row['currency']} {row['price']:,.0f}，"
            f"{row['date']} -> {row['return_date'] or '单程'}，"
            f"{row['airline']} {row['outbound_flights']}"
        ).bold = True
    document.add_paragraph(f"比价提示：{build_pdf_advice(rows)}", style="List Bullet")

    document.add_paragraph()
    table_heading = document.add_paragraph()
    table_run = table_heading.add_run(f"前 {min(top, len(rows))} 个方案")
    table_run.bold = True
    table_run.font.size = Pt(13)
    table_run.font.color.rgb = RGBColor(0x17, 0x32, 0x4D)

    visible_columns = [
        ("rank", "排名"),
        ("date", "去程"),
        ("return_date", "回程"),
        ("price", "票价 / 口径"),
        ("stops", "中转"),
        ("baggage", "行李"),
        ("refund_change", "退改"),
        ("provider", "出票方"),
        ("airline", "航司"),
        ("outbound_flights", "去程航班"),
        ("outbound_route", "路线"),
        ("return_flights", "返程航班"),
        ("aircraft", "机型"),
    ]
    table = document.add_table(rows=1, cols=len(visible_columns))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"
    for index, (_, label) in enumerate(visible_columns):
        cell = table.rows[0].cells[index]
        cell.text = label
        shade_cell(cell, "17324D")
        for run in cell.paragraphs[0].runs:
            run.bold = True
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    for row in rows[:top]:
        cells = table.add_row().cells
        for index, (key, _) in enumerate(visible_columns):
            value = row.get(key, "")
            if key == "price":
                value = f"{row['currency']} {float(value):,.0f} / {row['price_basis']}"
            if key == "stops":
                value = "直飞" if value == 0 else f"{value} 次"
            cells[index].text = str(value or "")

    document.add_paragraph()
    note_heading = document.add_paragraph()
    note_run = note_heading.add_run("说明")
    note_run.bold = True
    note_run.font.size = Pt(11)
    document.add_paragraph(
        "价格与余票来自查询时点，出票前必须重新核价。"
        "机票 JSON 不含行李或机型时，对应列保持空白，不得推测。",
        style="List Bullet",
    )
    document.add_paragraph(
        f"数据来源：{source_url}。仅比价、不出票。",
        style="List Bullet",
    )
    document.add_paragraph(
        "完整字段和全部候选行见配套 XLSX。",
        style="List Bullet",
    )

    document.save(path)


def configure_document_styles(document: Document) -> None:
    styles = document.styles
    for style_name in ("Normal", "List Bullet"):
        style = styles[style_name]
        style.font.name = "Arial"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "PingFang SC")
        style.font.size = Pt(9.5)


def shade_cell(cell: Any, hex_color: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shade = OxmlElement("w:shd")
    shade.set(qn("w:fill"), hex_color)
    properties.append(shade)


def compact_summary(
    rows: list[dict[str, Any]],
    pdf: Path | None,
    xlsx: Path | None,
    docx: Path | None,
) -> str:
    lines = [f"Rows: {len(rows)}"]
    if pdf:
        lines.append(f"PDF: {pdf}")
    if xlsx:
        lines.append(f"XLSX: {xlsx}")
    if docx:
        lines.append(f"DOCX: {docx}")
    if rows:
        best = rows[0]
        lines.append(
            f"Cheapest: {best['currency']} {best['price']:,.0f} | "
            f"{best['date']} -> {best['return_date'] or 'one-way'} | "
            f"{best['airline']} {best['outbound_flights']}"
        )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    if args.top < 1:
        raise ValueError("--top must be at least 1")

    input_path = Path(args.input).expanduser().resolve()
    data = load_input(input_path)
    rows = collect_candidates(data)
    if not rows:
        raise ValueError("no priced itineraries found in input JSON")

    pdf, xlsx, docx = resolve_outputs(args, input_path)
    if pdf:
        write_pdf(pdf.resolve(), rows, data, args.top, args.title, args.source, args.source_url)
    if xlsx:
        write_xlsx(xlsx.resolve(), rows, data, args.top, args.title, args.source, args.source_url)
    if docx:
        write_docx(docx.resolve(), rows, data, args.top, args.title, args.source, args.source_url)

    print(
        compact_summary(
            rows,
            pdf.resolve() if pdf else None,
            xlsx.resolve() if xlsx else None,
            docx.resolve() if docx else None,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        message = " ".join(str(exc).split())[:450]
        print(f"error: {message}")
        raise SystemExit(1)
