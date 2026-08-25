"""Bộ đo độ phủ nhãn hình — chính phép đo đã lộ ra lỗi ▲ của CTST (D-121).

Test không đụng ChromaDB thật; nó khoá hai thứ dễ hỏng âm thầm:
ngưỡng cảnh báo phải là số ĐO ĐƯỢC chứ không phải số gõ tay, và script phải
THOÁT KHÁC 0 khi có quyển dưới ngưỡng (nếu không thì đưa vào CI sẽ luôn xanh).
"""
import sys

import pytest

from src.test import qa_figure_coverage as Q


def test_nguong_canh_bao_nam_duoi_muc_do_duoc_cua_CD_va_KNTT():
    """Ngưỡng phải thấp hơn mức thật của CD (92%) và KNTT (95%).

    Đặt cao hơn thì hai bộ vốn đúng cũng bị gắn cờ và cảnh báo mất giá trị; đặt
    quá thấp thì CTST 51--65% cũng lọt. 0,80 nằm giữa hai mức đo được.
    """
    assert 0.65 < Q.NGUONG_CANH_BAO < 0.92


@pytest.mark.parametrize("text,mong_doi", [
    ("Hình 2.1. Kích thước", {("2", "1")}),
    ("À Hình 11.9 Sơ đồ", {("11", "9")}),
    ("Quan sát Hình 5.3 và Hình 5.4", {("5", "3"), ("5", "4")}),
    # Viết thường KHÔNG khớp, và đó là chủ đích: dạng thường gần như luôn là
    # tham chiếu thân bài. Đo được: bật IGNORECASE kéo 9_CD từ 97% xuống 84%
    # vì thêm 41 tham chiếu vào mẫu số mà chỉ thêm 9 nhãn vào tử số.
    ("xem hình 3.2 ở trang trước", set()),
    ("Hình 2,1 dấu phẩy do OCR", {("2", "1")}),
    ("Bảng 12.1 không phải hình", set()),
    ("không có nhãn nào", set()),
])
def test_bat_nhan_hinh_ke_ca_khi_OCR_lam_hong(text, mong_doi):
    assert set(Q.FIG.findall(text)) == mong_doi


def test_cai_gia_cua_viec_giu_chu_HOA_duoc_ghi_lai():
    """Lựa chọn này bỏ sót ~6% nhãn crop viết thường — phải nói ra trong mã.

    Một đánh đổi có đo mà không ghi lại thì lượt sau sẽ "sửa" nó và làm số tệ đi.
    """
    import inspect
    src = inspect.getsource(Q)
    assert "128/2126" in src, "phải ghi cái giá đo được của lựa chọn"
    assert "84%" in src, "phải ghi số đo của phương án bị loại"


def test_dem_theo_nhan_KHAC_NHAU_khong_theo_so_lan_xuat_hien():
    """Tham chiếu lặp ("Hình 2.1" nhắc 10 lần) không được thổi phồng độ phủ."""
    text = "Hình 2.1 " * 10
    assert len(set(Q.FIG.findall(text))) == 1


def test_thoat_khac_0_khi_co_quyen_duoi_nguong(monkeypatch, capsys):
    monkeypatch.setattr(Q, "thu_thap", lambda *a, **k: {
        "SGK_KHTN_6_CD": {"nhan_tren_chu": 100, "nhan_tu_crop": 95, "phu": 0.95,
                          "n_doc": 200, "n_co_figure_label": 190,
                          "trang_co_chu": 178, "trang_co_hinh": 150},
        "SGK_KHTN_6_CTST": {"nhan_tren_chu": 100, "nhan_tu_crop": 55, "phu": 0.55,
                            "n_doc": 120, "n_co_figure_label": 100,
                            "trang_co_chu": 203, "trang_co_hinh": 90},
    })
    monkeypatch.setattr(sys, "argv", ["cov"])
    assert Q.main() == 1
    out = capsys.readouterr().out
    assert "THẤP" in out and "SGK_KHTN_6_CTST" in out
    assert "CẬN DƯỚI CÓ NHIỄU" in out, "phải luôn in giới hạn của phép đo"


def test_thoat_0_khi_moi_quyen_dat_nguong(monkeypatch):
    monkeypatch.setattr(Q, "thu_thap", lambda *a, **k: {
        "SGK_KHTN_6_CD": {"nhan_tren_chu": 100, "nhan_tu_crop": 95, "phu": 0.95,
                          "n_doc": 200, "n_co_figure_label": 190,
                          "trang_co_chu": 178, "trang_co_hinh": 150},
    })
    monkeypatch.setattr(sys, "argv", ["cov"])
    assert Q.main() == 0


def test_quyen_chua_co_chu_khong_lam_vo_script(monkeypatch):
    """`phu = None` khi mẫu số bằng 0 — không được chia cho 0 hay gắn cờ oan."""
    monkeypatch.setattr(Q, "thu_thap", lambda *a, **k: {
        "SGK_KHTN_9_CD": {"nhan_tren_chu": 0, "nhan_tu_crop": 0, "phu": None,
                          "n_doc": 0, "n_co_figure_label": 0,
                          "trang_co_chu": 0, "trang_co_hinh": 0},
    })
    monkeypatch.setattr(sys, "argv", ["cov"])
    assert Q.main() == 0
