import os
from pathlib import Path

import pytest

from src.test.qa_layout import render_layout_overlay

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PDF_PATH = PROJECT_ROOT / "datasources" / "SGK KHTN 7 CTST.pdf"


@pytest.mark.skipif(not _PDF_PATH.exists(), reason=f"datasource PDF not present: {_PDF_PATH}")
def test_overlay_smoke(tmp_path):
    out = render_layout_overlay("SGK KHTN 7 CTST.pdf", page_index=40, out_dir=str(tmp_path))
    assert os.path.exists(out)
