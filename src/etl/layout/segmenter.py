"""Classical-CV page layout segmentation: coloured boxes + main text column.

Hộp màu (sidebar / info-box / khung câu hỏi) được tìm bằng mask HSV rồi lọc để
chỉ giữ vùng có **nền phẳng, thật sự có tông màu**. Đó là thứ phân biệt một hộp
màu thật với một tấm ảnh nằm trên nền trắng (phẳng nhưng không có tông).

## Vì sao bản này khác bản M1 (đo trên trang thật, spec §1.4)

Bản M1 tìm được **2,30 vùng/trang** — quá thấp — và trên trang chuẩn
`SGK_KHTN_6_KNTT/page_010.png`, nơi mắt thường đếm được ≥4 hộp màu, nó tìm được
**0 hộp**. Đo từng bước cho ra đúng hai nguyên nhân, và cả hai đều là lỗi thiết
kế chứ không phải tham số cần tinh chỉnh:

1. **Gộp rồi loại.** `morphologyEx(CLOSE, 25)` trên một mask duy nhất dán khung
   câu hỏi vàng, panel màu đào và mọi ảnh bên trong thành MỘT blob 975×672
   (39% trang). ROI đó chứa ảnh nên độ phẳng chỉ 0,06 -> bị loại -> **mất sạch
   cả 4 hộp**. Kernel nhỏ hơn cũng không cứu (đo ở k=3/7/15/25 đều một blob).
   -> Nay: close **nhỏ** (chỉ hàn răng cưa) + khi một thành phần bị loại thì
   **tách nó theo dải màu (hue)** và thử lại các phần. Panel màu đào và khung
   vàng khác tông nên tách ra được mà không cần biết trước palette của nhà xuất
   bản (không hardcode màu).
2. **Đo độ phẳng trên bbox thay vì trên chính vùng đó.** Sidebar tím ở
   `page_010` có độ phẳng 0,42 < ngưỡng 0,45 — trượt vì bbox của nó bao cả khe
   trắng và cái đuôi bong bóng thoại. -> Nay độ phẳng và tông màu được đo trên
   **đúng các pixel thuộc thành phần liên thông**, không phải cả hình chữ nhật.

Hai luật giữ cho recall cao mà không sinh chunk trùng:

* Một "hộp" to hơn `max_area_frac` trang thì không phải hộp mà là nền trang ->
  loại, để các hộp con bên trong được nhận.
* Hộp nằm ≥ `contained_ratio` bên trong một hộp khác đã nhận thì bị **bỏ** (giữ
  hộp ngoài cùng). Nhờ vậy text của hộp con vẫn được OCR — nó nằm trong vùng của
  hộp ngoài — mà không bị đếm hai lần thành hai chunk.
"""
import cv2
import numpy as np
from .regions import Region, RegionType, BBox
from ...config import LAYOUT_BOX_MIN_SATURATION, LAYOUT_BOX_MIN_AREA_FRAC

# Per-variant layout params. Chỉ còn KNTT trên corpus thật; giữ `variant` để một
# nguồn khác (PDF upload) vẫn đi qua được cùng một đường.
_BOX_DEFAULTS = {
    "min_sat": LAYOUT_BOX_MIN_SATURATION,       # HSV saturation của nền màu đậm
    "min_area_frac": LAYOUT_BOX_MIN_AREA_FRAC,  # diện tích tối thiểu / trang
    "max_area_frac": 0.85,      # to hơn thế thì là nền trang, không phải hộp
    "close_kernel": 5,          # chỉ hàn răng cưa/khe 1-2 px, KHÔNG dán hộp lại
    "pale_sat_min": 12,         # sat tối thiểu cho nền tông NHẠT
    "pale_val_min": 200,        # độ sáng tối thiểu của tông nhạt (loại chữ đen)
    "uniform_min": 0.45,        # tỉ lệ pixel gần màu trung vị CỦA VÙNG
    "tint_white_max": 232,      # trung vị sáng cỡ này (mọi kênh) => trắng => loại
    "tint_min_spread": 10,      # spread max-min của trung vị => có tông thật
    "uniform_tol": 40,          # khoảng cách L1 tới trung vị vẫn tính là "nền"
    "min_width_frac": 0.08,     # hộp hẹp hơn thế là icon/pill, không phải hộp
    "min_height_frac": 0.05,
    "contained_ratio": 0.90,    # nằm trong hộp khác bao nhiêu thì bị bỏ
    "hue_bin": 10,              # độ rộng bin hue khi tách một thành phần
    "hue_split_depth": 1,       # số lần tách theo hue (1 = một cấp lồng)
}
_HUE_MAX = 180          # OpenCV: hue 0..179


