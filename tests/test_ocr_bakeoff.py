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


class TestBaselineKhongCanEngine:
    """Baseline Tesseract luôn có sẵn (`may_doc` nằm trong items.json), nên nó
    phải in được NGAY — trước khi chạy bất cứ model nào.

    Đó là con số "hiện tại đang tệ đến mức nào", tức mốc để mọi engine so vào.
    Bắt người dùng chạy 4 model trên Colab rồi mới biết mốc là ngược thứ tự."""

    def test_compare_prints_the_baseline_with_no_engine_files(self, tmp_path,
                                                              capsys):
        import json

        from src.test.ocr_bakeoff import cmd_compare

        items = [{"id": "f1", "kind": "cong_thuc", "may_doc": "khí 0,",
                  "quyen": "A", "trang": 1, "cau_hoi": "gõ"},
                 {"id": "d1", "kind": "doi_chung", "may_doc": "Tế bào",
                  "quyen": "A", "trang": 1, "cau_hoi": "gõ"}]
        (tmp_path / "items.json").write_text(
            json.dumps(items, ensure_ascii=False), encoding="utf-8")
        (tmp_path / "phieu_nguoi.json").write_text(
            json.dumps({"traloi": {"f1": "khí O₂", "d1": "Tế bào"}},
                       ensure_ascii=False), encoding="utf-8")

        code = cmd_compare(tmp_path)
        out = capsys.readouterr().out

        assert code == 0
        assert "tesseract" in out
        assert "chưa có engine" in out.lower()


class TestTokenCongThuc:
    """Chỉ số CT phải đo TOKEN CÔNG THỨC, không phải cả dòng.

    Thiết kế §3.2 viết: "tỉ lệ **token công thức** mà engine đọc khớp từng ký tự
    với bản người duyệt". Code lần đầu so **cả dòng** — khắt khe hơn hẳn và trộn
    hai thứ: một dòng 15 từ chỉ sai một dấu phẩy ở chữ thường cũng bị tính là
    hỏng công thức. Con số ra từ đó không trả lời được câu hỏi "engine có đọc
    được `O₂` không".
    """

    def test_subscript_tokens_are_extracted(self):
        from src.test.ocr_bakeoff import formula_tokens

        assert formula_tokens("hấp thụ khí O₂ và thải ra khí CO₂") == \
            ["O₂", "CO₂"]

    def test_ascii_written_formulas_are_extracted_too(self):
        """Người duyệt được phép gõ `H2SO4` — §3.5 luật 3."""
        from src.test.ocr_bakeoff import formula_tokens

        assert formula_tokens("dung dịch H2SO4 loãng") == ["H2SO4"]

    def test_physics_equations_are_extracted(self):
        from src.test.ocr_bakeoff import formula_tokens

        assert formula_tokens("công thức A = Fs với F là lực") == ["A = Fs"]

    def test_plain_vietnamese_words_are_not_formulas(self):
        from src.test.ocr_bakeoff import formula_tokens

        assert formula_tokens("Tế bào là đơn vị cơ bản của sự sống") == []

    def test_a_bare_number_is_not_a_formula(self):
        from src.test.ocr_bakeoff import formula_tokens

        assert formula_tokens("khoảng 26,2 tỉ thùng năm 2016") == []

    def test_ct_counts_tokens_not_whole_lines(self):
        """Engine đọc đúng `O₂` nhưng sai một chữ thường ở cuối dòng vẫn phải
        được tính là ĐỌC ĐÚNG CÔNG THỨC."""
        from src.test.ocr_bakeoff import score_engine

        items = [{"id": "f1", "kind": "cong_thuc", "may_doc": "khí 0,"}]
        gold = {"f1": "hấp thụ khí O₂ ở lá"}
        hyp = {"f1": "hấp thụ khí O₂ ở lạ"}      # sai 1 chữ, đúng công thức

        assert score_engine(items, gold, hyp)["cong_thuc"] == 1.0

    def test_an_item_whose_gold_has_no_formula_is_excluded_from_ct(self):
        """Ô `so` (mất dấu phẩy thập phân) không có token công thức nào — tính
        nó vào mẫu số của CT sẽ pha loãng chỉ số bằng thứ nó không đo."""
        from src.test.ocr_bakeoff import score_engine

        items = [{"id": "s1", "kind": "so", "may_doc": "262"}]
        gold = {"s1": "khoảng 26,2 tỉ thùng"}

        got = score_engine(items, gold, {"s1": "khoảng 262 tỉ thùng"})

        assert got["n_cong_thuc"] == 0
        assert got["cong_thuc"] is None


