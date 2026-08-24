# -*- coding: utf-8 -*-
"""Cấu hình 2 của Giai đoạn 3: **RAG đa phương thức vs RAG chỉ văn bản**.

Đề cương, Mục tiêu 4: *"so sánh hiệu năng trực tiếp giữa … Hệ thống RAG đa
phương thức so với hệ thống RAG chỉ sử dụng văn bản."* Bảng Kế hoạch, Giai đoạn
3: *"cấu hình 2: Text-only vs Multi-modal."*

## Bảng này đo GÌ, và KHÔNG đo gì

Đo **ở tầng truy xuất, đúng bề rộng production**: LLM thật sự nhìn thấy
`RETRIEVER_K` chunk text và `MULTIMODAL_MAX_FIGURES` hình. Câu hỏi được trả lời
bằng số: *kênh hình có mang được TRANG VÀNG vào ngữ cảnh khi kênh text bỏ sót
không, và nó mang theo bao nhiêu nhiễu?*

**KHÔNG đo chất lượng câu trả lời.** Cấu hình 1 (D-82) cũng đo bằng chỉ số IR
với 0 lượt gọi LLM, nên hai bảng cùng một đơn vị. Chất lượng câu trả lời cần
LLM-as-a-judge, mà hạn mức/ngày của OpenRouter free tier vẫn CHƯA đo được
(D-67) — nói rõ chỗ thiếu thay vì để người đọc tự suy.

## Ba cái bẫy đã biết trước khi chạy

1. **Bề rộng production, không phải bề rộng đo.** Bài học đắt nhất của D-82: ở
   50 ứng viên/kênh ưu thế hybrid là +0,0065 MRR (nhiễu), ở 20 là +0,0117 MRR.
   Nên ở đây bề rộng lấy TRỰC TIẾP từ `src/config.py`, không có hằng số riêng.
2. **`HybridRetriever.search` bọc cả hai kênh trong `try/except` chỉ log
   warning.** Một lượt truy xuất ảnh hỏng sẽ làm "đa phương thức" trông y hệt
   "chỉ văn bản" — một hàng số sai mà trông hợp lý. Nên ở đây gọi hai retriever
   TRỰC TIẾP, không bọc, để lỗi nổ ra.
3. **Kho ảnh rỗng phải cho ra CHÍNH XÁC kết quả text-only.** Cột `delta` bằng 0
   khi kho rỗng là điều kiện cần; lệch thì đường ống có nhánh ẩn.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Sequence, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from src.config import (  # noqa: E402
    IMAGE_RELEVANCE_THRESHOLD,
    IMAGE_RERANK_ENABLED,
    IMAGE_RETRIEVER_FETCH_K,
    IMAGE_RETRIEVER_K,
    MULTIMODAL_MAX_FIGURES,
    PERSIST_DIR,
    RERANK_ENABLED,
    RETRIEVAL_MODE,
    RETRIEVER_K,
    TEXT_EXTRACTION_VERSION,
)
from src.rag.bm25 import chunk_ids_digest  # noqa: E402
from src.rag.multimodal_context import build_context, selected_figures  # noqa: E402
from src.test.ablation import load_testset  # noqa: E402
from src.test.qa_citation_page import (  # noqa: E402
    PageTextIndex,
    build_idf,
    coverage,
)

DEFAULT_CACHE = PERSIST_DIR / "mm_retrieval_cache.json"


def _page_key(meta: dict) -> Tuple[str, int]:
    """(quyển, số trang IN) — cùng hệ với gold key của bộ test.

    Chunk text mang `source` + `page`; doc hình mang `pdf_filename` +
    `page_number`. Trên corpus này `page == page_index` ở 16 393/16 393 chunk
    (đo 2026-08-25, offset 0 — D-65), nên `page_number` của phía ảnh cũng là số
    trang in. KHÔNG suy diễn thêm: thiếu khoá thì trả ("", -1) để nó không bao
    giờ khớp gold, thay vì đoán.
    """
    source = str(meta.get("source") or meta.get("pdf_filename") or "")
    page = meta.get("page", meta.get("page_number"))
    try:
        return (source, int(page))
    except (TypeError, ValueError):
        return ("", -1)


def collect(rows: Sequence[dict], cache_path: Path, text_k: int,
            image_k: int, min_score: float) -> Dict[str, dict]:
    """Chạy hai retriever production cho từng câu, lưu kết quả thô.

    Lưu lại vì phần đắt là bge-m3 + cross-encoder + CLIP; in lại bảng thì không
    được tốn thêm một giây model nào. Đệm mang dấu vân của CẢ HAI chỉ mục: đổi
    index text hay dựng lại kho ảnh thì đệm bị từ chối, không âm thầm dùng lại.
    """
    from src.rag.image_vectorstore import ImageVectorDB
    from src.rag.query_intent import is_image_only_query
    from src.rag.vectorstore import VectorDB

    text_db = VectorDB()
    image_db = ImageVectorDB()

    got = text_db.db._collection.get(include=[], limit=1_000_000)
    text_digest = chunk_ids_digest(got["ids"])
    img_ids = image_db._metadata_chroma._collection.get(
        include=[], limit=1_000_000)["ids"]
    image_digest = chunk_ids_digest(sorted(img_ids)) if img_ids else "EMPTY"
    stamp = {
        "text_digest": text_digest,
        "image_digest": image_digest,
        "text_version": TEXT_EXTRACTION_VERSION,
        # Đổi schema của bản ghi thì đệm cũ THIẾU cột mới; không đóng dấu thì
        # nó lộ ra dưới dạng KeyError ở tận lúc chấm điểm.
        "schema": "v2_cov",
        "widths": f"text_k={text_k} image_k={image_k} "
                  f"fetch_k={IMAGE_RETRIEVER_FETCH_K} "
                  f"min_score={min_score} "
                  f"mode={RETRIEVAL_MODE} rerank={RERANK_ENABLED} "
                  f"img_rerank={IMAGE_RERANK_ENABLED}",
    }
    print(f"[kho] text {len(got['ids'])} chunk · ảnh {len(img_ids)} doc")
    print(f"[bề rộng] {stamp['widths']}")

    data: Dict[str, dict] = {}
    if cache_path.exists():
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        if raw.get("stamp") == stamp:
            data = raw.get("cau", {})
            print(f"[đệm] nối tiếp {len(data)} câu đã có")
        else:
            print("[đệm] dấu vân KHÁC (index hoặc bề rộng đã đổi) -> chạy lại")

    # Độ phủ token có trọng số IDF của `ground_truth` — dùng lại đúng bộ đo
    # của cổng G3 (`qa_citation_page`), IDF đo trên CHÍNH các trang của index
    # (không dùng stopword: phép bỏ dấu làm từ chức năng đụng từ nội dung).
    trang = PageTextIndex(text_db.db._collection)
    idf = build_idf(trang.page_texts())
    print(f"[idf] {trang.n_pages()} trang, {len(idf)} token")

    text_retriever = text_db.get_retriever({"k": text_k})
    image_retriever = image_db.get_retriever({"k": image_k,
                                              "min_score": min_score})

    t0 = time.time()
    for i, row in enumerate(rows, 1):
        q = str(row["question"])
        if q in data:
            continue
        # KHÔNG try/except: xem docstring, bẫy #2.
        text_docs = text_retriever.invoke(q)
        image_docs = image_retriever.invoke(q, related_text_docs=text_docs)
        keep = selected_figures(image_docs)
        ngu_canh_text = build_context(text_docs, image_docs, multimodal=False)
        ngu_canh_mm = build_context(text_docs, image_docs, multimodal=True)
        gt = str(row.get("ground_truth", ""))
        cov_text, n_inf = coverage(gt, ngu_canh_text, idf)
        cov_mm, _ = coverage(gt, ngu_canh_mm, idf)
        data[q] = {
            "image_only_route": bool(is_image_only_query(q)),
            "text_pages": [list(_page_key(d.metadata)) for d in text_docs],
            "image_pages_retrieved": [list(_page_key(d.metadata))
                                      for d in image_docs],
            "context_pages": [list(_page_key(d.metadata)) for d in keep],
            "figure_labels": [str(d.metadata.get("figure_label", ""))
                              for d in keep],
            "ctx_text_only": len(ngu_canh_text),
            "ctx_multimodal": len(ngu_canh_mm),
            "cov_text": round(cov_text, 4),
            "cov_mm": round(cov_mm, 4),
            "n_informative": n_inf,
        }
        if i % 10 == 0 or i == len(rows):
            el = time.time() - t0
            print(f"[chạy] {i}/{len(rows)}  {el:.0f}s  {el / i:.2f}s/câu",
                  flush=True)
            _save(cache_path, stamp, data)
    _save(cache_path, stamp, data)
    return data


def _save(path: Path, stamp: dict, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"stamp": stamp, "cau": data},
                              ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def score(rows: Sequence[dict], data: Dict[str, dict],
          pages_with_figures: set) -> dict:
    n = len(rows)
    acc = {"text_R": 0, "mm_R": 0, "hinh_vang": 0, "hinh_khac": 0,
           "co_hinh": 0, "gold_co_hinh": 0, "them": 0.0, "chi_anh": 0,
           "cov_text": 0.0, "cov_mm": 0.0, "cov_tang": 0, "cov_giam": 0}
    for row in rows:
        q = str(row["question"])
        rec = data.get(q)
        if rec is None:
            raise RuntimeError(
                f"Thiếu kết quả truy xuất cho câu {q[:60]!r}. Chấm trên phần đã "
                "có sẽ cho một bảng thấp đi ÂM THẦM — chạy lại để bù.")
        gold = (str(row["source_book"]), int(row["source_page"]))
        text_pages = {tuple(p) for p in rec["text_pages"]}
        ctx_figs = [tuple(p) for p in rec["context_pages"]]
        acc["text_R"] += int(gold in text_pages)
        acc["mm_R"] += int(gold in text_pages or gold in set(ctx_figs))
        acc["co_hinh"] += int(bool(ctx_figs))
        acc["hinh_vang"] += sum(1 for p in ctx_figs if p == gold)
        acc["hinh_khac"] += sum(1 for p in ctx_figs if p != gold)
        acc["gold_co_hinh"] += int(gold in pages_with_figures)
        acc["them"] += rec["ctx_multimodal"] - rec["ctx_text_only"]
        acc["chi_anh"] += int(rec["image_only_route"])
        ct, cm = float(rec["cov_text"]), float(rec["cov_mm"])
        acc["cov_text"] += ct
        acc["cov_mm"] += cm
        acc["cov_tang"] += int(cm > ct)
        # Ngữ cảnh mm là TẬP CHA của ngữ cảnh text nên độ phủ không thể giảm.
        # Đếm riêng thay vì bỏ qua: một con số khác 0 ở đây là bằng chứng có
        # nhánh ẩn, không phải một kết quả.
        acc["cov_giam"] += int(cm < ct)
    return {
        "so_cau": n,
        "text_only_R": round(acc["text_R"] / n, 4),
        "multimodal_R": round(acc["mm_R"] / n, 4),
        "delta_R": round((acc["mm_R"] - acc["text_R"]) / n, 4),
        "cau_co_hinh_trong_ngu_canh": round(acc["co_hinh"] / n, 4),
        "hinh_dung_trang_vang": acc["hinh_vang"],
        "hinh_trang_khac": acc["hinh_khac"],
        "gold_co_hinh_trong_kho": round(acc["gold_co_hinh"] / n, 4),
        "cov_text_TB": round(acc["cov_text"] / n, 4),
        "cov_mm_TB": round(acc["cov_mm"] / n, 4),
        "so_cau_cov_tang": acc["cov_tang"],
        "so_cau_cov_giam": acc["cov_giam"],
        "ky_tu_them_TB": round(acc["them"] / n, 1),
        "dinh_tuyen_chi_anh": acc["chi_anh"],
    }


def pages_having_figures() -> set:
    """Tập (quyển, trang) có ít nhất một hình trong kho — TRẦN của phía ảnh.

    Ngoài tập này kênh hình KHÔNG THỂ giúp, theo cấu trúc. In nó ra để người đọc
    thấy delta nhỏ là vì trần thấp, chứ không phải vì hợp nhất tồi.
    """
    from src.rag.image_vectorstore import ImageVectorDB

    db = ImageVectorDB()
    got = db._metadata_chroma._collection.get(include=["metadatas"],
                                              limit=1_000_000)
    return {_page_key(m) for m in (got["metadatas"] or [])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--testset-dir", default="src/test/testsets")
    ap.add_argument("--bo-sach", default="KNTT",
                    help="Chỉ chấm bộ sách này. Phía ảnh chỉ đáng tin ở KNTT: "
                         "kênh pill đọc 0 nhãn trên 8/12 quyển CD/CTST (D-65), "
                         "nên trộn 12 quyển vào là pha loãng có chủ ý.")
    ap.add_argument("--cache", default=str(DEFAULT_CACHE))
    ap.add_argument("--out", default="src/test/ablation_mm_report")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument(
        "--min-score", type=float, default=IMAGE_RELEVANCE_THRESHOLD,
        help="Ngưỡng liên quan của kênh ảnh. Mặc định = production. Đặt 0 "
             "để CHẨN ĐOÁN: tách chuyện kênh ảnh không tìm ra hình khỏi "
             "chuyện ngưỡng cắt hết. Kết quả ở ngưỡng khác production KHÔNG "
             "được dùng để chốt mặc định (CẤM #12), chỉ để chẩn đoán.")
    args = ap.parse_args()

    rows = load_testset(Path(args.testset_dir))
    if args.bo_sach:
        thieu = [r for r in rows if not r.get("bo_sach")]
        if thieu:
            raise RuntimeError(
                f"{len(thieu)}/{len(rows)} câu thiếu nhãn 'bo_sach' — lọc theo "
                "nó sẽ cho một bảng bỏ sót mà trông đầy đủ.")
        rows = [r for r in rows if str(r["bo_sach"]) == args.bo_sach]
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        print("Không còn câu nào sau khi lọc.")
        return 1

    print(f"Bộ test: {len(rows)} câu (bo_sach={args.bo_sach or 'tất cả'}) — "
          f"{len(set(r['source_book'] for r in rows))} quyển")
    print("CẢNH BÁO phải đi kèm mọi số: bộ test do LLM SINH, CHƯA người duyệt "
          "(_generation_meta.json: human_reviewed=false).")

    if args.min_score != IMAGE_RELEVANCE_THRESHOLD:
        print(f"!! CHẨN ĐOÁN: min_score={args.min_score} KHÁC production "
              f"({IMAGE_RELEVANCE_THRESHOLD}). Bảng này KHÔNG phải thứ người "
              "dùng thật nhận, và KHÔNG được dùng để chốt mặc định.")
    data = collect(rows, Path(args.cache), RETRIEVER_K, IMAGE_RETRIEVER_K,
                   args.min_score)
    co_hinh = pages_having_figures()

    ket_qua = []
    tong = score(rows, data, co_hinh)
    tong["nhom"] = f"tất cả (n={len(rows)})"
    ket_qua.append(tong)

    # Nhóm mà phía ảnh CÓ THỂ giúp: trang vàng có hình trong kho. Ngoài nhóm này
    # delta bắt buộc bằng 0 theo cấu trúc, nên trộn vào chỉ làm loãng con số.
    khoa_co_hinh = [r for r in rows
                    if (str(r["source_book"]), int(r["source_page"])) in co_hinh]
    if khoa_co_hinh:
        nhom = score(khoa_co_hinh, data, co_hinh)
        nhom["nhom"] = f"trang vàng CÓ hình trong kho (n={len(khoa_co_hinh)})"
        ket_qua.append(nhom)
    khong = [r for r in rows
             if (str(r["source_book"]), int(r["source_page"])) not in co_hinh]
    if khong:
        nhom = score(khong, data, co_hinh)
        nhom["nhom"] = f"trang vàng KHÔNG có hình (n={len(khong)})"
        ket_qua.append(nhom)

    head = (f"{'nhóm':40s} {'text_R':>7s} {'mm_R':>7s} {'delta':>7s} "
            f"{'h.đúng':>7s} {'h.khác':>7s} "
            f"{'cov_txt':>8s} {'cov_mm':>7s} {'cov+':>5s} {'cov-':>5s} {'+ký tự':>8s}")
    print(f"\n### Cấu hình 2 — text_k={RETRIEVER_K}, image_k="
          f"{IMAGE_RETRIEVER_K}, min_score={args.min_score}, hình vào ngữ "
          f"cảnh <= {MULTIMODAL_MAX_FIGURES}"
          + ("  [BỀ RỘNG PRODUCTION]"
             if args.min_score == IMAGE_RELEVANCE_THRESHOLD
             else "  [CHẨN ĐOÁN, không phải production]"))
    print(head)
    print("-" * len(head))
    for r in ket_qua:
        print(f"{r['nhom']:40s} {r['text_only_R']:7.3f} {r['multimodal_R']:7.3f} "
              f"{r['delta_R']:7.3f} "
              f"{r['hinh_dung_trang_vang']:7d} {r['hinh_trang_khac']:7d} "
              f"{r['cov_text_TB']:8.3f} {r['cov_mm_TB']:7.3f} "
              f"{r['so_cau_cov_tang']:5d} {r['so_cau_cov_giam']:5d} "
              f"{r['ky_tu_them_TB']:8.1f}")

    print("\ncov_txt/cov_mm = độ phủ token đáp án (trọng số IDF, cùng bộ đo với cổng G3)")
    print("của ngữ cảnh chỉ-văn-bản so với ngữ cảnh đa-phương-thức. `cov+` = số câu nó")
    print("TĂNG thật; `cov-` phải bằng 0 vì ngữ cảnh mm là tập cha — khác 0 là có nhánh ẩn.")
    print(f"\nTrang có hình trong kho: {len(co_hinh)} (quyển, trang).")
    print(f"Trang vàng của bộ test nằm trong đó: "
          f"{tong['gold_co_hinh_trong_kho'] * 100:.1f}% — đây là TRẦN của phía "
          "ảnh, ngoài nó delta = 0 theo cấu trúc.")
    if tong["dinh_tuyen_chi_anh"]:
        print(f"!! {tong['dinh_tuyen_chi_anh']} câu bị `is_image_only_query` "
              "định tuyến thành truy vấn CHỈ ẢNH -> phía text bị bỏ hẳn.")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["nhom"] + [k for k in ket_qua[0] if k != "nhom"]
    with io.open(out.with_suffix(".csv"), "w", encoding="utf-8-sig",
                 newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, restval="")
        w.writeheader()
        w.writerows(ket_qua)
    print(f"\nĐã lưu: {out.with_suffix('.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
