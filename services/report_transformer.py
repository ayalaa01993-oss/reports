import random
from calendar import monthrange
from datetime import time

from models.attendance_report import AttendanceReport, AttendanceRow, ReportType
from services.hours_generator import HoursModel


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _time(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


def transform_report(
    source: AttendanceReport,
    seed: int | None = None,
) -> AttendanceReport:
    rng = random.Random(seed)
    transformers = {
        ReportType.TYPE1: _transform_type1,
        ReportType.TYPE2: _transform_type2,
    }
    try:
        transform = transformers[source.report_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported report type: {source.report_type}") from exc
    return transform(source, rng)


def _transform_type1(
    source: AttendanceReport,
    rng: random.Random,
) -> AttendanceReport:
    year = int(source.metadata["year"])
    month = int(source.metadata["month"])
    expected = monthrange(year, month)[1]
    if len(source.rows) != expected:
        raise ValueError(f"Expected {expected} type1 rows, got {len(source.rows)}")
    valid = [
        row for row in source.rows
        if row.entry is not None and row.exit is not None and not row.suspicious
    ]
    if not valid:
        raise ValueError("No valid rows to learn from")

    model = HoursModel()
    model.fit(
        [_minutes(row.entry) for row in valid],
        [_minutes(row.exit) - _minutes(row.entry) for row in valid],
    )
    transformed = []
    for row in source.rows:
        is_shabbat = row.day.weekday() == 5
        if is_shabbat or row.is_holiday or not (
            row.source_work_day or row.entry is not None
        ):
            transformed.append(AttendanceRow(
                day=row.day,
                note="חג" if row.is_holiday else "שבת" if is_shabbat else row.note,
                is_holiday=row.is_holiday,
            ))
            continue
        entry, length = model.sample(rng)
        transformed.append(AttendanceRow(
            day=row.day,
            entry=_time(entry),
            exit=_time(entry + length),
            total=round(length / 60, 2),
            note=row.note,
        ))
    return AttendanceReport(
        report_type=source.report_type,
        title=source.title,
        rows=transformed,
        metadata=dict(source.metadata),
    )


def _transform_type2(
    source: AttendanceReport,
    rng: random.Random,
) -> AttendanceReport:
    valid = [
        row for row in source.rows
        if row.entry is not None
        and row.exit is not None
        and row.day.weekday() != 5
        and not row.is_holiday
    ]
    if not valid:
        return AttendanceReport(
            report_type=source.report_type,
            title=source.title,
            rows=tuple(
                AttendanceRow(
                    day=row.day,
                    place=row.place,
                    note="חג" if row.is_holiday else "שבת",
                    is_holiday=row.is_holiday,
                )
                for row in source.rows
            ),
            metadata=dict(source.metadata),
        )
    model = HoursModel()
    entries = [_minutes(row.entry) for row in valid]
    lengths = [_minutes(row.exit) - _minutes(row.entry) for row in valid]
    model.fit(entries, lengths)
    breaks = [row.break_minutes for row in valid]

    transformed = []
    for row in source.rows:
        is_shabbat = row.day.weekday() == 5
        if is_shabbat or row.is_holiday or row.entry is None or row.exit is None:
            transformed.append(AttendanceRow(
                day=row.day,
                place=row.place,
                note="חג" if row.is_holiday else "שבת" if is_shabbat else row.note,
                is_holiday=row.is_holiday,
            ))
            continue
        break_minutes = rng.choice(breaks)
        entry, length = model.sample(rng, min_length=break_minutes + 30)
        net = round((length - break_minutes) / 60, 2)
        transformed.append(AttendanceRow(
            day=row.day,
            entry=_time(entry),
            exit=_time(entry + length),
            total=net,
            break_minutes=break_minutes,
            place=row.place,
            h100=0.0 if is_shabbat else net,
            shabbat=net if is_shabbat else 0.0,
        ))
    return AttendanceReport(
        report_type=source.report_type,
        title=source.title,
        rows=transformed,
        metadata=dict(source.metadata),
    )
