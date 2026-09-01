"""Script reset luồng TEXT hạ cờ checkpoint, nên phải khoá bằng test.

Ba tính chất, tương tự `test_reset_image_books.py` nhưng cho phía text
(D-158: reset toàn bộ 12 quyển sau khi sửa `download_models.py`/notebook,
không dựa vào bump version một mình vì D-157 đã lật assumption đó):

1. **Đọc đúng chỗ.** Trạng thái checkpoint nằm trong `documents` (JSON), KHÔNG
   nằm trong `metadatas`.
2. **Không đụng luồng ảnh.** Chỉ `text_indexed`/`text_extraction_version` bị hạ;
   `image_extracted`/`image_extraction_version` phải giữ nguyên — ảnh đã xong
   12/12 quyển, dựng lại tốn 5-6 giờ.
3. **Không đụng quyển khác / thoát khác 0 khi tên sai / hỗ trợ `--all`.**
"""
import json

import pytest


def _lam_ban_ghi(book, page, text_indexed=True):
    return json.dumps({
        "page_key": f"{book}#hash{page}", "page_number": page,
        "pdf_filename": book, "text_indexed": text_indexed,
        "image_extracted": True,
        "image_extraction_version": "v19_pill_kernels",
        "text_extraction_version": "v3_formula_hybrid",
        "last_updated": "2026-08-31T00:00:00",
    })


def test_doc_trang_thai_tu_documents_khong_phai_metadatas():
    from src.etl.processing_status import ProcessingStatus  # noqa: F401
    import inspect

    from src.etl import processing_status as M
    src = inspect.getsource(M.ProcessingStatus.update_status)
    assert 'page_content=json.dumps(updated)' in src
    assert 'metadata={"page_key": page_key, "page": page_number}' in src


def test_ha_co_chi_dung_truong_text():
    """Mô phỏng đúng phép biến đổi script làm: chỉ trường TEXT đổi."""
    d = json.loads(_lam_ban_ghi("SGK_KHTN_6_KNTT", 10))
    moi = {**d, "text_indexed": False, "text_extraction_version": ""}
    assert moi["text_indexed"] is False
    assert moi["text_extraction_version"] == ""
    # KHÔNG được đụng ảnh
    assert moi["image_extracted"] is True
    assert moi["image_extraction_version"] == "v19_pill_kernels"
    assert moi["page_key"] == d["page_key"]
    assert moi["page_number"] == d["page_number"]
    assert moi["pdf_filename"] == d["pdf_filename"]


def test_chi_chon_dung_quyen_duoc_yeu_cau():
    chon = {"SGK_KHTN_6_KNTT", "SGK_KHTN_7_KNTT"}
    ban_ghi = [
        ("id1", _lam_ban_ghi("SGK_KHTN_6_KNTT", 1)),
        ("id2", _lam_ban_ghi("SGK_KHTN_6_CD", 1)),
        ("id3", _lam_ban_ghi("SGK_KHTN_7_KNTT", 1)),
        ("id4", _lam_ban_ghi("SGK_KHTN_9_CTST", 1)),
        # trang chưa từng chạy text -> không cần reset
        ("id5", _lam_ban_ghi("SGK_KHTN_6_KNTT", 2, text_indexed=False)),
    ]
    lay = [i for i, raw in ban_ghi
           if json.loads(raw).get("pdf_filename") in chon
           and json.loads(raw).get("text_indexed")]
    assert lay == ["id1", "id3"]


def _loc_theo_version(ban_ghi, chon, target_version, ignore_version):
    """Sao chép đúng phép lọc trong `main()` để test tách biệt khỏi chromadb thật."""
    ket_qua = []
    for i, raw in ban_ghi:
        d = json.loads(raw)
        if d.get("pdf_filename") not in chon or not d.get("text_indexed"):
            continue
        if not ignore_version and d.get("text_extraction_version") == target_version:
            continue
        ket_qua.append(i)
    return ket_qua


