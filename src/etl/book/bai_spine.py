"""Dựng spine Chương/Bài bằng cách đối chiếu 3 nguồn.

Nguồn: (1) MỤC LỤC = giả thuyết, (2) banner "Bài N" trong trang = trang thật,
(3) ràng buộc toàn cục: `bai_so` tăng ngặt và `start` tăng ngặt.

Nguyên tắc: banner thắng TOC về *trang*; TOC cấp *tiêu đề*. Lỗi lẻ chỉ được sửa
khi ràng buộc đơn điệu chỉ ra **đúng một** ứng viên (ví dụ "Bài 3" kẹp giữa 30 và
32 thì chỉ 31 hợp), và mọi lần sửa đều để lại flag. Không giải được thì **bỏ hit
đó + flag**, tuyệt đối không đoán (spec §2, §3.2).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class BannerHit:
    pdf_index: int
    bai_so: int


@dataclass(frozen=True)
class BaiRecord:
    bai_so: int
    title: str
    start: int
    end: int
    source: str


@dataclass(frozen=True)
class SpineFlag:
    kind: str
    detail: str


def _repair_candidate(observed: int, lower: Optional[int], upper: Optional[int],
                      known: Sequence[int]) -> Optional[int]:
    """Số bài duy nhất trong (lower, upper) mà `observed` là tiền tố của nó."""
    fits = [b for b in known
            if (lower is None or b > lower)
            and (upper is None or b < upper)
            and str(b).startswith(str(observed))
            and b != observed]
    return fits[0] if len(fits) == 1 else None


def build_bai_spine(toc, banners, n_pages: int):
    titles = {e.bai_so: e.title for e in toc}
    toc_pages = {e.bai_so: e.start_page for e in toc}
    known = sorted(titles)
    flags: list[SpineFlag] = []

    # 1. banner hits theo thứ tự trang, sửa/loại cho đơn điệu
    accepted: list[BannerHit] = []
    hits = sorted(banners, key=lambda h: h.pdf_index)
    for position, hit in enumerate(hits):
        previous = accepted[-1].bai_so if accepted else None
        following = next((h.bai_so for h in hits[position + 1:]
                          if previous is None or h.bai_so > previous), None)
        bai_so = hit.bai_so
        if previous is not None and bai_so <= previous:
            repaired = _repair_candidate(bai_so, previous, following, known)
            if repaired is None:
                flags.append(SpineFlag(
                    "banner_out_of_order",
                    f"trang {hit.pdf_index}: Bài {bai_so} không tăng sau Bài "
                    f"{previous} và không sửa được -> bỏ hit"))
                continue
            flags.append(SpineFlag(
                "bai_so_repaired",
                f"trang {hit.pdf_index}: {bai_so} -> {repaired} "
                f"(kẹp giữa {previous} và {following})"))
            bai_so = repaired
        accepted.append(BannerHit(hit.pdf_index, bai_so))

    starts: dict[int, tuple[int, str]] = {}
    for hit in accepted:
        starts[hit.bai_so] = (hit.pdf_index, "banner+toc" if hit.bai_so in titles
                              else "banner")
        if hit.bai_so in toc_pages and toc_pages[hit.bai_so] != hit.pdf_index:
            flags.append(SpineFlag(
                "toc_page_mismatch",
                f"Bài {hit.bai_so}: TOC ghi trang {toc_pages[hit.bai_so]}, "
                f"banner ở trang {hit.pdf_index} -> lấy banner"))
        if hit.bai_so not in titles:
            flags.append(SpineFlag(
                "banner_without_toc",
                f"Bài {hit.bai_so} ở trang {hit.pdf_index} không có trong MỤC LỤC"))

    # 2. bài chỉ có trong TOC -> dùng trang của TOC, ghi flag
    for entry in toc:
        if entry.bai_so in starts:
            continue
        starts[entry.bai_so] = (entry.start_page, "toc")
        flags.append(SpineFlag(
            "toc_without_banner",
            f"Bài {entry.bai_so}: không thấy banner, dùng trang TOC "
            f"{entry.start_page}"))

    # 3. dựng record + khoảng trang
    ordered = sorted(starts.items(), key=lambda kv: kv[1][0])
    spine: list[BaiRecord] = []
    for position, (bai_so, (start, source)) in enumerate(ordered):
        end = (ordered[position + 1][1][0] - 1) if position + 1 < len(ordered) \
            else n_pages - 1
        spine.append(BaiRecord(bai_so=bai_so, title=titles.get(bai_so, ""),
                               start=start, end=max(start, end), source=source))
    return spine, flags
