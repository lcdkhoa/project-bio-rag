# -*- coding: utf-8 -*-
"""Hợp nhất kênh THƯA + kênh DÀY, và cổng lọc liên quan tách rời khỏi rerank.

## Vì sao hai thang điểm không cộng thẳng được

Kênh dày trả **khoảng cách** (nhỏ = gần), kênh thưa trả **điểm BM25** (lớn = tốt),
và BM25 không có cận trên. Cộng thẳng là vô nghĩa. Hai cách hợp lệ, ở đây có cả
hai vì đề cương đòi chọn bằng số chứ không bằng cảm tính:

- **RRF** (`rrf`) — chỉ dùng **thứ hạng**, nên miễn nhiễm với thang điểm. Mặc
  định hợp lý.
- **Chuẩn hoá min-max** (`norm`) — đưa mỗi kênh về [0,1] rồi cộng có trọng số.
  Giữ được **độ chênh** giữa hạng 1 và hạng 2, thứ mà RRF vứt đi.

## Cái bẫy của cổng lọc, đã lường trước

`RETRIEVER_DISTANCE_MARGIN = 0.3` là cổng theo **khoảng cách dày**. Sau khi hợp
nhất, thứ tự không còn do khoảng cách quyết định nữa, nên cổng cũ **có thể trở
thành vô nghĩa mà vẫn chạy êm** — đúng loại hỏng âm thầm mà repo này sợ nhất.

Cụ thể với RRF: điểm hạng 1 là `1/(60+1) = 0,01639`, hạng 10 là
`1/(60+10) = 0,01429` — chênh **12,8%**, tức một cổng tương đối `margin = 0,3`
**không bao giờ cắt gì** trong top 10. Đây là số tính ra được, không phải phỏng
đoán, và `gate_stats()` đo lại nó trên bộ test thật.

Nên `relevance_gate` ở đây là bản **tổng quát hoá** của cổng cũ: nó nhận thêm
`higher_is_better` để chạy được trên cả khoảng cách lẫn điểm. Ở đúng ngữ cảnh cũ
(một kênh dày, `higher_is_better=False`) nó trả về **đúng** kết quả của
`RelevanceGatedRetriever` — có test chốt điều đó.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Hashable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


@dataclass
class FusedItem:
    """Một ứng viên sau hợp nhất, còn giữ dấu vết của TỪNG kênh để giải thích."""

    key: Hashable
    score: float
    dense_rank: Optional[int] = None
    dense_distance: Optional[float] = None
    sparse_rank: Optional[int] = None
    sparse_score: Optional[float] = None
    payload: object = None

    @property
    def channels(self) -> str:
        both = []
        if self.dense_rank is not None:
            both.append("dense")
        if self.sparse_rank is not None:
            both.append("sparse")
        return "+".join(both) or "-"


def _rank_map(keys: Sequence[Hashable]) -> Dict[Hashable, int]:
    """Thứ hạng 1-based, giữ lần xuất hiện ĐẦU TIÊN nếu khoá trùng."""
    out: Dict[Hashable, int] = {}
    for i, k in enumerate(keys):
        out.setdefault(k, i + 1)
    return out


def _minmax(values: Sequence[float], higher_is_better: bool) -> List[float]:
    """Đưa về [0,1], 1 = tốt nhất. Mọi giá trị bằng nhau -> tất cả 1,0."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [1.0] * len(values)
    if higher_is_better:
        return [(v - lo) / (hi - lo) for v in values]
    return [(hi - v) / (hi - lo) for v in values]


