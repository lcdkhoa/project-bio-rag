# tests/layout/test_text_extract_formula_hybrid.py
# -*- coding: utf-8 -*-
"""Tich hop hybrid formula vao text_extract.py, client MinerU GIA (khong can
GPU). Anh that de bat loi off-by-one giua bbox dong va bbox region TRUOC khi
cham GPU that tren Colab."""
import numpy as np
import pytest

from src.config import DATA_DIR
from src.etl.page_source import find_page_source
from src.etl.layout.regions import Region, RegionType
from src.etl.layout.text_extract import extract_text_units


class _FakeClient:
    """Tra loi CO doc dung cho crop bat ky - du de test luong ghep end-to-end
    ma khong can biet truoc bbox chinh xac cua tung dong."""

    def read(self, crop_bgr, kind="text"):
        return "hấp thụ khí CO₂ và thải ra khí O₂ vào ban đêm"


def test_formula_hybrid_applies_on_real_broken_page():
    pytest.importorskip("cv2")
    try:
        source = find_page_source(DATA_DIR, "SGK_KHTN_7_KNTT")
        img = source.load(121)
    except Exception as exc:
        pytest.skip(f"trang mau khong co tren may nay: {exc}")

    h, w = img.shape[:2]
    # Vung chua dong bi vo o trang 121 (do o D-63/D-144): gan het chieu rong
    # trang, mot dai ngang o phan giua trang.
    region = Region(RegionType.BODY, (0, int(h * 0.2), w, int(h * 0.6)),
                     reading_order=0, meta={"excludes": []})

    units = extract_text_units(img, [region], "kntt",
                                formula_client=_FakeClient())

    assert len(units) == 1
    joined = units[0].text
    # Truoc khi co hybrid, vung nay chua "0," (chi so bi vo, D-63). Sau khi
    # ghep, PHAI khong con dang "0," dinh lien nua O IT NHAT mot cho — bang
    # chung ro rang nhat la text chua "CO₂" that (Unicode subscript).
    assert "CO₂" in joined or "O₂" in joined
    assert units[0].formula_hybrid_status, (
        "phai co it nhat mot trang thai hybrid duoc ghi lai")


def test_formula_hybrid_off_by_default_leaves_text_untouched():
    """`formula_client=None` va `FORMULA_HYBRID_ENABLED=false` (mac dinh may
    dev) -> hanh vi y het truoc khi co hybrid, khong goi gi ca."""
    pytest.importorskip("cv2")
    try:
        source = find_page_source(DATA_DIR, "SGK_KHTN_7_KNTT")
        img = source.load(121)
    except Exception as exc:
        pytest.skip(f"trang mau khong co tren may nay: {exc}")

    h, w = img.shape[:2]
    region = Region(RegionType.BODY, (0, int(h * 0.2), w, int(h * 0.6)),
                     reading_order=0, meta={"excludes": []})

    units = extract_text_units(img, [region], "kntt")  # formula_client mac dinh

    assert units[0].formula_hybrid_status == []
