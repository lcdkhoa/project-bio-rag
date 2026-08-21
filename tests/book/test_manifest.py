import json

import pytest

from src.etl.book.manifest import (
    MANIFEST_VERSION, book_id_from_source_name, build_manifest, load_manifest,
    printed_page_lookup, save_manifest,
)
from src.etl.book.page_map import NumberCandidate
from src.etl.book.toc import TocChuong, TocEntry, TocResult

from .conftest import page_of


def _build(source, *, numbers=None, toc=(), chuongs=(), toc_pages=(),
           banners=None):
    """Ba adapter giả, tra theo SỐ TRANG đọc từ pixel — không đếm lượt gọi.

    `numbers`: {page_index: printed_value}; side suy theo luật parity.
    `toc`: [(bai_so, title, SỐ TRANG IN)]. `toc_pages`: page_index của MỤC LỤC.
    `banners`: {page_index: bai_so hoặc tập bai_so} — huy hiệu trả về TẬP ứng
    viên, nên một `int` ở đây được bọc thành tập một phần tử.
    """
    numbers = numbers or {}

    def read(image_bgr):
        value = numbers.get(page_of(image_bgr))
        if value is None:
            return []
        return [NumberCandidate(value=value, conf=88.0,
                                side="L" if value % 2 == 0 else "R")]

    result = TocResult(
        entries=[TocEntry(bai_so, title, printed) for bai_so, title, printed in toc],
        chuongs=[TocChuong(*c) for c in chuongs],
        page_indices=list(toc_pages))

    def banner(image_bgr):
        found = (banners or {}).get(page_of(image_bgr))
        if found is None:
            return frozenset()
        return frozenset(found if isinstance(found, (set, frozenset)) else {found})

    return build_manifest(source,
                          read_candidates=read,
                          read_toc=lambda src: result,
                          detect_banner=banner)


def test_book_id_maps_the_folder_name_to_a_book_id():
    assert book_id_from_source_name("SGK_KHTN_6_KNTT") == "KHTN6-KNTT"
    assert book_id_from_source_name("SGK_KHTN_9_KNTT") == "KHTN9-KNTT"
    assert book_id_from_source_name("SGK-KHTN-Lop-6.pdf") == "KHTN6-KNTT"


def test_book_id_from_an_unexpected_name_is_the_stem():
    assert book_id_from_source_name("something-else") == "something-else"


def test_build_manifest_fills_pages_bai_and_source_hash(png_book):
    source = png_book(range(1, 9))
    # printed_page == page_index - 1 (đo được trên cả 4 quyển) -> offset -1
    manifest = _build(source,
                      numbers={i: i - 1 for i in range(1, 9)},
                      toc=[(1, "Mở đầu", 4)], chuongs=[("I", "A", 1)])
    assert manifest.book_id == "KHTN6-KNTT"
    assert manifest.source_name == "SGK_KHTN_6_KNTT"
    assert manifest.n_pages == 8
    assert manifest.page_offset == -1
    assert manifest.offset_votes == [8, 8]
    assert len(manifest.pages) == 8
    assert {p["source"] for p in manifest.pages} == {"ocr_confirmed"}
    # TOC ghi trang IN 4 -> page_index 5; Bài cuối kéo tới trang nguồn cuối (8)
    assert manifest.bai == [{"bai_so": 1, "title": "Mở đầu", "start": 5,
                             "end": 8, "source": "toc"}]
    assert manifest.chuong == [{"label": "I", "title": "A", "after_bai": 1}]
    assert len(manifest.source_hash) == 32


def test_build_manifest_flags_pages_whose_number_was_not_read(png_book):
    source = png_book(range(1, 7))
    numbers = {i: i - 1 for i in (1, 2, 3, 5, 6)}     # trang 4 không đọc được
    manifest = _build(source, numbers=numbers)
    page4 = next(p for p in manifest.pages if p["page_index"] == 4)
    assert page4["source"] == "model_inferred"
    assert page4["printed_page"] == 3
    kinds = [f["kind"] for f in manifest.flags]
    assert "page_number_not_read" in kinds
    assert "no_bai_detected" in kinds        # TOC rỗng + không banner
    page_flag = next(f for f in manifest.flags if f["kind"] == "page_number_not_read")
    assert "trang 4" in page_flag["detail"]


def test_build_manifest_flags_no_bai_detected_when_the_spine_is_empty(png_book):
    source = png_book(range(1, 5))
    manifest = _build(source, numbers={i: i - 1 for i in range(1, 5)})
    assert manifest.bai == []
    no_bai = [f for f in manifest.flags if f["kind"] == "no_bai_detected"]
    assert len(no_bai) == 1
    assert "KHTN6-KNTT" in no_bai[0]["detail"]


def test_build_manifest_marks_the_two_cover_pages_and_skips_nothing_else(png_book):
    # page_001/page_002 = trang in 0 và 1 = bìa + trang tên sách: KHÔNG in số
    # trang, không có nội dung bài -> role "cover" để bước chunk bỏ qua. File
    # nguồn không bị xoá (CẤM #4).
    source = png_book(range(1, 9))
    manifest = _build(source,
                      numbers={i: i - 1 for i in range(3, 9)},
                      toc=[(1, "Mở đầu", 4)])
    roles = {p["page_index"]: p["role"] for p in manifest.pages}
    assert roles[1] == "cover" and roles[2] == "cover"
    assert roles[3] == "front_matter" and roles[4] == "front_matter"
    assert roles[5] == "content" and roles[8] == "content"


def test_build_manifest_tags_pages_with_their_bai(png_book):
    source = png_book(range(1, 9))
    manifest = _build(source,
                      numbers={i: i - 1 for i in range(1, 9)},
                      toc=[(1, "Mở đầu", 4)])
    pages = {p["page_index"]: p for p in manifest.pages}
    assert pages[6]["bai_so"] == 1
    assert pages[1]["bai_so"] is None


