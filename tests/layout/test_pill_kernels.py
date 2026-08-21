"""Pill: HỢP ứng viên qua nhiều kernel CLOSE, không phải một kernel duy nhất.

Bài học lặp lại lần thứ tư trong repo (số trang góc D-33, ô số MỤC LỤC D-43, psm
của pill D-45, và giờ là kernel CLOSE D-51): không một tham số nào thắng ở mọi
trang, nên phải hợp ứng viên rồi để một ràng buộc TỰ KIỂM phán xử.

Phép thử chính chạy trên **TRANG THẬT** (`SGK_KHTN_9_KNTT/page_017`), không phải
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
    MAX_W,
    SAT_MIN,
    VAL_MAX,
    _dedupe_boxes,
    _iou,
    _pill_boxes_in_mask,
    find_pill_boxes,
)

# Pill `Hình 2.3`: cam, nằm trong ô nền kem, sát khối màu của minh hoạ.
BOOK, PAGE = "SGK_KHTN_9_KNTT", 17
PILL_BBOX = (399, 1108, 512, 1138)


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
    """Đo được trên trang thật: k=3 tách được pill, k>=5 nối nó vào minh hoạ.

    Ở k>=5 thành phần trở thành khối 505x286 (solidity ~0,50) rộng hơn `MAX_W`
    nên bị loại — mất hẳn nhãn hình, và kéo theo mất anchor của cả một hình.
    """
    mask = _solid_mask(real_page)

    small = _pill_boxes_in_mask(mask, 3)
    assert PILL_BBOX in small, f"k=3 phải tìm ra {PILL_BBOX}, có {small}"

    for kernel in (5, 7, 9):
        big = _pill_boxes_in_mask(mask, kernel)
        assert PILL_BBOX not in big, f"k={kernel} bất ngờ tìm ra pill: {big}"


def test_union_over_kernels_keeps_the_pill(real_page):
    assert PILL_BBOX in find_pill_boxes(real_page)


def test_the_merged_blob_is_rejected_for_being_too_wide(real_page):
    """Ghi lại LÝ DO pill bị mất ở kernel lớn, để nó không bị hiểu thành
    "vấn đề tương phản cục bộ" (D-40) như trước."""
    mask = _solid_mask(real_page)
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        closed, connectivity=8)

    label = labels[1125, 455]      # một điểm bên trong pill
    assert label != 0
    x, y, width, height, area = stats[label]
    assert width > MAX_W, f"khối gộp phải rộng hơn MAX_W={MAX_W}, có {width}"
    assert area / float(width * height) < 0.6   # không còn giống hình chữ nhật


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
