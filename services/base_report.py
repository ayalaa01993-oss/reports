from abc import ABC, abstractmethod
from pathlib import Path

from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from models.base_model import BaseData

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arial.ttf",                          # Windows
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",      # Linux
]
FONT_NAME = "ReportFont"


def heb(text: str) -> str:
    """Convert Hebrew text to visual order, because reportlab does not handle RTL."""
    return get_display(str(text))


class BaseReport(ABC):
    """Shared skeleton. Each report type fills in only what makes it different."""

    page_size = A4
    row_height = 18
    font_size = 10

    # ---------- What every report type must define ----------
    @property
    @abstractmethod
    def columns(self) -> list[str]:
        """Column headers, right to left (the first column is the rightmost)."""

    @abstractmethod
    def row_cells(self, row) -> list[str]:
        """Turn one row into a list of cells, in the same order as columns."""

    @abstractmethod
    def draw_header(self, c: Canvas, data: BaseData) -> float:
        """Draw the header. Returns the y where the table starts."""

    @abstractmethod
    def draw_summary(self, c: Canvas, data: BaseData, y: float) -> None:
        """Draw the summary (top, bottom or side, depending on the type)."""

    @abstractmethod
    def validate(self, data: BaseData) -> list[str]:
        """List of errors. Empty = valid."""

    @abstractmethod
    def generate(self, year: int, month: int, seed: int | None = None) -> BaseData:
        """Generate test data."""

    # ---------- What is shared ----------
    def build_pdf(self, data: BaseData, path: str | Path) -> Path:
        errors = self.validate(data)
        if errors:
            raise ValueError("הדוח לא תקין:\n" + "\n".join(errors))
        self._register_font()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        c = Canvas(str(path), pagesize=self.page_size)
        c.setFont(FONT_NAME, self.font_size)
        y = self.draw_header(c, data)
        y = self._draw_table(c, data, y)
        self.draw_summary(c, data, y)
        c.save()
        return path

    def _draw_table(self, c: Canvas, data: BaseData, y: float) -> float:
        width, _ = self.page_size
        margin = 30
        col_w = (width - 2 * margin) / len(self.columns)
        # Cell i is drawn from the right: x starts at the right edge
        def draw_line(cells, y, bold_box=False):
            for i, text in enumerate(cells):
                right = width - margin - i * col_w
                c.rect(right - col_w, y - self.row_height, col_w, self.row_height)
                c.drawCentredString(right - col_w / 2, y - self.row_height + 5, heb(text))
        draw_line(self.columns, y)
        y -= self.row_height
        for row in data.rows:
            draw_line(self.row_cells(row), y)
            y -= self.row_height
        return y

    @staticmethod
    def _register_font() -> None:
        if FONT_NAME in pdfmetrics.getRegisteredFontNames():
            return
        for p in FONT_CANDIDATES:
            if Path(p).exists():
                pdfmetrics.registerFont(TTFont(FONT_NAME, p))
                return
        raise FileNotFoundError("לא נמצא פונט עם תמיכה בעברית, הוסיפי נתיב ל-FONT_CANDIDATES")