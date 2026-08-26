"""Nhánh dự phòng của `_build_uncovered_caption_regions` không được dựng dải dọc hẹp.

Bối cảnh đo được (D-125, D-126): khi không tìm được vùng ảnh nào cho một chú thích,
code dựng khung cắt từ CHÍNH chú thích. Chú thích của KNTT là một pill nhỏ
(`Hình 1.1` rộng ~96 px) nên ra một dải dọc ~124 px cắt ngang giữa hình ghép — 17,5%
crop của KNTT rơi vào lớp lỗi này, so với 4,8% của Cánh Diều (chú thích là dòng chữ
dài). Sàn chiều rộng nay lấy theo TRANG.
"""

from src.etl.image_processor import ImageProcessor

W, H = 1094, 1536
PILL = (500, 1000, 596, 1030)          # `Hình 1.1` kiểu KNTT: rộng 96 px
CAPTION_DAI = (200, 1000, 900, 1030)   # chú thích kiểu CD/CTST: rộng 700 px


def _chay(caption_bbox):
    """Gọi thẳng nhánh dự phòng: không có vùng ảnh nào, không có dòng chữ nào."""
    return ImageProcessor()._build_uncovered_caption_regions(
        uncovered_caps=[{"bbox": caption_bbox, "text": "Hình 1.1 Ví dụ"}],
        visual_regions=[],
        existing_regions=[],
        text_lines=[],
        exclusion_zones=[],
        page_width=W,
        page_height=H,
    )


def _la_dai_doc_hep(bbox):
    """Định nghĩa của D-125: rộng < 20% trang VÀ cao > 1,5 lần rộng."""
    rong = bbox[2] - bbox[0]
    cao = bbox[3] - bbox[1]
    return rong < W * 0.20 and cao > 1.5 * rong


def test_pill_nho_khong_con_sinh_ra_dai_doc_hep():
    ra = _chay(PILL)
    assert len(ra) == 1
    assert not _la_dai_doc_hep(ra[0]["bbox"]), ra[0]["bbox"]


def test_san_chieu_rong_tinh_theo_trang_chu_khong_theo_chu_thich():
    rong_pill = _chay(PILL)[0]["bbox"]
    rong_pill = rong_pill[2] - rong_pill[0]
    # Sàn 0,32 x trang, nới 15% mỗi bên quanh chú thích -> phải rộng hơn hẳn
    # bề rộng của chính cái pill (96 px).
    assert rong_pill > 96 * 1.5


def test_chu_thich_dai_khong_bi_bop_lai():
    """Sàn chỉ được NÂNG bề rộng, không được hạ — CD/CTST phải giữ nguyên."""
    bbox = _chay(CAPTION_DAI)[0]["bbox"]
    rong = bbox[2] - bbox[0]
    assert rong >= (CAPTION_DAI[2] - CAPTION_DAI[0])


def test_khung_van_om_tron_chu_thich():
    """Nới rộng mà làm hụt mất chính chú thích thì là đổi lỗi này lấy lỗi khác."""
    bbox = _chay(PILL)[0]["bbox"]
    assert bbox[0] <= PILL[0] and bbox[2] >= PILL[2]
    assert bbox[1] <= PILL[1] and bbox[3] >= PILL[3]
