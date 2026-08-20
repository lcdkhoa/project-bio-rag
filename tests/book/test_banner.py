import cv2
import numpy as np

from src.etl.book.banner import detect_bai_banner

_H, _W = 1000, 700


def _blank():
    return np.full((_H, _W, 3), 255, np.uint8)


def _with_banner(text="Bai 6", colour=(160, 40, 150)):
    """Coloured header banner across the top with dark text on it."""
    img = _blank()
    cv2.rectangle(img, (0, 20), (_W - 40, 150), colour, -1)
    cv2.putText(img, text, (40, 115), cv2.FONT_HERSHEY_SIMPLEX, 1.6,
                (255, 255, 255), 4, cv2.LINE_AA)
    return img


def test_reads_the_bai_number_from_a_coloured_banner():
    assert detect_bai_banner(_with_banner("Bai 6")) == 6


def test_reads_a_two_digit_bai_number():
    assert detect_bai_banner(_with_banner("Bai 42")) == 42


def test_returns_none_when_there_is_no_coloured_banner():
    # A body-text cross-reference ("... trong Bài 6 ...") must never be mistaken
    # for a chapter opener; the coloured banner is what makes it a real opener.
    img = _blank()
    cv2.putText(img, "Bai 6", (40, 115), cv2.FONT_HERSHEY_SIMPLEX, 1.6,
                (0, 0, 0), 4, cv2.LINE_AA)
    assert detect_bai_banner(img) is None


def test_returns_none_for_a_coloured_banner_without_a_bai_label():
    assert detect_bai_banner(_with_banner("EM CO BIET")) is None


def test_ignores_a_bai_label_below_the_top_band():
    img = _blank()
    cv2.rectangle(img, (0, 600), (_W - 40, 720), (160, 40, 150), -1)
    cv2.putText(img, "Bai 6", (40, 690), cv2.FONT_HERSHEY_SIMPLEX, 1.6,
                (255, 255, 255), 4, cv2.LINE_AA)
    assert detect_bai_banner(img) is None


def test_returns_none_on_a_blank_page():
    assert detect_bai_banner(_blank()) is None
