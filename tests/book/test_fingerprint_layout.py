"""Test phần THUẦN của M0 §1–§2 — chỗ một hằng số px có thể lặng lẽ sai.

Không test OCR ở đây (đó là phép đo trên trang thật). Test đúng ba lớp có thể sai
mà không ai thấy:

1. **Ngưỡng px tỉ lệ theo trang.** Ở đúng 1094 px (KNTT) mọi bộ số phải trả về Y
   NGUYÊN con số đã được đo, nếu không thì "refactor cho CD" âm thầm đổi luôn kết
   quả của KNTT. Một bug thật đã bị bắt bởi test này: `2*round(k*3/2)+1` biến
   kernel 3 thành 5 ở scale 1× (banker's rounding), tức mất đúng kernel duy nhất
   đọc được `Hình 2.3` (D-51).
2. **Nhận diện chữ "MỤC LỤC"** trên bản đã bỏ dấu, kể cả khi OCR đọc sai nguyên âm.
3. **Ghép token của nhãn hình**: Tesseract tách `Hình 1.2` thành 2–3 token.
"""

import numpy as np
import pytest

from src.etl.book import fp_figure, fp_palette, fp_toc
from src.etl.book import toc as T
from src.etl.layout import pill as P


# ------------------------------------------- §2.2 ngưỡng hình học theo cỡ trang

def test_geom_o_1094px_tra_lai_dung_bo_so_da_do_tren_kntt():
    g = T.geom_for_width(1094)
    assert (g["col_gutter"], g["min_col_width"]) == (T.COL_GUTTER, T.MIN_COL_WIDTH)
    assert (g["row_gutter"], g["min_row_height"]) == (T.ROW_GUTTER, T.MIN_ROW_HEIGHT)
    assert (g["pad_gutter"], g["pad_gutter_wide"]) == (6, 12)
    assert (g["cell_pad_y"], g["eps"], g["min_col_gap"], g["row_extend"]) == (3, 4, 10, 26)


def test_geom_no_ra_theo_ti_le_khi_trang_to_hon():
    """CD 2480 px: khe 8 px của KNTT phải thành ~18 px, không được giữ 8."""
    g = T.geom_for_width(2480)
    assert g["col_gutter"] == 18
    assert g["min_col_width"] > T.MIN_COL_WIDTH
    assert g["row_extend"] > 26


def test_geom_khong_bao_gio_thu_nho_duoi_bo_so_goc():
    """Trang NHỎ hơn 1094 px không được làm ngưỡng nhỏ hơn số đã đo (k >= 1)."""
    g = T.geom_for_width(600)
    assert g["k"] == 1.0
    assert g["col_gutter"] == T.COL_GUTTER


def test_pads_chi_no_khi_cot_den_tu_gutter():
    """Cột có ĐƯỜNG KẺ thì pad = 0: nới ra sẽ liếm nét kẻ, ô trống OCR ra số ma."""
    g = T.geom_for_width(2480)
    assert T._pads("rules", geom=g) == (0,)
    assert T._pads("rules", full=True, geom=g) == (0,)
    assert T._pads("gutter", geom=g) == (g["pad_gutter"],)
    assert T._pads("gutter", full=True, geom=g) == (0, g["pad_gutter"],
                                                   g["pad_gutter_wide"])


# --------------------------------------------- §2.4 ngưỡng pill theo cỡ trang

def test_pill_bounds_o_1094px_giu_nguyen_ke_ca_kernel_3():
    """Kernel 3 là kernel DUY NHẤT đọc được `Hình 2.3` (D-51) — không được mất."""
    b = P.bounds_for_width(1094)
    assert (b["min_w"], b["max_w"]) == (P.MIN_W, P.MAX_W)
    assert (b["min_h"], b["max_h"]) == (P.MIN_H, P.MAX_H)
    assert b["close_kernels"] == P.CLOSE_KERNELS


def test_pill_bounds_no_ra_du_cho_pill_cua_cd():
    """MAX_W 460 px của KNTT sẽ loại sạch pill của CD nếu không nới theo trang."""
    b = P.bounds_for_width(2480)
    assert b["max_w"] > 900
    assert b["min_w"] > P.MIN_W


