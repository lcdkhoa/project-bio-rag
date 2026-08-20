"""Báo cáo cổng G1: định danh trang có đủ tin để đi tiếp hay không.

Ngưỡng (spec §4): 100% trang có `printed_page`, >= 95% là `ocr_confirmed`, và
**0** conflict spine chưa giải. `page_number_not_read` KHÔNG phải conflict — nó
đã được mô hình offset xử lý và ghi provenance; chỉ tỉ lệ confirmed mới chặn.

Nguyên tắc chặn (review round 1): G1 chỉ chặn khi **hai nguồn mâu thuẫn nhau**.
Một nguồn im lặng (không có tin) trong khi nguồn kia vẫn cho đủ thông tin thì
KHÔNG phải conflict — `toc_without_banner` (MỤC LỤC có Bài, không thấy banner —
dùng trang TOC) và `banner_without_toc` (banner có Bài, MỤC LỤC không liệt kê —
banner vẫn cho trang bắt đầu đáng tin, chỉ thiếu tiêu đề) là cùng một tình huống
soi gương: cả hai chỉ ghi lại một nguồn bị thiếu, không nguồn nào bị sai. MỤC
LỤC bỏ sót Bài là lỗi đã đo được trên corpus thật (không phải giả thuyết), nên
CHẶN trên `banner_without_toc` sẽ làm rớt sách thật vì một điều kiện đã biết
trước là bình thường — vì vậy nó KHÔNG ở trong UNRESOLVED_FLAG_KINDS. Ngược lại
`banner_out_of_order` (banner tự mâu thuẫn với chính banner khác), `spine_out_of_order`
(bổ sung sau review Task 5: thứ tự Bài mâu thuẫn với thứ tự trang trong spine đã
dựng), và `no_bai_detected` (bổ sung sau review round 1: cả banner lẫn TOC đều
không cho Bài nào — không phải "một nguồn im lặng" mà là "không nguồn nào nói
gì", sách coi như chưa định danh được) đều LÀ conflict thật, nên ở trong
UNRESOLVED_FLAG_KINDS.
"""
from __future__ import annotations

from typing import Sequence

UNRESOLVED_FLAG_KINDS = (
    "banner_out_of_order", "spine_out_of_order", "no_bai_detected")


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
