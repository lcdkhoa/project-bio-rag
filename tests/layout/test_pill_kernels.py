"""Pill: HỢP ứng viên qua nhiều kernel CLOSE, không phải một kernel duy nhất.

Bài học lặp lại lần thứ tư trong repo (số trang góc D-33, ô số MỤC LỤC D-43, psm
của pill D-45, và giờ là kernel CLOSE D-51): không một tham số nào thắng ở mọi
trang, nên phải hợp ứng viên rồi để một ràng buộc TỰ KIỂM phán xử.

Neo được ĐO LẠI ngày 2026-08-23. Neo cũ (`page_017`, pill `Hình 2.3` ở
(399, 1108, 512, 1138)) đã VÔ HIỆU: người dùng thay toàn bộ `datasources/` bằng
một bản khác, và `page_017` của bản mới in `Hình 2.4` ở (543, 1283) — nội dung
trang đổi thật, không chỉ đổi số trang. Quét 40 trang/quyển × 4 quyển KNTT tìm
lại được **3 trang** còn tái hiện đúng cơ chế D-51 (k=3 ra nhãn, k>=5 mất):
6_KNTT tr.59 `Hình 16.6`, 9_KNTT tr.53 `Hình 11.1`, 9_KNTT tr.68 `Hình 14.3`.

**Cách pill bị mất ở kernel lớn KHÔNG giống trang cũ** — và đó là thông tin, nên
ghi ra: trang cũ, pill dính vào minh hoạ thành khối 505×286 rộng hơn `MAX_W` nên
bị loại vì QUÁ RỘNG; ở neo mới, pill dính xuống dòng chú thích ngay dưới nên cao
28 -> 44 px và **solidity tụt 0,828 -> 0,60** dưới `SOLIDITY_MIN` = 0,80, tức bị
loại vì KHÔNG CÒN GIỐNG HÌNH CHỮ NHẬT. Kết luận D-51 ("hợp nhiều kernel, kernel
nhỏ đứng trước") vẫn đúng; cái sai là tưởng chỉ có một cơ chế mất.

Phép thử chính chạy trên **TRANG THẬT** (`SGK_KHTN_9_KNTT/page_053`), không phải
fixture tổng hợp. Lý do: khi viết test này bằng fixture, mấy lần đầu nó đỏ vì
fixture sai chứ không vì code sai — cơ chế "có lỗ" phụ thuộc vào việc nét chữ
MẢNH ĐỦ ĐỂ CLOSE LẤP LẠI (`holes = component & ~mask`, `component` lấy từ mask đã
close), nên nét vẽ dày 4 px thì `hole_frac` bằng 0 và pill bị loại vì lý do khác
hẳn. Một fixture cứ chỉnh tới khi xanh chỉ mã hoá lại chỗ mình hiểu sai. Các hàm
thuần (IoU, dedupe) thì vẫn test bằng dữ liệu tổng hợp — chúng không có cơ chế ẩn.

Test tự bỏ qua nếu không có `datasources/`, nên không làm đỏ máy chưa có corpus.
"""
import cv2
import numpy as np
import pytest

from src.etl.layout.pill import (
    CLOSE_KERNELS,
    HOLE_FRAC_MIN,
    SOLIDITY_MIN,
    SAT_MIN,
    VAL_MAX,
    _dedupe_boxes,
    _iou,
    _pill_boxes_in_mask,
    bounds_for_width,
    find_pill_boxes,
)

