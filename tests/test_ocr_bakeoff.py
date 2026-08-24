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


class TestChuanHoaCongThuc:
    """So công thức phải bỏ qua CÁCH GÕ, không bỏ qua NỘI DUNG.

    Người duyệt gõ `O2` hay `O₂` đều là cùng một câu trả lời đúng. Nhưng `O,`
    (chỉ số dưới bị phá thành dấu phẩy — D-56) là một câu trả lời KHÁC, và
    chuẩn hoá nó thành `O₂` sẽ là tự bịa ra điều mình không đọc được.
    """

    def test_ascii_digits_normalise_to_subscripts(self):
        from src.test.ocr_bakeoff import normalize_formula

        assert normalize_formula("H2SO4") == normalize_formula("H₂SO₄")
        assert normalize_formula("CO2") == normalize_formula("CO₂")

    def test_a_comma_is_NOT_normalised_into_a_subscript(self):
        """Đoán lại một chỉ số đã mất là BỊA (CẤM #5 của prompt M2)."""
        from src.test.ocr_bakeoff import normalize_formula

        assert normalize_formula("CO,") != normalize_formula("CO₂")

    def test_spacing_around_the_formula_does_not_matter(self):
        from src.test.ocr_bakeoff import normalize_formula

        assert normalize_formula("2 H₂O") == normalize_formula("2  H₂O ")


class TestTyLeLoiDau:
    """Chỉ số DẤU là cổng loại: model đọc giỏi công thức mà sai dấu thì bị loại."""

    def test_a_word_wrong_only_in_its_tone_mark_counts_as_a_diacritic_error(self):
        from src.test.ocr_bakeoff import diacritic_error_rate

        # "chế" -> "ché": bỏ dấu thì hai từ TRÙNG nhau => lỗi DẤU.
        assert diacritic_error_rate("cơ chế quang hợp", "cơ ché quang hợp") == \
            pytest.approx(1 / 4)

    def test_a_word_wrong_in_its_letters_is_NOT_a_diacritic_error(self):
        """`quang` -> `quaug` sai CHỮ, không phải sai dấu. Gộp hai loại lỗi vào
        một con số thì không biết model hỏng ở đâu."""
        from src.test.ocr_bakeoff import diacritic_error_rate

        assert diacritic_error_rate("cơ chế quang hợp", "cơ chế quaug hợp") == 0.0

    def test_a_perfect_read_has_no_diacritic_error(self):
        from src.test.ocr_bakeoff import diacritic_error_rate

        assert diacritic_error_rate("cơ chế quang hợp", "cơ chế quang hợp") == 0.0

    def test_empty_gold_gives_zero_not_a_crash(self):
        from src.test.ocr_bakeoff import diacritic_error_rate

        assert diacritic_error_rate("", "gì đó") == 0.0


class TestOBang:
    def test_cells_split_on_the_pipe_and_are_trimmed(self):
        from src.test.ocr_bakeoff import table_cells

        assert table_cells(" Năm | 1988 |1992 ") == ["Năm", "1988", "1992"]

    def test_cell_accuracy_is_position_sensitive(self):
        """`Bảng 12.1` hỏng vì TRỘN CỘT (D-63) — ô đúng nội dung mà sai vị trí
        vẫn là sai, nếu không thì phép đo không thấy được bệnh đó."""
        from src.test.ocr_bakeoff import table_cell_accuracy

        assert table_cell_accuracy("A | B | C", "A | B | C") == 1.0
        assert table_cell_accuracy("A | B | C", "A | C | B") == pytest.approx(1 / 3)

    def test_a_missing_cell_counts_against_the_engine(self):
        from src.test.ocr_bakeoff import table_cell_accuracy

        assert table_cell_accuracy("A | B | C", "A | B") == pytest.approx(2 / 3)


