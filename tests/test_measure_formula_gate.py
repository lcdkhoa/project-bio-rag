# -*- coding: utf-8 -*-
"""Khoá lại số đo D-144 trên gold set THẬT (`document/review/ocr_gold/`, đã
commit). Không phải test đơn vị thuần — nếu ai đó sửa `formula_tokens` hay
`is_formula_suspect` mà đổi con số đã ghi vào decision log, test này báo động
thay vì để số cũ lặng lẽ sai.
"""
from src.test.measure_formula_gate import load_labeled_items, score_gate


def test_gold_set_still_has_89_labeled_items_across_3_publishers():
    rows = load_labeled_items()
    assert len(rows) == 89
    nxb = {it.get("quyen", "").split("_")[-1] for it, _label, _text in rows}
    assert nxb == {"KNTT", "CTST", "CD"}


def test_gate_recall_is_perfect_and_precision_matches_d144():
    rows = load_labeled_items()
    st = score_gate(rows)
    assert st["fn"] == 0
    assert st["rec"] == 1.0
    assert (st["tp"], st["fp"]) == (45, 7)
