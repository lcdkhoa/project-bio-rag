from langchain_core.documents import Document
from src.rag.citations import (
    format_book_name, build_citations, format_citations_block, is_fallback_answer,
)


def _doc(source="SGK KHTN 7 CTST.pdf", page=40, region_type="body", text="Nội dung."):
    return Document(page_content=text, metadata={
        "source": source, "page": page, "region_type": region_type})


def test_format_book_name_parenthesizes_publisher():
    assert format_book_name("SGK KHTN 7 CTST.pdf") == "SGK KHTN 7 (CTST)"
    assert format_book_name("SGK KHTN 8 KNTT.pdf") == "SGK KHTN 8 (KNTT)"


def test_body_citation_has_no_section():
    cits = build_citations([_doc()])
    assert cits[0]["display"] == "SGK KHTN 7 (CTST), tr. 40"
    assert cits[0]["section"] is None


def test_sidebar_section_extracted_from_first_line():
    d = _doc(region_type="sidebar", text="Em có biết?\nCá voi là thú.")
    cits = build_citations([d])
    assert cits[0]["display"] == 'SGK KHTN 7 (CTST), tr. 40 — mục "Em có biết"'


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
    assert "- SGK KHTN 7 (CTST), tr. 40" in block
    assert format_citations_block([]) == ""


def test_is_fallback_answer_matches_normalized():
    assert is_fallback_answer("Thông tin này không được đề cập trong sách giáo khoa.")
    assert is_fallback_answer("... KHÔNG ĐƯỢC ĐỀ CẬP ...")
    assert not is_fallback_answer("Quang hợp là quá trình...")
