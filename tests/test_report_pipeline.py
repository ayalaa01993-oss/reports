from calendar import monthrange
import ast
from dataclasses import FrozenInstanceError, is_dataclass
from datetime import date, time
from pathlib import Path
from typing import get_args, get_origin, get_type_hints

import pytest

from models.attendance_report import AttendanceReport, ReportType
from services import report_pipeline
from services.report_detector import Detection, ReportType
from services.report_generator import ReportGenerator
from services.report_parser import (
    parse_type1_text,
    parse_type2_text,
    type2_rows_need_date_ocr,
)
from services.report_transformer import transform_report
from services.type2_report import MissingDatesError


def test_domain_models_do_not_depend_on_application_layers():
    model_dir = Path(__file__).parents[1] / "models"
    project_modules = {"models", "services", "extractors", "config", "main"}

    for path in model_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots = {node.module.split(".")[0]}
            else:
                continue
            assert roots.isdisjoint(project_modules), f"{path.name} imports project code"


def test_domain_data_models_are_frozen_and_report_rows_are_tuples():
    from models.attendance_report import AttendanceReport, AttendanceRow
    from models.base_model import BaseData, BaseRow
    from models.type1_model import Type1Data, Type1Row
    from models.type2_model import Type2Data, Type2Row

    model_types = (
        AttendanceReport, AttendanceRow, BaseData, BaseRow,
        Type1Data, Type1Row, Type2Data, Type2Row,
    )
    assert all(is_dataclass(model) and model.__dataclass_params__.frozen for model in model_types)
    for model in (AttendanceReport, BaseData, Type1Data, Type2Data):
        rows_type = get_type_hints(model)["rows"]
        assert get_origin(rows_type) is tuple
        assert get_args(rows_type)[1] is Ellipsis

    row = AttendanceRow(day=date(2026, 3, 1))
    report = AttendanceReport(report_type=ReportType.TYPE1, title="test", rows=[row])
    assert isinstance(report.rows, tuple)
    type1 = Type1Data(
        title="test", year=2026, month=3, hourly_rate=30,
        rows=[Type1Row(day=date(2026, 3, 1))],
    )
    type2 = Type2Data(
        title="test",
        rows=[Type2Row(day=date(2026, 3, 1))],
    )
    assert isinstance(type1.rows, tuple)
    assert isinstance(type2.rows, tuple)
    with pytest.raises(FrozenInstanceError):
        row.total = 1.0
    with pytest.raises(FrozenInstanceError):
        type1.title = "changed"
    with pytest.raises(FrozenInstanceError):
        type2.rows = ()
    with pytest.raises(TypeError):
        report.metadata["year"] = 2026


def test_generator_does_not_depend_on_parser_or_report_learning_services():
    path = Path(__file__).parents[1] / "services" / "report_generator.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = {
        "services.report_parser",
        "services.time_parser",
        "services.type1_report",
        "services.type2_report",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module not in forbidden
        elif isinstance(node, ast.Import):
            assert not any(alias.name in forbidden for alias in node.names)


def test_pytesseract_is_imported_only_by_ocr_adapter():
    project_root = Path(__file__).parents[1]
    importing_files = []
    for path in project_root.rglob("*.py"):
        if any(part in {".git", ".venv", "__pycache__"} for part in path.parts):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                alias.name == "pytesseract" for alias in node.names
            ):
                importing_files.append(path.relative_to(project_root))
            elif isinstance(node, ast.ImportFrom) and (
                node.module == "pytesseract"
                or (node.module and node.module.startswith("pytesseract."))
            ):
                importing_files.append(path.relative_to(project_root))

    assert importing_files == [Path("extractors/ocr_engine.py")]


def _type1_text(year=2026, month=3):
    lines = ["entry\texit\ttotal"]
    for day in range(1, monthrange(year, month)[1] + 1):
        if date(year, month, day).weekday() in (4, 5):
            lines.append("\t\t")
        else:
            lines.append("0800\t1600\t8.00")
    return "\n".join(lines)


def test_type1_parser_returns_unified_attendance_report():
    report = parse_type1_text(_type1_text(), year=2026, month=3)

    assert isinstance(report, AttendanceReport)
    assert report.report_type is ReportType.TYPE1
    assert len(report.rows) == 31
    assert report.rows[0].entry == time(8, 0)
    assert isinstance(report.rows[0].entry, time)
    assert isinstance(report.rows[0].exit, time)
    assert report.rows[6].entry is None


