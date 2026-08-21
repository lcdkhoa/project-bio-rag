"""Nhãn hình phải là SỐ HIỆU hình, không phải tiêu đề ô đứng gần đó.

Defect đã đo (D-41): một crop có sẵn `Hình 21.3` — pill anchor ĐỌC ĐÚNG nhãn đó —
vẫn bị gán `figure_label='quan sát'`, vì `_extract_figure_label` duyệt một danh
sách pattern có thứ tự cố định trong đó "Quan sát" đứng TRƯỚC `Hình N.M` và trả
về match đầu tiên. Chữ "Quan sát" xuất hiện gần như mọi trang SGK, nên lỗi này
không hiếm — nó ăn nhãn của rất nhiều hình.
"""
from src.etl.image_processor import ImageProcessor

_extract = ImageProcessor._extract_figure_label
_processor = ImageProcessor.__new__(ImageProcessor)   # không cần model nào


def label(context, anchor=""):
    return _extract(_processor, context, "", anchor_label=anchor)


def test_figure_number_beats_a_box_title_in_the_same_context():
    assert label("Quan sát Hình 21.3 và cho biết ...") == "Hình 21.3"


def test_anchor_label_wins_over_everything_in_the_surrounding_text():
    """Nhãn anchor đến từ pixel của chính cái pill, không phải chữ loanh quanh."""
    assert label("Em có biết ... Quan sát ...",
                 anchor="Hình 21.3 Sơ đồ cấu tạo") == "Hình 21.3"


def test_anchor_label_is_trimmed_to_the_identifier_not_the_whole_caption():
    assert label("", anchor="Hình 1.2 Một số phương tiện mà con người sử dụng") \
        == "Hình 1.2"


def test_a_table_number_is_also_a_real_identifier():
    assert label("Quan sát Bảng 3.1 rồi trả lời") == "Bảng 3.1"


def test_a_box_title_is_still_used_when_there_is_no_figure_number():
    assert label("Em có biết rằng nước chiếm ...") == "Em có biết"


def test_nothing_matches_gives_an_empty_label_not_a_guess():
    assert label("Các vật quanh ta đều chuyển động") == ""


def test_a_non_figure_anchor_does_not_hijack_the_label():
    """Anchor rác (không phải số hiệu) phải bị bỏ qua, rơi về text quanh crop."""
    assert label("Em có biết ...", anchor="Thông tin liên lạc") == "Em có biết"
