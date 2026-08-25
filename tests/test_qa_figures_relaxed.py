"""G4 phải nói ra khi nó KHÔNG kiểm được, thay vì in một con số đọc như đã đạt.

Đây là bài học D-96 đem sang cổng hình: ở bake-off OCR, một engine mới chạy 3/97
ô cho `DẤU = 0,000` — điểm HOÀN HẢO ở đúng cột quyết định thắng/thua, chỉ vì
thiếu dữ liệu. Cổng G4 có hai chỗ hỏng y hệt:

1. Quyển chưa có spine đáng tin: `Hình 7.4` nằm trên trang manifest ghi `Bài 6`
   có thể là crop gán sai, mà cũng có thể là manifest ghi sai — không quy được.
2. Mẫu là trang RỜI: `Hình 8.3` đứng một mình làm `max(B) = 3`, và phép "B liên
   tục 1..max" báo thiếu `1, 2` dù chẳng có hình nào bị bỏ sót.
"""
from src.test import qa_figures as Q


class _Source:
    name = "SGK_KHTN_6_CTST"


class _Manifest:
    def __init__(self, pages, flags):
        self.pages = pages
        self.flags = flags


def _ket_qua(spine_tin_duoc, chon_theo="bai", misassigned=1, gaps=None):
    return {
        "spine_tin_duoc": spine_tin_duoc,
        "co_spine": [] if spine_tin_duoc else ["bai_numbers_not_contiguous"],
        "chon_theo": chon_theo,
        "found": {4: [1, 2, 3]},
        "gaps": gaps if gaps is not None else {5: [1, 3]},
        "misassigned": [{"page": 32, "page_bai": 6, "label": "Hình 7.4"}] * misassigned,
        "unlabelled": 0, "rows": [], "oversized": [], "crop_stats": [(0.1, 0.0)],
        "pages_scanned": 6, "pages_with_bai": 6,
    }


def test_spine_dang_tin_thi_bao_cao_khong_doi():
    """Không được làm KNTT (spine sạch) đọc khác đi."""
    txt = Q.report("SGK_KHTN_6_KNTT", _ket_qua(True))
    assert "=== G4 SGK_KHTN_6_KNTT" in txt
    assert "gán SAI Bài" in txt
    assert "SPINE CHƯA TIN ĐƯỢC" not in txt


def test_spine_khong_tin_thi_KHONG_goi_do_la_gan_sai():
    """Con số vẫn in ra, nhưng KHÔNG được gọi tên là 'gán SAI Bài'."""
    txt = Q.report("SGK_KHTN_6_CTST", _ket_qua(False))
    assert "SPINE CHƯA TIN ĐƯỢC" in txt
    assert "KHÔNG quy được lỗi cho ai" in txt
    assert "  gán SAI Bài" not in txt
    assert "bai_numbers_not_contiguous" in txt
    assert "QA bằng MẮT" in txt


def test_mau_trang_roi_thi_so_THIEU_bi_danh_dau_la_khong_doc_duoc():
    txt = Q.report("SGK_KHTN_6_CD", _ket_qua(False, chon_theo="trang_mau"))
    assert "thiếu                 : KHÔNG ĐỌC ĐƯỢC" in txt
    assert "thiếu (cận dưới)" not in txt


def test_chon_theo_bai_van_giu_nguyen_cach_doc_can_duoi():
    txt = Q.report("SGK_KHTN_6_KNTT", _ket_qua(True, chon_theo="bai"))
    assert "thiếu (cận dưới)      : 2" in txt


def test_scan_doc_co_spine_tu_CHINH_manifest(monkeypatch):
    """Độ tin phải lấy từ cờ manifest, dùng đúng hằng số của đường text."""
    monkeypatch.setattr(Q, "make_image_processor", lambda name: object())
    monkeypatch.setattr(Q, "page_regions",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bỏ qua")))
    man = _Manifest(pages=[{"page_index": 10, "bai_so": 1}],
                    flags=[{"kind": "bai_numbers_not_contiguous"},
                           {"kind": "page_number_not_read"}])
    r = Q.scan(_Source(), man, [10])
    assert r["spine_tin_duoc"] is False
    # chỉ cờ SPINE mới hạ độ tin — `page_number_not_read` thì không
    assert r["co_spine"] == ["bai_numbers_not_contiguous"]

    sach = _Manifest(pages=[{"page_index": 10, "bai_so": 1}],
                     flags=[{"kind": "page_number_not_read"}])
    assert Q.scan(_Source(), sach, [10])["spine_tin_duoc"] is True
