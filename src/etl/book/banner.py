"""Đọc nhãn "Bài N" trên huy hiệu ở đỉnh trang mở Bài.

## Cái sai của bản trước (đã đo, không suy đoán)

Bản trước lấy dải 22% đỉnh trang, `threshold(gray, 200)` rồi OCR `--psm 6` cả
dải. Kết quả trên sách 6: **3 banner / 196 trang**. Hai lý do, cả hai là lỗi
thiết kế chứ không phải tham số:

1. **Nhầm về vật thể.** Nhãn KHÔNG phải chữ trắng trên nền màu (giả định của bản
   cũ): đo trên `page_008` thì huy hiệu là một **đĩa TRẮNG viền tím, chữ "Bài 1"
   in màu TÍM trên nền trắng**. Chữ tối trên nền sáng — đúng thứ Tesseract thích.
2. **OCR sai phạm vi.** Cùng dải đó chứa banner CHƯƠNG in chữ trắng trên nền cam
   /tím. Sau `threshold(200)` mảng màu ấy thành một khối ĐEN to choán dải, phá
   layout analysis, nên cái nhãn vốn đọc được cũng chết theo.

## Cách làm bây giờ

Huy hiệu = **đảo trắng nằm lọt trong vùng màu**: lấy mask "có màu"
(`sat >= 60 & gray < 235`), thành phần liên thông của phần *không* màu mà không
chạm biên dải chính là lòng đĩa. OCR **chỉ riêng** crop đó.

Hai chi tiết bắt buộc, mỗi cái sửa một lần đọc hỏng đã đo:

* **Mặt nạ theo bao lồi, không theo chính thành phần.** Chữ "Bài 1" màu tím
  thuộc mask "có màu", nên nếu xoá mọi pixel ngoài thành phần thì **xoá luôn chữ**
  (đo được: kết quả rỗng trên cả 17 trang). Tô bao lồi rồi mới xoá phần ngoài.
* **Đọc cả bản crop đủ lẫn bản co vào 10%.** Viền tròn còn sót ở góc crop làm
  Tesseract đọc ra rác (`'œ®'`, `'cà |'`); co vào thì mất viền nhưng đôi khi cụt
  chữ. Không bản nào thắng ở mọi trang nên đọc cả hai rồi hợp ứng viên.

## Giới hạn đã đo — đọc trước khi tin vào nó

**Chỉ đọc được sách 6.** Bốn quyển in nhãn Bài theo HAI kiểu ngược nhau:

* sách 6: đĩa TRẮNG, chữ Bài in MÀU -> đọc được, recall ~**2/3** trên 17 Bài đầu,
  và có trang ra **hai số mâu thuẫn** (Bài 13 ra cả 13 lẫn 15);
* sách 7/8/9: khối LỤC GIÁC MÀU ĐẶC, chữ Bài in TRẮNG -> **chưa đọc được**.

Kiểu thứ hai đã thử ba cách, đo trên 8 Bài đầu của mỗi quyển: OCR cả góc trái
trên ở hai chiều màu (0/48 tính cả sách 6), và khoanh đúng khối lục giác rồi OCR
bản đảo màu theo công thức đã hiệu quả của `layout/pill.py` (**0/24**). Khối lục
giác được TÌM THẤY ổn định (241x207 px) — hỏng ở khâu đọc chữ, không phải khâu
khoanh vùng. Đây cùng một lớp bài toán chưa giải với D-40 (chữ trắng trên nền
màu lớn), cần thiết kế theo tương phản cục bộ và một phiên đo riêng.

Hệ quả phải nói ra: với sách 7/8/9 hàm này trả về tập RỖNG ở mọi trang, nên cột
"huy hiệu xác nhận" trong báo cáo G1 sẽ là 0/k. Con số 0 đó là **đo được và cố
ý hiện ra**, không phải fallback im lặng: spine của các quyển ấy đứng hoàn toàn
trên MỤC LỤC, và người đọc báo cáo phải thấy điều đó.

Vì vậy hàm trả về **một TẬP ứng viên**, không phải một con số, và `bai_spine.py`
chỉ dùng nó để **xác nhận** MỤC LỤC — không bao giờ để ghi đè (D-43).
"""
from __future__ import annotations

import re

import cv2
import numpy as np
import pytesseract

from ...config import TESSERACT_CMD

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

