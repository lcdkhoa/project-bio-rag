from langchain_core.documents import Document
from src.rag.image_vectorstore import ImageVectorDB


def _bare_db():
    return ImageVectorDB.__new__(ImageVectorDB)   # bypass heavy __init__ (no CLIP)


def _scored(name, score, search_text=""):
    return Document(page_content=name, metadata={
        "image_relevance_score": score, "search_text": search_text})


class _FakeReranker:
    def __init__(self, mapping):
        self.mapping = mapping
    def score(self, query, texts):
        return [self.mapping[t] for t in texts]


def test_boost_reorders_by_cross_encoder(monkeypatch):
    import src.rag.image_vectorstore as M
    monkeypatch.setattr(M, "IMAGE_RERANK_ENABLED", True)
    monkeypatch.setattr(M, "IMAGE_RERANK_TOP_N", 12)
    monkeypatch.setattr(M, "IMAGE_RERANK_WEIGHT", 0.25)

    db = _bare_db()
    db._reranker = _FakeReranker({"tA": 0.1, "tB": 0.9})
    # B starts slightly behind A but the cross-encoder strongly prefers B
    docs = [_scored("A", 0.50, "tA"), _scored("B", 0.45, "tB")]
    out = db._cross_encoder_boost("q", docs)
    assert [d.page_content for d in out] == ["B", "A"]
    assert out[0].metadata["image_cross_encoder_score"] == 0.9


def test_disabled_is_noop(monkeypatch):
    import src.rag.image_vectorstore as M
    monkeypatch.setattr(M, "IMAGE_RERANK_ENABLED", False)
    db = _bare_db()
    db._reranker = _FakeReranker({"tA": 0.9})
    docs = [_scored("A", 0.5, "tA")]
    out = db._cross_encoder_boost("q", docs)
    assert out[0].metadata.get("image_cross_encoder_score") is None
    assert out[0].metadata["image_relevance_score"] == 0.5


def test_exact_phrase_lead_not_overturned(monkeypatch):
    import src.rag.image_vectorstore as M
    monkeypatch.setattr(M, "IMAGE_RERANK_ENABLED", True)
    monkeypatch.setattr(M, "IMAGE_RERANK_TOP_N", 12)
    monkeypatch.setattr(M, "IMAGE_RERANK_WEIGHT", 0.25)
    db = _bare_db()
    db._reranker = _FakeReranker({"tExact": 0.0, "tOther": 1.0})
    # exact phrase match gave +0.45 lead; max CE delta is 0.25 -> lead holds
    docs = [_scored("Exact", 0.80, "tExact"), _scored("Other", 0.40, "tOther")]
    out = db._cross_encoder_boost("q", docs)
    assert out[0].page_content == "Exact"
