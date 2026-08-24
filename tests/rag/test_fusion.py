# -*- coding: utf-8 -*-
"""Test hợp nhất thưa/dày + cổng lọc.

Test quan trọng nhất ở đây là `test_tat_kenh_thua_ra_dung_dense_thuan`: §3.3 của
prompt M2 gọi nó là **tự kiểm bắt buộc** — "hybrid mà tắt kênh thưa phải cho ra
ĐÚNG kết quả của dense thuần; không đúng thì đường ống có nhánh ẩn".
"""

import pytest

from src.rag.fusion import GateStats, fuse, relevance_gate


DENSE = [("a", 0.10), ("b", 0.20), ("c", 0.30)]      # khoảng cách, nhỏ = tốt
SPARSE = [("c", 9.0), ("d", 4.0), ("a", 1.0)]        # điểm, lớn = tốt


@pytest.mark.parametrize("method", ["rrf", "norm"])
def test_tat_kenh_thua_ra_dung_dense_thuan(method):
    """TỰ KIỂM BẮT BUỘC (§3.3): hybrid không có kênh thưa == dense thuần."""
    got = [it.key for it in fuse(DENSE, [], method=method)]
    assert got == [k for k, _ in DENSE]


@pytest.mark.parametrize("method", ["rrf", "norm"])
def test_tat_kenh_day_ra_dung_bm25_thuan(method):
    got = [it.key for it in fuse([], SPARSE, method=method)]
    assert got == [k for k, _ in SPARSE]


@pytest.mark.parametrize("method", ["rrf", "norm"])
def test_hop_nhat_giu_MOI_ung_vien_cua_ca_hai_kenh(method):
    """Kênh nọ sót kênh kia là chuyện bình thường — đó là lý do hợp nhất tồn tại."""
    keys = {it.key for it in fuse(DENSE, SPARSE, method=method)}
    assert keys == {"a", "b", "c", "d"}


def test_trung_o_ca_hai_kenh_thi_len_hang():
    """'a' hạng 1 dày + hạng 3 thưa phải thắng 'b' chỉ có ở một kênh."""
    items = fuse(DENSE, SPARSE, method="rrf", rrf_k=60)
    order = [it.key for it in items]
    assert order[0] == "a"
    assert order.index("a") < order.index("b")
    a = next(it for it in items if it.key == "a")
    assert a.channels == "dense+sparse"
    b = next(it for it in items if it.key == "b")
    assert b.channels == "dense"


def test_moi_item_giu_dau_vet_tung_kenh():
    items = {it.key: it for it in fuse(DENSE, SPARSE, method="rrf")}
    assert items["a"].dense_distance == 0.10 and items["a"].sparse_score == 1.0
    assert items["d"].dense_rank is None and items["d"].sparse_rank == 2


def test_dense_weight_1_bo_han_kenh_thua_trong_rrf():
    order = [it.key for it in fuse(DENSE, SPARSE, method="rrf", dense_weight=1.0)]
    assert order[:3] == ["a", "b", "c"], "trọng số 1.0 phải giữ nguyên thứ tự dày"


def test_method_la_khong_ro_thi_raise():
    with pytest.raises(ValueError):
        fuse(DENSE, SPARSE, method="magic")


def test_thu_tu_on_dinh_khi_hoa_diem():
    """Hai khoá cùng điểm phải ra thứ tự XÁC ĐỊNH, không phụ thuộc hash của set."""
    d = [("x", 0.5), ("y", 0.5)]
    for _ in range(5):
        assert [it.key for it in fuse(d, [], method="rrf")] == ["x", "y"]


# --- Cổng lọc -----------------------------------------------------------

def test_cong_loc_tren_khoang_cach_khop_cong_thuc_cu():
    """Bản tổng quát phải trả ĐÚNG kết quả của RelevanceGatedRetriever cũ."""
    dists = [0.10, 0.12, 0.13, 0.50]
    keep = relevance_gate(dists, margin=0.3, higher_is_better=False)
    cutoff = 0.10 * 1.3
    assert keep == [d <= cutoff for d in dists] == [True, True, True, False]


def test_cong_loc_tren_diem():
    scores = [9.0, 8.0, 1.0]
    assert relevance_gate(scores, margin=0.3, higher_is_better=True) == [
        True, True, False]


def test_cong_loc_rong_va_margin_0():
    assert relevance_gate([], margin=0.3, higher_is_better=False) == []
    assert relevance_gate([0.1, 0.1, 0.2], 0.0, False) == [True, True, False]


def test_diem_RRF_bi_NEN_nen_cong_loc_tuong_doi_gan_nhu_khong_cat():
    """Con số tính ra được, không phải phỏng đoán — đây là CÁI BẪY của §3.3.

    RRF hạng 1 = 1/61 = 0,01639; hạng 10 = 1/70 = 0,01429 -> chênh 12,8%, nằm
    TRONG margin 0,3, nên cổng tương đối không cắt gì cả.
    """
    rrf = [1.0 / (60 + r) for r in range(1, 11)]
    do_trai = (max(rrf) - min(rrf)) / max(rrf)
    assert do_trai == pytest.approx(0.1286, abs=1e-3)
    assert all(relevance_gate(rrf, margin=0.3, higher_is_better=True))


def test_gate_stats_dem_dung():
    st = GateStats()
    st.observe([9.0, 8.0, 1.0], [True, True, False])
    st.observe([5.0, 5.0], [True, True])
    s = st.summary()
    assert s["so_truy_van"] == 2
    assert s["ung_vien_tb"] == 2.5 and s["giu_lai_tb"] == 2.0
    assert s["ti_le_truy_van_bi_cat"] == 0.5
