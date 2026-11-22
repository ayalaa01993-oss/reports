"""Classify supported attendance-report PDFs using report-specific headings and structure.

Type2 needs attendance column headings. Type1 needs date/time headings and a table.
Files without enough evidence are rejected as UnknownReportType.
"""
from dataclasses import dataclass

import config
from extractors.page_image import render_page_gray
from extractors.pdf_to_text import pdf_to_text
from extractors.table_grid import find_horizontal_lines, select_table_lines
from models.attendance_report import ReportType
from services.report_parser import TIME_RE, find_date

MIN_TYPE2_ROWS = 3
MIN_TYPE2_KEYWORDS = 2
MIN_TYPE1_LINES = 20      # table lines needed to call the page a type1 table (a month has 28+ rows)
TYPE2_ENTRY_KEYWORDS = ("כניסה", "יציאה", "הפסקה")
TYPE2_DETAIL_KEYWORDS = ("תאריך", "סה\"כ", "סהכ", "100%", "125%", "150%", "שבת")
TYPE1_DATE_KEYWORDS = ("תאריך",)
TYPE1_HOURS_KEYWORDS = ("שעת", "כניסה", "יציאה")


class UnknownReportType(Exception):
    """The PDF does not look like either report type."""


@dataclass
class Detection:
    kind: ReportType
    text: str          # OCR text, so type2 does not have to run OCR a second time
    reason: str        # short explanation, useful for debugging


def _count_type2_rows(text: str) -> tuple[int, int]:
    """Return (lines with >= 3 valid times, lines that also contain a date)."""
    with_times = with_dates = 0
    for line in text.splitlines():
        if len(TIME_RE.findall(line)) >= 3:
            with_times += 1
            if find_date(line):
                with_dates += 1
    return with_times, with_dates


def _has_type1_table(pdf_path: str) -> bool:
    gray = render_page_gray(pdf_path, dpi=config.OCR_DPI)
    return len(select_table_lines(find_horizontal_lines(gray))) >= MIN_TYPE1_LINES


def _has_type1_attendance_markers(text: str) -> bool:
    has_date_heading = any(keyword in text for keyword in TYPE1_DATE_KEYWORDS)
    has_hours_heading = any(keyword in text for keyword in TYPE1_HOURS_KEYWORDS)
    return has_date_heading and has_hours_heading


def _has_type2_attendance_markers(text: str) -> bool:
    has_entry_heading = any(keyword in text for keyword in TYPE2_ENTRY_KEYWORDS)
    detail_headings = sum(keyword in text for keyword in TYPE2_DETAIL_KEYWORDS)
    return has_entry_heading and detail_headings >= MIN_TYPE2_KEYWORDS


def detect_report(pdf_path: str, text: str | None = None) -> Detection:
    """Look at the PDF and decide which report type it is."""
    if text is None:
        text = pdf_to_text(pdf_path)

    with_times, with_dates = _count_type2_rows(text)
    has_type2_markers = _has_type2_attendance_markers(text)

    if with_times >= MIN_TYPE2_ROWS and has_type2_markers:
        return Detection(ReportType.TYPE2, text,
                         f"{with_times} attendance rows with 3 times "
                         f"({with_dates} with a date) and attendance column headings")
    if has_type2_markers:
        return Detection(ReportType.TYPE2, text, "attendance column headings found")

    has_type1_table = _has_type1_table(pdf_path)
    has_type1_markers = _has_type1_attendance_markers(text)
    if has_type1_table and has_type1_markers:
        return Detection(ReportType.TYPE1, text,
                         "attendance date/time headings and a table were found")

    raise UnknownReportType(
        "לא ניתן לזהות את הקובץ כדוח נוכחות נתמך. "
        f"נמצאו {with_times} שורות עם שלוש שעות, "
        f"{'נמצאו' if has_type2_markers else 'לא נמצאו'} כותרות נוכחות ל-type2, "
        f"{'נמצאה' if has_type1_table else 'לא נמצאה'} טבלה, "
        f"{'ונמצאו' if has_type1_markers else 'ולא נמצאו'} כותרות תאריך/שעות ל-type1."
    )