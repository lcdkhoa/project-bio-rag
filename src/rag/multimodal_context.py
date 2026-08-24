# -*- coding: utf-8 -*-
"""Ngữ cảnh ĐA PHƯƠNG THỨC cho prompt: text chunk + nhãn/chú thích hình.

Đây là trục thứ hai của Mục tiêu 4 trong đề cương — *"Hệ thống RAG đa phương
thức so với hệ thống RAG chỉ sử dụng văn bản"*. Trước module này,
`src/app/api.py` dựng ngữ cảnh **chỉ từ `text_docs`** và `image_docs` chỉ chảy ra
gallery, nên hai cấu hình chênh nhau **0 theo cấu trúc**: bảng ablation sẽ in ra
hai hàng giống hệt và người đọc tưởng đó là kết luận "đa phương thức không giúp
gì".

## Ba luật, và vì sao

1. **Chỉ chữ đọc lại từ pixel.** `figure_label` (pill/OCR — D-45),
   `figure_caption` (caption neo bằng OCR), `crop_text` (OCR trong crop). KHÔNG
   đọc `visual_caption_vi` / `final_caption_vi` / `caption` / `caption_vi`: ba
   trường sau do model SINH ra, và Vintern-1B đã bị loại vì **bịa 4/12 crop**
   (D-47). Với `IMAGE_CAPTION_ENABLED=false` thì `caption` hiện chỉ là
   `figure_caption or context_text[:240]`, nhưng dựa vào điều đó là dựa vào một
   nhánh cấu hình có thể đổi — nên không đọc là an toàn theo *cấu trúc*.
2. **Hình không có một chữ deterministic nào thì BỎ.** Một khối `[HÌNH]` trống
   chỉ thêm nhiễu vào ngữ cảnh — đúng điều đề cương cảnh báo ở phần định tuyến.
3. **Kho ảnh rỗng phải cho ra ngữ cảnh Y HỆT text-only, tới từng byte.** Nếu
   không, bảng ablation đang đo thêm một nhánh ẩn chứ không đo phía ảnh.
"""

from __future__ import annotations

from typing import Iterable, List, Sequence

from src.config import (
    MULTIMODAL_CONTEXT_ENABLED,
    MULTIMODAL_CROP_TEXT_MAX_CHARS,
    MULTIMODAL_MAX_FIGURES,
)
from src.rag.citations import format_book_name

# Trường được phép đọc, theo đúng thứ tự xuất hiện trong khối. Danh sách này là
# hợp đồng của luật 1 — thêm một trường vào đây phải chứng minh nó deterministic.
_DETERMINISTIC_FIELDS = ("figure_label", "figure_caption", "crop_text")


def _meta(doc) -> dict:
    if isinstance(doc, dict):
        return doc.get("metadata", doc) or {}
    return getattr(doc, "metadata", None) or {}


def _clean(value, limit: int = 0) -> str:
    text = " ".join(str(value or "").split())
    if limit and len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def _selected(image_docs: Iterable,
              max_figures: int = MULTIMODAL_MAX_FIGURES,
              crop_text_max_chars: int = MULTIMODAL_CROP_TEXT_MAX_CHARS,
              ) -> List[tuple]:
    """[(doc, khối chữ)] cho những hình THẬT SỰ vào ngữ cảnh.

    Bảng ablation cần biết hình NÀO vào ngữ cảnh, không phải hình nào được truy
    xuất — hai con số khác nhau, vì hình không có một chữ deterministic nào thì
    bị bỏ (luật 2). Trả về cả doc để chỗ chấm điểm không phải suy lại từ chuỗi.
    """
    blocks: List[tuple] = []
    seen = set()
    for doc in image_docs or []:
        meta = _meta(doc)
        label = _clean(meta.get("figure_label"))
        caption = _clean(meta.get("figure_caption"))
        crop_text = _clean(meta.get("crop_text"), crop_text_max_chars)
        if not (label or caption or crop_text):
            continue  # luật 2

        source = str(meta.get("pdf_filename") or meta.get("source") or "")
        page = meta.get("page_number", meta.get("page"))
        # Khoá trùng: nhãn hình là danh tính thật của một hình (`Hình A.B` = hình
        # B của Bài A). Kênh CLIP và kênh metadata thường trả CÙNG một hình, và
        # in nó hai lần vừa tốn chỗ vừa làm LLM tưởng có hai hình.
        key = (source, str(page), label or caption or crop_text)
        if key in seen:
            continue
        seen.add(key)

        dau = " · ".join(part for part in (
            label,
            format_book_name(source) if source else "",
            f"trang {page}" if page not in (None, "") else "",
        ) if part)
        dong = [f"[HÌNH] {dau}" if dau else "[HÌNH]"]
        if caption:
            dong.append(f"Chú thích: {caption}")
        if crop_text and crop_text != caption:
            dong.append(f"Chữ đọc được trong hình: {crop_text}")
        blocks.append((doc, "\n".join(dong)))
        if len(blocks) >= max_figures:
            break
    return blocks


def figure_blocks(image_docs: Iterable,
                  max_figures: int = MULTIMODAL_MAX_FIGURES,
                  crop_text_max_chars: int = MULTIMODAL_CROP_TEXT_MAX_CHARS,
                  ) -> List[str]:
    """Khối ngữ cảnh cho từng hình, giữ nguyên thứ tự xếp hạng đầu vào."""
    return [block for _, block in _selected(image_docs, max_figures,
                                            crop_text_max_chars)]


def selected_figures(image_docs: Iterable,
                     max_figures: int = MULTIMODAL_MAX_FIGURES,
                     crop_text_max_chars: int = MULTIMODAL_CROP_TEXT_MAX_CHARS,
                     ) -> List:
    """Đúng những doc hình đã vào ngữ cảnh (để chấm điểm ablation)."""
    return [doc for doc, _ in _selected(image_docs, max_figures,
                                        crop_text_max_chars)]


def text_blocks(text_docs: Sequence) -> List[str]:
    out = []
    for doc in text_docs or []:
        content = (doc.get("page_content") if isinstance(doc, dict)
                   else getattr(doc, "page_content", ""))
        if content:
            out.append(str(content))
    return out


def build_context(text_docs: Sequence, image_docs: Sequence,
                  multimodal: bool = MULTIMODAL_CONTEXT_ENABLED,
                  max_figures: int = MULTIMODAL_MAX_FIGURES) -> str:
    """Ngữ cảnh đưa vào prompt. `multimodal=False` -> y nguyên hành vi cũ."""
    parts = text_blocks(text_docs)
    if multimodal:
        blocks = figure_blocks(image_docs, max_figures=max_figures)
        if blocks:
            # Tiêu đề chỉ xuất hiện KHI có khối — nhờ vậy kho ảnh rỗng cho ra
            # đúng chuỗi của text-only (luật 3).
            parts.append("[HÌNH ẢNH TRONG SÁCH LIÊN QUAN ĐẾN CÂU HỎI]\n"
                         + "\n\n".join(blocks))
    return "\n\n".join(parts)
