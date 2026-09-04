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

## Cấu trúc đo lại theo yêu cầu CBHD (D-181, 2026-09-03)

Chỉ đạo miệng, lệch có chủ đích khỏi `goal.docx` — xem D-181 trong
`document/decision_log.html`. Bốn thay đổi trong file này:

- `KS` có thêm `20`; mỗi K đi kèm **F1@K** (an toàn khi P+R=0, không chia 0/0).
  **F1@K là MACRO theo câu**: tính `2PR/(P+R)` cho TỪNG câu rồi lấy trung bình,
  giống hệt cách `P@K`/`R@K` đang được trung bình trong file này. Hệ quả phải nói
  trước kẻo người đọc tưởng bảng sai: `F1@K` in ra **không** bằng
  `2·P@K·R@K/(P@K+R@K)` tính từ hai cột kế bên (bất đẳng thức Jensen — macro-F1
  luôn ≤ F1 của macro-P/macro-R). Lấy trung bình rồi mới ghép là một độ đo khác,
  và nó che mất các câu recall 0.
- `R@K` đổi từ hit@k nhị phân sang **tỉ lệ chuẩn**: `|top-k ∩ gold| / m`, `m` lấy
  từ `_n_gold_chunks` đã có sẵn (không phải "có trúng hay không").
- Bốn "phương pháp" báo cáo (`METHOD_LABELS`) ánh xạ vào 4/12 dòng có sẵn của
  `ALL_CONFIGS` — không có đường truy vấn mới.
- Câu "ngoài phạm vi" (không có TRANG VÀNG theo định nghĩa) bị tách khỏi công
  thức P/R/F1@K — mẫu số 0 vô nghĩa — và đo bằng "tỉ lệ từ chối đúng" riêng
  (`ngoai_pham_vi_ti_le_tu_choi_dung`).

## Bảng này KHÔNG đi qua định tuyến ảnh (D-88) — phải nói ra khi trình bày

`rank_for()` chấm **thẳng kênh văn bản** cho mọi câu có trang vàng, kể cả 48 câu
HÌNH. Production thì khác: `HybridRetriever.search()` gọi `is_image_only_query()`
và với câu chỉ-cần-ảnh nó **bỏ qua truy xuất văn bản hoàn toàn** (D-88), nên
P/R/F1@K văn bản của đúng những câu đó ở production là **0 theo thiết kế, không
phải lỗi**. Hệ quả: số trong bảng này là *năng lực kênh văn bản*, luôn ≥ số
người dùng thật nhận trên nhóm câu hình. Đây chính là nguồn của khoảng lệch 0,004
giữa recall production và recall mô phỏng đã ghi ở D-175 (1/240 câu hình bị định
tuyến sang chỉ-cần-ảnh). Đừng dán hai con số cạnh nhau như thể cùng một phép đo.

