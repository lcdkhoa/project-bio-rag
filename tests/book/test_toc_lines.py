"""Test bộ đọc MỤC LỤC theo dòng (M1) — fixture tổng hợp, KHÔNG gọi OCR.

Mỗi test neo vào một ca ĐÃ ĐO trên corpus thật, ghi rõ ở docstring, để một lần
sửa sau này làm hồi quy thì thấy ngay là hồi quy cái gì.
"""
import numpy as np
import pytest

from src.etl.book.toc import TocResult
from src.etl.book import toc_lines as TL


def seg(text, x0=0, x1=None):
    tokens = text.split()
    width = 40
    boxes, x = [], x0
    for token in tokens:
        boxes.append((x, x + width, token))
        x += width + 10
    return TL.Segment(text=text, x0=x0, x1=x1 if x1 is not None else x,
                      tokens=tuple(boxes))


def line(*segments, page=4, y0=100, y1=140):
    return TL.TocLine(page_index=page, segments=tuple(segments), y0=y0, y1=y1)


BLANK = np.full((300, 400, 3), 255, dtype=np.uint8)


def parse(lines, style):
    result, seen = TocResult(), {}
    TL.parse_page(BLANK, lines, style, result, seen)
    return result, seen


# --------------------------------------------------------------- mục "Bài N"

def test_bai_entry_uppercase_matches():
    """CTST in `BÀI 1:` chữ HOA — `toc._BAI` phân biệt hoa/thường nên trượt."""
    _, seen = parse([line(seg("BÀI 1: Mô tả sóng âm 65"))], "bai")
    assert seen[1] == (65, "Mô tả sóng âm")


def test_bai_entry_lowercase_matches():
    _, seen = parse([line(seg("Bài 12. Mô tả sóng âm 65"))], "bai")
    assert seen[12][0] == 65


def test_carry_number_before_entry_is_not_the_page():
    """`10 7, Tốc độ của chuyển động 47` (7_CD): `10` là số trang của mục cột
    TRÁI bị dán vào; mục ở đây là 7 và trang của nó là 47, không phải 10."""
    _, seen = parse([line(seg("10 7, Tốc độ của chuyển động 47"))], "so_thu_tu")
    assert seen == {7: (47, "Tốc độ của chuyển động")}


def test_chu_de_digit_does_not_become_an_entry():
    """`Chủ đề4:Tốc độ 47` — chữ số dính ngay sau "đề". Nhận nó thành mục số 4 là
    tạo một Bài không tồn tại, phá phép tự kiểm 1..max."""
    result, seen = parse([line(seg("Chủ đề 4: Tốc độ 47"))], "so_thu_tu")
    assert seen == {}
    assert [c.label for c in result.chuongs] == ["4"]


def test_bai_tap_row_is_skipped():
    """`Bài tập (Chủ đề 4) 53` là mục ôn tập, không phải Bài — nhận vào thì
    `bai_so` trùng số chủ đề."""
    _, seen = parse([line(seg("Bài tập (Chủ đề 4) 53"))], "bai")
    assert seen == {}


# -------------------------------------------------- số trang: dừng ở mục kế

def test_page_search_stops_at_next_entry():
    """Ca đã đo trên 9_CTST: số của Bài 1 không đọc được, phép tìm đi tiếp và
    lấy `62` của mục khác -> `Bài 1 -> trang 62`. Phải bỏ, không lấy."""
    result, seen = parse(
        [line(seg("Bài 1. Phương pháp học tập", x0=0, x1=300),
              seg("Bài 12. Mô tả sóng âm 65", x0=800, x1=1200))], "bai")
    assert 1 not in seen                       # bỏ, không mượn số của Bài 12
    assert seen[12][0] == 65
    assert any(f["kind"] == "toc_page_unreadable" for f in result.flags)


def test_page_on_continuation_line_is_found():
    """CTST: tiêu đề tràn dòng nên số trang nằm ở DÒNG KẾ của cùng cột."""
    _, seen = parse([line(seg("Bài 1. Phương pháp và kĩ năng học tập")),
                     line(seg("môn Khoa học tự nhiên 6"), y0=150, y1=190)],
                    "bai")
    assert seen[1] == (6, "Phương pháp và kĩ năng học tập")


