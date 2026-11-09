import numpy as np
import pymupdf


def render_page_gray(pdf_path: str, page_number: int = 0, dpi: int = 300) -> np.ndarray:
    """Render a PDF page to a grayscale image (numpy array)."""
    with pymupdf.open(pdf_path) as doc:
        pix = doc[page_number].get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
        data = np.frombuffer(pix.samples, dtype=np.uint8)
        return data.reshape(pix.height, pix.stride)[:, : pix.width].copy()