"""Test spine Bài với vai mới: MỤC LỤC dựng spine, huy hiệu chỉ xác nhận (D-43)."""
from src.etl.book.bai_spine import banner_agreement, build_bai_spine
from src.etl.book.toc import TocEntry


def test_toc_builds_the_spine_and_a_matching_badge_confirms_it():
    toc = [TocEntry(6, "Đo khối lượng", 20), TocEntry(7, "Đo thời gian", 22)]
    banners = {20: frozenset({6}), 22: frozenset({7})}
    spine, flags = build_bai_spine(toc, banners, last_page_index=23)
    assert [(b.bai_so, b.start, b.end, b.source) for b in spine] == [
        (6, 20, 21, "toc+banner"), (7, 22, 23, "toc+banner")]
    assert flags == []
    assert banner_agreement(spine) == (2, 2)


def test_a_bai_with_no_badge_is_kept_without_a_flag():
    """Huy hiệu đọc được ~2/3 số trang mở Bài, nên 'không thấy huy hiệu' là
    chuyện bình thường đã đo — không phải mâu thuẫn, không được chặn G1."""
    toc = [TocEntry(6, "Đo khối lượng", 20), TocEntry(7, "Đo thời gian", 22)]
    spine, flags = build_bai_spine(toc, {20: frozenset({6})}, last_page_index=23)
    assert [(b.bai_so, b.source) for b in spine] == [(6, "toc+banner"), (7, "toc")]
    assert flags == []
    assert banner_agreement(spine) == (1, 2)


def test_the_toc_wins_when_the_badge_disagrees_and_the_clash_is_flagged():
    # Đo được: cùng một huy hiệu đọc ra hai số (Bài 13 ra cả 13 lẫn 15). Nguồn
    # như thế không được ghi đè MỤC LỤC — nhưng cũng không được nuốt im lặng.
    toc = [TocEntry(13, "Khối lượng riêng", 56)]
    spine, flags = build_bai_spine(toc, {56: frozenset({15})}, last_page_index=60)
    assert spine[0].bai_so == 13 and spine[0].source == "toc"
    assert [f.kind for f in flags] == ["banner_toc_mismatch"]
    assert "13" in flags[0].detail and "15" in flags[0].detail


def test_a_badge_reading_both_the_right_and_a_wrong_number_still_confirms():
    toc = [TocEntry(13, "Khối lượng riêng", 56)]
    spine, flags = build_bai_spine(toc, {56: frozenset({13, 15})},
                                   last_page_index=60)
    assert spine[0].source == "toc+banner"
    assert flags == []


def test_a_badge_on_a_page_the_toc_never_mentions_is_flagged_not_added():
    toc = [TocEntry(6, "Đo khối lượng", 20)]
    spine, flags = build_bai_spine(toc, {31: frozenset({9})}, last_page_index=40)
    assert [b.bai_so for b in spine] == [6]        # KHÔNG tự thêm Bài 9
    assert [f.kind for f in flags] == ["banner_without_toc"]


def test_a_badge_repeating_a_bai_on_a_later_page_is_not_flagged():
    """Bài 6 mở ở trang 20; huy hiệu còn in lại ở trang 21 (trang tiếp của Bài).
    Đó không phải Bài lạ, nên không được kêu."""
    toc = [TocEntry(6, "Đo khối lượng", 20)]
    spine, flags = build_bai_spine(toc, {21: frozenset({6})}, last_page_index=25)
    assert flags == []


def test_falls_back_to_badges_when_the_toc_is_empty():
    spine, flags = build_bai_spine([], {20: frozenset({6}), 25: frozenset({7})},
                                   last_page_index=30)
    assert [(b.bai_so, b.start, b.source) for b in spine] == [
        (6, 20, "banner"), (7, 25, "banner")]
    assert [f.kind for f in flags] == ["toc_empty"]
    # 0/2: không nguồn ĐỘC LẬP nào xác nhận — banner vừa dựng vừa tự xác nhận
    # thì con số đối chiếu phải bằng 0, không được tự khen.
    assert banner_agreement(spine) == (0, 2)


def test_an_ambiguous_badge_is_dropped_when_it_is_the_only_source():
    """Không có MỤC LỤC để đối chiếu thì một huy hiệu đọc ra hai số là vô dụng —
    bỏ, không chọn bừa."""
    spine, flags = build_bai_spine([], {20: frozenset({6, 8})}, last_page_index=30)
    assert spine == []
    assert sorted(f.kind for f in flags) == ["banner_ambiguous", "toc_empty"]


def test_out_of_order_bai_numbers_are_flagged():
    toc = [TocEntry(9, "A", 30), TocEntry(8, "B", 35)]
    spine, flags = build_bai_spine(toc, {}, last_page_index=40)
    assert [f.kind for f in flags] == ["spine_out_of_order"]


def test_the_last_bai_runs_to_the_last_source_page():
    toc = [TocEntry(54, "Hệ Mặt Trời", 188), TocEntry(55, "Ngân Hà", 191)]
    spine, _ = build_bai_spine(toc, {}, last_page_index=196)
    assert (spine[-1].start, spine[-1].end) == (191, 196)
    assert (spine[0].start, spine[0].end) == (188, 190)
