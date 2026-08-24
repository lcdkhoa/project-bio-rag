# -*- coding: utf-8 -*-
"""Quét tham số kênh THƯA bằng SỐ, không bằng mặc định của thư viện.

Bốn câu hỏi mà §3.2 của prompt M2 bắt phải trả lời bằng phép đo:

1. **`k1` x `b`** — BM25 rất nhạy với hai số này. Quét `k1 ∈ {0.9,1.2,1.5}` x
   `b ∈ {0.3,0.5,0.75}` và **báo cáo cả bảng**, không chỉ ô thắng.
2. **Tách từ** — (a) khoảng trắng + hạ chữ giữ dấu, (c) thêm bỏ dấu.
   `underthesea`/`pyvi` (b) **chưa cài**: chỉ thêm phụ thuộc nếu (a)/(c) cho thấy
   còn dư địa; không hơn bằng số thì không thêm (nguyên tắc 7).
3. **Chuẩn hoá công thức bật/tắt** — đo riêng trên **nhóm câu có công thức**, vì
   đó chính là chỗ đề cương nêu tên BM25 ("thuật ngữ khoa học đặc thù"). Recall
   tổng sẽ che mất nó: nhóm này chỉ là một phần nhỏ của bộ test.
4. **`overlap=120` có làm lệch IDF không** — dựng thêm một chỉ mục theo TRANG
   (không chồng lấn) và so thứ hạng.

Không cần LLM, không cần GPU, không cần bge-m3. Chạy vài phút.
"""

from __future__ import annotations

import argparse
import collections
import os
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np  # noqa: E402

from src.config import BM25_TOKENIZER  # noqa: E402
from src.rag.bm25 import BM25Index, SparseFingerprint  # noqa: E402
from src.rag.sparse_store import open_text_collection  # noqa: E402
from src.rag.text_normalize import NORMALIZER_VERSION, tokenize  # noqa: E402
from src.test.ablation import KS, load_testset  # noqa: E402

# Lưới MỞ RỘNG so với §3.2 ({0.9,1.2,1.5} x {0.3,0.5,0.75}): lượt quét đầu chọn
# ra ô Ở ĐÚNG BIÊN (k1=0.9, b=0.3), nên không biết đó là đỉnh hay là tường. Nới
# cả hai trục về phía biên thắng để trả lời câu đó bằng số.
K1_GRID = (0.5, 0.7, 0.9, 1.2, 1.5)
B_GRID = (0.0, 0.15, 0.3, 0.5, 0.75)


def _fp(n: int, tok: str) -> SparseFingerprint:
    return SparseFingerprint("biology_text", n, "quet", "quet", tok,
                             NORMALIZER_VERSION)


def recall_mrr(index: BM25Index, rows: Sequence[dict],
               page_of: Dict[str, Tuple[str, int]], k1: float, b: float,
               fold_accents: bool = True, formula: bool = True) -> dict:
    max_k = max(KS)
    hits = {k: 0 for k in KS}
    mrr = 0.0
    for row in rows:
        gold = (str(row["source_book"]), int(row["source_page"]))
        top = index.search(str(row["question"]), k=max_k, k1=k1, b=b,
                           fold_accents=fold_accents, formula=formula)
        flags = [page_of.get(c) == gold for c, _ in top]
        for k in KS:
            if any(flags[:k]):
                hits[k] += 1
        for i, f in enumerate(flags):
            if f:
                mrr += 1.0 / (i + 1)
                break
    n = max(len(rows), 1)
    out = {f"R@{k}": hits[k] / n for k in KS}
    out["MRR"] = mrr / n
    return out