def test_type1_transformer_keeps_source_dates_and_days_off():
    source = parse_type1_text(_type1_text(), year=2026, month=3)

    generated = transform_report(source, seed=2)

    assert isinstance(generated, AttendanceReport)
    assert type(source) is type(generated) is AttendanceReport
    assert [row.day for row in generated.rows] == [row.day for row in source.rows]
    assert [row.entry is None for row in generated.rows] == [
        row.entry is None for row in source.rows
    ]
    assert all(
        row.entry is None or isinstance(row.entry, time)
        for row in generated.rows
    )
    assert all(
        row.exit is None or isinstance(row.exit, time)
        for row in generated.rows
    )


def test_type2_parser_requires_dates_when_ocr_misses_them():
    text = "\n".join(
        f"day place 08:00 17:00 00:30" for _ in range(3)
    )

    with pytest.raises(MissingDatesError):
        parse_type2_text(text)


def test_type2_missing_dates_are_detected_before_parsing():
    missing = "\n".join(
        f"place 08:00 17:00 00:30" for _ in range(3)
    )
    complete = "01/03/2026 place 08:00 17:00 00:30"

    assert type2_rows_need_date_ocr(missing)
    assert not type2_rows_need_date_ocr(complete)


def test_pipeline_resolves_missing_dates_before_single_parse(monkeypatch):
    text = "\n".join("place 08:00 17:00 00:30" for _ in range(3))
    dates = [date(2026, 3, day) for day in range(1, 4)]
    calls = []

    monkeypatch.setattr(report_pipeline, "_read_ocr_text", lambda _path: text)
    monkeypatch.setattr(
        report_pipeline,
        "detect_report",
        lambda *_args, **_kwargs: Detection(ReportType.TYPE2, text, "test"),
    )
    monkeypatch.setattr(
        report_pipeline, "read_type2_dates", lambda _path: dates
    )
    monkeypatch.setattr(
        report_pipeline,
        "fill_missing_dates",
        lambda found: (found, []),
    )

    def parse_once(source_text, dates=None, holidays=frozenset()):
        calls.append(("parse", source_text, dates))
        return AttendanceReport(report_type=ReportType.TYPE2, title="test")

    monkeypatch.setattr(report_pipeline, "parse_type2_text", parse_once)
    monkeypatch.setattr(
        report_pipeline,
        "transform_report",
        lambda source, seed=None: source,
    )
    monkeypatch.setattr(
        report_pipeline,
        "_generate_output",
        lambda *_args: Path("generated.pdf"),
    )

    result = report_pipeline.make_report("sample.pdf")

    assert result == Path("generated.pdf")
    assert calls == [("parse", text, dates)]


@pytest.mark.parametrize("kind", [ReportType.TYPE1, ReportType.TYPE2])
def test_report_service_dispatches_to_registered_strategy(monkeypatch, kind):
    text = "sample OCR text"
    selected = []

    class StrategySpy:
        def generate(self, **kwargs):
            selected.append(kwargs)
            return Path("generated.pdf")

    monkeypatch.setattr(report_pipeline, "_read_ocr_text", lambda _path: text)
    monkeypatch.setattr(
        report_pipeline,
        "detect_report",
        lambda *_args, **_kwargs: Detection(kind, text, "test"),
    )
    monkeypatch.setattr(
        report_pipeline,
        "REPORT_STRATEGIES",
        {kind: StrategySpy()},
    )

    result = report_pipeline.make_report(
        "sample.pdf", year=2026, month=3, seed=7, output_format="html"
    )

    assert result == Path("generated.pdf")
    assert selected == [{
        "pdf_name": "sample.pdf",
        "year": 2026,
        "month": 3,
        "seed": 7,
        "text": text,
        "output_format": "html",
    }]


def test_report_strategy_registry_maps_types_to_strategy_classes():
    assert set(report_pipeline.REPORT_STRATEGIES) == {
        ReportType.TYPE1,
        ReportType.TYPE2,
    }
    assert isinstance(
        report_pipeline.REPORT_STRATEGIES[ReportType.TYPE1],
        report_pipeline.Type1ReportStrategy,
    )
    assert isinstance(
        report_pipeline.REPORT_STRATEGIES[ReportType.TYPE2],
        report_pipeline.Type2ReportStrategy,
    )


