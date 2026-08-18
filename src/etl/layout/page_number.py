"""Detect the page number printed on the page (bottom corners).

The crop geometry below is tuned on REAL scanned pages (validated across
CTST/KNTT/CD): a tight bottom-corner band isolates the page number from body
text and figure labels that a wider crop would wrongly read. PSM 6 (uniform
block) reads a lone number beside a decorative graphic where PSM 7 (single
line) silently fails. When nothing is read, the caller's `pdf_index` fallback
is returned. Tests pass their own `corners`/`psm` to exercise the read logic
independently of the production geometry.
"""
import re
import numpy as np
import pytesseract
from ...config import TESSERACT_CMD

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
_INT = re.compile(r"^\d{1,3}$")

# Real-page-tuned bottom-left / bottom-right corner crops (fractions of h, w).
_DEFAULT_CORNERS = [(0.0, 0.93, 0.12, 1.0), (0.88, 0.93, 1.0, 1.0)]
_DEFAULT_PSM = 6


def _crop(img, frac_box):
    h, w = img.shape[:2]
    x0, y0, x1, y1 = frac_box
    return img[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]


def detect_printed_page_number(image: np.ndarray, variant: str, pdf_index: int,
                               corners=None, psm: int = _DEFAULT_PSM) -> int:
    for box in (corners or _DEFAULT_CORNERS):
        crop = _crop(image, box)
        txt = pytesseract.image_to_string(
            crop, lang="vie", config=f"--psm {psm} -c tessedit_char_whitelist=0123456789")
        for tok in txt.split():
            if _INT.match(tok.strip()):
                return int(tok.strip())
    return pdf_index
