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


def test_format_book_name_never_guesses_an_unknown_book():
    """Không khớp khuôn thì trả nguyên văn — nhãn sai là chỉ học sinh sai quyển."""
    assert format_book_name("SGK_KHTN_6_CTST") == "SGK_KHTN_6_CTST"
    assert format_book_name("mot quyen la.pdf") == "mot quyen la"
    assert format_book_name("") == "Sách giáo khoa"


def test_format_book_name_round_trips_for_the_g3_lookup():
    """Cổng G3 map nhãn hiển thị NGƯỢC về `source`; nhãn phải là song ánh."""
    sources = ["SGK_KHTN_6_KNTT", "SGK_KHTN_7_KNTT",
               "SGK_KHTN_8_KNTT", "SGK_KHTN_9_KNTT"]
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
