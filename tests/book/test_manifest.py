import json

import fitz
import numpy as np
import pytest

from src.etl.book.manifest import (
    BookManifest, book_id_from_filename, build_manifest, load_manifest,
    printed_page_lookup, save_manifest,
)
from src.etl.book.page_map import NumberCandidate


def _make_pdf(tmp_path, name="SGK-KHTN-Lop-6.pdf", pages=8):
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=595, height=842)
    path = tmp_path / name
    doc.save(str(path))
    doc.close()
    return str(path)


def _fake_candidates(numbers):
    """numbers: {pdf_index: printed_value}. Side follows the parity rule."""
    def read(image_bgr):
        index = read.calls
        read.calls += 1
        value = numbers.get(index)
        if value is None:
            return []
        return [NumberCandidate(value=value, conf=88.0,
                                side="L" if value % 2 == 0 else "R")]
    read.calls = 0
    return read


def test_book_id_from_filename_maps_grade_to_a_kntt_book_id():
    assert book_id_from_filename("SGK-KHTN-Lop-6.pdf") == "KHTN6-KNTT"
    assert book_id_from_filename("SGK-KHTN-Lop-9.pdf") == "KHTN9-KNTT"


def test_book_id_from_an_unexpected_filename_is_the_stem():
    assert book_id_from_filename("something-else.pdf") == "something-else"


def test_build_manifest_fills_pages_bai_and_hash(tmp_path):
    pdf = _make_pdf(tmp_path, pages=8)
    manifest = build_manifest(
        pdf,
        read_candidates=_fake_candidates({i: i for i in range(8)}),
        read_toc=lambda path: ["Bài 1. Mở đầu 4", "CHƯƠNG I - A"],
        detect_banner=lambda img: None,
    )
    assert manifest.book_id == "KHTN6-KNTT"
    assert manifest.n_pages == 8
    assert manifest.page_offset == 0
    assert manifest.offset_votes == [8, 8]
    assert len(manifest.pages) == 8
    assert {p["source"] for p in manifest.pages} == {"ocr_confirmed"}
    assert manifest.bai == [{"bai_so": 1, "title": "Mở đầu", "start": 4,
                             "end": 7, "source": "toc"}]
    assert manifest.chuong == [{"label": "I", "title": "A", "after_bai": 1}]
    assert len(manifest.pdf_hash) == 32          # md5 hex, same as the checkpoint


def test_build_manifest_flags_pages_whose_number_was_not_read(tmp_path):
    pdf = _make_pdf(tmp_path, pages=6)
    manifest = build_manifest(
        pdf,
        read_candidates=_fake_candidates({0: 0, 1: 1, 2: 2, 4: 4, 5: 5}),
        read_toc=lambda path: [],
        detect_banner=lambda img: None,
    )
    assert manifest.pages[3]["source"] == "model_inferred"
    assert manifest.pages[3]["printed_page"] == 3
    # Empty TOC + no banners also means zero Bài were resolved for this book,
    # so build_manifest now also raises no_bai_detected (review round 1, finding 2).
    kinds = [f["kind"] for f in manifest.flags]
    assert "page_number_not_read" in kinds
    assert "no_bai_detected" in kinds
    page_flag = next(f for f in manifest.flags if f["kind"] == "page_number_not_read")
    assert "3" in page_flag["detail"]


def test_build_manifest_flags_no_bai_detected_when_the_spine_is_empty(tmp_path):
    # No banners fire and the TOC yields no entries -> zero Bài were resolved.
    # This must be flagged (and later blocked by G1) rather than silently
    # accepted as an all-front_matter book (review round 1, finding 2).
    pdf = _make_pdf(tmp_path, pages=4)
    manifest = build_manifest(
        pdf,
        read_candidates=_fake_candidates({i: i for i in range(4)}),
        read_toc=lambda path: [],
        detect_banner=lambda img: None,
    )
    assert manifest.bai == []
    no_bai_flags = [f for f in manifest.flags if f["kind"] == "no_bai_detected"]
    assert len(no_bai_flags) == 1
    assert "KHTN6-KNTT" in no_bai_flags[0]["detail"]


def test_build_manifest_tags_pages_with_their_bai_and_role(tmp_path):
    pdf = _make_pdf(tmp_path, pages=8)
    manifest = build_manifest(
        pdf,
        read_candidates=_fake_candidates({i: i for i in range(8)}),
        read_toc=lambda path: ["Bài 1. Mở đầu 4"],
        detect_banner=lambda img: None,
    )
    roles = [p["role"] for p in manifest.pages]
    assert roles[:4] == ["front_matter"] * 4
    assert roles[4:] == ["content"] * 4
    assert manifest.pages[5]["bai_so"] == 1
    assert manifest.pages[0]["bai_so"] is None


def test_build_manifest_uses_the_banner_page_over_the_toc_page(tmp_path):
    pdf = _make_pdf(tmp_path, pages=8)
    banners = {6: 1}

    def detect(image_bgr):
        detect.calls += 1
        return banners.get(detect.calls - 1)
    detect.calls = 0

    manifest = build_manifest(
        pdf,
        read_candidates=_fake_candidates({i: i for i in range(8)}),
        read_toc=lambda path: ["Bài 1. Mở đầu 4"],
        detect_banner=detect,
    )
    assert manifest.bai[0]["start"] == 6
    assert "toc_page_mismatch" in [f["kind"] for f in manifest.flags]


def test_toc_pages_are_converted_from_printed_to_pdf_index(tmp_path):
    # A book with unnumbered cover pages: printed page 1 sits at pdf_index 5, so
    # the offset model fits -4. A TOC row "Bài 1 ... 1" is a PRINTED page and must
    # land on pdf_index 5 in the spine. With offset 0 the two coincide, so this is
    # the only test that can catch the coordinate-space slip.
    pdf = _make_pdf(tmp_path, pages=8)
    manifest = build_manifest(
        pdf,
        read_candidates=_fake_candidates({5: 1, 6: 2, 7: 3}),
        read_toc=lambda path: ["Bài 1. Mở đầu 1"],
        detect_banner=lambda img: None,
    )
    assert manifest.page_offset == -4
    assert manifest.bai[0]["start"] == 5
    assert manifest.pages[5]["bai_so"] == 1
    assert manifest.pages[4]["bai_so"] is None


def test_save_and_load_manifest_round_trips(tmp_path):
    pdf = _make_pdf(tmp_path, pages=4)
    manifest = build_manifest(
        pdf,
        read_candidates=_fake_candidates({i: i for i in range(4)}),
        read_toc=lambda path: [],
        detect_banner=lambda img: None,
    )
    path = save_manifest(manifest, tmp_path / "manifests")
    assert path.name == "KHTN6-KNTT.json"
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["manifest_version"] == 1
    assert load_manifest(path) == manifest


def test_printed_page_lookup_maps_index_to_printed_page(tmp_path):
    pdf = _make_pdf(tmp_path, pages=4)
    manifest = build_manifest(
        pdf,
        read_candidates=_fake_candidates({i: i for i in range(4)}),
        read_toc=lambda path: [],
        detect_banner=lambda img: None,
    )
    assert printed_page_lookup(manifest) == {0: 0, 1: 1, 2: 2, 3: 3}
