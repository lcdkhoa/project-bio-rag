# -*- coding: utf-8 -*-
"""Bảng đối chiếu 12 cấu hình — hạng mục HỢP ĐỒNG của đề cương (Nội dung 4).

Bảng Kế hoạch thực hiện, Giai đoạn 3: *"thực nghiệm so sánh cấu hình 1: BM25
thuần túy vs. Vector Retrieval vs. Hybrid Search"*; Nội dung 4 thêm *"nghiên cứu
loại bỏ thành phần bật/tắt re-ranking và cổng lọc liên quan"*.
    3 chế độ x rerank{on,off} x cổng lọc{on,off} = **12 cấu hình**.

## Vì sao 12 cấu hình chỉ tốn ~1 lần chạy model

Phần đắt là **nhúng bge-m3** và **cross-encoder** — cả hai đều CPU. Nhưng cả hai
đều **không phụ thuộc cấu hình**: khoảng cách dày của một câu hỏi là như nhau ở
mọi cấu hình, và điểm cross-encoder của một cặp (câu hỏi, chunk) cũng vậy. Nên
chạy MỘT lần, lưu lại, rồi **phát lại** 12 cấu hình từ bộ nhớ đệm. BM25 rẻ
(đo được vài ms/truy vấn) nên tính trực tiếp — nhờ vậy quét `k1 x b` không cần
đệm gì cả.

Bộ nhớ đệm mang **dấu vân của index** (digest chunk id + `TEXT_EXTRACTION_VERSION`);
index đổi thì đệm bị từ chối chứ không âm thầm dùng lại (CẤM #6).

## Cách đo precision — báo cáo CẢ HAI định nghĩa (§2.2 của prompt M2)

`precision@k` theo một trang vàng duy nhất bị chặn trên bởi `min(k, m)/k`, với
`m` = **số chunk mà trang vàng có trong index** (không phải số lọt vào tập ứng
viên — con số đó phụ thuộc chính bộ truy xuất đang chấm, nên dùng nó là vòng
tròn luẩn quẩn). Báo cáo trần đó **cạnh** precision, để người đọc thấy 0,55 so
với **trần của chính nó** chứ không phải so với 1,0.
"""

from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import io
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from src.config import (  # noqa: E402
    BM25_B,
    BM25_FETCH_K,
    BM25_K1,
    BM25_TOKENIZER,
    FUSION_DENSE_WEIGHT,
    FUSION_METHOD,
    FUSION_RRF_K,
    PERSIST_DIR,
    RERANK_SCORE_MIN,
    RETRIEVER_DISTANCE_MARGIN,
    RETRIEVER_MAX_K,
    TEXT_EXTRACTION_VERSION,
)
from src.rag.bm25 import chunk_ids_digest  # noqa: E402


def sparse_params_stamp() -> str:
    return f"k1={BM25_K1} b={BM25_B} tok={BM25_TOKENIZER} n={CANDIDATE_N}"
from src.rag.fusion import GateStats, fuse, relevance_gate  # noqa: E402
from src.rag.sparse_store import get_sparse_index, open_text_collection  # noqa: E402

KS = (1, 3, 5, 10)
# Bề rộng ứng viên của MỖI kênh trước khi hợp nhất. Rộng hơn `RERANK_FETCH_K`
# đang chạy (20) vì bảng này phải đo được cả recall@10 SAU cổng lọc.
CANDIDATE_N = 50
DEFAULT_CACHE = PERSIST_DIR / "ablation_cache.json"


# --- Bộ test -------------------------------------------------------------

