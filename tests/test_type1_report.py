"""Tests for models/type1_model.py and services/type1_report.py.

These tests assume the updated API: learn(rows, year, month) and generate(seed).
"""
from calendar import monthrange
from dataclasses import replace
from datetime import date, time
from pathlib import Path

import pytest

from models.type1_model import OFF_WEEKDAYS, Type1Data, Type1Row
from services.base_report import FONT_CANDIDATES
from services.time_parser import CleanRow
from services.type1_report import Type1Report

HAS_FONT = any(Path(p).exists() for p in FONT_CANDIDATES)
YEAR, MONTH = 2026, 3


def make_source_rows(year: int = YEAR, month: int = MONTH) -> list[CleanRow]:
    """A fake source month: Friday/Saturday empty, other days 8-10 hour shifts."""
    rows = []
    for d in range(1, monthrange(year, month)[1] + 1):
        if date(year, month, d).weekday() in OFF_WEEKDAYS:
            rows.append(CleanRow(None, None, None))
        else:
            extra = d % 3
            rows.append(CleanRow(time(8, 0), time(16 + extra, 0), float(8 + extra)))
    return rows


@pytest.fixture
def learned_report() -> Type1Report:
    report = Type1Report()
    report.learn(make_source_rows(), YEAR, MONTH)
    return report


# ---------- model ----------
def test_model_summary_values():
    data = Type1Data(
        title="Test", year=YEAR, month=MONTH, hourly_rate=30.0,
        rows=[
            Type1Row(day=date(2026, 3, 2), entry=time(8, 0), exit=time(16, 0), total=8.0),
            Type1Row(day=date(2026, 3, 6)),   # Friday, empty
        ],
    )
    assert data.work_days == 1
    assert isinstance(data.rows, tuple)
    assert data.total_hours == 8.0
    assert data.payment == 240.0


# ---------- learn ----------
def test_learn_rejects_wrong_number_of_rows():
    report = Type1Report()
    with pytest.raises(ValueError):
        report.learn(make_source_rows()[:-1], YEAR, MONTH)


def test_learn_rejects_source_without_valid_rows():
    report = Type1Report()
    empty = [CleanRow(None, None, None) for _ in range(monthrange(YEAR, MONTH)[1])]
    with pytest.raises(ValueError):
        report.learn(empty, YEAR, MONTH)


def test_generate_before_learn_raises():
    with pytest.raises(RuntimeError):
        Type1Report().generate(seed=1)


# ---------- generate ----------
def test_generate_keeps_source_dates_and_days_off(learned_report):
    source = make_source_rows()
    data = learned_report.generate(seed=1)
    assert len(data.rows) == len(source)
    for i, (row, src) in enumerate(zip(data.rows, source), start=1):
        assert row.day == date(YEAR, MONTH, i)
        assert (row.entry is None) == src.is_empty


def test_generated_report_is_valid(learned_report):
    data = learned_report.generate(seed=1)
    assert learned_report.validate(data) == []


def test_generated_totals_match_exit_minus_entry(learned_report):
    data = learned_report.generate(seed=2)
    for r in data.rows:
        if r.entry is None:
            continue
        minutes = (r.exit.hour * 60 + r.exit.minute) - (r.entry.hour * 60 + r.entry.minute)
        assert r.total == pytest.approx(round(minutes / 60, 2), abs=0.01)


def test_same_seed_gives_same_report(learned_report):
    assert learned_report.generate(seed=5).rows == learned_report.generate(seed=5).rows


def test_different_seed_gives_different_report(learned_report):
    assert learned_report.generate(seed=1).rows != learned_report.generate(seed=2).rows


def test_hours_are_new_not_copied_from_source(learned_report):
    source = make_source_rows()
    data = learned_report.generate(seed=3)
    same = [
        r.entry == s.entry and r.exit == s.exit
        for r, s in zip(data.rows, source) if not s.is_empty
    ]
    assert not all(same)


# ---------- validate ----------
def test_validate_detects_work_on_friday(learned_report):
    data = learned_report.generate(seed=1)
    rows = tuple(
        replace(row, entry=time(8, 0), exit=time(9, 0), total=1.0)
        if row.day.weekday() == 4 else row
        for row in data.rows
    )
    assert learned_report.validate(replace(data, rows=rows))


def test_validate_detects_wrong_total(learned_report):
    data = learned_report.generate(seed=1)
    rows = tuple(
        replace(row, total=row.total + 3) if row.entry is not None else row
        for row in data.rows
    )
    assert learned_report.validate(replace(data, rows=rows))


def test_validate_detects_missing_rows(learned_report):
    data = learned_report.generate(seed=1)
    assert learned_report.validate(replace(data, rows=data.rows[:-1]))


def test_build_pdf_refuses_invalid_data(learned_report, tmp_path):
    data = learned_report.generate(seed=1)
    rows = tuple(
        replace(row, total=row.total + 5) if row.entry is not None else row
        for row in data.rows
    )
    data = replace(data, rows=rows)
    with pytest.raises(ValueError):
        learned_report.build_pdf(data, tmp_path / "bad.pdf")
    assert not (tmp_path / "bad.pdf").exists()


# ---------- PDF ----------
@pytest.mark.skipif(not HAS_FONT, reason="no Hebrew-capable font found")
def test_build_pdf_creates_a_valid_pdf(learned_report, tmp_path):
    data = learned_report.generate(seed=1)
    out = learned_report.build_pdf(data, tmp_path / "sub" / "type1.pdf")
    assert out.exists()
    assert out.read_bytes().startswith(b"%PDF")