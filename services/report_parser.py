import csv
import io
import re
from calendar import monthrange
from dataclasses import replace
from datetime import date, time
from pathlib import Path

from models.attendance_report import AttendanceReport, AttendanceRow, ReportType
from services.time_parser import reconcile


BIDI_MARKS = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})(?!\d)")
DATE_REVERSED_RE = re.compile(r"(?<!\d)(\d{4})\s*/\s*(\d{1,2})\s*/\s*(\d{1,2})(?!\d)")
TIME_RE = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)")
HOLIDAY_RE = re.compile(r"חג|holiday", re.IGNORECASE)


class MissingDatesError(ValueError):
    """Time rows were found but their dates could not be parsed."""


def find_date(line: str) -> date | None:
    line = BIDI_MARKS.sub("", line)
    for regex, order in ((DATE_RE, "dmy"), (DATE_REVERSED_RE, "ymd")):
        match = regex.search(line)
        if match:
            a, b, c = (int(group) for group in match.groups())
            day, month, year = (a, b, c) if order == "dmy" else (c, b, a)
            try:
                return date(year, month, day)
            except ValueError:
                return None
    return None


def type2_rows_need_date_ocr(text: str) -> bool:
    """Return whether any valid attendance row in OCR text lacks a readable date."""
    for line in text.splitlines():
        line = BIDI_MARKS.sub("", line)
        times = TIME_RE.findall(line)
        if len(times) < 3:
            continue
        try:
            entry = time(int(times[0][0]), int(times[0][1]))
            exit_ = time(int(times[1][0]), int(times[1][1]))
            break_minutes = int(times[2][0]) * 60 + int(times[2][1])
        except ValueError:
            continue
        shift_minutes = exit_.hour * 60 + exit_.minute - entry.hour * 60 - entry.minute
        if exit_ > entry and break_minutes < shift_minutes and find_date(line) is None:
            return True
    return False


def parse_type1_text(
    text: str,
    year: int,
    month: int,
    title: str = "עובד לדוגמה",
    hourly_rate: float = 30.0,
    holidays: frozenset[date] = frozenset(),
) -> AttendanceReport:
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    fields = ("entry", "exit", "total")
    if reader.fieldnames not in (list(fields), [*fields, "holiday"]):
        raise ValueError("Invalid type1 OCR text format")

    rows = []
    for line_number, raw in enumerate(reader, start=2):
        if None in raw or any(raw[field] is None for field in fields):
            raise ValueError(f"Invalid type1 OCR row at line {line_number}")
        clean = reconcile(raw["entry"], raw["exit"], raw["total"])
        day_number = len(rows) + 1
        if day_number > monthrange(year, month)[1]:
            raise ValueError("Type1 OCR text contains more rows than days in its month")
        day = date(year, month, day_number)
        holiday = _is_holiday(raw.get("holiday", "")) or day in holidays
        rows.append(AttendanceRow(
            day=day,
            entry=None if holiday else clean.entry,
            exit=None if holiday else clean.exit,
            total=0.0 if holiday else clean.total or 0.0,
            is_holiday=holiday,
            note="חג" if holiday else "",
            suspicious=clean.suspicious,
            source_work_day=not holiday and not clean.is_empty,
        ))

    expected = monthrange(year, month)[1]
    if len(rows) != expected:
        raise ValueError(f"Expected {expected} type1 OCR rows, got {len(rows)}")
    return AttendanceReport(
        report_type=ReportType.TYPE1,
        title=title,
        rows=rows,
        metadata={"year": year, "month": month, "hourly_rate": hourly_rate},
    )


def parse_type2_text(
    text: str,
    dates: list[date] | None = None,
    title: str = "חברה לדוגמה",
    place: str = "מקום לדוגמה",
    holidays: frozenset[date] = frozenset(),
) -> AttendanceReport:
    rows = []
    timed_rows = []
    for line in text.splitlines():
        line = BIDI_MARKS.sub("", line)
        day = find_date(line)
        holiday = _is_holiday(line)
        times = TIME_RE.findall(line)
        if len(times) < 3:
            if day is not None and holiday:
                rows.append(AttendanceRow(
                    day=day,
                    is_holiday=True,
                    note="חג",
                ))
            continue
        try:
            entry = time(int(times[0][0]), int(times[0][1]))
            exit_ = time(int(times[1][0]), int(times[1][1]))
            break_minutes = int(times[2][0]) * 60 + int(times[2][1])
        except ValueError:
            continue
        if exit_ <= entry or break_minutes >= (
            exit_.hour * 60 + exit_.minute - entry.hour * 60 - entry.minute
        ):
            continue
        row = AttendanceRow(
            day=day or date.min,
            entry=entry,
            exit=exit_,
            break_minutes=break_minutes,
            place=place,
            is_holiday=holiday,
            note="חג" if holiday else "",
        )
        rows.append(row)
        timed_rows.append(row)

    if not timed_rows:
        if rows:
            return AttendanceReport(
                report_type=ReportType.TYPE2,
                title=title,
                rows=rows,
            )
        raise ValueError("No valid attendance rows found in text")
    if dates is not None:
        if len(dates) != len(timed_rows):
            raise ValueError(
                f"Expected {len(timed_rows)} dates for type2 rows, received {len(dates)}"
            )
        replacements = {id(row): day for row, day in zip(timed_rows, dates)}
        rows = [
            replace(row, day=replacements[id(row)]) if id(row) in replacements else row
            for row in rows
        ]
    elif any(row.day == date.min for row in rows):
        raise MissingDatesError(
            "Time rows found but dates are missing or unreadable; pass dates separately"
        )
    existing_dates = {row.day for row in rows}
    for holiday in sorted(holidays - existing_dates):
        rows.append(AttendanceRow(
            day=holiday,
            is_holiday=True,
            note="חג",
        ))
    rows = [
        replace(
            row,
            entry=None,
            exit=None,
            total=0.0,
            break_minutes=0,
            h100=0.0,
            h125=0.0,
            h150=0.0,
            shabbat=0.0,
            is_holiday=True,
            note="חג",
        ) if row.day in holidays else row
        for row in rows
    ]

    return AttendanceReport(
        report_type=ReportType.TYPE2,
        title=title,
        rows=rows,
    )


def _is_holiday(value: str | None) -> bool:
    return bool(value and HOLIDAY_RE.search(value))


def read_holiday_dates(path: str | Path) -> frozenset[date]:
    """Read manually marked holiday dates, one ISO date (YYYY-MM-DD) per line."""
    holidays = set()
    for line_number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        try:
            holidays.add(date.fromisoformat(value))
        except ValueError as exc:
            raise ValueError(
                f"Invalid holiday date at {path}:{line_number}: {value!r}"
            ) from exc
    return frozenset(holidays)
