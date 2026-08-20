"""BookManifest — nguồn sự thật duy nhất về trang & Bài của một quyển.

Build một lần cho mỗi PDF, lưu JSON để **người đọc được và review được**. Ba
adapter OCR được truyền vào (dependency injection) nên toàn bộ luật đúng/sai
test được mà không cần OCR, và một adapter đổi (ví dụ đổi engine ở M1) không
làm hỏng logic.

`pdf_hash` dùng đúng `compute_file_hash` (MD5) của `processing_status` để manifest
và checkpoint chia sẻ **một** khoá. Không import `ProcessingStatus` ở đây —
`__init__` của nó load HuggingFaceEmbeddings, quá nặng cho một job manifest.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable

import fitz
import numpy as np

from .bai_spine import BannerHit, build_bai_spine
from .page_map import fit_offset, build_page_map
from .toc import parse_toc_lines
from ..processing_status import compute_file_hash
from ...config import PERSIST_DIR

MANIFEST_VERSION = 1
MANIFEST_DIR = PERSIST_DIR / "manifests"

_GRADE = re.compile(r"lop[\s_-]*(\d)", re.IGNORECASE)


@dataclass
class BookManifest:
    book_id: str
    pdf_name: str
    pdf_hash: str
    n_pages: int
    page_offset: int
    offset_votes: list
    pages: list
    bai: list
    chuong: list
    flags: list
    manifest_version: int = MANIFEST_VERSION


def book_id_from_filename(pdf_name: str) -> str:
    stem = Path(pdf_name).stem
    grade = _GRADE.search(stem.replace(" ", "-"))
    return f"KHTN{grade.group(1)}-KNTT" if grade else stem


def _render(doc: fitz.Document, index: int, dpi: int) -> np.ndarray:
    """Trang PDF -> mảng BGR uint8 (kênh alpha/grayscale được chuẩn hoá)."""
    pix = doc.load_page(index).get_pixmap(dpi=dpi)
    arr = np.frombuffer(pix.samples, np.uint8).reshape(
        pix.height, pix.width, pix.n)
    if pix.n == 1:
        return np.repeat(arr, 3, axis=2).copy()
    return arr[:, :, :3][:, :, ::-1].copy()


def build_manifest(pdf_path: str, *,
                   read_candidates: Callable,
                   read_toc: Callable,
                   detect_banner: Callable,
                   dpi: int = 300) -> BookManifest:
    doc = fitz.open(pdf_path)
    try:
        n_pages = doc.page_count
        reads: dict[int, list] = {}
        banners: list[BannerHit] = []
        for index in range(n_pages):
            image = _render(doc, index, dpi)
            reads[index] = list(read_candidates(image))
            bai_so = detect_banner(image)
            if bai_so is not None:
                banners.append(BannerHit(pdf_index=index, bai_so=int(bai_so)))
    finally:
        doc.close()

    fit = fit_offset(reads)
    page_records = build_page_map(n_pages, reads, fit)

    toc_printed, toc_chuongs = parse_toc_lines(read_toc(pdf_path))
    # MỤC LỤC ghi SỐ TRANG IN; spine và banner làm việc trên pdf_index. Đổi hệ
    # toạ độ đúng một lần, ngay tại biên. Với offset 0 hai hệ trùng nhau — nhưng
    # dựa vào sự trùng đó là đúng loại lỗi lệch hệ chỉ số mà spec §2 cấm.
    toc_entries = [replace(entry, start_page=entry.start_page - fit.offset)
                   for entry in toc_printed]
    spine, spine_flags = build_bai_spine(toc_entries, banners, n_pages)

    flags = [{"kind": "page_number_not_read",
              "detail": f"trang {record.pdf_index}: không đọc được số trang, "
                        f"suy ra {record.printed_page} từ offset {fit.offset}"}
             for record in page_records if record.source == "model_inferred"]
    flags += [{"kind": flag.kind, "detail": flag.detail} for flag in spine_flags]

    bai_of_page: dict[int, int] = {}
    for record in spine:
        for index in range(record.start, record.end + 1):
            bai_of_page[index] = record.bai_so
    first_content = min((r.start for r in spine), default=n_pages)
    last_content = max((r.end for r in spine), default=-1)

    pages = []
    for record in page_records:
        index = record.pdf_index
        if index < first_content:
            role = "front_matter"
        elif index > last_content:
            role = "back_matter"
        else:
            role = "content"
        pages.append({"pdf_index": index, "printed_page": record.printed_page,
                      "source": record.source, "side": record.side,
                      "conf": record.conf, "bai_so": bai_of_page.get(index),
                      "role": role})

    return BookManifest(
        book_id=book_id_from_filename(Path(pdf_path).name),
        pdf_name=Path(pdf_path).name,
        pdf_hash=compute_file_hash(pdf_path),
        n_pages=n_pages,
        page_offset=fit.offset,
        offset_votes=[fit.votes, fit.total],
        pages=pages,
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
    return BookManifest(**json.loads(Path(path).read_text(encoding="utf-8")))


def printed_page_lookup(manifest: BookManifest) -> dict:
    return {p["pdf_index"]: p["printed_page"] for p in manifest.pages}
