import json

import numpy as np
import pytest

from src.etl.layout import loader as L
from src.etl.layout.loader import LayoutOCRLoader, ManifestMissing
from src.etl.layout.regions import Region, RegionType, TextUnit


class FakeSource:
    """PageSource tối giản: trả cùng một trang trắng cho mọi số trang."""

    name = "SGK_KHTN_6_KNTT"

    def __init__(self, page_numbers=(1, 2, 10)):
        self._pages = list(page_numbers)

    def page_numbers(self):
        return list(self._pages)

    def load(self, page_number):
        assert page_number in self._pages
        return np.full((200, 200, 3), 255, np.uint8)

    def content_hash(self, page_number):
        return f"hash{page_number}"


def _write_manifest(tmp_path, pages):
    directory = tmp_path / "manifests"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "KHTN6-KNTT.json").write_text(
        json.dumps({
            "book_id": "KHTN6-KNTT", "source_name": "SGK_KHTN_6_KNTT",
            "source_hash": "x" * 32, "n_pages": len(pages), "page_offset": -1,
            "offset_votes": [1, 1], "pages": pages, "bai": [], "chuong": [],
            "flags": [], "manifest_version": 2,
        }, ensure_ascii=False), encoding="utf-8")
    return directory


def _page(page_index, printed_page, role="content", bai_so=None):
    return {"page_index": page_index, "printed_page": printed_page,
            "source": "ocr_confirmed", "side": "L", "conf": 90.0,
            "bai_so": bai_so, "role": role}


@pytest.fixture
def stubbed_pipeline(monkeypatch):
    monkeypatch.setattr(L, "segment_page",
                        lambda im, v: [Region(RegionType.BODY, (0, 0, 200, 200), 0, {})])
    monkeypatch.setattr(L, "extract_text_units", lambda im, regs, v: [
        TextUnit(RegionType.BODY, "quang hợp là gì", 0, (0, 0, 1, 1))])


def test_load_page_wires_pipeline_and_takes_the_printed_page_from_the_manifest(
        tmp_path, stubbed_pipeline):
    directory = _write_manifest(tmp_path, [_page(10, 9, bai_so=3)])
    docs = LayoutOCRLoader(manifest_dir=directory).load_page(FakeSource(), 10)
    assert len(docs) == 1
    meta = docs[0].metadata
    # SỐ TRANG IN từ manifest (9), không phải page_index 10 và không phải 11
    assert meta["page"] == 9
    assert meta["page_index"] == 10
    # `bai_so` CỐ TÌNH không có trong metadata chunk: spine Bài đo được là còn
    # sai nặng, nên nó ở lại manifest như giả thuyết có flag (nguyên tắc 1).
    assert "bai_so" not in meta
    assert meta["variant"] == "kntt"
    assert meta["region_type"] == "body"
    assert meta["source"] == "SGK_KHTN_6_KNTT"


def test_load_page_skips_cover_pages_without_touching_the_source(
        tmp_path, stubbed_pipeline):
    directory = _write_manifest(tmp_path, [_page(1, 0, role="cover")])

    class Exploding(FakeSource):
        def load(self, page_number):
            raise AssertionError("trang bìa không được OCR")

    assert LayoutOCRLoader(manifest_dir=directory).load_page(Exploding(), 1) == []


def test_load_page_refuses_to_guess_when_there_is_no_manifest(tmp_path):
    with pytest.raises(ManifestMissing):
        LayoutOCRLoader(manifest_dir=tmp_path / "nope").load_page(FakeSource(), 10)


def test_load_page_refuses_a_page_the_manifest_does_not_know(tmp_path,
                                                             stubbed_pipeline):
    # Manifest cũ hơn nguồn (trang tải bù chưa dựng lại manifest): thà dừng còn
    # hơn đoán số trang in.
    directory = _write_manifest(tmp_path, [_page(1, 0, role="cover")])
    with pytest.raises(ManifestMissing):
        LayoutOCRLoader(manifest_dir=directory).load_page(FakeSource(), 10)


def test_load_page_refuses_a_manifest_page_without_a_printed_number(
        tmp_path, stubbed_pipeline):
    page = _page(10, 9)
    page["printed_page"] = None
    directory = _write_manifest(tmp_path, [page])
    with pytest.raises(ManifestMissing):
        LayoutOCRLoader(manifest_dir=directory).load_page(FakeSource(), 10)


def test_load_book_walks_the_real_page_numbers_and_survives_one_bad_page(
        tmp_path, stubbed_pipeline):
    directory = _write_manifest(
        tmp_path, [_page(1, 0, role="cover"), _page(2, 1, role="cover"),
                   _page(10, 9)])
    source = FakeSource((1, 2, 10))
    docs = LayoutOCRLoader(manifest_dir=directory).load_book(source)
    # hai trang bìa -> rỗng; trang 10 -> một chunk
    assert [d.metadata["page_index"] for d in docs] == [10]
