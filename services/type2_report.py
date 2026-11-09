import random
import re
from calendar import monthrange
from collections import Counter
from datetime import date, time

from reportlab.pdfgen.canvas import Canvas

from models.type2_model import Type2Data, Type2Row
from services.base_report import BaseReport, heb

TIME_RE = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)")
HEBREW_DAYS = {6: "יום ראשון", 0: "יום שני", 1: "יום שלישי", 2: "יום רביעי",
               3: "יום חמישי", 4: "יום שישי", 5: "שבת"}
RIGHT = 565


def _m(t: time) -> int:
    return t.hour * 60 + t.minute


def _t(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


class Type2Report(BaseReport):
    """Type2 report: entry, exit, break, split into 100% / Shabbat. Summary at the bottom."""

    font_size = 8
    row_height = 17

    def __init__(self, company: str = "חברה לדוגמה", place: str = "מקום לדוגמה"):
        self.company = company        # intentionally fake name
        self.place = place
        self._entries: list[int] = []
        self._lengths: list[int] = []
        self._break = 30

    # ---------- Learning from OCR text ----------
    def parse_text(self, text: str) -> None:
        entries, lengths, breaks = [], [], []
        for line in text.splitlines():
            times = TIME_RE.findall(line)
            if len(times) < 3:
                continue
            try:
                entry = _m(time(int(times[0][0]), int(times[0][1])))
                exit_ = _m(time(int(times[1][0]), int(times[1][1])))
            except ValueError:
                continue
            brk = int(times[2][0]) * 60 + int(times[2][1])
            if exit_ <= entry or brk >= exit_ - entry:
                continue
            entries.append(entry)
            lengths.append(exit_ - entry)
            breaks.append(brk)
        if not entries:
            raise ValueError("לא נמצאו שורות נוכחות תקינות בטקסט")
        self._entries, self._lengths = entries, lengths
        self._break = Counter(breaks).most_common(1)[0][0]

    # ---------- Generation ----------
    def generate(self, year: int, month: int, seed: int | None = None) -> Type2Data:
        if not self._entries:
            raise RuntimeError("קודם צריך לקרוא parse_text")
        rng = random.Random(seed)
        rows = []
        for d in range(1, monthrange(year, month)[1] + 1):
            day = date(year, month, d)
            is_shabbat = day.weekday() == 5
            if rng.random() > (0.3 if is_shabbat else 0.75):
                continue
            entry = rng.choice(self._entries) + rng.choice([-10, -5, 0, 5, 10])
            length = rng.choice(self._lengths) + rng.choice([-15, 0, 0, 15])
            net = round((length - self._break) / 60, 2)
            rows.append(Type2Row(
                day=day, place=self.place, entry=_t(entry), exit=_t(entry + length),
                break_minutes=self._break, total=net,
                h100=0.0 if is_shabbat else net,
                shabbat=net if is_shabbat else 0.0,
            ))
        return Type2Data(title=self.company, rows=rows)

    # ---------- Validation ----------
    def validate(self, data: Type2Data) -> list[str]:
        errors = []
        if not data.rows:
            errors.append("אין שורות בדוח")
        seen = set()
        for r in data.rows:
            tag = r.day.isoformat()
            if r.day in seen:
                errors.append(f"{tag}: תאריך כפול")
            seen.add(r.day)
            if r.entry is None or r.exit is None or _m(r.exit) <= _m(r.entry):
                errors.append(f"{tag}: כניסה/יציאה לא תקינות")
                continue
            expected = round((_m(r.exit) - _m(r.entry) - r.break_minutes) / 60, 2)
            if abs(expected - r.total) > 0.01:
                errors.append(f"{tag}: סה\"כ {r.total} לא תואם {expected}")
            split = round(r.h100 + r.h125 + r.h150 + r.shabbat, 2)
            if abs(split - r.total) > 0.01:
                errors.append(f"{tag}: פירוק השעות ({split}) שונה מהסה\"כ")
            if (r.day.weekday() == 5) != (r.shabbat > 0):
                errors.append(f"{tag}: שעות שבת לא תואמות ליום")
        days = sorted(seen)
        if days and (days[0].year, days[0].month) != (days[-1].year, days[-1].month):
            errors.append("הדוח חוצה יותר מחודש אחד")
        return errors

    # ---------- PDF rendering ----------
    @property
    def columns(self) -> list[str]:
        return ["תאריך", "יום", "מקום עבודה", "כניסה", "יציאה", "הפסקה",
                'סה"כ', "100%", "125%", "150%", "שבת"]

    def row_cells(self, r: Type2Row) -> list[str]:
        return [r.day.strftime("%d/%m/%Y"), HEBREW_DAYS[r.day.weekday()], r.place,
                r.entry.strftime("%H:%M"), r.exit.strftime("%H:%M"),
                f"{r.break_minutes // 60:02d}:{r.break_minutes % 60:02d}",
                f"{r.total:.2f}", f"{r.h100:.2f}", f"{r.h125:.2f}",
                f"{r.h150:.2f}", f"{r.shabbat:.2f}"]

    def draw_header(self, c: Canvas, data: Type2Data) -> float:
        c.setFont(c._fontname, 12)
        c.drawRightString(RIGHT, 805, heb(data.title))
        c.setFont(c._fontname, self.font_size)
        return 780

    def draw_summary(self, c: Canvas, data: Type2Data, y: float) -> None:
        t = data.totals
        items = [("ימים", t["days"]), ("סה\"כ שעות", f"{t['total']:g}"),
                 ("שעות 100%", f"{t['h100']:g}"), ("שעות 125%", f"{t['h125']:g}"),
                 ("שעות 150%", f"{t['h150']:g}"), ("שבת 150%", f"{t['shabbat']:g}"),
                 ("בונוס", f"{data.bonus:g}"), ("נסיעות", f"{data.travel:g}")]
        y -= 25
        for label, value in items:
            c.rect(RIGHT - 130, y - 4, 130, 16)
            c.drawRightString(RIGHT - 6, y, heb(label))
            c.drawString(RIGHT - 124, y, heb(str(value)))
            y -= 16