def test_continuation_scan_stops_at_next_entry():
    _, seen = parse([line(seg("Bài 1. Phương pháp và kĩ năng học tập")),
                     line(seg("Bài 2. Nguyên tử 14"), y0=150, y1=190)], "bai")
    assert 1 not in seen
    assert seen[2][0] == 14


# ---------------------------------------------------- tự kiểm: dãy không giảm

def test_lnds_drops_the_minority_not_the_tail():
    """Phép quét tham lam bỏ TOÀN BỘ phần sau một mục sai ở đầu dãy (9_CTST: 40
    cờ, còn 3 mục). Dãy con không giảm dài nhất chỉ bỏ đúng mục sai."""
    pairs = [(1, 62), (2, 6), (3, 10), (4, 14), (5, 20)]
    keep = TL._longest_non_decreasing(pairs)
    assert sorted(pairs[i][0] for i in keep) == [2, 3, 4, 5]


def test_finalise_flags_what_it_drops():
    result = TocResult()
    TL.finalise(result, {1: (62, "a"), 2: (6, "b"), 3: (10, "c"), 4: (14, "d")})
    assert [e.bai_so for e in result.entries] == [2, 3, 4]
    assert [f["kind"] for f in result.flags] == ["toc_page_out_of_order"]


def test_finalise_keeps_equal_pages():
    """Hai Bài cùng bắt đầu trên một trang là hợp lệ (không giảm, không phải
    tăng nghiêm ngặt)."""
    result = TocResult()
    TL.finalise(result, {1: (6, "a"), 2: (6, "b")})
    assert [e.start_page for e in result.entries] == [6, 6]


# ------------------------------------------------------------- tách cột

def _two_column_page(width=2280, height=3201, gutter=(1067, 1188)):
    page = np.full((height, width, 3), 255, dtype=np.uint8)
    page[400:2800, 100:gutter[0] - 50] = 0
    page[400:2800, gutter[1] + 50:width - 100] = 0
    return page


def test_split_columns_finds_a_centred_gutter():
    """CTST: đo được khe 99–123 px, tâm x = 0,493–0,507 trên 8/8 trang."""
    boxes = TL.split_columns(_two_column_page())
    assert len(boxes) == 2
    assert 0.42 <= (boxes[0][1] + boxes[1][0]) / 2 / 2280 <= 0.58


def test_split_columns_ignores_a_right_margin_gap():
    """8_CD/9_CD: MỤC LỤC MỘT cột; chỗ trống rộng nhất nằm ở x=0,61–0,68 (lề
    phải). Nhận nó làm khe cột là cắt đôi giữa tiêu đề."""
    page = np.full((3201, 2280, 3), 255, dtype=np.uint8)
    page[400:2800, 100:1500] = 0          # một cột chạy tới x=1500
    assert TL.split_columns(page) == [(0, 2279)]


def test_split_columns_ignores_a_gutter_that_is_too_narrow():
    page = np.full((3201, 2280, 3), 255, dtype=np.uint8)
    page[400:2800, 100:1130] = 0
    page[400:2800, 1140:2180] = 0         # khe 10 px < 1,5% * 2280 = 34 px
    assert TL.split_columns(page) == [(0, 2279)]


# ---------------------------------------------------------------- trùng mục

def test_duplicate_entry_with_a_different_page_is_flagged():
    result, seen = parse([line(seg("1. Nguyên tử 10")),
                          line(seg("1. Nguyên tử 61"), y0=150, y1=190)],
                         "so_thu_tu")
    assert seen[1][0] == 10
    assert any(f["kind"] == "toc_entry_duplicated" for f in result.flags)


@pytest.mark.parametrize("text,expected", [
    ("1. Nguyên tử 10", 10),
    ("18. Quang hợp ở thực vặt 80", 80),
    ("12: Ánh sáng, tỉa sáng 65", 65),      # OCR đọc `12.` thành `12:`
])
def test_so_thu_tu_variants(text, expected):
    _, seen = parse([line(seg(text))], "so_thu_tu")
    assert list(seen.values())[0][0] == expected
