# -*- coding: utf-8 -*-
"""Bake-off OCR: gom dòng, phân loại ô cần duyệt, và chấm điểm.

Ba hàm thuần được khoá ở đây vì mỗi hàm là một chỗ đã cắn trong repo này:

1. `group_lines` — gom word box của Tesseract thành DÒNG. Đơn vị công việc của
   người duyệt phải là một dòng được crop ra; sửa cả trang 2 000 ký tự là chỗ
   sinh ra tật đóng dấu cho qua (D-55: 23/24 file gold cũ trùng TỪNG CHỮ với
   output của máy).
2. `classify_line` — chỉ đưa vào phiếu những dòng CÓ bệnh, để 15 trang còn ~90 ô
   chứ không phải 900.
3. `score_answers` — và nó phải **từ chối công bố** khi phiếu có dấu hiệu đóng dấu
   cho qua, chứ không in số kèm chú thích (bài học đắt của D-89/D-90).
"""
import pytest

from src.test.ocr_bakeoff import (
    ItemKind,
    classify_line,
    group_lines,
    score_answers,
)


def _word(text, line=0, left=0, top=0, w=20, h=18, block=1, par=1, conf=90):
    return {"text": text, "block_num": block, "par_num": par, "line_num": line,
            "left": left, "top": top, "width": w, "height": h, "conf": conf}


class TestGroupLines:
    def test_words_of_one_line_become_one_line_with_union_bbox(self):
        words = [_word("hấp", left=10, top=100, w=40),
                 _word("thụ", left=60, top=100, w=40),
                 _word("khí", left=110, top=98, w=40, h=22)]

        lines = group_lines(words)

        assert len(lines) == 1
        assert lines[0]["text"] == "hấp thụ khí"
        assert lines[0]["bbox"] == (10, 98, 150, 120)

    def test_different_line_numbers_stay_separate(self):
        words = [_word("một", line=0, top=100), _word("hai", line=1, top=130)]

        assert len(group_lines(words)) == 2

    def test_same_line_number_in_a_different_block_is_a_different_line(self):
        """Tesseract đánh `line_num` LẠI TỪ 0 trong mỗi block — gom chỉ theo
        `line_num` sẽ dán hai cột của bố cục hai cột vào cùng một dòng."""
        words = [_word("cột", block=1, line=0), _word("phải", block=2, line=0)]

        assert len(group_lines(words)) == 2

    def test_empty_and_whitespace_words_are_dropped(self):
        words = [_word("", left=0), _word("   ", left=30), _word("chữ", left=60)]

        lines = group_lines(words)

        assert [l["text"] for l in lines] == ["chữ"]

    def test_no_words_gives_no_lines(self):
        assert group_lines([]) == []


class TestClassifyLine:
    @pytest.mark.parametrize("text", [
        "hấp thụ khí 0, và thải ra khí (0,",   # O2 / CO2 (D-63)
        "dung dịch H,SO, loãng",                # H2SO4
        "khí CO, gây hiệu ứng nhà kính",        # CO2
    ])
    def test_damaged_formula_lines_are_selected(self, text):
        assert classify_line(text) == ItemKind.CONG_THUC

    def test_line_with_a_long_digit_run_is_flagged_as_number(self):
        """`26,2` -> `262` là sai 10×, và nó IM LẶNG (D-63)."""
        assert classify_line("Năm 2020 sản lượng đạt 262 nghìn tấn") == \
            ItemKind.SO

    def test_table_caption_line_is_flagged_as_table(self):
        assert classify_line("Bảng 12.1 Tính chất của một số vật liệu") == \
            ItemKind.BANG

    def test_plain_body_text_is_not_selected(self):
        assert classify_line("Tế bào là đơn vị cơ bản của sự sống") is None

    def test_a_year_alone_is_not_a_damaged_number(self):
        """4 chữ số là năm, gặp khắp nơi. Cờ nó thì phiếu toàn nhiễu."""
        assert classify_line("Đến năm 2020, sản lượng tăng") is None

    def test_formula_beats_number_when_a_line_has_both(self):
        """Công thức là bệnh chính; một dòng chỉ vào phiếu MỘT lần."""
        assert classify_line("2 mol H,O ứng với 360 gam") == ItemKind.CONG_THUC


