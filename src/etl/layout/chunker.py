"""Turn TextUnits into indexed Documents: body split, boxes atomic."""
from langchain_core.documents import Document
from .regions import TextUnit, RegionType
from ..text_splitter import TextSplitter
from ...config import CHUNK_SIZE, CHUNK_OVERLAP

_splitter = TextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

def _meta(source, page, variant, region_type, idx):
    return {"source": source, "page": page, "variant": variant,
            "region_type": region_type, "chunk_index": idx}

def chunk_units(units, source: str, page: int, variant: str):
    docs, idx = [], 0
    body_text = "\n".join(u.text for u in units if u.region_type == RegionType.BODY).strip()
    if body_text:
        base = Document(page_content=body_text)
        for piece in _splitter.split([base]):
            docs.append(Document(page_content=piece.page_content,
                                 metadata=_meta(source, page, variant, "body", idx)))
            idx += 1
    for u in units:
        if u.region_type == RegionType.BODY:
            continue
        docs.append(Document(page_content=u.text.strip(),
                             metadata=_meta(source, page, variant, u.region_type.value, idx)))
        idx += 1
    return docs
