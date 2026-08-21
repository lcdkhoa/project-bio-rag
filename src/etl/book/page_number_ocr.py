"""Adapter OCR: đọc candidate số trang trong dải đáy trang.

Chỉ làm một việc: biến pixel thành `NumberCandidate`. Mọi phán xét (parity,
offset, confirmed/inferred) thuộc `page_map.py`.

Vì sao `psm 11` (sparse text) chứ không `psm 6`: dải đáy thường CHỈ có một con
số lẻ loi giữa nền trắng. Đo trên corpus thật, mở rộng dải crop cho "chắc" lại
làm kết quả TỆ HƠN vì lọt chữ thân bài vào — nên giữ dải hẹp + lọc theo hình
học của token thay vì nới crop (spec §1.1).

Task 7 (controller ruling 11): đo lại trên 4 quyển thật cho thấy chiến lược
`psm 11` sparse đơn lẻ trượt ngưỡng G1 (95%) ở cả 4 quyển (81.9%–90.9%), dù số
trang VẪN được in — đây là lỗi adapter, không phải thiếu dữ liệu. Đo thêm một
chiến lược thứ hai — crop đúng góc trang (hẹp hơn dải + lề ngoài hiện tại) với
`psm 6` (một khối văn bản) và whitelist chỉ chữ số — cho 94.5%–98.0%. Hai chiến
lược có điểm mù khác nhau (sparse: token lọt giữa dải; corner: cắt hụt số nằm
lệch góc) nên `read_page_number_candidates` giờ trả về HỢP của cả hai, khử
trùng theo (value, side) — không hạ MIN_CONF, không nới `outer`, parity vẫn
khoá theo giá trị đọc được như cũ.
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

# Góc trang dùng cho lần đọc thứ hai (psm 6 + whitelist số). Hẹp hơn dải sparse
# rất nhiều — chỉ phần đáy-góc chắc chắn không dính chữ thân bài — nên side suy
# thẳng từ góc nào sinh ra token, không cần tính centre như đường sparse.
CORNER_Y_TOP_FRAC = 0.925
CORNER_LEFT_X_FRAC = (0.0, 0.14)
CORNER_RIGHT_X_FRAC = (0.86, 1.0)
_CORNER_CONFIG = "--psm 6 -c tessedit_char_whitelist=0123456789"

_DIGITS = re.compile(r"^\d{1,3}$")


def _read_sparse(image_bgr: np.ndarray, band_top: float, outer: float,
                 min_conf: float) -> list[NumberCandidate]:
    """Đường đọc gốc: dải đáy rộng, `psm 11`, lọc theo centre của token."""
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


def _read_corner(image_bgr: np.ndarray, y_top: float, x_frac: tuple[float, float],
                 side: str, min_conf: float) -> list[NumberCandidate]:
    """Đường đọc thứ hai: crop đúng góc trang, `psm 6` + whitelist số.

    `side` cố định theo góc đang đọc (trái/phải) — không suy từ centre, vì
    crop đã hẹp tới mức chỉ còn đúng một góc.
    """
    height, width = image_bgr.shape[:2]
    x0, x1 = int(width * x_frac[0]), int(width * x_frac[1])
    crop = image_bgr[int(height * y_top):height, x0:x1]
    if crop.size == 0:
        return []
    data = pytesseract.image_to_data(crop, lang="eng", config=_CORNER_CONFIG,
                                     output_type=pytesseract.Output.DICT)
    out: list[NumberCandidate] = []
    for text, conf in zip(data["text"], data["conf"]):
        token = (text or "").strip()
        if not _DIGITS.match(token):
            continue
        try:
            confidence = float(conf)
        except (TypeError, ValueError):
            continue
        if confidence < min_conf:
            continue
        out.append(NumberCandidate(value=int(token), conf=confidence, side=side))
    return out


def read_page_number_candidates(image_bgr: np.ndarray,
                                band_top: float = BAND_TOP_FRAC,
                                outer: float = OUTER_FRAC,
                                min_conf: float = MIN_CONF) -> list[NumberCandidate]:
    combined = (
        _read_sparse(image_bgr, band_top, outer, min_conf)
        + _read_corner(image_bgr, CORNER_Y_TOP_FRAC, CORNER_LEFT_X_FRAC, "L", min_conf)
        + _read_corner(image_bgr, CORNER_Y_TOP_FRAC, CORNER_RIGHT_X_FRAC, "R", min_conf)
    )
    # Khử trùng: hai đường đọc thường thấy CÙNG một con số thật trên trang —
    # giữ candidate có conf cao hơn cho mỗi (value, side) thay vì nhân đôi phiếu.
    best: dict[tuple[int, str], NumberCandidate] = {}
    for cand in combined:
        key = (cand.value, cand.side)
        if key not in best or cand.conf > best[key].conf:
            best[key] = cand
    return list(best.values())
