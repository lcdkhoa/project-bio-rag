"""Phát hiện banner mở đầu Bài ("Bài N") ở đỉnh trang.

Hai điều kiện PHẢI đồng thời đúng mới coi là banner mở bài:
1. đỉnh trang có một vùng màu đủ lớn (banner in màu của KNTT), và
2. trong dải đó OCR ra được nhãn "Bài N".

Chỉ dựa vào chữ là sai: thân bài trích dẫn "… ở Bài 6 …" rất thường xuyên, và
nhận nhầm sẽ làm spine Bài lệch cả quyển. Đây là nguồn *độc lập* để đối chiếu
với MỤC LỤC — chính nó thắng khi hai bên lệch, vì nó là trang thật.
"""
from __future__ import annotations

import re
from typing import Optional

import cv2
import numpy as np
import pytesseract

from ...config import TESSERACT_CMD

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

TOP_FRAC = 0.22
MIN_BANNER_AREA_FRAC = 0.04
MIN_SATURATION = 45

_BAI_LABEL = re.compile(r"B[àa]i\s+(\d{1,2})\b", re.IGNORECASE)


def _coloured_area_frac(band_bgr: np.ndarray, min_sat: int) -> float:
    hsv = cv2.cvtColor(band_bgr, cv2.COLOR_BGR2HSV)
    coloured = hsv[:, :, 1] >= min_sat
    return float(coloured.mean())


def detect_bai_banner(image_bgr: np.ndarray,
                      top_frac: float = TOP_FRAC,
                      min_area_frac: float = MIN_BANNER_AREA_FRAC,
                      min_sat: int = MIN_SATURATION) -> Optional[int]:
    height = image_bgr.shape[0]
    band = image_bgr[0:int(height * top_frac), :]
    if band.size == 0:
        return None
    if _coloured_area_frac(band, min_sat) < min_area_frac:
        return None

    # Preprocess for better OCR: grayscale + threshold for high contrast
    band_gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
    _, band_thresh = cv2.threshold(band_gray, 200, 255, cv2.THRESH_BINARY)

    text = pytesseract.image_to_string(band_thresh, lang="vie", config="--psm 6")
    match = _BAI_LABEL.search(" ".join(text.split()))
    return int(match.group(1)) if match else None