def test_moi_kernel_pill_deu_la_so_le_va_it_nhat_3():
    """k chẵn làm morphology lệch tâm; k<3 thì `closed == mask` -> loại mọi pill."""
    for width in (1094, 1536, 2280, 2480, 3000):
        for k in P.bounds_for_width(width)["close_kernels"]:
            assert k >= 3 and k % 2 == 1, (width, k)


# ------------------------------------------------------ §2.1 nhận chữ MỤC LỤC

@pytest.mark.parametrize("text, expected", [
    ("MỤC LỤC", "exact"),
    ("Mục lục", "exact"),
    ("muc luc", "exact"),
    # Dính liền vẫn nhận: tiêu đề "MỤC LỤC" thường in giãn chữ và OCR hay nuốt
    # khoảng trắng. "mucluc" không phải một từ tiếng Việt nào khác nên rủi ro
    # khớp bừa gần bằng 0, trong khi bỏ sót nó là bỏ sót cả bảng mục lục.
    ("MUCLUC", "exact"),
    ("MỤC  LỤC", "exact"),
    ("MOC LOC", "fuzzy"),             # OCR đọc ụ thành o
    ("M0C L0C", "fuzzy"),
    ("Bài 1. Mở đầu", None),
    ("", None),
])
def test_marker_muc_luc(text, expected):
    assert fp_toc.muc_luc_marker(text) == expected


def test_fold_bo_dau_va_giu_khoang_trang():
    assert fp_toc.fold("Đường HÓA học") == "duong hoa hoc"
    assert fp_toc.fold("  nhiều   khoảng \n trắng ") == "nhieu khoang trang"


def test_contiguous():
    assert fp_toc._contiguous([6, 7, 8])
    assert fp_toc._contiguous([6])
    assert fp_toc._contiguous([])
    assert not fp_toc._contiguous([6, 8])


# ------------------------------------------------------- §2.3 vùng nền phẳng

def _page(width=1000, height=1400):
    return np.full((height, width, 3), 255, np.uint8)


def test_flat_regions_bat_duoc_hop_mau_phang():
    img = _page()
    img[200:600, 100:700] = (200, 180, 120)      # ~17% trang, nền phẳng có tông
    regions = fp_palette.flat_regions(img)
    assert len(regions) == 1
    assert regions[0]["area_frac"] > 0.15
    assert regions[0]["uniform"] > 0.9


def test_flat_regions_bo_qua_anh_nhieu():
    """Ảnh chụp có tông nhưng KHÔNG phẳng -> không phải hộp."""
    rng = np.random.default_rng(0)
    img = _page()
    img[200:600, 100:700] = rng.integers(0, 256, (400, 600, 3), dtype=np.uint8)
    assert fp_palette.flat_regions(img) == []


def test_flat_regions_bo_qua_vung_qua_nho():
    img = _page()
    img[200:260, 100:200] = (200, 180, 120)      # ~0,4% trang < 2%
    assert fp_palette.flat_regions(img) == []


def test_flat_regions_bo_qua_giay_trang():
    """Trang trắng trơn không được sinh ra "hộp" nào (sat < SAT_FLOOR)."""
    assert fp_palette.flat_regions(_page()) == []


def test_flat_regions_lap_lai_duoc():
    img = _page()
    img[200:900, 100:800] = (210, 150, 90)
    a = fp_palette.flat_regions(img)
    b = fp_palette.flat_regions(img)
    assert a == b


# ------------------------------------------------- §2.4 ghép token nhãn hình

def _words(*texts):
    return [{"text": t, "conf": 90.0, "cx": 0.5, "cy": 0.8} for t in texts]


def test_caption_hits_ghep_hai_token():
    hits = fp_figure.caption_hits(_words("Hình", "1.2", "Sơ", "đồ"))
    assert [h["pattern"] for h in hits] == ["hinh_n_m"]
    assert hits[0]["text"] == "Hình 1.2"


def test_caption_hits_ghep_ba_token():
    hits = fp_figure.caption_hits(_words("Hình", "1", ".2"))
    assert [h["pattern"] for h in hits] == ["hinh_n_m"]


def test_caption_hits_phan_biet_hinh_n_voi_hinh_n_m():
    assert [h["pattern"] for h in fp_figure.caption_hits(_words("Hình", "5"))] \
        == ["hinh_n"]


