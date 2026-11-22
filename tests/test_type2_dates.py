"""Tests for the scanned-type2 date handling: extractors/type2_dates.py and parse_text(dates=...)."""
from datetime import date

import pytest

pytest.importorskip("cv2")
pytest.importorskip("pytesseract")
pytest.importorskip("pymupdf")

from extractors.type2_dates import (  # noqa: E402
    _TIME_WORD,
    _drop_other_months,
    _keep_consistent,
    _parse_date,
    fill_missing_dates,
)
from services.type2_report import MissingDatesError, Type2Report  # noqa: E402

# Lines as the full-page OCR returns them for a scan: times are fine, the date column is lost.
SCANNED_TEXT = "\n".join(
    f" 2 יום ראשון גליליון ( {7 + d % 2:02d}:00 {15 + d % 2:02d}:00 6.50//00:30 6.500 /0.00"
    for d in range(1, 8)
)

D = lambda day, month=10: date(2022, month, day)


# ---------- _parse_date ----------
@pytest.mark.parametrize("text, expected", [
    ("02/10/2022", date(2022, 10, 2)),
    ("902/10/2022", date(2022, 10, 2)),       # junk digit from the neighbouring column
    ("7908/10/2022", date(2022, 10, 8)),
    ("29430/10/2022", date(2022, 10, 30)),
])
def test_parse_date_takes_the_last_full_date(text, expected):
    assert _parse_date(text) == expected


@pytest.mark.parametrize("text", ["", "12", "31/02/2022", "2/10/22"])
def test_parse_date_rejects_bad_text(text):
    assert _parse_date(text) is None


# ---------- parse_text with dates ----------
def test_scanned_text_without_dates_raises_missing_dates():
    with pytest.raises(MissingDatesError):
        Type2Report().parse_text(SCANNED_TEXT)


def test_missing_dates_error_is_a_value_error():
    assert issubclass(MissingDatesError, ValueError)


def test_parse_text_uses_dates_passed_in():
    dates = [date(2022, 10, d) for d in (2, 7, 8, 9, 11)]
    report = Type2Report()
    report.parse_text(SCANNED_TEXT, dates=dates)
    data = report.generate(seed=1)
    assert [r.day for r in data.rows] == dates
    assert report.validate(data) == []


def test_empty_dates_list_still_raises_missing_dates():
    with pytest.raises(MissingDatesError):
        Type2Report().parse_text(SCANNED_TEXT, dates=[])


# ---------- fill_missing_dates ----------
def test_fill_in_the_middle():
    out, filled = fill_missing_dates([D(5), None, D(7)])
    assert out == [D(5), D(6), D(7)]
    assert filled == [2]


def test_fill_at_the_start_and_at_the_end():
    out, filled = fill_missing_dates([None, D(3), D(4), None])
    assert out == [D(2), D(3), D(4), D(5)]
    assert filled == [1, 4]


def test_fill_with_skipped_days_continues_from_the_earlier_date():
    # 2 rows between the 2nd and the 9th: ambiguous, takes the earliest possible days
    out, _ = fill_missing_dates([D(2), None, None, D(9)])
    assert out == [D(2), D(3), D(4), D(9)]


def test_nothing_to_fill_reports_nothing():
    dates = [D(2), D(3), D(4)]
    assert fill_missing_dates(dates) == (dates, [])


def test_empty_list_and_all_none():
    assert fill_missing_dates([]) == ([], [])
    with pytest.raises(ValueError):
        fill_missing_dates([None, None])


def test_fill_that_leaves_the_month_raises():
    with pytest.raises(ValueError):
        fill_missing_dates([None, None, D(1)])     # would need Sep 29-30


# ---------- _keep_consistent ----------
def test_keep_consistent_drops_a_reading_that_breaks_the_order():
    # row 3 was read as the 1st although it sits between the 4th and the 6th
    assert _keep_consistent([D(3), D(4), D(1), D(6)]) == [D(3), D(4), None, D(6)]


def test_keep_consistent_drops_a_duplicate():
    assert _keep_consistent([D(3), D(4), D(4), D(6)]).count(None) == 1


def test_keep_consistent_survives_one_wrong_high_reading():
    # the 8th was read as the 28th: only that row is dropped, not everything after it
    assert _keep_consistent([D(7), D(28), D(9), D(10)]) == [D(7), None, D(9), D(10)]


# ---------- _drop_other_months ----------
def test_drop_other_months_keeps_positions():
    out = _drop_other_months([D(1), D(2, 11), D(3), None])
    assert out == [D(1), None, D(3), None]


# ---------- _TIME_WORD (the bug that dropped rows such as 7/10) ----------
@pytest.mark.parametrize("word", ["08:00", "00:30/", "(08:00", "8:05"])
def test_time_word_accepts_a_time_with_junk_next_to_it(word):
    assert _TIME_WORD.search(word)


@pytest.mark.parametrize("word", ["6.50", "100:300", "abc"])
def test_time_word_rejects_non_times(word):
    assert _TIME_WORD.search(word) is None