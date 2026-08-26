# -*- coding: utf-8 -*-
"""Hình dạng phản hồi của API — thứ mà giao diện web thực sự đọc.

Ba khiếm khuyết được khoá lại ở đây, cả ba đều đo được trên server thật ngày
2026-08-26 trước khi sửa:

1. `image_path` trả ra là đường dẫn TUYỆT ĐỐI của máy đã chạy ETL
   (`D:\\personal_repo\\...`), nên trình duyệt không tải nổi một hình nào.
2. Không có trường `citations`: trích dẫn xác định bị chèn vào giữa `answer`
   dưới dạng chữ, nên giao diện muốn hiện tử tế thì phải đi cắt chuỗi tiếng Việt
   — và trên thực tế đã không làm.
3. `format_book_name` chỉ dịch được `KNTT`, nên 8/12 quyển hiện ra trước mắt học
   sinh đúng tên thư mục. Ngay câu hỏi thử đầu tiên đã dính 2/3 trích dẫn.
"""
from __future__ import annotations

import pytest
from langchain_core.documents import Document

from src.app.api import build_gallery_items, chat_response_body, image_url_for
from src.config import IMAGES_DIR
from src.rag.citations import format_book_name


class TestImageUrlFor:
    def test_duong_dan_tuyet_doi_windows_thanh_url(self):
        raw = r"D:\personal_repo\project_rag\database\images\SGK_KHTN_7_CTST\page_108_img_0.png"
        assert image_url_for(raw) == "/images/SGK_KHTN_7_CTST/page_108_img_0.png"

    def test_duong_dan_tuyet_doi_posix_thanh_url(self):
        raw = "/content/drive/MyDrive/rag/database/images/SGK_KHTN_6_CD/page_3_img_0.png"
        assert image_url_for(raw) == "/images/SGK_KHTN_6_CD/page_3_img_0.png"

    def test_duoi_images_dir_that_van_quy_duoc(self):
        """Không có chuỗi `/database/images/` thì vẫn quy được theo IMAGES_DIR."""
        duong = IMAGES_DIR / "SGK_KHTN_8_KNTT" / "page_6_img_0.png"
        assert image_url_for(str(duong)) == "/images/SGK_KHTN_8_KNTT/page_6_img_0.png"

    def test_url_san_thi_giu_nguyen(self):
        assert image_url_for("/images/a/b.png") == "/images/a/b.png"

    @pytest.mark.parametrize("raw", ["", None, "   "])
    def test_rong_thi_tra_rong(self, raw):
        assert image_url_for(raw) == ""

    def test_khong_quy_duoc_thi_tra_RONG_chu_khong_doan(self):
        """Thà một `<img>` hỏng còn hơn một đường dẫn trỏ sang ảnh của bài khác."""
        assert image_url_for(r"C:\somewhere\else\anh.png") == ""


class TestBuildGalleryItems:
    def _doc(self, **metadata):
        base = {
            "image_path": r"D:\repo\database\images\SGK_KHTN_7_CTST\page_108_img_0.png",
            "page_number": 108,
            "pdf_filename": "SGK_KHTN_7_CTST",
            "figure_label": "Hình 23.1",
            "figure_caption": "Sơ đồ mô tả quá trình quang hợp",
        }
        base.update(metadata)
        return Document(page_content="", metadata=base)

    def test_tra_url_tuong_doi_khong_lo_duong_dan_may_chu(self):
        item = build_gallery_items([self._doc()])[0]
        assert item["image_url"] == "/images/SGK_KHTN_7_CTST/page_108_img_0.png"
        # Tên cũ giữ nguyên để giao diện cũ không gãy, nhưng KHÔNG còn là đường
        # dẫn tuyệt đối.
        assert item["image_path"] == item["image_url"]
        assert "D:" not in item["image_path"]

    def test_kem_truong_de_hien_chu_thich_khong_phai_cat_chuoi(self):
        item = build_gallery_items([self._doc()])[0]
        assert item["figure_label"] == "Hình 23.1"
        assert item["page"] == 108
        assert item["book"] == "Khoa học tự nhiên 7 (Chân trời sáng tạo)"


class TestChatResponseBody:
    CITATIONS = [
        {"book": "Khoa học tự nhiên 7 (Cánh Diều)", "page": 91, "section": None,
         "display": "Khoa học tự nhiên 7 (Cánh Diều), tr. 91"},
    ]

    def test_co_du_ba_truong(self):
        body = chat_response_body("Quang hợp là...", self.CITATIONS, [])
        assert set(body) == {"answer", "answer_text", "citations", "images"}

    def test_answer_text_KHONG_kem_khoi_nguon(self):
        body = chat_response_body("Quang hợp là...", self.CITATIONS, [])
        assert body["answer_text"] == "Quang hợp là..."
        assert "📚" not in body["answer_text"]

    def test_answer_VAN_kem_khoi_nguon_de_khong_pha_phia_goi_cu(self):
        body = chat_response_body("Quang hợp là...", self.CITATIONS, [])
        assert "📚 Nguồn:" in body["answer"]
        assert "tr. 91" in body["answer"]

    def test_khong_co_nguon_thi_citations_la_mang_rong_khong_phai_None(self):
        body = chat_response_body("Không biết.", None, [])
        assert body["citations"] == []


class TestFormatBookName:
    """Nhãn sách phải đọc được với CẢ BA nhà xuất bản, không chỉ Kết nối tri thức."""

    @pytest.mark.parametrize("source,mong_doi", [
        ("SGK_KHTN_7_KNTT", "Khoa học tự nhiên 7 (Kết nối tri thức)"),
        ("SGK_KHTN_7_CTST", "Khoa học tự nhiên 7 (Chân trời sáng tạo)"),
        ("SGK_KHTN_7_CD", "Khoa học tự nhiên 7 (Cánh Diều)"),
        ("SGK_KHTN_9_CD", "Khoa học tự nhiên 9 (Cánh Diều)"),
    ])
    def test_ba_nha_xuat_ban(self, source, mong_doi):
        assert format_book_name(source) == mong_doi

    def test_ten_la_thi_tra_NGUYEN_VAN_khong_doan(self):
        assert format_book_name("SGK_KHTN_7_XYZ") == "SGK_KHTN_7_XYZ"

    def test_nhan_la_song_anh_moi_quyen_mot_nhan_khac_nhau(self):
        """Cổng G3 ánh xạ nhãn hiển thị NGƯỢC về `source`, nên nhãn phải phân biệt được."""
        sach = [f"SGK_KHTN_{k}_{nxb}"
                for k in (6, 7, 8, 9) for nxb in ("KNTT", "CTST", "CD")]
        nhan = [format_book_name(s) for s in sach]
        assert len(set(nhan)) == len(sach)
