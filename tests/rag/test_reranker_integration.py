"""Real-model integration test for the cross-encoder reranker.

Skipped by default (no model download / no GPU dependency at collection
time). Set RUN_RERANK_INTEGRATION=1 to actually load BAAI/bge-reranker-v2-m3
and confirm it scores a clearly-relevant Vietnamese passage above an
irrelevant one — i.e. the cross-encoder is oriented correctly before eval
numbers are trusted.
"""
import os

import pytest

RUN = os.getenv("RUN_RERANK_INTEGRATION") == "1"


@pytest.mark.skipif(not RUN, reason="set RUN_RERANK_INTEGRATION=1 to load bge-reranker")
def test_real_reranker_orders_relevant_higher():
    from src.rag.reranker import CrossEncoderReranker

    r = CrossEncoderReranker()
    scores = r.score(
        "Quang hợp là gì?",
        [
            "Quang hợp là quá trình cây xanh tổng hợp chất hữu cơ từ ánh sáng.",
            "Bảng tuần hoàn các nguyên tố hóa học.",
        ],
    )
    assert len(scores) == 2
    assert scores[0] > scores[1]
