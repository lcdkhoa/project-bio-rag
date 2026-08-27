# tests/layout/test_formula_merge.py
# -*- coding: utf-8 -*-
from src.etl.layout.formula_merge import (
    apply_line_merge_to_region,
    merge_formula_line,
)


class TestMergeFormulaLineChemistry:
    def test_two_broken_subscripts_matched_by_two_mineru_tokens(self):
        tesseract = "hấp thụ khí 0, và thải ra khí (0,"
        mineru = "hấp thụ khí CO₂ và thải ra khí O₂"

        out = merge_formula_line(tesseract, mineru)

        assert out.status == "applied"
        assert out.n_holes == 2
        assert out.n_applied == 2
        assert out.text == "hấp thụ khí CO₂ và thải ra khí O₂"

    def test_count_mismatch_keeps_original_line_untouched(self):
        tesseract = "hấp thụ khí 0, và thải ra khí (0,"  # 2 lỗ hổng
        mineru = "hấp thụ khí CO₂"                          # chỉ 1 token

        out = merge_formula_line(tesseract, mineru)

        assert out.status == "unmatched_count"
        assert out.n_holes == 2
        assert out.n_applied == 0
        assert out.text == tesseract

    def test_empty_mineru_reading_keeps_original(self):
        tesseract = "hấp thụ khí 0, và thải ra khí (0,"

        out = merge_formula_line(tesseract, "")

        assert out.status == "unmatched_count"
        assert out.text == tesseract

    def test_repeated_identical_hole_maps_to_different_correct_tokens(self):
        """Khoá lại bug đã bắt khi phản biện thiết kế: hai lỗ hổng CÙNG chuỗi
        (`0,`) nhưng ứng với hai công thức KHÁC NHAU không được ghép nhầm bằng
        nhau — phải ghép theo VỊ TRÍ, không theo str.replace() toàn cục."""
        tesseract = "hấp thụ khí 0, rồi hấp thụ khí 0,"
        mineru = "hấp thụ khí CO₂ rồi hấp thụ khí CH₄"

        out = merge_formula_line(tesseract, mineru)

        assert out.status == "applied"
        assert out.text == "hấp thụ khí CO₂ rồi hấp thụ khí CH₄"


class TestMergeFormulaLinePhysics:
    def test_broken_physics_equation_matched(self):
        tesseract = "công thức 1 J = 1 Ñm"
        mineru = "công thức 1 J = 1 N·m"

        out = merge_formula_line(tesseract, mineru)

        assert out.status == "applied"
        assert "N·m" in out.text


class TestMergeFormulaLineNotSuspect:
    def test_plain_prose_returns_not_suspect_unchanged(self):
        tesseract = "Tế bào là đơn vị cơ bản của sự sống"

        out = merge_formula_line(tesseract, "bất kỳ gì")

        assert out.status == "not_suspect"
        assert out.n_holes == 0
        assert out.text == tesseract


class TestApplyLineMergeToRegion:
    def test_line_found_exactly_once_is_replaced(self):
        region = "Câu 1.\nhấp thụ khí 0, và thải ra khí (0,\nCâu 2."
        original = "hấp thụ khí 0, và thải ra khí (0,"
        merged = "hấp thụ khí CO₂ và thải ra khí O₂"

        new_text, status = apply_line_merge_to_region(region, original, merged)

        assert status == "applied"
        assert new_text == "Câu 1.\nhấp thụ khí CO₂ và thải ra khí O₂\nCâu 2."

    def test_line_not_found_fails_safe(self):
        region = "Câu 1.\ndòng khác hẳn\nCâu 2."
        original = "hấp thụ khí 0, và thải ra khí (0,"

        new_text, status = apply_line_merge_to_region(region, original, "sửa")

        assert status == "line_not_located_in_region_text"
        assert new_text == region

    def test_line_appearing_twice_fails_safe_no_guessing(self):
        region = "0, đầu đoạn.\nvăn khác.\n0, đầu đoạn."
        original = "0, đầu đoạn."

        new_text, status = apply_line_merge_to_region(region, original, "đã sửa")

        assert status == "line_ambiguous_in_region_text"
        assert new_text == region