class TestBaselineOBang:
    """`BẢNG = 0.000` ở lượt baseline đầu tiên KHÔNG phải kết quả — nó là
    artefact của cách dựng dữ liệu, đúng loại "số sai mà trông hợp lý".

    `may_doc` của ô bảng là dòng **tiêu đề** (`Bảng 35.1. Sản lượng…`), vì đó là
    dòng anchor dùng để tìm bảng. Người duyệt thì gõ **nội dung** bảng. So hai
    thứ đó luôn cho 0, và con số 0 ấy nói về cách tôi dựng phiếu chứ không nói
    gì về Tesseract.

    Baseline đúng: Tesseract chạy trên **chính dải bảng** — cùng mẩu pixel engine
    sẽ đọc.
    """

    def test_a_table_item_carries_the_ocr_of_the_whole_band(self):
        import numpy as np

        from src.test.ocr_bakeoff import build_items

        img = np.full((1536, 1094, 3), 255, dtype=np.uint8)
        items = build_items(img, {"quyen": "A", "trang": 1, "loai": "bang"})

        for it in items:
            if it["kind"] == "bang":
                assert "may_doc_vung" in it, (
                    "ô bảng phải mang OCR của cả dải, nếu không baseline so "
                    "dòng tiêu đề với nội dung bảng và luôn ra 0")

    def test_baseline_uses_the_band_ocr_for_table_items(self):
        from src.test.ocr_bakeoff import baseline_reading

        items = [{"id": "b1", "kind": "bang", "may_doc": "Bảng 35.1. Sản lượng",
                  "may_doc_vung": "Năm | 1988 | 1992"},
                 {"id": "f1", "kind": "cong_thuc", "may_doc": "khí 0,"}]

        got = baseline_reading(items)

        assert got["b1"] == "Năm | 1988 | 1992"
        assert got["f1"] == "khí 0,"

    def test_a_table_item_without_band_ocr_falls_back_loudly(self):
        """Ô bảng cũ (dựng trước bản vá) không có `may_doc_vung`. Dùng thầm dòng
        tiêu đề sẽ tái lập đúng con số 0 giả — nên phải raise."""
        from src.test.ocr_bakeoff import baseline_reading

        with pytest.raises(RuntimeError, match="may_doc_vung"):
            baseline_reading([{"id": "b1", "kind": "bang",
                               "may_doc": "Bảng 35.1"}])


