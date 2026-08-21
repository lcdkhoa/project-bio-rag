"""Pill = chữ TRẮNG trên nền MÀU ĐẶC. Test dựng pill tổng hợp, không cần trang thật.

Điều quan trọng nhất bị khoá ở đây: `read_pill_labels` **không bịa** — pill đọc
ra rác thì `figure_label` phải là None, và một khối màu đặc không có chữ thì
không được coi là pill.
"""
import cv2
import numpy as np

from src.etl.layout.pill import (FIGURE_LABEL, find_pill_boxes,
                                 read_pill_labels)


def _page_with_pill(text="Hinh 1.2", fill=(29, 148, 247)):
    """Trang trắng + một pill màu có chữ TRẮNG (đúng kiểu nhãn hình của KNTT).

    Chữ trong fixture viết KHÔNG DẤU vì `cv2.putText` (font Hershey) không vẽ
    được dấu tiếng Việt — nó vẽ ra "H??nh". Không sao: điều cần test là "đọc được
    chữ trắng trên nền màu rồi chuẩn hoá thành nhãn hình", và model `vie` của
    tesseract tự đọc ra "Hình"/"Hỉnh" — đúng lý do regex nhận mọi biến thể dấu
    của chữ "i".
    """
    page = np.full((400, 600, 3), 255, np.uint8)
    cv2.rectangle(page, (60, 200), (240, 235), fill, -1)
    cv2.putText(page, text, (70, 227), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (255, 255, 255), 2, cv2.LINE_AA)
    return page


def test_finds_a_pill_on_paper():
    boxes = find_pill_boxes(_page_with_pill())
    assert len(boxes) == 1
    x0, y0, x1, y1 = boxes[0]
    assert x0 <= 62 and y0 <= 202 and x1 >= 238 and y1 >= 233


def test_a_solid_block_with_no_text_is_not_a_pill():
    # Không có lỗ -> không có chữ -> không phải nhãn.
    page = np.full((400, 600, 3), 255, np.uint8)
    cv2.rectangle(page, (60, 200), (240, 235), (29, 148, 247), -1)
    assert find_pill_boxes(page) == []


def test_a_pale_tinted_box_is_not_a_pill():
    # Hộp tông nhạt (sat thấp) là info-box, việc của segmenter, không phải pill.
    page = np.full((400, 600, 3), 255, np.uint8)
    cv2.rectangle(page, (60, 200), (240, 235), (225, 243, 231), -1)
    cv2.putText(page, "Hinh 1.2", (70, 227), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (0, 0, 0), 2, cv2.LINE_AA)
    assert find_pill_boxes(page) == []


def test_reads_the_white_text_and_normalises_a_figure_label():
    items = read_pill_labels(_page_with_pill("Hinh 1.2"))
    assert len(items) == 1
    # OCR có thể trả "Hình1.2" / "Hình 1. 2" -> nhãn được CHUẨN HOÁ, không bịa
    assert items[0]["figure_label"] == "Hình 1.2"


def test_a_pill_that_is_not_a_figure_label_has_no_figure_label():
    items = read_pill_labels(_page_with_pill("San xuat"))
    assert all(item["figure_label"] is None for item in items)


def test_figure_label_regex_accepts_ocr_slips_but_not_arbitrary_numbers():
    assert FIGURE_LABEL.search("Hình1.2")
    assert FIGURE_LABEL.search("Hinh 25,5")      # dấu phẩy thay dấu chấm
    assert not FIGURE_LABEL.search("Hình 12")    # thiếu phần thứ hai
    assert not FIGURE_LABEL.search("1.2")        # không có chữ "Hình"
