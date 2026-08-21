"""Fixture chung cho test sách: một thư mục PNG giả = một quyển.

Ảnh 12×8 px trắng là đủ: mọi adapter OCR trong các test này đều được bơm giả
(dependency injection), nên nội dung pixel không quan trọng — cái quan trọng là
**tên file** (số trang nguồn) và việc `PngFolderPageSource` đọc được nó thật.
"""
import cv2
import numpy as np
import pytest

from src.etl.page_source import PngFolderPageSource


def make_png_book(directory, page_numbers, name="SGK_KHTN_6_KNTT"):
    """Tạo thư mục `page_NNN.png` rồi trả về `PngFolderPageSource`."""
    folder = directory / name
    folder.mkdir(parents=True, exist_ok=True)
    for number in page_numbers:
        image = np.full((8, 12, 3), 255, dtype=np.uint8)
        # Pixel (0,0) MÃ HOÁ SỐ TRANG NGUỒN. Hai tác dụng: mỗi trang có bytes
        # khác nhau (checkpoint per-page mới có nghĩa), và adapter OCR giả có thể
        # biết nó đang xem trang nào **mà không cần đếm lượt gọi** — nếu đếm lượt
        # gọi thì mọi test sẽ lệch khi production bỏ qua một trang (ví dụ không
        # dò banner trên trang MỤC LỤC).
        image[0, 0] = (number % 250, 1, 2)
        cv2.imwrite(str(folder / f"page_{number:03d}.png"), image)
    return PngFolderPageSource(folder)


def page_of(image) -> int:
    """Số trang nguồn được mã hoá trong pixel (0,0) bởi `make_png_book`."""
    return int(image[0, 0][0])


@pytest.fixture
def png_book(tmp_path):
    def build(page_numbers=range(1, 9), name="SGK_KHTN_6_KNTT"):
        return make_png_book(tmp_path, list(page_numbers), name)
    return build
