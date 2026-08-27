# tests/layout/test_formula_ocr.py
# -*- coding: utf-8 -*-
import numpy as np
import pytest

from src.etl.layout.formula_ocr import FormulaMinerUClient, get_formula_client


def test_client_raises_clear_error_without_mineru_installed(monkeypatch):
    """Máy dev không cài `mineru_vl_utils` — client phải báo lỗi RÕ, không
    silently disable (nguyên tắc 5)."""
    client = FormulaMinerUClient(model_id="fake/model")

    with pytest.raises(Exception) as exc_info:
        client._load()  # noqa: SLF001 — test trực tiếp việc load lười

    assert "mineru" in str(exc_info.value).lower() or \
        isinstance(exc_info.value, ImportError)


def test_read_calls_load_only_once_across_multiple_calls(monkeypatch):
    """Model phải load MỘT LẦN cho cả tiến trình — load lại mỗi lần gọi là bug
    đã bắt khi phản biện thiết kế (D-104: nạp model ~35s/lần)."""
    n_loads = {"count": 0}

    class FakeInnerClient:
        def content_extract(self, image, type="text"):
            return "CO₂"

    def fake_load(self):
        n_loads["count"] += 1
        self._client = FakeInnerClient()

    monkeypatch.setattr(FormulaMinerUClient, "_load", fake_load)
    client = FormulaMinerUClient(model_id="fake/model")
    crop = np.zeros((30, 100, 3), dtype=np.uint8)

    client.read(crop, kind="text")
    client.read(crop, kind="text")
    client.read(crop, kind="text")

    assert n_loads["count"] == 1


def test_get_formula_client_returns_same_instance(monkeypatch):
    import src.etl.layout.formula_ocr as mod
    monkeypatch.setattr(mod, "_singleton", None)

    a = get_formula_client()
    b = get_formula_client()

    assert a is b
