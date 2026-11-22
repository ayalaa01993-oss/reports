import random
from calendar import monthrange
from datetime import date, time
from reportlab.pdfgen.canvas import Canvas
from models.type1_model import OFF_WEEKDAYS, Type1Data, Type1Row
from services.base_report import BaseReport, heb
from services.hours_generator import HoursModel
from services.time_parser import CleanRow

HEBREW_DAYS = {6: "ראשון", 0: "שני", 1: "שלישי", 2: "רביעי", 3: "חמישי", 4: "שישי", 5: "שבת"}
MONTH_ABBR = ["ינו", "פבר", "מרץ", "אפר", "מאי", "יונ", "יול", "אוג", "ספט", "אוק", "נוב", "דצמ"]
RIGHT = 565

def _m(t: time) -> int:
    return t.hour * 60 + t.minute


def _t(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


class Type1Report(BaseReport):
    def __init__(self, worker: str = "עובד לדוגמה", hourly_rate: float = 30.0):
        self.worker = worker
        self.hourly_rate = hourly_rate
        self._model: HoursModel | None = None
        self._year = self._month = 0
        self._work_days: set[int] = set()

    def learn(self, rows: list[CleanRow], year: int, month: int) -> None:
        """year/month are those of the SOURCE report. Row i is day i of the month."""
        days_in_month = monthrange(year, month)[1]
        if len(rows) != days_in_month:
            raise ValueError(f"Expected {days_in_month} table rows for {month}/{year}, got {len(rows)}")
        good = [r for r in rows if r.entry and r.exit and not r.suspicious]
        if not good:
            raise ValueError("No valid rows to learn from")
        self._year, self._month = year, month
        self._work_days = {i for i, r in enumerate(rows, start=1) if not r.is_empty}
        self._model = HoursModel()
        self._model.fit([_m(r.entry) for r in good],
                        [_m(r.exit) - _m(r.entry) for r in good])

    def generate(self, seed: int | None = None) -> Type1Data:
        if self._model is None:
            raise RuntimeError("Call learn() first")
        rng = random.Random(seed)
        rows = []
        for d in range(1, monthrange(self._year, self._month)[1] + 1):
            day = date(self._year, self._month, d)
            if d not in self._work_days:      # same days off as the source
                rows.append(Type1Row(day=day))
                continue
            entry, length = self._model.sample(rng)
            rows.append(Type1Row(day=day, entry=_t(entry), exit=_t(entry + length),
                                 total=round(length / 60, 2)))
        return Type1Data(title=self.worker, year=self._year, month=self._month,
                         hourly_rate=self.hourly_rate, rows=rows)
    # ---------- Validation ----------
    def validate(self, data: Type1Data) -> list[str]:
        errors = []
        expected_days = monthrange(data.year, data.month)[1]
        if len(data.rows) != expected_days:
            errors.append(f"מספר שורות {len(data.rows)} במקום {expected_days}")
        for i, r in enumerate(data.rows, start=1):
            tag = r.day.isoformat()
            if r.day != date(data.year, data.month, min(i, expected_days)):
                errors.append(f"{tag}: שורה {i} לא ברצף הימים")
            if r.entry is None:
                if r.total:
                    errors.append(f"{tag}: שורה ריקה עם סה\"כ")
                continue
            if r.day.weekday() in OFF_WEEKDAYS:
                errors.append(f"{tag}: עבודה ביום שישי/שבת")
            if r.exit is None or _m(r.exit) <= _m(r.entry):
                errors.append(f"{tag}: יציאה לא אחרי כניסה")
                continue
            expected = round((_m(r.exit) - _m(r.entry)) / 60, 2)
            if abs(expected - r.total) > 0.01:
                errors.append(f"{tag}: סה\"כ {r.total} לא תואם {expected}")
        if data.hourly_rate <= 0:
            errors.append("תעריף שעתי לא חיובי")
        return errors

    # ---------- PDF rendering ----------
    @property
    def columns(self) -> list[str]:
        return ["תאריך", "יום בשבוע", "שעת כניסה", "שעת יציאה", 'סה"כ שעות', "הערות"]

    def row_cells(self, r: Type1Row) -> list[str]:
        if r.entry is None:
            return [f"{r.day.day}/{r.day.month}/{r.day.strftime('%y')}",
                    HEBREW_DAYS[r.day.weekday()], "", "", "", r.note]
        return [f"{r.day.day}/{r.day.month}/{r.day.strftime('%y')}",
                HEBREW_DAYS[r.day.weekday()],
                f"{r.entry.hour}:{r.entry.minute:02d}",
                f"{r.exit.hour}:{r.exit.minute:02d}",
                f"{r.total:.2f}", r.note]

    def draw_header(self, c: Canvas, data: Type1Data) -> float:
        c.setFont(c._fontname, 11)
        c.drawRightString(RIGHT, 805, heb(f"שם העובד: {data.title}"))
        items = [
            ("סה\"כ ימי עבודה לחודש", str(data.work_days)),
            ("סה\"כ שעות חודשיות", f"{data.total_hours:.2f}"),
            ("מחיר לשעה", f"{data.hourly_rate:.2f}"),
            ("סה\"כ לתשלום", f"{data.payment:,.2f}"),
        ]
        y = 780
        for label, value in items:
            c.rect(RIGHT - 300, y - 4, 300, 18)
            c.drawRightString(RIGHT - 6, y, heb(label))
            c.drawString(RIGHT - 294, y, heb(value))
            y -= 18
        c.drawRightString(RIGHT, y - 12,
                          heb(f"כרטיס עובד לחודש: {MONTH_ABBR[data.month - 1]}-{data.year % 100}"))
        c.setFont(c._fontname, self.font_size)
        return y - 30

    def draw_summary(self, c: Canvas, data: Type1Data, y: float) -> None:
        """In type1 the summary is already at the top of the page."""