class TestSoEngine:
    """Bảng so engine phải trả lời được câu hỏi CHỌN CÁI NÀO, và phải từ chối
    trả lời khi chưa đủ dữ kiện."""

    GOLD_ITEMS = [
        {"id": "f1", "kind": "cong_thuc", "may_doc": "khí 0, và (0,"},
        {"id": "d1", "kind": "doi_chung", "may_doc": "Tế bào nhân thực"},
        {"id": "b1_1", "kind": "bang", "may_doc": "Bảng 35.1"},
    ]
    GOLD = {"f1": "khí O₂ và CO₂", "d1": "Tế bào nhân thực",
            "b1_1": "Năm | 1988 | 1992"}

    def test_a_perfect_engine_scores_one_on_every_axis(self):
        from src.test.ocr_bakeoff import score_engine

        got = score_engine(self.GOLD_ITEMS, self.GOLD, dict(self.GOLD))

        assert got["cong_thuc"] == 1.0
        assert got["loi_dau"] == 0.0
        assert got["bang"] == 1.0

    def test_engine_losing_subscripts_scores_zero_on_formulas(self):
        from src.test.ocr_bakeoff import score_engine

        got = score_engine(self.GOLD_ITEMS, self.GOLD,
                           {**self.GOLD, "f1": "khí 0, và (0,"})

        assert got["cong_thuc"] == 0.0

    def test_ascii_subscripts_from_an_engine_still_count_as_correct(self):
        from src.test.ocr_bakeoff import score_engine

        got = score_engine(self.GOLD_ITEMS, self.GOLD,
                           {**self.GOLD, "f1": "khí O2 và CO2"})

        assert got["cong_thuc"] == 1.0

    def test_diacritic_damage_shows_up_on_the_control_axis(self):
        """Ô đối chứng là chỗ đo chữ thường — 93% corpus là chữ thường."""
        from src.test.ocr_bakeoff import score_engine

        got = score_engine(self.GOLD_ITEMS, self.GOLD,
                           {**self.GOLD, "d1": "Te bào nhân thực"})

        assert got["loi_dau"] > 0

    def test_an_item_the_engine_did_not_answer_counts_as_wrong_not_skipped(self):
        """Bỏ qua ô không đọc được sẽ thưởng cho engine im lặng — đúng loại
        'số cao mà sai' mà repo này sợ nhất."""
        from src.test.ocr_bakeoff import score_engine

        got = score_engine(self.GOLD_ITEMS, self.GOLD, {"d1": "Tế bào nhân thực"})

        assert got["cong_thuc"] == 0.0
        assert got["bang"] == 0.0

    def test_items_the_human_left_blank_are_excluded_from_every_axis(self):
        """Không có bản người thì không có chuẩn để so — chấm bừa là bịa."""
        from src.test.ocr_bakeoff import score_engine

        got = score_engine(self.GOLD_ITEMS, {"d1": "Tế bào nhân thực"},
                           dict(self.GOLD))

        assert got["n_cong_thuc"] == 0
        assert got["n_doi_chung"] == 1
        assert got["cong_thuc"] is None

    def test_human_marked_unreadable_items_are_excluded_too(self):
        """`???` nghĩa là NGƯỜI cũng không đọc được — không dùng làm chuẩn."""
        from src.test.ocr_bakeoff import score_engine

        got = score_engine(self.GOLD_ITEMS, {**self.GOLD, "f1": "???"},
                           dict(self.GOLD))

        assert got["n_cong_thuc"] == 0
        assert got["n_khong_doc_duoc"] == 1


