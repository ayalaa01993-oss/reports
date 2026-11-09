from pathlib import Path

import cv2
import numpy as np
import pytesseract

import config

if Path(config.TESSERACT_CMD).exists():
    pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD

_WHITELIST = "0123456789:./"


def is_blank(cell: np.ndarray) -> bool:
    return (cell < 140).mean() < config.MIN_INK_RATIO


def read_cell(cell: np.ndarray) -> str:
    """OCR a single digit-only cell. Returns an empty string if the cell is blank."""
    if cell.size == 0 or is_blank(cell):
        return ""
    cell = cv2.copyMakeBorder(cell, 15, 15, 15, 15, cv2.BORDER_CONSTANT, value=255)
    cell = cv2.resize(cell, None, fx=config.CELL_SCALE, fy=config.CELL_SCALE,
                      interpolation=cv2.INTER_AREA)
    cfg = f"--psm 7 -c tessedit_char_whitelist={_WHITELIST}"
    return pytesseract.image_to_string(cell, lang="eng", config=cfg).strip()