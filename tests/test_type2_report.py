"""Tests for models/type2_model.py and services/type2_report.py.

These tests assume the updated API: parse_text(text) and generate(seed).
"""
from dataclasses import replace
from datetime import date, time
from pathlib import Path

import pytest

from models.type2_model import Type2Data, Type2Row
from services.base_report import FONT_CANDIDATES
from services.type2_report import Type2Report

HAS_FONT = any(Path(p).exists() for p in FONT_CANDIDATES)
SOURCE_DAYS = list(range(1, 11))   # 1-10 March 2026 (includes Saturday, March 7)


def make_source_text() -> str:
    """Fake OCR text in the format parse_text expects: date, entry, exit, break."""
    lines = ["Attendance report", "this line has no date or times"]
    for d in SOURCE_DAYS:
        entry = f"{7 + d % 3:02d}:00"
        exit_ = f"{16 + d % 3:02d}:00"
        lines.append(f"{d:02d}/03/2026 day place {entry} {exit_} 00:30 08:30")
    return "\n".join(lines)


@pytest.fixture
def learned_report() -> Type2Report:
    report = Type2Report()
    report.parse_text(make_source_text())
    return report


# ---------- model ----------
def test_model_totals():
    data = Type2Data(title="Test", rows=[
        Type2Row(day=date(2026, 3, 2), entry=time(8, 0), exit=time(17, 0),
                 break_minutes=30, total=8.5, h100=8.5),
        Type2Row(day=date(2026, 3, 7), entry=time(8, 0), exit=time(12, 30),
                 break_minutes=30, total=4.0, shabbat=4.0),
    ])
    totals = data.totals
    assert isinstance(data.rows, tuple)
    assert totals["days"] == 2
    assert totals["total"] == 12.5
    assert totals["h100"] == 8.5
    assert totals["shabbat"] == 4.0
    assert totals["break_minutes"] == 60


# ---------- parse_text ----------
def test_parse_text_without_valid_rows_raises():
    with pytest.raises(ValueError):
        Type2Report().parse_text("no attendance here\n12/03/2026 but no times")


def test_parse_text_skips_rows_where_break_is_longer_than_shift():
    text = "01/03/2026 x 08:00 08:20 00:30\n02/03/2026 x 08:00 17:00 00:30"
    report = Type2Report()
    report.parse_text(text)
    data = report.generate(seed=1)
    assert [r.day for r in data.rows] == [date(2026, 3, 2)]


def test_generate_before_parse_raises():
    with pytest.raises(RuntimeError):
        Type2Report().generate(seed=1)


# ---------- generate ----------
def test_generate_keeps_source_dates(learned_report):
    data = learned_report.generate(seed=1)
    assert [r.day for r in data.rows] == [date(2026, 3, d) for d in SOURCE_DAYS]


def test_generated_report_is_valid(learned_report):
    data = learned_report.generate(seed=1)
    assert learned_report.validate(data) == []


def test_generated_rows_are_arithmetically_consistent(learned_report):
    data = learned_report.generate(seed=4)
    for r in data.rows:
        minutes = (r.exit.hour * 60 + r.exit.minute) - (r.entry.hour * 60 + r.entry.minute)
        assert r.total == pytest.approx(round((minutes - r.break_minutes) / 60, 2), abs=0.01)
        assert r.h100 + r.h125 + r.h150 + r.shabbat == pytest.approx(r.total, abs=0.01)


def test_saturday_hours_go_to_shabbat_column(learned_report):
    data = learned_report.generate(seed=1)
    saturdays = [r for r in data.rows if r.day.weekday() == 5]
    assert saturdays, "the source dates should include a Saturday"
    for r in data.rows:
        assert (r.day.weekday() == 5) == (r.shabbat > 0)


def test_break_comes_from_source(learned_report):
    data = learned_report.generate(seed=1)
    assert {r.break_minutes for r in data.rows} == {30}


def test_same_seed_gives_same_report(learned_report):
    assert learned_report.generate(seed=9).rows == learned_report.generate(seed=9).rows


def test_different_seed_gives_different_report(learned_report):
    assert learned_report.generate(seed=1).rows != learned_report.generate(seed=2).rows


# ---------- validate ----------
def test_validate_detects_duplicate_date(learned_report):
    data = learned_report.generate(seed=1)
    assert learned_report.validate(replace(data, rows=data.rows + (replace(data.rows[0]),)))


def test_validate_detects_wrong_split(learned_report):
    data = learned_report.generate(seed=1)
    rows = tuple(
        replace(row, h100=0.0) if row.day.weekday() != 5 else row
        for row in data.rows
    )
    assert learned_report.validate(replace(data, rows=rows))


def test_validate_detects_wrong_total(learned_report):
    data = learned_report.generate(seed=1)
    rows = (replace(data.rows[0], total=data.rows[0].total + 2),) + data.rows[1:]
    assert learned_report.validate(replace(data, rows=rows))


def test_validate_detects_two_months(learned_report):
    data = learned_report.generate(seed=1)
    rows = data.rows[:-1] + (
        replace(data.rows[-1], day=date(2026, 4, 1), shabbat=0.0),
    )
    assert learned_report.validate(replace(data, rows=rows))


# ---------- PDF ----------
@pytest.mark.skipif(not HAS_FONT, reason="no Hebrew-capable font found")
def test_build_pdf_creates_a_valid_pdf(learned_report, tmp_path):
    data = learned_report.generate(seed=1)
    out = learned_report.build_pdf(data, tmp_path / "type2.pdf")
    assert out.exists()
    assert out.read_bytes().startswith(b"%PDF")