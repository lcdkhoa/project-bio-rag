"""Đọc MỤC LỤC như một BẢNG, không như một khối text.

## Vì sao viết lại (đo được, 2026-08-21)

Bản cũ OCR cả trang --psm 4 rồi khớp regex "Bài N. Title <số trang>" trên từng
dòng. Trên nguồn PNG nó trả về **0 entry cho sách 6** — không phải vì OCR kém,
mà vì MỤC LỤC là một **bảng hai/ba cột**: số trang nằm trong một cột hẹp riêng ở
bên phải, cách phần tiêu đề một khoảng lớn. Tesseract không ghép nó vào cuối
dòng, nên không dòng nào kết thúc bằng số trang và regex không bao giờ khớp. Đo
thêm: --psm 6 trên cả trang chỉ ra **49 từ** cho một trang MỤC LỤC đầy chữ, vì
đường kẻ của bảng dính vào chữ số (đọc ra "[z7", "[áÌ").

Cách làm ở đây: tìm **hình học của bảng** trước (deterministic, CV thuần), rồi
mới OCR từng ô. Bốn quyển in MỤC LỤC theo ba kiểu khác nhau — sách 6 và 9 kẻ
khung, sách 7 và 8 dùng dải màu xen kẽ không kẻ; sách 7/8 tách "Bài N" thành một
cột riêng — nên phần hình học phải tự hiệu chỉnh, không hardcode toạ độ.

## Luật

1. **Cột số trang** = dải nằm giữa HAI đường kẻ dọc cuối cùng nếu trang có kẻ
   khung (đo: sách 6/9 có đúng 2 đường kẻ ở nửa phải), ngược lại là **nhóm mực
   ngoài cùng bên phải** tách khỏi phần còn lại bởi một khoảng trắng >= 8 px
   (sách 7/8). Cần cả hai vì sách 9 KHÔNG có khoảng trắng nào chạy suốt chiều
   cao bảng (tiêu đề chương dài sát đường kẻ), còn sách 7/8 không có đường kẻ.
2. **Hàng** = các cụm mực rời nhau theo chiều dọc *bên trong cột số trang*. Mỗi
   số trang là một cụm biệt lập, nên đây là bộ chia hàng đáng tin nhất.
3. Ô tiêu đề của hàng i = dải y giữa hai trung điểm hàng kề. Lấy theo trung điểm
   (không theo bbox của số) để **hàng chương hai dòng không bị cắt cụt**.
4. Số trang đọc bằng **hợp của nhiều scale x nhiều psm**. Đây đúng là lỗi đã đo
   ở số trang góc (D-33): chữ số nhỏ bị Tesseract cắt cụt — "166" thành "16",
   "169" thành "19". Không scale/psm nào tốt nhất ở mọi ô (đo trên sách 9: 166
   chỉ ra ở 3x/psm 7, còn 169 chỉ ra ở 3x/psm 8|13), nên phải hợp lại rồi để
   ràng buộc đơn điệu chọn. **Đây là ngoại lệ upscale duy nhất được phép cùng
   với số trang góc và pill** — thân bài vẫn OCR ở 1x.
5. Ứng viên số trang được chốt bằng **ràng buộc đơn điệu** (số trang không giảm
   khi đi xuống). Không ứng viên nào hợp lệ -> **bỏ entry + flag**, không đoán.

## Giới hạn (nói ra, không giấu)

Sách 6 in tiêu đề CHƯƠNG bằng chữ trắng trên nền màu và ô số trang của hàng đó
để trống, nên hàng chương dính vào ô tiêu đề của Bài ngay dưới và OCR ra rác.
Tên Bài vẫn đọc đúng (regex lấy phần sau "Bài N"), nhưng **danh sách chương của
sách 6 sẽ thiếu** — đó là một flag, không phải một con số bịa.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

import cv2
import numpy as np
import pytesseract

from ...config import TESSERACT_CMD

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

# Khoảng SỐ TRANG NGUỒN có thể chứa MỤC LỤC. Đo được: sách 6 dùng trang 5-7, ba
# quyển còn lại dùng 5-6. Bản cũ hardcode (5, 6) và vì thế **mất 16 Bài cuối của
# sách 6** (Bài 40-55 nằm ở page_007). Không hardcode nữa: quét dải này rồi để
# chính nội dung quyết định (>= MIN_BAI_ROWS hàng đọc ra "Bài N").
TOC_SEARCH_PAGES = range(3, 10)
MIN_BAI_ROWS = 3
MAX_PRINTED_PAGE = 400

RULE_RUN_FRAC = 0.30      # cột có nét dọc dài >= 30% chiều cao = đường kẻ bảng
INK_MAX = 128             # mực = tối hơn ngưỡng này
PALE_MAX = 235            # "không phải giấy trắng" (bắt cả nét kẻ màu)
TOP_CLIP, BOT_CLIP = 0.06, 0.92   # bỏ vùng số trang ở góc trên/dưới
COL_GUTTER = 8
ROW_GUTTER = 6
MIN_COL_WIDTH = 10
MIN_ROW_HEIGHT = 8
MIN_ROWS = 8
NUMBER_SCALES = (1, 3)
NUMBER_PSMS_FAST = (7, 6)
NUMBER_PSMS_FULL = (7, 6, 8, 13)
# Nới crop ô số ra hai bên. Đo trên sách 8: cột số chỉ rộng 29 px trong khi số
# ba chữ số rộng hơn thế, nên **chữ số đầu bị CROP cắt mất** — "180" đọc ra
# "80", "191" ra "9". Đây không phải lỗi OCR: nới 6 px là đọc đúng cả dãy
# 177/180/185/188/191. Ứng viên rác sinh thêm do nới (ví dụ "74") bị ràng buộc
# đơn điệu loại, nên nới rộng an toàn hơn là cắt cụt.
# ...NHƯNG chỉ khi cột được xác định bằng KHOẢNG TRẮNG. Cột xác định bằng ĐƯỜNG
# KẺ đã là đúng bề rộng ô (sách 6: 67 px, sách 9: 84 px) và nới ra sẽ liếm vào
# chính nét kẻ: đo được là ô TRỐNG của hàng chương khi đó OCR ra "149", con số
# ma ấy đẩy con trỏ đơn điệu lên và giết Bài 40 + 41 của sách 6.
NUMBER_PADS_RULES = (0,)
NUMBER_PADS_GUTTER = (6,)
NUMBER_PADS_RULES_FULL = (0,)
NUMBER_PADS_GUTTER_FULL = (0, 6, 12)


def _pads(how: str, full: bool = False) -> tuple:
    if how == "rules":
        return NUMBER_PADS_RULES_FULL if full else NUMBER_PADS_RULES
    return NUMBER_PADS_GUTTER_FULL if full else NUMBER_PADS_GUTTER

# "Bài 12", "Bài 12.", "Bài I" (OCR đọc chữ số 1 thành I/l/|). Chỉ nhận tối đa 2
# chữ số: không quyển nào tới 100 Bài, và nới ra sẽ nuốt cả số trang.
_BAI = re.compile(r"B[àaáâ]i\s*([0-9IlL|]{1,2})(?![0-9IlL|])")
_CHUONG = re.compile(r"CH[ƯU][ƠO]NG\s+([IVXL]+)\s*[-–—.]?\s*(.*)", re.IGNORECASE)
_ONE_LIKE = str.maketrans({"I": "1", "l": "1", "L": "1", "|": "1"})


@dataclass(frozen=True)
class TocEntry:
    bai_so: int
    title: str
    start_page: int           # SỐ TRANG IN (đúng như MỤC LỤC ghi)


@dataclass(frozen=True)
class TocChuong:
    label: str
    title: str
    after_bai: Optional[int]


@dataclass(frozen=True)
class TocRow:
    page_index: int
    candidates: frozenset      # ứng viên số trang đọc được cho hàng này
    text: str                  # OCR ô tiêu đề


@dataclass
class TocResult:
    entries: list = field(default_factory=list)
    chuongs: list = field(default_factory=list)
    flags: list = field(default_factory=list)
    page_indices: list = field(default_factory=list)   # trang nguồn là MỤC LỤC


# ---------------------------------------------------------------- hình học

def _max_run_per_column(mask: np.ndarray) -> np.ndarray:
    """Nét dọc dài nhất của từng cột. Lặp theo HÀNG (1536 phép vector) chứ không
    theo pixel: bản vòng lặp thuần Python tốn ~1,7 triệu bước cho mỗi trang."""
    current = np.zeros(mask.shape[1], dtype=np.int32)
    best = np.zeros(mask.shape[1], dtype=np.int32)
    for row in mask:
        current = np.where(row, current + 1, 0)
        np.maximum(best, current, out=best)
    return best


def _runs(flags: np.ndarray, lo: int, hi: int, gutter: int) -> list:
    """Các đoạn True liên tiếp, gộp qua khe < `gutter`."""
    out: list = []
    start = None
    gap = 0
    for index in range(lo, hi):
        if flags[index]:
            if start is None:
                start = index
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= gutter:
                out.append((start, index - gap))
                start, gap = None, 0
    if start is not None:
        out.append((start, hi - 1))
    return out


def _rule_columns(gray: np.ndarray) -> np.ndarray:
    height = gray.shape[0]
    return _max_run_per_column(gray < PALE_MAX) >= RULE_RUN_FRAC * height


def number_column(gray: np.ndarray) -> tuple:
    """`((x0, x1), "rules"|"gutter")` của cột số trang, hoặc `(None, None)`."""
    height, width = gray.shape
    rules = _rule_columns(gray)
    rule_groups = [g for g in _runs(rules, 0, width, gutter=1) if g[0] > width // 2]
    if len(rule_groups) >= 2:
        left, right = rule_groups[-2], rule_groups[-1]
        if right[0] - left[1] >= MIN_COL_WIDTH + 2:
            return (left[1] + 1, right[0] - 1), "rules"
    body = (gray < INK_MAX)[int(TOP_CLIP * height):int(BOT_CLIP * height), :]
    has_ink = (body.sum(axis=0) > 2) & (~rules)
    groups = [g for g in _runs(has_ink, width // 2, width, gutter=COL_GUTTER)
              if g[1] - g[0] + 1 >= MIN_COL_WIDTH]
    return (groups[-1], "gutter") if groups else (None, None)


def row_bands(gray: np.ndarray, x0: int, x1: int) -> list:
    height = gray.shape[0]
    has_ink = ((gray[:, x0:x1 + 1] < INK_MAX).sum(axis=1)) > 0
    bands = _runs(has_ink, int(TOP_CLIP * height), int(BOT_CLIP * height),
                  gutter=ROW_GUTTER)
    return [b for b in bands if b[1] - b[0] + 1 >= MIN_ROW_HEIGHT]


def _left_edge(gray: np.ndarray) -> int:
    height = gray.shape[0]
    body = (gray < INK_MAX)[int(TOP_CLIP * height):int(BOT_CLIP * height), :]
    inked = np.nonzero(body.sum(axis=0) > 2)[0]
    return int(inked.min()) if inked.size else 0


# ------------------------------------------------------------------- OCR

def _ocr(image: np.ndarray, psm: int, whitelist: str = "") -> str:
    config = f"--psm {psm}"
    if whitelist:
        config += f" -c tessedit_char_whitelist={whitelist}"
    return pytesseract.image_to_string(image, lang="vie", config=config)


def read_number_cell(image: np.ndarray, box: tuple,
                     psms: Sequence = NUMBER_PSMS_FAST,
                     pads: Sequence = (0,)) -> set:
    """Hợp các số đọc được từ một ô, qua nhiều pad x scale x psm (docstring §4)."""
    y0, y1, x0, x1 = box
    found: set = set()
    for pad in pads:
        crop = image[max(0, y0 - 3):y1 + 4, max(0, x0 - pad):x1 + 1 + pad]
        if crop.size == 0:
            continue
        for scale in NUMBER_SCALES:
            scaled = crop if scale == 1 else cv2.resize(
                crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            for psm in psms:
                digits = "".join(c for c in _ocr(scaled, psm, "0123456789")
                                 if c.isdigit())
                if digits and len(digits) <= 3:
                    value = int(digits)
                    if 0 < value <= MAX_PRINTED_PAGE:
                        found.add(value)
    return found


def read_row_text(image: np.ndarray, box: tuple) -> str:
    """OCR ô tiêu đề. `--psm 6` là mặc định; ô nào ra RỖNG thì thử lại `--psm 4`
    ở 2x. Đo được trên sách 7: hàng đầu bảng (Bài 19 "Từ trường") ra rỗng ở psm
    6/7/11 nhưng đọc đủ ở psm 4 — bỏ qua nó là mất hẳn một Bài khỏi spine. Chỉ
    chạy khi kết quả rỗng, nên không đổi gì ở các hàng vốn đã đọc được."""
    y0, y1, x0, x1 = box
    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        return ""
    text = " ".join(_ocr(crop, 6).split())
    if text:
        return text
    scaled = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    return " ".join(_ocr(scaled, 4).split())


def _table_geometry(source, page_index: int):
    """(image, gray, (nx0, nx1), bands, left_x, how) hoặc None nếu không phải bảng."""
    image = source.load(page_index)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    column, how = number_column(gray)
    if column is None:
        return None
    nx0, nx1 = column
    bands = row_bands(gray, nx0, nx1)
    if len(bands) < MIN_ROWS:
        return None
    left_x = _left_edge(gray)
    if nx0 - 4 <= left_x + 10:
        return None
    return image, gray, (nx0, nx1), bands, left_x, how


def read_toc_rows(source, page_index: int) -> Optional[list]:
    """Hàng của bảng MỤC LỤC trên một trang, hoặc None nếu trang không phải bảng."""
    geometry = _table_geometry(source, page_index)
    if geometry is None:
        return None
    image, gray, (nx0, nx1), bands, left_x, how = geometry
    height = gray.shape[0]
    centers = [(b[0] + b[1]) // 2 for b in bands]
    rows = []
    for index, (band, center) in enumerate(zip(bands, centers)):
        top = (centers[index - 1] + center) // 2 if index else max(0, band[0] - 26)
        bottom = ((centers[index + 1] + center) // 2 if index + 1 < len(centers)
                  else min(height - 1, band[1] + 26))
        text = read_row_text(image, (top, bottom, max(0, left_x - 4), nx0 - 4))
        # Ô số trang chỉ đọc khi hàng đó thực sự là một Bài/Chương — OCR số là
        # phần đắt nhất (nhiều scale x psm) và phần lớn hàng không cần tới.
        candidates = set()
        if _BAI.search(text):
            candidates = read_number_cell(image, (band[0], band[1], nx0, nx1),
                                          pads=_pads(how))
        rows.append(TocRow(page_index=page_index,
                           candidates=frozenset(candidates), text=text))
    return rows


# ------------------------------------------------------------- phát hiện

def find_toc_pages(source, search: Iterable = TOC_SEARCH_PAGES) -> tuple:
    """Các trang nguồn là MỤC LỤC (liền nhau), kèm hàng đã đọc của từng trang."""
    available = set(source.page_numbers())
    found: dict = {}
    for page_index in search:
        if page_index not in available:
            continue
        rows = read_toc_rows(source, page_index)
        if rows is None or sum(1 for r in rows if _BAI.search(r.text)) < MIN_BAI_ROWS:
            if found:
                break          # hết dải MỤC LỤC liền mạch
            continue
        found[page_index] = rows
    return sorted(found), found


# --------------------------------------------------------------- phân tích

def _normalise_bai(token: str) -> Optional[int]:
    digits = token.translate(_ONE_LIKE)
    return int(digits) if digits.isdigit() else None


def parse_toc_rows(rows: Sequence, *, rescue=None) -> TocResult:
    """Hàng bảng -> entries/chuongs, chốt số trang bằng ràng buộc đơn điệu.

    `rescue(row_position, row)` (tuỳ chọn) đọc lại ô số của một hàng với đủ psm;
    chỉ được gọi khi bộ ứng viên nhanh không có cái nào hợp ràng buộc.
    """
    result = TocResult()
    previous_page = 0
    previous_bai = 0
    for position, row in enumerate(rows):
        chuong = _CHUONG.search(row.text)
        bai = _BAI.search(row.text)
        if chuong and not bai:
            result.chuongs.append(TocChuong(
                label=chuong.group(1).upper(),
                title=chuong.group(2).strip(" -–—.").strip(),
                after_bai=previous_bai or None))
            # KHÔNG cho hàng chương đẩy con trỏ đơn điệu: số trang của nó luôn
            # trùng số trang của Bài ngay dưới (không thêm tin gì), còn ô trống
            # của nó thì OCR ra số ma — đúng thứ đã giết Bài 40/41 của sách 6.
            continue
        if not bai:
            continue
        bai_so = _normalise_bai(bai.group(1))
        if bai_so is None or bai_so <= previous_bai:
            continue           # "Bài tập …" trong tiêu đề, hoặc số không tăng
        candidates = {c for c in row.candidates if c >= previous_page}
        if not candidates and rescue is not None:
            candidates = {c for c in rescue(position, row) if c >= previous_page}
        if not candidates:
            result.flags.append({
                "kind": "toc_page_unreadable",
                "detail": f"Bài {bai_so} (trang nguồn {row.page_index}): ứng viên "
                          f"số trang {sorted(row.candidates)} đều < {previous_page} "
                          f"-> bỏ entry, không đoán"})
            continue
        start_page = min(candidates)
        if len(candidates) > 1:
            result.flags.append({
                "kind": "toc_page_ambiguous",
                "detail": f"Bài {bai_so}: nhiều ứng viên {sorted(candidates)} "
                          f"-> lấy {start_page} (nhỏ nhất hợp đơn điệu)"})
        title = row.text[bai.end():].strip(" .:-–—").strip()
        result.entries.append(TocEntry(bai_so=bai_so, title=title,
                                       start_page=start_page))
        previous_bai, previous_page = bai_so, start_page
    return result


def read_toc(source) -> TocResult:
    """Điểm vào: đọc MỤC LỤC của một quyển thành entries + chuongs + flags."""
    page_indices, rows_by_page = find_toc_pages(source)
    if not page_indices:
        return TocResult(flags=[{
            "kind": "toc_not_found",
            "detail": f"{source.name}: không tìm thấy trang MỤC LỤC nào trong "
                      f"{list(TOC_SEARCH_PAGES)}"}])

    rows: list = []
    boxes: list = []           # (page_index, band) song song với `rows`
    for page_index in page_indices:
        geometry = _table_geometry(source, page_index)
        page_rows = rows_by_page[page_index]
        bands = geometry[3] if geometry else [None] * len(page_rows)
        rows.extend(page_rows)
        boxes.extend((page_index, band) for band in bands[:len(page_rows)])

    def rescue(position, row):
        page_index, band = boxes[position]
        if band is None:
            return set()
        geometry = _table_geometry(source, page_index)
        if geometry is None:
            return set()
        image, _gray, (nx0, nx1), _bands, _left, how = geometry
        return read_number_cell(image, (band[0], band[1], nx0, nx1),
                                psms=NUMBER_PSMS_FULL, pads=_pads(how, full=True))

    result = parse_toc_rows(rows, rescue=rescue)
    result.page_indices = page_indices
    return result
