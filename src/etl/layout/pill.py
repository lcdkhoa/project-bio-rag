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

## Kích thước và kernel là theo TỈ LỆ chiều rộng trang

`MIN_W/MAX_W = 55/460`, `MIN_H/MAX_H = 18/70` và `CLOSE_KERNELS = (3, 5, 9)` đều
được **đo trên KNTT ở 1094 px chiều rộng**. CD/CTST rộng 2280-2480 px, nên một
pill `Hình N.M` ở đó rộng ~2,1-2,3 lần: `MAX_W = 460` sẽ **loại sạch mọi pill**
của CD/CTST vì chúng vượt ngưỡng. `bounds_for_width(w)` nhân theo `w / 1094` và
ở đúng 1094 px trả lại y nguyên bộ số cũ (có test chốt). Bộ số thực dùng phải
được GHI RA khi đo, để một kết quả 0 pill phân biệt được "quyển này không dùng
pill" với "ta đo bằng ngưỡng của quyển khác".

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
# MỘT kernel CLOSE là không đủ — cùng bài học với số trang góc (D-33), ô số MỤC
# LỤC (D-43) và psm của pill (D-45): không tham số nào thắng ở mọi trang, nên hợp
# ứng viên qua nhiều biến thể rồi để một ràng buộc TỰ KIỂM (`Hình N.M`) phán xử.
#
# Đo trên `SGK_KHTN_9_KNTT/page_017`, pill `Hình 2.3` (cam, nằm trong ô nền kem,
# sát khối màu của minh hoạ):
#   k=3 -> thành phần 113x30, solidity 0,882, đọc ra "Hình2.3"  ✓
#   k=5,7,9,11 -> pill DÍNH vào minh hoạ thành khối 505x286 (solidity 0,50),
#                 rộng 505 > MAX_W 460 nên bị loại -> mất hẳn nhãn hình.
# Kernel nhỏ đứng trước để bbox khít nhất được giữ khi dedupe.
#
# k=0 bị loại theo CẤU TRÚC, không phải theo phép đo: khi không close thì
# `closed == mask` nên `holes` luôn rỗng -> `hole_frac = 0` < HOLE_FRAC_MIN, mọi
# pill đều bị loại. Đừng thêm 0 vào đây.
CLOSE_KERNELS = (3, 5, 9)
OCR_SCALE = 2           # crop pill quá nhỏ để OCR ở kích thước gốc
# (scale, psm) đọc thử theo thứ tự. MỘT psm là KHÔNG đủ — đo trên `page_010`:
# pill `Hình 1.3` đọc được ở psm 7, còn pill `Hình 1.2` NGAY TRÊN CÙNG TRANG chỉ
# ra ở psm 8/13 (psm 7 trả về rỗng), nên bản chỉ-psm-7 làm mất hẳn một nhãn hình
# và kéo theo mất luôn anchor của cả một hình. Cùng bài học với ô số MỤC LỤC
# (D-43): không scale/psm nào thắng ở mọi ô, phải thử rồi để regex phán xử.
OCR_VARIANTS = ((2, 7), (2, 8), (2, 13), (3, 7), (3, 8))

# `Hình 1.2`, `Hình 25.5`. Chữ "i" nhận MỌI biến thể dấu vì OCR trên pill đảo màu
# đọc ra đủ kiểu (đo được: `Hỉnh`, `Hình`, `Hinh`) — dấu của chữ "Hình" không mang
# thông tin nào, còn HAI CON SỐ thì không được đoán: chúng phải đọc ra thật.
FIGURE_LABEL = re.compile(r"H[iìíỉĩị]nh\s*(\d{1,2})\s*[.,]\s*(\d{1,2})")


REF_WIDTH = 1094          # chiều rộng trang mà mọi ngưỡng px trên đây đo trên đó


