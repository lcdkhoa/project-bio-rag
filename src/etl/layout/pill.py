"""Đọc chữ TRẮNG trên nền MÀU ĐẶC ("pill") — thứ OCR thường bỏ trắng.

## Vì sao cần

Tesseract giả định chữ tối trên nền sáng. KNTT in ba loại nhãn quan trọng theo
kiểu ngược lại — chữ trắng trên nền màu đặc:

* nhãn hình `Hình N.M` (viên thuốc màu cam) — **chính là anchor mà phía crop hình
  dựa vào**;
* nhãn ô so sánh (`Thông tin liên lạc`, `Sản xuất`, `Giao thông vận tải`);
* nhãn mở đầu Bài trong banner.

Đo trên nguồn PNG: các nhãn này **không đọc được ở bất kỳ scale nào** (1×, 1,134×
= đúng kích thước bản render 150 DPI cũ, 1,5×, 2×) — nên đây không phải vấn đề độ
phân giải, và **đảo màu cả trang/cả crop lớn cũng không cứu** (tesseract tự
binarize cục bộ nên vẫn đọc ra phần chữ tối). Chỉ cách này hoạt động: khoanh
đúng cái pill, rồi OCR trên bản **đảo màu** của riêng nó.

## Luật (deterministic, giải thích được)

1. Thành phần liên thông của `sat >= SAT_MIN & val <= VAL_MAX` = một mảng màu đặc.
2. Nó **lấp gần kín bbox** (`solidity >= SOLIDITY_MIN`) → hình chữ nhật/viên
   thuốc, không phải nét vẽ hay ảnh.
3. Nó **có lỗ** (`HOLE_FRAC` trong khoảng) → bên trong có chữ, không phải khối đặc.
4. Kích thước cỡ một nhãn, không phải cả panel.
5. Rồi OCR bản đảo màu và **để chính nội dung đọc được phán xử**: nhãn hình chỉ
   được nhận khi khớp `Hình N.M`. Đây là phép thử tự kiểm — một pill giả đọc ra
   rác thì bị loại, không có chuyện đoán.

Cố tình KHÔNG kiểm màu của lỗ bằng ngưỡng tuyệt đối: đo được là chữ trắng bị
antialias xuống gray median 168 trên pill sáng và 223 trên pill đậm, nên mọi
ngưỡng đều loại oan một trong hai (đúng cái pill `Hình 1.2` của `page_010`).
"""
from __future__ import annotations

import re

import cv2
import numpy as np
import pytesseract

from ..cleaner import clean_vietnamese_text
from ...config import TESSERACT_CMD

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

SAT_MIN = 70            # nền màu thật, không phải giấy/tông nhạt
VAL_MAX = 250
MIN_W, MAX_W = 55, 460
MIN_H, MAX_H = 18, 70
SOLIDITY_MIN = 0.80
HOLE_FRAC_MIN, HOLE_FRAC_MAX = 0.05, 0.55
CLOSE_KERNEL = 9
OCR_SCALE = 2           # crop pill quá nhỏ để OCR ở kích thước gốc

# `Hình 1.2`, `Hình 25.5`. Chữ "i" nhận MỌI biến thể dấu vì OCR trên pill đảo màu
# đọc ra đủ kiểu (đo được: `Hỉnh`, `Hình`, `Hinh`) — dấu của chữ "Hình" không mang
# thông tin nào, còn HAI CON SỐ thì không được đoán: chúng phải đọc ra thật.
FIGURE_LABEL = re.compile(r"H[iìíỉĩị]nh\s*(\d{1,2})\s*[.,]\s*(\d{1,2})")