def has_formula(text: str) -> bool:
    return any("#" in t for t in tokenize(text))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--testset-dir", default="src/test/testsets")
    args = ap.parse_args()

    rows = load_testset(Path(args.testset_dir))
    if not rows:
        print(f"Không có *_testset.csv trong {args.testset_dir}")
        return 1

    col = open_text_collection()
    got = col.get(include=["documents", "metadatas"], limit=1_000_000)
    ids, docs, metas = got["ids"], got["documents"], got["metadatas"]
    page_of = {c: (str(m["source"]), int(m["page"])) for c, m in zip(ids, metas)}
    print(f"Bộ test: {len(rows)} câu · index: {len(ids)} chunk\n")

    # --- 1. k1 x b ------------------------------------------------------
    fold = BM25_TOKENIZER == "folded"
    print(f"=== 1. Quét k1 x b (tokenizer={BM25_TOKENIZER}, công thức bật) ===")
    print("    Quét PHẢI chạy trên đúng bộ tách từ sẽ dùng thật: lượt trước quét")
    print("    trên 'folded' rồi mới đo ra 'plain' thắng, nên k1/b của lượt đó là")
    print("    tối ưu của một cấu hình KHÁC.")
    idx = BM25Index.build(ids, docs, _fp(len(ids), BM25_TOKENIZER),
                          fold_accents=fold)
    print(f"{'k1':>5s} {'b':>5s} " + " ".join(f"{'R@'+str(k):>7s}" for k in KS)
          + f" {'MRR':>7s}")
    best = None
    for k1 in K1_GRID:
        for b in B_GRID:
            m = recall_mrr(idx, rows, page_of, k1, b, fold_accents=fold)
            print(f"{k1:5.1f} {b:5.2f} "
                  + " ".join(f"{m['R@'+str(k)]:7.3f}" for k in KS)
                  + f" {m['MRR']:7.3f}")
            if best is None or m["MRR"] > best[0]["MRR"]:
                best = (m, k1, b)
    print(f"-> tốt nhất theo MRR: k1={best[1]}, b={best[2]} "
          f"(MRR={best[0]['MRR']:.3f}, R@10={best[0]['R@10']:.3f})\n")
    bk1, bb = best[1], best[2]

    # --- 2. tách từ ------------------------------------------------------
    print("=== 2. Tách từ: bỏ dấu vs giữ dấu (k1/b tốt nhất ở trên) ===")
    other_tok = "folded" if BM25_TOKENIZER == "plain" else "plain"
    idx_other = BM25Index.build(ids, docs, _fp(len(ids), other_tok),
                                fold_accents=(other_tok == "folded"))
    pairs = {BM25_TOKENIZER: (idx, fold), other_tok: (idx_other, not fold)}
    for name, tok in (("(a) giữ dấu", "plain"), ("(c) bỏ dấu ", "folded")):
        index, fa = pairs[tok]
        m = recall_mrr(index, rows, page_of, bk1, bb, fold_accents=fa)
        print(f"  {name}  từ vựng={len(index.vocab):6d}  "
              + " ".join(f"R@{k}={m['R@'+str(k)]:.3f}" for k in KS)
              + f"  MRR={m['MRR']:.3f}")
    print("  (b) tách từ tiếng Việt bằng thư viện: underthesea/pyvi CHƯA CÀI —")
    print("      chỉ thêm phụ thuộc nếu (a)/(c) cho thấy còn dư địa.\n")

    # --- 3. chuẩn hoá công thức ------------------------------------------
    formula_rows = [r for r in rows if has_formula(str(r["question"]))]
    print(f"=== 3. Chuẩn hoá công thức bật/tắt — nhóm câu CÓ công thức "
          f"({len(formula_rows)}/{len(rows)} câu) ===")
    idx_nf = BM25Index.build(ids, docs, _fp(len(ids), BM25_TOKENIZER),
                             fold_accents=fold, formula=False)
    for label, subset in (("toàn bộ", rows), ("nhóm công thức", formula_rows)):
        if not subset:
            print(f"  {label}: 0 câu — KHÔNG ĐO ĐƯỢC")
            continue
        on = recall_mrr(idx, subset, page_of, bk1, bb, fold_accents=fold)
        off = recall_mrr(idx_nf, subset, page_of, bk1, bb,
                          fold_accents=fold, formula=False)
        print(f"  {label:16s} n={len(subset):3d}")
        for k in KS:
            print(f"      R@{k:<2d} tắt={off['R@'+str(k)]:.3f} "
                  f"bật={on['R@'+str(k)]:.3f} "
                  f"chênh={on['R@'+str(k)]-off['R@'+str(k)]:+.3f}")
        print(f"      MRR   tắt={off['MRR']:.3f} bật={on['MRR']:.3f} "
              f"chênh={on['MRR']-off['MRR']:+.3f}")
    if formula_rows:
        print("  câu có công thức:")
        for r in formula_rows[:8]:
            print(f"      - {str(r['question'])[:88]}")
    print()

    # --- 4. IDF: chunk chồng lấn vs trang ---------------------------------
    print("=== 4. overlap=120 có làm lệch IDF không, và có ĐỔI THỨ HẠNG không ===")
    pages: Dict[Tuple[str, int], List[str]] = collections.defaultdict(list)
    for cid, doc, meta in zip(ids, docs, metas):
        pages[(str(meta["source"]), int(meta["page"]))].append(doc or "")
    pids = list(pages)
    pidx = BM25Index.build([f"{s}|{p}" for s, p in pids],
                           ["\n".join(pages[k]) for k in pids],
                           _fp(len(pids), BM25_TOKENIZER), fold_accents=fold)
    # Kiểm bất biến TRƯỚC khi so: văn bản trang là nối các chunk của nó, nên
    # vốn từ theo trang PHẢI chứa trọn vốn từ theo chunk. Lượt trước hai chỉ mục
    # vô tình dựng bằng hai bộ tách từ khác nhau và phép so ra một con số sai mà
    # trông hợp lý (R@1 = 0,16) — đúng loại lỗi mà cả repo này đề phòng.
    thieu = [t for t in idx.vocab if t not in pidx.vocab]
    if thieu:
        raise RuntimeError(
            f"{len(thieu)} token có ở chỉ mục chunk mà không có ở chỉ mục trang "
            f"(ví dụ {thieu[:5]}) — hai chỉ mục không cùng bộ tách từ.")
    common = [t for t in idx.vocab if t in pidx.vocab]
    a = np.array([idx.idf[idx.vocab[t]] for t in common])
    bb_ = np.array([pidx.idf[pidx.vocab[t]] for t in common])
    ra, rb = np.argsort(np.argsort(-a)), np.argsort(np.argsort(-bb_))
    d = np.abs(ra - rb)
    print(f"  {len(idx.ids)} chunk chồng lấn (len TB {idx.avg_len:.1f} token) vs "
          f"{len(pidx.ids)} trang (len TB {pidx.avg_len:.1f})")
    print(f"  lệch hạng IDF trên {len(common)} từ chung: "
          f"p50={np.percentile(d,50):.0f} p90={np.percentile(d,90):.0f} max={d.max()}")
    # Câu hỏi thật sự quan trọng: có đổi KẾT QUẢ không?
    page_self = {f"{s}|{p}": (s, p) for s, p in pids}
    m_chunk = recall_mrr(idx, rows, page_of, bk1, bb, fold_accents=fold)
    m_page = recall_mrr(pidx, rows, page_self, bk1, bb, fold_accents=fold)
    print(f"  xếp hạng theo CHUNK: " + " ".join(
        f"R@{k}={m_chunk['R@'+str(k)]:.3f}" for k in KS) + f" MRR={m_chunk['MRR']:.3f}")
    print(f"  xếp hạng theo TRANG: " + " ".join(
        f"R@{k}={m_page['R@'+str(k)]:.3f}" for k in KS) + f" MRR={m_page['MRR']:.3f}")
    print("  (hai dòng này KHÔNG so trực tiếp được — đơn vị xếp hạng khác nhau,")
    print("   trang thì dễ trúng hơn chunk. Đọc nó như: IDF lệch tới mức nào thì")
    print("   vẫn không phá được thứ hạng.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
