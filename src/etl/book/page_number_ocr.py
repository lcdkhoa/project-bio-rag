"""Adapter OCR: đọc candidate số trang trong dải đáy trang.

Chỉ làm một việc: biến pixel thành `NumberCandidate`. Mọi phán xét (parity,
offset, confirmed/inferred) thuộc `page_map.py`.

Vì sao `psm 11` (sparse text) chứ không `psm 6`: dải đáy thường CHỈ có một con
số lẻ loi giữa nền trắng. Đo trên corpus thật, mở rộng dải crop cho "chắc" lại
làm kết quả TỆ HƠN vì lọt chữ thân bài vào — nên giữ dải hẹp + lọc theo hình
học của token thay vì nới crop (spec §1.1).
"""
from __future__ import annotations

import re

import numpy as np
import pytesseract

from .page_map import NumberCandidate
from ...config import TESSERACT_CMD

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

BAND_TOP_FRAC = 0.88
OUTER_FRAC = 0.22
MIN_CONF = 50.0

_DIGITS = re.compile(r"^\d{1,3}$")


def read_page_number_candidates(image_bgr: np.ndarray,
                                band_top: float = BAND_TOP_FRAC,
                                outer: float = OUTER_FRAC,
                                min_conf: float = MIN_CONF) -> list[NumberCandidate]:
    height, width = image_bgr.shape[:2]
    band = image_bgr[int(height * band_top):height, 0:width]
    if band.size == 0:
        return []
    data = pytesseract.image_to_data(band, lang="eng", config="--psm 11",
                                     output_type=pytesseract.Output.DICT)
    out: list[NumberCandidate] = []
    for text, conf, left, box_w in zip(data["text"], data["conf"],
                                       data["left"], data["width"]):
        token = (text or "").strip()
        if not _DIGITS.match(token):
            continue
        try:
            confidence = float(conf)
        except (TypeError, ValueError):
            continue
        if confidence < min_conf:
            continue
        centre = (left + box_w / 2.0) / width
        if centre <= outer:
            side = "L"
        elif centre >= 1.0 - outer:
            side = "R"
        else:
            continue
        out.append(NumberCandidate(value=int(token), conf=confidence, side=side))
    return out