def _params_for(variant: str = "") -> dict:
    """Tham số hộp màu. Ba biến thể cd/ctst/kntt trước đây đều trỏ về CÙNG một
    bộ số (`_BOX_DEFAULTS`) — một lớp gián tiếp không mang thông tin, và corpus
    giờ chỉ còn KNTT. Giữ tham số `variant` để call site không phải đổi, nhưng
    nó không còn chọn gì; muốn có bộ số riêng cho nhà xuất bản khác thì phải ĐO
    rồi thêm tường minh, chứ không phải sao chép defaults.
    """
    return dict(_BOX_DEFAULTS)


def _candidate_mask(image: np.ndarray, p: dict) -> np.ndarray:
    """Pixel thuộc một hộp màu: bão hoà mạnh HOẶC tông nhạt nhưng sáng."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    s, v = hsv[:, :, 1], hsv[:, :, 2]
    strong = s >= p["min_sat"]
    pale = (s >= p["pale_sat_min"]) & (s < p["min_sat"]) & (v >= p["pale_val_min"])
    return ((strong | pale).astype(np.uint8)) * 255


def _is_box_pixels(image: np.ndarray, pixel_mask: np.ndarray, p: dict) -> bool:
    """`pixel_mask` (bool, cùng shape trang) có trông như nền một hộp màu không?

    Đo trên ĐÚNG các pixel của vùng, không phải cả bbox: một hộp có nền PHẲNG
    (phần lớn pixel gần một màu) và màu đó là một TÔNG thật (không trắng/xám).
    Ảnh chụp thì có tông nhưng không phẳng; hình vẽ trên nền trắng thì phẳng
    nhưng trung vị là trắng. Đòi cả hai nên loại được cả hai.
    """
    pixels = image[pixel_mask]
    if pixels.size == 0:
        return False
    flat = pixels.astype(np.int16)
    med = np.median(flat, axis=0)
    uniform = float((np.abs(flat - med).sum(axis=1) < p["uniform_tol"]).mean())
    if uniform < p["uniform_min"]:
        return False
    near_white = int(med.min()) >= p["tint_white_max"]
    spread = int(med.max() - med.min())
    return (not near_white) and spread >= p["tint_min_spread"]


def _size_ok(bbox: BBox, image_h: int, image_w: int, p: dict) -> bool:
    x0, y0, x1, y1 = bbox
    width, height = x1 - x0, y1 - y0
    area = width * height
    page_area = image_h * image_w
    return (area >= p["min_area_frac"] * page_area
            and area <= p["max_area_frac"] * page_area
            and width > p["min_width_frac"] * image_w
            and height > p["min_height_frac"] * image_h)


def _components(mask: np.ndarray, p: dict):
    """Các thành phần liên thông của mask, sau một close NHỎ. -> [(bbox, mask)]"""
    kernel = np.ones((p["close_kernel"], p["close_kernel"]), np.uint8)
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        (closed > 0).astype(np.uint8), connectivity=8)
    out = []
    for label in range(1, count):
        x, y, width, height, _area = stats[label]
        out.append(((x, y, x + width, y + height), labels == label))
    return out


def _hue_bands(hue_values: np.ndarray, p: dict) -> list:
    """Các dải hue có mặt trong vùng, gộp bin liền nhau (vòng tròn qua 0).

    Không hardcode màu của nhà xuất bản: dải được suy ra từ chính pixel của
    vùng, nên một quyển đổi palette vẫn chạy.
    """
    bin_width = p["hue_bin"]
    n_bins = int(np.ceil(_HUE_MAX / bin_width))
    counts = np.bincount(np.minimum(hue_values // bin_width, n_bins - 1),
                         minlength=n_bins)
    # bin phải chiếm ít nhất 5% pixel của vùng mới coi là một tông riêng, để
    # viền/răng cưa không sinh ra hàng chục dải rác.
    occupied = counts >= max(1, int(0.05 * hue_values.size))
    if not occupied.any():
        return []
    bands, start = [], None
    # duyệt 2 vòng để gộp được dải bắc qua mốc 0 (đỏ/hồng)
    for index in range(2 * n_bins):
        bin_index = index % n_bins
        if occupied[bin_index] and start is None:
            start = index
        elif not occupied[bin_index] and start is not None:
            bands.append((start % n_bins, (index - 1) % n_bins))
            start = None
            if index >= n_bins:
                break
    if start is not None:
        bands.append((start % n_bins, (2 * n_bins - 1) % n_bins))
    seen, unique = set(), []
    for lo, hi in bands:
        if (lo, hi) not in seen:
            seen.add((lo, hi))
            unique.append((lo * bin_width,
                           min(_HUE_MAX, (hi + 1) * bin_width) - 1))
    return unique


def _hue_in_band(hue: np.ndarray, lo: int, hi: int) -> np.ndarray:
    if lo <= hi:
        return (hue >= lo) & (hue <= hi)
    return (hue >= lo) | (hue <= hi)        # dải bắc qua mốc 0


def _collect_boxes(image: np.ndarray, mask: np.ndarray, hue: np.ndarray,
                   p: dict, depth: int) -> list:
    """Hộp tìm được trong `mask`; thành phần bị loại thì tách theo hue rồi thử lại."""
    height, width = image.shape[:2]
    boxes = []
    for bbox, pixel_mask in _components(mask, p):
        if not _size_ok(bbox, height, width, p):
            continue
        if _is_box_pixels(image, pixel_mask, p):
            boxes.append(bbox)
            continue
        if depth >= p["hue_split_depth"]:
            continue
        # Thành phần này lẫn nhiều thứ (panel + ảnh + hộp con). Tách theo tông
        # màu rồi thử lại từng phần — đây là chỗ bản cũ mất sạch 4 hộp.
        region_hue = hue[pixel_mask]
        for lo, hi in _hue_bands(region_hue, p):
            sub = (pixel_mask & _hue_in_band(hue, lo, hi)).astype(np.uint8) * 255
            boxes.extend(_collect_boxes(image, sub, hue, p, depth + 1))
    return boxes


def _contained(inner: BBox, outer: BBox, ratio: float) -> bool:
    """`inner` nằm >= ratio diện tích của nó bên trong `outer`?"""
    ix0 = max(inner[0], outer[0])
    iy0 = max(inner[1], outer[1])
    ix1 = min(inner[2], outer[2])
    iy1 = min(inner[3], outer[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return False
    overlap = (ix1 - ix0) * (iy1 - iy0)
    area = (inner[2] - inner[0]) * (inner[3] - inner[1])
    return area > 0 and overlap / area >= ratio


def _drop_nested(boxes: list, p: dict) -> list:
    """Giữ hộp NGOÀI CÙNG: hộp con nằm trong hộp lớn hơn thì bỏ.

    Drop-only, và không mất chữ: text của hộp con vẫn được OCR vì nó nằm trong
    vùng của hộp ngoài. Mục đích là không sinh hai chunk cho cùng một đoạn chữ.
    """
    ordered = sorted(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]),
                     reverse=True)
    kept: list = []
    for bbox in ordered:
        if any(_contained(bbox, other, p["contained_ratio"]) for other in kept):
            continue
        kept.append(bbox)
    return kept


def _colored_boxes(image: np.ndarray, p: dict) -> list[BBox]:
    hue = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[:, :, 0]
    boxes = _collect_boxes(image, _candidate_mask(image, p), hue, p, depth=0)
    return _drop_nested(boxes, p)


def _classify_box(bbox: BBox, image_w: int) -> RegionType:
    # Right-column tall box => sidebar; wide banner box => info_box.
    x0, y0, x1, y1 = bbox
    width_frac = (x1 - x0) / image_w
    return RegionType.INFO_BOX if width_frac > 0.5 else RegionType.SIDEBAR


def segment_page(image: np.ndarray, variant: str) -> list[Region]:
    h, w = image.shape[:2]
    boxes = _colored_boxes(image, _params_for(variant))
    regions: list[Region] = []
    # Main body = the whole page minus box columns; first in reading order.
    regions.append(Region(RegionType.BODY, (0, 0, w, h), reading_order=0,
                          meta={"excludes": boxes}))
    for i, b in enumerate(sorted(boxes, key=lambda z: (z[1], z[0]))):
        regions.append(Region(_classify_box(b, w), b, reading_order=i + 1, meta={}))
    return regions
