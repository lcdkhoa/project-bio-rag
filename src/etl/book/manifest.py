"""BookManifest — nguồn sự thật duy nhất về trang & Bài của một quyển.

Build một lần cho mỗi quyển, lưu JSON để **người đọc được và review được**. Ba
adapter OCR được truyền vào (dependency injection) nên toàn bộ luật đúng/sai
test được mà không cần OCR, và một adapter đổi (ví dụ đổi engine) không làm hỏng
logic.

Nguồn là `PageSource` (thư mục PNG một file/trang; PDF chỉ còn cho đường upload
legacy) — xem `src/etl/page_source.py`. Ba điểm phải nhớ:

* `page_index` = **số trong tên file**, không phải thứ tự enumerate. Dãy có thể
  có LỖ (sách 9 từng thiếu 19 trang) -> `flags` ghi lỗ ra, không lấp im lặng.
* `printed_page` suy từ offset đo được (`page_index + offset`; đo được là −1 trên
  cả 4 quyển) — không hardcode, không `index + 1`.
* `source_hash` là hash của (số trang, hash từng trang) — để biết manifest có
  còn khớp nguồn hay không. **Khoá checkpoint là hash TỪNG TRANG**, không phải
  cái này (xem `processing_status`).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable

from .bai_spine import banner_agreement, build_bai_spine
from .page_map import build_page_map, fit_offset, missing_page_indices
from .toc import TocResult
from ..page_source import source_hash
from ...config import (MANIFEST_DIR, PROGRESS_LOG_EVERY_PAGES,
                       PROGRESS_LOG_EVERY_SECONDS)
from ...utils.progress import ProgressLogger

logger = logging.getLogger(__name__)

MANIFEST_VERSION = 3

# Trang in 0 và 1 = bìa trước + trang tên sách. Đã xem bằng mắt trên sách 6:
# không in số trang (nên `model_inferred` ở đó là ĐÚNG, không phải lỗi OCR) và
# không có nội dung bài học. Gắn role để bước chunk skip — **không xoá file**
# (CẤM #4: reversible).
COVER_PRINTED_PAGES = (0, 1)

_GRADE = re.compile(r"(?:lop|khtn)[\s_-]*(\d)", re.IGNORECASE)


@dataclass
class BookManifest:
    book_id: str
    source_name: str          # tên thư mục PNG (hoặc tên file PDF legacy)
    source_hash: str
    n_pages: int              # SỐ LƯỢNG trang có thật, không phải max page_index
    page_offset: int
    offset_votes: list
    pages: list
    bai: list
    banner_votes: list        # [số Bài được huy hiệu xác nhận, tổng số Bài]
    chuong: list
    flags: list
    manifest_version: int = MANIFEST_VERSION


# Nhà xuất bản đọc TỪ TÊN QUYỂN. Trước 2026-08-23 hàm dưới nối cứng `-KNTT` —
# tàn dư của thời một nhà xuất bản (D-50), thứ mà D-64 đã đảo chiều. Hậu quả đã
# xảy ra thật trong lượt dựng manifest 12 quyển: `SGK_KHTN_6_CTST` ra `book_id`
# `KHTN6-KNTT` nên nó **ghi đè manifest của 6_CD**, và ba nhà xuất bản cùng lớp
# dùng chung một file. Đúng loại lỗi nguyên tắc 1 cấm: nhãn sai đưa học sinh sang
# sai quyển sách (D-71).
_PUBLISHERS = ("KNTT", "CTST", "CD")


MIN_OFFSET_RATIO = 0.8


def _fingerprint_offset(book: str):
    """Offset đã ĐO ở M0 cho quyển này, hoặc None nếu chưa đo / đo hỏng."""
    from .toc import load_fingerprint          # tránh import vòng
    from ...config import FINGERPRINT_DIR
    path = FINGERPRINT_DIR / f"{book}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return None
    block = data.get("page_number") or {}
    offset = block.get("offset")
    if offset is None:
        return None
    return {"offset": int(offset),
            "hit_rate": float(block.get("hit_rate") or 0.0),
            "margin": int(block.get("margin_over_runner_up") or 0)}


def book_id_from_source_name(source_name: str) -> str:
    """"SGK_KHTN_6_CTST" -> "KHTN6-CTST". Thiếu lớp HOẶC thiếu NXB -> giữ stem.

    Giữ nguyên stem khi không nhận ra là **cố ý**: một cái tên lạ phải đi tiếp
    dưới chính tên của nó, chứ không được gán cho nhà xuất bản nào (thà id xấu
    còn hơn id của quyển khác).
    """
    stem = Path(source_name).stem
    normalised = stem.replace(" ", "-")
    grade = _GRADE.search(normalised)
    if not grade:
        return stem
    parts = {p.upper() for p in re.split(r"[^A-Za-z0-9]+", normalised)}
    publisher = next((p for p in _PUBLISHERS if p in parts), None)
    return f"KHTN{grade.group(1)}-{publisher}" if publisher else stem


def build_manifest(source, *,
                   read_candidates: Callable,
                   read_toc: Callable,
                   detect_banner: Callable) -> BookManifest:
    page_numbers = source.page_numbers()
    if not page_numbers:
        raise ValueError(f"{source.name}: nguồn không có trang nào")

    # MỤC LỤC đọc TRƯỚC: nó cho biết trang nào là MỤC LỤC, và những trang đó
    # phải được loại khỏi vòng dò banner. Trang MỤC LỤC nhiều màu và đầy chữ
    # "Bài N" nên detector từng khớp và sinh ra một Bài giả ở ngay đầu quyển
    # (đo được: "Bài 20 ở trang 6" cho sách 6). Trước đây dải trang này là hằng
    # số `TOC_PAGE_NUMBERS = (5, 6)`; đo lại thì sách 6 dùng BA trang (5–7) nên
    # hằng số đó vừa chặn sai vừa **làm mất 16 Bài cuối** — nay tự phát hiện.
    toc: TocResult = read_toc(source)
    toc_pages = set(toc.page_indices)

    reads: dict[int, list] = {}
    banners: dict[int, frozenset] = {}
    # Vòng này đọc số trang (crop góc 1x + 3x) và dò banner Bài trên TỪNG trang
    # của cả quyển — chậm và trước đây hoàn toàn im lặng (D-53).
    with ProgressLogger(logger, f"[{source.name}] manifest",
                        len(page_numbers),
                        every_items=PROGRESS_LOG_EVERY_PAGES,
                        every_seconds=PROGRESS_LOG_EVERY_SECONDS,
                        unit="trang") as progress:
        for page_index in page_numbers:
            image = source.load(page_index)
            reads[page_index] = list(read_candidates(image))
            if page_index in toc_pages:
                progress.advance(trang_muc_luc=1)
                continue
            candidates = detect_banner(image)
            if candidates:
                banners[page_index] = frozenset(int(c) for c in candidates)
            progress.advance(so_trang_doc_duoc=1 if reads[page_index] else 0,
                             banner=1 if candidates else 0)

    fit = fit_offset(reads)
    offset_flags: list = []
    min_ratio = MIN_OFFSET_RATIO
    if fit.ratio < MIN_OFFSET_RATIO:
        # Đồng thuận yếu KHÔNG được phép đoán, nhưng cũng không được phép bỏ qua
        # một phép đo MẠNH HƠN về CÙNG đại lượng đó. Fingerprint M0 đo offset
        # riêng, trên vùng số trang ĐO ĐƯỢC của chính quyển này (`zone_read`), và
        # với 6_CD nó đạt 39/40 phiếu, margin 38 — trong khi đường của manifest
        # chỉ được 66/101 = 65%. Hai nguồn cùng chỉ một offset thì đi tiếp và GẮN
        # CỜ; khác nhau thì RAISE để người xem (nguyên tắc 6).
        measured = _fingerprint_offset(source.name)
        if measured is None:
            offset_flags.append({
                "kind": "offset_weak_consensus_no_fingerprint",
                "detail": f"{source.name}: đồng thuận offset {fit.votes}/"
                          f"{fit.total} ({fit.ratio:.0%}) và KHÔNG có fingerprint "
                          f"để đối chứng — chạy `python -m src.etl.book."
                          f"fingerprint --book {source.name}`"})
        elif measured["offset"] == fit.offset:
            min_ratio = 0.0
            offset_flags.append({
                "kind": "offset_weak_consensus_confirmed_by_fingerprint",
                "detail": f"{source.name}: đồng thuận yếu ở đường manifest "
                          f"({fit.votes}/{fit.total} = {fit.ratio:.0%}) nhưng "
                          f"fingerprint M0 đo CÙNG offset {measured['offset']} với "
                          f"hit {measured['hit_rate']:.0%} và margin "
                          f"{measured['margin']} -> đi tiếp bằng offset đã đo"})
        else:
            offset_flags.append({
                "kind": "offset_conflict_with_fingerprint",
                "detail": f"{source.name}: đường manifest ra offset {fit.offset} "
                          f"({fit.ratio:.0%}) còn fingerprint đo được "
                          f"{measured['offset']} (hit {measured['hit_rate']:.0%}) "
                          f"-> KHÔNG chọn bừa"})
    page_records = build_page_map(page_numbers, reads, fit, min_ratio=min_ratio)

    # MỤC LỤC ghi SỐ TRANG IN; spine và banner làm việc trên page_index. Đổi hệ
    # toạ độ đúng một lần, ngay tại biên — dựa vào chuyện hai hệ "gần trùng"
    # chính là loại lỗi lệch hệ chỉ số mà spec §2 cấm.
    toc_entries = [replace(entry, start_page=entry.start_page - fit.offset)
                   for entry in toc.entries]
    toc_chuongs = toc.chuongs
    spine, spine_flags = build_bai_spine(toc_entries, banners, page_numbers[-1])

    flags = list(toc.flags) + offset_flags
    flags += [{"kind": "page_number_not_read",
               "detail": f"trang {record.page_index}: không đọc được số trang, "
                         f"suy ra {record.printed_page} từ offset {fit.offset}"}
              for record in page_records if record.source == "model_inferred"]
    flags += [{"kind": flag.kind, "detail": flag.detail} for flag in spine_flags]

    gaps = missing_page_indices(page_numbers)
    if gaps:
        # KHÔNG lấp: thiếu trang nguồn là thiếu dữ liệu, phải tải bù rồi dựng
        # lại manifest. Ghi ra để người xử lý, không bịa record.
        flags.append({
            "kind": "missing_source_pages",
            "detail": f"{source.name}: thiếu file trang {gaps[:20]}"
                      f"{' …' if len(gaps) > 20 else ''} "
                      f"({len(gaps)} trang) giữa {page_numbers[0]}"
                      f"–{page_numbers[-1]}"})

    # Spine đầy đủ thì số Bài phải là 1..k liền mạch. Thiếu -> spine là giả
    # thuyết vá lỗ, KHÔNG được dùng như sự thật (vì vậy `bai_so` không đi vào
    # metadata chunk — xem `layout/loader.py`). Flag này KHÔNG chặn G1: nó mô tả
    # một điểm yếu đã biết của M0, không phải hai nguồn mâu thuẫn.
    bai_numbers = sorted(record.bai_so for record in spine)
    if bai_numbers and bai_numbers != list(range(1, len(bai_numbers) + 1)):
        missing_bai = [n for n in range(1, max(bai_numbers) + 1)
                       if n not in set(bai_numbers)]
        flags.append({
            "kind": "bai_numbers_not_contiguous",
            "detail": f"{len(bai_numbers)} Bài dựng được, cao nhất "
                      f"{max(bai_numbers)}; thiếu {missing_bai[:20]}"
                      f"{' …' if len(missing_bai) > 20 else ''}"})

    book_id = book_id_from_source_name(source.name)
    if not spine:
        # Không banner nào, không TOC entry nào -> không nguồn nào nói gì, khác
        # hẳn "một nguồn im lặng" (đã có flag riêng, không chặn). Sách coi như
        # chưa định danh được Bài nào, phải chặn G1.
        flags.append({
            "kind": "no_bai_detected",
            "detail": f"{book_id}: không phát hiện banner Bài nào và MỤC LỤC "
                      f"không có entry nào -> 0 Bài được dựng cho sách này"})

    present = set(page_numbers)
    bai_of_page: dict[int, int] = {}
    for record in spine:
        for page_index in range(record.start, record.end + 1):
            if page_index in present:      # không gán Bài cho trang không tồn tại
                bai_of_page[page_index] = record.bai_so
    first_content = min((r.start for r in spine), default=page_numbers[-1] + 1)
    # Bài cuối luôn được `build_bai_spine` kéo `end` tới trang cuối, nên không có
    # tín hiệu nào cho back matter -> M0 không đoán (không có heuristic "N trang
    # cuối"); bìa sau/bảng thuật ngữ hiện vẫn mang role "content".

    pages = []
    for record in page_records:
        if record.printed_page in COVER_PRINTED_PAGES:
            role = "cover"
        elif record.page_index < first_content:
            role = "front_matter"
        else:
            role = "content"
        pages.append({"page_index": record.page_index,
                      "printed_page": record.printed_page,
                      "source": record.source, "side": record.side,
                      "conf": record.conf,
                      "bai_so": bai_of_page.get(record.page_index),
                      "role": role})

    return BookManifest(
        book_id=book_id,
        source_name=source.name,
        source_hash=source_hash(source),
        n_pages=len(page_numbers),
        page_offset=fit.offset,
        offset_votes=[fit.votes, fit.total],
        pages=pages,
        banner_votes=list(banner_agreement(spine)),
        bai=[{"bai_so": r.bai_so, "title": r.title, "start": r.start,
              "end": r.end, "source": r.source} for r in spine],
        chuong=[{"label": c.label, "title": c.title, "after_bai": c.after_bai}
                for c in toc_chuongs],
        flags=flags,
    )


def save_manifest(manifest: BookManifest,
                  directory: Path = MANIFEST_DIR) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{manifest.book_id}.json"
    path.write_text(json.dumps(asdict(manifest), ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return path


def load_manifest(path: Path) -> BookManifest:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    version = data.get("manifest_version")
    if version != MANIFEST_VERSION:
        # Manifest cũ dùng `pdf_index` (0-based) — đọc nó ở đây sẽ lệch đúng 1
        # trang trên mọi citation. Fail loudly.
        raise ValueError(
            f"{path}: manifest_version {version} != {MANIFEST_VERSION} — "
            f"dựng lại bằng `python main.py --build-manifests`")
    return BookManifest(**data)


def printed_page_lookup(manifest: BookManifest) -> dict:
    return {p["page_index"]: p["printed_page"] for p in manifest.pages}
