"""Bản đồ trang: lọc candidate theo parity + mô hình offset toàn quyển.

Toàn bộ module này là logic thuần (không OCR, không I/O) nên mọi quy tắc đúng/sai
đều test được bằng fixture tổng hợp. Adapter OCR nằm ở `page_number_ocr.py`.

Hai bằng chứng đo được trên corpus KNTT (spec §1.1) định hình module này:
1. `printed_page == pdf_index` cả 4 quyển — nhưng offset vẫn phải được *suy ra*,
   không hardcode, để một quyển có trang bìa không số cũng xử lý đúng.
2. Parity đúng 695/695: giá trị CHẴN in ở lề trái, LẺ ở lề phải. Ràng buộc đặt
   trên *giá trị đọc được* nên không vòng tròn (không cần biết trước số trang).
"""
from __future__ import annotations

import collections
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence


class PageMapError(RuntimeError):
    """Không dựng được bản đồ trang đáng tin — phải dừng, không được đoán."""


@dataclass(frozen=True)
class NumberCandidate:
    value: int
    conf: float
    side: str          # "L" | "R"


@dataclass(frozen=True)
class OffsetFit:
    offset: int
    votes: int
    total: int

    @property
    def ratio(self) -> float:
        return (self.votes / self.total) if self.total else 0.0


@dataclass(frozen=True)
class PageRecord:
    pdf_index: int
    printed_page: int
    source: str        # "ocr_confirmed" | "model_inferred"
    side: Optional[str] = None
    conf: Optional[float] = None


def _expected_side(value: int) -> str:
    return "L" if value % 2 == 0 else "R"


def keep_parity(cands: Sequence[NumberCandidate]) -> list[NumberCandidate]:
    return [c for c in cands if c.side == _expected_side(c.value)]


def fit_offset(reads: Mapping[int, Sequence[NumberCandidate]]) -> OffsetFit:
    votes: collections.Counter[int] = collections.Counter()
    for index, cands in reads.items():
        for cand in keep_parity(cands):
            votes[cand.value - index] += 1
    if not votes:
        raise PageMapError(
            "không đọc được số trang nào hợp parity — không thể dựng bản đồ trang")
    offset, count = votes.most_common(1)[0]
    return OffsetFit(offset=offset, votes=count, total=sum(votes.values()))


def build_page_map(n_pages: int,
                   reads: Mapping[int, Sequence[NumberCandidate]],
                   fit: OffsetFit,
                   min_ratio: float = 0.8) -> list[PageRecord]:
    if fit.ratio < min_ratio:
        raise PageMapError(
            f"đồng thuận offset quá yếu: {fit.votes}/{fit.total} "
            f"({fit.ratio:.0%} < {min_ratio:.0%}) cho offset {fit.offset}")
    out: list[PageRecord] = []
    for index in range(n_pages):
        printed = index + fit.offset
        match = next((c for c in keep_parity(reads.get(index, ()))
                      if c.value == printed), None)
        if match is None:
            out.append(PageRecord(index, printed, "model_inferred"))
        else:
            out.append(PageRecord(index, printed, "ocr_confirmed",
                                  side=match.side, conf=match.conf))
    return out