def fuse(
    dense: Sequence[Tuple[Hashable, float]],
    sparse: Sequence[Tuple[Hashable, float]],
    method: str = "rrf",
    rrf_k: int = 60,
    dense_weight: float = 0.5,
    payloads: Optional[Dict[Hashable, object]] = None,
) -> List[FusedItem]:
    """Hợp nhất hai danh sách xếp hạng thành một, sắp giảm dần theo điểm.

    `dense` là `(khoá, KHOẢNG CÁCH)` — nhỏ hơn là tốt hơn.
    `sparse` là `(khoá, ĐIỂM BM25)` — lớn hơn là tốt hơn.
    Một kênh rỗng thì hàm trả về **đúng** thứ tự của kênh còn lại (test chốt) —
    đây là điều kiện tự kiểm mà §3.3 đòi: "hybrid tắt kênh thưa == dense thuần".
    """
    dense = list(dense)
    sparse = list(sparse)
    payloads = payloads or {}

    d_rank = _rank_map([k for k, _ in dense])
    s_rank = _rank_map([k for k, _ in sparse])
    d_val = {}
    for k, v in dense:
        d_val.setdefault(k, v)
    s_val = {}
    for k, v in sparse:
        s_val.setdefault(k, v)

    if method == "rrf":
        scores: Dict[Hashable, float] = {}
        for k, r in d_rank.items():
            scores[k] = scores.get(k, 0.0) + dense_weight / (rrf_k + r)
        for k, r in s_rank.items():
            scores[k] = scores.get(k, 0.0) + (1.0 - dense_weight) / (rrf_k + r)
    elif method == "norm":
        d_keys = list(d_rank)
        s_keys = list(s_rank)
        d_norm = dict(zip(d_keys, _minmax([d_val[k] for k in d_keys], False)))
        s_norm = dict(zip(s_keys, _minmax([s_val[k] for k in s_keys], True)))
        scores = {}
        for k in set(d_keys) | set(s_keys):
            # Khoá vắng ở một kênh nhận 0 Ở KÊNH ĐÓ — không phải bị loại. Kênh
            # thưa và kênh dày sót nhau là chuyện bình thường, và đó chính là lý
            # do hợp nhất tồn tại.
            scores[k] = (dense_weight * d_norm.get(k, 0.0)
                         + (1.0 - dense_weight) * s_norm.get(k, 0.0))
    else:
        raise ValueError(f"method={method!r} phải là 'rrf' hoặc 'norm'")

    items = [
        FusedItem(
            key=k,
            score=scores[k],
            dense_rank=d_rank.get(k),
            dense_distance=d_val.get(k),
            sparse_rank=s_rank.get(k),
            sparse_score=s_val.get(k),
            payload=payloads.get(k),
        )
        for k in scores
    ]
    # Sắp xếp ỔN ĐỊNH: điểm giảm dần, hoà thì ưu tiên hạng dày rồi hạng thưa.
    items.sort(key=lambda it: (
        -it.score,
        it.dense_rank if it.dense_rank is not None else 10**9,
        it.sparse_rank if it.sparse_rank is not None else 10**9,
    ))
    return items


def relevance_gate(
    scores: Sequence[float],
    margin: float,
    higher_is_better: bool,
) -> List[bool]:
    """Cổng lọc TƯƠNG ĐỐI quanh ứng viên tốt nhất. Trả cờ giữ/bỏ theo thứ tự vào.

    Với khoảng cách (`higher_is_better=False`): giữ khi `d <= best*(1+margin)`
    — **đúng công thức của `RelevanceGatedRetriever`** (có test chốt).
    Với điểm (`higher_is_better=True`): giữ khi `s >= best*(1-margin)`.
    """
    if not scores:
        return []
    if higher_is_better:
        best = max(scores)
        cutoff = best * (1.0 - margin)
        return [s >= cutoff for s in scores]
    best = min(scores)
    cutoff = best * (1.0 + margin)
    return [s <= cutoff for s in scores]


@dataclass
class GateStats:
    """Cổng lọc CÓ THỰC SỰ CẮT không — số để dán vào báo cáo, không phải cảm tính."""

    n_queries: int = 0
    n_candidates: int = 0
    n_kept: int = 0
    n_queries_gate_cut: int = 0
    spreads: List[float] = field(default_factory=list)

    def observe(self, scores: Sequence[float], keep: Sequence[bool]) -> None:
        if not scores:
            return
        self.n_queries += 1
        self.n_candidates += len(scores)
        self.n_kept += sum(1 for k in keep if k)
        if not all(keep):
            self.n_queries_gate_cut += 1
        lo, hi = min(scores), max(scores)
        self.spreads.append((hi - lo) / hi if hi > 0 else 0.0)

    def summary(self) -> Dict[str, float]:
        n = max(self.n_queries, 1)
        return {
            "so_truy_van": self.n_queries,
            "ung_vien_tb": round(self.n_candidates / n, 2),
            "giu_lai_tb": round(self.n_kept / n, 2),
            "ti_le_truy_van_bi_cat": round(self.n_queries_gate_cut / n, 4),
            "do_trai_diem_tb": round(
                sum(self.spreads) / max(len(self.spreads), 1), 4),
        }
