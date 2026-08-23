"""M0 — đo ĐẶC TRƯNG LAYOUT của từng quyển, không mượn tham số của quyển khác.

Vì sao file này tồn tại: corpus nay là 12 quyển / 3 nhà xuất bản, và mọi hằng số
layout đang có trong repo (`page_number_ocr.BAND_TOP_FRAC = 0.88`, các góc
`CORNER_*`, `TOC_PAGE_NUMBERS`, bảng màu hộp) đều **chỉ được đo trên KNTT ở
1094×1536**. CD/CTST lớn gấp ~3,5 lần diện tích và trình bày khác. Dùng lại số cũ
cho quyển mới là đoán, không phải đo (nguyên tắc 2 và 3).

## Thiết kế: đo VỊ TRÍ, đừng khai báo vị trí

Cách sai (và là cách bản KNTT cũ làm): tự chọn trước một dải "0,88 → 1,00 chiều
cao" rồi OCR trong đó. Nếu quyển khác in số trang ở lề bên thì dải đó trả về rỗng
và ta không biết vì sao — không có gì phân biệt "quyển này không in số" với "ta
nhìn sai chỗ".

Cách ở đây: OCR **cả bốn dải biên** (trên/dưới/trái/phải, mỗi dải 12%), ghi lại
MỌI token chữ số kèm toạ độ tâm đã chuẩn hoá; rồi mới **suy ngược** ra
(1) độ lệch giữa số in và số trong tên file, (2) vùng chứa số trang — bằng chính
toạ độ của những token đã khớp. Vùng là **kết quả đo**, không phải giả định đầu vào.

## Ba cái bẫy đã tính trước (nguyên tắc 4)

1. **Trùng ngẫu nhiên.** Trang 12 có thể chứa chữ "Bài 12" ở tiêu đề → khớp giả.
   Nên: (a) báo cáo `margin` = số phiếu của offset thắng trừ offset á quân, (b) báo
   cáo độ TÚM TỤM của toạ độ các token khớp (`spread_x/spread_y` theo IQR). Số
   trang thật nằm gần như cùng một chỗ mọi trang; "Bài 12" thì không.
2. **Whitelist chữ số bóp méo chữ cái.** `O`→`0`, `l`→`1`. Nên lọc theo `conf` và
   theo miền giá trị hợp lệ (1..n_pages+5), và không bao giờ tin một trang đơn lẻ.
3. **Chẵn/lẻ so le.** Nhiều sách in số ở lề ngoài nên trang chẵn một bên, trang lẻ
   một bên. Nếu ép về một vùng duy nhất sẽ mất một nửa. Nên vùng được đo **tách
   theo parity** và chỉ gộp lại khi hai bên thật sự chồng nhau.

Không có bước "sửa": quyển nào không đạt ngưỡng thì bị **gắn cờ**, không được đoán
offset (nguyên tắc 5 + CẤM #4).

## Năm trường, mỗi trường một phép đo riêng (M0)

| trường | ở đâu | đo bằng gì |
|---|---|---|
| `page_number` | file này | OCR bốn dải biên rồi suy offset (hai giai đoạn) |
| `toc_pages` / `toc_geometry` | `fp_toc.py` | ba bằng chứng độc lập (§2.1–2.2) |
| `box_palette` | `fp_palette.py` | histogram hue của vùng nền phẳng >= 2% |
| `pill_pattern` | `fp_figure.py` | hai kênh: pill đảo màu vs OCR thường |

Mỗi stage ghi vào CÙNG một file `database/fingerprints/{book}.json` và **chỉ ghi
đè phần của chính nó khi đo thành công** — một stage hỏng không được xoá số đo
tốt của stage khác (CẤM #8, đã cắn thật một lần: xem §0.4.3 của prompt M0).

Dùng:
    python -m src.etl.book.fingerprint --all
    python -m src.etl.book.fingerprint --all --stages toc,palette,pill
    python -m src.etl.book.fingerprint --book SGK_KHTN_6_CD --sample 40 --verbose
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import statistics
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Iterable, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Bốn dải biên. 12% là chọn RỘNG có chủ đích: thà OCR thừa rồi lọc bằng toạ độ,
# còn hơn cắt hụt và kết luận "quyển này không in số trang".
EDGE_FRAC = 0.12
STRIPS = ("top", "bottom", "left", "right")

MIN_CONF = 40.0
OFFSET_RANGE = range(-5, 6)
# Ngưỡng nghiệm thu: >=80% trang mẫu khớp cùng một offset, và offset thắng phải
# hơn á quân ít nhất 5 phiếu. Hai điều kiện chặn hai kiểu sai khác nhau: tỉ lệ
# thấp = nhìn sai chỗ; margin thấp = có thể đang khớp nhiễu.
MIN_HIT_RATE = 0.80
MIN_MARGIN = 5

_DIGITS = re.compile(r"^\d+$")

# Lấy mẫu cho các stage layout. BỎ phần đầu sách: bìa / lời nói đầu / MỤC LỤC
# không có hộp màu thân bài lẫn nhãn hình, nên đưa chúng vào mẫu chỉ làm loãng
# phép đo (và một mẫu 0 hộp ở trang bìa không nói gì về palette của quyển).
SKIP_FRONT_PAGES = 10
PALETTE_SAMPLE = 30
PILL_SAMPLE = 30

STAGES = ("page_number", "toc", "palette", "pill")


@dataclass
class DigitToken:
    """Một token chữ số đã đọc được, toạ độ tâm CHUẨN HOÁ theo cỡ trang."""
    value: int
    conf: float
    cx: float
    cy: float
    strip: str


@dataclass
class PageNumberFingerprint:
    offset: Optional[int]
    votes: int
    total_pages_probed: int
    hit_rate: float
    margin_over_runner_up: int
    runner_up_offset: Optional[int]
    scale_used: int
    zone_by_parity: dict = field(default_factory=dict)
    spread: dict = field(default_factory=dict)
    zone_read: dict = field(default_factory=dict)
    flags: list = field(default_factory=list)


# --------------------------------------------------------------- OCR một trang

def _tesseract():
    import pytesseract
    from src.config import TESSERACT_CMD
    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    return pytesseract


def _strip_rects(h: int, w: int) -> dict:
    e_h, e_w = int(h * EDGE_FRAC), int(w * EDGE_FRAC)
    return {
        "top":    (0, 0, w, e_h),
        "bottom": (0, h - e_h, w, e_h),
        "left":   (0, 0, e_w, h),
        "right":  (w - e_w, 0, e_w, h),
    }


def read_digit_tokens(image_bgr: np.ndarray, scale: int = 1,
                      max_value: int = 10_000) -> list:
    """Mọi token chữ số ở bốn dải biên, toạ độ tâm chuẩn hoá về [0,1]×[0,1].

    `psm 11` (sparse) vì dải biên thường chỉ có vài ký tự rời — `psm 6` giả định
    một khối văn bản và bỏ sót chúng (đo trên KNTT, xem `page_number_ocr.py`).
    """
    pt = _tesseract()
    h, w = image_bgr.shape[:2]
    out: list = []
    seen: set = set()
    for name, (x0, y0, cw, ch) in _strip_rects(h, w).items():
        crop = image_bgr[y0:y0 + ch, x0:x0 + cw]
        if crop.size == 0:
            continue
        if scale != 1:
            crop = cv2.resize(crop, None, fx=scale, fy=scale,
                              interpolation=cv2.INTER_CUBIC)
        data = pt.image_to_data(
            crop, output_type=pt.Output.DICT,
            config="--psm 11 -c tessedit_char_whitelist=0123456789")
        for txt, conf, left, top, tw, th in zip(
                data["text"], data["conf"], data["left"], data["top"],
                data["width"], data["height"]):
            txt = (txt or "").strip()
            if not _DIGITS.match(txt):
                continue
            try:
                conf = float(conf)
            except (TypeError, ValueError):
                continue
            if conf < MIN_CONF:
                continue
            value = int(txt)
            if value <= 0 or value > max_value:
                continue
            # Toạ độ tâm trong hệ của TRANG, không phải của crop.
            cx = (x0 + (left + tw / 2) / scale) / w
            cy = (y0 + (top + th / 2) / scale) / h
            key = (value, round(cx, 3), round(cy, 3))
            if key in seen:      # dải trái/phải chồng dải trên/dưới ở 4 góc
                continue
            seen.add(key)
            out.append(DigitToken(value, conf, cx, cy, name))
    return out


# ------------------------------------------------- suy offset (thuần, test được)

def best_offset(observations: Iterable[tuple]) -> tuple:
    """`observations` = [(filenum, [giá trị số đọc được]), ...].

    Trả `(offset, votes, runner_up_offset, runner_up_votes)`. Mỗi trang bỏ TỐI ĐA
    một phiếu cho mỗi offset — nếu không, một trang nhiều chữ số sẽ tự bỏ phiếu
    nhiều lần và một trang ồn ào có thể lật kết quả của cả quyển.
    """
    tally = {off: 0 for off in OFFSET_RANGE}
    for filenum, values in observations:
        vals = set(values)
        for off in OFFSET_RANGE:
            if filenum + off in vals:
                tally[off] += 1
    ranked = sorted(tally.items(), key=lambda kv: (-kv[1], abs(kv[0])))
    (off1, v1), (off2, v2) = ranked[0], ranked[1]
    if v1 == 0:
        return None, 0, None, 0
    return off1, v1, off2, v2


def _iqr(values: list) -> float:
    if len(values) < 4:
        return 0.0
    q = statistics.quantiles(values, n=4)
    return float(q[2] - q[0])


def zone_from_tokens(tokens: list) -> dict:
    """Vùng chứa số trang, suy từ chính toạ độ các token đã khớp."""
    if not tokens:
        return {}
    xs = [t.cx for t in tokens]
    ys = [t.cy for t in tokens]
    return {
        "n": len(tokens),
        "x_min": round(min(xs), 4), "x_max": round(max(xs), 4),
        "y_min": round(min(ys), 4), "y_max": round(max(ys), 4),
        "x_median": round(statistics.median(xs), 4),
        "y_median": round(statistics.median(ys), 4),
        "x_iqr": round(_iqr(xs), 4), "y_iqr": round(_iqr(ys), 4),
        "strips": sorted({t.strip for t in tokens}),
    }


# ---------------------------------------------------------------- đo một quyển

def sample_pages(page_numbers: list, k: int) -> list:
    """Mẫu rải đều cả quyển (không lấy k trang đầu — đầu sách không đại diện)."""
    if len(page_numbers) <= k:
        return list(page_numbers)
    step = len(page_numbers) / k
    return [page_numbers[int(i * step)] for i in range(k)]


def probe_page_numbers(source, sample: int = 40, verbose: bool = False,
                       refine: bool = True) -> PageNumberFingerprint:
    pages = sample_pages(list(source.page_numbers()), sample)
    n_all = len(source.page_numbers())
    max_value = n_all + 5

    result = None
    for scale in (1, 2):
        obs, per_page = [], {}
        t0 = time.time()
        for pn in pages:
            img = source.load(pn)
            toks = read_digit_tokens(img, scale=scale, max_value=max_value)
            per_page[pn] = toks
            obs.append((pn, [t.value for t in toks]))
        off, votes, off2, votes2 = best_offset(obs)
        hit = votes / len(pages) if pages else 0.0
        if verbose:
            print(f"    scale={scale}x  offset={off} votes={votes}/{len(pages)} "
                  f"({hit:.0%})  a_quan={off2}:{votes2}  "
                  f"{time.time() - t0:.0f}s")
        result = (scale, off, votes, off2, votes2, hit, per_page, pages)
        if off is not None and hit >= MIN_HIT_RATE:
            break

    scale, off, votes, off2, votes2, hit, per_page, pages = result
    fp = PageNumberFingerprint(
        offset=off, votes=votes, total_pages_probed=len(pages),
        hit_rate=round(hit, 4),
        margin_over_runner_up=votes - votes2,
        runner_up_offset=off2, scale_used=scale)

    if off is None:
        fp.flags.append("khong_doc_duoc_so_trang_nao")
        return fp

    matched_even, matched_odd = [], []
    for pn, toks in per_page.items():
        want = pn + off
        hits = [t for t in toks if t.value == want]
        if not hits:
            continue
        best = max(hits, key=lambda t: t.conf)
        (matched_even if want % 2 == 0 else matched_odd).append(best)

    fp.zone_by_parity = {
        "even": zone_from_tokens(matched_even),
        "odd": zone_from_tokens(matched_odd),
    }
    allm = matched_even + matched_odd
    fp.spread = {"x_iqr": zone_from_tokens(allm).get("x_iqr", 0.0),
                 "y_iqr": zone_from_tokens(allm).get("y_iqr", 0.0)}

    if hit < MIN_HIT_RATE:
        fp.flags.append(f"ti_le_khop_thap_{hit:.0%}")
    if fp.margin_over_runner_up < MIN_MARGIN:
        fp.flags.append(f"margin_thap_{fp.margin_over_runner_up}")
    # y_iqr lớn nghĩa là các token "khớp" nằm rải khắp trang -> nhiều khả năng
    # đang khớp nhiễu chứ không phải một vị trí số trang cố định.
    if fp.spread.get("y_iqr", 0) > 0.10 and "bottom" not in (
            fp.zone_by_parity.get("even", {}).get("strips", [])
            + fp.zone_by_parity.get("odd", {}).get("strips", [])):
        fp.flags.append("vi_tri_khong_tum_tum")

    if refine:
        fp = refine_with_zone(source, fp, pages, verbose=verbose)
    return fp


# ------------------------------------- giai doan B: doc ky trong vung da do

# Vùng đọc kỹ, nới từ tâm đã đo. Nới RỘNG có chủ đích: lỗi "15" đọc thành "1" của
# CD lớp 6 (và "11"->"1" của KNTT trước đây) đều do crop cắt cụt chữ số đầu.
ZONE_HALF_W_MIN = 0.060
ZONE_HALF_H_MIN = 0.022
ZONE_IQR_MULT = 3.0
# Không psm nào thắng mọi trang (đo trên KNTT: 56 chỉ đọc ở psm 6, 169 ở psm 8/13,
# 166 ở psm 7). Nên hợp nhất ứng viên thay vì chọn một psm.
ZONE_PSMS = (7, 8, 13, 6)
# (scale, phép nội suy) — ĐO trên 3 trang trượt + 4 trang đối chứng của CD:
# cubic 2/3/4 sửa 0/3, **lanczos 6/8 sửa 2/3** và giữ 4/4 đối chứng; nearest kém
# hơn cả hai. Hợp nhất cả hai nhóm nên chỉ THÊM ứng viên, không bao giờ mất.
# Đây là ngoại lệ upscale đã được phép (crop số trang), không phải thân bài.
ZONE_RESIZES = ((2, cv2.INTER_CUBIC), (3, cv2.INTER_CUBIC), (4, cv2.INTER_CUBIC),
                (6, cv2.INTER_LANCZOS4), (8, cv2.INTER_LANCZOS4))
# Một số trang không thể rộng quá ngần này; rộng hơn nghĩa là cụm đã dính chữ
# chân trang (đo: 6_CD tr.171/175 ra cụm 355 px thay vì 33 px).
MAX_NUM_W_FRAC = 0.05
# Ngưỡng mực + các khoảng cách, ĐỀU theo tỉ lệ chiều rộng trang: một hằng số px
# hợp với CD 2480 px sẽ gộp nhầm mọi thứ trên KNTT 1094 px.
INK_MAX_GRAY = 128
GAP_FRAC = 0.007
MIN_RUN_FRAC = 0.003
PAD_FRAC = 0.004
OUTER_GROUPS = 2


def zone_box(zone: dict):
    """(x0, y0, x1, y1) theo phân số, từ tâm + độ tản đã đo."""
    if not zone or zone.get("n", 0) == 0:
        return None
    hw = max(ZONE_HALF_W_MIN, zone.get("x_iqr", 0.0) * ZONE_IQR_MULT)
    hh = max(ZONE_HALF_H_MIN, zone.get("y_iqr", 0.0) * ZONE_IQR_MULT)
    x, y = zone["x_median"], zone["y_median"]
    return (max(0.0, x - hw), max(0.0, y - hh),
            min(1.0, x + hw), min(1.0, y + hh))


def _ink_runs(band_bgr, gap_px: int, min_w: int) -> list:
    """Các cụm mực theo cột trong dải, đã gộp khoảng trắng nhỏ hơn `gap_px`."""
    g = cv2.cvtColor(band_bgr, cv2.COLOR_BGR2GRAY)
    on = (g < INK_MAX_GRAY).sum(axis=0) > 0
    runs, s0 = [], None
    for i, v in enumerate(on):
        if v and s0 is None:
            s0 = i
        elif not v and s0 is not None:
            runs.append((s0, i))
            s0 = None
    if s0 is not None:
        runs.append((s0, len(on)))
    merged = []
    for a, b in runs:
        if merged and a - merged[-1][1] < gap_px:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return [(a, b) for a, b in merged if b - a >= min_w]


def read_band_outer_groups(image_bgr, y0f: float, y1f: float, side: str,
                           n_groups: int = OUTER_GROUPS,
                           max_value: int = 10_000) -> set:
    """Đọc MÙ `n_groups` cụm mực ngoài cùng của một dải ngang.

    Vì sao phải tìm cụm bằng CV trước rồi mới OCR, thay vì OCR nguyên một ô:
    **đã đo** trên `SGK_KHTN_6_CD`. Ô cố định quanh vị trí số trang cũng nuốt luôn
    chữ chân trang "KHOA HỌC TỰ NHIÊN 6" bên cạnh; với whitelist chữ số, Tesseract
    trả về **`6`** (số của quyển) cho trang 75 và `5,6,7` cho trang 15 — tức đọc
    sai chứ không phải đọc trượt. Cắt riêng cụm ngoài cùng rồi OCR: 6/6 trang thử
    đọc đúng, gồm cả hai trang vừa sai. Cùng khuôn mẫu với `book/toc.py` (dựng
    hình học bằng CV trước, OCR từng ô sau).

    Lấy 2 cụm ngoài cùng chứ không phải 1: có sách in số ở phía trong chữ chân
    trang. Cụm thừa chỉ thêm một ứng viên hằng số (ví dụ "6"), mà một giá trị hằng
    không thể thắng phiếu offset nào — nó chỉ khớp đúng một trang.

    Hàm KHÔNG nhận giá trị kỳ vọng: nó chỉ được nói "tôi thấy gì".
    """
    pt = _tesseract()
    h, w = image_bgr.shape[:2]
    band = image_bgr[int(y0f * h):int(y1f * h), :]
    if band.size == 0:
        return set()
    gap_px = max(8, round(w * GAP_FRAC))
    min_w = max(4, round(w * MIN_RUN_FRAC))
    pad = max(4, round(w * PAD_FRAC))
    runs = _ink_runs(band, gap_px, min_w)
    if not runs:
        return set()
    picked = runs[-n_groups:] if side == "right" else runs[:n_groups]
    # Cụm rộng bất thường = đã nuốt chữ chân trang ("KHOA HỌC TỰ NHIÊN 6" dính
    # vào ô số vì khe hở nhỏ hơn `gap_px`). Tách lại bằng khe nhỏ hơn rồi lấy
    # cụm ngoài cùng. Đo: 6_CD tr.171/175 từ TRƯỢT thành ĐỌC ĐÚNG, hai trang đối
    # chứng không đổi.
    resplit = []
    for a, b in picked:
        if b - a > w * MAX_NUM_W_FRAC:
            sub = _ink_runs(band[:, a:b], max(2, gap_px // 4), min_w)
            if sub:
                sa, sb = sub[-1] if side == "right" else sub[0]
                resplit.append((a + sa, a + sb))
                continue
        resplit.append((a, b))
    picked = resplit

    found = set()
    gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
    for a, b in picked:
        # Cắt theo BBOX MỰC hai chiều, không phải cả chiều cao dải. Đo được trên
        # `SGK_KHTN_7_CD`: dải cao 141 px cho chữ số cao ~45 px, phần còn lại là
        # nền ô màu, và psm 7/8 đọc "26" ra "2" / "60" ra rỗng. Cắt sát mực:
        # 6/7 trang trước đó trượt đọc đúng ngay.
        rows = np.where((gray[:, a:b] < INK_MAX_GRAY).any(axis=1))[0]
        if rows.size == 0:
            continue
        r0 = max(0, rows[0] - pad)
        r1 = min(band.shape[0], rows[-1] + 1 + pad)
        crop = band[r0:r1, max(0, a - pad):min(w, b + pad)]
        if crop.size == 0:
            continue
        for scale, interp in ZONE_RESIZES:
            c = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=interp)
            for psm in ZONE_PSMS:
                txt = pt.image_to_string(
                    c, config=f"--psm {psm} "
                              f"-c tessedit_char_whitelist=0123456789")
                for run in re.findall(r"\d+", txt or ""):
                    v = int(run)
                    if 0 < v <= max_value:
                        found.add(v)
    return found


def band_and_side(zone: dict):
    """(y0, y1, side) suy từ vùng đã đo. `None` nếu chưa đo được vùng."""
    if not zone or zone.get("n", 0) == 0:
        return None
    hh = max(ZONE_HALF_H_MIN, zone.get("y_iqr", 0.0) * ZONE_IQR_MULT)
    y = zone["y_median"]
    side = "left" if zone["x_median"] < 0.5 else "right"
    return (max(0.0, y - hh), min(1.0, y + hh), side)


def refine_with_zone(source, fp, pages, verbose: bool = False):
    """Đọc lại trong dải đã đo, rồi BẦU LẠI offset từ số của giai đoạn B.

    Cross-check thật: offset giai đoạn B được tính độc lập với offset giai đoạn A.
    Hai bên lệch nhau -> gắn cờ, vì khi đó dải đo được (vốn suy từ offset A) không
    còn đáng tin. Không có nhánh nào "sửa" offset theo kỳ vọng.
    """
    bands = {p: band_and_side(fp.zone_by_parity.get(p) or {})
             for p in ("even", "odd")}
    if not any(bands.values()):
        fp.flags.append("khong_do_duoc_vung_de_doc_ky")
        return fp
    max_value = len(source.page_numbers()) + 5

    obs, missing = [], []
    for pn in pages:
        parity = "even" if (pn + (fp.offset or 0)) % 2 == 0 else "odd"
        band = bands.get(parity) or bands.get("even") or bands.get("odd")
        y0, y1, side = band
        vals = read_band_outer_groups(source.load(pn), y0, y1, side,
                                      max_value=max_value)
        obs.append((pn, sorted(vals)))
        if (pn + (fp.offset or 0)) not in vals:
            missing.append(pn)

    off_b, votes_b, off2_b, votes2_b = best_offset(obs)
    hit_b = votes_b / len(pages) if pages else 0.0
    if verbose:
        print(f"    [giai doan B] offset={off_b} votes={votes_b}/{len(pages)} "
              f"({hit_b:.0%}) a_quan={off2_b}:{votes2_b}")

    fp.zone_read = {
        "band_even": bands.get("even"), "band_odd": bands.get("odd"),
        "offset": off_b, "votes": votes_b, "hit_rate": round(hit_b, 4),
        "margin": votes_b - votes2_b,
        "trang_khong_doc_duoc": missing,
    }
    if off_b is not None and fp.offset is not None and off_b != fp.offset:
        fp.flags.append(f"offset_2_giai_doan_lech_{fp.offset}_vs_{off_b}")
    if hit_b > fp.hit_rate:
        fp.hit_rate = round(hit_b, 4)
        fp.votes = votes_b
        fp.margin_over_runner_up = votes_b - votes2_b
        fp.flags = [f for f in fp.flags
                    if not f.startswith(("ti_le_khop_thap", "margin_thap"))]
        if hit_b < MIN_HIT_RATE:
            fp.flags.append(f"ti_le_khop_thap_{hit_b:.0%}")
        if fp.margin_over_runner_up < MIN_MARGIN:
            fp.flags.append(f"margin_thap_{fp.margin_over_runner_up}")
    return fp


def body_sample(source, k: int, skip_front: int = SKIP_FRONT_PAGES) -> list:
    """Mẫu rải đều phần THÂN sách (bỏ `skip_front` trang đầu)."""
    pages = list(source.page_numbers())
    body = pages[skip_front:] or pages
    return sample_pages(body, k)


# ---------------------------------------------------------------------- CLI



def _load_existing(dest: Path) -> dict:
    if not dest.exists():
        return {}
    try:
        return json.loads(dest.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        print(f"    KHONG DOC DUOC {dest.name}: {exc} -> coi nhu chua co")
        return {}


def _run_stage(name: str, fn) -> tuple:
    """`(ket_qua, that_bai)`. Lỗi được IN RA và gắn cờ, không nuốt (CẤM #7)."""
    try:
        return fn(), False
    except Exception as exc:                # noqa: BLE001 - cô lập theo stage
        print(f"    LOI stage {name}: {type(exc).__name__}: {exc}")
        return {"flags": [f"loi_khi_do:{type(exc).__name__}: {exc}"]}, True


def _probe_book(source, stages: tuple, sample: int, toc_scan: int,
                toc_back: int, palette_sample: int, pill_sample: int,
                verbose: bool) -> dict:
    from . import fp_figure, fp_palette, fp_toc

    results: dict = {}
    if "page_number" in stages:
        results["page_number"], _ = _run_stage(
            "page_number",
            lambda: asdict(probe_page_numbers(source, sample=sample,
                                              verbose=verbose)))
    if "toc" in stages:
        results["toc"], _ = _run_stage(
            "toc", lambda: fp_toc.probe_toc(source, scan=toc_scan,
                                            back=toc_back, verbose=verbose))
    if "palette" in stages:
        results["box_palette"], _ = _run_stage(
            "palette",
            lambda: fp_palette.probe_box_palette(
                source, body_sample(source, palette_sample), verbose=verbose))
    if "pill" in stages:
        results["pill_pattern"], _ = _run_stage(
            "pill",
            lambda: fp_figure.probe_pill_pattern(
                source, body_sample(source, pill_sample), verbose=verbose))
    return results


def _print_book(name: str, merged: dict, stages: tuple) -> list:
    """In gọn kết quả một quyển; trả về danh sách cờ của các stage vừa chạy."""
    flags: list = []
    pn = merged.get("page_number") or {}
    if "page_number" in stages and pn:
        ez = (pn.get("zone_by_parity") or {}).get("even", {})
        oz = (pn.get("zone_by_parity") or {}).get("odd", {})
        print(f"    so trang: offset={pn.get('offset')} "
              f"khop={pn.get('votes')}/{pn.get('total_pages_probed')} "
              f"margin={pn.get('margin_over_runner_up')} "
              f"scale={pn.get('scale_used')}x")
        print(f"      chan x~{ez.get('x_median')} y~{ez.get('y_median')} "
              f"(n={ez.get('n')}) | le x~{oz.get('x_median')} "
              f"y~{oz.get('y_median')} (n={oz.get('n')})")
        flags += [f"page_number:{f}" for f in pn.get("flags", [])]

    toc = merged.get("toc") or {}
    if "toc" in stages and toc:
        spine = toc.get("spine") or {}
        print(f"    muc luc : trang={toc.get('toc_pages')} "
              f"({toc.get('where')}) style={toc.get('entry_style')} "
              f"how={toc.get('how')} cot={toc.get('n_col_groups')} "
              f"dot_leader={toc.get('uses_dot_leader')}")
        print(f"      spine : {spine.get('reader')} -> {spine.get('n_entries')} bai "
              f"({spine.get('bai_min')}..{spine.get('bai_max')}) "
              f"bai_lien_mach={spine.get('contiguous')}")
        flags += [f"toc:{f}" for f in toc.get("flags", [])]

    pal = merged.get("box_palette") or {}
    if "palette" in stages and pal:
        top = (pal.get("hue_bands") or [])[:3]
        print(f"    palette : {pal.get('n_regions')} vung "
              f"({pal.get('regions_per_page')}/trang), "
              f"sat p10={(pal.get('sat_percentiles') or {}).get('p10')} "
              f"p50={(pal.get('sat_percentiles') or {}).get('p50')}")
        for band in top:
            print(f"      hue {band['hue_lo']:>3}-{band['hue_hi']:<3} n={band['n']:<4}"
                  f" sat~{band['sat_median']} val~{band['val_median']} "
                  f"dt~{band['area_frac_median']}")
        flags += [f"palette:{f}" for f in pal.get("flags", [])]

    pill = merged.get("pill_pattern") or {}
    if "pill" in stages and pill:
        print(f"    nhan hinh: {pill.get('ket_luan')} | pill={pill.get('n_pill_boxes')}"
              f" doc={pill.get('n_pill_read')} nhan={pill.get('n_pill_figure_label')}"
              f" | caption={pill.get('caption_counts')}")
        flags += [f"pill:{f}" for f in pill.get("flags", [])]

    if flags:
        print(f"    CO CO: {flags}")
    return flags


def run(book: Optional[str], sample: int, verbose: bool,
        stages: tuple = STAGES, toc_scan: int = 15, toc_back: int = 8,
        palette_sample: int = PALETTE_SAMPLE,
        pill_sample: int = PILL_SAMPLE) -> int:
    from src.config import DATA_DIR, FINGERPRINT_DIR
    from src.etl.page_source import discover_page_sources

    sources = discover_page_sources(DATA_DIR)
    if book:
        sources = [s for s in sources if s.name == book]
        if not sources:
            print(f"Khong tim thay quyen {book}")
            return 1

    FINGERPRINT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"stage: {','.join(stages)}")
    rows = []
    for s in sources:
        t0 = time.time()
        print(f"\n[{s.name}] {len(s.page_numbers())} trang")
        # Cô lập lỗi THEO QUYỂN **và theo stage**: một quyển hỏng (ví dụ file bị
        # xoá giữa lượt đo — `PngFolderPageSource` cache danh sách file lúc khởi
        # tạo) không được giết cả phép đo 12 quyển, và một stage hỏng không được
        # giết ba stage còn lại.
        results = _probe_book(s, stages, sample, toc_scan, toc_back,
                              palette_sample, pill_sample, verbose)

        dest = FINGERPRINT_DIR / f"{s.name}.json"
        merged = _load_existing(dest)
        merged["book"] = s.name
        merged["n_pages"] = len(s.page_numbers())
        # KHÔNG ghi đè một phép đo TỐT bằng một lần đo HỎNG. Đã xảy ra thật: giết
        # tiến trình giữa lượt chạy làm mọi tesseract con chết, mỗi quyển raise
        # `TesseractError`, và nhánh cô lập lỗi ghi đè 11/12 file đo tốt bằng bản
        # `offset=None`. Mất phép đo vì hạ tầng là mất dữ liệu, không phải là kết
        # quả — nên bản hỏng chỉ được ghi khi CHƯA có gì để mất.
        for key, value in results.items():
            failed = any(str(f).startswith("loi_khi_do")
                         for f in (value.get("flags") or []))
            if failed and merged.get(key) and not any(
                    str(f).startswith("loi_khi_do")
                    for f in (merged[key].get("flags") or [])):
                print(f"    GIU NGUYEN {key} cua {dest.name} (ban do cu con tot)")
                continue
            merged[key] = value
        dest.write_text(json.dumps(merged, ensure_ascii=False, indent=2),
                        encoding="utf-8")

        flags = _print_book(s.name, merged, stages)
        print(f"    tong {time.time() - t0:.0f}s")
        rows.append((s.name, merged, flags))

    print("\n" + "=" * 96)
    header = f"{'quyen':<18}{'offset':>7}{'khop':>9}{'toc':>10}{'bai':>6}{'pal':>6}{'nhan':>12}  co"
    print(header)
    bad = 0
    for name, merged, flags in rows:
        pn = merged.get("page_number") or {}
        toc = merged.get("toc") or {}
        spine = toc.get("spine") or {}
        pal = merged.get("box_palette") or {}
        pill = merged.get("pill_pattern") or {}
        bad += 1 if flags else 0
        print(f"{name:<18}{str(pn.get('offset')):>7}"
              f"{f'{pn.get("votes")}/{pn.get("total_pages_probed")}':>9}"
              f"{str(toc.get('toc_pages') or '-'):>10}"
              f"{str(spine.get('n_entries') or '-'):>6}"
              f"{str(pal.get('n_regions') or '-'):>6}"
              f"{str(pill.get('ket_luan') or '-'):>12}  "
              f"{';'.join(flags) if flags else '-'}")
    print(f"\n{len(rows) - bad}/{len(rows)} quyen KHONG co co nao.")
    return 0 if bad == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="M0 — do dac trung layout tung quyen")
    ap.add_argument("--book", help="chi mot quyen")
    ap.add_argument("--all", action="store_true", help="tat ca cac quyen")
    ap.add_argument("--sample", type=int, default=40,
                    help="so trang lay mau cho stage page_number")
    ap.add_argument("--stages", default="all",
                    help=f"danh sach stage, phay: {','.join(STAGES)} (mac dinh all)")
    ap.add_argument("--toc-scan", type=int, default=15,
                    help="so trang DAU sach quet tim MUC LUC")
    ap.add_argument("--toc-back", type=int, default=8,
                    help="so trang CUOI sach quet tim MUC LUC (CD in o cuoi)")
    ap.add_argument("--palette-sample", type=int, default=PALETTE_SAMPLE)
    ap.add_argument("--pill-sample", type=int, default=PILL_SAMPLE)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    if not a.book and not a.all:
        ap.error("can --book hoac --all")
    stages = (STAGES if a.stages.strip() == "all"
              else tuple(x.strip() for x in a.stages.split(",") if x.strip()))
    unknown = [x for x in stages if x not in STAGES]
    if unknown:
        ap.error(f"stage khong biet: {unknown}; chon trong {list(STAGES)}")
    logging.basicConfig(level=logging.WARNING)
    return run(a.book, a.sample, a.verbose, stages=stages, toc_scan=a.toc_scan,
               toc_back=a.toc_back, palette_sample=a.palette_sample,
               pill_sample=a.pill_sample)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    raise SystemExit(main())
