from src.etl.book.manifest import BookManifest
from src.etl.book.report import g1_check, g1_report


def _manifest(confirmed, total, flags=()):
    pages = [{"pdf_index": i, "printed_page": i,
              "source": "ocr_confirmed" if i < confirmed else "model_inferred",
              "side": "L", "conf": 90.0, "bai_so": None, "role": "content"}
             for i in range(total)]
    return BookManifest(book_id="KHTN6-KNTT", pdf_name="SGK-KHTN-Lop-6.pdf",
                        pdf_hash="x" * 32, n_pages=total, page_offset=0,
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


def test_g1_tolerates_page_number_not_read_flags_within_the_ratio():
    ok, _ = g1_check(_manifest(96, 100, flags=("page_number_not_read",) * 4))
    assert ok


def test_g1_report_lists_every_book_with_its_numbers():
    text = g1_report([_manifest(96, 100)])
    assert "KHTN6-KNTT" in text and "96" in text and "offset" in text
