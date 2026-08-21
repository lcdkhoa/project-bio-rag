"""Vệt nhiễu OCR trên ảnh không được nối hai cột bảng thành một dòng.

Defect đã đo trên `SGK_KHTN_9_KNTT/page_009` (D-46): Tesseract quét ra hai "từ"
nhiễu ngay trên tấm ảnh bát sứ — `'`.'` cao **62 px** và `'_'` cao **54 px**,
trong khi chữ thật cùng dòng cao 18–24 px. Hai vệt ấy nằm vừa trong khe cột nên
bước tách theo `gutter_gap` không cắt, và cả dòng thành `[126, 260, 492, 322]`
vắt từ ô ảnh sang cột chữ. Hộp dòng đó phủ **51,6%** ô ảnh -> ô ảnh bị
`_filter_text_visual_regions` bỏ vì tưởng là khối chữ -> `Hình 1.7` mất vùng.

Phân biệt bằng chiều cao so với TRUNG VỊ của chính dòng đó, không phải ngưỡng
tuyệt đối và **không** phải confidence (D-38: lọc theo conf xoá cả chữ thật).
"""
from src.etl.image_processor import ImageProcessor

drop = ImageProcessor._drop_smear_words


def word(x0, y0, x1, y1, text="w"):
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "word": text}


def test_drops_the_two_smears_measured_on_page_009():
    words = [word(126, 260, 163, 322, "`."),     # vệt, cao 62
             word(198, 264, 276, 318, "_"),      # vệt, cao 54
             word(301, 291, 342, 312, "hiện"),   # chữ thật, cao 21
             word(357, 292, 395, 312, "một"),
             word(410, 291, 430, 309, "số"),
             word(444, 291, 492, 314, "phản")]
    kept = drop(words)
    assert [w["word"] for w in kept] == ["hiện", "một", "số", "phản"]


def test_a_heading_line_of_uniformly_tall_words_is_untouched():
    """Tự hiệu chỉnh theo trung vị: dòng tiêu đề chữ to đều không bị đụng."""
    words = [word(100, 100, 200, 150, "MỘT"),
             word(210, 100, 320, 150, "SỐ"),
             word(330, 100, 460, 150, "HOÁ")]
    assert drop(words) == words


def test_a_short_line_is_left_alone():
    """Dòng dưới 3 từ thì trung vị không đáng tin — không cắt gì."""
    words = [word(126, 260, 163, 322, "`."), word(301, 291, 342, 312, "hiện")]
    assert drop(words) == words


def test_never_returns_an_empty_line():
    """Nếu luật loại sạch thì giữ nguyên: thà thừa còn hơn mất hết hộp chữ."""
    words = [word(0, 0, 10, 100), word(0, 0, 10, 100), word(0, 0, 10, 100)]
    assert drop(words) == words


def test_normal_body_text_keeps_every_word():
    words = [word(100, 100, 140, 121), word(150, 100, 190, 122),
             word(200, 100, 250, 120), word(260, 100, 300, 123)]
    assert drop(words) == words
