from dataclasses import dataclass, field
from datetime import date, time


@dataclass(kw_only=True)
class BaseRow:
    """Fields shared by every row in every report type."""
    day: date
    entry: time | None = None   # None = empty row (e.g. Friday/Saturday in type1)
    exit: time | None = None
    total: float = 0.0


@dataclass(kw_only=True)
class BaseData:
    """A full report: a placeholder for the header plus a list of rows."""
    title: str                                   # worker / company name (use a fake one!)
    header: dict[str, str] = field(default_factory=dict)  # free-form header fields
    rows: list[BaseRow] = field(default_factory=list)

    @property
    def total_hours(self) -> float:
        return round(sum(r.total for r in self.rows), 2)