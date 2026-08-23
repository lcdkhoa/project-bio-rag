"""Báo cáo cổng G1: định danh trang có đủ tin để đi tiếp hay không.

Ngưỡng: 100% trang có `printed_page`, >= 95% trang **có in số** là
`ocr_confirmed`, và **0** conflict spine chưa giải.

Vì sao tỉ lệ tính trên trang CÓ IN SỐ (`role != "cover"`): hai trang đầu mỗi
quyển (trang in 0 = bìa, 1 = trang tên sách) **thật sự không in số trang** — đã
xem bằng mắt. Bắt OCR "xác nhận" một con số không tồn tại là bắt nó bịa; để
chúng trong mẫu số thì cổng đo lẫn hai thứ khác nhau (adapter đọc kém vs trang
không có gì để đọc). Vì vậy `model_inferred` trên trang `cover` là ĐÚNG, còn
trên trang khác là một phép đo cần thấy — nên nó được in ra danh sách, không bị
gộp vào một con số.

Nguyên tắc chặn: G1 chỉ chặn khi **hai nguồn mâu thuẫn nhau**. Một nguồn im lặng
(không có tin) trong khi nguồn kia vẫn cho đủ thông tin thì KHÔNG phải conflict —
`toc_without_banner` (MỤC LỤC có Bài, không thấy banner — dùng trang TOC) và
`banner_without_toc` (banner có Bài, MỤC LỤC không liệt kê — banner vẫn cho trang
bắt đầu đáng tin, chỉ thiếu tiêu đề) là cùng một tình huống soi gương: cả hai chỉ
ghi lại một nguồn bị thiếu, không nguồn nào bị sai. MỤC LỤC bỏ sót Bài là lỗi đã
đo được trên corpus thật (không phải giả thuyết), nên CHẶN trên
`banner_without_toc` sẽ làm rớt sách thật vì một điều kiện đã biết trước là bình
thường — vì vậy nó KHÔNG ở trong UNRESOLVED_FLAG_KINDS. Ngược lại
`banner_out_of_order` (banner tự mâu thuẫn với chính banner khác),
`spine_out_of_order` (thứ tự Bài mâu thuẫn với thứ tự trang trong spine đã dựng),
`no_bai_detected` (cả banner lẫn TOC đều không cho Bài nào) và
`missing_source_pages` (thiếu hẳn file trang trong nguồn — thiếu dữ liệu, phải
tải bù rồi dựng lại, không được index một quyển có lỗ mà im lặng) đều LÀ vấn đề
thật, nên ở trong UNRESOLVED_FLAG_KINDS.
"""
from __future__ import annotations

from typing import Sequence

UNRESOLVED_FLAG_KINDS = (
    "banner_out_of_order", "spine_out_of_order", "no_bai_detected",
    "missing_source_pages")

# `banner_toc_mismatch` KHÔNG chặn: đo được huy hiệu chỉ đọc đúng ~2/3 số trang
# mở Bài và có ca đọc ra hai số mâu thuẫn, nên một lần lệch là *nguồn yếu nói
# sai*, không phải hai nguồn ngang nhau đánh nhau. Nó vẫn được in ra để người
# xem — chỉ là không rớt cổng vì một điều kiện đã biết trước là thường xảy ra.

MAX_LISTED = 10


def _numbered_pages(manifest) -> list:
    """Trang được kỳ vọng có in số trang (bìa thì không)."""
    return [p for p in manifest.pages if p.get("role") != "cover"]


def unconfirmed_numbered_pages(manifest) -> list:
    """`page_index` của các trang CÓ IN SỐ mà OCR không xác nhận được."""
    return [p["page_index"] for p in _numbered_pages(manifest)
            if p["source"] != "ocr_confirmed"]


def confirm_stats(manifest) -> tuple[int, int, float]:
    numbered = _numbered_pages(manifest)
    confirmed = sum(1 for p in numbered if p["source"] == "ocr_confirmed")
    total = len(numbered)
    return confirmed, total, (confirmed / total if total else 0.0)


