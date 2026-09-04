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
    cand_n = 50  # C-A: evaluate() nay đọc cfg.cand_n để ghi cột "cand_n" ra output


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

    # I-4 (phản biện Opus 5, 2026-09-04): ghim giá trị CHÍNH XÁC, không chỉ
    # "> 0" — chặn hồi quy nếu R@K vô tình quay lại hit@k nhị phân, hoặc F1@K
    # tính sai công thức (macro vs micro). q_ok có 5 chunk vàng
    # (`_n_gold_chunks=5`), `_fake_rank_for()` trả ["c1".."c5"] và mọi c1..c5
    # đều map về đúng trang vàng (page_of), nên top-1 CHỈ khớp 1/5 gold chunk:
    #   R@1 = |top-1 ∩ gold| / |gold| = 1/5 = 0.2  (TỈ LỆ CHUẨN, không phải
    #   hit@k nhị phân — nhị phân sẽ ra 1.0 vì có ít nhất 1 khớp trong top-1).
    #   R@5 = 5/5 = 1.0 (khớp hết 5/5).
    #   P@1 = 1/1 = 1.0 (1 trong 1 ứng viên top-1 là đúng).
    #   F1@1 = 2*P*R/(P+R) = 2*1.0*0.2/1.2 = 1/3.
    #   tranP@1 = min(k, n_gold_total)/k = min(1,5)/1 = 1.0.
    assert out["R@1"] == 0.2
    assert out["R@5"] == 1.0
    assert out["P@1"] == 1.0
    assert out["F1@1"] == pytest.approx(1 / 3, abs=1e-4)
    assert out["tranP@1"] == 1.0