TOP_FRAC = 0.30           # huy hiệu đo được nằm trong 30% đỉnh trang
SAT_MIN = 60
PALE_MAX = 235
CLOSE_KERNEL = 7
MIN_W, MAX_W = 55, 520
MIN_H, MAX_H = 30, 260
MIN_FILL = 0.35           # đĩa tròn lấp ~0,785 bbox; chừa biên cho hình méo
# Huy hiệu thật gần vuông (đo: 136x136, 139x141, 111x104 -> tỉ lệ 0,99-1,07).
# Các đảo trắng khác trong dải đỉnh trang có tỉ lệ 1,43-5,40, nên chặn ở đây
# vừa bỏ được phần lớn crop rác vừa cắt chi phí OCR trên 801 trang.
MIN_ASPECT, MAX_ASPECT = 0.75, 1.35
INNER_SHAVE = 0.10

# (dùng bản crop nào, scale, psm). Bộ này CHỌN THEO ĐO ĐẠC, không phải quét mù:
# mỗi mục ở đây là biến thể duy nhất đọc được ít nhất một nhãn mà các mục khác
# bỏ sót (full/1/6 đọc phần lớn; inner/1/8 và inner/1/13 cứu Bài 10, 11, 13, 15;
# full/3/6 cứu Bài 8; full/2/7 cứu Bài 2).
VARIANTS = (("full", 1, 6), ("full", 2, 7), ("full", 3, 6),
            ("inner", 1, 6), ("inner", 1, 8), ("inner", 1, 13))

# Chữ số 1 hay bị đọc thành I/l/|/ì trên nền cong của huy hiệu.
_BAI_LABEL = re.compile(r"B[àaáâ]i\s*([0-9IlL|ì]{1,2})(?![0-9IlL|ì])",
                        re.IGNORECASE)
_ONE_LIKE = str.maketrans({"I": "1", "l": "1", "L": "1", "|": "1", "ì": "1"})


def badge_crops(band_bgr: np.ndarray) -> list:
    """Crop của từng huy hiệu (đảo trắng lọt trong vùng màu), đã xoá nền ngoài."""
    hsv = cv2.cvtColor(band_bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(band_bgr, cv2.COLOR_BGR2GRAY)
    coloured = ((hsv[:, :, 1] >= SAT_MIN) & (gray < PALE_MAX)).astype(np.uint8)
    coloured = cv2.morphologyEx(
        coloured, cv2.MORPH_CLOSE, np.ones((CLOSE_KERNEL, CLOSE_KERNEL), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        (1 - coloured).astype(np.uint8), connectivity=8)
    height, width = band_bgr.shape[:2]
    crops = []
    for label in range(1, count):
        x, y, w, h, area = stats[label]
        if not (MIN_W <= w <= MAX_W and MIN_H <= h <= MAX_H):
            continue
        if area < MIN_FILL * w * h:
            continue
        if not (MIN_ASPECT <= w / float(h) <= MAX_ASPECT):
            continue
        if x == 0 or y == 0 or x + w >= width or y + h >= height:
            continue          # chạm biên dải -> là nền giấy, không phải đảo
        component = (labels[y:y + h, x:x + w] == label).astype(np.uint8)
        contours, _ = cv2.findContours(component, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        hull = cv2.convexHull(np.vstack(contours))
        solid = np.zeros_like(component)
        cv2.fillPoly(solid, [hull], 1)
        crop = band_bgr[y:y + h, x:x + w].copy()
        crop[solid == 0] = 255
        crops.append(crop)
    return crops


def _read_label(crop: np.ndarray) -> set:
    height, width = crop.shape[:2]
    shave = int(INNER_SHAVE * min(height, width))
    views = {"full": crop, "inner": crop[shave:height - shave, shave:width - shave]}
    found = set()
    for which, scale, psm in VARIANTS:
        view = views[which]
        if view.size == 0:
            continue
        image = view if scale == 1 else cv2.resize(
            view, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        text = " ".join(pytesseract.image_to_string(
            image, lang="vie", config=f"--psm {psm}").split())
        match = _BAI_LABEL.search(text)
        if not match:
            continue
        token = match.group(1).translate(_ONE_LIKE)
        if token.isdigit():
            found.add(int(token))
    return found


def detect_bai_banner(image_bgr: np.ndarray, top_frac: float = TOP_FRAC) -> frozenset:
    """TẬP số Bài đọc được trên huy hiệu ở đỉnh trang (rỗng nếu không thấy).

    Trả về tập chứ không phải một số: đo được là cùng một huy hiệu có thể đọc ra
    hai giá trị mâu thuẫn, và giấu chuyện đó sau một `int` là đúng kiểu fallback
    im lặng mà repo cấm. Người gọi (`bai_spine`) quyết định phải làm gì với nó.
    """
    height = image_bgr.shape[0]
    band = image_bgr[0:int(height * top_frac), :]
    if band.size == 0:
        return frozenset()
    found: set = set()
    for crop in badge_crops(band):
        found |= _read_label(crop)
    return frozenset(found)