class TestScoreAnswers:
    ITEMS = [
        {"id": "i1", "kind": "cong_thuc", "may_doc": "khí 0, và (0,"},
        {"id": "i2", "kind": "cong_thuc", "may_doc": "H,SO, loãng"},
        {"id": "i3", "kind": "doi_chung", "may_doc": "Tế bào nhân thực"},
    ]

    def test_answer_matching_the_machine_on_a_broken_item_is_suspicious(self):
        """Ô `cong_thuc` vào phiếu vì máy ĐÃ đọc sai. Gõ lại y nguyên chữ của
        máy nghĩa là không mở ảnh ra xem — đây là phép kiểm thay cho ca mồi."""
        got = score_answers(self.ITEMS, {"i1": "khí 0, và (0,",
                                         "i2": "H,SO, loãng",
                                         "i3": "Tế bào nhân thực"})

        assert got["nghi_dong_dau"] == 2
        assert got["cong_bo_duoc"] is False
        assert "đóng dấu" in got["ly_do"]

    def test_real_corrections_are_publishable(self):
        got = score_answers(self.ITEMS, {"i1": "khí O₂ và CO₂",
                                         "i2": "H₂SO₄ loãng",
                                         "i3": "Tế bào nhân thực"})

        assert got["nghi_dong_dau"] == 0
        assert got["cong_bo_duoc"] is True
        assert got["da_dien"] == 3

    def test_a_half_filled_sheet_is_not_publishable(self):
        got = score_answers(self.ITEMS, {"i1": "khí O₂ và CO₂"})

        assert got["da_dien"] == 1
        assert got["cong_bo_duoc"] is False
        assert "chưa điền" in got["ly_do"]

    def test_control_item_agreeing_with_the_machine_is_NOT_suspicious(self):
        """Ô `doi_chung` vào phiếu vì máy có thể đọc ĐÚNG — trùng là bình thường,
        và đó chính là điều cần đo ở 3 trang đối chứng."""
        got = score_answers([self.ITEMS[2]], {"i3": "Tế bào nhân thực"})

        assert got["nghi_dong_dau"] == 0
        assert got["cong_bo_duoc"] is True


class TestClassifyLineNoise:
    """Ba lỗi tìm ra bằng cách MỞ PHIẾU ĐẦU TIÊN ra đối chiếu, không bằng test."""

    def test_a_bare_page_number_line_is_not_a_damaged_number(self):
        """Phiếu đầu tiên có một ô nội dung đúng là `'155'` — số trang in.
        `_SO_DAI` bắt mọi chuỗi 3 chữ số nên nó bắt luôn số trang."""
        assert classify_line("155") is None
        assert classify_line("  44 ") is None

    def test_a_line_with_an_equals_sign_is_a_formula_candidate(self):
        """`1 J = 1 Ñm` (D-63, RAG trả lời RỖNG) KHÔNG có dấu phẩy-chỉ-số-dưới
        nên bộ lọc cũ bỏ sót nó hoàn toàn. Công thức Lý gần như luôn có `=`."""
        assert classify_line("1 J = 1 Ñm") == ItemKind.CONG_THUC
        assert classify_line("A = Fs") == ItemKind.CONG_THUC

    def test_prose_merely_mentioning_a_table_is_not_the_table_item(self):
        """`(xem Bảng 12.1).` là câu văn trỏ tới bảng, không phải bảng. Đưa nó
        vào phiếu thì người duyệt gõ lại một câu văn và ta không đo được gì về
        quan hệ hàng/cột — đúng thứ đang bị mất (D-63)."""
        assert classify_line(
            "Ngoài tính dẫn điện và dẫn nhiệt, các vật liệu còn có các "
            "tính chát khác (xem Bảng 12.1).") is None

    def test_a_table_title_line_still_counts_as_the_table_anchor(self):
        assert classify_line("Bảng 12.1 Tính chất của một số vật liệu thông dụng") \
            == ItemKind.BANG


class TestTableBand:
    """Ô loại bảng phải là một DẢI ảnh chứa cả bảng, không phải dòng tiêu đề."""

    def test_band_starts_at_the_caption_and_covers_half_the_page(self):
        from src.test.ocr_bakeoff import table_band_bbox

        bbox = table_band_bbox(caption_bbox=(60, 300, 900, 330),
                              page_w=1094, page_h=1536)

        assert bbox == (0, 300, 1094, 300 + 768)

    def test_band_is_clipped_at_the_bottom_of_the_page(self):
        from src.test.ocr_bakeoff import table_band_bbox

        bbox = table_band_bbox(caption_bbox=(60, 1400, 900, 1430),
                              page_w=1094, page_h=1536)

        assert bbox == (0, 1400, 1094, 1536)


class TestTableItemsAskTwoConcreteRows:
    """Một khung nhập cho bảng 2 cột × 7 hàng là không gõ được. Và hai bệnh đã
    ghi trong D-63 là HAI bệnh khác nhau: `Bảng 35.1` mất **hàng header**,
    `Bảng 12.1` **trộn cột**. Nên hỏi thành hai câu riêng."""

    def test_one_table_band_becomes_two_questions(self):
        from src.test.ocr_bakeoff import table_questions

        qs = table_questions()

        assert len(qs) == 2
        assert "header" in qs[0].lower() or "đầu" in qs[0].lower()
        assert "|" in qs[0] and "|" in qs[1]

    def test_every_item_carries_the_question_shown_to_the_reviewer(self):
        """Không có `cau_hoi` thì người duyệt phải tự đoán phải gõ gì — và người
        đoán khác nhau giữa các ô thì gold set không so được."""
        from src.test.ocr_bakeoff import question_for

        assert question_for(ItemKind.CONG_THUC)
        assert question_for(ItemKind.SO)
        assert question_for(ItemKind.DOI_CHUNG)
