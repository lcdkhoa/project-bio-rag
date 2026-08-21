from src.etl.book.manifest import BookManifest
from src.etl.book.report import g1_check, g1_report


def _manifest(confirmed, total, flags=(), covers=0):
    """`covers` trang đầu mang role "cover" (không in số trang -> ngoài mẫu số)."""
    pages = [{"page_index": i + 1, "printed_page": i,
              "source": "ocr_confirmed" if i < confirmed else "model_inferred",
              "side": "L", "conf": 90.0, "bai_so": None,
              "role": "cover" if i < covers else "content"}
             for i in range(total)]
    return BookManifest(book_id="KHTN6-KNTT", source_name="SGK_KHTN_6_KNTT",
                        source_hash="x" * 32, n_pages=total, page_offset=-1,
                        offset_votes=[confirmed, total], pages=pages, bai=[],
                        chuong=[], flags=[{"kind": k, "detail": ""} for k in flags])


def test_g1_passes_when_every_page_has_a_number_and_confirmation_is_high():
    ok, problems = g1_check(_manifest(96, 100))
    assert ok and problems == []


def test_g1_fails_when_confirmation_ratio_is_below_the_threshold():
    ok, problems = g1_check(_manifest(80, 100))
    assert not ok
    assert any("ocr_confirmed" in p for p in problems)


def test_g1_fails_on_an_unresolved_spine_conflict():
    ok, problems = g1_check(_manifest(100, 100, flags=("banner_out_of_order",)))
    assert not ok
    assert any("banner_out_of_order" in p for p in problems)


def test_g1_fails_on_a_spine_out_of_order_conflict():
    ok, problems = g1_check(_manifest(100, 100, flags=("spine_out_of_order",)))
    assert not ok
    assert any("spine_out_of_order" in p for p in problems)


def test_g1_fails_on_a_no_bai_detected_conflict():
    ok, problems = g1_check(_manifest(100, 100, flags=("no_bai_detected",)))
    assert not ok
    assert any("no_bai_detected" in p for p in problems)


def test_g1_tolerates_page_number_not_read_flags_within_the_ratio():
    ok, _ = g1_check(_manifest(96, 100, flags=("page_number_not_read",) * 4))
    assert ok


def test_g1_tolerates_banner_without_toc_because_the_banner_still_gives_a_page():
    # banner_without_toc means a banner fired but the TOC has no matching entry
    # for it -- one source (TOC) is silent while the other (banner) still gives
    # an authoritative start page; only the title is missing. This is a known,
    # measured corpus failure mode (dropped TOC lessons), not a contradiction
    # between two sources, so G1 must not block on it (review round 1, finding 1).
    ok, problems = g1_check(_manifest(100, 100, flags=("banner_without_toc",)))
    assert ok
    assert problems == []


def test_g1_report_lists_every_book_with_its_numbers():
    text = g1_report([_manifest(96, 100)])
    assert "KHTN6-KNTT" in text and "96" in text and "offset" in text


def test_g1_excludes_cover_pages_from_the_confirmation_ratio():
    # Hai trang bìa mỗi quyển THẬT SỰ không in số trang, nên `model_inferred` ở
    # đó là đúng. Để chúng trong mẫu số là đo lẫn "adapter đọc kém" với "trang
    # không có gì để đọc" — và với sách 20 trang thì 2 bìa đã kéo tỉ lệ xuống 90%.
    ok, problems = g1_check(_manifest(confirmed=0, total=20, covers=2))
    assert not ok          # 18 trang có số mà 0 trang đọc được -> vẫn phải fail

    manifest = _manifest(confirmed=0, total=20, covers=2)
    for page in manifest.pages[2:]:
        page["source"] = "ocr_confirmed"
    ok, problems = g1_check(manifest)
    assert ok and problems == []


def test_g1_report_lists_the_numbered_pages_it_could_not_read():
    manifest = _manifest(confirmed=0, total=4, covers=2)
    manifest.pages[3]["source"] = "ocr_confirmed"
    text = g1_report([manifest])
    assert "KHÔNG đọc được: [3]" in text
    assert "2 bìa không in số" in text


def test_g1_fails_when_source_pages_are_missing():
    ok, problems = g1_check(_manifest(100, 100, flags=("missing_source_pages",)))
    assert not ok
    assert any("missing_source_pages" in p for p in problems)
