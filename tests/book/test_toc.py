"""Test bộ đọc MỤC LỤC dạng bảng.

Tách hai tầng: `parse_toc_rows` là logic thuần (không OCR) nên test được mọi luật
đúng/sai; phần hình học test bằng ảnh tổng hợp nhỏ, không cần Tesseract.
"""
import cv2
import numpy as np

from src.etl.book.toc import (TocChuong, TocEntry, TocRow, number_column,
                              parse_toc_rows, row_bands)


def _row(text, candidates=(), page_index=5):
    return TocRow(page_index=page_index, candidates=frozenset(candidates),
                  text=text)


def test_reads_bai_number_from_text_and_page_from_the_number_cell():
    rows = [_row("Bài 6. Đo khối lượng", {20}),
            _row("Bài 7. Đo thời gian", {22})]
    result = parse_toc_rows(rows)
    assert result.entries == [TocEntry(6, "Đo khối lượng", 20),
                              TocEntry(7, "Đo thời gian", 22)]
    assert result.flags == []


def test_monotonic_constraint_picks_the_uncut_candidate():
    # Lỗi đã đo: chữ số nhỏ bị Tesseract cắt cụt nên ô đọc ra cả "16" lẫn "166".
    # Ràng buộc "số trang không giảm" loại 16 mà không cần đoán gì.
    rows = [_row("Bài 37. Các quy luật di truyền", {162}),
            _row("Bài 38. Nucleic acid và gene", {16, 166})]
    result = parse_toc_rows(rows)
    assert [(e.bai_so, e.start_page) for e in result.entries] == [(37, 162), (38, 166)]
    assert [f["kind"] for f in result.flags] == []


def test_flags_when_more_than_one_candidate_survives_the_constraint():
    rows = [_row("Bài 3. Cơ năng", {18}),
            _row("Bài 4. Công và công suất", {21, 210})]
    result = parse_toc_rows(rows)
    assert result.entries[-1].start_page == 21
    assert [f["kind"] for f in result.flags] == ["toc_page_ambiguous"]


def test_drops_the_entry_when_no_candidate_fits_and_never_invents_one():
    rows = [_row("Bài 38. Nucleic acid", {166}),
            _row("Bài 39. Tái bản DNA", {19}),      # thật là 169, OCR cắt cụt
            _row("Bài 40. Dịch mã", {173})]
    result = parse_toc_rows(rows)
    assert [e.bai_so for e in result.entries] == [38, 40]
    assert [f["kind"] for f in result.flags] == ["toc_page_unreadable"]


def test_rescue_is_only_called_for_a_row_the_fast_read_could_not_resolve():
    calls = []

    def rescue(position, row):
        calls.append(position)
        return {169}

    rows = [_row("Bài 38. Nucleic acid", {166}),
            _row("Bài 39. Tái bản DNA", {19}),
            _row("Bài 40. Dịch mã", {173})]
    result = parse_toc_rows(rows, rescue=rescue)
    assert calls == [1]
    assert [(e.bai_so, e.start_page) for e in result.entries] == [
        (38, 166), (39, 169), (40, 173)]
    assert result.flags == []


def test_reads_a_bai_number_ocred_as_a_roman_looking_one():
    # Đo được trên corpus thật: "Bài 1" ra "Bài I", "Bài 41" ra "Bài 4l".
    rows = [_row("Bài I Sử dụng một số hoá chất", {6}),
            _row("Bài 4l Môi trường và các nhân tố sinh thái", {170})]
    result = parse_toc_rows(rows)
    assert [(e.bai_so, e.start_page) for e in result.entries] == [(1, 6), (41, 170)]


def test_ignores_a_bai_mention_inside_a_title():
    # "Bài 10. Kính lúp. Bài tập thấu kính" — chỉ số đầu dòng mới là số Bài.
    rows = [_row("Bài 10. Kính lúp. Bài tập thấu kính", {50})]
    result = parse_toc_rows(rows)
    assert [(e.bai_so, e.title) for e in result.entries] == [
        (10, "Kính lúp. Bài tập thấu kính")]


def test_ignores_a_row_whose_bai_number_does_not_increase():
    rows = [_row("Bài 12. Một số vật liệu", {42}),
            _row("Bài 2 rác OCR", {46})]
    result = parse_toc_rows(rows)
    assert [e.bai_so for e in result.entries] == [12]


def test_collects_chuong_headings_and_the_bai_they_follow():
    rows = [_row("Bài 1. Giới thiệu", {7}),
            _row("CHƯƠNG II - CHẤT QUANH TA", {28}),
            _row("Bài 9. Sự đa dạng của chất", {28})]
    result = parse_toc_rows(rows)
    assert result.chuongs == [TocChuong("II", "CHẤT QUANH TA", 1)]
    assert [(e.bai_so, e.start_page) for e in result.entries] == [(1, 7), (9, 28)]


def test_skips_front_matter_rows_without_a_bai_number():
    result = parse_toc_rows([_row("Hướng dẫn sử dụng sách", {2}),
                             _row("Lời nói đầu", {3})])
    assert result.entries == []


# ------------------------------------------------------------- hình học

def _ruled_table(width=400, height=600):
    """Bảng kẻ khung hai cột: nội dung | số trang (kiểu sách 6/9)."""
    image = np.full((height, width, 3), 255, np.uint8)
    for x in (40, 300, 370):                      # ba đường kẻ dọc
        cv2.line(image, (x, 60), (x, height - 60), (200, 120, 40), 3)
    for index in range(6):                        # chữ trong hai cột
        y = 100 + index * 60
        cv2.putText(image, "Bai", (60, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (0, 0, 0), 2)
        cv2.putText(image, "20", (320, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (0, 0, 0), 2)
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def test_number_column_sits_between_the_last_two_vertical_rules():
    column, how = number_column(_ruled_table())
    assert how == "rules"
    assert 300 < column[0] and column[1] < 370


def test_number_column_falls_back_to_the_rightmost_ink_group_without_rules():
    """Sách 7/8 dùng dải màu, không kẻ khung -> phải dùng khoảng trắng."""
    image = np.full((600, 400, 3), 255, np.uint8)
    for index in range(6):
        y = 100 + index * 60
        cv2.putText(image, "Bai", (60, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (0, 0, 0), 2)
        cv2.putText(image, "20", (330, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (0, 0, 0), 2)
    column, how = number_column(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
    assert how == "gutter"
    assert column[0] >= 300


def test_row_bands_find_one_band_per_number():
    gray = _ruled_table()
    column, _ = number_column(gray)
    assert len(row_bands(gray, *column)) == 6
