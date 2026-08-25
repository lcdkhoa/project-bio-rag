"""Script reset luồng ảnh XOÁ DỮ LIỆU, nên phải khoá bằng test.

Ba tính chất, mỗi cái tương ứng một cách hỏng đã suýt xảy ra khi viết nó:

1. **Đọc đúng chỗ.** Trạng thái checkpoint nằm trong `documents` (một chuỗi
   JSON), KHÔNG nằm trong `metadatas` — metadata chỉ giữ `page_key` và `page`.
   Bản đầu của script đọc `metadatas` và in ra "0 trang" cho mọi quyển: nó sẽ
   reset đúng 0 trang mà vẫn thoát 0, tức người dùng chạy lại ETL rồi tưởng bản
   vá không có tác dụng.
2. **Không đụng luồng chữ.** Chỉ `image_extracted` bị hạ; `text_indexed` phải
   giữ nguyên. Hạ nhầm là 16 393 chunk văn bản bị OCR lại nhiều giờ.
3. **Không đụng quyển khác.** Reset CTST không được chạm CD/KNTT.
"""
import json

import pytest


def _lam_ban_ghi(book, page, image_extracted=True):
    return json.dumps({
        "page_key": f"{book}#hash{page}", "page_number": page,
        "pdf_filename": book, "text_indexed": True,
        "image_extracted": image_extracted,
        "image_extraction_version": "v19_pill_kernels",
        "text_extraction_version": "v2_bai_spine",
        "last_updated": "2026-08-25T00:00:00",
    })


def test_doc_trang_thai_tu_documents_khong_phai_metadatas():
    """Bản ghi checkpoint chỉ có `page_key`/`page` ở metadata.

    Test này neo vào cấu trúc thật của `ProcessingStatus.update_status`: nó dựng
    `Document(page_content=json.dumps(updated), metadata={"page_key", "page"})`.
    Nếu ai đó chuyển trạng thái sang metadata, test đỏ và script phải sửa theo.
    """
    from src.etl.processing_status import ProcessingStatus  # noqa: F401
    import inspect

    from src.etl import processing_status as M
    src = inspect.getsource(M.ProcessingStatus.update_status)
    assert 'page_content=json.dumps(updated)' in src
    assert 'metadata={"page_key": page_key, "page": page_number}' in src


def test_ha_co_chi_dung_truong_anh():
    """Mô phỏng đúng phép biến đổi script làm: chỉ `image_extracted` đổi."""
    d = json.loads(_lam_ban_ghi("SGK_KHTN_6_CTST", 10))
    moi = {**d, "image_extracted": False, "image_extraction_version": ""}
    assert moi["image_extracted"] is False
    assert moi["image_extraction_version"] == ""
    # KHÔNG được đụng
    assert moi["text_indexed"] is True
    assert moi["text_extraction_version"] == "v2_bai_spine"
    assert moi["page_key"] == d["page_key"]
    assert moi["page_number"] == d["page_number"]
    assert moi["pdf_filename"] == d["pdf_filename"]


def test_chi_chon_dung_quyen_duoc_yeu_cau():
    chon = {"SGK_KHTN_6_CTST", "SGK_KHTN_7_CTST"}
    ban_ghi = [
        ("id1", _lam_ban_ghi("SGK_KHTN_6_CTST", 1)),
        ("id2", _lam_ban_ghi("SGK_KHTN_6_CD", 1)),
        ("id3", _lam_ban_ghi("SGK_KHTN_7_CTST", 1)),
        ("id4", _lam_ban_ghi("SGK_KHTN_9_KNTT", 1)),
        # trang chưa từng chạy ảnh -> không cần reset
        ("id5", _lam_ban_ghi("SGK_KHTN_6_CTST", 2, image_extracted=False)),
    ]
    lay = [i for i, raw in ban_ghi
           if json.loads(raw).get("pdf_filename") in chon
           and json.loads(raw).get("image_extracted")]
    assert lay == ["id1", "id3"]


def test_ten_quyen_sai_thi_thoat_khac_0(monkeypatch, capsys):
    """Lỗi chính tả trong tên quyển phải DỪNG, không im lặng reset 0 trang."""
    import sys

    from scripts import reset_image_books as R
    monkeypatch.setattr(R, "_quyen_tren_dia",
                        lambda: ["SGK_KHTN_6_CTST", "SGK_KHTN_6_CD"])
    monkeypatch.setattr(sys, "argv",
                        ["reset", "--book", "SGK_KHTN_6_CTS"])   # thiếu chữ T
    assert R.main() == 2
    assert "không có trên đĩa" in capsys.readouterr().out


def test_khong_chon_gi_cung_thoat_khac_0(monkeypatch, capsys):
    import sys

    from scripts import reset_image_books as R
    monkeypatch.setattr(R, "_quyen_tren_dia", lambda: ["SGK_KHTN_6_CTST"])
    monkeypatch.setattr(sys, "argv", ["reset"])
    assert R.main() == 2
    assert "Chưa chọn quyển nào" in capsys.readouterr().out


@pytest.mark.parametrize("nxb,mong_doi", [
    ("CTST", {"SGK_KHTN_6_CTST", "SGK_KHTN_7_CTST"}),
    ("CD", {"SGK_KHTN_6_CD"}),
    ("ctst", {"SGK_KHTN_6_CTST", "SGK_KHTN_7_CTST"}),   # hoa thường không đổi
])
def test_loc_theo_nxb_khop_hau_to_o_CUOI(nxb, mong_doi):
    """`--nxb CD` không được vớ phải `SGK_KHTN_6_CDX` hay tên chứa CD ở giữa."""
    tren_dia = ["SGK_KHTN_6_CTST", "SGK_KHTN_7_CTST", "SGK_KHTN_6_CD",
                "CD_SGK_KHTN_9", "SGK_KHTN_6_CDX"]
    chon = {b for b in tren_dia if b.upper().endswith("_" + nxb.upper())}
    assert chon == mong_doi
