from src.etl.book.toc import TocChuong, TocEntry, parse_toc_lines


def test_parses_bai_lines_with_trailing_page_number():
    lines = ["MỤC LỤC",
             "Bài 6. Đo khối lượng 20",
             "Bài 7. Đo thời gian 22"]
    entries, _ = parse_toc_lines(lines)
    assert entries == [TocEntry(6, "Đo khối lượng", 20),
                       TocEntry(7, "Đo thời gian", 22)]


def test_parses_chuong_headings_and_remembers_position():
    lines = ["CHƯƠNG I - MỞ ĐẦU VỀ KHOA HỌC TỰ NHIÊN",
             "Bài 1. Giới thiệu về Khoa học tự nhiên 7",
             "CHƯƠNG II - CHẤT QUANH TA",
             "Bài 9. Sự đa dạng của chất 28"]
    entries, chuongs = parse_toc_lines(lines)
    assert [e.bai_so for e in entries] == [1, 9]
    assert chuongs == [TocChuong("I", "MỞ ĐẦU VỀ KHOA HỌC TỰ NHIÊN", None),
                       TocChuong("II", "CHẤT QUANH TA", 1)]


def test_skips_front_matter_rows_without_a_bai_number():
    entries, _ = parse_toc_lines(["Hướng dẫn sử dụng sách 2", "Lời nói đầu 3"])
    assert entries == []


def test_drops_a_line_whose_page_number_is_missing():
    entries, _ = parse_toc_lines(["Bài 12. Một số vật liệu"])
    assert entries == []


def test_keeps_a_garbled_bai_number_verbatim_for_the_spine_to_repair():
    # Measured OCR failure on the real TOC: "Bài 31" came out as "Bài 3" and
    # "Bài 41" as "Bài 4". The parser must NOT silently fix it — repairing with
    # the monotonic constraint is bai_spine's job, and it flags what it changed.
    entries, _ = parse_toc_lines(["Bài 3. l Hệ vận động ở người 125"])
    assert entries == [TocEntry(3, "l Hệ vận động ở người", 125)]


def test_ignores_a_page_number_that_is_out_of_range():
    entries, _ = parse_toc_lines(["Bài 5. Đo chiều dài 4017"])
    assert entries == []


def test_tolerates_a_colon_or_missing_separator_after_the_number():
    lines = ["Bài 19 Từ trường 90", "Bài 20: Chế tạo nam châm điện 95"]
    entries, _ = parse_toc_lines(lines)
    assert [(e.bai_so, e.start_page) for e in entries] == [(19, 90), (20, 95)]