class TestColabEngineLoader:
    """`scripts/colab_run_ocr_engines.py` nạp model bằng auto-class NÀO.

    Bản đầu dùng một `AutoModelForCausalLM` cho cả ba engine. Đo trên
    `config.json` của HF (2026-08-26) thì 2/3 sai:
        nanonets/Nanonets-OCR2-3B     Qwen2_5_VLForConditionalGeneration, auto_map RỖNG
        opendatalab/MinerU2.5-...     Qwen2VLForConditionalGeneration,   auto_map RỖNG
        dots-studio/dots.ocr          auto_map = {AutoConfig, AutoModelForCausalLM}
    Hai model Qwen*VL không nằm trong registry của `AutoModelForCausalLM`, nên
    engine chết ngay bước nạp — người dùng đốt một phiên Colab để biết điều đó.
    """

    @staticmethod
    def _loader():
        import importlib.util
        from pathlib import Path

        p = Path(__file__).resolve().parents[1] / "scripts" / "colab_run_ocr_engines.py"
        spec = importlib.util.spec_from_file_location("colab_run_ocr_engines", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_tries_the_next_auto_class_and_says_which_one_won(self, monkeypatch, capsys):
        import torch
        import transformers

        mod = self._loader()
        goi = []

        class _Hong:
            @staticmethod
            def from_pretrained(*a, **k):
                raise ValueError("Unrecognized configuration class")

        class _Duoc:
            @staticmethod
            def from_pretrained(model_id, **k):
                goi.append(k)
                return TestTieWeightsGate._Model(tie_roi=True)

        monkeypatch.setattr(transformers, "AutoModelForImageTextToText", _Hong,
                            raising=False)
        monkeypatch.setattr(transformers, "AutoModelForCausalLM", _Duoc,
                            raising=False)

        assert mod._load_vlm("dots-studio/dots.ocr", torch) is not None
        # Phải NÓI RA class nào đã nạp — nếu không, engine chạy bằng đường
        # không ai kiểm được (đúng bệnh D-83/D-94).
        assert "AutoModelForCausalLM" in capsys.readouterr().out
        assert goi[0]["trust_remote_code"] is True
        assert goi[0]["device_map"] == "auto"

    def test_all_classes_failing_raises_with_every_error(self, monkeypatch):
        import torch
        import transformers

        mod = self._loader()

        class _Hong:
            @staticmethod
            def from_pretrained(*a, **k):
                raise ValueError("khong nap duoc")

        for ten in mod._AUTO_CLASSES:
            monkeypatch.setattr(transformers, ten, _Hong, raising=False)

        with pytest.raises(RuntimeError) as e:
            mod._load_vlm("x/y", torch)
        # Không được nuốt lỗi nào: cả ba class phải có tên trong thông báo.
        for ten in mod._AUTO_CLASSES:
            assert ten in str(e.value)

    def test_dtype_kwarg_follows_the_installed_transformers(self, monkeypatch):
        """`torch_dtype` bị bỏ ở transformers 5.x, `dtype` chỉ có từ 4.56."""
        import torch
        import transformers

        mod = self._loader()
        goi = []

        class _Duoc:
            @staticmethod
            def from_pretrained(model_id, **k):
                goi.append(k)
                return TestTieWeightsGate._Model(tie_roi=True)

        monkeypatch.setattr(transformers, "AutoModelForImageTextToText", _Duoc,
                            raising=False)

        monkeypatch.setattr(transformers, "__version__", "4.46.3", raising=False)
        mod._load_vlm("x/y", torch)
        assert "torch_dtype" in goi[-1] and "dtype" not in goi[-1]

        monkeypatch.setattr(transformers, "__version__", "5.0.0", raising=False)
        mod._load_vlm("x/y", torch)
        assert "dtype" in goi[-1] and "torch_dtype" not in goi[-1]

    def test_it_points_at_the_dir_compare_actually_reads(self):
        """`--compare` đọc `document/review/ocr_gold` (ocr_bakeoff.py:ARCHIVE_DIR).

        Script từng bảo người dùng chép `engine_*.json` về `database/review/...`;
        làm theo thì `--compare` không thấy file nào và chỉ in lại baseline —
        một thất bại trông như kết quả bình thường.
        """
        from pathlib import Path

        from src.test.ocr_bakeoff import ARCHIVE_DIR

        src = (Path(__file__).resolve().parents[1] / "scripts"
               / "colab_run_ocr_engines.py").read_text(encoding="utf-8")

        assert "database/review/ocr_gold" not in src
        assert ARCHIVE_DIR.as_posix() in src


class TestPartialEngineRun:
    """Engine mới chạy vài ô KHÔNG được in số — và vì sao đó không chỉ là thiếu.

    Đo trên phiếu thật (lượt Colab `--limit 3` ngày 2026-08-26): engine có 3/97
    ô, `score_engine` cho CT 0,000 / **DẤU 0,000** / BẢNG 0,000. DẤU 0,000 là
    điểm HOÀN HẢO ở đúng cột quyết định thắng/thua, vì một từ mất hẳn không phải
    "lỗi dấu" (`_fold("Quang") != _fold("")`). Bảng ấy nói NGƯỢC sự thật.
    """

    @staticmethod
    def _items():
        return [
            {"id": "f1", "kind": "cong_thuc", "may_doc": "khí 0,"},
            {"id": "d1", "kind": "doi_chung", "may_doc": "Quang hợp ở lá"},
            {"id": "d2", "kind": "doi_chung", "may_doc": "Rễ hút nước"},
        ]

    def test_a_silent_engine_scores_a_perfect_diacritic_rate(self):
        """Chốt CƠ CHẾ đã cắn, để không ai 'sửa' nó thành 1,0 mà không đo lại."""
        from src.test.ocr_bakeoff import score_engine

        gold = {"f1": "khí O₂", "d1": "Quang hợp ở lá", "d2": "Rễ hút nước"}

        st = score_engine(self._items(), gold, {})

        assert st["loi_dau"] == 0.0        # <- cái bẫy, cố ý khoá lại
        assert st["n_o_thieu"] == 3        # <- và cái cứu nó
        assert st["n_o_cham"] == 3

    def test_missing_and_empty_cells_are_counted_separately(self):
        """Thiếu key = engine chưa chạy ô đó; rỗng = chạy rồi, không đọc được.

        Hai chuyện khác nhau: nhiều ô rỗng nghĩa là engine đọc kém, nhiều ô
        thiếu nghĩa là lượt chạy chưa xong.
        """
        from src.test.ocr_bakeoff import score_engine

        gold = {"f1": "khí O₂", "d1": "Quang hợp ở lá", "d2": "Rễ hút nước"}

        st = score_engine(self._items(), gold, {"f1": "khí O2", "d1": ""})

        assert st["n_o_thieu"] == 1 and st["n_o_rong"] == 1
        assert st["n_o_cham"] == 3

    def test_cells_dropped_from_CT_still_count_in_the_cell_total(self):
        """`n_o_cham` KHÔNG phải `n_ct + n_dc + n_bang`.

        Ô `so` không có token công thức nào bị loại khỏi trục CT nhưng vẫn được
        chấm ở trục DẤU. Cộng ba trục cho mẫu số NHỎ HƠN thực tế — đã in ra
        "thiếu 94/77 ô" và "mới trả lời -17/97 ô" trước bản vá.
        """
        from src.test.ocr_bakeoff import score_engine

        items = [{"id": "s1", "kind": "so", "may_doc": "262"}]

        st = score_engine(items, {"s1": "26,2"}, {})

        assert st["n_cong_thuc"] == 0                       # không có token CT
        assert st["n_o_cham"] == 1                          # nhưng vẫn được chấm
        assert st["n_o_cham"] > st["n_cong_thuc"] + st["n_doi_chung"] + st["n_bang"]

    def test_compare_refuses_to_print_numbers_for_a_partial_engine(self, tmp_path, capsys):
        """`--compare` in `—` và nói thiếu bao nhiêu ô, thay vì in 0,000."""
        import json

        from src.test.ocr_bakeoff import cmd_compare

        items = self._items()
        (tmp_path / "items.json").write_text(json.dumps(items), encoding="utf-8")
        (tmp_path / "phieu_nguoi.json").write_text(json.dumps(
            {"traloi": {"f1": "khí O₂", "d1": "Quang hợp ở lá",
                        "d2": "Rễ hút nước"}}), encoding="utf-8")
        (tmp_path / "engine_moi.json").write_text(
            json.dumps({"f1": "khí O2"}), encoding="utf-8")

        assert cmd_compare(tmp_path) == 0
        out = capsys.readouterr().out

        dong = [l for l in out.splitlines() if l.startswith("engine_moi")
                or l.startswith("moi")]
        assert dong and "0.000" not in dong[0], dong
        assert "CHƯA ĐỦ: thiếu 2/3 ô" in out
        assert "mới trả lời 1/3 ô" in out

    def test_the_decision_rule_is_not_applied_to_a_partial_engine(self, tmp_path, capsys):
        """Engine chưa đủ không được tuyên THẮNG lẫn LOẠI — số của nó chưa tồn tại."""
        import json

        from src.test.ocr_bakeoff import cmd_compare

        (tmp_path / "items.json").write_text(json.dumps(self._items()),
                                             encoding="utf-8")
        (tmp_path / "phieu_nguoi.json").write_text(json.dumps(
            {"traloi": {"f1": "khí O₂", "d1": "Quang hợp ở lá",
                        "d2": "Rễ hút nước"}}), encoding="utf-8")
        (tmp_path / "engine_moi.json").write_text(json.dumps({}), encoding="utf-8")

        cmd_compare(tmp_path)

        assert "-> LOẠI" not in capsys.readouterr().out


class TestDoiChieu:
    """`--doi-chieu` phục vụ CẤM #11: không kết luận từ bảng mà chưa đọc ô."""

    @staticmethod
    def _setup(tmp_path, hyp):
        import json

        items = [
            {"id": "f1", "kind": "cong_thuc", "may_doc": "khí 0,"},
            {"id": "d1", "kind": "doi_chung", "may_doc": "Quang hợp ở lá"},
            {"id": "x1", "kind": "cong_thuc", "may_doc": "gì đó"},
        ]
        (tmp_path / "items.json").write_text(json.dumps(items), encoding="utf-8")
        (tmp_path / "phieu_nguoi.json").write_text(json.dumps(
            {"traloi": {"f1": "khí O₂", "d1": "Quang hợp ở lá", "x1": "???"}}),
            encoding="utf-8")
        (tmp_path / "engine_e.json").write_text(json.dumps(hyp), encoding="utf-8")
        return items

    def test_only_prints_cells_the_engine_actually_ran(self, tmp_path, capsys):
        """Ô chưa chạy không nói gì về engine — và in nó ra dưới dạng dòng rỗng
        sẽ trông y hệt ô engine đọc không ra (hai chuyện khác nhau, D-96)."""
        from src.test.ocr_bakeoff import cmd_doi_chieu

        self._setup(tmp_path, {"f1": "khí O2"})

        assert cmd_doi_chieu(tmp_path, "e", 0) == 0
        out = capsys.readouterr().out
        assert "f1" in out and "d1" not in out
        assert "đã chạy 1/3 ô" in out

    def test_a_cell_the_human_could_not_read_is_skipped(self, tmp_path, capsys):
        """`???` = không ai đọc được, kể cả người -> không có chuẩn để so."""
        from src.test.ocr_bakeoff import cmd_doi_chieu

        self._setup(tmp_path, {"x1": "engine doc gi do"})

        assert cmd_doi_chieu(tmp_path, "e", 0) == 1
        assert "Không có ô nào" in capsys.readouterr().out

    def test_filters_by_kind(self, tmp_path, capsys):
        from src.test.ocr_bakeoff import cmd_doi_chieu

        self._setup(tmp_path, {"f1": "khí O2", "d1": "Quang hop o la"})

        cmd_doi_chieu(tmp_path, "e", 0, "doi_chung")
        out = capsys.readouterr().out
        assert "d1" in out and "\nf1" not in out

    def test_shows_the_human_the_engine_and_tesseract_together(self, tmp_path, capsys):
        from src.test.ocr_bakeoff import cmd_doi_chieu

        self._setup(tmp_path, {"f1": "khí O2"})

        cmd_doi_chieu(tmp_path, "e", 0)
        out = capsys.readouterr().out
        assert "NGƯỜI" in out and "khí O₂" in out    # bản người
        assert "khí O2" in out                       # engine
        assert "khí 0," in out                       # tesseract, để so ba chiều


class TestTieWeightsGate:
    """Model nạp THIẾU lm_head sinh RÁC, không phải "đọc kém" — phải chặn.

    Ca thật (Colab, 2026-08-26, transformers 5.15.1): Nanonets-OCR2-3B báo
    `lm_head.weight | MISSING` rồi đọc 3/3 ô ra token ngẫu nhiên đa ngôn ngữ
    (`瞠`, `Uber`, `xoops` lặp lại). ĐO ĐƯỢC nguyên nhân trên HF:
    `model.safetensors.index.json` **không có key `lm_head.weight`** nào trong
    824 key (checkpoint TIED), và `tie_word_embeddings: true` chỉ khai trong
    `text_config` — top-level là `None`.
    """

    @staticmethod
    def _loader():
        return TestColabEngineLoader._loader()

    class _W:
        def __init__(self, ptr):
            self._ptr = ptr

        def data_ptr(self):
            return self._ptr

    class _Emb:
        def __init__(self, ptr):
            self.weight = TestTieWeightsGate._W(ptr)

    class _Model:
        """Model giả: `tie_weights()` làm lm_head trỏ vào cùng bộ nhớ embedding."""

        def __init__(self, tie_roi, tie_duoc=True):
            self._inp = TestTieWeightsGate._Emb(111)
            self._out = TestTieWeightsGate._Emb(111 if tie_roi else 999)
            self._tie_duoc = tie_duoc
            self.da_goi_tie = False

        def get_input_embeddings(self):
            return self._inp

        def get_output_embeddings(self):
            return self._out

        def tie_weights(self):
            self.da_goi_tie = True
            if self._tie_duoc:
                self._out = TestTieWeightsGate._Emb(111)

    def test_detects_an_untied_lm_head(self):
        mod = self._loader()

        assert mod._tie_da_xay_ra(self._Model(tie_roi=True)) is True
        assert mod._tie_da_xay_ra(self._Model(tie_roi=False)) is False

    def test_a_model_without_lm_head_is_fine(self):
        """Không có lm_head riêng thì không có gì để buộc — không được raise."""
        mod = self._loader()

        class _KhongCoLmHead(self._Model):
            def get_output_embeddings(self):
                return None

        assert mod._tie_da_xay_ra(_KhongCoLmHead(tie_roi=False)) is True

    def test_load_ties_the_weights_when_the_model_declares_it(self, monkeypatch, capsys):
        import torch
        import transformers

        mod = self._loader()
        m = self._Model(tie_roi=False)

        class _Cls:
            @staticmethod
            def from_pretrained(*a, **k):
                return m

        monkeypatch.setattr(transformers, "AutoModelForImageTextToText", _Cls,
                            raising=False)
        monkeypatch.setattr(mod, "_khai_bao_tie", lambda mid: True)

        assert mod._load_vlm("x/y", torch) is m
        assert m.da_goi_tie is True
        out = capsys.readouterr().out
        assert "CHƯA được buộc" in out and "xong" in out

    def test_load_raises_when_tying_does_not_take(self, monkeypatch):
        """Không sửa được thì DỪNG — không để engine chấm một bảng vô nghĩa."""
        import pytest
        import torch
        import transformers

        mod = self._loader()

        class _Cls:
            @staticmethod
            def from_pretrained(*a, **k):
                return TestTieWeightsGate._Model(tie_roi=False, tie_duoc=False)

        monkeypatch.setattr(transformers, "AutoModelForImageTextToText", _Cls,
                            raising=False)
        monkeypatch.setattr(mod, "_khai_bao_tie", lambda mid: True)

        with pytest.raises(RuntimeError, match="sinh"):
            mod._load_vlm("x/y", torch)

    def test_a_model_that_does_not_declare_tying_is_left_alone(self, monkeypatch):
        """Không khai tie thì lm_head rời là ĐÚNG — không được tự ý buộc."""
        import torch
        import transformers

        mod = self._loader()
        m = self._Model(tie_roi=False)

        class _Cls:
            @staticmethod
            def from_pretrained(*a, **k):
                return m

        monkeypatch.setattr(transformers, "AutoModelForImageTextToText", _Cls,
                            raising=False)
        monkeypatch.setattr(mod, "_khai_bao_tie", lambda mid: False)

        assert mod._load_vlm("x/y", torch) is m
        assert m.da_goi_tie is False


class TestTieGateIsLoud:
    """Cổng tie phải NÓI RA thứ nó quan sát được, kể cả khi mọi thứ ổn.

    Ca thật (Colab 2026-08-26, lượt 2): cổng **không in gì cả** — không `[vá]`,
    không raise — nên không phân biệt được "đã tie" với "không kiểm được". Một
    cổng im lặng khi ổn là một cổng vô dụng đúng lúc cần nhất.
    """

    @staticmethod
    def _loader():
        return TestColabEngineLoader._loader()

    def test_says_so_when_the_weights_are_already_tied(self, capsys):
        mod = self._loader()

        assert mod._tie_da_xay_ra(TestTieWeightsGate._Model(tie_roi=True)) is True
        assert "ĐÃ buộc" in capsys.readouterr().out

    def test_says_so_when_they_are_not(self, capsys):
        mod = self._loader()

        assert mod._tie_da_xay_ra(TestTieWeightsGate._Model(tie_roi=False)) is False
        assert "CHƯA buộc" in capsys.readouterr().out

    def test_a_hidden_lm_head_is_still_checked(self, capsys):
        """`get_output_embeddings() = None` KHÔNG phải bằng chứng model ổn.

        Qwen2.5-VL trong transformers 5.x đặt phần ngôn ngữ dưới
        `model.language_model`, nên lớp ngoài có thể không lộ lm_head ra — mà
        lm_head vẫn có thật và vẫn có thể chưa được buộc.
        """
        mod = self._loader()

        class _Sau(TestTieWeightsGate._Model):
            def __init__(self):
                super().__init__(tie_roi=False)
                self.language_model = type("_LM", (), {})()
                self.language_model.lm_head = self._out

            def get_output_embeddings(self):
                return None

        assert mod._tie_da_xay_ra(_Sau()) is False
        out = capsys.readouterr().out
        assert "TÌM THẤY lm_head ở lớp sâu" in out and "CHƯA buộc" in out

    def test_a_model_with_no_lm_head_anywhere_passes_and_says_why(self, capsys):
        mod = self._loader()

        class _Khong(TestTieWeightsGate._Model):
            def get_output_embeddings(self):
                return None

        assert mod._tie_da_xay_ra(_Khong(tie_roi=False)) is True
        assert "không tìm thấy lm_head" in capsys.readouterr().out


class TestTransformers5Warning:
    """transformers 5.x nạp hỏng lm_head của Nanonets — phải cảnh báo TRƯỚC.

    Bằng chứng (T4, 2026-08-26): ba lượt nạp cho ba chuỗi rác KHÁC HẲN nhau dù
    `do_sample=False`. Greedy + cùng ảnh + cùng prompt mà output đổi giữa các
    lượt nạp => trọng số đổi mỗi lượt => lm_head khởi tạo ngẫu nhiên.
    """

    @staticmethod
    def _loader():
        return TestColabEngineLoader._loader()

    def _chay(self, monkeypatch, capsys, version):
        import torch
        import transformers

        mod = self._loader()

        class _Cls:
            @staticmethod
            def from_pretrained(*a, **k):
                return TestTieWeightsGate._Model(tie_roi=True)

        monkeypatch.setattr(transformers, "AutoModelForImageTextToText", _Cls,
                            raising=False)
        monkeypatch.setattr(transformers, "__version__", version, raising=False)
        mod._load_vlm("x/y", torch)
        return capsys.readouterr().out

    def test_warns_on_5x(self, monkeypatch, capsys):
        out = self._chay(monkeypatch, capsys, "5.15.1")
        assert "transformers>=4.49,<5" in out and "RÁC" in out

    def test_stays_quiet_on_4x(self, monkeypatch, capsys):
        out = self._chay(monkeypatch, capsys, "4.49.0")
        assert "transformers>=4.49,<5" not in out


class TestNghiModelHong:
    """Phân biệt "model HỎNG" với "model đọc kém" — chuyện của BÁO CÁO.

    Viết "model X đọc kém tiếng Việt" khi thật ra nó nạp hỏng là một kết luận
    SAI về một model có thể tốt, và nó sẽ nằm trong đồ án.

    Giả thuyết đầu tiên (tỉ lệ ký tự ngoài Latin) đã bị chính phép đo bác bỏ:
    chuỗi rác thật của ba lượt Nanonets cho 0,106 / 0,149 / 0,118 — sát nhiễu,
    vì phần lớn token rác là tiếng Anh.
    """

    NGUOI = ("cây phú quý, cây oải hương, cây lưỡi hổ, ngoài khả năng "
             "hấp thụ CO₂ và tạo ra khí O₂ vào ban")

    def test_tesseract_reading_badly_is_not_flagged(self):
        """Hỏng chỉ số dưới nhưng trúng gần hết từ -> đọc kém, KHÔNG phải rác."""
        from src.test.ocr_bakeoff import dai_gap, ty_le_trung_tu

        tess = self.NGUOI.replace("CO₂", "(0,").replace("O₂", "0,")

        assert ty_le_trung_tu(self.NGUOI, tess) > 0.5
        assert dai_gap(self.NGUOI, tess) < 3.0

    def test_random_tokens_are_flagged(self):
        from src.test.ocr_bakeoff import dai_gap, ty_le_trung_tu

        rac = "getSession_Point Layer 瞠 Cocoa Fighting ировать " * 20

        assert ty_le_trung_tu(self.NGUOI, rac) == 0.0
        assert dai_gap(self.NGUOI, rac) > 3.0

    def test_an_accentless_reading_is_not_flagged(self):
        """Đọc mất dấu vẫn trùng từ (so trên dạng bỏ dấu) -> đọc kém, không rác."""
        from src.test.ocr_bakeoff import ty_le_trung_tu

        assert ty_le_trung_tu(self.NGUOI, "cay phu quy cay oai huong") > 0.05

    def test_compare_warns_and_refuses_to_judge_a_broken_engine(self, tmp_path, capsys):
        import json

        from src.test.ocr_bakeoff import cmd_compare

        items = [{"id": f"c{i}", "kind": "doi_chung", "may_doc": self.NGUOI}
                 for i in range(4)]
        (tmp_path / "items.json").write_text(json.dumps(items), encoding="utf-8")
        (tmp_path / "phieu_nguoi.json").write_text(json.dumps(
            {"traloi": {f"c{i}": self.NGUOI for i in range(4)}}), encoding="utf-8")
        (tmp_path / "engine_hong.json").write_text(json.dumps(
            {f"c{i}": "getSession_Point Layer 瞠 Cocoa ировать " * 20
             for i in range(4)}), encoding="utf-8")

        assert cmd_compare(tmp_path) == 0
        out = capsys.readouterr().out
        assert "NGHI MODEL HỎNG" in out
        assert "đọc kém tiếng Việt" in out     # câu nhắc đừng viết vào báo cáo
        assert "-> LOẠI" not in out            # không tuyên án khi model hỏng

    def test_an_empty_cell_is_not_called_garbage(self, tmp_path):
        """Ô rỗng là chuyện của `n_o_rong`, không phải bằng chứng model hỏng."""
        from src.test.ocr_bakeoff import nghi_model_hong

        items = [{"id": "c1", "kind": "doi_chung", "may_doc": self.NGUOI}]

        h = nghi_model_hong(items, {"c1": self.NGUOI}, {"c1": ""})

        assert h["o_cham"] == 0 and h["nghi"] is False


class TestMineruUsesItsOwnInterface:
    """MinerU2.5 KHÔNG nhận prompt tự do — nó có giao diện riêng.

    Đo 2026-08-26 với `PROMPT_DONG`: một ô model lặp lại chính câu prompt
    ("Trích xuất chính xác toàn bộ chữ trong ảnh, từ 0 đến 100…" ×25), một ô
    khác xuất format nội bộ `<|class_start|>chart<|class_end|>` kèm nội dung
    không có trên ảnh. Đó là dấu hiệu ÉP MODEL VÀO GIAO DIỆN SAI, không phải
    bằng chứng model bịa — loại nó vì "bịa" sẽ lặp lại đúng cái sai suýt xảy ra
    với Nanonets (D-102).
    """

    @staticmethod
    def _loader():
        return TestColabEngineLoader._loader()

    def test_mineru_is_not_routed_through_the_free_prompt_path(self):
        mod = self._loader()

        assert mod.ENGINES["mineru25"] is mod._mineru25
        assert mod.ENGINES["dots_ocr"] is not mod._mineru25

    def test_the_free_prompt_path_still_serves_dots_ocr(self):
        """dots.ocr vẫn đi đường chat thường — đừng đổi cả hai vì một."""
        mod = self._loader()
        import inspect

        assert "dots" in inspect.getsource(mod.ENGINES["dots_ocr"])


class TestEngineRunSignature:
    """Mọi engine nhận `kind` — MinerU cần biết ô là DÒNG hay BẢNG.

    `two_step_extract` trên crop cho RỖNG 3/3 ô (đo 2026-08-26): bước 1 phân
    tích BỐ CỤC CẢ TRANG, mà crop một dòng thì không có bố cục nào để tìm -> 0
    block -> chuỗi rỗng. Không phải model đọc không ra. `content_extract` là
    bước 2 với bbox = cả ảnh, tức đúng đơn vị mà bake-off đang chấm.
    """

    @staticmethod
    def _loader():
        return TestColabEngineLoader._loader()

    def test_every_engine_run_takes_kind(self):
        import inspect

        mod = self._loader()
        src = inspect.getsource(mod)

        # ba engine -> ba `def run(...)`, tất cả phải có `kind`
        dong = [l for l in src.splitlines() if l.strip().startswith("def run(png")]
        assert len(dong) == 3, dong
        assert all("kind" in l for l in dong), dong

    def test_the_loop_passes_the_kind_through(self):
        import inspect

        mod = self._loader()
        src = inspect.getsource(mod.main)

        assert 'it.get("kind", "")' in src
        # phải truyền HAI lần: một cho prompt, một cho engine
        assert src.count('it.get("kind", "")') >= 2

    def test_mineru_maps_table_cells_to_the_table_type(self):
        import inspect

        mod = self._loader()
        src = inspect.getsource(mod._mineru25)

        assert '"table" if kind == "bang" else "text"' in src
        assert "client.content_extract(" in src
        assert "client.two_step_extract(" not in src   # còn nhắc trong docstring là được
