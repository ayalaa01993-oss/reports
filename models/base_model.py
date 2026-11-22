from dataclasses import dataclass, field
from datetime import date, time
from types import MappingProxyType
from typing import Mapping


@dataclass(kw_only=True, frozen=True)
class BaseRow:
    """Fields shared by every row in every report type."""
    day: date
    entry: time | None = None   # None = empty row (e.g. Friday/Saturday in type1)
    exit: time | None = None
    total: float = 0.0


@dataclass(kw_only=True, frozen=True)
class BaseData:
    """A full report: a placeholder for the header plus a list of rows."""
    title: str                                   # worker / company name (use a fake one!)
    header: Mapping[str, str] = field(default_factory=dict)  # free-form header fields
    rows: tuple[BaseRow, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "header", MappingProxyType(dict(self.header)))
        object.__setattr__(self, "rows", tuple(self.rows))

    @property
    def total_hours(self) -> float:
        return round(sum(r.total for r in self.rows), 2)