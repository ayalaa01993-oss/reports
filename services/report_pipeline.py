from pathlib import Path
from datetime import date
from typing import Protocol

import config
from extractors.pdf_to_text import pdf_to_text_file
from extractors.type1_reader import read_type1_pdf, write_type1_rows
from extractors.type2_dates import fill_missing_dates, read_type2_dates
from models.attendance_report import AttendanceReport, ReportType
from services.report_detector import detect_report
from services.report_generator import ReportGenerator
from services.report_parser import (
    TIME_RE,
    parse_type1_text,
    parse_type2_text,
    read_holiday_dates,
    type2_rows_need_date_ocr,
)
from services.report_transformer import transform_report


def _read_ocr_text(pdf_path: str) -> str:
    text_path = pdf_to_text_file(pdf_path)
    return text_path.read_text(encoding="utf-8")


def _read_holiday_dates(pdf_name: str) -> frozenset[date]:
    holiday_path = config.TEXT_DIR / f"{Path(pdf_name).stem}_holidays.txt"
    if not holiday_path.exists():
        return frozenset()
    return read_holiday_dates(holiday_path)


def _generate_output(
    report: AttendanceReport,
    pdf_name: str,
    output_format: str,
) -> Path:
    generator = ReportGenerator()
    if output_format == "pdf":
        path = config.OUTPUT_DIR / f"{Path(pdf_name).stem}_generated.pdf"
        return generator.generate_pdf(report, path)
    if output_format == "html":
        path = config.OUTPUT_DIR / f"{Path(pdf_name).stem}_generated.html"
        return generator.generate_html(report, path)
    raise ValueError("output_format must be 'pdf' or 'html'")


class ReportStrategy(Protocol):
    def generate(
        self,
        pdf_name: str,
        year: int | None,
        month: int | None,
        seed: int | None,
        text: str | None,
        output_format: str,
    ) -> Path: ...


class Type1ReportStrategy:
    def generate(
        self,
        pdf_name: str,
        year: int | None,
        month: int | None,
        seed: int | None,
        text: str | None,
        output_format: str,
    ) -> Path:
        if year is None or month is None:
            raise ValueError("A type1 report needs year and month (of the source report)")
        pdf_path = str(config.PDF_DIR / pdf_name)
        rows_path = config.TEXT_DIR / f"{Path(pdf_name).stem}_type1_rows.txt"
        write_type1_rows(read_type1_pdf(pdf_path), rows_path)
        source = parse_type1_text(
            rows_path.read_text(encoding="utf-8"),
            year,
            month,
            holidays=_read_holiday_dates(pdf_name),
        )
        transformed = transform_report(source, seed=seed)
        return _generate_output(transformed, pdf_name, output_format)


class Type2ReportStrategy:
    def generate(
        self,
        pdf_name: str,
        year: int | None,
        month: int | None,
        seed: int | None,
        text: str | None,
        output_format: str,
    ) -> Path:
        pdf_path = str(config.PDF_DIR / pdf_name)
        if text is None:
            text = _read_ocr_text(pdf_path)
        dates = None
        if type2_rows_need_date_ocr(text):
            dates, filled = fill_missing_dates(read_type2_dates(pdf_path))
            n_time_rows = sum(
                1 for line in text.splitlines()
                if len(TIME_RE.findall(line)) >= 3
            )
            if len(dates) != n_time_rows:
                print(
                    f"WARNING: {len(dates)} dates were read but the text has "
                    f"{n_time_rows} rows with times; a row may be missing"
                )
            if filled:
                print(
                    f"WARNING: dates were filled in automatically for rows {filled}; "
                    "check them against the PDF"
                )
        source = parse_type2_text(
            text,
            dates=dates,
            holidays=_read_holiday_dates(pdf_name),
        )
        transformed = transform_report(source, seed=seed)
        return _generate_output(transformed, pdf_name, output_format)


REPORT_STRATEGIES: dict[ReportType, ReportStrategy] = {
    ReportType.TYPE1: Type1ReportStrategy(),
    ReportType.TYPE2: Type2ReportStrategy(),
}


def make_type1(
    pdf_name: str,
    year: int,
    month: int,
    seed: int | None = None,
    output_format: str = "pdf",
) -> Path:
    return Type1ReportStrategy().generate(
        pdf_name, year, month, seed, None, output_format
    )


def make_type2(
    pdf_name: str,
    seed: int | None = None,
    text: str | None = None,
    output_format: str = "pdf",
) -> Path:
    return Type2ReportStrategy().generate(
        pdf_name, None, None, seed, text, output_format
    )


def make_report(
    pdf_name: str,
    year: int | None = None,
    month: int | None = None,
    seed: int | None = None,
    output_format: str = "pdf",
) -> Path:
    pdf_path = str(config.PDF_DIR / pdf_name)
    text = _read_ocr_text(pdf_path)
    detection = detect_report(pdf_path, text=text)
    print(f"{pdf_name}: {detection.kind.value} ({detection.reason})")
    try:
        strategy = REPORT_STRATEGIES[detection.kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported report type: {detection.kind}") from exc
    return strategy.generate(
        pdf_name=pdf_name,
        year=year,
        month=month,
        seed=seed,
        text=detection.text,
        output_format=output_format,
    )


def run_default_reports() -> None:
    print(make_report("type1_1.pdf", year=2026, month=3, seed=7))
    print(make_report("type2_1.pdf", seed=7))
