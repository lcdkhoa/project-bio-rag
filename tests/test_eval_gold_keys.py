"""Khoá vàng của bộ test phải khớp metadata chunk THẬT — chứng minh, không tin mắt.

Đây là test đắt nhất trong repo (chạy OCR layout trên một trang thật), nhưng nó
khoá lại đúng cái lỗi đã làm mọi metric IR của bản cũ bằng 0 mà không ai thấy:

- `source_book` ghi `"SGK KHTN 6 KNTT.pdf"` trong khi metadata chunk là
  `"SGK_KHTN_6_KNTT"`;
- `source_page` ghi số trong TÊN FILE (`page_013` -> 13) trong khi metadata `page`
  là số trang IN — trên corpus CŨ hai số lệch đúng 1, và `PAGE_TOLERANCE = 1` cũ
  che mất.

**Cập nhật 2026-08-23 (D-65/D-73): trên corpus 12 quyển thì `offset = 0`**, tức
`page == page_index` trên cả 12 quyển. Nên khoá sai kiểu "dùng `page_index`" nay
**trùng** khoá đúng và không còn là một ca kiểm được — nó đã được thay bằng một
khoá lệch thật (`page + 1`). Chính hai test dưới đây đã đỏ khi index 12 quyển
được dựng xong, đúng như dòng "nếu quan hệ này đổi, test phải đỏ" mong muốn.

Test tự bỏ qua nếu không có `datasources/` hoặc chưa có manifest, nên nó không
làm CI đỏ trên máy chưa có corpus.
"""
from __future__ import annotations

import pytest

from src.config import DATA_DIR
from src.test.metrics import PAGE_TOLERANCE, make_page_relevance

BOOK = "SGK_KHTN_6_KNTT"


@pytest.fixture(scope="module")
def real_page_payload():
    from src.etl.layout.loader import LayoutOCRLoader
    from src.etl.page_source import discover_page_sources
    from src.test.generate_testsets import _page_payload

    sources = [s for s in discover_page_sources(DATA_DIR) if s.name == BOOK]
    if not sources:
        pytest.skip(f"không có {BOOK} trong {DATA_DIR}")
    source = sources[0]

    loader = LayoutOCRLoader()
    try:
        chunks = loader.load_page(source, 22)
    except Exception as exc:  # thiếu manifest / thiếu tesseract
        pytest.skip(f"không đọc được trang thật: {exc}")
    if not chunks:
        pytest.skip("trang 22 không sinh chunk nào")

    payload = _page_payload(loader, source, 22)
    return payload, chunks


def test_gold_keys_come_from_chunk_metadata(real_page_payload):
    payload, chunks = real_page_payload
    meta = chunks[0].metadata

    assert payload["source_book"] == meta["source"] == BOOK
    assert payload["source_page"] == meta["page"]
    assert payload["source_page_index"] == meta["page_index"] == 22
    # Trên corpus 12 quyển, số trang in = số trong TÊN FILE (offset 0, đo trên
    # 12/12 quyển — D-65). Corpus cũ 4 quyển KNTT lệch −1 (D-33). Nếu quan hệ này
    # đổi nữa, test phải đỏ để người xem lại, chứ không được đi tiếp âm thầm.
    assert payload["source_page"] == 22


def test_gold_keys_match_the_relevance_function(real_page_payload):
    """Khoá vàng ghi ra CSV phải làm `make_page_relevance` trả True cho chunk thật."""
    payload, chunks = real_page_payload
    is_relevant = make_page_relevance(
        payload["source_book"], payload["source_page"])

    assert all(is_relevant(c.metadata) for c in chunks)


@pytest.mark.parametrize("wrong_key", ["book_with_pdf_suffix", "page_off_by_one"])
def test_old_broken_keys_are_detected(real_page_payload, wrong_key):
    """Khoá sai phải KHÔNG khớp — nếu khớp thì test này vô nghĩa.

    `page_index` từng là một khoá SAI (corpus cũ lệch −1) nhưng với offset 0 nó
    trùng khoá đúng, nên nó được thay bằng `page + 1`: một trang lân cận thật,
    đúng thứ mà `PAGE_TOLERANCE = 1` cũ từng cho qua.
    """
    payload, chunks = real_page_payload
    meta = chunks[0].metadata

    if wrong_key == "book_with_pdf_suffix":
        is_relevant = make_page_relevance(
            "SGK KHTN 6 KNTT.pdf", payload["source_page"])
    else:
        is_relevant = make_page_relevance(
            payload["source_book"], payload["source_page"] + 1)

    assert not is_relevant(meta), (
        f"khoá cũ ({wrong_key}) vẫn khớp — dung sai trang đang che lỗi? "
        f"PAGE_TOLERANCE={PAGE_TOLERANCE}")


def test_page_tolerance_is_zero():
    """Chunk không bao giờ vắt qua hai trang, nên dung sai ±1 chỉ thổi recall."""
    assert PAGE_TOLERANCE == 0
