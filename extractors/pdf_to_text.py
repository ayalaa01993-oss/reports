import io
from pathlib import Path

import cv2
import numpy as np
import pymupdf as fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageOps

import config

if Path(config.TESSERACT_CMD).exists():
    pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD


def _remove_lines(gray: np.ndarray) -> np.ndarray:
    """Whiten the table lines (horizontal and vertical) in a grayscale image."""
    bw = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 31, 15
    )
    h, w = bw.shape

    horiz_k = cv2.getStructuringElement(cv2.MORPH_RECT, (max(w // 30, 20), 1))
    vert_k = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(h // 30, 20)))
    horiz = cv2.morphologyEx(bw, cv2.MORPH_OPEN, horiz_k)
    vert = cv2.morphologyEx(bw, cv2.MORPH_OPEN, vert_k)

    lines = cv2.bitwise_or(horiz, vert)
    lines = cv2.dilate(lines, np.ones((3, 3), np.uint8), iterations=1)

    cleaned = gray.copy()
    cleaned[lines > 0] = 255
    return cleaned


def _preprocess(img: Image.Image) -> Image.Image:
    """Grayscale, contrast and table-line removal to improve OCR."""
    img = ImageOps.grayscale(img)
    img = ImageOps.autocontrast(img)
    arr = _remove_lines(np.array(img))
    return Image.fromarray(arr)


def pdf_to_text(
    pdf_path: str,
    lang: str = "heb",
    dpi: int = 400,
    psm: int = 6,
    debug: bool = False,
) -> str:
    """Extract text from a PDF: embedded text first, OCR as a fallback."""
    pages_text = []
    config_str = f"--psm {psm} -c preserve_interword_spaces=1"
    with fitz.open(pdf_path) as doc:
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text().strip()
            if text:
                pages_text.append(text)
                continue
            pix = page.get_pixmap(dpi=dpi)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            img = _preprocess(img)

            if debug:
                config.DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                img.save(config.DEBUG_DIR / f"{Path(pdf_path).stem}_p{page_num}.png")

            pages_text.append(
                pytesseract.image_to_string(img, lang=lang, config=config_str)
            )
    return "\n\n".join(pages_text)


def pdf_to_text_file(
    pdf_path: str,
    lang: str = "heb",
    dpi: int = 400,
    psm: int = 6,
    debug: bool = False,
) -> Path:
    """Convert a PDF to text and save it in TEXT_DIR under the original file name."""
    text = pdf_to_text(pdf_path, lang=lang, dpi=dpi, psm=psm, debug=debug)

    config.TEXT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = config.TEXT_DIR / f"{Path(pdf_path).stem}.txt"
    output_path.write_text(text, encoding="utf-8")
    return output_path