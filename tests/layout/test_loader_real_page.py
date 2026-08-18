"""End-to-end dry run of the M1 layout-aware text ETL on a real SGK page.

Skips when the corpus PDF isn't present (e.g. CI without git-LFS). Proves the
whole pipeline (render -> preprocess -> segment -> printed page number ->
per-region OCR -> chunk) produces clean, correctly-split chunks on a real page.
"""
import os
import unicodedata

import pytest

from src.etl.layout.loader import LayoutOCRLoader

PDF = os.path.join("datasources", "SGK KHTN 7 CTST.pdf")
PAGE_INDEX = 40           # 0-based; the printed page number on it is 40


def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


@pytest.mark.skipif(not os.path.exists(PDF), reason=f"corpus PDF not present: {PDF}")
def test_real_page_splits_sidebar_from_body_and_reads_printed_number():
    docs = LayoutOCRLoader().load_page(PDF, PAGE_INDEX)
    assert docs, "no chunks produced for a real content page"

    # printed page number (40), not the raw 1-based PDF index (41)
    assert all(d.metadata["page"] == 40 for d in docs), \
        f"expected printed page 40, got {sorted({d.metadata['page'] for d in docs})}"

    body = " ".join(d.page_content for d in docs if d.metadata["region_type"] == "body")
    boxes = [d for d in docs if d.metadata["region_type"] in ("sidebar", "info_box")]

    assert len(body) > 500, "body text unexpectedly short"
    assert boxes, "expected >=1 sidebar/info_box chunk (F-A pale-box detection on a real page)"

    # 'bảng tuần hoàn' (periodic table) appears only in the sidebar question on this
    # page, not in the covalent-bond body. If the pale sidebar leaked into the body
    # flow it would show up in `body`. Accent-insensitive so OCR diacritic slips
    # don't make the assertion brittle.
    marker = "bang tuan hoan"
    assert marker not in _strip_accents(body), "sidebar text leaked into body chunks"
    assert any(marker in _strip_accents(b.page_content) for b in boxes), \
        "sidebar marker was not captured in a box chunk either — segmentation lost it"
