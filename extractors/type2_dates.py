"""Read the date column of a scanned type2 report.

Why: the full-page OCR reads the times in type2 well, but drops the date column
(it comes out as a single digit). So the dates are read separately:
  1. Find the table rows from the time words (they are read reliably).
  2. Find the date column: the rightmost block of ink inside the rows area.
  3. OCR only that column, one row at a time, digits and '/' only.
  4. Rows that could not be read are kept as None (so the position is not lost),
     and fill_missing_dates() completes them from their neighbours.
"""
import re
from collections import Counter
from datetime import date, timedelta

import cv2
import numpy as np
from PIL import Image

import config
from extractors.page_image import render_page_gray
from extractors.ocr_engine import image_to_data, image_to_string
from extractors.pdf_to_text import _preprocess

_TIME_WORD = re.compile(r"(?<!\d)\d{1,2}:\d{2}(?!\d)")
_DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
_DATE_CONFIG = "--psm 7 -c tessedit_char_whitelist=0123456789/"

MIN_TIMES_PER_ROW = 3      # entry, exit and break are read as times
TEXT_HEIGHT_TARGET = 36    # px: scale small text up to about this height before OCR


def _find_row_bands(gray: np.ndarray) -> tuple[list[tuple[int, int]], float]:
    """Return ([(top, bottom) of every table row], median text height), found by the time words."""
    data = image_to_data(Image.fromarray(gray), lang="heb", config="--psm 6")
    words = [(data["top"][i], data["top"][i] + data["height"][i])
             for i, t in enumerate(data["text"]) if _TIME_WORD.search(t)]
    if not words:
        return [], 0.0
    height = float(np.median([b - t for t, b in words]))
    words.sort(key=lambda w: (w[0] + w[1]) / 2)

    # words whose vertical centers are close belong to the same row
    rows: list[list[tuple[int, int]]] = [[words[0]]]
    for w in words[1:]:
        last = rows[-1]
        last_center = sum((t + b) / 2 for t, b in last) / len(last)
        if (w[0] + w[1]) / 2 - last_center > 0.6 * height:
            rows.append([w])
        else:
            last.append(w)
    bands = [(min(t for t, _ in r), max(b for _, b in r))
             for r in rows if len(r) >= MIN_TIMES_PER_ROW]
    return bands, height


def _find_date_column(gray: np.ndarray, y0: int, y1: int, height: float) -> tuple[int, int] | None:
    """The date column is the rightmost wide block of ink inside the rows area."""
    ink = (gray[y0:y1] < 140).sum(axis=0) > 0
    xs = np.where(ink)[0]
    if len(xs) == 0:
        return None
    gap = max(2.0, 0.5 * height)     # larger than the gaps inside a date, smaller than between columns
    runs, start, prev = [], xs[0], xs[0]
    for x in xs[1:]:
        if x - prev > gap:
            runs.append((int(start), int(prev)))
            start = x
        prev = x
    runs.append((int(start), int(prev)))
    wide = [r for r in runs if r[1] - r[0] >= 4 * height]   # a date is much wider than a speck of noise
    return wide[-1] if wide else None


def _parse_date(text: str) -> date | None:
    """Last dd/mm/yyyy in the text (junk from the neighbouring column may come before it)."""
    matches = _DATE.findall(text)
    if not matches:
        return None
    d, m, y = (int(g) for g in matches[-1])
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _drop_other_months(found: list[date | None]) -> list[date | None]:
    """A report covers one month: mark readings from any other month as None (OCR slips).
    Positions are kept, nothing is removed from the list."""
    known = [d for d in found if d is not None]
    if not known:
        return found
    common = Counter((d.year, d.month) for d in known).most_common(1)[0][0]
    return [d if d is not None and (d.year, d.month) == common else None for d in found]


def _keep_consistent(found: list[date | None]) -> list[date | None]:
    """Mark as None every date that breaks the row order.

    Row j can come after row i only if date_j - date_i >= j - i (days only move forward,
    and one row is at least one day). That is the same as: (ordinal - index) never decreases.
    We keep the longest subsequence that satisfies this, and mark the rest as None.
    """
    idx = [i for i, d in enumerate(found) if d is not None]
    if not idx:
        return found
    keys = [found[i].toordinal() - i for i in idx]
    best = [1] * len(idx)
    prev = [-1] * len(idx)
    for a in range(len(idx)):
        for b in range(a):
            if keys[b] <= keys[a] and best[b] + 1 > best[a]:
                best[a], prev[a] = best[b] + 1, b
    end = max(range(len(idx)), key=best.__getitem__)
    keep = set()
    while end != -1:
        keep.add(idx[end])
        end = prev[end]
    return [d if i in keep else None for i, d in enumerate(found)]


def read_dates_from_image(gray: np.ndarray) -> list[date | None]:
    """Read the dates of all table rows, top to bottom, from a grayscale page image.
    One item per row. A row that could not be read (or whose reading does not fit
    the rows around it) is None, so its position is kept."""
    bands, height = _find_row_bands(gray)
    if not bands:
        return []
    x_range = _find_date_column(gray, bands[0][0] - 4, bands[-1][1] + 4, height)
    if x_range is None:
        return []

    scale = min(3.0, max(1.0, TEXT_HEIGHT_TARGET / height))
    pad_x, pad_y = int(0.3 * height), int(0.4 * height)
    found: list[date | None] = []
    for top, bottom in bands:
        cell = gray[max(top - pad_y, 0): bottom + pad_y,
                    max(x_range[0] - pad_x, 0): x_range[1] + pad_x]
        cell = cv2.resize(cell, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        cell = cv2.copyMakeBorder(cell, 15, 15, 15, 15, cv2.BORDER_CONSTANT, value=255)
        found.append(_parse_date(image_to_string(cell, lang="eng", config=_DATE_CONFIG)))

    return _keep_consistent(_drop_other_months(found))


def fill_missing_dates(dates: list[date | None]) -> tuple[list[date], list[int]]:
    """Fill the None items from their neighbours.
    Returns (full list of dates, 1-based row numbers that were filled in).

    Between two known dates we continue from the earlier one, one day per row.
    (If days were skipped there, e.g. a day off, this is only a best guess.)
    Before the first known date we count backwards, after the last one forward.
    """
    if not dates:
        return [], []
    known = [i for i, d in enumerate(dates) if d is not None]
    if not known:
        raise ValueError("No date could be read from any row")

    out = list(dates)
    first, last = known[0], known[-1]
    for i in range(first):
        out[i] = dates[first] - timedelta(days=first - i)
    for a, b in zip(known, known[1:]):
        for i in range(a + 1, b):
            out[i] = dates[a] + timedelta(days=i - a)
    for i in range(last + 1, len(out)):
        out[i] = dates[last] + timedelta(days=i - last)

    if len({(d.year, d.month) for d in out}) > 1:
        raise ValueError("Filling the missing dates crossed into another month; check the dates by hand")
    filled = [i + 1 for i, d in enumerate(dates) if d is None]
    return out, filled


def read_type2_dates(pdf_path: str, dpi: int = config.OCR_DPI) -> list[date | None]:
    """One item per table row (None = not read). Empty list if no rows were found."""
    gray = render_page_gray(pdf_path, dpi=dpi)
    return read_dates_from_image(np.array(_preprocess(Image.fromarray(gray))))
