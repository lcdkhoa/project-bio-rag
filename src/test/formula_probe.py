# -*- coding: utf-8 -*-
"""Chuẩn hoá công thức đáng bao nhiêu — đo TRỰC TIẾP, không cần bộ test, không LLM.

## Vì sao phải có phép đo riêng

Bộ test 100 câu chứa **đúng 1 câu** có công thức hoá học thật (`H2SO4`); bốn câu
còn lại mà bộ dò bắt được là dương tính giả (`Bo,` tên riêng, `I,`/`XIII,` số La
Mã — đã sửa ở `NORMALIZER_VERSION = v2`). Với n = 1 thì **không kết luận được gì**
về recall. Nói "chuẩn hoá công thức cải thiện X%" dựa trên đó là bịa số.

## Mẹo để không cần người gán nhãn

Đáp án đúng **đọc được từ chính index**: một chunk là "chứa công thức F" khi văn
bản đã lưu của nó chứa dạng OCR hỏng của F (`CO,` cho CO₂). Đó là sự thật kiểm
được bằng `in`, không phải phán đoán. Nên với truy vấn ở **dạng học sinh gõ**
(`CO2`), ta đo được chính xác: bao nhiêu chunk đúng lọt top-k, có và không có
chuẩn hoá.

Cùng kiểu lập luận với cổng G4 (`Hình A.B` nghĩa là hình B của Bài A nên spine
liền mạch tự kiểm được) — cấu trúc của dữ liệu làm ra đáp án, không cần người.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, List, Sequence, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from src.config import BM25_B, BM25_K1, BM25_TOKENIZER  # noqa: E402
from src.rag.bm25 import BM25Index, SparseFingerprint  # noqa: E402
from src.rag.sparse_store import open_text_collection  # noqa: E402
from src.rag.text_normalize import NORMALIZER_VERSION  # noqa: E402

# (truy vấn học sinh gõ, các dạng OCR HỎNG tương ứng có thật trong index).
# Dạng hỏng lấy từ phép đếm của D-73, không phải bịa ra.
CASES: List[Tuple[str, Tuple[str, ...]]] = [
    ("CO2", ("CO,",)),
    ("O2", ("O,",)),
    ("H2O", ("H,O",)),
    ("H2SO4", ("H,SO,",)),
    ("CH4", ("CH,",)),
    ("SO2", ("SO,",)),
    ("N2", ("N,",)),
    ("CaCO3", ("CaCO,",)),
    ("CuSO4", ("CuSO,",)),
    ("Fe2O3", ("Fe,O,",)),
    ("Na2SO4", ("Na,SO,",)),
    ("CuO", ("CuO,",)),
]
TOP_K = 10


def gold_chunks(docs: Sequence[str], ids: Sequence[str],
                damaged: Sequence[str]) -> set:
    """Chunk 'đúng' = văn bản ĐÃ LƯU của nó chứa dạng OCR hỏng. Kiểm được, không đoán."""
    out = set()
    for cid, doc in zip(ids, docs):
        text = doc or ""
        if any(d in text for d in damaged):
            out.add(cid)
    return out


def main() -> int:
    col = open_text_collection()
    got = col.get(include=["documents"], limit=1_000_000)
    ids, docs = got["ids"], got["documents"]
    fold = BM25_TOKENIZER == "folded"
    fp = SparseFingerprint("biology_text", len(ids), "probe", "probe",
                           BM25_TOKENIZER, NORMALIZER_VERSION)
    print(f"index {len(ids)} chunk · tokenizer={BM25_TOKENIZER} "
          f"(fold_accents={fold}) · k1={BM25_K1} b={BM25_B} · top-{TOP_K}\n")
    idx_on = BM25Index.build(ids, docs, fp, fold_accents=fold, formula=True)
    idx_off = BM25Index.build(ids, docs, fp, fold_accents=fold, formula=False)

    head = (f"{'truy vấn':10s} {'dạng hỏng':12s} {'chunk đúng':>10s} "
            f"{'TẮT':>18s} {'BẬT':>18s}")
    print(head)
    print("-" * len(head))
    tot_on = tot_off = tot_gold = 0
    n_on = n_off = 0
    for query, damaged in CASES:
        gold = gold_chunks(docs, ids, damaged)
        on = [c for c, _ in idx_on.search(query, TOP_K, BM25_K1, BM25_B,
                                          fold_accents=fold, formula=True)]
        off = [c for c, _ in idx_off.search(query, TOP_K, BM25_K1, BM25_B,
                                            fold_accents=fold, formula=False)]
        h_on = sum(1 for c in on if c in gold)
        h_off = sum(1 for c in off if c in gold)
        tot_on += h_on
        tot_off += h_off
        tot_gold += len(gold)
        n_on += 1 if h_on else 0
        n_off += 1 if h_off else 0
        print(f"{query:10s} {damaged[0]:12s} {len(gold):10d} "
              f"{h_off:>6d}/{len(off):<2d} trúng@{TOP_K} "
              f"{h_on:>6d}/{len(on):<2d} trúng@{TOP_K}")
    n = len(CASES)
    print("-" * len(head))
    print(f"TỔNG {n} công thức · {tot_gold} chunk chứa dạng hỏng trong kho")
    print(f"  chuẩn hoá TẮT: {tot_off} chunk đúng trong top-{TOP_K}; "
          f"{n_off}/{n} truy vấn tìm được ít nhất một")
    print(f"  chuẩn hoá BẬT: {tot_on} chunk đúng trong top-{TOP_K}; "
          f"{n_on}/{n} truy vấn tìm được ít nhất một")
    print("\nĐọc kết quả: cột 'chunk đúng' là số chunk trong CẢ KHO có dạng hỏng.")
    print("Học sinh gõ 'CO2'; nếu không chuẩn hoá thì không token nào của truy vấn")
    print("khớp được chữ đã lưu 'CO,' — đúng cái đề cương gọi là 'không bỏ sót các")
    print("truy vấn chứa thuật ngữ khoa học đặc thù'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
