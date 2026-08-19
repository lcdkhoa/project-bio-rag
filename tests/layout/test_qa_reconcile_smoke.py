import os
from pathlib import Path

import pytest

PDF = os.path.join("datasources", "SGK KHTN 6 CD.pdf")

# The QA tool pulls a heavy native import chain (langchain -> sentence_transformers
# -> datasets -> pyarrow) that can segfault on a bad DLL load order on Windows.
# A segfault kills the whole pytest process, so this smoke test is opt-in
# (RUN_QA_SMOKE=1) and never runs in a normal suite. The tool itself pre-loads
# pyarrow to avoid the crash; this gate is belt-and-braces.
RUN = os.getenv("RUN_QA_SMOKE") == "1"


@pytest.mark.skipif(not RUN, reason="set RUN_QA_SMOKE=1 (and have corpus) to run the QA overlay")
@pytest.mark.skipif(not os.path.exists(PDF), reason="corpus not present")
def test_reconcile_overlay_smoke(tmp_path):
    from src.test.test_image_extraction_full import run_page
    from src.etl.image_processor import make_image_processor
    processor = make_image_processor(Path(PDF).name)
    page_dir = tmp_path / "page_008"
    # run_page(processor, pdf_path, page_number, out_dir, keep_old=False);
    # out_dir IS the page dir — it writes overlays directly into it.
    run_page(processor, Path(PDF), 8, page_dir)
    assert (page_dir / "04_reconciled.png").exists()
