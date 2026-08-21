"""Checkpoint ETL theo TỪNG TRANG, khoá theo nội dung trang + version.

Khoá là `page_key` = `{tên quyển}#{md5 nội dung trang}` (xem
`page_source.page_checkpoint_key`), **không** phải hash của cả quyển như bản cũ:
tải bù 19 trang chỉ re-process 19 trang, và thay một trang dưới cùng tên file
cũng bị bắt.

Cả hai phía đều có version gate: `TEXT_EXTRACTION_VERSION` cho đường text (mới —
trước đây chỉ ảnh có version nên đổi logic OCR không ép re-OCR được) và
`IMAGE_EXTRACTION_VERSION` cho đường ảnh. Bump version = ép làm lại.
"""

import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from ..config import (PERSIST_DIR, STATUS_COLLECTION_NAME, EMBEDDING_MODEL,
                      IMAGE_EXTRACTION_VERSION, TEXT_EXTRACTION_VERSION,
                      embedding_model_kwargs)
from .page_source import page_checkpoint_key

logger = logging.getLogger(__name__)


def compute_file_hash(file_path: str) -> str:
    """Compute MD5 hash of a file for deduplication."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def compute_string_hash(text: str) -> str:
    """Compute MD5 hash of a string."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


class ProcessingStatus:
    """Trạng thái xử lý của từng trang — nguồn sự thật duy nhất cho resume."""

    def __init__(self):
        self.embedding = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs=embedding_model_kwargs(),
        )
        self.db = Chroma(
            collection_name=STATUS_COLLECTION_NAME,
            embedding_function=self.embedding,
            persist_directory=str(PERSIST_DIR),
        )
        self._status_cache: Dict[str, dict] = {}
        self._load_cache()

    def _load_cache(self):
        """Load all status records into memory for fast lookup."""
        try:
            results = self.db.get()
            if results and results.get("ids"):
                for i, doc_id in enumerate(results["ids"]):
                    doc = results["documents"][i]
                    self._status_cache[doc_id] = json.loads(doc)
        except Exception:
            self._status_cache = {}

    def _make_doc_id(self, page_key: str, page_number: int) -> str:
        return f"{page_key}_page_{page_number}"

    def get_status(self, page_key: str, page_number: int) -> Optional[dict]:
        """Trạng thái của một trang (`page_key` = khoá nội dung trang)."""
        doc_id = self._make_doc_id(page_key, page_number)
        return self._status_cache.get(doc_id)

    def needs_text_processing(
        self,
        page_key: str,
        page_number: int,
        required_version: Optional[str] = None,
    ) -> bool:
        """Trang này còn phải OCR/index text không (theo version yêu cầu)?"""
        status = self.get_status(page_key, page_number)
        if status is None or not status.get("text_indexed", False):
            return True
        if not required_version:
            return False
        current = str(status.get("text_extraction_version") or "").strip()
        return current != required_version

    def needs_image_processing(self, page_key: str, page_number: int) -> bool:
        """Check if a page needs image extraction."""
        return self.needs_image_processing_versioned(page_key, page_number, required_version=None)

    def needs_image_processing_versioned(
        self,
        page_key: str,
        page_number: int,
        required_version: Optional[str] = None,
    ) -> bool:
        """Check if a page needs image extraction for the current extraction version."""
        status = self.get_status(page_key, page_number)
        if status is None or not status.get("image_extracted", False):
            return True

        if not required_version:
            return False

        current_version = str(status.get("image_extraction_version") or "").strip()
        return current_version != required_version

    def update_status(
        self,
        page_key: str,
        page_number: int,
        text_indexed: Optional[bool] = None,
        image_extracted: Optional[bool] = None,
        image_extraction_version: Optional[str] = None,
        text_extraction_version: Optional[str] = None,
        pdf_filename: Optional[str] = None,
    ):
        """Ghi trạng thái của một trang."""
        doc_id = self._make_doc_id(page_key, page_number)
        existing = self.get_status(page_key, page_number) or {}

        updated = {
            "page_key": page_key,
            "page_number": page_number,
            "pdf_filename": pdf_filename or existing.get("pdf_filename"),
            "text_indexed": text_indexed if text_indexed is not None else existing.get("text_indexed", False),
            "image_extracted": image_extracted if image_extracted is not None else existing.get("image_extracted", False),
            "image_extraction_version": image_extraction_version
            if image_extraction_version is not None
            else existing.get("image_extraction_version", ""),
            "text_extraction_version": text_extraction_version
            if text_extraction_version is not None
            else existing.get("text_extraction_version", ""),
            "last_updated": datetime.now().isoformat(),
        }

        self._status_cache[doc_id] = updated

        from langchain_core.documents import Document

        doc = Document(page_content=json.dumps(updated),
                       metadata={"page_key": page_key, "page": page_number})
        self.db.add_documents([doc], ids=[doc_id])

    def mark_text_indexed(self, page_key: str, page_number: int,
                          pdf_filename: str,
                          text_extraction_version: Optional[str] = None):
        """Đánh dấu một trang đã index text, kèm version đã dùng."""
        self.update_status(
            page_key,
            page_number,
            text_indexed=True,
            text_extraction_version=text_extraction_version,
            pdf_filename=pdf_filename,
        )
        logger.debug(f"[{pdf_filename}] Page {page_number}: text indexed")

    def mark_image_extracted(
        self,
        page_key: str,
        page_number: int,
        pdf_filename: str,
        image_extraction_version: Optional[str] = None,
    ):
        """Mark images as extracted for a specific page."""
        self.update_status(
            page_key,
            page_number,
            image_extracted=True,
            image_extraction_version=image_extraction_version,
            pdf_filename=pdf_filename,
        )
        logger.debug(f"[{pdf_filename}] Page {page_number}: images extracted")

    def pages_needing_text(self, source,
                           required_version: str = TEXT_EXTRACTION_VERSION
                           ) -> List[int]:
        """Các SỐ TRANG NGUỒN còn phải index text, tăng dần.

        Duyệt `source.page_numbers()` (số trong tên file) chứ không `range(n)`:
        dãy trang có thể có lỗ, và `range` sẽ đi hỏi trạng thái của những trang
        không tồn tại.
        """
        return [number for number in source.page_numbers()
                if self.needs_text_processing(
                    page_checkpoint_key(source, number), number,
                    required_version=required_version)]

    def pages_needing_images(self, source,
                             required_version: str = IMAGE_EXTRACTION_VERSION
                             ) -> List[int]:
        """Các SỐ TRANG NGUỒN còn phải crop hình, tăng dần."""
        return [number for number in source.page_numbers()
                if self.needs_image_processing_versioned(
                    page_checkpoint_key(source, number), number,
                    required_version=required_version)]

    def get_all_status_for_source(self, source_name: str) -> List[dict]:
        """Mọi trạng thái trang của một quyển (khoá bắt đầu bằng tên quyển)."""
        return [
            status
            for doc_id, status in self._status_cache.items()
            if doc_id.startswith(f"{source_name}#")
        ]
