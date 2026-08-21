import os
from pathlib import Path

import pytest

from src.test.qa_layout import region_counts, render_layout_overlay

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BOOK = "SGK_KHTN_6_KNTT"
_BOOK_DIR = PROJECT_ROOT / "datasources" / BOOK
PAGE = 10          # trang chuẩn để QA: mắt thường đếm được >= 4 hộp màu


@pytest.mark.skipif(not _BOOK_DIR.exists(),
                    reason=f"datasource không có: {_BOOK_DIR}")
def test_overlay_smoke(tmp_path):
    out = render_layout_overlay(BOOK, page_number=PAGE, out_dir=str(tmp_path))
    assert os.path.exists(out)
    assert Path(out).name == f"{BOOK}_p{PAGE}_layout.png"


@pytest.mark.skipif(not _BOOK_DIR.exists(),
                    reason=f"datasource không có: {_BOOK_DIR}")
def test_region_counts_reports_per_page():
    counts = region_counts(BOOK, [PAGE])
    assert set(counts) == {PAGE}
    assert counts[PAGE].get("body") == 1        # luôn có đúng một vùng thân bài
