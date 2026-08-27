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
