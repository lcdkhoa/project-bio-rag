# -*- coding: utf-8 -*-
"""Module dùng chung giữa bake-off và gate D-144 — test trực tiếp trên đường
dẫn PRODUCTION (`src.etl.layout.formula_signals`), không qua re-export của
`ocr_bakeoff.py` (test đó đã có sẵn ở `tests/test_ocr_bakeoff.py`).
"""
from src.etl.layout.formula_signals import (
    CO_DAU_BANG,
    CONG_THUC_HONG,
    formula_tokens,
    normalize_formula,
)


def test_normalize_formula_equates_ascii_and_unicode_subscript():
    assert normalize_formula("H2SO4") == normalize_formula("H₂SO₄")


def test_normalize_formula_does_not_repair_broken_comma():
    assert normalize_formula("CO,") != normalize_formula("CO₂")


def test_formula_tokens_reads_chemistry_and_physics():
    assert formula_tokens("hấp thụ khí O₂ và thải ra khí CO₂") == ["O₂", "CO₂"]
    assert formula_tokens("công thức A = Fs với F là lực") == ["A = Fs"]


def test_cong_thuc_hong_matches_measured_d56_patterns():
    for broken in ("CO,", "CH,", "SO,", "H, O", "0, "):
        assert CONG_THUC_HONG.search(broken), broken


def test_co_dau_bang_matches_loose_equation_shape():
    assert CO_DAU_BANG.search("A = Fs")
    assert not CO_DAU_BANG.search("không có phương trình nào ở đây cả")


def test_co_dau_bang_does_not_span_a_line_break():
    """D-154: đo trên DB local sau lượt Colab 7 — CẢ 158 nhóm chunk mang
    `formula_hybrid_status=gate_hit_no_line_located` đều do CO_DAU_BANG khớp
    XUYÊN một dấu xuống dòng (`\\s*` khớp cả `\\n`), nối rác OCR cuối một dòng
    với rác OCR đầu dòng kế tiếp (ví dụ thật từ `SGK_KHTN_6_KNTT` tr.8:
    `'\\n” Sq=\\n3) b)\\n'`) — không ca nào trong 158 nhóm là công thức thật
    trên một dòng. CONG_THUC_HONG (tín hiệu D-56/D-73 gốc) không dính lỗi này
    (0/158). Vì `_maybe_apply_formula_hybrid` chỉ cắt ảnh theo TỪNG DÒNG để
    gửi MinerU, một khớp xuyên dòng không bao giờ định vị được — gate phải
    chỉ bắt khớp NẰM TRỌN trong một dòng.
    """
    rac_xuyen_dong = "” Sq=\n3) b)"
    assert not CO_DAU_BANG.search(rac_xuyen_dong), (
        "CO_DAU_BANG không được khớp xuyên qua dấu xuống dòng — đây chính là "
        "rác OCR (nhãn hình a)/b)), không phải công thức Lý thật")
    # Công thức thật nằm gọn một dòng vẫn phải khớp bình thường (không hồi quy).
    assert CO_DAU_BANG.search("A = Fs")
    assert CO_DAU_BANG.search("1 J = 1 N·m")