def g1_check(manifest, min_confirmed_ratio: float = 0.95):
    problems: list[str] = []
    total = len(manifest.pages)
    if total != manifest.n_pages:
        problems.append(
            f"{manifest.book_id}: {total} page record cho {manifest.n_pages} trang")
    missing = [p["page_index"] for p in manifest.pages
               if p.get("printed_page") is None]
    if missing:
        problems.append(f"{manifest.book_id}: thiếu printed_page ở {missing[:MAX_LISTED]}")
    confirmed, numbered, ratio = confirm_stats(manifest)
    if ratio < min_confirmed_ratio:
        problems.append(
            f"{manifest.book_id}: ocr_confirmed {confirmed}/{numbered} "
            f"({ratio:.1%}) < {min_confirmed_ratio:.0%}")
    unresolved = [f for f in manifest.flags if f["kind"] in UNRESOLVED_FLAG_KINDS]
    for flag in unresolved:
        problems.append(f"{manifest.book_id}: {flag['kind']} — {flag['detail']}")
    return (not problems), problems


def spine_gap(manifest) -> str:
    """`" (THIẾU 21 Bài)"` nếu spine không liền mạch `1..max`, ngược lại `""`.

    Vì sao phải in ra ngay cạnh số Bài: G1 chỉ kiểm **định danh trang**, nên một
    quyển CTST đọc được 17/38 Bài vẫn `PASS` nếu `ocr_confirmed` = 100%. Đo được
    trên lượt 12 quyển ngày 2026-08-23: 4 quyển CTST PASS trong khi thiếu 21–33
    Bài. Dòng báo cáo cũ chỉ ghi "Bài 17", và người đọc sẽ hiểu là quyển đó có 17
    Bài — một con số SAI MÀ TRÔNG HỢP LÝ. `bai_numbers_not_contiguous` cố ý KHÔNG
    làm rớt cổng (nó là việc của spine, không phải của định danh trang), nhưng nó
    không được phép vô hình (D-73).
    """
    numbers = sorted(b["bai_so"] for b in manifest.bai) if manifest.bai else []
    if not numbers:
        return " (KHÔNG đọc được Bài nào)"
    missing = [n for n in range(1, numbers[-1] + 1) if n not in set(numbers)]
    return f" (spine THIẾU {len(missing)} Bài trong 1..{numbers[-1]})" if missing else ""


def g1_report(manifests: Sequence) -> str:
    lines = ["=== G1: định danh trang ==="]
    for manifest in manifests:
        confirmed, numbered, ratio = confirm_stats(manifest)
        covers = len(manifest.pages) - numbered
        unconfirmed = unconfirmed_numbered_pages(manifest)
        ok, problems = g1_check(manifest)
        lines.append(
            f"{manifest.book_id}: {len(manifest.pages)} trang "
            f"({covers} bìa không in số) | offset {manifest.page_offset} "
            f"(phiếu {manifest.offset_votes[0]}/{manifest.offset_votes[1]}) | "
            f"ocr_confirmed {confirmed}/{numbered} ({ratio:.1%}) | "
            f"Bài {len(manifest.bai)}{spine_gap(manifest)} "
            f"(huy hiệu xác nhận {manifest.banner_votes[0]}/"
            f"{manifest.banner_votes[1]}) | flag {len(manifest.flags)} | "
            f"{'PASS' if ok else 'FAIL'}")
        if unconfirmed:
            lines.append(
                f"    - trang in số nhưng KHÔNG đọc được: "
                f"{unconfirmed[:MAX_LISTED]}"
                f"{f' … (+{len(unconfirmed) - MAX_LISTED})' if len(unconfirmed) > MAX_LISTED else ''}")
        lines.extend(f"    - {p}" for p in problems)
    return "\n".join(lines)
