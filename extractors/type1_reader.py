import csv
from dataclasses import dataclass
from pathlib import Path

import config
from extractors.cell_reader import read_cell
from extractors.page_image import render_page_gray
from extractors.table_grid import find_horizontal_lines, select_table_lines


@dataclass
class RawRow:
    """Raw OCR text, before any correction."""
    entry: str
    exit: str
    total: str


TYPE1_TEXT_FIELDS = ("entry", "exit", "total")


def read_type1_pdf(pdf_path: str) -> list[RawRow]:
    """Read a type1 report and return one raw row per table day, in order."""
    gray = render_page_gray(pdf_path, dpi=config.OCR_DPI)
    width = gray.shape[1]
    lines = select_table_lines(find_horizontal_lines(gray))
    if len(lines) < 2:
        raise ValueError("לא נמצאה טבלה בדף")

    spans = {name: (int(a * width) + config.CELL_H_PAD, int(b * width) - config.CELL_H_PAD)
             for name, (a, b) in config.TYPE1_COLUMNS.items()}
    rows = []
    for top, bottom in zip(lines, lines[1:]):
        pad = 8  # stay away from the grid lines themselves
        cells = {name: read_cell(gray[top + pad: bottom - pad, x0:x1])
                 for name, (x0, x1) in spans.items()}
        rows.append(RawRow(**cells))
    return rows


def write_type1_rows(rows: list[RawRow], text_path: str | Path) -> Path:
    """Save cell-by-cell OCR results as tab-separated text."""
    path = Path(text_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=TYPE1_TEXT_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(
            {"entry": row.entry, "exit": row.exit, "total": row.total}
            for row in rows
        )
    return path


def read_type1_rows(text_path: str | Path) -> list[RawRow]:
    """Load cell-by-cell OCR results from their tab-separated text file."""
    with Path(text_path).open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file, delimiter="\t")
        if reader.fieldnames != list(TYPE1_TEXT_FIELDS):
            raise ValueError(f"Invalid type1 OCR text file format: {text_path}")
        rows = []
        for line_number, row in enumerate(reader, start=2):
            if None in row or any(row[field] is None for field in TYPE1_TEXT_FIELDS):
                raise ValueError(
                    f"Invalid type1 OCR row at line {line_number}: {text_path}"
                )
            rows.append(
                RawRow(entry=row["entry"], exit=row["exit"], total=row["total"])
            )
        return rows