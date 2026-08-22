"""Test nhắm đúng phần TÍNH SỐ của cổng G2.

Chỉ test chỗ mà một con số sai sẽ lặng lẽ thành con số trong báo cáo: phân loại
thay thế (dấu / hoa-thường / khác chữ), parse block, và luật "chưa duyệt thì
không tính". Không test OCR hay chọn trang — cần ảnh thật, đắt và không đáng.
"""

import pytest

from src.test.qa_ocr_gold import (_align_chars, _parse_blocks, _strip_marks,
                                  _word_distance, REVIEW_RE)


def test_giong_nhau_thi_khong_co_loi():
    dist, dau, hoa, khac, ins, dele = _align_chars("quang hợp", "quang hợp")
    assert (dist, dau, hoa, khac, ins, dele) == (0, 0, 0, 0, 0, 0)


def test_loi_dau_duoc_dem_rieng():
    # 'ợ' -> 'o': cùng chữ gốc, khác dấu.
    dist, dau, hoa, khac, ins, dele = _align_chars("hợp", "hop")
    assert dist == 1
    assert (dau, hoa, khac) == (1, 0, 0)


def test_loi_hoa_thuong_KHONG_bi_dem_thanh_loi_dau():
    # Đây là bug đã bắt được khi tự soát: fold cả hoa/thường thì 'A'->'a' bị
    # tính là lỗi DẤU và thổi phồng đúng con số có ngưỡng 2%.
    dist, dau, hoa, khac, ins, dele = _align_chars("Axit", "axit")
    assert dist == 1
    assert dau == 0, "lỗi hoa/thường không được tính là lỗi dấu"
    assert hoa == 1


def test_khac_han_chu_la_sub_khac():
    dist, dau, hoa, khac, ins, dele = _align_chars("man", "nan")
    assert (dist, dau, hoa, khac) == (1, 0, 0, 1)


def test_ocr_thieu_va_them_chu():
    _, _, _, _, ins, dele = _align_chars("abc", "ab")
    assert (ins, dele) == (0, 1)
    _, _, _, _, ins2, dele2 = _align_chars("ab", "abc")
    assert (ins2, dele2) == (1, 0)


def test_ocr_mat_ca_vung_thi_dist_bang_do_dai_gold():
    gold = "Quang hợp là quá trình"
    dist, *_ = _align_chars(gold, "")
    assert dist == len(gold)


def test_strip_marks_giu_hoa_thuong():
    assert _strip_marks("ế") == "e"
    assert _strip_marks("Ế") == "E"
    assert _strip_marks("A") != _strip_marks("a")


def test_word_distance():
    assert _word_distance("a b c".split(), "a b c".split()) == 0
    assert _word_distance("a b c".split(), "a x c".split()) == 1
    assert _word_distance("a b".split(), "a b c".split()) == 1


def test_parse_blocks_bo_phan_dau_file():
    text = ("#REVIEWED-BY: khoa\n"
            "# ghi chu\n"
            "=== [1] body ===\n"
            "dong mot\n"
            "dong hai\n"
            "\n"
            "=== [2] sidebar ===\n"
            "noi dung sidebar\n")
    blocks = _parse_blocks(text)
    assert set(blocks) == {1, 2}
    assert blocks[1] == "dong mot\ndong hai"
    assert blocks[2] == "noi dung sidebar"
    assert "REVIEWED" not in blocks[1]


def test_parse_blocks_giu_tieu_de_nhung_xoa_chu_thi_rong():
    blocks = _parse_blocks("=== [1] body ===\n\n=== [2] body ===\nco chu\n")
    assert blocks[1] == ""
    assert blocks[2] == "co chu"


@pytest.mark.parametrize("line,mong_doi", [
    ("#REVIEWED-BY: khoa", "khoa"),
    ("#REVIEWED-BY:khoa", "khoa"),
    ("#REVIEWED-BY:", ""),
    ("#REVIEWED-BY:   ", ""),
])
def test_review_marker(line, mong_doi):
    mm = REVIEW_RE.search(line + "\n")
    assert mm is not None
    assert mm.group(1).strip() == mong_doi
