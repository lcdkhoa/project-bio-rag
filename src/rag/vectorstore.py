"""Vector database management using ChromaDB."""

import logging
from typing import List, Optional

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

from ..config import EMBEDDING_MODEL, CHROMA_COLLECTION_NAME, PERSIST_DIR, RETRIEVER_K, HF_TOKEN

logger = logging.getLogger(__name__)


class VectorDB:
    """ChromaDB vector store wrapper with embedding support."""

    def __init__(
        self,
        documents: Optional[List[Document]] = None,
        embedding_model: str = EMBEDDING_MODEL,
        collection_name: str = CHROMA_COLLECTION_NAME,
        persist_dir: str = str(PERSIST_DIR),
    ):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.embedding = HuggingFaceEmbeddings(
            model_name=embedding_model,
            model_kwargs={"token": HF_TOKEN} if HF_TOKEN else {},
        )
        self.db = self._build_db(documents)
        logger.info(f"VectorDB initialized with {self.db._collection.count()} existing chunks")

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
        if search_kwargs is None:
            search_kwargs = {"k": RETRIEVER_K}
        return self.db.as_retriever(
            search_type="similarity",
            search_kwargs=search_kwargs,
        )
