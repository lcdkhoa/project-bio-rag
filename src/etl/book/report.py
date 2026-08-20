"""Báo cáo cổng G1: định danh trang có đủ tin để đi tiếp hay không.

Ngưỡng (spec §4): 100% trang có `printed_page`, >= 95% là `ocr_confirmed`, và
**0** conflict spine chưa giải. `page_number_not_read` KHÔNG phải conflict — nó
đã được mô hình offset xử lý và ghi provenance; chỉ tỉ lệ confirmed mới chặn.

`spine_out_of_order` (bổ sung sau review Task 5) LÀ một conflict: nó nghĩa là
thứ tự Bài mâu thuẫn với thứ tự trang trong spine đã dựng — không thể coi là đã
giải quyết chỉ vì mỗi trang có số. Ngưỡng G1 cho conflict là 0, nên nó vào
UNRESOLVED_FLAG_KINDS như banner_out_of_order/banner_without_toc.
"""
from __future__ import annotations

from typing import Sequence

UNRESOLVED_FLAG_KINDS = (
    "banner_out_of_order", "banner_without_toc", "spine_out_of_order")


def g1_check(manifest, min_confirmed_ratio: float = 0.95):
    problems: list[str] = []
    total = len(manifest.pages)
    if total != manifest.n_pages:
        problems.append(
            f"{manifest.book_id}: {total} page record cho {manifest.n_pages} trang")
    missing = [p["pdf_index"] for p in manifest.pages
               if p.get("printed_page") is None]
    if missing:
        problems.append(f"{manifest.book_id}: thiếu printed_page ở {missing[:10]}")
    confirmed = sum(1 for p in manifest.pages if p["source"] == "ocr_confirmed")
    ratio = confirmed / total if total else 0.0
    if ratio < min_confirmed_ratio:
        problems.append(
            f"{manifest.book_id}: ocr_confirmed {confirmed}/{total} "
            f"({ratio:.1%}) < {min_confirmed_ratio:.0%}")
    unresolved = [f for f in manifest.flags if f["kind"] in UNRESOLVED_FLAG_KINDS]
    for flag in unresolved:
        problems.append(f"{manifest.book_id}: {flag['kind']} — {flag['detail']}")
    return (not problems), problems


def g1_report(manifests: Sequence) -> str:
    lines = ["=== G1: định danh trang ==="]
    for manifest in manifests:
        total = len(manifest.pages)
        confirmed = sum(1 for p in manifest.pages if p["source"] == "ocr_confirmed")
        ratio = (confirmed / total) if total else 0.0
        ok, problems = g1_check(manifest)
        lines.append(
            f"{manifest.book_id}: {total} trang | offset {manifest.page_offset} "
            f"(phiếu {manifest.offset_votes[0]}/{manifest.offset_votes[1]}) | "
            f"ocr_confirmed {confirmed}/{total} ({ratio:.1%}) | "
            f"Bài {len(manifest.bai)} | flag {len(manifest.flags)} | "
            f"{'PASS' if ok else 'FAIL'}")
        lines.extend(f"    - {p}" for p in problems)
    return "\n".join(lines)
