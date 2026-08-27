# -*- coding: utf-8 -*-
"""Uoc luong so lan phai goi MinerU tren CA 12 QUYEN, doc thang tu index
`biology_text` DA CO (khong OCR lai) - de biet ETA that truoc khi chay Colab.

Chay: python -m src.test.estimate_formula_hybrid_cost
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.etl.layout.formula_gate import is_formula_suspect
from src.rag.sparse_store import open_text_collection

SECONDS_PER_CALL = 2.6  # do that o D-108 (content_extract, khong phai two_step_extract)


def main() -> int:
    # `open_text_collection()` mo Chroma THUAN, KHONG nap bge-m3 (sparse_store.py
    # da ghi ro: nap embedding model chi de doc chu la ~1 phut CPU doi lay dung 0
    # thong tin). Dung lai ham co san thay vi VectorDB() de script nay chay nhanh.
    coll = open_text_collection()
    data = coll.get(include=["documents"], limit=1_000_000)
    docs = data.get("documents") or []

    n_lines_suspect = 0
    n_docs_with_hit = 0
    for text in docs:
        lines = str(text or "").split("\n")
        hit_lines = [l for l in lines if is_formula_suspect(l)]
        if hit_lines:
            n_docs_with_hit += 1
            n_lines_suspect += len(hit_lines)

    eta_seconds = n_lines_suspect * SECONDS_PER_CALL
    print(f"Tổng chunk: {len(docs)}")
    print(f"Chunk có ≥1 dòng nghi công thức: {n_docs_with_hit}")
    print(f"Tổng số DÒNG nghi công thức (ước số lần gọi MinerU): {n_lines_suspect}")
    print(f"ETA gọi MinerU (@ {SECONDS_PER_CALL}s/dòng, D-108): "
          f"{eta_seconds:.0f}s ≈ {eta_seconds / 60:.1f} phút")
    print("Lưu ý: đây là số đếm trên index CŨ (chưa hybrid) — số THẬT khi ETL "
          "chạy lại có thể khác vì gate chạy trên OCR MỚI, không phải trên "
          "text cũ này. Coi đây là CẬN TRÊN thô để ước ETA Colab, không phải "
          "số chính xác.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
