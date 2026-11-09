from dataclasses import dataclass

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