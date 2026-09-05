"""
Singleton manager for Biology RAG components to avoid reloading heavy models on every request.
"""
import logging
from src.rag import get_hf_llm, BiologyRAG, HybridRetriever

logger = logging.getLogger(__name__)

class AppServices:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AppServices, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        logger.info("Initializing AppServices singleton...")
        # D-186: `self.vdb = VectorDB()` từng nạp một bản bge-m3 THỨ BA hoàn
        # toàn không dùng tới (HybridRetriever tự tạo VectorDB riêng cho truy
        # xuất text) — trên Colab GPU 14,56 GiB, ba bản bge-m3 fp32 + Qwen2.5-
        # 3B fp16 + CLIP + reranker chiếm gần hết VRAM, khiến forward pass đầu
        # tiên của reranker (chỉ cần thêm ~80 MiB) CUDA OOM. Grep xác nhận
        # không nơi nào đọc `AppServices().vdb` trước khi xoá.
        self.hybrid_retriever = HybridRetriever()
        self.llm = get_hf_llm()
        self.rag = BiologyRAG(self.llm)

        self._initialized = True
        logger.info("AppServices initialized successfully.")

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls()
        return cls._instance
