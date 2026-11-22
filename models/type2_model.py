from dataclasses import dataclass, field
from datetime import date, time
from types import MappingProxyType
from typing import Mapping


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
class Type2Row(BaseRow):
    """A type2 row: place, break, and the hours split by pay percentage."""
    place: str = ""
    break_minutes: int = 30
    h100: float = 0.0
    h125: float = 0.0
    h150: float = 0.0
    shabbat: float = 0.0


@dataclass(kw_only=True, frozen=True)
class Type2Data(BaseData):
    """A type2 report. Totals are always computed from the rows."""
    bonus: float = 0.0
    travel: float = 0.0

    @property
    def totals(self) -> dict:
        r = self.rows
        return {
            "days": len(r),
            "total": round(sum(x.total for x in r), 2),
            "h100": round(sum(x.h100 for x in r), 2),
            "h125": round(sum(x.h125 for x in r), 2),
            "h150": round(sum(x.h150 for x in r), 2),
            "shabbat": round(sum(x.shabbat for x in r), 2),
            "break_minutes": sum(x.break_minutes for x in r),
        }