"""Bản đồ trang: lọc candidate theo parity + mô hình offset toàn quyển.

Toàn bộ module này là logic thuần (không OCR, không I/O) nên mọi quy tắc đúng/sai
đều test được bằng fixture tổng hợp. Adapter OCR nằm ở `page_number_ocr.py`.

Ba bằng chứng đo được trên corpus KNTT định hình module này:

1. **`printed_page == page_index − 1`** cả 4 quyển (`page_001.png` = trang in 0 =
   bìa trước) — nhưng offset vẫn phải được *suy ra*, không hardcode.
2. **Parity không có ngoại lệ**: giá trị CHẴN in ở lề trái, LẺ ở lề phải. Ràng
   buộc đặt trên *giá trị đọc được* nên không vòng tròn (không cần biết trước số
   trang).
3. **Trang nguồn có thể có LỖ.** `page_index` là *số trong tên file*, không phải
   thứ tự enumerate: sách 9 từng thiếu 19 trang giữa quyển. Vì vậy
   `build_page_map` duyệt **tập số trang có thật** và **flag** lỗ ra thay vì lấp
   im lặng — bản cũ duyệt `range(n_pages)`, một bug chờ xảy ra (spec Task 5).
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
    page_index: int    # SỐ TRONG TÊN FILE (nguồn tự đánh), không phải thứ tự
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
    for page_index, cands in reads.items():
        for cand in keep_parity(cands):
            votes[cand.value - page_index] += 1
    if not votes:
        raise PageMapError(
            "không đọc được số trang nào hợp parity — không thể dựng bản đồ trang")
    offset, count = votes.most_common(1)[0]
    return OffsetFit(offset=offset, votes=count, total=sum(votes.values()))


def missing_page_indices(page_indices: Sequence[int]) -> list[int]:
    """Các số trang THIẾU giữa min..max của dãy. Rỗng = liền mạch."""
    numbers = sorted(set(page_indices))
    if not numbers:
        return []
    present = set(numbers)
    return [n for n in range(numbers[0], numbers[-1] + 1) if n not in present]


def build_page_map(page_indices: Sequence[int],
                   reads: Mapping[int, Sequence[NumberCandidate]],
                   fit: OffsetFit,
                   min_ratio: float = 0.8) -> list[PageRecord]:
    """Một record cho mỗi trang CÓ THẬT trong `page_indices`.

    Không bịa record cho số trang không tồn tại (lỗ trong dãy) — lỗ được báo
    riêng qua `missing_page_indices`, việc của caller là flag nó ra.
    """
    if fit.ratio < min_ratio:
        raise PageMapError(
            f"đồng thuận offset quá yếu: {fit.votes}/{fit.total} "
            f"({fit.ratio:.0%} < {min_ratio:.0%}) cho offset {fit.offset}")
    out: list[PageRecord] = []
    for page_index in sorted(set(page_indices)):
        printed = page_index + fit.offset
        match = next((c for c in keep_parity(reads.get(page_index, ()))
                      if c.value == printed), None)
        if match is None:
            out.append(PageRecord(page_index, printed, "model_inferred"))
        else:
            out.append(PageRecord(page_index, printed, "ocr_confirmed",
                                  side=match.side, conf=match.conf))
    return out
