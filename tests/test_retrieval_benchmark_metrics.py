import pytest

from src.test.retrieval_benchmark import KS, _gold_key, evaluate, reciprocal_rank


def test_reciprocal_rank_giu_nguyen_hanh_vi():
    assert reciprocal_rank([False, True, False]) == 0.5
    assert reciprocal_rank([True, False]) == 1.0
    assert reciprocal_rank([False, False]) == 0.0


def test_gold_key_rong_khi_thieu_source_book_hoac_page():
    assert _gold_key({"source_book": "", "source_page": "5"}) is None
    assert _gold_key({"source_book": "SGK_KHTN_6_CD", "source_page": ""}) is None
    assert _gold_key({}) is None


def test_gold_key_hop_le():
    assert _gold_key({"source_book": "SGK_KHTN_6_CD", "source_page": "5"}) \
        == ("SGK_KHTN_6_CD", 5)


class _FakeConfig:
    label = "fake"
    mode = "dense"
    rerank = False
    gate = False


def _fake_rank_for(*args, **kwargs):
    return ["c1", "c2", "c3", "c4", "c5"]


def test_evaluate_phan_biet_3_nhom(monkeypatch):
    monkeypatch.setattr(
        "src.test.retrieval_benchmark.rank_for",
        lambda cfg, q, cache, sparse, top_n, gate_stats=None: _fake_rank_for())
    monkeypatch.setattr(
        "src.test.retrieval_benchmark.method_label", lambda cfg: "")

    rows = [
        # nhóm 1: không có trang vàng -> ngoai_pham_vi
        {"question": "q_opv", "source_book": "", "source_page": "",
         "_n_gold_chunks": 0},
        # nhóm 2: có trang vàng, 0 chunk -> suy_bien
        {"question": "q_sb", "source_book": "SGK_KHTN_6_CD",
         "source_page": "999", "_n_gold_chunks": 0},
        # nhóm 3: có trang vàng, có chunk -> tính bình thường
        {"question": "q_ok", "source_book": "SGK_KHTN_6_CD",
         "source_page": "5", "_n_gold_chunks": 5},
    ]
    page_of = {f"c{i}": ("SGK_KHTN_6_CD", 5) for i in range(1, 6)}
    out = evaluate(_FakeConfig(), rows, cache=None, sparse=None, page_of=page_of)

    assert out["so_cau"] == 1          # chỉ nhóm 3 vào mẫu P/R/F1/MRR
    assert out["suy_bien_gold_0_chunk"] == 1
    assert out["ngoai_pham_vi_so_cau"] == 1
    for k in KS:
        assert out[f"P@{k}"] > 0       # nhóm 3 khớp hết -> P/R > 0
