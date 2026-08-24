"""Vector database management using ChromaDB."""

import logging
from typing import Any, List, Optional

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict

from .reranker import get_reranker
from ..config import (
    EMBEDDING_MODEL,
    TEXT_COLLECTION_NAME,
    PERSIST_DIR,
    RETRIEVER_FETCH_K,
    RETRIEVER_MAX_K,
    RETRIEVER_DISTANCE_MARGIN,
    RERANK_ENABLED,
    RERANK_FETCH_K,
    RERANK_SCORE_MIN,
    RETRIEVAL_MODE,
    embedding_model_kwargs,
)

logger = logging.getLogger(__name__)


class RelevanceGatedRetriever(BaseRetriever):
    """Retriever that drops chunks far from the best match.

    Plain top-k similarity always returns ``k`` chunks regardless of how
    relevant they are, so off-topic pages bleed into the LLM context and the
    answer (e.g. a fish-colour question pulling in unrelated reproduction /
    light-mixing pages). This retriever fetches a wider candidate set, then
    keeps only chunks whose distance is within ``(1 + margin)`` of the closest
    match — chunks that are clearly farther away are discarded.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    vectorstore: Chroma
    fetch_k: int = RETRIEVER_FETCH_K
    max_k: int = RETRIEVER_MAX_K
    distance_margin: float = RETRIEVER_DISTANCE_MARGIN

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        # Chroma returns (doc, distance) with lower distance = more similar.
        scored = self.vectorstore.similarity_search_with_score(query, k=self.fetch_k)
        if not scored:
            return []

        scored.sort(key=lambda pair: pair[1])
        best_distance = scored[0][1]
        cutoff = best_distance * (1.0 + self.distance_margin)

        kept = []
        for doc, distance in scored:
            if distance <= cutoff:
                kept.append(doc)
            else:
                logger.debug(
                    "Gated out chunk (dist=%.3f > cutoff=%.3f): %s",
                    distance, cutoff, doc.page_content[:60].replace("\n", " "),
                )
            if len(kept) >= self.max_k:
                break

        logger.info(
            "RelevanceGatedRetriever: %d/%d candidates kept (best=%.3f, cutoff=%.3f) for query=%r",
            len(kept), len(scored), best_distance, cutoff, query,
        )
        return kept


class RerankedRetriever(BaseRetriever):
    """Fetch wide, cross-encoder rerank, keep top max_k, gate on rerank score.

    Cross-encoder relevance (higher = better) replaces embedding distance for
    the final ordering. An absolute score gate (score_min) drops weak chunks so
    an all-irrelevant fetch returns nothing and the LLM emits its fallback. If
    the reranker yields no usable scores, fall back to distance order.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    vectorstore: Any
    reranker: Any = None
    fetch_k: int = RERANK_FETCH_K
    max_k: int = RETRIEVER_MAX_K
    score_min: float = RERANK_SCORE_MIN

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        scored = self.vectorstore.similarity_search_with_score(query, k=self.fetch_k)
        if not scored:
            return []
        docs = [doc for doc, _ in scored]
        reranker = self.reranker or get_reranker()
        ce = reranker.score(query, [doc.page_content for doc in docs])

        if not ce or len(ce) != len(docs):
            scored_sorted = sorted(scored, key=lambda pair: pair[1])
            logger.warning("RerankedRetriever: reranker unavailable, distance fallback")
            return [doc for doc, _ in scored_sorted[: self.max_k]]

        paired = sorted(zip(docs, ce), key=lambda pair: pair[1], reverse=True)
        kept: List[Document] = []
        for doc, score in paired:
            if score < self.score_min:
                break
            doc.metadata["rerank_score"] = round(float(score), 4)
            kept.append(doc)
            if len(kept) >= self.max_k:
                break
        logger.info(
            "RerankedRetriever: %d/%d kept (top=%.3f, min=%.2f) for query=%r",
            len(kept), len(docs), paired[0][1], self.score_min, query,
        )
        return kept


class VectorDB:
    """ChromaDB vector store wrapper with embedding support."""

    def __init__(
        self,
        documents: Optional[List[Document]] = None,
        embedding_model: str = EMBEDDING_MODEL,
        collection_name: str = TEXT_COLLECTION_NAME,
        persist_dir: str = str(PERSIST_DIR),
    ):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.embedding = HuggingFaceEmbeddings(
            model_name=embedding_model,
            model_kwargs=embedding_model_kwargs(),
        )
        self.db = self._build_db(documents)
        self._chunk_lookup = None
        logger.info(f"VectorDB initialized with {self.db._collection.count()} existing chunks")

    def chunk_lookup(self):
        """`ChunkLookup` dùng chung, dựng MỘT lần.

        `get_retriever()` được gọi hai chỗ (`AppServices` và
        `HybridRetriever.__init__`), mà mỗi `ChunkLookup` phải đọc trọn 16 393
        chunk. Dựng hai lần là đọc hai lần và giữ hai bản trong RAM.
        """
        if self._chunk_lookup is None:
            from .hybrid_text_retriever import ChunkLookup
            self._chunk_lookup = ChunkLookup(self.db._collection)
        return self._chunk_lookup

    def _build_db(self, documents):
        if documents is None or len(documents) == 0:
            logger.info("Loading existing VectorDB")
            db = Chroma(
                collection_name=self.collection_name,
                embedding_function=self.embedding,
                persist_directory=self.persist_dir,
            )
        else:
            logger.info(f"Creating new VectorDB with {len(documents)} documents")
            db = Chroma.from_documents(
                documents=documents,
                embedding=self.embedding,
                collection_name=self.collection_name,
                persist_directory=self.persist_dir,
            )
        return db

    def get_retriever(self, search_kwargs: dict = None):
        search_kwargs = search_kwargs or {}
        # `k` (if supplied by callers like HybridRetriever) caps the number of
        # chunks kept *after* relevance gating; the wider candidate sweep is
        # controlled by fetch_k.
        max_k = search_kwargs.get("k", RETRIEVER_MAX_K)

        # M2: đường thưa+dày. `RETRIEVAL_MODE="dense"` giữ NGUYÊN hai lớp cũ để
        # mặc định không đổi hành vi khi chưa có bảng số (nguyên tắc 3); hai chế
        # độ kia đi qua `HybridTextRetriever`, nơi cổng lọc và rerank là hai
        # công tắc RỜI NHAU.
        if RETRIEVAL_MODE != "dense":
            from .hybrid_text_retriever import HybridTextRetriever
            from .sparse_store import get_sparse_index

            collection = self.db._collection
            return HybridTextRetriever(
                vectorstore=self.db,
                lookup=self.chunk_lookup(),
                sparse=get_sparse_index(collection=collection),
                mode=RETRIEVAL_MODE,
                max_k=max_k,
                dense_fetch_k=max(RERANK_FETCH_K, max_k),
            )

        if RERANK_ENABLED:
            return RerankedRetriever(
                vectorstore=self.db,
                fetch_k=max(RERANK_FETCH_K, max_k),
                max_k=max_k,
            )
        return RelevanceGatedRetriever(
            vectorstore=self.db,
            fetch_k=max(RETRIEVER_FETCH_K, max_k),
            max_k=max_k,
        )
