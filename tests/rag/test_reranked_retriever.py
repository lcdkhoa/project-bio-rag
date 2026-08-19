# tests/rag/test_reranked_retriever.py
from langchain_core.documents import Document
from src.rag.vectorstore import RerankedRetriever


class _FakeStore:
    """Mimics Chroma.similarity_search_with_score(query, k) -> [(doc, distance)]."""
    def __init__(self, pairs):
        self._pairs = pairs
    def similarity_search_with_score(self, query, k):
        return self._pairs[:k]


class _FakeReranker:
    def __init__(self, scores):
        self._scores = scores
    def score(self, query, texts):
        # map by page_content marker "d0".."dn" set up in the test
        return [self._scores[t] for t in texts]


def _doc(name):
    return Document(page_content=name, metadata={"source": "s.pdf", "page": 1})


def test_keeps_top_max_k_by_rerank_score():
    # distance order says A best, but reranker says C > A > B
    pairs = [(_doc("A"), 0.1), (_doc("B"), 0.2), (_doc("C"), 0.3)]
    rr = RerankedRetriever(
        vectorstore=_FakeStore(pairs),
        reranker=_FakeReranker({"A": 0.7, "B": 0.3, "C": 0.9}),
        fetch_k=3, max_k=2, score_min=0.2,
    )
    docs = rr.invoke("q")
    assert [d.page_content for d in docs] == ["C", "A"]      # top-2 by rerank
    assert docs[0].metadata["rerank_score"] == 0.9


def test_drops_below_score_min():
    pairs = [(_doc("A"), 0.1), (_doc("B"), 0.2)]
    rr = RerankedRetriever(
        vectorstore=_FakeStore(pairs),
        reranker=_FakeReranker({"A": 0.5, "B": 0.05}),
        fetch_k=2, max_k=4, score_min=0.2,
    )
    docs = rr.invoke("q")
    assert [d.page_content for d in docs] == ["A"]           # B gated out


def test_all_below_min_returns_empty():
    pairs = [(_doc("A"), 0.1)]
    rr = RerankedRetriever(
        vectorstore=_FakeStore(pairs),
        reranker=_FakeReranker({"A": 0.01}),
        fetch_k=1, max_k=4, score_min=0.2,
    )
    assert rr.invoke("q") == []


def test_reranker_failure_falls_back_to_distance_order():
    pairs = [(_doc("A"), 0.3), (_doc("B"), 0.1)]   # B closer by distance

    class _Empty:
        def score(self, query, texts):
            return []                              # model failed
    rr = RerankedRetriever(vectorstore=_FakeStore(pairs), reranker=_Empty(),
                           fetch_k=2, max_k=1, score_min=0.2)
    docs = rr.invoke("q")
    assert [d.page_content for d in docs] == ["B"]           # distance fallback
