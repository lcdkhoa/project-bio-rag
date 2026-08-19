"""Tính nhanh Recall@k (k=3/5/10) cho retrieval — KHÔNG cần Qwen, KHÔNG cần judge.

Chỉ dùng text vector DB + embedding để chứng minh: tăng k thì recall tăng. Rất nhanh
vì không nạp LLM. Đối chiếu trang vàng (source_book, source_page) trong các bộ test
đã sinh ở testsets/.

Chạy:
    python src/test/recall_at_k.py
Kết quả: in bảng + lưu testsets/../recall_at_k_report.csv (+ .md).
"""

import os
import sys
import glob

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd

from src.rag.vectorstore import VectorDB
from src.rag.reranker import get_reranker
from src.test.metrics import make_page_relevance

KS = (3, 5, 10)
TAGS = ("base", "rer")


def reciprocal_rank(rel_flags):
    """1/rank của kết quả liên quan đầu tiên (1-based), 0 nếu không có."""
    for i, is_rel in enumerate(rel_flags):
        if is_rel:
            return 1.0 / (i + 1)
    return 0.0


def _rerank_order(query, scored, reranker):
    """Sắp lại (doc,dist) theo cross-encoder; fallback distance nếu reranker rỗng."""
    docs = [d for d, _ in scored]
    if not docs:
        return []
    ce = reranker.score(query, [d.page_content for d in docs])
    if not ce or len(ce) != len(docs):
        return [d for d, _ in sorted(scored, key=lambda p: p[1])]
    return [d for d, _ in sorted(zip(docs, ce), key=lambda p: p[1], reverse=True)]


def main():
    base = os.path.dirname(__file__)
    testsets = sorted(glob.glob(os.path.join(base, "testsets", "*_testset.csv")))
    if not testsets:
        print("Không tìm thấy bộ test trong testsets/. Chạy generate_testsets.py trước.")
        return

    print("Đang nạp text vector DB (bge-m3)...")
    db = VectorDB().db
    max_k = max(KS)

    try:
        reranker = get_reranker()
    except Exception as e:
        print(f"CẢNH BÁO: không nạp được reranker ({e}); chỉ đo baseline.")
        reranker = None

    rows = []
    for csv_path in testsets:
        book = os.path.basename(csv_path).replace("_testset.csv", "")
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
        hits = {(t, k): 0 for t in TAGS for k in KS}
        mrr_sum = {"base": 0.0, "rer": 0.0}
        for _, r in df.iterrows():
            q = str(r["question"])
            is_rel = make_page_relevance(str(r["source_book"]), int(r["source_page"]))
            scored = db.similarity_search_with_score(q, k=max_k)
            base_docs = [d for d, _ in sorted(scored, key=lambda p: p[1])]
            rer_docs = _rerank_order(q, scored, reranker) if reranker else base_docs
            for tag, docs_ordered in (("base", base_docs), ("rer", rer_docs)):
                flags = [is_rel(d.metadata or {}) for d in docs_ordered]
                for k in KS:
                    if any(flags[:k]):
                        hits[(tag, k)] += 1
                mrr_sum[tag] += reciprocal_rank(flags)
        n = len(df)
        row = {"book": book, "num_questions": n}
        for tag in TAGS:
            row.update({f"recall@{k} ({tag})": round(hits[(tag, k)] / n, 4) if n else 0.0 for k in KS})
            row[f"MRR ({tag})"] = round(mrr_sum[tag] / n, 4) if n else 0.0
        rows.append(row)
        summary = "  ".join(f"R@{k}(base/rer)={row[f'recall@{k} (base)']:.2f}/{row[f'recall@{k} (rer)']:.2f}" for k in KS)
        print(f"  {book:<22} {summary}  MRR(base/rer)={row['MRR (base)']:.2f}/{row['MRR (rer)']:.2f}")

    report = pd.DataFrame(rows)
    avg = {"book": "TRUNG BÌNH", "num_questions": int(report["num_questions"].mean())}
    for tag in TAGS:
        avg.update({f"recall@{k} ({tag})": round(report[f"recall@{k} ({tag})"].mean(), 4) for k in KS})
        avg[f"MRR ({tag})"] = round(report[f"MRR ({tag})"].mean(), 4)
    report = pd.concat([report, pd.DataFrame([avg])], ignore_index=True)

    out_csv = os.path.join(base, "recall_at_k_report.csv")
    report.to_csv(out_csv, index=False, encoding="utf-8-sig")

    # Markdown
    out_md = os.path.join(base, "recall_at_k_report.md")
    k_head = " | ".join(f"Recall@{k} (base\\|rer)" for k in KS)
    md = [
        "# Recall@k theo từng bộ sách — baseline (distance) vs rerank (cross-encoder)\n",
        "Chứng minh: **tăng k thì recall tăng đơn điệu**; rerank không tăng recall@max_k "
        "(chỉ đảo thứ tự trong tập đã fetch) nhưng cải thiện recall@k nhỏ và MRR — "
        "đúng luận điểm D-08 \"nút thắt ở xếp hạng\".\n",
        f"| Sách | {k_head} | MRR (base\\|rer) |",
        "|---|" + "---|" * len(KS) + "---|",
    ]
    for _, r in report.iterrows():
        cells = " | ".join(f"{r[f'recall@{k} (base)']:.2f}\\|{r[f'recall@{k} (rer)']:.2f}" for k in KS)
        mrr_cell = f"{r['MRR (base)']:.2f}\\|{r['MRR (rer)']:.2f}"
        name = f"**{r['book']}**" if r["book"] == "TRUNG BÌNH" else r["book"]
        md.append(f"| {name} | {cells} | {mrr_cell} |")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"\nĐã lưu: {out_csv}")
    print(f"Đã lưu: {out_md}")
    print("\n=== TRUNG BÌNH toàn bộ ===")
    print("  " + "  ".join(f"Recall@{k}(base/rer) = {avg[f'recall@{k} (base)']:.3f}/{avg[f'recall@{k} (rer)']:.3f}" for k in KS))
    print(f"  MRR(base/rer) = {avg['MRR (base)']:.3f}/{avg['MRR (rer)']:.3f}")


if __name__ == "__main__":
    main()
