import random

import pytest

from src.test.build_testset import (
    _anh_xa_hinh_sang_cot,
    _kiem_tra_du_pool,
    _kiem_tra_input,
    _tinh_n_moi_nhom,
)


def test_tinh_n_moi_nhom_tong_bang_n_total():
    n = _tinh_n_moi_nhom(n_total=240, n_ngoai_pham_vi=30,
                          n_chunk=16515, n_anh=3881)
    assert n["n_van_ban"] + n["n_hinh"] + n["n_ngoai_pham_vi"] == 240
    assert n["n_ngoai_pham_vi"] == 30


def test_tinh_n_moi_nhom_ti_le_hinh_dung_cong_thuc():
    n = _tinh_n_moi_nhom(n_total=210, n_ngoai_pham_vi=0,
                          n_chunk=8000, n_anh=2000)
    # p_hinh = 2000 / 10000 = 0.2 -> n_hinh = round(210 * 0.2) = 42
    assert n["n_hinh"] == 42
    assert n["n_van_ban"] == 168


def test_kiem_tra_input_chan_ngoai_pham_vi_qua_lon():
    with pytest.raises(SystemExit, match="n-ngoai-pham-vi"):
        _kiem_tra_input(n_total=100, n_ngoai_pham_vi=100)
    with pytest.raises(SystemExit, match="n-ngoai-pham-vi"):
        _kiem_tra_input(n_total=100, n_ngoai_pham_vi=150)


def test_kiem_tra_input_hop_le_khong_raise():
    _kiem_tra_input(n_total=240, n_ngoai_pham_vi=30)  # không raise


def test_kiem_tra_du_pool_chan_pool_thieu():
    with pytest.raises(SystemExit, match="pool"):
        _kiem_tra_du_pool(pool_size=10, n_can=40)


def test_anh_xa_hinh_sang_cot_dung_pdf_filename_page_number():
    meta = {
        "pdf_filename": "SGK_KHTN_6_CD",
        "page_number": 5,
        "figure_label": "Hình 1.1",
    }
    row = _anh_xa_hinh_sang_cot(meta)
    assert row["source_book"] == "SGK_KHTN_6_CD"
    assert row["source_page"] == "5"
    assert row["figure_label"] == "Hình 1.1"


def test_anh_xa_hinh_sang_cot_khong_bao_gio_doc_truong_source():
    # Nếu code lỡ đọc metadata.get("source")/metadata.get("page") (tên trường
    # bên TEXT, không tồn tại bên ẢNH) sẽ ra None -> rỗng. Test này chặn hồi quy
    # đúng lỗi nghiêm trọng nhất tìm được ở phản biện lần 4 của spec.
    meta = {"pdf_filename": "SGK_KHTN_7_CTST", "page_number": 12,
            "figure_label": "Hình 2.3", "source": None, "page": None}
    row = _anh_xa_hinh_sang_cot(meta)
    assert row["source_book"] == "SGK_KHTN_7_CTST"
    assert row["source_page"] == "12"


def test_seed_tai_lap_duoc():
    ids = [f"c{i}" for i in range(1000)]
    a = random.Random(42).sample(ids, 50)
    b = random.Random(42).sample(ids, 50)
    c = random.Random(43).sample(ids, 50)
    assert a == b
    assert a != c
