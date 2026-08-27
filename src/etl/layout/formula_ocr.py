# -*- coding: utf-8 -*-
"""Client goi MinerU2.5 that qua `content_extract` (D-104) - CHI chay tren
Colab GPU. May dev (CPU, khong co `mineru_vl_utils`) khong tu chay duoc phan
nay; test dung client gia (dependency injection qua `formula_client` param cua
`extract_text_units`).

API DUNG (D-104, KHONG phai `two_step_extract` - da do rong 3/3 o tren crop
mot dong):
    MinerUClient(backend="transformers", model=model, processor=proc)
        .content_extract(PIL.Image, type="text"|"table")

Dung `vlm_loader._load_vlm` (chuyen tu scripts/colab_run_ocr_engines.py, D-99/
D-101) de nap model - KHONG tu goi AutoModelForImageTextToText truc tiep, vi
transformers>=5 nap HONG lm_head cua ho Qwen2-VL neu khong co buoc kiem tie-
weights (da do: sinh token rac thay vi doc kem).

Thiet ke day du: document/specs/2026-08-27-formula-ocr-hybrid-buoc23-design.md §4.
"""
from __future__ import annotations

from ...config import FORMULA_MINERU_MODEL


class FormulaMinerUClient:
    """Load MODEL MOT LAN cho ca tien trinh (nguyen tac 4/D-104: nap ~35s/lan).

    `read()` lazy-load o LAN GOI DAU TIEN, khong phai luc __init__ - de import
    module nay tren may khong co GPU khong fail ngay.
    """

    def __init__(self, model_id: str = FORMULA_MINERU_MODEL):
        self.model_id = model_id
        self._client = None

    def _load(self) -> None:
        import torch
        from mineru_vl_utils import MinerUClient
        from transformers import AutoProcessor

        from .vlm_loader import _load_vlm

        proc = AutoProcessor.from_pretrained(self.model_id, use_fast=True)
        model = _load_vlm(self.model_id, torch)
        model.eval()
        self._client = MinerUClient(backend="transformers", model=model,
                                     processor=proc)

    def read(self, crop_bgr, kind: str = "text") -> str:
        if self._client is None:
            self._load()
        from PIL import Image
        import cv2

        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        loai = "table" if kind == "table" else "text"
        res = self._client.content_extract(image, type=loai)
        return "" if res is None else str(res).strip()


_singleton: "FormulaMinerUClient | None" = None


def get_formula_client() -> FormulaMinerUClient:
    global _singleton
    if _singleton is None:
        _singleton = FormulaMinerUClient()
    return _singleton
