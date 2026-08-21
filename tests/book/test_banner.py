"""Test đọc huy hiệu "Bài N" ở đỉnh trang.

Fixture dựng đúng thứ đã ĐO trên trang thật: một dải màu ở đỉnh trang, trong đó
có một **đĩa TRẮNG** và chữ "Bài N" in MÀU TỐI trên đĩa. Bản banner cũ giả định
ngược lại (chữ trắng trên nền màu) nên fixture cũ cũng sai theo, và test xanh
trong khi trang thật đọc được 3/196.
"""
import cv2
import numpy as np

from src.etl.book.banner import detect_bai_banner

_H, _W = 1000, 700
_PURPLE = (150, 40, 160)


def _blank():
    return np.full((_H, _W, 3), 255, np.uint8)


def _with_badge(text="Bai 6", top=20, colour=_PURPLE):
    """Dải màu ở đỉnh + đĩa trắng chứa chữ tối (đúng cách KNTT in nhãn Bài)."""
    img = _blank()
    cv2.rectangle(img, (0, top), (_W - 40, top + 220), colour, -1)
    cv2.circle(img, (180, top + 110), 105, (255, 255, 255), -1)
    (width, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 3)
    cv2.putText(img, text, (180 - width // 2, top + 125),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (120, 30, 130), 3, cv2.LINE_AA)
    return img


def test_reads_the_bai_number_from_the_badge():
    assert 6 in detect_bai_banner(_with_badge("Bai 6"))


def test_reads_a_two_digit_bai_number():
    assert 42 in detect_bai_banner(_with_badge("Bai 42"))


def test_returns_an_empty_set_when_there_is_no_badge():
    # Trích dẫn trong thân bài ("... xem Bài 6 ...") không được coi là mở Bài:
    # cái làm nên trang mở Bài là huy hiệu, không phải mấy chữ đó.
    img = _blank()
    cv2.putText(img, "Bai 6", (40, 115), cv2.FONT_HERSHEY_SIMPLEX, 1.6,
                (0, 0, 0), 4, cv2.LINE_AA)
    assert detect_bai_banner(img) == frozenset()


def test_returns_an_empty_set_for_a_badge_without_a_bai_label():
    assert detect_bai_banner(_with_badge("EM CO BIET")) == frozenset()


def test_ignores_a_badge_below_the_top_band():
    img = _blank()
    cv2.rectangle(img, (0, 700), (_W - 40, 900), _PURPLE, -1)
    cv2.circle(img, (150, 800), 78, (255, 255, 255), -1)
    cv2.putText(img, "Bai 6", (95, 815), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                (120, 30, 130), 3, cv2.LINE_AA)
    assert detect_bai_banner(img) == frozenset()


def test_returns_an_empty_set_on_a_blank_page():
    assert detect_bai_banner(_blank()) == frozenset()


def test_returns_every_candidate_it_read_rather_than_picking_one():
    """Trả về TẬP, không phải một số: đo được cùng huy hiệu ra hai giá trị mâu
    thuẫn, và giấu chuyện đó sau một `int` là fallback im lặng (nguyên tắc 5)."""
    result = detect_bai_banner(_with_badge("Bai 6"))
    assert isinstance(result, frozenset)
