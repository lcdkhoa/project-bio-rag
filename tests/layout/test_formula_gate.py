# -*- coding: utf-8 -*-
"""Gate D-144: quyết định một dòng Tesseract có nghi công thức Hoá/Lý hỏng.

Các ca dưới đây khoá đúng hành vi đã ĐO trên gold set 89 ô (D-144), bao gồm cả
ca mơ hồ đã biết (`Mg, Al, Zn, Fe`) — test này không đòi gate "sửa" ca đó, chỉ
khoá lại để một thay đổi regex sau này KHÔNG âm thầm đổi hành vi đã đo.
"""
from src.etl.layout.formula_gate import is_formula_suspect


class TestBrokenChemistrySubscript:
    def test_co2_collapsed_to_comma_is_suspect(self):
        assert is_formula_suspect("hấp thụ khí 0, và thải ra khí (0,") is True

    def test_h2o_collapsed_to_comma_is_suspect(self):
        assert is_formula_suspect("cho H, O vào cốc") is True

    def test_h2so4_collapsed_is_suspect(self):
        assert is_formula_suspect("dung dịch H, SO, loãng") is True


class TestPhysicsEquation:
    def test_equation_with_equals_sign_is_suspect(self):
        assert is_formula_suspect("công thức A = Fs với F là lực") is True

    def test_broken_unit_equation_is_suspect(self):
        assert is_formula_suspect("1 J = 1 Ñm") is True


class TestNegativeControls:
    def test_plain_prose_is_not_suspect(self):
        text = ("Tế bào là đơn vị cơ bản cấu tạo nên mọi cơ thể sống, từ vi "
                "khuẩn đơn giản đến con người phức tạp.")
        assert is_formula_suspect(text) is False

    def test_plain_number_line_is_not_suspect(self):
        assert is_formula_suspect("khoảng 26,2 tỉ thùng năm 2016") is False

    def test_page_reference_is_not_suspect(self):
        assert is_formula_suspect("xem thêm ở trang 154") is False

    def test_empty_text_is_not_suspect(self):
        assert is_formula_suspect("") is False
        assert is_formula_suspect(None) is False


class TestKnownAmbiguity:
    """D-144: đo được đây là false-positive DUY NHẤT không quy được cho lỗi đo
    lường (khác 6/7 ca còn lại). Test này khoá lại hành vi ĐÃ ĐO, không phải
    hành vi mong muốn — sửa nó cần thêm ngữ cảnh ngoài một dòng (xem
    formula_gate.py)."""

    def test_element_symbol_list_in_prose_is_a_measured_false_positive(self):
        text = "M là một số kim loại như Mg, AI, Zn, Fe, ..."
        assert is_formula_suspect(text) is True
