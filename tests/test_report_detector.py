"""Tests for services/report_detector.py. OCR and table detection are replaced with fakes,
so no PDF or Tesseract is needed."""
import shutil
from pathlib import Path

import pytest

pytest.importorskip("cv2")
pytest.importorskip("pytesseract")

import config  # noqa: E402
from services import report_detector as rd  # noqa: E402
from services.report_detector import (  # noqa: E402
    ReportType,
    UnknownReportType,
    detect_report,
)

TYPE2_TEXT = "\n".join(
    f"{d:02d}/03/2026 day place 08:00 17:00 00:30" for d in range(1, 6)
)
TYPE2_REPORT_TEXT = (
    "תאריך כניסה יציאה הפסקה סה\"כ 100% 125% 150%\n" + TYPE2_TEXT
)
GIBBERISH = "ו1ק 4ח ::: אבג 12 .. 8 1 4\nרר ?? 7 99 ננ"


def _no_table_check(_path):
    pytest.fail("the table check should not run for a clean type2 text")


def test_clean_text_is_type2(monkeypatch):
    monkeypatch.setattr(rd, "pdf_to_text", lambda p: TYPE2_REPORT_TEXT)
    monkeypatch.setattr(rd, "_has_type1_table", _no_table_check)
    result = detect_report("x.pdf")
    assert result.kind is ReportType.TYPE2
    assert result.text == TYPE2_REPORT_TEXT   # reused, so OCR does not run twice


def test_supplied_text_skips_pdf_ocr(monkeypatch):
    monkeypatch.setattr(rd, "pdf_to_text", lambda p: pytest.fail("OCR should not run"))
    monkeypatch.setattr(rd, "_has_type1_table", _no_table_check)

    result = detect_report("x.pdf", text=TYPE2_REPORT_TEXT)

    assert result.kind is ReportType.TYPE2
    assert result.text == TYPE2_REPORT_TEXT


def test_readable_column_titles_identify_type2(monkeypatch):
    monkeypatch.setattr(
        rd,
        "pdf_to_text",
        lambda p: "תאריך יום מקום כניסה יציאה הפסקה 100% 125% 150%",
    )
    monkeypatch.setattr(rd, "_has_type1_table", _no_table_check)
    assert detect_report("x.pdf").kind is ReportType.TYPE2


def test_attendance_headings_with_a_table_are_type1(monkeypatch):
    monkeypatch.setattr(
        rd, "pdf_to_text", lambda p: "תאריך יום בשבוע שעת כניסה שעת יציאה"
    )
    monkeypatch.setattr(rd, "_has_type1_table", lambda p: True)
    assert detect_report("x.pdf").kind is ReportType.TYPE1


def test_generic_table_without_attendance_headings_is_unknown(monkeypatch):
    monkeypatch.setattr(rd, "pdf_to_text", lambda p: GIBBERISH)
    monkeypatch.setattr(rd, "_has_type1_table", lambda p: True)
    with pytest.raises(UnknownReportType, match="דוח נוכחות"):
        detect_report("x.pdf")


def test_timetable_rows_without_attendance_headings_are_unknown(monkeypatch):
    timetable = "\n".join(
        f"{d:02d}/03/2026 08:00 12:00 13:00 17:00" for d in range(1, 6)
    )
    monkeypatch.setattr(rd, "pdf_to_text", lambda p: timetable)
    monkeypatch.setattr(rd, "_has_type1_table", lambda p: False)
    with pytest.raises(UnknownReportType, match="דוח נוכחות"):
        detect_report("x.pdf")


def test_gibberish_without_a_table_is_unknown(monkeypatch):
    monkeypatch.setattr(rd, "pdf_to_text", lambda p: GIBBERISH)
    monkeypatch.setattr(rd, "_has_type1_table", lambda p: False)
    with pytest.raises(UnknownReportType):
        detect_report("x.pdf")


def test_two_matching_lines_are_not_enough_for_type2(monkeypatch):
    two_lines = "תאריך כניסה יציאה הפסקה\n" + "\n".join(TYPE2_TEXT.splitlines()[:2])
    monkeypatch.setattr(rd, "pdf_to_text", lambda p: two_lines)
    monkeypatch.setattr(rd, "_has_type1_table", lambda p: False)
    with pytest.raises(UnknownReportType, match="דוח נוכחות"):
        detect_report("x.pdf")


def test_all_sample_pdfs_classify_using_saved_ocr_examples():
    examples = {
        ReportType.TYPE1: (config.TEXT_DIR / "type1_1.txt").read_text(encoding="utf-8"),
        ReportType.TYPE2: (config.TEXT_DIR / "type2_1.txt").read_text(encoding="utf-8"),
    }
    samples = (
        ("type1_1.pdf", ReportType.TYPE1),
        ("type1_2.pdf", ReportType.TYPE1),
        ("type2_1.pdf", ReportType.TYPE2),
        ("type2_2.pdf", ReportType.TYPE2),
    )

    for filename, expected in samples:
        pdf_path = config.PDF_DIR / filename
        assert pdf_path.is_file(), f"Missing sample PDF: {pdf_path}"
        result = detect_report(str(pdf_path), text=examples[expected])
        assert result.kind is expected, filename


TESSERACT_AVAILABLE = (
    Path(config.TESSERACT_CMD).is_file()
    or shutil.which(config.TESSERACT_CMD) is not None
)


@pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="Tesseract is not installed")
@pytest.mark.parametrize(
    ("filename", "expected"),
    (
        ("type1_1.pdf", ReportType.TYPE1),
        ("type1_2.pdf", ReportType.TYPE1),
        ("type2_1.pdf", ReportType.TYPE2),
        ("type2_2.pdf", ReportType.TYPE2),
    ),
)
def test_all_sample_pdfs_classify_with_live_ocr(filename, expected):
    pdf_path = config.PDF_DIR / filename
    assert pdf_path.is_file(), f"Missing sample PDF: {pdf_path}"
    assert detect_report(str(pdf_path)).kind is expected