def test_the_toc_page_wins_and_a_badge_elsewhere_is_only_flagged(png_book):
    """Vai đã đảo (D-43): MỤC LỤC đọc gần đủ và tự nhất quán, huy hiệu đọc ~2/3
    kèm ca mâu thuẫn — nên huy hiệu KHÔNG được dời trang bắt đầu của Bài."""
    source = png_book(range(1, 12))
    manifest = _build(source,
                      numbers={i: i - 1 for i in range(1, 12)},
                      toc=[(1, "Mở đầu", 4)],
                      banners={9: 1})
    assert manifest.bai[0]["start"] == 5          # trang IN 4 -> page_index 5
    # Huy hiệu Bài 1 ở trang 9 là trang TIẾP của Bài 1 (KNTT in lại nhãn), nên
    # không phải Bài lạ -> không kêu. Cái phải giữ là: nó không dời `start`.
    assert manifest.flags == []
    assert manifest.banner_votes == [0, 1]


def test_a_badge_on_the_bai_start_page_confirms_it(png_book):
    source = png_book(range(1, 12))
    manifest = _build(source,
                      numbers={i: i - 1 for i in range(1, 12)},
                      toc=[(1, "Mở đầu", 4)],
                      banners={5: 1})
    assert manifest.bai[0]["source"] == "toc+banner"
    assert manifest.banner_votes == [1, 1]


def test_banner_detection_skips_the_toc_pages(png_book):
    # MỤC LỤC nhiều màu và đầy chữ "Bài N" -> detector khớp và sinh một Bài giả
    # ngay đầu quyển. Đo được trên sách 6 ("Bài 20 ở trang 6") và sách 7
    # ("Bài 19 ở trang 6") — cả hai trang 6 đều LÀ trang MỤC LỤC.
    source = png_book(range(1, 12))
    manifest = _build(source,
                      numbers={i: i - 1 for i in range(1, 12)},
                      toc_pages=(5, 6),
                      banners={5: 20, 6: 20, 9: 1})
    assert [b["bai_so"] for b in manifest.bai] == [1]
    assert manifest.bai[0]["start"] == 9


def test_build_manifest_flags_a_non_contiguous_bai_spine(png_book):
    # Spine đầy đủ thì số Bài là 1..k. {1, 5} nghĩa là thiếu 2,3,4 -> spine là
    # giả thuyết vá lỗ, phải nói ra (không chặn G1, nhưng phải thấy được).
    source = png_book(range(1, 12))
    manifest = _build(source,
                      numbers={i: i - 1 for i in range(1, 12)},
                      banners={7: 1, 10: 5})
    flag = next(f for f in manifest.flags
                if f["kind"] == "bai_numbers_not_contiguous")
    assert "[2, 3, 4]" in flag["detail"]


def test_toc_pages_are_converted_from_printed_to_page_index(png_book):
    # Sách có 4 trang đầu không số: trang in 1 nằm ở page_index 6 -> offset -5.
    # Dòng TOC "Bài 1 … 1" là SỐ TRANG IN và phải rơi vào page_index 6.
    source = png_book(range(1, 9))
    manifest = _build(source, numbers={6: 1, 7: 2, 8: 3},
                      toc=[(1, "Mở đầu", 1)])
    assert manifest.page_offset == -5
    assert manifest.bai[0]["start"] == 6
    pages = {p["page_index"]: p for p in manifest.pages}
    assert pages[6]["bai_so"] == 1
    assert pages[5]["bai_so"] is None


def test_build_manifest_flags_a_gap_in_the_source_pages(png_book):
    # Sách 9 từng thiếu 19 file trang. Thiếu trang là THIẾU DỮ LIỆU: flag ra,
    # không bịa record cho trang không tồn tại.
    source = png_book([1, 2, 3, 6, 7])
    manifest = _build(source, numbers={i: i - 1 for i in (1, 2, 3, 6, 7)})
    assert [p["page_index"] for p in manifest.pages] == [1, 2, 3, 6, 7]
    gap = next(f for f in manifest.flags if f["kind"] == "missing_source_pages")
    assert "[4, 5]" in gap["detail"]


def test_build_manifest_does_not_flag_a_contiguous_book(png_book):
    source = png_book(range(1, 6))
    manifest = _build(source, numbers={i: i - 1 for i in range(1, 6)})
    assert [f["kind"] for f in manifest.flags
            if f["kind"] == "missing_source_pages"] == []


def test_save_and_load_manifest_round_trips(png_book, tmp_path):
    source = png_book(range(1, 5))
    manifest = _build(source, numbers={i: i - 1 for i in range(1, 5)})
    path = save_manifest(manifest, tmp_path / "manifests")
    assert path.name == "KHTN6-KNTT.json"
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["manifest_version"] == MANIFEST_VERSION
    assert load_manifest(path) == manifest


def test_load_manifest_refuses_an_older_manifest_version(tmp_path):
    # Manifest v1 dùng `pdf_index` 0-based: đọc nó ở đây sẽ lệch đúng 1 trang
    # trên mọi citation -> phải fail loudly, không đọc "cho có".
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"manifest_version": 1, "pages": []}),
                    encoding="utf-8")
    with pytest.raises(ValueError):
        load_manifest(path)


def test_printed_page_lookup_maps_page_index_to_printed_page(png_book):
    source = png_book(range(1, 5))
    manifest = _build(source, numbers={i: i - 1 for i in range(1, 5)})
    assert printed_page_lookup(manifest) == {1: 0, 2: 1, 3: 2, 4: 3}