# Pill `Hình 11.1`: cam, ngay trên dòng chú thích của hình.
BOOK, PAGE = "SGK_KHTN_9_KNTT", 53
PILL_BBOX = (708, 1179, 815, 1207)
# Một điểm nằm TRONG pill, dùng để lấy đúng thành phần liên thông ở kernel lớn.
INSIDE_PILL = ((PILL_BBOX[1] + PILL_BBOX[3]) // 2,
               (PILL_BBOX[0] + PILL_BBOX[2]) // 2)


@pytest.fixture(scope="module")
def real_page():
    from src.config import DATA_DIR
    from src.etl.page_source import discover_page_sources

    sources = [s for s in discover_page_sources(DATA_DIR) if s.name == BOOK]
    if not sources:
        pytest.skip(f"không có {BOOK} trong {DATA_DIR}")
    return sources[0].load(PAGE)


def _solid_mask(image_bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    return ((hsv[:, :, 1] >= SAT_MIN) & (hsv[:, :, 2] <= VAL_MAX)).astype(np.uint8)


def test_small_kernel_finds_the_pill_a_big_kernel_loses(real_page):
    """Đo được trên trang thật: k=3 tách được pill, k>=5 dính nó vào chú thích."""
    mask = _solid_mask(real_page)
    bounds = bounds_for_width(real_page.shape[1])

    small = _pill_boxes_in_mask(mask, 3, bounds)
    assert PILL_BBOX in small, f"k=3 phải tìm ra {PILL_BBOX}, có {small}"

    for kernel in (5, 7, 9):
        big = _pill_boxes_in_mask(mask, kernel, bounds)
        assert PILL_BBOX not in big, f"k={kernel} bất ngờ tìm ra pill: {big}"


def test_union_over_kernels_keeps_the_pill(real_page):
    assert PILL_BBOX in find_pill_boxes(real_page)


def test_the_merged_blob_is_rejected_for_losing_solidity(real_page):
    """Ghi lại LÝ DO pill bị mất ở kernel lớn, để nó không bị hiểu thành
    "vấn đề tương phản cục bộ" (D-40) như trước.

    Trên neo này lý do là SOLIDITY, không phải bề rộng: pill dính xuống dòng chú
    thích nên cao gấp rưỡi và không còn lấp kín bbox. Đo được: k=3 -> 107×28
    solidity 0,828 (nhận); k=9 -> 114×44 solidity 0,593 (loại).
    """
    mask = _solid_mask(real_page)
    row, col = INSIDE_PILL

    tight = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    _n, labels, stats, _c = cv2.connectedComponentsWithStats(tight, connectivity=8)
    label = labels[row, col]
    assert label != 0
    _x, _y, width, height, area = stats[label]
    assert area / float(width * height) >= SOLIDITY_MIN, "k=3 phải còn đặc"

    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    _n, labels, stats, _c = cv2.connectedComponentsWithStats(closed, connectivity=8)
    label = labels[row, col]
    assert label != 0
    _x, _y, width9, height9, area9 = stats[label]
    assert height9 > height, "k=9 phải dính thêm dòng chú thích bên dưới"
    assert area9 / float(width9 * height9) < SOLIDITY_MIN, (
        f"khối gộp phải tụt dưới SOLIDITY_MIN={SOLIDITY_MIN}, "
        f"có {area9 / float(width9 * height9):.3f}")


def test_close_kernels_are_ordered_small_first():
    """Dedupe giữ bbox ĐẾN TRƯỚC, nên kernel nhỏ (khít hơn) phải đứng trước."""
    assert list(CLOSE_KERNELS) == sorted(CLOSE_KERNELS)
    assert CLOSE_KERNELS[0] >= 3


def test_zero_kernel_is_structurally_useless():
    """k=0 -> `closed == mask` -> `holes` luôn rỗng -> `hole_frac = 0`.

    Không phải chuyện đo: với k=0 MỌI pill đều bị loại, nên 0 không được có mặt
    trong `CLOSE_KERNELS`.
    """
    assert 0 not in CLOSE_KERNELS
    assert HOLE_FRAC_MIN > 0


def test_dedupe_keeps_first_and_drops_overlaps():
    a = (10, 10, 110, 40)
    near = (12, 11, 112, 41)      # cùng pill, kernel khác -> bỏ
    far = (300, 300, 400, 330)    # pill khác -> giữ
    assert _dedupe_boxes([a, near, far]) == [a, far]
    assert _iou(a, near) > 0.5
    assert _iou(a, far) == 0.0
