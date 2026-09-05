"""Shared cross-encoder reranker (BAAI/bge-reranker-v2-m3), GPU/CPU-safe.

Lazy singleton reused by both text (RerankedRetriever) and image
(ImageVectorDB._rerank) sides. Scores are sigmoid(logit) in [0,1]; any load
or inference failure returns [] so callers fall back to their non-reranked
order instead of crashing the request.
"""
import logging
import math
from typing import Callable, List, Optional

from ..config import RERANK_MODEL, USE_GPU

logger = logging.getLogger(__name__)


def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-float(x)))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


class CrossEncoderReranker:
    def __init__(self, model_name: str = RERANK_MODEL,
                 predictor: Optional[Callable[[list], List[float]]] = None):
        self._model_name = model_name
        self._predictor = predictor          # injected for tests/DI
        self._model = None

    def _predict(self, pairs: list) -> List[float]:
        if self._predictor is not None:
            return list(self._predictor(pairs))
        if self._model is None:
            from sentence_transformers import CrossEncoder
            device = "cpu"
            if USE_GPU:
                try:
                    import torch
                    if torch.cuda.is_available():
                        device = "cuda"
                except Exception:
                    device = "cpu"
            logger.info("Loading reranker %s on %s", self._model_name, device)
            self._model = CrossEncoder(self._model_name, device=device, max_length=512)
        return list(self._model.predict(pairs))

    def score(self, query: str, texts: List[str]) -> List[float]:
        if not texts:
            return []
        try:
            pairs = [[query, t] for t in texts]
            logits = self._predict(pairs)
            if len(logits) != len(texts):
                logger.error("Reranker returned %d scores for %d texts", len(logits), len(texts))
                return []
            return [_sigmoid(x) for x in logits]
        except Exception:
            # D-184: traceback đầy đủ, không phải warning(str(e)) — đây là
            # nguyên nhân GỐC khi caller (hybrid_text_retriever.py) thấy `ce`
            # rỗng và raise RuntimeError chung chung "Cross-encoder trả 0
            # điểm..."; không có dòng này thì lý do THẬT (model không tải
            # được, OOM, v.v.) không bao giờ lộ ra.
            logger.exception("Reranker scoring failed (model=%s)", self._model_name)
            return []


_RERANKER: Optional[CrossEncoderReranker] = None


def get_reranker() -> CrossEncoderReranker:
    global _RERANKER
    if _RERANKER is None:
        _RERANKER = CrossEncoderReranker()
    return _RERANKER
