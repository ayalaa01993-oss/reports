"""Tests for extractors/cell_reader.py.

The blank-cell tests need no Tesseract. The OCR smoke test is skipped when Tesseract
is not available, so it also works as a quick check of the installation.
"""
import shutil
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
pytest.importorskip("pytesseract")

import config  # noqa: E402
from extractors.cell_reader import is_blank, read_cell  # noqa: E402

HAS_TESSERACT = Path(config.TESSERACT_CMD).exists() or shutil.which("tesseract") is not None


def test_white_cell_is_blank():
    cell = np.full((60, 200), 255, dtype=np.uint8)
    assert is_blank(cell)
    assert read_cell(cell) == ""


def test_empty_array_returns_empty_string():
    assert read_cell(np.zeros((0, 0), dtype=np.uint8)) == ""


def test_cell_with_ink_is_not_blank():
    cell = np.full((60, 200), 255, dtype=np.uint8)
    cell[10:50, 20:180] = 0
    assert not is_blank(cell)


@pytest.mark.skipif(not HAS_TESSERACT, reason="Tesseract is not installed")
def test_read_cell_reads_digits():
    cell = np.full((100, 300), 255, dtype=np.uint8)
    cv2.putText(cell, "8:30", (30, 70), cv2.FONT_HERSHEY_SIMPLEX, 2.2, 0, 4)
    digits = "".join(ch for ch in read_cell(cell) if ch.isdigit())
    assert digits == "830"