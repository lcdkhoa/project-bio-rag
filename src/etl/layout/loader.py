"""Layout-aware text loader: PDF page -> clean chunk Documents."""
import logging
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np

from .preprocess import preprocess_page
from .segmenter import segment_page
from .text_extract import extract_text_units
from .chunker import chunk_units
from .page_number import detect_printed_page_number
from ..image_processor import get_pdf_variant
from ...config import RENDER_DPI

logger = logging.getLogger(__name__)


def _render_page(pdf_file: str, index: int, dpi: int) -> np.ndarray:
    """Render one PDF page to an HxWx3 BGR uint8 array.

    fitz.Pixmap.n varies with the page's color mode: 1 (grayscale), 3 (RGB),
    or 4 (RGBA). Each is normalized to 3-channel BGR before returning.
    """
    doc = fitz.open(pdf_file)
    try:
        pix = doc[index].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))
        arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 1:
            # grayscale -> replicate to 3 channels (order irrelevant, R=G=B)
            arr = np.repeat(arr, 3, axis=2)
        else:
            # RGB or RGBA -> drop alpha (if any), then RGB -> BGR
            arr = arr[:, :, :3][:, :, ::-1]
        return arr.copy()
    finally:
        doc.close()


class LayoutOCRLoader:
    """Orchestrates the M1 layout-aware data path for one PDF, page by page."""

    def load_page(self, pdf_file: str, index: int):
        variant = get_pdf_variant(Path(pdf_file).name)
        img = _render_page(pdf_file, index, RENDER_DPI)
        img = preprocess_page(img, variant)
        regions = segment_page(img, variant)
        page_no = detect_printed_page_number(img, variant, index + 1)
        units = extract_text_units(img, regions, variant)
        return chunk_units(units, source=Path(pdf_file).name, page=page_no, variant=variant)

    def load_pdf(self, pdf_file: str):
        doc = fitz.open(pdf_file)
        n = len(doc)
        doc.close()
        out = []
        for i in range(n):
            try:
                out.extend(self.load_page(pdf_file, i))
            except Exception as e:
                logger.error(f"[{Path(pdf_file).name}] page {i}: {e}")
        return out
