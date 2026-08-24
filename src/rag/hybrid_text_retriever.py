# -*- coding: utf-8 -*-
"""Đường truy xuất VĂN BẢN sau M2: thưa + dày -> cổng lọc -> rerank.

Đừng nhầm với `hybrid_retriever.py`: cái đó lai **văn bản + ảnh**. Cái này lai
**thưa + dày**, đúng nghĩa "hybrid search" của đề cương.

    truy vấn
      ├─ dày:  Chroma similarity_search_with_score  -> (chunk_id, khoảng cách)
      └─ thưa: BM25Index.search                     -> (chunk_id, điểm)
                 |
            hợp nhất (RRF hoặc chuẩn hoá min-max)
                 |
            cổng lọc liên quan   (RELEVANCE_GATE_ENABLED)
                 |
            rerank cross-encoder (RERANK_ENABLED) + sàn RERANK_SCORE_MIN
                 |
            top `max_k` Document

**Thứ tự này là bắt buộc và không được đảo**: điểm hợp nhất KHÔNG thay thế
rerank. Cross-encoder đọc cả câu hỏi lẫn đoạn văn cùng lúc; điểm hợp nhất chỉ
biết hai thứ hạng.

## Một điều phải nói thẳng: TRƯỚC M2 hai thành phần này bị TRỘN

`VectorDB.get_retriever()` cũ chọn **một trong hai**: `RERANK_ENABLED=true` thì
trả `RerankedRetriever` và `RelevanceGatedRetriever` **không bao giờ chạy**. Tức
trong cấu hình đang chạy thật, `RETRIEVER_DISTANCE_MARGIN = 0.3` là **số chết**,
còn cổng lọc thực sự đang hoạt động là sàn tuyệt đối `RERANK_SCORE_MIN = 0.2`.
Nội dung 4 đòi bật/tắt **từng** thành phần, nên ở đây hai thứ tách hẳn ra.

## Cổng lọc: định nghĩa ĐÃ ĐỔI, và nói rõ là đã đổi

Cổng cũ so **khoảng cách dày**. Sau hợp nhất thì thứ tự không do khoảng cách
quyết định nữa, nên cổng được tổng quát thành "tương đối quanh ứng viên tốt
nhất **theo điểm xếp hạng hiện hành**" (`fusion.relevance_gate`). Ở đúng ngữ
cảnh cũ (một kênh dày) nó trả về **đúng** kết quả cũ — có test chốt.

Cảnh báo đã tính ra được: với RRF, điểm hạng 1 là 1/61 và hạng 10 là 1/70 —
chênh **12,8%**, nằm gọn trong `margin = 0.3`, nên cổng tương đối **không cắt gì
trong top 10**. Đó là lý do `FUSION_METHOD = "norm"` tồn tại: chuẩn hoá min-max
giữ lại độ chênh thật nên cổng mới có nghĩa. Chọn cái nào là việc của bảng số,
không phải của trực giác.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict

from ..config import (
    BM25_B,
    BM25_FETCH_K,
    BM25_K1,
    BM25_TOKENIZER,
    FUSION_DENSE_WEIGHT,
    FUSION_METHOD,
    FUSION_RRF_K,
    RELEVANCE_GATE_ENABLED,
    RERANK_ENABLED,
    RERANK_FETCH_K,
    RERANK_SCORE_MIN,
    RETRIEVAL_MODE,
    RETRIEVER_DISTANCE_MARGIN,
    RETRIEVER_MAX_K,
)
from .fusion import fuse, relevance_gate
from .reranker import get_reranker

logger = logging.getLogger(__name__)


class ChunkLookup:
    """Ánh xạ hai chiều giữa `chunk_id` và (văn bản, metadata). Nạp MỘT lần.

    Cần vì `langchain-chroma` trả `Document` **không kèm id**, còn chỉ mục thưa
    chỉ nói chuyện bằng `chunk_id`. Khớp bằng bộ ba
    `(source, page_index, chunk_index)` — đúng ba khoá dựng nên `chunk_id`, nên
    ánh xạ là **song ánh** và hàm dựng sẽ raise nếu không phải. Khớp bằng NỘI
    DUNG thì không được: `overlap=120` làm hai chunk kề nhau chia ~30% chữ.
    """

    def __init__(self, collection):
        got = collection.get(include=["documents", "metadatas"], limit=1_000_000)
        self.text: Dict[str, str] = {}
        self.meta: Dict[str, dict] = {}
        self._by_triple: Dict[Tuple[str, int, int], str] = {}
        for cid, doc, meta in zip(got["ids"], got["documents"], got["metadatas"]):
            meta = meta or {}
            self.text[cid] = doc or ""
            self.meta[cid] = dict(meta)
            triple = (str(meta.get("source")), int(meta.get("page_index", -1)),
                      int(meta.get("chunk_index", -1)))
            if triple in self._by_triple:
                raise RuntimeError(
                    f"Khoá {triple} trùng ở hai chunk — không còn là song ánh, "
                    "không hợp nhất hai kênh theo chunk_id được.")
            self._by_triple[triple] = cid

    def id_of(self, doc: Document) -> str:
        meta = doc.metadata or {}
        triple = (str(meta.get("source")), int(meta.get("page_index", -1)),
                  int(meta.get("chunk_index", -1)))
        cid = self._by_triple.get(triple)
        if cid is None:
            raise RuntimeError(
                f"Không khớp được Document {triple} về chunk_id. Chỉ mục thưa và "
                "index dày đang nhìn hai tập dữ liệu khác nhau.")
        return cid

    def document(self, cid: str) -> Document:
        return Document(page_content=self.text[cid],
                        metadata=dict(self.meta[cid]))


class HybridTextRetriever(BaseRetriever):
    """Truy xuất văn bản có công tắc cho đủ 12 cấu hình ablation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    vectorstore: Any
    lookup: Any
    sparse: Any = None
    mode: str = RETRIEVAL_MODE
    max_k: int = RETRIEVER_MAX_K
    dense_fetch_k: int = RERANK_FETCH_K
    sparse_fetch_k: int = BM25_FETCH_K
    fusion_method: str = FUSION_METHOD
    rrf_k: int = FUSION_RRF_K
    dense_weight: float = FUSION_DENSE_WEIGHT
    gate_enabled: bool = RELEVANCE_GATE_ENABLED
    gate_margin: float = RETRIEVER_DISTANCE_MARGIN
    rerank_enabled: bool = RERANK_ENABLED
    rerank_score_min: float = RERANK_SCORE_MIN
    k1: float = BM25_K1
    b: float = BM25_B
    reranker: Any = None

    def _dense(self, query: str) -> List[Tuple[str, float]]:
        if self.mode == "bm25":
            return []
        scored = self.vectorstore.similarity_search_with_score(
            query, k=self.dense_fetch_k)
        pairs = [(self.lookup.id_of(doc), float(dist)) for doc, dist in scored]
        pairs.sort(key=lambda p: p[1])
        return pairs

    def _sparse(self, query: str) -> List[Tuple[str, float]]:
        if self.mode == "dense":
            return []
        if self.sparse is None:
            raise RuntimeError(
                f"RETRIEVAL_MODE={self.mode!r} cần chỉ mục thưa nhưng không có. "
                "Dựng bằng: python main.py --build-bm25")
        return self.sparse.search(query, k=self.sparse_fetch_k, k1=self.k1,
                                  b=self.b,
                                  fold_accents=(BM25_TOKENIZER == "folded"))

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        dense = self._dense(query)
        sparse = self._sparse(query)
        # Chỉ một kênh thì trọng số phải là 1 cho kênh đó, nếu không RRF sẽ chia
        # đôi điểm và điểm tuyệt đối lệch khỏi "dense thuần" — thứ hạng vẫn đúng
        # nhưng cổng lọc tương đối thì KHÔNG.
        weight = {"dense": 1.0, "bm25": 0.0}.get(self.mode, self.dense_weight)
        items = fuse(dense, sparse, method=self.fusion_method, rrf_k=self.rrf_k,
                     dense_weight=weight)
        n_fused = len(items)

        n_after_gate = n_fused
        if self.gate_enabled and items:
            keep = relevance_gate([it.score for it in items], self.gate_margin,
                                  higher_is_better=True)
            items = [it for it, k in zip(items, keep) if k]
            n_after_gate = len(items)

        if self.rerank_enabled and items:
            reranker = self.reranker or get_reranker()
            docs = [self.lookup.document(it.key) for it in items]
            ce = reranker.score(query, [d.page_content for d in docs])
            if not ce or len(ce) != len(docs):
                # KHÔNG im lặng xếp theo điểm hợp nhất: rerank tắt âm thầm đã
                # cắn thật một lần (HF_HUB_OFFLINE=1 + RERANK_MODEL là HF id).
                raise RuntimeError(
                    f"Cross-encoder trả {len(ce) if ce else 0} điểm cho "
                    f"{len(docs)} đoạn — rerank KHÔNG chạy. Kiểm RERANK_MODEL "
                    "(phải là đường dẫn local khi HF_HUB_OFFLINE=1).")
            paired = sorted(zip(items, docs, ce), key=lambda t: -t[2])
            out: List[Document] = []
            for it, doc, score in paired:
                if score < self.rerank_score_min:
                    break
                doc.metadata["rerank_score"] = round(float(score), 4)
                doc.metadata["retrieval_channels"] = it.channels
                out.append(doc)
                if len(out) >= self.max_k:
                    break
        else:
            out = []
            for it in items[: self.max_k]:
                doc = self.lookup.document(it.key)
                doc.metadata["fusion_score"] = round(it.score, 6)
                doc.metadata["retrieval_channels"] = it.channels
                out.append(doc)

        logger.info(
            "HybridTextRetriever[%s]: dày=%d thưa=%d -> hợp nhất=%d -> cổng lọc "
            "(%s)=%d -> rerank(%s) -> %d cho truy vấn %r",
            self.mode, len(dense), len(sparse), n_fused,
            "bật" if self.gate_enabled else "tắt", n_after_gate,
            "bật" if self.rerank_enabled else "tắt", len(out), query,
        )
        return out
