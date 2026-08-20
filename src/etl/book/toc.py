"""Đọc MỤC LỤC (idx 4–5) — kết quả là GIẢ THUYẾT, không phải sự thật.

Đo trên corpus thật: TOC OCR thiếu bài, sai số trang ("Bài 24 | tr. 90" trong khi
Bài 23 đã ở tr. 95), sai số bài ("Bài 3" thay vì 31). Vì vậy module này **không**
tự sửa gì: nó trả về đúng thứ nó đọc được, còn việc đối chiếu/sửa/flag là của
`bai_spine.py` (spec §1.3).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Sequence

import fitz
import numpy as np
import pytesseract

from ...config import TESSERACT_CMD

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

TOC_PAGE_INDICES = (4, 5)
MAX_PRINTED_PAGE = 400          # không quyển nào tới 400 trang -> số lớn hơn là rác OCR

_BAI = re.compile(r"^B[àa]i\s+(\d{1,2})\s*[.:]?\s+(.+?)\s+(\d{1,3})$")
_CHUONG = re.compile(r"^CH[ƯU][ƠO]NG\s+([IVX]+)\s*[-–—.]?\s*(.*)$", re.IGNORECASE)


@dataclass(frozen=True)
class TocEntry:
    bai_so: int
    title: str
    start_page: int


@dataclass(frozen=True)
class TocChuong:
    label: str
    title: str
    after_bai: Optional[int]


def parse_toc_lines(lines: Sequence[str]) -> tuple[list[TocEntry], list[TocChuong]]:
    entries: list[TocEntry] = []
    chuongs: list[TocChuong] = []
    for raw in lines:
        line = " ".join(str(raw or "").split())
        if not line:
            continue
        chuong = _CHUONG.match(line)
        if chuong:
            chuongs.append(TocChuong(
                label=chuong.group(1).upper(),
                title=chuong.group(2).strip(" -–—"),
                after_bai=entries[-1].bai_so if entries else None))
            continue
        bai = _BAI.match(line)
        if not bai:
            continue
        page = int(bai.group(3))
        if page > MAX_PRINTED_PAGE:
            continue
        entries.append(TocEntry(bai_so=int(bai.group(1)),
                                title=bai.group(2).strip(),
                                start_page=page))
    return entries, chuongs


def read_toc_lines(pdf_path: str,
                   indices: Sequence[int] = TOC_PAGE_INDICES,
                   dpi: int = 300) -> list[str]:
    """OCR các trang MỤC LỤC thành danh sách dòng thô (psm 4: text nhiều cột)."""
    doc = fitz.open(pdf_path)
    try:
        out: list[str] = []
        for index in indices:
            if index >= doc.page_count:
                continue
            pix = doc.load_page(index).get_pixmap(dpi=dpi)
            arr = np.frombuffer(pix.samples, np.uint8).reshape(
                pix.height, pix.width, pix.n)[:, :, :3]
            text = pytesseract.image_to_string(arr, lang="vie", config="--psm 4")
            out.extend(line for line in text.splitlines() if line.strip())
        return out
    finally:
        doc.close()
