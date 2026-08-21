"""Deterministic citations built from retrieved-chunk metadata.

Citations are generated from the metadata of chunks that actually fed the
answer — never emitted by the LLM — so page numbers cannot be hallucinated
(the source is a lookup tool for students). Sidebar / info-box chunks carry a
section label ("mục ...") derived from the box's own first line.
"""
import re
from typing import List, Optional

from langchain_core.documents import Document

from .query_intent import strip_accents

# Nhãn sách cho NGƯỜI ĐỌC. Trích dẫn hiện ra trước mắt học sinh và giáo viên, nên
# "SGK_KHTN_6 (KNTT)" — tên thư mục lẫn viết tắt — là không đọc được. Bảng dưới
# đây chỉ dịch phần viết tắt; không suy diễn gì thêm.
_PUBLISHER_FULL = {"KNTT": "Kết nối tri thức"}
# `SGK_KHTN_6_KNTT` / `SGK KHTN 6 KNTT.pdf` -> lớp 6, nhà xuất bản KNTT.
_BOOK_ID = re.compile(
    r"^SGK[\s_]+KHTN[\s_]+(\d{1,2})[\s_]+([A-Za-z]+)$", re.IGNORECASE)

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
    """Tên sách để HIỂN THỊ trong trích dẫn.

    `SGK_KHTN_6_KNTT` -> `Khoa học tự nhiên 6 (Kết nối tri thức)`.

    Tên nào KHÔNG khớp khuôn thì trả về nguyên văn (đã bỏ `.pdf`) — không đoán,
    vì một nhãn sai trong trích dẫn là chỉ học sinh tới sai quyển sách. Bản cũ
    dựa vào `get_pdf_variant`, hàm này nay là hằng số nên nó sẽ dán "(KNTT)" lên
    mọi thứ; ở đây nhà xuất bản đọc từ CHÍNH tên quyển sách.
    """
    stem = re.sub(r"\.pdf$", "", str(source or ""), flags=re.IGNORECASE).strip()
    if not stem:
        return "Sách giáo khoa"

    match = _BOOK_ID.match(stem)
    if not match:
        return stem
    grade, abbrev = match.group(1), match.group(2).upper()
    publisher = _PUBLISHER_FULL.get(abbrev)
    if not publisher:
        return stem
    return f"Khoa học tự nhiên {grade} ({publisher})"


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
