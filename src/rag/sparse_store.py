# -*- coding: utf-8 -*-
"""Dựng / nạp chỉ mục thưa từ chính `biology_text`. Không OCR lại gì cả.

Cả module này chỉ có một việc: giữ cho chỉ mục thưa **luôn là ảnh chiếu của
index dày tại một thời điểm xác định**, và **gào lên** khi nó không còn như thế.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import List, Optional, Tuple

from ..config import (
    BM25_TOKENIZER,
    PERSIST_DIR,
    SPARSE_INDEX_DIR,
    TEXT_COLLECTION_NAME,
    TEXT_EXTRACTION_VERSION,
)
from .bm25 import BM25Index, live_fingerprint

logger = logging.getLogger(__name__)

_CACHE: Optional[BM25Index] = None


def fold_accents_flag(tokenizer: str = BM25_TOKENIZER) -> bool:
    return tokenizer == "folded"


def open_text_collection(persist_dir=None, collection_name: str = TEXT_COLLECTION_NAME):
    """Mở `biology_text` bằng client Chroma thuần — KHÔNG nạp bge-m3.

    Dựng chỉ mục thưa không cần embedding model nào; nạp bge-m3 chỉ để đọc chữ
    ra là ~1 phút CPU đổi lấy đúng 0 thông tin.
    """
    import chromadb

    client = chromadb.PersistentClient(path=str(persist_dir or PERSIST_DIR))
    return client.get_collection(collection_name)


def _read_all(collection) -> Tuple[List[str], List[str]]:
    got = collection.get(include=["documents"], limit=1_000_000)
    ids = got.get("ids") or []
    docs = got.get("documents") or []
    if len(ids) != len(docs):
        raise RuntimeError(
            f"Chroma trả {len(ids)} id nhưng {len(docs)} văn bản — không ghép cặp được")
    return ids, docs


def build_sparse_index(persist_dir=None, index_dir=None,
                       tokenizer: str = BM25_TOKENIZER) -> BM25Index:
    """Dựng lại chỉ mục thưa từ đầu và lưu xuống đĩa."""
    t0 = time.time()
    collection = open_text_collection(persist_dir)
    ids, docs = _read_all(collection)
    if not ids:
        raise RuntimeError(
            f"`{TEXT_COLLECTION_NAME}` rỗng — chưa có gì để dựng chỉ mục thưa. "
            "Chạy `python main.py --text-only` trước.")
    fp = live_fingerprint(collection, tokenizer=tokenizer,
                          text_extraction_version=TEXT_EXTRACTION_VERSION)
    index = BM25Index.build(ids, docs, fp,
                            fold_accents=fold_accents_flag(tokenizer))
    target = Path(index_dir or SPARSE_INDEX_DIR)
    index.save(target)
    logger.info(
        "Chỉ mục thưa: %d chunk, %d từ vựng, độ dài TB %.1f token, %.1f s -> %s",
        len(index.ids), len(index.vocab), index.avg_len, time.time() - t0, target)
    global _CACHE
    _CACHE = index
    return index


def get_sparse_index(persist_dir=None, index_dir=None,
                     tokenizer: str = BM25_TOKENIZER,
                     collection=None) -> BM25Index:
    """Nạp chỉ mục thưa và **đối chiếu** với index dày hiện tại.

    Lệch -> `SparseIndexStale`. Không có nhánh "thôi dùng tạm bản cũ" (CẤM #6):
    một chỉ mục thưa cũ hơn index trả về `chunk_id` không còn tồn tại, và cách
    hỏng đó **im lặng** — cùng loại D-52.
    """
    global _CACHE
    index = _CACHE or BM25Index.load(Path(index_dir or SPARSE_INDEX_DIR))
    col = collection if collection is not None else open_text_collection(persist_dir)
    index.verify(live_fingerprint(
        col, tokenizer=tokenizer,
        text_extraction_version=TEXT_EXTRACTION_VERSION))
    _CACHE = index
    return index


def reset_cache() -> None:
    global _CACHE
    _CACHE = None