def test_type2_parser_and_transformer_keep_source_dates():
    text = "\n".join(
        f"{day:02d}/03/2026 place 08:00 17:00 00:30"
        for day in range(1, 4)
    )
    source = parse_type2_text(text)

    generated = transform_report(source, seed=4)

    assert type(source) is type(generated) is AttendanceReport
    assert generated.report_type is ReportType.TYPE2
    assert [row.day for row in generated.rows] == [
        date(2026, 3, day) for day in range(1, 4)
    ]
    assert all(isinstance(row.entry, time) for row in generated.rows)
    assert all(isinstance(row.exit, time) for row in generated.rows)
    assert all(isinstance(row.break_minutes, int) for row in generated.rows)
    assert all(row.total == pytest.approx(round(
        (row.exit.hour * 60 + row.exit.minute
         - row.entry.hour * 60 - row.entry.minute - row.break_minutes) / 60,
        2,
    )) for row in generated.rows)


def test_type2_shabbat_and_marked_holiday_rows_have_no_hours():
    text = "\n".join([
        "06/03/2026 place 08:00 17:00 00:30",
        "07/03/2026 place 08:00 17:00 00:30",
        "08/03/2026 חג",
        "09/03/2026 place 08:00 17:00 00:30",
    ])
    source = parse_type2_text(text)

    generated = transform_report(source, seed=4)
    shabbat, holiday = generated.rows[1:3]

    assert shabbat.day == date(2026, 3, 7)
    assert shabbat.entry is None and shabbat.exit is None
    assert shabbat.total == 0
    assert shabbat.note == "שבת"
    assert holiday.day == date(2026, 3, 8)
    assert holiday.is_holiday
    assert holiday.entry is None and holiday.exit is None
    assert holiday.total == 0
    assert holiday.note == "חג"

    columns, rows = ReportGenerator()._html_table(generated)
    assert "הערות" in columns
    assert rows[1][-1] == "שבת"
    assert rows[2][-1] == "חג"


def test_type1_parser_keeps_manually_marked_holiday_row_without_hours():
    lines = ["entry\texit\ttotal\tholiday"]
    for day in range(1, monthrange(2026, 3)[1] + 1):
        marked = day == 2
        if date(2026, 3, day).weekday() in (4, 5) or marked:
            lines.append(f"\t\t\t{'חג' if marked else ''}")
        else:
            lines.append("0800\t1600\t8.00\t")

    source = parse_type1_text("\n".join(lines), year=2026, month=3)
    generated = transform_report(source, seed=2)

    holiday = generated.rows[1]
    assert holiday.is_holiday
    assert holiday.entry is None and holiday.exit is None
    assert holiday.total == 0
    assert holiday.note == "חג"


def test_holiday_date_file_marks_and_adds_report_rows(tmp_path):
    holiday_file = tmp_path / "type2_holidays.txt"
    holiday_file.write_text(
        "# one ISO date per line\n2026-03-08\n",
        encoding="utf-8",
    )
    holidays = report_pipeline.read_holiday_dates(holiday_file)
    text = "06/03/2026 place 08:00 17:00 00:30\n09/03/2026 place 08:00 17:00 00:30"

    source = parse_type2_text(text, holidays=holidays)

    holiday = next(row for row in source.rows if row.day == date(2026, 3, 8))
    assert holiday.is_holiday
    assert holiday.entry is None
    assert holiday.note == "חג"


def test_holiday_date_file_rejects_invalid_dates(tmp_path):
    holiday_file = tmp_path / "invalid_holidays.txt"
    holiday_file.write_text("not-a-date\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid holiday date"):
        report_pipeline.read_holiday_dates(holiday_file)


def test_generator_creates_valid_rtl_html(tmp_path):
    source = parse_type1_text(_type1_text(), year=2026, month=3)
    generated = transform_report(source, seed=2)

    output = ReportGenerator().generate_html(generated, tmp_path / "report.html")

    html = output.read_text(encoding="utf-8")
    assert '<html lang="he" dir="rtl">' in html
    assert "<table>" in html
    assert "סה״כ לתשלום" in html


def test_generator_accepts_the_unified_domain_model_only():
    from typing import get_type_hints

    assert get_type_hints(ReportGenerator.generate_pdf)["report"] is AttendanceReport
    assert get_type_hints(ReportGenerator.generate_html)["report"] is AttendanceReport
    assert get_type_hints(transform_report)["source"] is AttendanceReport
    assert get_type_hints(transform_report)["return"] is AttendanceReport
