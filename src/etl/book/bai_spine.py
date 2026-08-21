"""Dựng spine Chương/Bài từ MỤC LỤC, dùng banner để ĐỐI CHIẾU.

## Đổi vai so với bản trước (đo được 2026-08-21, xem D-43)

Bản trước cho **banner thắng TOC** về số trang, lý do: "banner là trang thật".
Đo lại trên nguồn PNG thì tương quan độ tin cậy đã đảo ngược:

* MỤC LỤC đọc bằng bộ đọc BẢNG mới (`toc.py`): sách 9 ra **51/51 Bài liền mạch**,
  sách 6 ra **55/55** (bản cũ ra 0 vì hardcode thiếu trang MỤC LỤC thứ ba).
* Banner "Bài N" nằm trong một huy hiệu tròn ở đỉnh trang: recall đo trên 17 Bài
  đầu của sách 6 chỉ khoảng **2/3**, và có ô đọc ra **hai số mâu thuẫn**
  (Bài 13 đọc được cả `13` lẫn `15`).

Một nguồn đọc gần đủ và tự nhất quán thì không thể để một nguồn đọc 2/3 kèm mâu
thuẫn ghi đè. Vì vậy: **TOC dựng spine, banner chỉ xác nhận**. Banner lệch thì
ghi `banner_toc_mismatch` để người xem — không im lặng, cũng không tự sửa.

Banner vẫn giữ giá trị: nó là nguồn ĐỘC LẬP duy nhất chứng minh trang mở Bài có
thật, nên tỉ lệ đồng thuận banner/TOC là một con số báo cáo được (cổng G1).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from .toc import TocEntry


@dataclass(frozen=True)
class BaiRecord:
    bai_so: int
    title: str
    start: int          # SỐ TRANG NGUỒN (page_index) nơi Bài bắt đầu
    end: int
    source: str


@dataclass(frozen=True)
class SpineFlag:
    kind: str
    detail: str


def _from_banners_only(banners: Mapping, flags: list) -> list:
    """Không có MỤC LỤC: dựng tạm từ banner, chỉ nhận ô đọc ra ĐÚNG MỘT số."""
    picks = []
    for page_index in sorted(banners):
        candidates = banners[page_index]
        if len(candidates) == 1:
            picks.append((page_index, next(iter(candidates))))
        elif candidates:
            flags.append(SpineFlag(
                "banner_ambiguous",
                f"trang {page_index}: huy hiệu đọc ra nhiều số "
                f"{sorted(candidates)} -> bỏ, không chọn bừa"))
    accepted = []
    for page_index, bai_so in picks:
        if accepted and bai_so <= accepted[-1][1]:
            flags.append(SpineFlag(
                "banner_out_of_order",
                f"trang {page_index}: Bài {bai_so} không tăng sau Bài "
                f"{accepted[-1][1]} -> bỏ hit"))
            continue
        accepted.append((page_index, bai_so))
    return accepted


def build_bai_spine(toc: Sequence[TocEntry],
                    banners: Mapping[int, frozenset],
                    last_page_index: int) -> tuple[list, list]:
    """`toc` mang `start_page` đã đổi sang HỆ page_index (xem `manifest.py`).

    `banners` là `{page_index: set(số Bài đọc được trên huy hiệu)}`.
    `last_page_index` = SỐ TRANG NGUỒN cuối cùng, để đóng khoảng của Bài cuối —
    không phải `n_pages`: dãy trang có thể có lỗ.
    """
    flags: list[SpineFlag] = []
    banners = {int(k): frozenset(v) for k, v in (banners or {}).items() if v}

    toc_driven = bool(toc)
    if toc_driven:
        starts = [(entry.start_page, entry.bai_so, entry.title, "toc")
                  for entry in toc]
    else:
        flags.append(SpineFlag(
            "toc_empty", "MỤC LỤC không cho entry nào -> dựng tạm từ banner"))
        starts = [(page_index, bai_so, "", "banner")
                  for page_index, bai_so in _from_banners_only(banners, flags)]

    # --- đối chiếu banner (không ghi đè, chỉ xác nhận hoặc flag)
    start_of_bai = {bai_so: page_index for page_index, bai_so, _t, _s in starts}
    bai_at_page = {page_index: bai_so for page_index, bai_so, _t, _s in starts}
    confirmed: set = set()
    # Không có MỤC LỤC thì banner CHÍNH LÀ spine — không có gì để đối chiếu, và
    # chạy vòng dưới sẽ kêu `banner_without_toc` cho đúng cái banner vừa dùng.
    for page_index, candidates in (sorted(banners.items()) if toc_driven else ()):
        expected = bai_at_page.get(page_index)
        if expected is not None:
            if expected in candidates:
                confirmed.add(expected)
            else:
                flags.append(SpineFlag(
                    "banner_toc_mismatch",
                    f"trang {page_index}: MỤC LỤC nói Bài {expected}, huy hiệu "
                    f"đọc ra {sorted(candidates)} -> giữ MỤC LỤC"))
            continue
        unknown = {c for c in candidates if c not in start_of_bai}
        if unknown:
            flags.append(SpineFlag(
                "banner_without_toc",
                f"trang {page_index}: huy hiệu đọc ra Bài {sorted(unknown)} "
                f"không có trong MỤC LỤC"))

    # --- dựng record + khoảng trang
    ordered = sorted(starts)
    spine: list[BaiRecord] = []
    for position, (start, bai_so, title, source) in enumerate(ordered):
        end = (ordered[position + 1][0] - 1) if position + 1 < len(ordered) \
            else last_page_index
        spine.append(BaiRecord(
            bai_so=bai_so, title=title, start=start, end=max(start, end),
            source=f"{source}+banner" if bai_so in confirmed else source))

    for position in range(len(spine) - 1):
        current, following = spine[position], spine[position + 1]
        if following.bai_so <= current.bai_so:
            flags.append(SpineFlag(
                "spine_out_of_order",
                f"Bài {current.bai_so} (trang {current.start}) không tăng trước "
                f"Bài {following.bai_so} (trang {following.start})"))

    return spine, flags


def banner_agreement(spine: Sequence[BaiRecord]) -> tuple[int, int]:
    """(số Bài được banner xác nhận, tổng số Bài) — con số báo cáo cho G1."""
    return sum(1 for r in spine if r.source.endswith("+banner")), len(spine)
