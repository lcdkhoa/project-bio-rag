from langchain_core.documents import Document
from src.rag.citations import (
    format_book_name, build_citations, format_citations_block, is_fallback_answer,
)


def _doc(source="SGK_KHTN_7_KNTT", page=40, region_type="body", text="Nội dung."):
    return Document(page_content=text, metadata={
        "source": source, "page": page, "region_type": region_type})


def test_format_book_name_is_readable_by_a_student():
    """Trích dẫn hiện ra trước mắt học sinh, nên không được là tên thư mục.

    Trước: `SGK_KHTN_6_KNTT` -> `"SGK_KHTN_6 (KNTT)"`.
    """
    assert format_book_name("SGK_KHTN_6_KNTT") ==         "Khoa học tự nhiên 6 (Kết nối tri thức)"
    assert format_book_name("SGK KHTN 8 KNTT.pdf") ==         "Khoa học tự nhiên 8 (Kết nối tri thức)"


def test_format_book_name_dich_du_ba_nha_xuat_ban():
    """Kho là 12 quyển / 3 bộ sách, nên nhãn phải đọc được ở cả ba.

    Dòng cũ ở đây khẳng định `SGK_KHTN_6_CTST` trả về NGUYÊN VĂN — nó khoá lại
    đúng khuyết điểm chứ không phải đặc tả: bảng nhà xuất bản khi ấy chỉ có
    `KNTT`, nên 8/12 quyển hiện ra trước mắt học sinh đúng tên thư mục. Đo trên
    server thật ngày 2026-08-26, một câu hỏi cho ra 2/3 trích dẫn dạng
    `SGK_KHTN_7_CD`.
    """
    assert format_book_name("SGK_KHTN_6_CTST") == "Khoa học tự nhiên 6 (Chân trời sáng tạo)"
    assert format_book_name("SGK_KHTN_6_CD") == "Khoa học tự nhiên 6 (Cánh Diều)"
    assert format_book_name("SGK_KHTN_6_KNTT") == "Khoa học tự nhiên 6 (Kết nối tri thức)"


def test_format_book_name_never_guesses_an_unknown_book():
    """Không khớp khuôn thì trả nguyên văn — nhãn sai là chỉ học sinh sai quyển."""
    assert format_book_name("SGK_KHTN_6_XYZ") == "SGK_KHTN_6_XYZ"
    assert format_book_name("mot quyen la.pdf") == "mot quyen la"
    assert format_book_name("") == "Sách giáo khoa"


def test_format_book_name_round_trips_for_the_g3_lookup():
    """Cổng G3 map nhãn hiển thị NGƯỢC về `source`; nhãn phải là song ánh."""
    sources = [f"SGK_KHTN_{grade}_{pub}"
               for grade in (6, 7, 8, 9)
               for pub in ("KNTT", "CTST", "CD")]
    labels = [format_book_name(s) for s in sources]
    assert len(set(labels)) == len(sources)


def test_body_citation_has_no_section():
    cits = build_citations([_doc()])
    assert cits[0]["display"] == "Khoa học tự nhiên 7 (Kết nối tri thức), tr. 40"
    assert cits[0]["section"] is None


def test_sidebar_section_extracted_from_first_line():
    d = _doc(region_type="sidebar", text="Em có biết?\nCá voi là thú.")
    cits = build_citations([d])
    assert cits[0]["display"] == (
        'Khoa học tự nhiên 7 (Kết nối tri thức), tr. 40 — mục "Em có biết"')


def test_sidebar_generic_label_when_no_keyword():
    d = _doc(region_type="info_box", text="Một đoạn bất kỳ không có tiêu đề.")
    cits = build_citations([d])
    assert cits[0]["display"].endswith('— mục "khung thông tin"')


def test_dedup_same_book_page_section():
    cits = build_citations([_doc(), _doc(), _doc(page=12)])
    assert len(cits) == 2
    assert [c["page"] for c in cits] == [12, 40]      # sorted by (book, page)


def test_format_block_and_empty():
    cits = build_citations([_doc()])
    block = format_citations_block(cits)
    assert block.startswith("📚 Nguồn:")
    assert "- Khoa học tự nhiên 7 (Kết nối tri thức), tr. 40" in block
    assert format_citations_block([]) == ""


def test_is_fallback_answer_matches_normalized():
    assert is_fallback_answer("Thông tin này không được đề cập trong sách giáo khoa.")
    assert is_fallback_answer("... KHÔNG ĐƯỢC ĐỀ CẬP ...")
    assert not is_fallback_answer("Quang hợp là quá trình...")
