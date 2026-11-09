from dataclasses import dataclass

from models.base_model import BaseData, BaseRow

OFF_WEEKDAYS = (4, 5)  # date.weekday(): Friday=4, Saturday=5


@dataclass(kw_only=True)
class Type1Row(BaseRow):
    """A type1 row: all fields are shared; an empty row (entry=None) is a day off."""
    note: str = ""

    @property
    def is_work_day(self) -> bool:
        return self.entry is not None


@dataclass(kw_only=True)
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