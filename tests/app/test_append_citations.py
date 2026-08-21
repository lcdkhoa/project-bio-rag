from langchain_core.documents import Document
from src.rag.citations import build_citations
from src.app.api import append_citations


def _cits():
    return build_citations([Document(page_content="x", metadata={
        "source": "SGK_KHTN_7_KNTT", "page": 40, "region_type": "body"})])


def test_appends_sources_block():
    out = append_citations("Quang hợp là quá trình.", _cits())
    assert "📚 Nguồn:" in out
    assert "Khoa học tự nhiên 7 (Kết nối tri thức), tr. 40" in out


def test_suppressed_on_fallback_answer():
    out = append_citations("Thông tin này không được đề cập trong sách giáo khoa.", _cits())
    assert "Nguồn" not in out


def test_no_citations_returns_answer_unchanged():
    assert append_citations("Bất kỳ.", []) == "Bất kỳ."
