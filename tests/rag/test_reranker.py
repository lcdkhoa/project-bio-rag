import math
from src.rag.reranker import CrossEncoderReranker, get_reranker


def test_score_applies_sigmoid_in_order():
    r = CrossEncoderReranker(predictor=lambda pairs: [2.0, -2.0, 0.0])
    out = r.score("q", ["a", "b", "c"])
    assert len(out) == 3
    # sigmoid: 2.0 -> ~0.88, -2.0 -> ~0.12, 0.0 -> 0.5, order preserved
    assert out[0] > out[2] > out[1]
    assert math.isclose(out[2], 0.5, abs_tol=1e-6)
    assert all(0.0 <= s <= 1.0 for s in out)


def test_empty_texts_returns_empty():
    r = CrossEncoderReranker(predictor=lambda pairs: [1.0])
    assert r.score("q", []) == []


def test_predictor_error_returns_empty():
    def boom(pairs):
        raise RuntimeError("model down")
    r = CrossEncoderReranker(predictor=boom)
    assert r.score("q", ["a", "b"]) == []


def test_get_reranker_is_singleton():
    assert get_reranker() is get_reranker()
