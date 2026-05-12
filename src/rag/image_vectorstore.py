"""Image vector store using CLIP embeddings via sentence-transformers."""

import logging
from pathlib import Path
from typing import List, Optional

import torch
from PIL import Image
from langchain_core.documents import Document
from sentence_transformers import util
from transformers import CLIPModel, CLIPProcessor

from ..config import (
    CLIP_MODEL,
    IMAGE_COLLECTION_NAME,
    IMAGES_DIR,
    PERSIST_DIR,
    HF_TOKEN,
    IMAGE_RETRIEVER_K,
)

logger = logging.getLogger(__name__)


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
        self._clip_model: Optional[CLIPModel] = None
        self._clip_processor: Optional[CLIPProcessor] = None

        self._init_clip()
        self._init_chroma(documents)

        logger.info(f"ImageVectorDB initialized, collection: {self.collection_name}")

    def _init_clip(self):
        """Initialize CLIP model and processor via sentence-transformers."""
        logger.info(f"Loading CLIP model: {CLIP_MODEL}")
        self._clip_model = CLIPModel.from_pretrained(CLIP_MODEL, token=HF_TOKEN)
        self._clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL, token=HF_TOKEN)
        logger.info("CLIP model loaded")

    def _init_chroma(self, documents: Optional[List[Document]]):
        """Initialize ChromaDB for image storage."""
        from langchain_chroma import Chroma

        self._chroma = Chroma(
            collection_name=self.collection_name,
            embedding_function=_DummyEmbeddingFunction(),
            persist_directory=self.persist_dir,
        )

        if documents:
            self.add_documents(documents)

    def _encode_image(self, image_path: str) -> Optional[torch.Tensor]:
        """Encode an image to CLIP embedding using PIL."""
        try:
            from PIL import Image

            image = Image.open(image_path).convert("RGB")
            inputs = self._clip_processor(images=image, return_tensors="pt")
            with torch.no_grad():
                embedding = self._clip_model.get_image_features(**inputs)
            return embedding.pooler_output.squeeze(0)
        except Exception as e:
            logger.warning(f"Failed to encode image {image_path}: {e}")
            return None

    def _encode_text(self, text: str) -> torch.Tensor:
        """Encode text query to CLIP embedding."""
        inputs = self._clip_processor(text=[text], return_tensors="pt", padding=True)
        with torch.no_grad():
            embedding = self._clip_model.get_text_features(**inputs)
        return embedding.pooler_output.squeeze(0)

    def add_documents(self, documents: List[Document]):
        """Add image documents to the vector store."""
        if not documents:
            return

        ids = []
        embeddings = []
        metadatas = []
        page_contents = []

        for doc in documents:
            image_path = doc.metadata.get("image_path")
            if not image_path or not Path(image_path).exists():
                logger.warning(f"Image not found: {image_path}, skipping")
                continue

            embedding = self._encode_image(image_path)
            if embedding is None:
                continue

            doc_id = f"{Path(image_path).stem}_{Path(image_path).parent.name}"
            ids.append(doc_id)
            embeddings.append(embedding.cpu().numpy().tolist())
            metadatas.append(doc.metadata)
            page_contents.append(doc.page_content)

        if ids:
            self._chroma._collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=page_contents,
            )
            logger.info(f"Added {len(ids)} images to ImageVectorDB")

    def similarity_search(self, query: str, k: int = IMAGE_RETRIEVER_K) -> List[Document]:
        """Find most similar images to a text query using CLIP."""
        try:
            query_embedding = self._encode_text(query).cpu().numpy().tolist()

            results = self._chroma._collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
            )

            docs = []
            if results and results.get("ids") and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    doc = Document(
                        page_content=results["documents"][0][i],
                        metadata=results["metadatas"][0][i],
                    )
                    docs.append(doc)

            return docs
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


class ImageRetriever:
    """Retriever wrapper for ImageVectorDB with CLIP similarity."""

    def __init__(self, image_db: ImageVectorDB, search_kwargs: dict):
        self.image_db = image_db
        self.k = search_kwargs.get("k", IMAGE_RETRIEVER_K)

    def invoke(self, query: str) -> List[Document]:
        """Retrieve relevant images for a text query."""
        return self.image_db.similarity_search(query, k=self.k)