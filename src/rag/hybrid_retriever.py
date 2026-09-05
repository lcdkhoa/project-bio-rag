"""Hybrid retriever combining text (MiniLM) and image (CLIP) search."""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

from langchain_core.documents import Document

from ..config import RETRIEVER_K, IMAGE_RETRIEVER_K
from .vectorstore import VectorDB
from .image_vectorstore import ImageVectorDB
from .query_intent import has_image_intent, is_image_only_query

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Combined search result from text and image retrieval."""

    text_docs: List[Document]
    image_docs: List[Document]
    image_only_query: bool = False

    @property
    def has_images(self) -> bool:
        return len(self.image_docs) > 0

    @property
    def all_docs(self) -> List[Document]:
        return self.text_docs + self.image_docs


class HybridRetriever:
    """Unified retriever that searches both text and image collections."""

    def __init__(
        self,
        text_retriever_k: int = RETRIEVER_K,
        image_retriever_k: int = IMAGE_RETRIEVER_K,
    ):
        self.text_db = VectorDB()
        self.image_db = ImageVectorDB()

        self.text_k = text_retriever_k
        self.image_k = image_retriever_k

        self._text_retriever = self.text_db.get_retriever({"k": self.text_k})
        self._image_retriever = self.image_db.get_retriever({"k": self.image_k})

    def search(self, query: str) -> SearchResult:
        """Perform hybrid search: text + image simultaneously."""
        text_docs = []
        image_docs = []
        image_only_query = is_image_only_query(query)

        if image_only_query:
            image_docs = self.search_image_only(query)
            return SearchResult(
                text_docs=[],
                image_docs=image_docs,
                image_only_query=True,
            )

        try:
            text_docs = self._text_retriever.invoke(query)
        except Exception:
            # D-184: dùng logger.exception (traceback đầy đủ), không phải
            # warning(str(e)) — một lượt eval Colab 2026-09-04 nuốt lỗi này
            # thành "0 kết quả" cho 240/240 câu mà không ai biết nguyên nhân
            # vì message ngắn không đủ để chẩn đoán.
            logger.exception("Text retrieval failed for query: %r", query)

        # Chỉ tìm ảnh khi câu hỏi có tín hiệu RÕ RÀNG cần hình (`has_image_intent`,
        # cùng bộ từ khoá đã dùng cho định tuyến chỉ-ảnh). Trước bản vá này, MỌI
        # câu hỏi thuần chữ đều kèm gallery ảnh — đo thật 2026-09-02: câu hỏi Hoá
        # thuần "sắt tác dụng với axit tạo thành gì" vẫn trả về 3 ảnh không ai hỏi.
        if has_image_intent(query):
            try:
                image_docs = self._image_retriever.invoke(query, related_text_docs=text_docs)
            except Exception:
                logger.exception("Image retrieval failed for query: %r", query)

        return SearchResult(
            text_docs=text_docs,
            image_docs=image_docs,
            image_only_query=image_only_query,
        )

    def search_text_only(self, query: str) -> List[Document]:
        """Search text collection only."""
        try:
            return self._text_retriever.invoke(query)
        except Exception:
            logger.exception("Text retrieval failed for query: %r", query)
            return []

    def search_image_only(self, query: str) -> List[Document]:
        """Search image collection only."""
        try:
            return self._image_retriever.invoke(query)
        except Exception:
            logger.exception("Image retrieval failed for query: %r", query)
            return []
