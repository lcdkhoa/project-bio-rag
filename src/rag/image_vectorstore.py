"""Image vector store using CLIP embeddings via sentence-transformers."""

import logging
import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from transformers import CLIPModel, CLIPProcessor

from ..config import (
    CLIP_MODEL,
    EMBEDDING_MODEL,
    IMAGE_COLLECTION_NAME,
    IMAGE_METADATA_COLLECTION_NAME,
    IMAGE_METADATA_FETCH_K,
    PERSIST_DIR,
    HF_TOKEN,
    IMAGE_RETRIEVER_K,
    IMAGE_RETRIEVER_FETCH_K,
    IMAGE_RELEVANCE_THRESHOLD,
)

logger = logging.getLogger(__name__)

VIETNAMESE_TO_ENGLISH_VISUAL_HINTS = {
    "ca": "fish",
    "ca xiem": "betta fish siamese fighting fish",
    "mau": "color colorful",
    "doi mau": "changing color",
    "te bao": "cell",
    "gan": "liver",
    "muoi": "mosquito",
    "sot ret": "malaria",
    "thuc vat": "plant",
    "dong vat": "animal",
    "hoa": "flower",
    "hat": "seed",
    "re": "root",
}


class ImageVectorDB:
    """ChromaDB-backed image store with CLIP embeddings for semantic image search."""

    def __init__(
        self,
        documents: Optional[List[Document]] = None,
        collection_name: str = IMAGE_COLLECTION_NAME,
        persist_dir: str = str(PERSIST_DIR),
    ):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.metadata_collection_name = IMAGE_METADATA_COLLECTION_NAME
        self._clip_model: Optional[CLIPModel] = None
        self._clip_processor: Optional[CLIPProcessor] = None
        self._metadata_embedding = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"token": HF_TOKEN} if HF_TOKEN else {},
        )

        self._init_clip()
        self._init_chroma(documents)

        logger.info(f"ImageVectorDB initialized, collection: {self.collection_name}")

    def _init_clip(self):
        """Initialize CLIP model and processor via sentence-transformers."""
        logger.info(f"Loading CLIP model: {CLIP_MODEL}")
        self._clip_model = CLIPModel.from_pretrained(CLIP_MODEL, token=HF_TOKEN)
        self._clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL, token=HF_TOKEN)
        self._clip_model.eval()
        logger.info("CLIP model loaded")

    def _init_chroma(self, documents: Optional[List[Document]]):
        """Initialize ChromaDB for image storage."""
        from langchain_chroma import Chroma

        self._chroma = Chroma(
            collection_name=self.collection_name,
            embedding_function=_DummyEmbeddingFunction(),
            persist_directory=self.persist_dir,
        )
        self._metadata_chroma = Chroma(
            collection_name=self.metadata_collection_name,
            embedding_function=_DummyMetadataEmbeddingFunction(self._metadata_embedding),
            persist_directory=self.persist_dir,
        )

        if documents:
            self.add_documents(documents)

    def _to_projected_embedding(self, output: Any, projection_name: str) -> torch.Tensor:
        """Extract a tensor embedding across transformers versions."""
        if isinstance(output, torch.Tensor):
            return output

        for attr_name in ("image_embeds", "text_embeds"):
            embedding = getattr(output, attr_name, None)
            if isinstance(embedding, torch.Tensor):
                return embedding

        pooled = getattr(output, "pooler_output", None)
        if isinstance(pooled, torch.Tensor):
            projection = getattr(self._clip_model, projection_name, None)
            return projection(pooled) if projection is not None else pooled

        if isinstance(output, (tuple, list)) and output:
            return self._to_projected_embedding(output[0], projection_name)

        raise TypeError(f"Unsupported CLIP output type: {type(output)!r}")

    def _normalize_embedding(self, embedding: torch.Tensor) -> torch.Tensor:
        """Normalize CLIP embeddings so vector distance maps more closely to cosine similarity."""
        embedding = embedding.squeeze(0)
        norm = embedding.norm(p=2).clamp(min=1e-12)
        return embedding / norm

    def _encode_image(self, image_path: str) -> Optional[torch.Tensor]:
        """Encode an image to CLIP embedding using PIL."""
        try:
            from PIL import Image

            image = Image.open(image_path).convert("RGB")
            inputs = self._clip_processor(images=image, return_tensors="pt")
            with torch.no_grad():
                output = self._clip_model.get_image_features(**inputs)
                embedding = self._to_projected_embedding(output, "visual_projection")
            return self._normalize_embedding(embedding)
        except Exception as e:
            logger.warning(f"Failed to encode image {image_path}: {e}")
            return None

    def _encode_text(self, text: str) -> torch.Tensor:
        """Encode text query to CLIP embedding."""
        inputs = self._clip_processor(text=[text], return_tensors="pt", padding=True)
        with torch.no_grad():
            output = self._clip_model.get_text_features(**inputs)
            embedding = self._to_projected_embedding(output, "text_projection")
        return self._normalize_embedding(embedding)

    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Keep metadata Chroma-compatible and predictable."""
        sanitized = {}
        for key, value in metadata.items():
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                sanitized[key] = value
            elif isinstance(value, Path):
                sanitized[key] = str(value)
            elif isinstance(value, (list, tuple)):
                sanitized[key] = ",".join(str(item) for item in value)
            else:
                sanitized[key] = str(value)
        return sanitized

    def _build_search_text(self, doc: Document) -> str:
        """Combine visual caption and local OCR text for bilingual image retrieval."""
        metadata = doc.metadata or {}
        parts = [
            doc.page_content,
            metadata.get("figure_label", ""),
            metadata.get("section_title", ""),
            metadata.get("image_type", ""),
            metadata.get("keywords_vi", ""),
            metadata.get("caption_vi", ""),
            metadata.get("caption", ""),
            metadata.get("caption_en", ""),
            metadata.get("context_text", ""),
            metadata.get("nearby_text", ""),
            metadata.get("ocr_text", ""),
            metadata.get("pdf_filename", ""),
            f"trang {metadata.get('page_number', '')}",
        ]

        seen = set()
        cleaned_parts = []
        for part in parts:
            text = str(part or "").strip()
            if text and text not in seen:
                cleaned_parts.append(text)
                seen.add(text)

        return "\n".join(cleaned_parts)

    def add_documents(self, documents: List[Document]):
        """Add image documents to the vector store."""
        if not documents:
            return

        metadata_ids = []
        metadata_embeddings = []
        metadata_metadatas = []
        metadata_page_contents = []
        visual_ids = []
        visual_embeddings = []
        visual_metadatas = []
        visual_page_contents = []

        for doc in documents:
            image_path = doc.metadata.get("image_path")
            if not image_path or not Path(image_path).exists():
                logger.warning(f"Image not found: {image_path}, skipping")
                continue

            doc_id = f"{Path(image_path).stem}_{Path(image_path).parent.name}"
            search_text = self._build_search_text(doc)
            metadata = self._sanitize_metadata({**doc.metadata, "search_text": search_text})

            metadata_ids.append(doc_id)
            metadata_metadatas.append(metadata)
            metadata_page_contents.append(search_text)

            visual_embedding = self._encode_image(image_path)
            if visual_embedding is None:
                continue

            visual_ids.append(doc_id)
            visual_embeddings.append(visual_embedding.cpu().numpy().tolist())
            visual_metadatas.append(metadata)
            visual_page_contents.append(search_text)

        if metadata_ids:
            metadata_embeddings = self._metadata_embedding.embed_documents(metadata_page_contents)
            self._metadata_chroma._collection.upsert(
                ids=metadata_ids,
                embeddings=metadata_embeddings,
                metadatas=metadata_metadatas,
                documents=metadata_page_contents,
            )
            logger.info(f"Added {len(metadata_ids)} image metadata docs to ImageVectorDB")

        if visual_ids:
            self._chroma._collection.upsert(
                ids=visual_ids,
                embeddings=visual_embeddings,
                metadatas=visual_metadatas,
                documents=visual_page_contents,
            )
            logger.info(f"Added {len(visual_ids)} visual image docs to ImageVectorDB")

    def _normalize_text(self, text: str) -> str:
        text = unicodedata.normalize("NFD", text.lower())
        text = "".join(char for char in text if unicodedata.category(char) != "Mn")
        return re.sub(r"[^a-z0-9\s]+", " ", text)

    def _tokenize(self, text: str) -> List[str]:
        stopwords = {
            "a",
            "an",
            "and",
            "are",
            "as",
            "cua",
            "co",
            "con",
            "duoc",
            "gi",
            "hinh",
            "la",
            "mot",
            "nhung",
            "the",
            "trong",
            "ve",
            "what",
            "which",
            "with",
        }
        return [
            token
            for token in self._normalize_text(text).split()
            if len(token) > 1 and token not in stopwords
        ]

    def _expand_query_for_clip(self, query: str) -> str:
        """Add lightweight English visual hints for CLIP's English-heavy text encoder."""
        normalized_query = self._normalize_text(query)
        hints = []
        for vietnamese_term, english_hint in VIETNAMESE_TO_ENGLISH_VISUAL_HINTS.items():
            if vietnamese_term in normalized_query:
                hints.append(english_hint)

        if not hints:
            return query

        return f"{query}. {' '.join(dict.fromkeys(hints))}"

    def _lexical_score(self, query: str, doc: Document) -> float:
        query_tokens = set(self._tokenize(query))
        if not query_tokens:
            return 0.0

        metadata = doc.metadata or {}
        search_text = " ".join(
            str(value or "")
            for value in (
                doc.page_content,
                metadata.get("search_text"),
                metadata.get("figure_label"),
                metadata.get("section_title"),
                metadata.get("keywords_vi"),
                metadata.get("caption_vi"),
                metadata.get("caption"),
                metadata.get("caption_en"),
                metadata.get("context_text"),
                metadata.get("nearby_text"),
            )
        )
        doc_tokens = set(self._tokenize(search_text))
        if not doc_tokens:
            return 0.0

        overlap = len(query_tokens & doc_tokens) / len(query_tokens)
        normalized_query = self._normalize_text(query).strip()
        normalized_doc = self._normalize_text(search_text)
        exact_bonus = 0.2 if normalized_query and normalized_query in normalized_doc else 0.0
        return min(1.0, overlap + exact_bonus)

    def _distance_to_similarity(self, distance: Optional[float]) -> float:
        if distance is None or not math.isfinite(distance):
            return 0.0
        if distance <= 2:
            return max(0.0, 1.0 - (distance / 2.0))
        return max(0.0, 1.0 / (1.0 + distance))

    def _extract_related_pages(self, related_text_docs: Optional[List[Document]]) -> Dict[int, float]:
        page_boosts: Dict[int, float] = {}
        for rank, doc in enumerate(related_text_docs or []):
            metadata = doc.metadata or {}
            page = metadata.get("page") or metadata.get("page_number")
            try:
                page_number = int(page)
            except (TypeError, ValueError):
                continue

            boost = max(0.12, 0.3 - (rank * 0.05))
            page_boosts[page_number] = max(page_boosts.get(page_number, 0.0), boost)
            page_boosts[page_number - 1] = max(page_boosts.get(page_number - 1, 0.0), boost * 0.45)
            page_boosts[page_number + 1] = max(page_boosts.get(page_number + 1, 0.0), boost * 0.45)
        return page_boosts

    def _docs_from_query_results(
        self,
        results: dict,
        score_field: str,
        distance_field: str,
        source: str,
    ) -> List[Document]:
        docs = []
        ids = results.get("ids", [[]])[0] if results else []
        documents = results.get("documents", [[]])[0] if results else []
        metadatas = results.get("metadatas", [[]])[0] if results else []
        distances = results.get("distances", [[]])[0] if results else []

        for i, doc_id in enumerate(ids):
            metadata = dict(metadatas[i] or {})
            distance = distances[i] if i < len(distances) else None
            metadata["image_doc_id"] = doc_id
            metadata[distance_field] = distance
            metadata[score_field] = self._distance_to_similarity(distance)
            metadata["image_retrieval_source"] = source
            docs.append(Document(page_content=documents[i] or "", metadata=metadata))
        return docs

    def _get_page_candidates(self, page_boosts: Dict[int, float]) -> List[Document]:
        if not page_boosts:
            return []

        docs = []
        for page_number in sorted(page_boosts):
            if page_number <= 0:
                continue
            try:
                results = self._metadata_chroma._collection.get(
                    where={"page_number": page_number},
                    include=["documents", "metadatas"],
                )
            except Exception as e:
                logger.debug(f"Could not fetch image candidates for page {page_number}: {e}")
                continue

            for i, doc_id in enumerate(results.get("ids", [])):
                metadata = dict((results.get("metadatas") or [])[i] or {})
                metadata["image_doc_id"] = doc_id
                metadata["image_metadata_distance"] = None
                metadata["image_metadata_score"] = 0.0
                metadata["image_visual_distance"] = None
                metadata["image_visual_score"] = 0.0
                metadata["image_retrieval_source"] = "page_context"
                docs.append(Document(page_content=(results.get("documents") or [""])[i] or "", metadata=metadata))
        return docs

    def _page_boost(self, doc: Document, page_boosts: Dict[int, float]) -> float:
        page = (doc.metadata or {}).get("page_number")
        try:
            return page_boosts.get(int(page), 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _rerank(
        self,
        query: str,
        candidates: List[Document],
        page_boosts: Dict[int, float],
        k: int,
        min_score: float,
    ) -> List[Document]:
        unique: Dict[str, Document] = {}
        for doc in candidates:
            metadata = doc.metadata or {}
            dedupe_key = metadata.get("image_doc_id") or metadata.get("image_path") or doc.page_content
            if dedupe_key not in unique:
                unique[dedupe_key] = doc
                continue

            existing = unique[dedupe_key]
            merged_metadata = {**(existing.metadata or {})}
            for key, value in metadata.items():
                if key in {"image_metadata_score", "image_visual_score", "image_page_boost", "image_relevance_score"}:
                    merged_metadata[key] = max(float(merged_metadata.get(key) or 0.0), float(value or 0.0))
                elif key not in merged_metadata or merged_metadata[key] in (None, "", 0):
                    merged_metadata[key] = value

            sources = {
                source
                for source in (
                    str(merged_metadata.get("image_retrieval_source") or ""),
                    str(metadata.get("image_retrieval_source") or ""),
                )
                if source
            }
            if sources:
                merged_metadata["image_retrieval_source"] = ",".join(sorted(sources))
            page_content = existing.page_content if len(existing.page_content) >= len(doc.page_content) else doc.page_content
            unique[dedupe_key] = Document(page_content=page_content, metadata=merged_metadata)

        scored_docs = []
        for doc in unique.values():
            metadata = dict(doc.metadata or {})
            metadata_score = float(metadata.get("image_metadata_score") or 0.0)
            visual_score = float(metadata.get("image_visual_score") or 0.0)
            lexical_score = self._lexical_score(query, doc)
            page_score = self._page_boost(doc, page_boosts)
            final_score = (metadata_score * 0.5) + (lexical_score * 0.25) + (visual_score * 0.15) + page_score

            metadata["image_lexical_score"] = round(lexical_score, 4)
            metadata["image_page_boost"] = round(page_score, 4)
            metadata["image_relevance_score"] = round(final_score, 4)
            scored_docs.append(Document(page_content=doc.page_content, metadata=metadata))

        scored_docs.sort(key=lambda doc: doc.metadata.get("image_relevance_score", 0.0), reverse=True)
        filtered = [doc for doc in scored_docs if doc.metadata.get("image_relevance_score", 0.0) >= min_score]

        logger.info(
            "Image retrieval candidates=%s, kept=%s, threshold=%.2f, top_scores=%s",
            len(scored_docs),
            len(filtered[:k]),
            min_score,
            [doc.metadata.get("image_relevance_score") for doc in scored_docs[: min(5, len(scored_docs))]],
        )
        return filtered[:k]

    def similarity_search(
        self,
        query: str,
        k: int = IMAGE_RETRIEVER_K,
        related_text_docs: Optional[List[Document]] = None,
        fetch_k: int = IMAGE_RETRIEVER_FETCH_K,
        min_score: float = IMAGE_RELEVANCE_THRESHOLD,
    ) -> List[Document]:
        """Find relevant images using Vietnamese metadata first, with visual CLIP as rerank support."""
        try:
            metadata_query_embedding = self._metadata_embedding.embed_query(query)
            metadata_results = self._metadata_chroma._collection.query(
                query_embeddings=[metadata_query_embedding],
                n_results=max(k, IMAGE_METADATA_FETCH_K),
                include=["documents", "metadatas", "distances"],
            )

            clip_query = self._expand_query_for_clip(query)
            query_embedding = self._encode_text(clip_query).cpu().numpy().tolist()

            visual_results = self._chroma._collection.query(
                query_embeddings=[query_embedding],
                n_results=max(k, fetch_k),
                include=["documents", "metadatas", "distances"],
            )

            page_boosts = self._extract_related_pages(related_text_docs)
            candidates = self._docs_from_query_results(
                metadata_results,
                score_field="image_metadata_score",
                distance_field="image_metadata_distance",
                source="metadata",
            )
            candidates.extend(
                self._docs_from_query_results(
                    visual_results,
                    score_field="image_visual_score",
                    distance_field="image_visual_distance",
                    source="visual",
                )
            )
            candidates.extend(self._get_page_candidates(page_boosts))
            return self._rerank(query, candidates, page_boosts, k, min_score)
        except Exception as e:
            logger.error(f"Image similarity search failed: {e}")
            return []

    def get_retriever(self, search_kwargs: dict = None):
        """Return a retriever for image search."""
        if search_kwargs is None:
            search_kwargs = {"k": IMAGE_RETRIEVER_K}

        return ImageRetriever(self, search_kwargs)


class _DummyEmbeddingFunction:
    """Dummy embedding function since we pre-compute CLIP embeddings manually."""

    def embed_documents(self, texts):
        return [[0.0] * 512 for _ in texts]

    def embed_query(self, text):
        return [0.0] * 512


class _DummyMetadataEmbeddingFunction:
    """Adapter used when querying the raw Chroma collection with precomputed embeddings."""

    def __init__(self, embedding_model: HuggingFaceEmbeddings):
        self.embedding_model = embedding_model

    def embed_documents(self, texts):
        return self.embedding_model.embed_documents(texts)

    def embed_query(self, text):
        return self.embedding_model.embed_query(text)


class ImageRetriever:
    """Retriever wrapper for ImageVectorDB with CLIP similarity."""

    def __init__(self, image_db: ImageVectorDB, search_kwargs: dict):
        self.image_db = image_db
        self.k = search_kwargs.get("k", IMAGE_RETRIEVER_K)
        self.fetch_k = search_kwargs.get("fetch_k", IMAGE_RETRIEVER_FETCH_K)
        self.min_score = search_kwargs.get("min_score", IMAGE_RELEVANCE_THRESHOLD)

    def invoke(self, query: str, related_text_docs: Optional[List[Document]] = None) -> List[Document]:
        """Retrieve relevant images for a text query."""
        return self.image_db.similarity_search(
            query,
            k=self.k,
            related_text_docs=related_text_docs,
            fetch_k=self.fetch_k,
            min_score=self.min_score,
        )
