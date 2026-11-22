from dataclasses import dataclass, field
from datetime import date, time
from types import MappingProxyType
from typing import Mapping

OFF_WEEKDAYS = (4, 5)  # date.weekday(): Friday=4, Saturday=5


@dataclass(kw_only=True, frozen=True)
class BaseRow:
    day: date
    entry: time | None = None
    exit: time | None = None
    total: float = 0.0


@dataclass(kw_only=True, frozen=True)
class BaseData:
    title: str
    header: Mapping[str, str] = field(default_factory=dict)
    rows: tuple[BaseRow, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "header", MappingProxyType(dict(self.header)))
        object.__setattr__(self, "rows", tuple(self.rows))

    @property
    def total_hours(self) -> float:
        return round(sum(row.total for row in self.rows), 2)


@dataclass(kw_only=True, frozen=True)
class Type1Row(BaseRow):
    """A type1 row: all fields are shared; an empty row (entry=None) is a day off."""
    note: str = ""

    @property
    def is_work_day(self) -> bool:
        return self.entry is not None


@dataclass(kw_only=True, frozen=True)
class Type1Data(BaseData):
    """A type1 report: summary at the top. Values here are computed, not stored."""
    year: int
    month: int
    hourly_rate: float

    @property
    def work_days(self) -> int:
        return sum(1 for r in self.rows if r.entry is not None)

    @property
    def payment(self) -> float:
        return round(self.total_hours * self.hourly_rate, 2)