def test_caption_hits_bat_bang_n_m():
    hits = fp_figure.caption_hits(_words("Bảng", "12.1", "Tính", "chất"))
    assert [h["pattern"] for h in hits] == ["bang_n_m"]


def test_caption_hits_khong_khop_chu_thuong_giua_cau():
    """"hình" trong câu ("có hình cầu") không phải nhãn -> không được đếm."""
    assert fp_figure.caption_hits(_words("có", "hình", "cầu")) == []


def test_caption_hits_giu_vi_tri_cua_token_dau():
    words = [{"text": "Hình", "conf": 88.0, "cx": 0.3, "cy": 0.72},
             {"text": "2.4", "conf": 91.0, "cx": 0.4, "cy": 0.72}]
    hits = fp_figure.caption_hits(words)
    assert hits[0]["cx"] == 0.3 and hits[0]["cy"] == 0.72


# ------------------------------ §2.1 hình dạng dòng mục lục theo từng nhà XB

def test_row_shape_kntt_bai():
    c = fp_toc.row_shape_counts("Bài 3: Quy định an toàn 15\nBài 4: Đo chiều dài 18")
    assert c["bai"] == 2 and c["toc_rows"] == 2


def test_row_shape_ctst_so_trang_la_rac_van_dem_duoc():
    """9_CTST: `Bài 2. Cơ năng ..... TŨ` — số trang OCR ra rác.

    Nếu mẫu `bai` đòi chữ số ở cuối dòng thì cả quyển CTST bị bỏ sót.
    """
    c = fp_toc.row_shape_counts("Bài 2. Cơ năng ............................... TŨ")
    assert c["bai"] == 1
    assert c["dot_leader"] == 1


def test_row_shape_cd_khong_co_chu_bai():
    """6_CD/9_CD: mục là `N. Tiêu đề <số trang>`, không có chữ "Bài"."""
    text = ("1. Giới thiệu về khoa học tự nhiên 4\n"
            "2. Một số dụng cụ đo và quy định an toàn 12\n"
            "3. Đo chiều dài, khối lượng và thời gian 19")
    c = fp_toc.row_shape_counts(text)
    assert c["so_thu_tu"] == 3 and c["bai"] == 0


def test_row_shape_khong_dem_danh_sach_trong_than_bai():
    """`1. Quan sát hình` không có số trang ở cuối -> không phải dòng mục lục."""
    c = fp_toc.row_shape_counts("1. Quan sát hình bên và trả lời câu hỏi")
    assert c["toc_rows"] == 0


def test_row_shape_chu_de():
    c = fp_toc.row_shape_counts("Chủ đề 2: Các phép đo 19")
    assert c["chu_de"] == 1


def test_row_shape_mot_dong_chi_dem_cho_mot_mau():
    """`Bài 3: ... 27` khớp cả `bai`; không được đếm thêm vào mẫu khác."""
    c = fp_toc.row_shape_counts("Bài 3: Quy định an toàn 27")
    assert c["bai"] + c["chu_de"] + c["so_thu_tu"] == 1


def test_entry_style_lay_mau_troi():
    assert fp_toc.entry_style_of({"bai": 40, "chu_de": 8, "so_thu_tu": 2}) == "bai"
    assert fp_toc.entry_style_of(
        {"bai": 0, "chu_de": 9, "so_thu_tu": 35}) == "so_thu_tu"


def test_entry_style_khong_dem_duoc_thi_None():
    assert fp_toc.entry_style_of({"bai": 0, "chu_de": 0, "so_thu_tu": 0}) is None


def test_scan_window_quet_ca_hai_dau():
    """CD in MỤC LỤC ở HAI TRANG CUỐI — quét chỉ đầu sách là mất sạch."""
    pages = list(range(1, 180))
    window = fp_toc.scan_window(pages, front=15, back=8)
    assert window[:15] == list(range(1, 16))
    assert 178 in window and 179 in window
    assert len(window) == len(set(window))


def test_scan_window_sach_ngan_khong_lap_trang():
    pages = list(range(1, 11))
    assert fp_toc.scan_window(pages, front=15, back=8) == pages