class TestDumpCrops:
    """Engine chạy trên COLAB, mà PNG nguồn là 4,1 GB không nằm trong git
    (D-68). Nên phải xuất đúng 97 crop (vài MB) để mang lên."""

    def test_each_item_becomes_one_png_named_by_its_id(self, tmp_path):
        import base64

        from src.test.ocr_bakeoff import dump_crops

        # PNG 1×1 hợp lệ, đủ để kiểm đường ghi file.
        px = base64.b64encode(bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000a49444154789c6300010000050001"
            "0d0a2db40000000049454e44ae426082")).decode()
        items = [{"id": "A_p1_01", "anh_b64": px, "kind": "cong_thuc",
                  "quyen": "A", "trang": 1, "cau_hoi": "gõ lại"},
                 {"id": "A_p1_02", "anh_b64": px, "kind": "doi_chung",
                  "quyen": "A", "trang": 1, "cau_hoi": "gõ lại"}]

        n = dump_crops(items, tmp_path)

        assert n == 2
        assert (tmp_path / "A_p1_01.png").exists()
        assert (tmp_path / "A_p1_02.png").exists()

    def test_a_manifest_lists_every_crop_so_colab_needs_no_source_pngs(self,
                                                                       tmp_path):
        import base64
        import json

        from src.test.ocr_bakeoff import dump_crops

        px = base64.b64encode(bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000a49444154789c6300010000050001"
            "0d0a2db40000000049454e44ae426082")).decode()
        items = [{"id": "A_p1_01", "anh_b64": px, "kind": "bang", "quyen": "A",
                  "trang": 1, "cau_hoi": "hàng đầu"}]

        dump_crops(items, tmp_path)
        man = json.loads((tmp_path / "crops.json").read_text(encoding="utf-8"))

        assert man[0]["id"] == "A_p1_01"
        assert man[0]["file"] == "A_p1_01.png"
        assert man[0]["kind"] == "bang"
        assert "anh_b64" not in man[0]

    def test_an_item_with_no_crop_is_reported_not_silently_skipped(self,
                                                                  tmp_path):
        from src.test.ocr_bakeoff import dump_crops

        items = [{"id": "A_p1_01", "anh_b64": "", "kind": "so", "quyen": "A",
                  "trang": 1, "cau_hoi": "gõ"}]

        with pytest.raises(RuntimeError, match="không có ảnh"):
            dump_crops(items, tmp_path)


class TestLuuCongNguoi:
    """`database/` bị gitignore (D-68). Phiếu người duyệt là **công người,
    không dựng lại được** — để nó nằm trong `database/` là hẹn ngày mất nó.
    Tiền lệ đã có: `document/review/testset_review_50.csv` nằm trong git."""

    def test_a_usable_sheet_is_copied_into_the_versioned_review_dir(self,
                                                                    tmp_path):
        import json

        from src.test.ocr_bakeoff import archive_human_sheet

        src = tmp_path / "db" / "phieu_nguoi.json"
        src.parent.mkdir(parents=True)
        src.write_text(json.dumps({"traloi": {"a": "x"}}), encoding="utf-8")
        kho = tmp_path / "document" / "review" / "ocr_gold"

        dest = archive_human_sheet(src, kho)

        assert dest == kho / "phieu_nguoi.json"
        assert json.loads(dest.read_text(encoding="utf-8"))["traloi"] == {"a": "x"}

    def test_an_existing_archive_is_never_silently_overwritten(self, tmp_path):
        """Ghi đè im lặng một phiếu cũ = xoá công người mà không ai biết."""
        import json

        from src.test.ocr_bakeoff import archive_human_sheet

        src = tmp_path / "phieu_nguoi.json"
        src.write_text(json.dumps({"traloi": {"a": "moi"}}), encoding="utf-8")
        kho = tmp_path / "kho"
        kho.mkdir()
        (kho / "phieu_nguoi.json").write_text(
            json.dumps({"traloi": {"a": "cu"}}), encoding="utf-8")

        dest = archive_human_sheet(src, kho)

        assert dest.name.startswith("phieu_nguoi")
        assert dest != kho / "phieu_nguoi.json"
        assert json.loads((kho / "phieu_nguoi.json").read_text(
            encoding="utf-8"))["traloi"] == {"a": "cu"}