def _pill_boxes_in_mask(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Pill trong một mask nhị phân: lấp kín bbox, có lỗ (chữ), cỡ một nhãn."""
    closed = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE, np.ones((CLOSE_KERNEL, CLOSE_KERNEL), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    out = []
    for label in range(1, count):
        x, y, width, height, area = stats[label]
        if not (MIN_W <= width <= MAX_W and MIN_H <= height <= MAX_H):
            continue
        if area < SOLIDITY_MIN * width * height:
            continue
        component = labels[y:y + height, x:x + width] == label
        filled = mask[y:y + height, x:x + width].astype(bool) & component
        holes = component & ~filled
        hole_frac = holes.sum() / float(area)
        if not (HOLE_FRAC_MIN <= hole_frac <= HOLE_FRAC_MAX):
            continue
        out.append((int(x), int(y), int(x + width), int(y + height)))
    return out


def find_pill_boxes(image_bgr: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Các bbox `(x0, y0, x1, y1)` trông như một pill có chữ bên trong.

    **Giới hạn đã đo, nói ra để không ai tưởng nó bắt hết:** luật này chỉ bắt
    được pill nằm trên nền GIẤY (nhãn `Hình N.M`). Pill nằm LỒNG trong một ô/panel
    đã có tông màu thì dính vào ô đó rồi bị loại vì quá to — và không sửa được
    bằng một ngưỡng saturation nào, vì pill không nhất thiết đậm hơn nền: đo trên
    `page_010`, pill "Giao thông vận tải" có sat **82** còn dải tím nó nằm trên có
    sat **157**. Tách theo dải hue cũng đã thử: KHÔNG khá hơn (cùng kết quả trên
    `page_010`, thêm rác trên `page_011`). Vì vậy ba nhãn ô so sánh
    ("Thông tin liên lạc" / "Sản xuất" / "Giao thông vận tải") **vẫn chưa đọc
    được** — cần một thiết kế dựa trên tương phản CỤC BỘ và một phiên đo riêng.
    """
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    solid = ((hsv[:, :, 1] >= SAT_MIN) & (hsv[:, :, 2] <= VAL_MAX)).astype(np.uint8)
    return _pill_boxes_in_mask(solid)


def read_pill(image_bgr: np.ndarray, bbox: tuple[int, int, int, int],
              scale: int = OCR_SCALE) -> str:
    """OCR một pill trên bản ĐẢO MÀU (chữ trắng -> chữ tối). `--psm 7`: một dòng."""
    x0, y0, x1, y1 = bbox
    crop = image_bgr[y0:y1, x0:x1]
    if crop.size == 0:
        return ""
    if scale != 1:
        crop = cv2.resize(crop, None, fx=scale, fy=scale,
                          interpolation=cv2.INTER_CUBIC)
    raw = pytesseract.image_to_string(255 - crop, lang="vie", config="--psm 7")
    return " ".join(clean_vietnamese_text(raw).split())


def read_pill_labels(image_bgr: np.ndarray) -> list[dict]:
    """Mọi pill đọc được chữ, dạng `{"text", "bbox", "figure_label"}`.

    `figure_label` là `"Hình N.M"` đã chuẩn hoá nếu pill đó là nhãn hình, ngược
    lại là `None`. Pill đọc ra rỗng bị bỏ (không bịa).
    """
    out = []
    for bbox in find_pill_boxes(image_bgr):
        text = read_pill(image_bgr, bbox)
        if not text:
            continue
        match = FIGURE_LABEL.search(text)
        out.append({
            "text": text,
            "bbox": bbox,
            "figure_label": (f"Hình {int(match.group(1))}.{int(match.group(2))}"
                             if match else None),
        })
    return out


def figure_label_lines(image_bgr: np.ndarray) -> list[dict]:
    """Chỉ các pill LÀ nhãn hình, dạng `{"text", "bbox"}` để nối vào text_lines.

    `text` được ghi lại theo dạng chuẩn `Hình N.M` (chuẩn hoá từ chính chữ đọc
    được, không thêm gì), vì đường crop hình khớp anchor bằng regex trên text.
    """
    return [{"text": item["figure_label"], "bbox": item["bbox"]}
            for item in read_pill_labels(image_bgr) if item["figure_label"]]
