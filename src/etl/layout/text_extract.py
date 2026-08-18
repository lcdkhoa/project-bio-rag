"""OCR each layout region separately, in reading order."""
import numpy as np
import pytesseract
from .regions import Region, RegionType, TextUnit
from ..cleaner import clean_vietnamese_text
from ..diacritic import fix_diacritics
from ...config import TESSERACT_CMD, DIACRITIC_FIX_ENABLED

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

def _ocr(img: np.ndarray) -> str:
    raw = pytesseract.image_to_string(img, lang="vie")
    cleaned = clean_vietnamese_text(raw)
    return fix_diacritics(cleaned) if DIACRITIC_FIX_ENABLED else cleaned

def _mask_out(img: np.ndarray, boxes) -> np.ndarray:
    out = img.copy()
    for (x0, y0, x1, y1) in boxes:
        out[y0:y1, x0:x1] = 255
    return out

def extract_text_units(image: np.ndarray, regions: list[Region], variant: str) -> list[TextUnit]:
    units: list[TextUnit] = []
    for r in sorted(regions, key=lambda z: z.reading_order):
        if r.type in (RegionType.FIGURE, RegionType.PAGE_ARTIFACT):
            continue
        x0, y0, x1, y1 = r.bbox
        crop = image[y0:y1, x0:x1]
        if r.type == RegionType.BODY:
            crop = _mask_out(crop, r.meta.get("excludes", []))
        text = _ocr(crop)
        if text and len(text) > 5:
            units.append(TextUnit(r.type, text, r.reading_order, r.bbox))
    return units
