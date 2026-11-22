from calendar import monthrange
from datetime import date
from html import escape
from pathlib import Path

from bidi.algorithm import get_display
import config
from models.attendance_report import AttendanceReport, AttendanceRow, ReportType
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

FONT_CANDIDATES = config.FONT_CANDIDATES
FONT_NAME = config.FONT_NAME
HEBREW_DAYS = {
    6: "ראשון", 0: "שני", 1: "שלישי", 2: "רביעי",
    3: "חמישי", 4: "שישי", 5: "שבת",
}
MONTH_ABBR = [
    "ינו", "פבר", "מרץ", "אפר", "מאי", "יונ",
    "יול", "אוג", "ספט", "אוק", "נוב", "דצמ",
]


def _hebrew(text: object) -> str:
    return get_display(str(text))


class ReportGenerator:
    """Render a transformed attendance report as either PDF or HTML."""

    def generate_pdf(self, report: AttendanceReport, path: str | Path) -> Path:
        errors = self._validate(report)
        if errors:
            raise ValueError("הדוח לא תקין:\n" + "\n".join(errors))
        self._register_font()
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)

        canvas = Canvas(str(output), pagesize=A4)
        canvas.setFont(FONT_NAME, 10)
        header_drawers = {
            ReportType.TYPE1: self._draw_type1_header,
            ReportType.TYPE2: self._draw_type2_header,
        }
        y = header_drawers[report.report_type](canvas, report)
        y = self._draw_pdf_table(canvas, report, y)
        self._draw_pdf_summary(canvas, report, y)
        canvas.save()
        return output

    def generate_html(self, report: AttendanceReport, path: str | Path) -> Path:
        errors = self._validate(report)
        if errors:
            raise ValueError("הדוח לא תקין:\n" + "\n".join(errors))

        columns, rows = self._html_table(report)
        header = "".join(f"<th>{escape(value)}</th>" for value in columns)
        body = "".join(
            "<tr>" + "".join(f"<td>{escape(value)}</td>" for value in row) + "</tr>"
            for row in rows
        )
        summary = self._html_summary(report)
        document = f"""<!doctype html>
<html lang="he" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(report.title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #888; padding: .4rem; text-align: center; }}
    th {{ background: #15355f; color: white; }}
    .summary {{ margin-top: 1.5rem; }}
  </style>
</head>
<body>
  <h1>{escape(report.title)}</h1>
  <table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>
  <section class="summary">{summary}</section>
</body>
</html>
"""
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(document, encoding="utf-8")
        return output

    @staticmethod
    def _columns(report: AttendanceReport) -> list[str]:
        columns_by_type = {
            ReportType.TYPE1: [
                "תאריך", "יום בשבוע", "שעת כניסה", "שעת יציאה", 'סה"כ שעות', "הערות",
            ],
            ReportType.TYPE2: [
                "תאריך", "יום", "מקום עבודה", "כניסה", "יציאה", "הפסקה",
                'סה"כ', "100%", "125%", "150%", "שבת", "הערות",
            ],
        }
        try:
            return columns_by_type[report.report_type]
        except KeyError as exc:
            raise ValueError(f"Unsupported report type: {report.report_type}") from exc

    @classmethod
    def _row_cells(cls, report: AttendanceReport, row: AttendanceRow) -> list[str]:
        row_renderers = {
            ReportType.TYPE1: cls._type1_row_cells,
            ReportType.TYPE2: cls._type2_row_cells,
        }
        try:
            return row_renderers[report.report_type](row)
        except KeyError as exc:
            raise ValueError(f"Unsupported report type: {report.report_type}") from exc

    @classmethod
    def _type1_row_cells(cls, row: AttendanceRow) -> list[str]:
        day = f"{row.day.day}/{row.day.month}/{row.day.strftime('%y')}"
        if row.entry is None:
            return [day, cls._type1_day_name(row.day.weekday()), "", "", "", row.note]
        return [
            day,
            cls._type1_day_name(row.day.weekday()),
            f"{row.entry.hour}:{row.entry.minute:02d}",
            f"{row.exit.hour}:{row.exit.minute:02d}",
            f"{row.total:.2f}",
            row.note,
        ]

    @classmethod
    def _type2_row_cells(cls, row: AttendanceRow) -> list[str]:
        return [
            row.day.strftime("%d/%m/%Y"),
            cls._type2_day_name(row.day.weekday()),
            row.place,
            row.entry.strftime("%H:%M") if row.entry else "",
            row.exit.strftime("%H:%M") if row.exit else "",
            (
                f"{row.break_minutes // 60:02d}:{row.break_minutes % 60:02d}"
                if row.entry is not None else ""
            ),
            f"{row.total:.2f}",
            f"{row.h100:.2f}",
            f"{row.h125:.2f}",
            f"{row.h150:.2f}",
            f"{row.shabbat:.2f}",
            row.note,
        ]

    @classmethod
    def _html_table(cls, report: AttendanceReport) -> tuple[list[str], list[list[str]]]:
        return cls._columns(report), [
            cls._row_cells(report, row) for row in report.rows
        ]

    @staticmethod
    def _html_summary(report: AttendanceReport) -> str:
        summaries = {
            ReportType.TYPE1: ReportGenerator._type1_html_summary,
            ReportType.TYPE2: ReportGenerator._type2_html_summary,
        }
        try:
            return summaries[report.report_type](report)
        except KeyError as exc:
            raise ValueError(f"Unsupported report type: {report.report_type}") from exc

    @staticmethod
    def _type1_html_summary(report: AttendanceReport) -> str:
        total = sum(row.total for row in report.rows)
        items = [("סה״כ ימים", str(len(report.rows))), ("סה״כ שעות", f"{total:.2f}")]
        rate = float(report.metadata["hourly_rate"])
        items.extend([
            ("ימי עבודה", str(sum(row.entry is not None for row in report.rows))),
            ("תעריף לשעה", f"{rate:.2f}"),
            ("סה״כ לתשלום", f"{total * rate:.2f}"),
        ])
        return ReportGenerator._format_html_summary(items)

    @staticmethod
    def _type2_html_summary(report: AttendanceReport) -> str:
        total = sum(row.total for row in report.rows)
        items = [("סה״כ ימים", str(len(report.rows))), ("סה״כ שעות", f"{total:.2f}")]
        items.extend([
            ("שעות 100%", f"{sum(row.h100 for row in report.rows):.2f}"),
            ("שעות 125%", f"{sum(row.h125 for row in report.rows):.2f}"),
            ("שעות 150%", f"{sum(row.h150 for row in report.rows):.2f}"),
            ("שעות שבת", f"{sum(row.shabbat for row in report.rows):.2f}"),
        ])
        return ReportGenerator._format_html_summary(items)

    @staticmethod
    def _format_html_summary(items: list[tuple[str, str]]) -> str:
        return "<p>" + " | ".join(
            f"<strong>{escape(label)}:</strong> {escape(value)}"
            for label, value in items
        ) + "</p>"

    @staticmethod
    def _type1_day_name(weekday: int) -> str:
        return {
            6: "ראשון", 0: "שני", 1: "שלישי", 2: "רביעי",
            3: "חמישי", 4: "שישי", 5: "שבת",
        }[weekday]

    @staticmethod
    def _type2_day_name(weekday: int) -> str:
        return {
            6: "יום ראשון", 0: "יום שני", 1: "יום שלישי",
            2: "יום רביעי", 3: "יום חמישי", 4: "יום שישי", 5: "שבת",
        }[weekday]

    @staticmethod
    def _validate(report: AttendanceReport) -> list[str]:
        validators = {
            ReportType.TYPE1: ReportGenerator._validate_type1,
            ReportType.TYPE2: ReportGenerator._validate_type2,
        }
        try:
            validate = validators[report.report_type]
        except KeyError:
            return [f"Unsupported report type: {report.report_type}"]
        return validate(report)

    @staticmethod
    def _validate_type1(report: AttendanceReport) -> list[str]:
        errors = []
        if not report.rows:
            return ["אין שורות בדוח"]
        year, month = int(report.metadata["year"]), int(report.metadata["month"])
        date_days = monthrange(year, month)[1]
        if len(report.rows) != date_days:
            errors.append(f"מספר שורות {len(report.rows)} במקום {date_days}")
        for index, row in enumerate(report.rows, start=1):
            if row.day != date(year, month, min(index, date_days)):
                errors.append(f"{row.day.isoformat()}: שורה {index} לא ברצף הימים")
            if row.entry is None:
                if row.total:
                    errors.append(f"{row.day.isoformat()}: שורה ריקה עם סה\"כ")
                continue
            if row.day.weekday() in (4, 5):
                errors.append(f"{row.day.isoformat()}: עבודה ביום שישי/שבת")
            if row.exit is None or ReportGenerator._minutes(row.exit) <= ReportGenerator._minutes(row.entry):
                errors.append(f"{row.day.isoformat()}: יציאה לא אחרי כניסה")
                continue
            expected = round(
                (ReportGenerator._minutes(row.exit) - ReportGenerator._minutes(row.entry)) / 60,
                2,
            )
            if abs(expected - row.total) > 0.01:
                errors.append(f"{row.day.isoformat()}: סה\"כ {row.total} לא תואם {expected}")
        if float(report.metadata["hourly_rate"]) <= 0:
            errors.append("תעריף שעתי לא חיובי")
        return errors

    @staticmethod
    def _validate_type2(report: AttendanceReport) -> list[str]:
        errors = []
        if not report.rows:
            return ["אין שורות בדוח"]
        seen = set()
        for row in report.rows:
            tag = row.day.isoformat()
            if row.day in seen:
                errors.append(f"{tag}: תאריך כפול")
            seen.add(row.day)
            if row.entry is None and row.exit is None:
                if row.total or row.break_minutes or row.h100 or row.h125 or row.h150 or row.shabbat:
                    errors.append(f"{tag}: שורת שבת/חג צריכה להיות ללא שעות")
                if row.day.weekday() != 5 and not row.is_holiday:
                    errors.append(f"{tag}: שורה ללא שעות אינה מסומנת כשבת או חג")
                continue
            if row.entry is None or row.exit is None or ReportGenerator._minutes(row.exit) <= ReportGenerator._minutes(row.entry):
                errors.append(f"{tag}: כניסה/יציאה לא תקינות")
                continue
            expected = round(
                (ReportGenerator._minutes(row.exit) - ReportGenerator._minutes(row.entry)
                 - row.break_minutes) / 60,
                2,
            )
            if abs(expected - row.total) > 0.01:
                errors.append(f"{tag}: סה\"כ {row.total} לא תואם {expected}")
            split = round(row.h100 + row.h125 + row.h150 + row.shabbat, 2)
            if abs(split - row.total) > 0.01:
                errors.append(f"{tag}: פירוק השעות ({split}) שונה מהסה\"כ")
            if row.day.weekday() == 5 or row.is_holiday:
                errors.append(f"{tag}: שורת שבת/חג צריכה להיות ללא שעות")
        days = sorted(seen)
        if days and (days[0].year, days[0].month) != (days[-1].year, days[-1].month):
            errors.append("הדוח חוצה יותר מחודש אחד")
        return errors

    @staticmethod
    def _minutes(value) -> int:
        return value.hour * 60 + value.minute

    @staticmethod
    def _register_font() -> None:
        if FONT_NAME in pdfmetrics.getRegisteredFontNames():
            return
        for font_path in FONT_CANDIDATES:
            if Path(font_path).exists():
                pdfmetrics.registerFont(TTFont(FONT_NAME, font_path))
                return
        raise FileNotFoundError(
            "No Hebrew-capable font found; set REPORT_FONT_PATH to a font file"
        )

    @staticmethod
    def _draw_type1_header(canvas: Canvas, report: AttendanceReport) -> float:
        year, month = int(report.metadata["year"]), int(report.metadata["month"])
        work_rows = [row for row in report.rows if row.entry is not None]
        total_hours = sum(row.total for row in report.rows)
        rate = float(report.metadata["hourly_rate"])
        canvas.setFont(FONT_NAME, 11)
        canvas.drawRightString(565, 805, _hebrew(f"שם העובד: {report.title}"))
        items = [
            ("סה\"כ ימי עבודה לחודש", str(len(work_rows))),
            ("סה\"כ שעות חודשיות", f"{total_hours:.2f}"),
            ("מחיר לשעה", f"{rate:.2f}"),
            ("סה\"כ לתשלום", f"{total_hours * rate:,.2f}"),
        ]
        y = 780
        for label, value in items:
            canvas.rect(265, y - 4, 300, 18)
            canvas.drawRightString(559, y, _hebrew(label))
            canvas.drawString(271, y, _hebrew(value))
            y -= 18
        canvas.drawRightString(
            565, y - 12, _hebrew(f"כרטיס עובד לחודש: {MONTH_ABBR[month - 1]}-{year % 100}")
        )
        canvas.setFont(FONT_NAME, 10)
        return y - 30

    @staticmethod
    def _draw_type2_header(canvas: Canvas, report: AttendanceReport) -> float:
        canvas.setFont(FONT_NAME, 12)
        canvas.drawRightString(565, 805, _hebrew(report.title))
        canvas.setFont(FONT_NAME, 8)
        return 780

    @classmethod
    def _draw_pdf_table(cls, canvas: Canvas, report: AttendanceReport, y: float) -> float:
        width, _ = A4
        margin = 30
        columns = cls._columns(report)
        col_width = (width - 2 * margin) / len(columns)
        row_styles = {
            ReportType.TYPE1: (18, 10),
            ReportType.TYPE2: (17, 8),
        }
        try:
            row_height, font_size = row_styles[report.report_type]
        except KeyError as exc:
            raise ValueError(f"Unsupported report type: {report.report_type}") from exc
        canvas.setFont(FONT_NAME, font_size)

        def draw_line(cells, line_y):
            for index, value in enumerate(cells):
                right = width - margin - index * col_width
                canvas.rect(right - col_width, line_y - row_height, col_width, row_height)
                canvas.drawCentredString(
                    right - col_width / 2, line_y - row_height + 5, _hebrew(value)
                )

        draw_line(columns, y)
        y -= row_height
        for row in report.rows:
            draw_line(cls._row_cells(report, row), y)
            y -= row_height
        return y

    @staticmethod
    def _draw_pdf_summary(canvas: Canvas, report: AttendanceReport, y: float) -> None:
        summary_drawers = {
            ReportType.TYPE1: lambda _canvas, _report, _y: None,
            ReportType.TYPE2: ReportGenerator._draw_type2_pdf_summary,
        }
        try:
            summary_drawers[report.report_type](canvas, report, y)
        except KeyError as exc:
            raise ValueError(f"Unsupported report type: {report.report_type}") from exc

    @staticmethod
    def _draw_type2_pdf_summary(canvas: Canvas, report: AttendanceReport, y: float) -> None:
        total = sum(row.total for row in report.rows)
        items = [
            ("ימים", len(report.rows)),
            ("סה\"כ שעות", f"{total:g}"),
            ("שעות 100%", f"{sum(row.h100 for row in report.rows):g}"),
            ("שעות 125%", f"{sum(row.h125 for row in report.rows):g}"),
            ("שעות 150%", f"{sum(row.h150 for row in report.rows):g}"),
            ("שבת 150%", f"{sum(row.shabbat for row in report.rows):g}"),
        ]
        canvas.setFont(FONT_NAME, 8)
        y -= 25
        for label, value in items:
            canvas.rect(435, y - 4, 130, 16)
            canvas.drawRightString(559, y, _hebrew(label))
            canvas.drawString(441, y, _hebrew(value))
            y -= 16
