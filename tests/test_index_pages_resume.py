"""Regression test: resume must index ONLY the pages that still need text,
using deterministic per-page-per-chunk ids (so a re-add upserts instead of
duplicating rows in Chroma).

Bug this locks down: the previous implementation called
`loader.load_pdf(pdf_file)` (whole book) then `text_db.add_documents(docs)`
unconditionally, even when `pages_to_index` was a small subset (partial
resume after a crash/disconnect). That re-OCR'd the whole book and re-added
chunks for already-indexed pages with fresh UUIDs -> literal duplicate rows
that grow on every resume.
"""
from types import SimpleNamespace

from main import _index_pdf_pages


class FakeDoc:
    def __init__(self, chunk_index):
        self.metadata = {"chunk_index": chunk_index}


class FakeLoader:
    """Records which 0-based page indices load_page was called with."""

    def __init__(self):
        self.calls = []

    def load_page(self, pdf_file, index):
        self.calls.append(index)
        # one fake Document per page, chunk_index=0
        return [FakeDoc(chunk_index=0)]


class FakeTextDB:
    """Records add_documents calls (docs + ids)."""

    def __init__(self):
        self.add_calls = []

    def add_documents(self, docs, ids=None):
        self.add_calls.append((docs, ids))


class FakeStatusTracker:
    """Records mark_text_indexed calls."""

    def __init__(self):
        self.marked = []

    def mark_text_indexed(self, pdf_hash, page_num, filename):
        self.marked.append((pdf_hash, page_num, filename))


def test_only_needed_pages_are_loaded_with_deterministic_ids():
    loader = FakeLoader()
    text_db = FakeTextDB()
    status_tracker = FakeStatusTracker()
    pdf_hash = "deadbeef"
    filename = "SGK KHTN8 KNTT.pdf"
    pages_to_index = [2, 5]

    _index_pdf_pages(loader, text_db, status_tracker, "some.pdf", pdf_hash,
                      filename, pages_to_index)

    # (a) load_page called EXACTLY for the needed pages, converted to 0-based,
    # and NOT for the whole book.
    assert loader.calls == [1, 4]

    # (b) ids passed to add_documents are the deterministic {hash}_p{page}_c{idx} form
    assert len(text_db.add_calls) == 2
    for (docs, ids), page_num in zip(text_db.add_calls, pages_to_index):
        assert ids == [f"{pdf_hash}_p{page_num}_c0"]
        assert len(docs) == 1

    # (c) mark_text_indexed called once per page_num
    assert status_tracker.marked == [
        (pdf_hash, 2, filename),
        (pdf_hash, 5, filename),
    ]


def test_page_with_no_docs_still_gets_marked():
    loader = SimpleNamespace(load_page=lambda pdf_file, index: [])
    text_db = FakeTextDB()
    status_tracker = FakeStatusTracker()

    _index_pdf_pages(loader, text_db, status_tracker, "some.pdf", "h",
                      "f.pdf", [3])

    assert text_db.add_calls == []
    assert status_tracker.marked == [("h", 3, "f.pdf")]


def test_failing_page_is_skipped_and_left_unmarked():
    """One bad page must not abort the rest of the book.

    --etl now shares this helper with --text-only. The old --etl path swallowed
    OCR errors inside RobustOCRLoader.load_pdf, so a mid-book failure still let
    the image side run; if the exception escapes here instead, it kills the
    whole book (text AND figures). The failing page must also stay unmarked so
    the next run retries it.
    """
    class FlakyLoader:
        def __init__(self):
            self.calls = []

        def load_page(self, pdf_file, index):
            self.calls.append(index)
            if index == 3:  # page 4
                raise RuntimeError("tesseract blew up on this page")
            return [FakeDoc(chunk_index=0)]

    loader = FlakyLoader()
    text_db = FakeTextDB()
    status_tracker = FakeStatusTracker()

    _index_pdf_pages(loader, text_db, status_tracker, "some.pdf", "h",
                      "f.pdf", [2, 4, 6])

    assert loader.calls == [1, 3, 5], "must keep going after the failing page"
    assert [p for _, p, _ in status_tracker.marked] == [2, 6], \
        "failed page must stay unmarked so it is retried"
