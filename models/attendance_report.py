from dataclasses import dataclass, field
from datetime import date, time
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class ReportType(Enum):
    TYPE1 = "type1"
    TYPE2 = "type2"


@dataclass(frozen=True)
class AttendanceRow:
    day: date
    entry: time | None = None
    exit: time | None = None
    total: float = 0.0
    break_minutes: int = 0
    place: str = ""
    note: str = ""
    h100: float = 0.0
    h125: float = 0.0
    h150: float = 0.0
    shabbat: float = 0.0
    is_holiday: bool = False
    suspicious: bool = False
    source_work_day: bool = False


@dataclass(frozen=True)
class AttendanceReport:
    report_type: ReportType
    title: str
    rows: tuple[AttendanceRow, ...] = ()
    metadata: Mapping[str, int | float | str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", tuple(self.rows))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
