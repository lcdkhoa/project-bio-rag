r"""Adapter OCR: đọc candidate số trang trong dải đáy trang.

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

Nguồn PNG (spec §1.6): crop góc ở phân giải gốc chỉ **153×115 px**, nhỏ tới mức
tesseract CẮT MẤT chữ số — `"11" -> "1"` (conf 83), `"110" -> "10"` (conf 45,
rơi dưới MIN_CONF). Phóng crop góc **3×** sửa được cả hai (conf 95 / 62). Nhưng
3× KHÔNG thắng tuyệt đối: `page_165` sách 9 đọc được ở 1× và **không đọc được gì**
ở 3×. Vì mọi biến thể đều cho cùng một offset, HỢP hai lần đọc là superset an
toàn — trang nào một biến thể xác nhận được thì hợp cũng xác nhận được. Đây là
NGOẠI LỆ DUY NHẤT của lệnh cấm upscale (CẤM #2): thân bài phóng to không đổi CER,
chỉ crop góc mới có gì để cứu.

`_DIGITS` không còn là `^\d{1,3}$`: `"110°"` (số trang dính ký hiệu độ của thân
bài) bị luật cũ loại oan. Nay trích dãy chữ số trong token — vẫn giới hạn 1–3
chữ số, vẫn không hạ ngưỡng conf.
"""
from __future__ import annotations

import re

import cv2
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
# Đọc crop góc ở cả hai scale rồi HỢP kết quả (xem docstring): 1× cứu trang mà
# 3× mù, 3× cứu chữ số bị cắt ở 1×.
CORNER_SCALES = (1, 3)

_DIGIT_RUNS = re.compile(r"\d+")


def _digit_value(token: str):
    """Giá trị số trang trong token, hoặc None.

    Chỉ nhận token có ĐÚNG một dãy chữ số (không quá 3 chữ số) — "110°" hợp lệ,
    "2020" (4 chữ số) và "1.2" (hai dãy: nhãn hình, không phải số trang) không.
    """
    runs = _DIGIT_RUNS.findall(token)
    if len(runs) != 1 or not 1 <= len(runs[0]) <= 3:
        return None
    return int(runs[0])


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
        value = _digit_value(token)
        if value is None:
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
        out.append(NumberCandidate(value=value, conf=confidence, side=side))
    return out


def _read_corner(image_bgr: np.ndarray, y_top: float, x_frac: tuple[float, float],
                 side: str, min_conf: float,
                 scale: int = 1) -> list[NumberCandidate]:
    """Đường đọc thứ hai: crop đúng góc trang, `psm 6` + whitelist số.

    `side` cố định theo góc đang đọc (trái/phải) — không suy từ centre, vì
    crop đã hẹp tới mức chỉ còn đúng một góc. `scale` phóng crop lên trước khi
    OCR (chỉ crop góc, không phải cả trang).
    """
    height, width = image_bgr.shape[:2]
    x0, x1 = int(width * x_frac[0]), int(width * x_frac[1])
    crop = image_bgr[int(height * y_top):height, x0:x1]
    if crop.size == 0:
        return []
    if scale != 1:
        crop = cv2.resize(crop, None, fx=scale, fy=scale,
                          interpolation=cv2.INTER_CUBIC)
    data = pytesseract.image_to_data(crop, lang="eng", config=_CORNER_CONFIG,
                                     output_type=pytesseract.Output.DICT)
    out: list[NumberCandidate] = []
    for text, conf in zip(data["text"], data["conf"]):
        value = _digit_value((text or "").strip())
        if value is None:
            continue
        try:
            confidence = float(conf)
        except (TypeError, ValueError):
            continue
        if confidence < min_conf:
            continue
        out.append(NumberCandidate(value=value, conf=confidence, side=side))
    return out


def read_page_number_candidates(image_bgr: np.ndarray,
                                band_top: float = BAND_TOP_FRAC,
                                outer: float = OUTER_FRAC,
                                min_conf: float = MIN_CONF) -> list[NumberCandidate]:
    combined = _read_sparse(image_bgr, band_top, outer, min_conf)
    for scale in CORNER_SCALES:
        combined += _read_corner(image_bgr, CORNER_Y_TOP_FRAC,
                                 CORNER_LEFT_X_FRAC, "L", min_conf, scale)
        combined += _read_corner(image_bgr, CORNER_Y_TOP_FRAC,
                                 CORNER_RIGHT_X_FRAC, "R", min_conf, scale)
    # Khử trùng: hai đường đọc thường thấy CÙNG một con số thật trên trang —
    # giữ candidate có conf cao hơn cho mỗi (value, side) thay vì nhân đôi phiếu.
    best: dict[tuple[int, str], NumberCandidate] = {}
    for cand in combined:
        key = (cand.value, cand.side)
        if key not in best or cand.conf > best[key].conf:
            best[key] = cand
    return list(best.values())
