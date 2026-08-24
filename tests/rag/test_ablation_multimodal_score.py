# -*- coding: utf-8 -*-
"""Chấm điểm bảng cấu hình 2 — hai cột dễ hiểu sai nhất được khoá ở đây.

1. `delta_R` là recall TRANG: kênh hình chỉ được tính là "thêm" khi nó mang trang
   vàng vào ngữ cảnh mà kênh text **bỏ sót**. Trang vàng đã có sẵn từ text thì
   thêm hình không phải là thêm recall — đo được nó là 0 là một kết quả thật,
   không phải bug.
2. `cov` là độ phủ token đáp án. Ngữ cảnh đa phương thức là **tập cha** của ngữ
   cảnh text, nên `cov_mm >= cov_text` luôn đúng; cột đáng đọc là **có bao nhiêu
   câu mà nó tăng thật**. Nếu bảng in ra `cov_mm < cov_text` thì có nhánh ẩn.
3. Thiếu câu trong đệm phải **raise**, không được chấm trên phần đã có — một
   bảng thấp đi âm thầm là loại lỗi tệ nhất ở đây.
"""
import pytest

from src.test.ablation_multimodal import score


def _row(book="SGK_KHTN_6_KNTT", page=10, q="câu hỏi?"):
    return {"question": q, "source_book": book, "source_page": page,
            "ground_truth": "đáp án"}


def _rec(text_pages, context_pages, cov_text=0.5, cov_mm=0.5):
    return {
        "image_only_route": False,
        "text_pages": [list(p) for p in text_pages],
        "image_pages_retrieved": [list(p) for p in context_pages],
        "context_pages": [list(p) for p in context_pages],
        "figure_labels": ["Hình 1.1"] * len(context_pages),
        "ctx_text_only": 100, "ctx_multimodal": 100 + 40 * len(context_pages),
        "cov_text": cov_text, "cov_mm": cov_mm, "n_informative": 4,
    }


GOLD = ("SGK_KHTN_6_KNTT", 10)
KHAC = ("SGK_KHTN_6_KNTT", 77)


def test_figure_rescues_a_page_the_text_channel_missed():
    row = _row()
    data = {row["question"]: _rec([KHAC], [GOLD])}

    got = score([row], data, {GOLD})

    assert got["text_only_R"] == 0.0
    assert got["multimodal_R"] == 1.0
    assert got["delta_R"] == 1.0


def test_figure_on_a_page_text_already_found_adds_no_recall():
    row = _row()
    data = {row["question"]: _rec([GOLD], [GOLD])}

    got = score([row], data, {GOLD})

    assert got["text_only_R"] == got["multimodal_R"] == 1.0
    assert got["delta_R"] == 0.0
    assert got["hinh_dung_trang_vang"] == 1


def test_figures_from_other_pages_are_counted_as_noise():
    row = _row()
    data = {row["question"]: _rec([GOLD], [KHAC, KHAC])}

    got = score([row], data, {GOLD})

    assert got["hinh_trang_khac"] == 2
    assert got["hinh_dung_trang_vang"] == 0


def test_coverage_gain_counts_only_questions_where_it_actually_rose():
    rows = [_row(q="a"), _row(q="b")]
    data = {"a": _rec([GOLD], [GOLD], cov_text=0.5, cov_mm=0.75),
            "b": _rec([GOLD], [GOLD], cov_text=0.5, cov_mm=0.5)}

    got = score(rows, data, {GOLD})

    assert got["cov_text_TB"] == 0.5
    assert got["cov_mm_TB"] == 0.625
    assert got["so_cau_cov_tang"] == 1


def test_coverage_going_down_is_reported_not_hidden():
    """Ngữ cảnh mm là tập cha nên KHÔNG thể giảm — nếu giảm thì có nhánh ẩn."""
    rows = [_row(q="a")]
    data = {"a": _rec([GOLD], [GOLD], cov_text=0.8, cov_mm=0.3)}

    got = score(rows, data, {GOLD})

    assert got["so_cau_cov_giam"] == 1


def test_missing_question_raises_instead_of_scoring_a_short_set():
    with pytest.raises(RuntimeError, match="Thiếu kết quả truy xuất"):
        score([_row()], {}, set())
