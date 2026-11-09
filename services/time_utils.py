"""Cleaning and reconciling OCR values: times and totals, including rebuilding entry from exit minus total."""
import re
from dataclasses import dataclass
from datetime import time
from itertools import product

TOLERANCE_MIN = 1          # allowed difference in minutes, because the total is rounded to two decimals
MAX_SHIFT_HOURS = 12


def parse_time(text: str) -> time | None:
    """'8:01', '801', '1105' -> time. Returns None if it does not look like a time."""
    digits = re.sub(r"[^\d]", "", text or "")
    if len(digits) not in (3, 4):
        return None
    hour, minute = int(digits[:-2]), int(digits[-2:])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour, minute)


def parse_hours(text: str) -> float | None:
    """'3.07' or '307' (a lost decimal point) -> 3.07."""
    text = (text or "").strip()
    if re.fullmatch(r"\d{1,2}\.\d{1,2}", text):
        value = float(text)
    elif re.fullmatch(r"\d{3}", text):
        value = int(text) / 100
    else:
        return None
    return value if 0 < value <= MAX_SHIFT_HOURS else None


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _from_minutes(m: int) -> time:
    m %= 24 * 60
    return time(m // 60, m % 60)


# Digits that Tesseract tends to confuse in these scans
CONFUSABLE = {"1": "4", "4": "1"}


def _variants(text: str) -> list[str]:
    """The original text, plus versions where one digit was swapped for a look-alike."""
    out = [text]
    for i, ch in enumerate(text):
        if ch in CONFUSABLE:
            out.append(text[:i] + CONFUSABLE[ch] + text[i + 1:])
    return out


def _repair(entry_text: str, exit_text: str, total_text: str):
    """Search for a combination of small digit fixes that makes the three readings consistent
    (exit - entry = total). Prefers the combination with the fewest changes."""
    best = None
    for e, x, t in product(_variants(entry_text), _variants(exit_text), _variants(total_text)):
        entry, exit_, total = parse_time(e), parse_time(x), parse_hours(t)
        if None in (entry, exit_, total):
            continue
        if abs(_minutes(exit_) - _minutes(entry) - total * 60) > TOLERANCE_MIN:
            continue
        changes = (e != entry_text) + (x != exit_text) + (t != total_text)
        if best is None or changes < best[0]:
            best = (changes, entry, exit_, total)
    return best

@dataclass
class CleanRow:
    entry: time | None
    exit: time | None
    total: float | None
    suspicious: bool = False   # data is inconsistent, worth checking by hand

    @property
    def is_empty(self) -> bool:
        return self.entry is None and self.exit is None and self.total is None


def reconcile(entry_text: str, exit_text: str, total_text: str) -> CleanRow:
    """Combine three OCR readings into one consistent row.
    Rule: entry ~ exit - total. If the OCR entry is far from the rebuilt one, prefer the rebuilt one."""
    entry, exit_, total = parse_time(entry_text), parse_time(exit_text), parse_hours(total_text)

    if entry is None and exit_ is None and total is None:
        return CleanRow(None, None, None)

    repaired = _repair(entry_text, exit_text, total_text)
    if repaired is not None:
        _, entry, exit_, total = repaired
        return CleanRow(entry, exit_, total)

    if exit_ is not None and total is not None:
        rebuilt = _minutes(exit_) - round(total * 60)
        if entry is None or abs(_minutes(entry) - rebuilt) > TOLERANCE_MIN:
            return CleanRow(_from_minutes(rebuilt), exit_, total,
                            suspicious=entry is not None)
        return CleanRow(entry, exit_, total)

    if entry is not None and exit_ is not None:
        diff = _minutes(exit_) - _minutes(entry)
        return CleanRow(entry, exit_, round(diff / 60, 2), suspicious=True)

    return CleanRow(entry, exit_, total, suspicious=True)