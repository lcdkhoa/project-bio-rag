from src.test.retrieval_benchmark import reciprocal_rank


def test_reciprocal_rank_first_hit():
    assert reciprocal_rank([False, True, False]) == 0.5
    assert reciprocal_rank([True, False]) == 1.0
    assert reciprocal_rank([False, False]) == 0.0
