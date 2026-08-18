"""Detect the page number printed on the page (bottom corners)."""
import re
import numpy as np
import pytesseract
from ...config import TESSERACT_CMD

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
_INT = re.compile(r"^\d{1,3}$")

def _crop(img, frac_box):
    h, w = img.shape[:2]
    x0, y0, x1, y1 = frac_box
    return img[int(h*y0):int(h*y1), int(w*x0):int(w*x1)]

def detect_printed_page_number(image: np.ndarray, variant: str, pdf_index: int) -> int:
    # bottom-left and bottom-right corners
    for box in [(0.0, 0.85, 0.25, 1.0), (0.75, 0.85, 1.0, 1.0)]:
        crop = _crop(image, box)
        txt = pytesseract.image_to_string(
            crop, lang="vie", config="--psm 7 -c tessedit_char_whitelist=0123456789")
        for tok in txt.split():
            if _INT.match(tok.strip()):
                return int(tok.strip())
    return pdf_index
