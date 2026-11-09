from dataclasses import dataclass

from models.base_model import BaseData, BaseRow


@dataclass(kw_only=True)
class Type2Row(BaseRow):
    """A type2 row: place, break, and the hours split by pay percentage."""
    place: str = ""
    break_minutes: int = 30
    h100: float = 0.0
    h125: float = 0.0
    h150: float = 0.0
    shabbat: float = 0.0


@dataclass(kw_only=True)
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