`recall_at_k.py` đã **gộp vào đây và bị xoá**: chức năng độc nhất của nó (recall
dense baseline vs rerank, không LLM) đã trùng với hai dòng có sẵn trong
`ALL_CONFIGS` (`mode=dense rerank=off/on gate=off`) — chạy `--build-cache` một
lần rồi đọc đúng hai dòng đó thay vì một script rời. Trục "theo từng quyển" của
nó (mà nó có vì bộ test cũ tách file theo sách) **không được mang sang** —
CBHD nói rõ tách theo quyển/môn làm vector DB "rời rạc" (D-181 #5); trục phân
tích đúng bây giờ là LOẠI câu hỏi (văn bản/hình/ngoài-phạm-vi), không phải
sách. Hàm `reciprocal_rank()` (dùng nội bộ để tính MRR) được giữ lại nguyên
tên vì `tests/test_mrr_metric.py` import trực tiếp nó.

## Nguồn dữ liệu (D-182)

Đọc MỘT file `src/test/testset/draft.csv` (do `build_testset.py` sinh, qua cổng
người duyệt `testset_common.require_human_reviewed`) thay vì glob nhiều
`*_testset.csv` như bản `ablation.py` cũ.
"""

from __future__ import annotations

import argparse
import csv
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
    RERANK_FETCH_K,
    RERANK_SCORE_MIN,
    RETRIEVER_DISTANCE_MARGIN,
    RETRIEVER_MAX_K,
    TEXT_EXTRACTION_VERSION,
)
from src.rag.bm25 import chunk_ids_digest  # noqa: E402
from src.rag.fusion import GateStats, fuse, relevance_gate  # noqa: E402
from src.rag.sparse_store import get_sparse_index, open_text_collection  # noqa: E402

KS = (1, 3, 5, 10, 20)
# Bề rộng ứng viên của MỖI kênh trước khi hợp nhất. Rộng hơn `RERANK_FETCH_K`
# đang chạy (20) vì bảng này phải đo được cả recall@10 SAU cổng lọc.
CANDIDATE_N = 50
DEFAULT_CACHE = PERSIST_DIR / "ablation_cache.json"


def sparse_params_stamp() -> str:
    return f"k1={BM25_K1} b={BM25_B} tok={BM25_TOKENIZER} n={CANDIDATE_N}"


def sparse_search(sparse, query: str, k: int, k1: float = None, b: float = None):
    """MỘT chỗ duy nhất gọi kênh thưa.

    Trước đây `build_cache` gọi `sparse.search(...)` mà **quên `fold_accents`**,
    nên nó lấy ứng viên bằng bộ tách từ BỎ DẤU trong khi chỉ mục dựng bằng
    `plain` (GIỮ dấu) — hai tập ứng viên khác nhau, và bước phát lại báo "thiếu
    điểm cross-encoder cho 37 ứng viên". Lỗi đó chỉ lộ ra vì chỗ kia **raise**
    thay vì lặng lẽ chấm trên phần đã có. Gom về một hàm để không tái diễn.
    """
    return sparse.search(
        query,
        k=k,
        k1=BM25_K1 if k1 is None else k1,
        b=BM25_B if b is None else b,
        fold_accents=(BM25_TOKENIZER == "folded"),
    )


# --- Bộ test -------------------------------------------------------------

def load_testset(csv_path: Path) -> List[dict]:
    rows: List[dict] = []
    with io.open(csv_path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
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

    # NỐI TIẾP đệm cũ thay vì bắt đầu từ rỗng. Lý do là một lỗi đã cắn thật:
    # `_save` ghi đè CÙNG một file sau mỗi 10 câu, nên một lượt `--build-cache`
    # bị giết giữa chừng **thay đệm 100 câu bằng đệm 20 câu** — mất 51 phút công
    # đã bỏ ra. Ghi từng đợt (chống mất trắng) và bắt đầu từ rỗng (huỷ cái đã có)
    # là hai thứ mâu thuẫn nhau; nối tiếp giải quyết cả hai, và tiện thể làm
    # `--build-cache` tự nó resume được.
    dense: Dict[str, List[Tuple[str, float]]] = {}
    rerank: Dict[str, Dict[str, float]] = {}
    if cache_path.exists():
        try:
            cu = Cache.from_json(json.loads(cache_path.read_text(encoding="utf-8")))
        except (ValueError, KeyError) as exc:
            raise RuntimeError(
                f"Đệm cũ ở {cache_path} đọc không được ({exc}). Xoá nó rồi chạy "
                "lại — KHÔNG tự xoá hộ, vì nó có thể là hàng giờ công.") from exc
        if cu.index_digest == digest and cu.text_version == TEXT_EXTRACTION_VERSION:
            dense, rerank = cu.dense, cu.rerank
            print(f"[cache] nối tiếp đệm cũ: {len(dense)} câu đã có "
                  f"(dấu vân index khớp)")
        else:
            print("[cache] đệm cũ thuộc index KHÁC -> dựng lại từ đầu")

    print(f"[cache] nạp bge-m3 …")
    db = VectorDB().db
    reranker = get_reranker()

    t0 = time.time()
    for i, row in enumerate(rows, 1):
        q = str(row["question"])
        if q in dense and q in rerank:
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
        cand |= {c for c, _ in sparse_search(sparse, q, candidate_n)}
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


def topup_cache(cache: Cache, rows, collection, sparse, cache_path: Path,
                candidate_n: int = CANDIDATE_N) -> Cache:
    """Chấm cross-encoder cho ĐÚNG những cặp còn thiếu, giữ nguyên phần đã có.

    Dựng lại toàn bộ tốn ~51 phút (đo: 30,6 s/câu). Nhưng phần **dày** (nhúng
    bge-m3) không phụ thuộc tham số kênh thưa, và phần lớn điểm cross-encoder
    cũng đã có — chỉ những ứng viên MỚI của kênh thưa là thiếu. Nên khi đổi
    `k1`/`b`/tokenizer, việc đúng là bù vào chứ không phải làm lại từ đầu.
    """
    from src.rag.reranker import get_reranker

    got = collection.get(include=["documents"], limit=1_000_000)
    text_of = dict(zip(got["ids"], got["documents"]))

    thieu = {}
    for row in rows:
        q = str(row["question"])
        if q not in cache.dense:
            raise RuntimeError(
                f"Bộ nhớ đệm chưa có phần DÀY của câu {q[:60]!r} — "
                "phải --build-cache, không bù được.")
        cand = {c for c, _ in cache.dense[q]}
        cand |= {c for c, _ in sparse_search(sparse, q, candidate_n)}
        con_thieu = sorted(c for c in cand if c not in cache.rerank.get(q, {}))
        if con_thieu:
            thieu[q] = con_thieu

    tong = sum(len(v) for v in thieu.values())
    if not tong:
        print("[topup] không thiếu cặp nào — đệm đã đủ.")
        cache.sparse_params = sparse_params_stamp()
        _save(cache, cache_path)
        return cache

    print(f"[topup] thiếu {tong} cặp (câu, chunk) trên {len(thieu)}/{len(rows)} "
          f"câu — chấm bù, KHÔNG dựng lại từ đầu.")
    reranker = get_reranker()
    t0 = time.time()
    for i, (q, cids) in enumerate(thieu.items(), 1):
        scores = reranker.score(q, [text_of[c] for c in cids])
        if not scores or len(scores) != len(cids):
            raise RuntimeError(
                f"Cross-encoder trả {len(scores) if scores else 0} điểm cho "
                f"{len(cids)} ứng viên — rerank KHÔNG chạy.")
        cache.rerank.setdefault(q, {}).update(
            {c: float(s) for c, s in zip(cids, scores)})
        if i % 10 == 0 or i == len(thieu):
            print(f"[topup] {i}/{len(thieu)}  {time.time() - t0:.0f}s", flush=True)
            cache.sparse_params = sparse_params_stamp()
            _save(cache, cache_path)
    cache.sparse_params = sparse_params_stamp()
    _save(cache, cache_path)
    print(f"[topup] xong trong {time.time() - t0:.0f}s -> {cache_path}")
    return cache


def load_cache(path: Path, collection, check_sparse_params: bool = True) -> Cache:
    if not path.exists():
        raise FileNotFoundError(
            f"Chưa có bộ nhớ đệm ở {path}. Chạy với --build-cache.")
    cache = Cache.from_json(json.loads(path.read_text(encoding="utf-8")))
    got = collection.get(include=[], limit=1_000_000)
    live = chunk_ids_digest(got["ids"])
    stamp = sparse_params_stamp()
    # Ba điều kiện, không phải hai. Thiếu điều kiện thứ ba thì đổi `k1`/`b`/
    # tokenizer sẽ không bị chặn ở đây mà lộ ra tận lúc phát lại, dưới dạng
    # "thiếu điểm cross-encoder cho 37 ứng viên" — một thông báo đúng nhưng chỉ
    # nói triệu chứng, không nói nguyên nhân. (Đúng là chuyện đã xảy ra thật.)
    if (cache.index_digest != live
            or cache.text_version != TEXT_EXTRACTION_VERSION
            or (check_sparse_params and cache.sparse_params != stamp)):
        raise RuntimeError(
            "Bộ nhớ đệm KHÔNG khớp cấu hình hiện tại — từ chối dùng.\n"
            f"  digest: đệm={cache.index_digest[:12]}… index={live[:12]}…\n"
            f"  version: đệm={cache.text_version} index={TEXT_EXTRACTION_VERSION}\n"
            f"  tham số thưa: đệm={cache.sparse_params!r} hiện tại={stamp!r}\n"
            "Dựng lại: --build-cache · chấm bù phần thiếu: --topup-cache")
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
    # Bề rộng ứng viên MỖI kênh. Mặc định `CANDIDATE_N = 50` là bề rộng để ĐO
    # (trần chất lượng truy xuất), KHÔNG phải bề rộng production: `.env` đang
    # chạy `RERANK_FETCH_K = 20` và `BM25_FETCH_K = 20`. Chốt mặc định dựa trên
    # số đo ở 50 mà đem chạy ở 20 là khuyến nghị dựa trên một cấu hình KHÁC.
    cand_n: int = CANDIDATE_N

    @property
    def label(self) -> str:
        rong = "" if self.cand_n == CANDIDATE_N else f" n={self.cand_n}"
        return (f"{self.mode:6s} rerank={'on ' if self.rerank else 'off'} "
                f"gate={'on ' if self.gate else 'off'} fus={self.fusion:4s}{rong}")


# Bốn "phương pháp" báo cáo theo yêu cầu CBHD (D-181 #3) — ánh xạ trực tiếp vào
# 4/12 dòng có sẵn của `ALL_CONFIGS` bên dưới, KHÔNG phải đường truy vấn mới.
# Khoá là (mode, rerank, gate) đúng TÊN TRƯỜNG thật của `Config` — bản D-181 gốc
# giả định tên `retrieval_mode`, đã đối chiếu code và sửa thành `mode`.
METHOD_LABELS: Dict[Tuple[str, bool, bool], str] = {
    ("bm25", False, False): "keyword",
    ("dense", False, False): "dense",
    ("hybrid", False, False): "truyen_thong",
    ("hybrid", True, False): "de_xuat",  # cấu hình production thật (D-180)
}


def method_label(cfg: "Config") -> str:
    return METHOD_LABELS.get((cfg.mode, cfg.rerank, cfg.gate), "")


def rank_for(cfg: Config, query: str, cache: Cache, sparse,
             top_n: int, gate_stats: Optional[GateStats] = None) -> List[str]:
    """Trả danh sách chunk_id đã xếp hạng cho MỘT câu hỏi dưới MỘT cấu hình."""
    if cfg.mode in ("dense", "hybrid") and query not in cache.dense:
        # KHÔNG được trả rỗng: một bộ nhớ đệm dựng dở (bị ngắt giữa chừng) sẽ
        # làm mọi câu chưa đệm bị đếm là "rỗng" và recall thấp đi MỘT CÁCH ÂM
        # THẦM — một bảng số sai mà trông hợp lý, đúng loại lỗi tệ nhất ở đây.
        raise RuntimeError(
            f"Bộ nhớ đệm thiếu câu hỏi ({len(cache.dense)} câu đã đệm): "
            f"{query[:70]!r}. Đệm dựng dở thì phải dựng nốt (--build-cache), "
            "không được chấm trên phần đã có.")
    dense = (cache.dense.get(query, [])[: cfg.cand_n]
             if cfg.mode in ("dense", "hybrid") else [])
    sp: List[Tuple[str, float]] = []
    if cfg.mode in ("bm25", "hybrid"):
        sp = sparse_search(sparse, query, cfg.cand_n, k1=cfg.k1, b=cfg.b)

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

def _gold_key(row: dict) -> Optional[Tuple[str, int]]:
    """Khoá (sách, trang) của câu hỏi, hoặc `None` nếu câu KHÔNG có trang vàng.

    Câu "ngoài phạm vi" (D-181 #4) không thuộc corpus 12 quyển nên không có
    trang vàng — `source_book`/`source_page` rỗng là tín hiệu THIẾT KẾ của loại
    câu đó, không phải lỗi dữ liệu cần raise (khác với `ManifestMissing` ở
    đường ETL, nơi thiếu là bug).
    """
    sb = str(row.get("source_book", "") or "").strip()
    sp = str(row.get("source_page", "") or "").strip()
    if not sb or not sp:
        return None
    try:
        return (sb, int(sp))
    except ValueError:
        return None


def reciprocal_rank(flags: Sequence[bool]) -> float:
    """1/hạng của phần tử `True` đầu tiên (1-based), 0.0 nếu không có.

    Giữ lại từ `recall_at_k.py` (đã gộp/xoá, D-181 #7) — `tests/test_mrr_metric.py`
    import thẳng tên này.
    """
    for i, f in enumerate(flags):
        if f:
            return 1.0 / (i + 1)
    return 0.0


def evaluate(cfg: Config, rows: Sequence[dict], cache: Cache, sparse,
             page_of: Dict[str, Tuple[str, int]]) -> dict:
    """Tính P/R/F1@K trên nhóm câu CÓ gold chunk; nhóm ngoài-phạm-vi tách riêng.

    Ranh giới là **KHÔNG CÓ TRANG VÀNG** (`_gold_key(row) is None`), KHÔNG phải
    `_n_gold_chunks == 0`. Hai điều kiện đó trùng nhau trên corpus hôm nay (đo
    2026-09-03: 30/270 câu không có trang vàng, và **0** câu có trang vàng mà
    trang đó lại 0 chunk trong index 16 515 chunk) nhưng chúng là HAI THỨ KHÁC
    HẲN nhau:

    - không có trang vàng  -> câu ngoài phạm vi 12 quyển (D-181 #4), đúng thiết kế;
    - có trang vàng nhưng trang đó 0 chunk -> **khuyết dữ liệu** (trang bìa, trang
      ETL bỏ sót, gold key lệch số trang).

    Dùng `_n_gold_chunks == 0` cho cả hai thì ca thứ hai bị ÂM THẦM đổi nhãn
    thành "ngoài phạm vi" và chui vào mẫu số của tỉ lệ từ chối đúng, đồng thời
    `so_cau` tụt đi mà không ai biết — đúng loại fallback im lặng Nguyên tắc 5
    cấm. Nên ca đó bị tách ra thành `suy_bien_*` và NÊU TÊN, không bị gộp vào
    đâu cả.
    """
    max_k = max(KS)
    out_scope = [r for r in rows if _gold_key(r) is None]
    co_trang_vang = [r for r in rows if _gold_key(r) is not None]
    in_scope = [r for r in co_trang_vang if int(r.get("_n_gold_chunks", 0)) > 0]
    suy_bien = [r for r in co_trang_vang if int(r.get("_n_gold_chunks", 0)) == 0]

    prec = {k: 0.0 for k in KS}
    rec = {k: 0.0 for k in KS}
    f1 = {k: 0.0 for k in KS}
    ceil = {k: 0.0 for k in KS}
    mrr = 0.0
    empty = 0
    gate_stats = GateStats()
    for row in in_scope:
        q = str(row["question"])
        gold = _gold_key(row)
        ranked = rank_for(cfg, q, cache, sparse, max_k, gate_stats)
        if not ranked:
            empty += 1
        flags = [page_of.get(c) == gold for c in ranked]
        mrr += reciprocal_rank(flags)
        # Trần của precision: trang vàng chỉ có `m` chunk, nên precision@k
        # không thể vượt min(k, m)/k dù xếp hạng hoàn hảo (§2.2 prompt M2).
        n_gold_total = int(row["_n_gold_chunks"])  # in_scope đảm bảo > 0
        for k in KS:
            hit_count = sum(flags[:k])
            p_k = hit_count / k
            # Recall@K = tỉ lệ chuẩn (D-181 #2), KHÔNG còn là hit@k nhị phân:
            # |top-k ∩ gold| / |gold|, mẫu số là TỔNG chunk vàng trong index.
            r_k = hit_count / n_gold_total
            prec[k] += p_k
            rec[k] += r_k
            f1[k] += (2 * p_k * r_k / (p_k + r_k)) if (p_k + r_k) > 0 else 0.0
            ceil[k] += min(k, n_gold_total) / k

    n = len(in_scope)
    out = {
        "cau_hinh": cfg.label,
        "phuong_phap_bao_cao": method_label(cfg),
        "cand_n": cfg.cand_n,
        "so_cau": n,
        "rong": empty,
        "MRR": round(mrr / n, 4) if n else 0.0,
    }
    for k in KS:
        out[f"P@{k}"] = round(prec[k] / n, 4) if n else 0.0
        out[f"R@{k}"] = round(rec[k] / n, 4) if n else 0.0
        out[f"F1@{k}"] = round(f1[k] / n, 4) if n else 0.0
        out[f"tranP@{k}"] = round(ceil[k] / n, 4) if n else 0.0
    out.update({f"gate_{key}": val for key, val in gate_stats.summary().items()})

    # Nhóm ngoài-phạm-vi (D-181 #4/#5): tách khỏi P/R/F1@K ở trên (mẫu số 0 vô
    # nghĩa). Chỉ số đúng câu hỏi của nhóm này là "có từ chối đúng không" — hệ
    # thống KHÔNG trả về trích dẫn nào, tức không tuyên bố sai (Nguyên tắc 1).
    tu_choi_dung = None
    if out_scope:
        so_tu_choi = 0
        for row in out_scope:
            q = str(row["question"])
            ranked = rank_for(cfg, q, cache, sparse, max_k, gate_stats)
            if not ranked:
                so_tu_choi += 1
        tu_choi_dung = round(so_tu_choi / len(out_scope), 4)
    out["ngoai_pham_vi_so_cau"] = len(out_scope)
    out["ngoai_pham_vi_ti_le_tu_choi_dung"] = tu_choi_dung
    # CHỈ tính tỉ lệ từ chối đúng cho cấu hình "de_xuat" (production, có
    # RERANK_SCORE_MIN làm mốc rõ ràng) — 3 cấu hình còn lại ghi None (in ra
    # "n/a") vì RERANK_SCORE_MIN vô nghĩa khi rerank=off, và không có ngưỡng
    # tương đương đã đo cho BM25/dense thô (spec mục 3.3, "còn mở, đã chốt").
    if method_label(cfg) != "de_xuat":
        out["ngoai_pham_vi_ti_le_tu_choi_dung"] = None
    # Câu CÓ trang vàng nhưng trang đó không có chunk nào trong index: không
    # tính được P/R/F1 (mẫu số 0) và cũng KHÔNG phải câu ngoài phạm vi. Đếm
    # riêng để nó không biến mất khỏi mọi cột (0 là con số đúng hôm nay — đo
    # 2026-09-03 trên 270 câu / 16 515 chunk).
    out["suy_bien_gold_0_chunk"] = len(suy_bien)

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


# 12 cấu hình HỢP ĐỒNG (Nội dung 4 + bảng Kế hoạch Giai đoạn 3).
ALL_CONFIGS = [
    Config(mode=m, rerank=r, gate=g)
    for m in ("bm25", "dense", "hybrid")
    for r in (False, True)
    for g in (False, True)
]

# 4 "phương pháp" báo cáo CBHD (D-181 #3) — CHÍNH XÁC 4/12 dòng của ALL_CONFIGS
# ở trên, không phải danh sách rời. Thứ tự khớp METHOD_LABELS để bảng in ra
# đúng thứ tự keyword -> dense -> truyền thống -> đề xuất.
#
# `cand_n` mặc định = CANDIDATE_N = 50 (bề rộng ĐO, không phải production) — bảng
# này KHÔNG dùng cho báo cáo, chỉ giữ lại để đối chiếu 4/12 dòng ở đúng bề rộng
# 12-cấu-hình. Bảng dùng cho báo cáo chương 4/5 là REPORT_CONFIGS_PROD ngay dưới.
REPORT_CONFIGS = [Config(mode=m, rerank=r, gate=g)
                  for (m, r, g) in METHOD_LABELS]

# C-A (Critical, phản biện Opus 5, 2026-09-04): `--chi-4-phuong-phap` — bảng
# dùng thẳng cho báo cáo chương 4/5 — trước đây gọi table(..., REPORT_CONFIGS)
# nên đo ở CANDIDATE_N=50, KHÔNG phải bề rộng production thật (.env:
# RERANK_FETCH_K=BM25_FETCH_K=20). Đúng loại lỗi mà C-1 (dòng ~750 dưới) đã
# cảnh báo cho bảng 12-cấu-hình nhưng bỏ sót ở nhánh 4-phương-pháp. `PROD_N`
# và `REPORT_CONFIGS_PROD` ở cấp module để cả `--chi-4-phuong-phap` lẫn nhánh
# else (bảng "Bề rộng PRODUCTION") dùng chung MỘT định nghĩa bề rộng.
PROD_N = max(RERANK_FETCH_K, BM25_FETCH_K)
REPORT_CONFIGS_PROD = [Config(mode=m, rerank=r, gate=g, cand_n=PROD_N)
                        for (m, r, g) in METHOD_LABELS]

# Bảng phụ: CHỌN CÁCH HỢP NHẤT BẰNG SỐ (§3.3 đòi "đo cả hai rồi mới chốt").
# Miễn phí — bộ nhớ đệm không phụ thuộc cách hợp nhất, nên đây chỉ là phát lại.
# Nó cũng là chỗ DUY NHẤT nhìn thấy cái bẫy RRF: điểm RRF bị nén (hạng 1 = 1/61,
# hạng 10 = 1/70, chênh 12,86%) nên cổng lọc tương đối margin=0,3 KHÔNG cắt gì —
# tức dưới `rrf`, cột "cổng lọc bật/tắt" của bảng trên là hai hàng GIỐNG HỆT
# nhau. Cột `gate_ti_le_truy_van_bi_cat` cho thấy điều đó thay vì để nó im lặng.
FUSION_CONFIGS = [
    Config(mode=m, rerank=True, gate=g, fusion=f)
    for m in ("bm25", "dense", "hybrid")
    for f in ("rrf", "norm")
    for g in (False, True)
]


def main() -> int:
    from src.test.testset_common import (DRAFT_CSV,
                                          duong_dan_output,
                                          meta_path_for,
                                          require_human_reviewed)

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--testset-csv", default=str(DRAFT_CSV))
    ap.add_argument("--cache", default=str(DEFAULT_CACHE))
    ap.add_argument("--build-cache", action="store_true")
    ap.add_argument("--topup-cache", action="store_true")
    ap.add_argument("--allow-draft", action="store_true")
    ap.add_argument(
        "--chi-4-phuong-phap", action="store_true",
        help="Chỉ chạy 4 cấu hình CBHD yêu cầu (keyword/dense/truyền thống/"
             "đề xuất, D-181 #3) — dùng cho báo cáo chương 4/5.")
    args = ap.parse_args()

    # I-3 (phản biện Opus 5, 2026-09-04): cổng duyệt phải theo ĐÚNG
    # `--testset-csv` người dùng truyền, không phải hằng số META_JSON mặc
    # định — nếu không, trỏ --testset-csv sang một CSV khác (chưa duyệt) khi
    # meta.json mặc định vẫn human_reviewed=true (từ lượt trước) sẽ lọt cổng.
    require_human_reviewed(meta_path_for(args.testset_csv),
                           allow_draft=args.allow_draft)

    rows = load_testset(Path(args.testset_csv))
    if not rows:
        print(f"Không có dữ liệu trong {args.testset_csv}")
        return 1
    collection = open_text_collection()
    sparse = get_sparse_index(collection=collection)
    page_of, per_page = build_page_lookup(collection)
    for row in rows:
        gold = _gold_key(row)
        row["_n_gold_chunks"] = per_page.get(gold, 0) if gold else 0

    _suy_bien = [r for r in rows
                 if _gold_key(r) is not None and r["_n_gold_chunks"] == 0]
    if _suy_bien:
        print(f"\n!! {len(_suy_bien)}/{len(rows)} câu CÓ trang vàng nhưng "
              "trang đó KHÔNG có chunk nào trong index -> bị loại khỏi "
              "P/R/F1@K, và KHÔNG được tính là câu ngoài phạm vi:")
        for r in _suy_bien[:10]:
            print(f"   {_gold_key(r)}  {str(r['question'])[:60]!r}")

    # I-2 (phản biện Task 4, Opus 5): đối chiếu cột `loai` (do build_testset.py
    # ghi vào draft.csv) với kết luận suy ra thuần tuý từ source_book/
    # source_page ở `_gold_key()`. Hai nguồn phải khớp — lệch nhau nghĩa là
    # draft.csv có dữ liệu lỗi (câu van_ban/hinh thiếu source_book/source_page,
    # hoặc câu ngoai_pham_vi lại có trang vàng), KHÔNG phải lỗi của module này.
    # In cảnh báo, KHÔNG raise — cùng tinh thần "flag for review" như _suy_bien.
    _lech_loai = [r for r in rows
                  if (str(r.get("loai", "")).strip() == "ngoai_pham_vi") != (_gold_key(r) is None)]
    if _lech_loai:
        print(f"\n!! {len(_lech_loai)}/{len(rows)} câu có cột `loai` KHÔNG khớp "
              "kết luận suy ra từ source_book/source_page (dữ liệu draft.csv có "
              "vấn đề, không phải lỗi retrieval_benchmark.py):")
        for r in _lech_loai[:10]:
            print(f"   loai={r.get('loai')!r} gold={_gold_key(r)}  "
                  f"{str(r['question'])[:60]!r}")

    cache_path = Path(args.cache)
    if args.build_cache:
        cache = build_cache(rows, collection, sparse, cache_path)
    elif args.topup_cache:
        cache = topup_cache(load_cache(cache_path, collection,
                                       check_sparse_params=False),
                            rows, collection, sparse, cache_path)
    else:
        cache = load_cache(cache_path, collection)

    def table(title, configs):
        rows_out = [evaluate(c, rows, cache, sparse, page_of) for c in configs]
        head = (f"{'cấu hình':38s} "
                + " ".join(f"{'R@' + str(k):>7s}" for k in KS)
                + f" {'MRR':>7s} {'P@5':>7s} {'F1@10':>7s} {'trầnP@5':>8s}"
                + f" {'rỗng':>5s} {'cắt':>6s} {'ngPV.tcđ':>9s}")
        print(f"\n### {title}")
        print(head)
        print("-" * len(head))
        for r in rows_out:
            tcd = r.get("ngoai_pham_vi_ti_le_tu_choi_dung")
            tcd_s = f"{tcd:9.2f}" if tcd is not None else f"{'—':>9s}"
            print(f"{r['cau_hinh']:38s} "
                  + " ".join(f"{r['R@' + str(k)]:7.3f}" for k in KS)
                  + f" {r['MRR']:7.3f} {r['P@5']:7.3f} {r['F1@10']:7.3f}"
                  + f" {r['tranP@5']:8.3f}"
                  + f" {r['rong']:5d}"
                  + f" {r.get('gate_ti_le_truy_van_bi_cat', 0):6.2f}"
                  + f" {tcd_s}")
        return rows_out

    if args.chi_4_phuong_phap:
        # C-A: dùng REPORT_CONFIGS_PROD (n=PROD_N, bề rộng production thật),
        # KHÔNG phải REPORT_CONFIGS (n=CANDIDATE_N=50) — bảng này đi thẳng vào
        # báo cáo chương 4/5 nên phải đo đúng cấu hình `.env` đang chạy.
        results = table(f"4 phương pháp báo cáo (keyword/dense/truyền thống/"
                        f"đề xuất) — bề rộng PRODUCTION n={PROD_N}",
                        REPORT_CONFIGS_PROD)
        print("\n`ngPV.tcđ` = tỉ lệ TỪ CHỐI ĐÚNG trên nhóm câu ngoài phạm vi "
              "(D-181 #4): hệ thống KHÔNG trả về trích dẫn nào cho câu không "
              "thuộc corpus 12 quyển — '—' nghĩa là chỉ tính cho cấu hình "
              "`de_xuat` (production); ba phương pháp còn lại in '—'.")
    else:
        results = table("12 cấu hình hợp đồng", ALL_CONFIGS)

        # I-5 (phản biện Task 4): bảng phụ CHỌN CÁCH HỢP NHẤT BẰNG SỐ — miễn
        # phí (đọc lại từ cùng bộ nhớ đệm), nhưng là chỗ DUY NHẤT lộ ra cái
        # bẫy RRF (cổng lọc tương đối không cắt gì dưới `rrf`). Không được
        # để `FUSION_CONFIGS` là code chết — đây là bảng dùng nó.
        fusion_rows = table(
            "Chọn cách hợp nhất BẰNG SỐ, và tách riêng tác dụng của cổng lọc "
            "(rerank BẬT ở mọi hàng)", FUSION_CONFIGS)
        print("\n`cắt` = tỉ lệ truy vấn mà cổng lọc thực sự bỏ bớt ứng viên (tính trên")
        print(f"toàn bộ {CANDIDATE_N} ứng viên, không phải trên top-10).")
        results = results + fusion_rows

        # C-1 (Critical, phản biện Task 4): bảng "Bề rộng PRODUCTION" — `.env`
        # chạy RERANK_FETCH_K = 20 và BM25_FETCH_K = 20, KHÔNG phải
        # CANDIDATE_N = 50. Bảng 12-cấu-hình ở trên là TRẦN chất lượng truy
        # xuất; bảng này là thứ người dùng thật sẽ nhận. Toàn bộ số liệu hiện
        # có trong CLAUDE.md/report/tex_source/ (D-82, D-175, D-180) đo ở
        # ĐÚNG bảng này (n=20), không phải bảng n=50 ở trên — thiếu đoạn này
        # là mất khả năng tái lập những con số đó.
        prod_n = max(RERANK_FETCH_K, BM25_FETCH_K)
        if prod_n != CANDIDATE_N:
            prod_rows = table(
                f"Bề rộng PRODUCTION ({prod_n} ứng viên/kênh, không phải "
                f"{CANDIDATE_N}) — đây là thứ người dùng thật nhận",
                [Config(mode=m, rerank=True, gate=g, cand_n=prod_n)
                 for m in ("bm25", "dense", "hybrid") for g in (False, True)])
            results = results + prod_rows

    out_csv = duong_dan_output("retrieval_report.csv", args.allow_draft)
    out_md = duong_dan_output("retrieval_report.md", args.allow_draft)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    for r in results:
        for k in r:
            if k not in fields:
                fields.append(k)
    with io.open(out_csv, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, restval="")
        w.writeheader()
        w.writerows(results)
    # I-6 (phản biện Task 4): ghi bảng markdown THẬT (header + từng hàng của
    # `results`, đúng các cột đã in ra console) thay vì stub 2 dòng vô nghĩa.
    # Tính năng MỚI so với `ablation.py` gốc (nó chưa từng ghi .md) — làm gọn,
    # không cố bọc lại toàn bộ định dạng của bảng console.
    md_cols = ["cau_hinh", "phuong_phap_bao_cao", "cand_n", "so_cau"] + \
        [f"R@{k}" for k in KS] + ["MRR", "P@5", "F1@10", "tranP@5", "rong",
                                   "gate_ti_le_truy_van_bi_cat",
                                   "ngoai_pham_vi_so_cau",
                                   "ngoai_pham_vi_ti_le_tu_choi_dung",
                                   "suy_bien_gold_0_chunk"]
    md_lines = [f"# Bảng đối chiếu truy xuất\n", f"{len(results)} cấu hình.\n",
                "| " + " | ".join(md_cols) + " |",
                "|" + "|".join("---" for _ in md_cols) + "|"]
    for r in results:
        md_lines.append(
            "| " + " | ".join(str(r.get(c, "")) for c in md_cols) + " |")
    with io.open(out_md, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md_lines) + "\n")
    print(f"\nĐã lưu: {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
