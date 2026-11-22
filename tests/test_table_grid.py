"""Tests for extractors/table_grid.py: grouping, line selection and detection."""
import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from extractors.table_grid import (  # noqa: E402
    _group,
    find_horizontal_lines,
    select_table_lines,
)


def test_group_merges_adjacent_indices():
    assert _group(np.array([10, 11, 12, 50, 51])) == [11, 50]


def test_select_keeps_evenly_spaced_lines():
    lines = [100, 150, 200, 250, 300, 350]
    assert select_table_lines(lines) == lines


def test_select_fills_in_a_missing_line():
    # The line at y=200 was not detected in the scan.
    assert select_table_lines([100, 150, 250, 300]) == [100, 150, 200, 250, 300]


def test_select_drops_duplicate_lines():
    # 103 is a duplicate of 100 (for example from a skewed scan).
    assert select_table_lines([100, 103, 150, 200, 250]) == [100, 150, 200, 250]


def test_select_short_input_is_returned_as_is():
    assert select_table_lines([100, 200]) == [100, 200]


def test_find_horizontal_lines_on_synthetic_image():
    img = np.full((800, 600), 255, dtype=np.uint8)
    expected = (100, 200, 300, 400)
    for y in expected:
        img[y - 1: y + 2, 20:580] = 0            # 3px thick black line
    found = find_horizontal_lines(img)
    assert len(found) == len(expected)
    for got, want in zip(found, expected):
        assert abs(got - want) <= 2