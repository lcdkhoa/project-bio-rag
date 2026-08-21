"""Turn TextUnits into indexed Documents: body split, boxes atomic.

Metadata mang cả `page` (SỐ TRANG IN, đi vào citation) và `page_index` (số trang
NGUỒN = số trong tên file). Hai hệ toạ độ khác nhau và lệch nhau đúng 1 trên
corpus này, nên gộp chúng lại là mời một off-by-one im lặng: citation phải dùng
`page`, còn truy về file gốc phải dùng `page_index`.

`needs_review` / `review_tokens` chỉ là CỜ cho người xem (`diacritic.py` không
sửa ký tự nào). Chroma không nhận metadata dạng list nên token được ghép thành
một string phân tách bằng dấu phẩy.
"""
from langchain_core.documents import Document
from .regions import TextUnit, RegionType
from ..text_splitter import TextSplitter
from ...config import CHUNK_SIZE, CHUNK_OVERLAP

_splitter = TextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

# Hộp (sidebar/info-box) được giữ NGUYÊN KHỐI vì một câu hỏi bị cắt giữa là câu
# hỏi vô nghĩa. Nhưng đo trên 25 trang thật: 22% hộp dài hơn CHUNK_SIZE, 10% dài
# hơn 600 và có hộp 1607 ký tự ("Em có biết?" nhiều đoạn). Một chunk 1607 ký tự
# trong một index chunk 400 thì embedding loãng, retrieval kém. Ngưỡng 1,5 ×
# CHUNK_SIZE: câu hỏi/hoạt động thường lệ vẫn nguyên khối, chỉ những hộp dài
# thật sự mới bị cắt — và cắt thì vẫn giữ nhãn `region_type` nên citation không
# mất nhãn "khung thông tin"/"mục bên lề".
BOX_ATOMIC_MAX_CHARS = int(CHUNK_SIZE * 1.5)

def _meta(source, page, variant, region_type, idx, page_index, bai_so, flags):
    meta = {"source": source, "page": page, "variant": variant,
            "region_type": region_type, "chunk_index": idx,
            "needs_review": bool(flags),
            "review_tokens": ",".join(flags)}
    if page_index is not None:
        meta["page_index"] = page_index
    if bai_so is not None:
        meta["bai_so"] = bai_so
    return meta

def chunk_units(units, source: str, page: int, variant: str,
                page_index: int = None, bai_so: int = None):
    docs, idx = [], 0
    body_units = [u for u in units if u.region_type == RegionType.BODY]
    body_text = "\n".join(u.text for u in body_units).strip()
    if body_text:
        # Cờ review của cả phần thân bài áp cho mọi chunk thân bài: sau khi
        # splitter cắt, không còn biết token đáng ngờ rơi vào chunk nào — thà
        # gắn rộng cho người xem hơn là mất dấu.
        body_flags = _dedupe(f for u in body_units for f in u.review_flags)
        base = Document(page_content=body_text)
        for piece in _splitter.split([base]):
            docs.append(Document(page_content=piece.page_content,
                                 metadata=_meta(source, page, variant, "body",
                                                idx, page_index, bai_so,
                                                body_flags)))
            idx += 1
    for u in units:
        if u.region_type == RegionType.BODY:
            continue
        text = u.text.strip()
        flags = _dedupe(u.review_flags)
        pieces = [text]
        if len(text) > BOX_ATOMIC_MAX_CHARS:
            pieces = [p.page_content for p in
                      _splitter.split([Document(page_content=text)])]
        for piece in pieces:
            docs.append(Document(page_content=piece,
                                 metadata=_meta(source, page, variant,
                                                u.region_type.value, idx,
                                                page_index, bai_so, flags)))
            idx += 1
    return docs

def _dedupe(tokens):
    out = []
    for token in tokens:
        if token not in out:
            out.append(token)
    return out
