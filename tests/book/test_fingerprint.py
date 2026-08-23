"""Test phần THUẦN của M0 — chỗ off-by-one thật sự ẩn nấp.

Không test OCR ở đây (đó là phép đo trên trang thật, không phải unit test). Test
đúng ba thứ có thể sai lặng lẽ: bầu offset, lấy mẫu trang, và tính vùng.
"""

import pytest

from src.etl.book.fingerprint import (DigitToken, best_offset, sample_pages,
                                      zone_from_tokens)


def test_offset_0_khi_so_in_trung_ten_file():
    obs = [(n, [n]) for n in range(1, 21)]
    off, votes, _, _ = best_offset(obs)
    assert off == 0
    assert votes == 20


def test_offset_am_1_duoc_phat_hien():
    """Corpus KNTT cũ: printed = filenum − 1. Không được nhầm dấu."""
    obs = [(n, [n - 1]) for n in range(2, 22)]
    off, votes, _, _ = best_offset(obs)
    assert off == -1
    assert votes == 20


def test_mot_trang_chi_bo_toi_da_mot_phieu_cho_moi_offset():
    """Một trang chứa cùng một giá trị hai lần không được đếm thành hai phiếu."""
    obs = [(5, [5, 5, 5])]
    off, votes, _, _ = best_offset(obs)
    assert votes == 1


def test_trang_nhieu_chu_so_khong_lat_duoc_ket_qua():
    """19 trang sạch khớp offset 0; 1 trang rác chứa đủ mọi offset.

    Trang rác vẫn bỏ 1 phiếu cho MỌI offset, nên nó nâng đều tất cả — không thể
    biến một offset sai thành người thắng.
    """
    obs = [(n, [n]) for n in range(1, 20)]
    obs.append((100, [95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105]))
    off, votes, off2, votes2 = best_offset(obs)
    assert off == 0
    assert votes == 20          # 19 trang sạch + trang rác
    assert votes2 == 1          # á quân chỉ có phiếu của trang rác
    assert votes - votes2 == 19


def test_khong_doc_duoc_gi_thi_tra_None_chu_khong_doan():
    obs = [(n, []) for n in range(1, 11)]
    off, votes, _, _ = best_offset(obs)
    assert off is None
    assert votes == 0


def test_hoa_phieu_uu_tien_offset_gan_0_hon():
    """Hai offset cùng số phiếu -> chọn cái gần 0; tie-break phải TẤT ĐỊNH."""
    obs = [(n, [n, n + 3]) for n in range(1, 11)]
    off, votes, off2, votes2 = best_offset(obs)
    assert off == 0
    assert votes == votes2 == 10
    assert off2 == 3


def test_sample_pages_rai_deu_va_khong_trung():
    pages = list(range(1, 201))
    got = sample_pages(pages, 40)
    assert len(got) == 40
    assert len(set(got)) == 40
    assert got == sorted(got)
    assert got[0] == 1 and got[-1] <= 200
    # rải đều: không được dồn vào đầu sách
    assert got[-1] > 180


def test_sample_pages_it_hon_k_thi_lay_het():
    pages = [1, 2, 3]
    assert sample_pages(pages, 40) == [1, 2, 3]


def test_zone_tum_tum_cho_iqr_nho():
    toks = [DigitToken(i, 90.0, 0.50 + 0.001 * (i % 2), 0.95, "bottom")
            for i in range(20)]
    z = zone_from_tokens(toks)
    assert z["y_iqr"] < 0.01
    assert z["strips"] == ["bottom"]


def test_zone_rai_rac_cho_iqr_lon():
    toks = [DigitToken(i, 90.0, 0.1 + 0.04 * i, 0.05 + 0.04 * i, "top")
            for i in range(20)]
    z = zone_from_tokens(toks)
    assert z["y_iqr"] > 0.2


def test_zone_rong_khi_khong_co_token():
    assert zone_from_tokens([]) == {}


# ---------------------------------------------- giai đoạn B: tìm cụm mực bằng CV

import numpy as np

from src.etl.book.fingerprint import _ink_runs, band_and_side


def _band(width=1000, height=40, marks=()):
    """Dải trắng, vẽ các cụm mực đen theo [x0, x1)."""
    img = np.full((height, width, 3), 255, np.uint8)
    for x0, x1 in marks:
        img[5:height - 5, x0:x1] = 0
    return img


def test_ink_runs_tach_hai_cum_cach_xa():
    band = _band(marks=[(100, 140), (700, 760)])
    runs = _ink_runs(band, gap_px=10, min_w=4)
    assert runs == [(100, 140), (700, 760)]


def test_ink_runs_gop_khoang_trang_nho_hon_gap():
    """Hai chữ số cạnh nhau phải là MỘT cụm, nếu không '75' sẽ tách thành '7','5'."""
    band = _band(marks=[(100, 120), (126, 146)])
    runs = _ink_runs(band, gap_px=10, min_w=4)
    assert runs == [(100, 146)]


def test_ink_runs_bo_cum_qua_hep():
    band = _band(marks=[(100, 102), (700, 760)])
    runs = _ink_runs(band, gap_px=10, min_w=8)
    assert runs == [(700, 760)]


def test_ink_runs_dai_trang_tron_tra_rong():
    assert _ink_runs(_band(), gap_px=10, min_w=4) == []


def test_band_and_side_trai_phai_theo_x_median():
    assert band_and_side({"n": 5, "y_median": 0.94, "y_iqr": 0.0,
                          "x_median": 0.10})[2] == "left"
    assert band_and_side({"n": 5, "y_median": 0.94, "y_iqr": 0.0,
                          "x_median": 0.89})[2] == "right"


def test_band_and_side_khong_do_duoc_thi_None():
    assert band_and_side({}) is None
    assert band_and_side({"n": 0}) is None


def test_band_khong_bao_gio_vuot_khoi_trang():
    y0, y1, _ = band_and_side({"n": 5, "y_median": 0.99, "y_iqr": 0.20,
                               "x_median": 0.9})
    assert 0.0 <= y0 < y1 <= 1.0