def bounds_for_width(width: int) -> dict:
    """Ngưỡng kích thước pill + kernel CLOSE, tỉ lệ theo chiều rộng trang."""
    k = max(1.0, width / float(REF_WIDTH))
    return {
        "k": round(k, 4),
        "min_w": max(1, round(MIN_W * k)), "max_w": max(2, round(MAX_W * k)),
        "min_h": max(1, round(MIN_H * k)), "max_h": max(2, round(MAX_H * k)),
        # Kernel phải là số LẺ (morphology đối xứng) và >= 3 — k=0/1 bị loại theo
        # cấu trúc: không close thì `closed == mask`, `hole_frac = 0` và mọi pill
        # bị loại (xem chú thích CLOSE_KERNELS).
        #
        # Làm tròn rồi ÉP LẺ bằng `| 1`, không phải `2*round(n/2)+1`: bản sau làm
        # tròn 1,5 lên 2 (banker's rounding của Python) nên **k=3 biến thành 5
        # ngay ở scale 1×** — tức mất đúng cái kernel duy nhất đọc được
        # `Hình 2.3` (D-51). Ở 1094 px bộ này phải trả lại y nguyên (3, 5, 9).
        "close_kernels": tuple(sorted({max(3, int(round(kk * k)) | 1)
                                       for kk in CLOSE_KERNELS})),
    }


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix = max(0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    if inter == 0:
        return 0.0
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / float(union) if union else 0.0


def _dedupe_boxes(boxes: list[tuple[int, int, int, int]],
                  iou_max: float = 0.5) -> list[tuple[int, int, int, int]]:
    """Bỏ bbox trùng giữa các kernel. Giữ cái ĐẾN TRƯỚC (kernel nhỏ = khít hơn)."""
    kept: list[tuple[int, int, int, int]] = []
    for box in boxes:
        if any(_iou(box, other) > iou_max for other in kept):
            continue
        kept.append(box)
    return kept


def _pill_boxes_in_mask(mask: np.ndarray, close_kernel: int,
                        bounds: dict | None = None
                        ) -> list[tuple[int, int, int, int]]:
    """Pill trong một mask nhị phân: lấp kín bbox, có lỗ (chữ), cỡ một nhãn."""
    b = bounds or bounds_for_width(REF_WIDTH)
    closed = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE, np.ones((close_kernel, close_kernel), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    out = []
    for label in range(1, count):
        x, y, width, height, area = stats[label]
        if not (b["min_w"] <= width <= b["max_w"]
                and b["min_h"] <= height <= b["max_h"]):
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


def find_pill_boxes(image_bgr: np.ndarray,
                    bounds: dict | None = None
                    ) -> list[tuple[int, int, int, int]]:
    """Các bbox `(x0, y0, x1, y1)` trông như một pill có chữ bên trong.

    Ứng viên được HỢP qua nhiều kernel CLOSE (`CLOSE_KERNELS`) rồi dedupe theo
    IoU — xem chú thích ở `CLOSE_KERNELS` để biết vì sao một kernel là không đủ.

    **Giới hạn đã đo, nói ra để không ai tưởng nó bắt hết:** pill nằm LỒNG trong
    một ô/panel đã có tông màu **cùng hệ màu với nó** thì vẫn dính vào ô đó rồi bị
    loại vì quá to, và không sửa được bằng một ngưỡng saturation nào, vì pill
    không nhất thiết đậm hơn nền: đo trên `page_010`, pill "Giao thông vận tải" có
    sat **82** còn dải tím nó nằm trên có sat **157**. Tách theo dải hue cũng đã
    thử: KHÔNG khá hơn (cùng kết quả trên `page_010`, thêm rác trên `page_011`).
    Vì vậy ba nhãn ô so sánh ("Thông tin liên lạc" / "Sản xuất" / "Giao thông vận
    tải") **vẫn chưa đọc được** — cần một thiết kế dựa trên tương phản CỤC BỘ và
    một phiên đo riêng (D-40).
    """
    b = bounds or bounds_for_width(image_bgr.shape[1])
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    solid = ((hsv[:, :, 1] >= SAT_MIN) & (hsv[:, :, 2] <= VAL_MAX)).astype(np.uint8)
    candidates: list[tuple[int, int, int, int]] = []
    for kernel in b["close_kernels"]:
        candidates.extend(_pill_boxes_in_mask(solid, kernel, b))
    return _dedupe_boxes(candidates)


def read_pill(image_bgr: np.ndarray, bbox: tuple[int, int, int, int],
              scale: int = OCR_SCALE, psm: int = 7) -> str:
    """OCR một pill trên bản ĐẢO MÀU (chữ trắng -> chữ tối). Mặc định `--psm 7`."""
    x0, y0, x1, y1 = bbox
    crop = image_bgr[y0:y1, x0:x1]
    if crop.size == 0:
        return ""
    if scale != 1:
        crop = cv2.resize(crop, None, fx=scale, fy=scale,
                          interpolation=cv2.INTER_CUBIC)
    raw = pytesseract.image_to_string(255 - crop, lang="vie",
                                      config=f"--psm {psm}")
    return " ".join(clean_vietnamese_text(raw).split())


def read_pill_variants(image_bgr: np.ndarray,
                       bbox: tuple[int, int, int, int]) -> list[str]:
    """Chữ đọc được từ một pill qua mọi (scale, psm) trong `OCR_VARIANTS`.

    Trả về danh sách theo thứ tự thử, đã bỏ rỗng và bỏ trùng. Người gọi chọn:
    nhãn hình lấy biến thể ĐẦU TIÊN khớp `Hình N.M` (phép thử tự kiểm), còn
    `text` hiển thị lấy biến thể đầu tiên đọc được gì đó.
    """
    seen: list[str] = []
    for scale, psm in OCR_VARIANTS:
        text = read_pill(image_bgr, bbox, scale=scale, psm=psm)
        if text and text not in seen:
            seen.append(text)
    return seen


def read_pill_labels(image_bgr: np.ndarray,
                     bounds: dict | None = None) -> list[dict]:
    """Mọi pill đọc được chữ, dạng `{"text", "bbox", "figure_label"}`.

    `figure_label` là `"Hình N.M"` đã chuẩn hoá nếu pill đó là nhãn hình, ngược
    lại là `None`. Pill đọc ra rỗng bị bỏ (không bịa).
    """
    out = []
    for bbox in find_pill_boxes(image_bgr, bounds):
        variants = read_pill_variants(image_bgr, bbox)
        if not variants:
            continue
        match = next((m for m in (FIGURE_LABEL.search(v) for v in variants) if m),
                     None)
        out.append({
            "text": variants[0],
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
