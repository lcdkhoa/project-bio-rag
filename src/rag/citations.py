"""Deterministic citations built from retrieved-chunk metadata.

Citations are generated from the metadata of chunks that actually fed the
answer — never emitted by the LLM — so page numbers cannot be hallucinated
(the source is a lookup tool for students). Sidebar / info-box chunks carry a
section label ("mục ...") derived from the box's own first line.
"""
import re
from typing import List, Optional

from langchain_core.documents import Document

from ..etl.image_processor import get_pdf_variant
from .query_intent import strip_accents

_PUBLISHER = {"cd": "CD", "ctst": "CTST", "kntt": "KNTT"}

# (accent-free keyword, display label). "cau hoi" also triggers on a "?" line.
_SECTION_KEYWORDS = [
    ("em co biet", "Em có biết"),
    ("cau hoi", "Câu hỏi"),
    ("hoat dong", "Hoạt động"),
    ("luyen tap", "Luyện tập"),
    ("van dung", "Vận dụng"),
    ("tim hieu them", "Tìm hiểu thêm"),
]
_GENERIC_SECTION = {
    "sidebar": "mục bên lề",
    "info_box": "khung thông tin",
    "caption": "chú thích hình",
}


def format_book_name(source: str) -> str:
    stem = re.sub(r"\.pdf$", "", str(source or ""), flags=re.IGNORECASE).strip()
    if not stem:
        return "Sách giáo khoa"
    variant = get_pdf_variant(str(source or ""))
    label = _PUBLISHER.get(variant)
    if label:
        pat = re.compile(rf"[\s_\-]*{variant}\s*$", re.IGNORECASE)
        if pat.search(stem):
            stem = pat.sub("", stem).strip()
            return f"{stem} ({label})"
    return stem


def _fold(text: str) -> str:
    """Bare ASCII-ish lowercase form for accent-free keyword matching.

    ``strip_accents`` only strips NFD-decomposable combining marks. Vietnamese
    "đ"/"Đ" (U+0111/U+0110) are distinct base letters — not a base + combining
    accent — so NFD does not decompose them and ``strip_accents`` alone leaves
    them untouched (e.g. "được" -> "đuoc", not "duoc"). Fold them explicitly
    before stripping the remaining accents.
    """
    folded = str(text or "").replace("đ", "d").replace("Đ", "D")
    return strip_accents(folded).lower()


def _section_label(doc: Document) -> Optional[str]:
    metadata = doc.metadata or {}
    region_type = str(metadata.get("region_type") or "body")
    if region_type == "body":
        return None
    content = doc.page_content or ""
    first_line = content.strip().splitlines()[0] if content.strip() else ""
    bare = _fold(first_line)
    for keyword, label in _SECTION_KEYWORDS:
        if keyword in bare or (keyword == "cau hoi" and "?" in first_line):
            return label
    return _GENERIC_SECTION.get(region_type)


def _display(book: str, page, section: Optional[str]) -> str:
    base = f"{book}, tr. {page}"
    return f'{base} — mục "{section}"' if section else base


def _page_sort_key(page):
    try:
        return (0, int(page))
    except (TypeError, ValueError):
        return (1, 0)      # unknown pages ("?") sort last


def build_citations(docs: List[Document]) -> List[dict]:
    seen = set()
    out = []
    for doc in docs or []:
        metadata = getattr(doc, "metadata", {}) or {}
        book = format_book_name(metadata.get("source"))
        page = metadata.get("page", metadata.get("page_number", "?"))
        section = _section_label(doc)
        key = (book, str(page), section)
        if key in seen:
            continue
        seen.add(key)
        out.append({"book": book, "page": page, "section": section,
                    "display": _display(book, page, section)})
    out.sort(key=lambda c: (c["book"], _page_sort_key(c["page"])))
    return out


def format_citations_block(citations: List[dict]) -> str:
    if not citations:
        return ""
    lines = "\n".join(f"- {c['display']}" for c in citations)
    return f"📚 Nguồn:\n{lines}"


def is_fallback_answer(answer: str) -> bool:
    bare = _fold(answer)
    return "khong duoc de cap" in bare
