import random
from datetime import time

import pytest

from services.hours_generator import HoursModel
from services.time_parser import CleanRow, parse_hours, parse_time, reconcile


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("8:05", time(8, 5)),
        ("0805", time(8, 5)),
        ("9.30", time(9, 30)),
        ("", None),
        ("1260", None),
        ("2500", None),
    ],
)
def test_parse_time(text, expected):
    assert parse_time(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("8.5", 8.5),
        ("850", 8.5),
        (" 12.00 ", 12.0),
        ("0", None),
        ("12.01", None),
        ("8:30", None),
    ],
)
def test_parse_hours(text, expected):
    assert parse_hours(text) == expected


def test_reconcile_empty_row():
    row = reconcile("", "", "")

    assert row == CleanRow(None, None, None)
    assert row.is_empty


def test_reconcile_repairs_confusable_digit():
    row = reconcile("840", "1640", "8.5")

    assert row == CleanRow(time(8, 10), time(16, 40), 8.5)
    assert not row.suspicious


def test_reconcile_rebuilds_entry_from_exit_and_total():
    row = reconcile("", "16:00", "8.0")

    assert row == CleanRow(time(8, 0), time(16, 0), 8.0)
    assert not row.suspicious


def test_reconcile_marks_inconsistent_row_suspicious():
    row = reconcile("08:00", "16:00", "")

    assert row == CleanRow(time(8, 0), time(16, 0), 8.0, suspicious=True)


def test_hours_model_fit_and_sample_respects_minimums_and_day_boundary():
    model = HoursModel()
    model.fit([1430, 1430], [600, 600])

    assert model.mean_e == 1430
    assert model.mean_l == 600
    assert model.std_e == model.MIN_STD_ENTRY
    assert model.std_l == model.MIN_STD_LENGTH
    assert model.corr == 0.0

    entry, length = model.sample(random.Random(1), min_length=720)

    assert length >= 720
    assert 0 <= entry
    assert entry + length < 24 * 60