def load_testset(directory: Path) -> List[dict]:
    rows: List[dict] = []
    for path in sorted(glob.glob(str(Path(directory) / "*_testset.csv"))):
        with io.open(path, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                row["_file"] = os.path.basename(path)
                rows.append(row)
    return rows


# --- Bộ nhớ đệm ----------------------------------------------------------

@dataclass
class Cache:
    index_digest: str
    text_version: str
    # Tham số kênh THƯA lúc dựng đệm. Cần vì tập ứng viên được chấm
    # cross-encoder là HỢP của top dày và top thưa; đổi `k1`/`b`/tokenizer thì
    # top thưa đổi theo và đệm sẽ THIẾU điểm cho ứng viên mới. Không đóng dấu thì
    # cách hỏng đó chỉ lộ ra bằng một RuntimeError khó hiểu ở tận lúc phát lại.
    sparse_params: str
    dense: Dict[str, List[Tuple[str, float]]]      # câu hỏi -> [(chunk_id, khoảng cách)]
    rerank: Dict[str, Dict[str, float]]            # câu hỏi -> {chunk_id: điểm CE}

    def to_json(self) -> dict:
        return {
            "index_digest": self.index_digest,
            "text_version": self.text_version,
            "sparse_params": self.sparse_params,
            "dense": {q: [[c, d] for c, d in v] for q, v in self.dense.items()},
            "rerank": self.rerank,
        }

    @classmethod
    def from_json(cls, raw: dict) -> "Cache":
        return cls(
            index_digest=raw["index_digest"],
            text_version=raw["text_version"],
            sparse_params=raw.get("sparse_params", ""),
            dense={q: [(c, float(d)) for c, d in v]
                   for q, v in raw["dense"].items()},
            rerank={q: {c: float(s) for c, s in v.items()}
                    for q, v in raw["rerank"].items()},
        )


def build_cache(rows: Sequence[dict], collection, sparse, cache_path: Path,
                candidate_n: int = CANDIDATE_N) -> Cache:
    """Chạy MỘT lần phần đắt: nhúng dày + cross-encoder trên hợp các ứng viên."""
    from src.rag.reranker import get_reranker
    from src.rag.vectorstore import VectorDB

    got = collection.get(include=["documents", "metadatas"], limit=1_000_000)
    text_of = dict(zip(got["ids"], got["documents"]))
    digest = chunk_ids_digest(got["ids"])
    # langchain-chroma trả `Document` KHÔNG kèm id, nên phải khớp ngược. Khớp
    # bằng bộ ba (source, page_index, chunk_index) — đúng ba khoá dựng nên
    # chunk_id, nên ánh xạ là song ánh; khớp bằng nội dung thì KHÔNG, vì
    # overlap=120 làm hai chunk kề nhau chia sẻ ~30% chữ.
    id_by_meta = {}
    for cid, meta in zip(got["ids"], got["metadatas"]):
        key = (str(meta["source"]), int(meta["page_index"]), int(meta["chunk_index"]))
        if key in id_by_meta:
            raise RuntimeError(f"Khoá metadata trùng: {key} — không còn là song ánh")
        id_by_meta[key] = cid

    print(f"[cache] nạp bge-m3 …")
    db = VectorDB().db
    reranker = get_reranker()

    dense: Dict[str, List[Tuple[str, float]]] = {}
    rerank: Dict[str, Dict[str, float]] = {}
    t0 = time.time()
    for i, row in enumerate(rows, 1):
        q = str(row["question"])
        if q in dense:
            continue
        scored = db.similarity_search_with_score(q, k=candidate_n)
        # Chroma trả Document, không trả id -> khớp lại bằng (source, page,
        # chunk_index), đúng ba khoá dựng nên chunk_id. Không đoán.
        pairs: List[Tuple[str, float]] = []
        for doc, dist in scored:
            m = doc.metadata or {}
            key = (str(m.get("source")), int(m.get("page_index", -1)),
                   int(m.get("chunk_index", -1)))
            cid = id_by_meta.get(key)
            if cid is None:
                raise RuntimeError(
                    f"Không khớp được Document {key} về chunk_id — hai nguồn sự thật.")
            pairs.append((cid, float(dist)))
        pairs.sort(key=lambda p: p[1])
        dense[q] = pairs

        cand = {c for c, _ in pairs}
        cand |= {c for c, _ in sparse.search(q, k=candidate_n,
                                             k1=BM25_K1, b=BM25_B)}
        cand_list = sorted(cand)
        scores = reranker.score(q, [text_of[c] for c in cand_list])
        if not scores or len(scores) != len(cand_list):
            raise RuntimeError(
                f"Cross-encoder trả {len(scores) if scores else 0} điểm cho "
                f"{len(cand_list)} ứng viên — rerank KHÔNG chạy. Không có "
                "fallback ở đây: một bảng ablation với rerank tắt âm thầm là "
                "một bảng số sai mà trông hợp lý.")
        rerank[q] = {c: float(s) for c, s in zip(cand_list, scores)}
        if i % 10 == 0 or i == len(rows):
            el = time.time() - t0
            print(f"[cache] {i}/{len(rows)}  {el:.0f}s  {el/i:.2f}s/câu",
                  flush=True)
            # Ghi từng đợt: cross-encoder trên CPU đo được ~0,5 s/cặp nên một
            # lượt là ~50 phút. Sập ở phút 49 mà mất trắng là lãng phí có thể
            # tránh được bằng bốn dòng.
            _save(Cache(index_digest=digest,
                        text_version=TEXT_EXTRACTION_VERSION,
                        sparse_params=sparse_params_stamp(),
                        dense=dense, rerank=rerank), cache_path)

    cache = Cache(index_digest=digest, text_version=TEXT_EXTRACTION_VERSION,
                  sparse_params=sparse_params_stamp(), dense=dense, rerank=rerank)
    _save(cache, cache_path)
    print(f"[cache] đã lưu -> {cache_path}")
    return cache


def _save(cache: Cache, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache.to_json(), ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(path)


def load_cache(path: Path, collection) -> Cache:
    if not path.exists():
        raise FileNotFoundError(
            f"Chưa có bộ nhớ đệm ở {path}. Chạy với --build-cache.")
    cache = Cache.from_json(json.loads(path.read_text(encoding="utf-8")))
    got = collection.get(include=[], limit=1_000_000)
    live = chunk_ids_digest(got["ids"])
    if cache.index_digest != live or cache.text_version != TEXT_EXTRACTION_VERSION:
        raise RuntimeError(
            "Bộ nhớ đệm CŨ HƠN index — từ chối dùng.\n"
            f"  digest: đệm={cache.index_digest[:12]}… index={live[:12]}…\n"
            f"  version: đệm={cache.text_version} index={TEXT_EXTRACTION_VERSION}\n"
            "Dựng lại: --build-cache")
    return cache


# --- Một cấu hình --------------------------------------------------------

@dataclass(frozen=True)
class Config:
    mode: str            # dense | bm25 | hybrid
    rerank: bool
    gate: bool
    fusion: str = FUSION_METHOD
    k1: float = BM25_K1
    b: float = BM25_B
    dense_weight: float = FUSION_DENSE_WEIGHT
    rrf_k: int = FUSION_RRF_K
    margin: float = RETRIEVER_DISTANCE_MARGIN
    score_min: float = RERANK_SCORE_MIN

    @property
    def label(self) -> str:
        return (f"{self.mode:6s} rerank={'on ' if self.rerank else 'off'} "
                f"gate={'on ' if self.gate else 'off'}")


def rank_for(cfg: Config, query: str, cache: Cache, sparse,
             top_n: int, gate_stats: Optional[GateStats] = None) -> List[str]:
    """Trả danh sách chunk_id đã xếp hạng cho MỘT câu hỏi dưới MỘT cấu hình."""
    dense = cache.dense.get(query, []) if cfg.mode in ("dense", "hybrid") else []
    sp: List[Tuple[str, float]] = []
    if cfg.mode in ("bm25", "hybrid"):
        sp = sparse.search(query, k=CANDIDATE_N, k1=cfg.k1, b=cfg.b,
                           fold_accents=(BM25_TOKENIZER == "folded"))

    if cfg.mode == "dense":
        items = fuse(dense, [], method=cfg.fusion, rrf_k=cfg.rrf_k,
                     dense_weight=1.0)
    elif cfg.mode == "bm25":
        items = fuse([], sp, method=cfg.fusion, rrf_k=cfg.rrf_k,
                     dense_weight=0.0)
    else:
        items = fuse(dense, sp, method=cfg.fusion, rrf_k=cfg.rrf_k,
                     dense_weight=cfg.dense_weight)

    if cfg.gate and items:
        keep = relevance_gate([it.score for it in items], cfg.margin,
                              higher_is_better=True)
        if gate_stats is not None:
            gate_stats.observe([it.score for it in items], keep)
        items = [it for it, k in zip(items, keep) if k]

    if cfg.rerank and items:
        ce = cache.rerank.get(query, {})
        scored = [(it, ce.get(it.key)) for it in items]
        missing = [it.key for it, s in scored if s is None]
        if missing:
            raise RuntimeError(
                f"Thiếu điểm cross-encoder cho {len(missing)} ứng viên — "
                "bộ nhớ đệm không phủ hết. Dựng lại bằng --build-cache.")
        scored.sort(key=lambda p: -p[1])
        # Sàn tuyệt đối của rerank: đây LÀ cổng lọc theo nghĩa "bỏ ứng viên yếu".
        scored = [(it, s) for it, s in scored if s >= cfg.score_min]
        items = [it for it, _ in scored]

    return [it.key for it in items[:top_n]]


# --- Chỉ số -------------------------------------------------------------

def evaluate(cfg: Config, rows: Sequence[dict], cache: Cache, sparse,
             page_of: Dict[str, Tuple[str, int]]) -> dict:
    max_k = max(KS)
    hits = {k: 0 for k in KS}
    prec = {k: 0.0 for k in KS}
    ceil = {k: 0.0 for k in KS}
    mrr = 0.0
    empty = 0
    gate_stats = GateStats()
    for row in rows:
        q = str(row["question"])
        gold = (str(row["source_book"]), int(row["source_page"]))
        ranked = rank_for(cfg, q, cache, sparse, max_k, gate_stats)
        if not ranked:
            empty += 1
        flags = [page_of.get(c) == gold for c in ranked]
        for i, f in enumerate(flags):
            if f:
                mrr += 1.0 / (i + 1)
                break
        # Trần của precision: trang vàng chỉ có `m` chunk, nên precision@k
        # không thể vượt min(k, m)/k dù xếp hạng hoàn hảo (§2.2 prompt M2).
        n_gold_total = int(row.get("_n_gold_chunks", 0))
        for k in KS:
            if any(flags[:k]):
                hits[k] += 1
            prec[k] += sum(flags[:k]) / k
            ceil[k] += min(k, n_gold_total) / k
    n = len(rows)
    out = {"cau_hinh": cfg.label, "so_cau": n, "rong": empty,
           "MRR": round(mrr / n, 4)}
    for k in KS:
        out[f"R@{k}"] = round(hits[k] / n, 4)
    for k in KS:
        out[f"P@{k}"] = round(prec[k] / n, 4)
        out[f"tranP@{k}"] = round(ceil[k] / n, 4)
    out.update({f"gate_{key}": val for key, val in gate_stats.summary().items()})
    return out


def build_page_lookup(collection) -> Tuple[Dict[str, Tuple[str, int]], Dict[Tuple[str, int], int]]:
    got = collection.get(include=["metadatas"], limit=1_000_000)
    page_of: Dict[str, Tuple[str, int]] = {}
    per_page: Dict[Tuple[str, int], int] = {}
    for cid, meta in zip(got["ids"], got["metadatas"]):
        key = (str(meta["source"]), int(meta["page"]))
        page_of[cid] = key
        per_page[key] = per_page.get(key, 0) + 1
    return page_of, per_page


ALL_CONFIGS = [
    Config(mode=m, rerank=r, gate=g)
    for m in ("bm25", "dense", "hybrid")
    for r in (False, True)
    for g in (False, True)
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--testset-dir", default="src/test/testsets")
    ap.add_argument("--cache", default=str(DEFAULT_CACHE))
    ap.add_argument("--build-cache", action="store_true")
    ap.add_argument("--out", default="src/test/ablation_report")
    args = ap.parse_args()

    rows = load_testset(Path(args.testset_dir))
    if not rows:
        print(f"Không có *_testset.csv trong {args.testset_dir}")
        return 1
    collection = open_text_collection()
    sparse = get_sparse_index(collection=collection)
    page_of, per_page = build_page_lookup(collection)
    for row in rows:
        row["_n_gold_chunks"] = per_page.get(
            (str(row["source_book"]), int(row["source_page"])), 0)

    cache_path = Path(args.cache)
    if args.build_cache:
        cache = build_cache(rows, collection, sparse, cache_path)
    else:
        cache = load_cache(cache_path, collection)

    print(f"\nBộ test: {len(rows)} câu từ {args.testset_dir}")
    print(f"Chỉ mục thưa: {len(sparse.ids)} chunk, {len(sparse.vocab)} từ vựng")
    print(f"Hợp nhất: {FUSION_METHOD} (rrf_k={FUSION_RRF_K}, "
          f"dense_weight={FUSION_DENSE_WEIGHT}), BM25 k1={BM25_K1} b={BM25_B}, "
          f"tokenizer={BM25_TOKENIZER}")
    print(f"Ứng viên mỗi kênh: {CANDIDATE_N}; cổng lọc margin="
          f"{RETRIEVER_DISTANCE_MARGIN}; sàn rerank={RERANK_SCORE_MIN}\n")

    results = [evaluate(cfg, rows, cache, sparse, page_of) for cfg in ALL_CONFIGS]

    head = f"{'cấu hình':30s} " + " ".join(f"{'R@'+str(k):>7s}" for k in KS) + \
           f" {'MRR':>7s} {'P@5':>7s} {'trầnP@5':>8s} {'rỗng':>5s} {'cắt':>6s}"
    print(head)
    print("-" * len(head))
    for r in results:
        print(f"{r['cau_hinh']:30s} "
              + " ".join(f"{r['R@'+str(k)]:7.3f}" for k in KS)
              + f" {r['MRR']:7.3f} {r['P@5']:7.3f} {r['tranP@5']:8.3f}"
              + f" {r['rong']:5d} {r.get('gate_ti_le_truy_van_bi_cat', 0):6.2f}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with io.open(out.with_suffix(".csv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)
    print(f"\nĐã lưu: {out.with_suffix('.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
