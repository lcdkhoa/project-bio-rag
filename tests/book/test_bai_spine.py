from src.etl.book.bai_spine import BannerHit, build_bai_spine
from src.etl.book.toc import TocEntry


def test_banner_and_toc_agreeing_yields_a_clean_spine():
    toc = [TocEntry(6, "Đo khối lượng", 20), TocEntry(7, "Đo thời gian", 22)]
    banners = [BannerHit(20, 6), BannerHit(22, 7)]
    spine, flags = build_bai_spine(toc, banners, n_pages=24)
    assert [(b.bai_so, b.start, b.end, b.source) for b in spine] == [
        (6, 20, 21, "banner+toc"), (7, 22, 23, "banner+toc")]
    assert flags == []


def test_banner_page_wins_when_toc_page_disagrees():
    # Measured: the TOC misprints/mis-OCRs page numbers. The banner is the real
    # page, so it wins - and the disagreement is flagged, never swallowed.
    toc = [TocEntry(24, "Cường độ dòng điện", 90)]
    banners = [BannerHit(98, 24)]
    spine, flags = build_bai_spine(toc, banners, n_pages=100)
    assert spine[0].start == 98
    assert [f.kind for f in flags] == ["toc_page_mismatch"]
    assert "24" in flags[0].detail


def test_repairs_a_truncated_bai_number_using_the_monotonic_constraint():
    # Real OCR failure: "Bài 31" read as "Bài 3" between 30 and 32.
    toc = [TocEntry(30, "A", 120), TocEntry(31, "B", 125), TocEntry(32, "C", 128)]
    banners = [BannerHit(120, 30), BannerHit(125, 3), BannerHit(128, 32)]
    spine, flags = build_bai_spine(toc, banners, n_pages=130)
    assert [b.bai_so for b in spine] == [30, 31, 32]
    assert [f.kind for f in flags] == ["bai_so_repaired"]
    assert "3 -> 31" in flags[0].detail


def test_drops_an_unrepairable_out_of_order_banner_and_flags_it():
    # No TOC number fits between 30 and 32 that starts with "7" -> refuse to
    # guess: drop the hit, flag it, keep the spine monotonic.
    toc = [TocEntry(30, "A", 120), TocEntry(32, "C", 128)]
    banners = [BannerHit(120, 30), BannerHit(124, 7), BannerHit(128, 32)]
    spine, flags = build_bai_spine(toc, banners, n_pages=130)
    assert [b.bai_so for b in spine] == [30, 32]
    assert [f.kind for f in flags] == ["banner_out_of_order"]


def test_falls_back_to_the_toc_page_when_no_banner_was_detected():
    toc = [TocEntry(6, "Đo khối lượng", 20), TocEntry(7, "Đo thời gian", 22)]
    banners = [BannerHit(20, 6)]
    spine, flags = build_bai_spine(toc, banners, n_pages=24)
    assert [(b.bai_so, b.start, b.source) for b in spine] == [
        (6, 20, "banner+toc"), (7, 22, "toc")]
    assert [f.kind for f in flags] == ["toc_without_banner"]


def test_keeps_a_banner_with_no_toc_entry_and_flags_the_missing_title():
    banners = [BannerHit(20, 6)]
    spine, flags = build_bai_spine([], banners, n_pages=24)
    assert [(b.bai_so, b.title, b.source) for b in spine] == [(6, "", "banner")]
    assert [f.kind for f in flags] == ["banner_without_toc"]


def test_end_of_the_last_bai_reaches_the_last_page():
    spine, _ = build_bai_spine([TocEntry(6, "X", 20)], [BannerHit(20, 6)],
                               n_pages=25)
    assert spine[0].end == 24


def test_duplicate_banner_for_the_same_bai_keeps_the_first_page():
    toc = [TocEntry(6, "X", 20)]
    banners = [BannerHit(20, 6), BannerHit(21, 6)]
    spine, flags = build_bai_spine(toc, banners, n_pages=23)
    assert [(b.bai_so, b.start, b.end) for b in spine] == [(6, 20, 22)]
    assert [f.kind for f in flags] == ["banner_out_of_order"]


def test_empty_inputs_produce_an_empty_spine_without_crashing():
    spine, flags = build_bai_spine([], [], n_pages=10)
    assert spine == [] and flags == []


def test_refuses_to_repair_when_upper_bound_is_absent():
    # Real failure mode: OCR truncates "Bài 20" to "Bài 2", it is the last hit,
    # and no later banner provides an upper bound. TOC lists 19 and 25 but not 20-24.
    # The repair rule must refuse — it would invent "2 -> 25" (unique in (19, None))
    # which is wrong. Instead, drop the hit and flag it, leaving lesson 20 recoverable
    # as a flagged toc_without_banner.
    toc = [TocEntry(19, "A", 100), TocEntry(25, "B", 200)]
    banners = [BannerHit(100, 19), BannerHit(150, 2)]
    spine, flags = build_bai_spine(toc, banners, n_pages=250)
    assert [b.bai_so for b in spine] == [19, 25]
    # Should NOT repair "2" — should drop it
    assert not any(f.kind == "bai_so_repaired" for f in flags)
    # Should flag the drop with explanation of absent upper bound
    assert any(f.kind == "banner_out_of_order" for f in flags)
    out_of_order_flag = [f for f in flags if f.kind == "banner_out_of_order"][0]
    assert "upper bound" in out_of_order_flag.detail.lower() or "không" in out_of_order_flag.detail


def test_flags_toc_only_lesson_that_breaks_monotonic_order():
    # A TOC-only lesson (no banner) has a corrupted page number that would place it
    # before an earlier-numbered lesson. The spine is built in page order (necessary
    # for computing end ranges), but the violation must be flagged as spine_out_of_order.
    # The record is NOT dropped.
    toc = [TocEntry(5, "A", 50), TocEntry(6, "B", 10)]  # Bài 6's page (10) < Bài 5's page (50)
    banners = [BannerHit(50, 5)]  # Only 5 has a banner
    spine, flags = build_bai_spine(toc, banners, n_pages=100)
    # Spine contains both lessons, sorted by page (not dropped)
    assert len(spine) == 2
    assert [b.bai_so for b in spine] == [6, 5]  # page order: 10 < 50
    # The violation must be flagged
    assert any(f.kind == "spine_out_of_order" for f in flags)
    spine_out_of_order_flag = [f for f in flags if f.kind == "spine_out_of_order"][0]
    assert "5" in spine_out_of_order_flag.detail and "6" in spine_out_of_order_flag.detail