def test_mac_dinh_bo_qua_trang_da_dat_version_moi_resume_safe():
    """D-158: mặc định KHÔNG hạ cờ trang đã lên đúng version mới — nếu một
    phiên ETL dài bị ngắt giữa chừng và 5/12 quyển đã OCR lại đúng bằng code
    mới (đã lên version mới), chạy lại script không được xoá công đã làm."""
    chon = {"SGK_KHTN_6_KNTT"}
    ban_ghi = [
        # trang 1: van con version CU (tu luot truoc, phai reset)
        ("cu", json.dumps({
            "page_key": "k1", "page_number": 1, "pdf_filename": "SGK_KHTN_6_KNTT",
            "text_indexed": True, "text_extraction_version": "v3_formula_hybrid",
        })),
        # trang 2: DA duoc OCR lai dung trong phien nay (version MOI)
        ("da_xong_phien_nay", json.dumps({
            "page_key": "k2", "page_number": 2, "pdf_filename": "SGK_KHTN_6_KNTT",
            "text_indexed": True, "text_extraction_version": "v4_formula_hybrid_fix",
        })),
    ]
    # Mac dinh (khong ignore_version): CHI reset trang con version cu.
    assert _loc_theo_version(ban_ghi, chon, "v4_formula_hybrid_fix",
                             ignore_version=False) == ["cu"]
    # --ignore-version: reset CA HAI, bat ke version.
    assert _loc_theo_version(ban_ghi, chon, "v4_formula_hybrid_fix",
                             ignore_version=True) == ["cu", "da_xong_phien_nay"]


def test_ten_quyen_sai_thi_thoat_khac_0(monkeypatch, capsys):
    import sys

    from scripts import reset_text_all_books as R
    monkeypatch.setattr(R, "_quyen_tren_dia",
                        lambda: ["SGK_KHTN_6_KNTT", "SGK_KHTN_6_CD"])
    monkeypatch.setattr(sys, "argv",
                        ["reset", "--book", "SGK_KHTN_6_KNT"])   # thiếu chữ T
    assert R.main() == 2
    assert "không có trên đĩa" in capsys.readouterr().out


def test_khong_chon_gi_cung_thoat_khac_0(monkeypatch, capsys):
    import sys

    from scripts import reset_text_all_books as R
    monkeypatch.setattr(R, "_quyen_tren_dia", lambda: ["SGK_KHTN_6_KNTT"])
    monkeypatch.setattr(sys, "argv", ["reset"])
    assert R.main() == 2
    assert "Chưa chọn quyển nào" in capsys.readouterr().out


def test_all_chon_moi_quyen_tren_dia():
    """`--all` phải hợp nhất với TOÀN BỘ quyển có trên đĩa, không chỉ --book/--nxb.

    Test logic hợp nhất thuần tuý (không gọi `main()`) để không chạm chromadb
    thật ở `PERSIST_DIR` — `reset_image_books.py` cũng không test đường main()
    đầy đủ vì lý do này.
    """
    tren_dia = ["SGK_KHTN_6_KNTT", "SGK_KHTN_6_CD", "SGK_KHTN_7_CTST"]

    def _hop_nhat(book=(), nxb="", chon_all=False):
        chon = list(book)
        if nxb:
            chon += [b for b in tren_dia if b.upper().endswith("_" + nxb.upper())]
        if chon_all:
            chon += tren_dia
        return sorted(set(chon))

    assert _hop_nhat(chon_all=True) == sorted(tren_dia)
    assert _hop_nhat(book=["SGK_KHTN_6_KNTT"]) == ["SGK_KHTN_6_KNTT"]
    assert _hop_nhat(nxb="CD") == ["SGK_KHTN_6_CD"]


@pytest.mark.parametrize("nxb,mong_doi", [
    ("CTST", {"SGK_KHTN_6_CTST", "SGK_KHTN_7_CTST"}),
    ("CD", {"SGK_KHTN_6_CD"}),
    ("ctst", {"SGK_KHTN_6_CTST", "SGK_KHTN_7_CTST"}),   # hoa thường không đổi
])
def test_loc_theo_nxb_khop_hau_to_o_CUOI(nxb, mong_doi):
    tren_dia = ["SGK_KHTN_6_CTST", "SGK_KHTN_7_CTST", "SGK_KHTN_6_CD",
                "CD_SGK_KHTN_9", "SGK_KHTN_6_CDX"]
    chon = {b for b in tren_dia if b.upper().endswith("_" + nxb.upper())}
    assert chon == mong_doi
