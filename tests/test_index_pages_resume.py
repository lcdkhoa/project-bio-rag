"""Regression test: resume chỉ index đúng những trang còn thiếu text, với id
chunk tất định theo *nội dung trang* (nên add lại là upsert, không nhân bản).

Bug bị khoá lại ở đây: bản trước gọi `loader.load_pdf(pdf_file)` (cả quyển) rồi
`text_db.add_documents(docs)` vô điều kiện, kể cả khi `pages_to_index` chỉ là một
tập nhỏ (resume sau khi crash). Nó re-OCR cả quyển và add lại chunk của những
trang đã index với UUID mới -> dòng trùng, lớn dần mỗi lần resume.

Thêm sau khi đổi nguồn PNG: trang được gọi theo **số trang nguồn** (số trong tên
file), không qua bất kỳ phép `-1`/`+1` nào, và chunk cũ của trang bị xoá trước
khi ghi bản mới.
"""
from types import SimpleNamespace

from main import _index_source_pages
from src.config import TEXT_EXTRACTION_VERSION


class FakeDoc:
    def __init__(self, chunk_index):
        self.metadata = {"chunk_index": chunk_index}


class FakeSource:
    name = "SGK_KHTN_8_KNTT"

    def page_numbers(self):
        return [1, 2, 3, 4, 5, 6]

    def content_hash(self, page_number):
        return f"h{page_number}"


class FakeLoader:
    """Ghi lại các SỐ TRANG NGUỒN mà load_page được gọi với."""

    def __init__(self):
        self.calls = []

    def load_page(self, source, page_number):
        self.calls.append(page_number)
        return [FakeDoc(chunk_index=0)]


class FakeTextDB:
    def __init__(self):
        self.add_calls = []
        self.deletes = []

    def add_documents(self, docs, ids=None):
        self.add_calls.append((docs, ids))

    def delete(self, where=None):
        self.deletes.append(where)


class FakeStatusTracker:
    def __init__(self):
        self.marked = []

    def mark_text_indexed(self, page_key, page_number, filename,
                          text_extraction_version=None):
        self.marked.append((page_key, page_number, filename,
                            text_extraction_version))


def test_only_needed_pages_are_loaded_with_deterministic_ids():
    loader, text_db, status = FakeLoader(), FakeTextDB(), FakeStatusTracker()
    source = FakeSource()
    pages_to_index = [2, 5]

    _index_source_pages(loader, text_db, status, source, pages_to_index)

    # (a) load_page gọi ĐÚNG các số trang nguồn cần làm — không lệch 1, không cả quyển
    assert loader.calls == [2, 5]

    # (b) id là dạng tất định {tên quyển}#{hash trang}_p{trang}_c{idx}
    assert len(text_db.add_calls) == 2
    for (docs, ids), page_number in zip(text_db.add_calls, pages_to_index):
        assert ids == [f"SGK_KHTN_8_KNTT#h{page_number}_p{page_number}_c0"]
        assert len(docs) == 1

    # (c) chunk cũ của đúng trang đó bị xoá trước khi ghi bản mới
    assert text_db.deletes == [
        {"$and": [{"source": {"$eq": "SGK_KHTN_8_KNTT"}},
                  {"page_index": {"$eq": page}}]}
        for page in pages_to_index]

    # (d) mark một lần cho mỗi trang, kèm version đang dùng
    assert [(p, v) for _, p, _, v in status.marked] == [
        (2, TEXT_EXTRACTION_VERSION), (5, TEXT_EXTRACTION_VERSION)]


def test_page_with_no_docs_still_gets_marked():
    loader = SimpleNamespace(load_page=lambda source, page_number: [])
    text_db, status = FakeTextDB(), FakeStatusTracker()

    _index_source_pages(loader, text_db, status, FakeSource(), [3])

    assert text_db.add_calls == []
    assert [p for _, p, _, _ in status.marked] == [3]


def test_failing_page_is_skipped_and_left_unmarked():
    """Một trang lỗi không được giết phần còn lại của quyển.

    `--etl` dùng chung helper này; nếu exception thoát ra đây thì nó giết cả
    quyển (text VÀ hình). Trang lỗi cũng phải ở lại chưa mark để lần sau làm lại.
    """
    class FlakyLoader:
        def __init__(self):
            self.calls = []

        def load_page(self, source, page_number):
            self.calls.append(page_number)
            if page_number == 4:
                raise RuntimeError("tesseract blew up on this page")
            return [FakeDoc(chunk_index=0)]

    loader, text_db, status = FlakyLoader(), FakeTextDB(), FakeStatusTracker()

    _index_source_pages(loader, text_db, status, FakeSource(), [2, 4, 6])

    assert loader.calls == [2, 4, 6], "must keep going after the failing page"
    assert [p for _, p, _, _ in status.marked] == [2, 6], \
        "failed page must stay unmarked so it is retried"
