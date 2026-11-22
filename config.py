"""Central settings: paths and constants. Change values here, not in other files."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# ---- Folders ----
DATA_DIR = PROJECT_ROOT / "data"
PDF_DIR = DATA_DIR / "pdf_reports"  # source reports
TEXT_DIR = DATA_DIR / "text_reports"  # text produced by OCR
DEBUG_DIR = DATA_DIR / "debug_images"  # intermediate images for debugging
OUTPUT_DIR = DATA_DIR / "output"  # generated reports

# ---- Tesseract ----
TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "tesseract")

# ---- Report fonts ----
FONT_NAME = "ReportFont"
FONT_CANDIDATES = []
if os.environ.get("REPORT_FONT_PATH"):
    FONT_CANDIDATES.append(Path(os.environ["REPORT_FONT_PATH"]))
if os.environ.get("WINDIR"):
    FONT_CANDIDATES.append(Path(os.environ["WINDIR"]) / "Fonts" / "arial.ttf")
FONT_CANDIDATES.append(Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))

# ---- type1 extraction ----
OCR_DPI = 300
CELL_SCALE = 0.6  # shrink each cell before OCR; found to improve accuracy
CELL_H_PAD = 25  # pixels: stay away from vertical grid lines
MIN_INK_RATIO = 0.004  # below this ink ratio a cell is considered empty

# Column ranges as a fraction of page width: total, exit, entry
TYPE1_COLUMNS = {
    "total": (0.282, 0.373),
    "exit": (0.377, 0.470),
    "entry": (0.472, 0.558),
}