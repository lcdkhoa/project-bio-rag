"""Regression tests: `--etl` / `--image-only` must obey the hash+version checkpoint.

Bugs covered here:

1. `run_etl()` and `run_etl_image_only()` short-circuited on
   `filename in processed_files.txt / processed_images.txt`. That made an
   `IMAGE_EXTRACTION_VERSION` bump a silent no-op, and skipped a replaced
   same-name PDF whose content hash had changed. `run_etl_text_only()` was
   already fixed (see `test_checkpoint_no_filename_skip.py`); these two
   entrypoints were left behind.

2. `run_etl()` indexed text with the legacy `RobustOCRLoader` + `TextSplitter`
   instead of the layout-aware `LayoutOCRLoader` that `--text-only` uses, so
   `--etl` produced chunks with no `variant` / `region_type` / `chunk_index`
   metadata and citations lost their sidebar/info-box labels.

3. `run_etl()` ran full-PDF OCR *before* consulting the checkpoint, so a
   nothing-to-do book still paid for a whole book of OCR.

Everything heavy (OCR, embeddings, ChromaDB, the image processor) is faked; the
only real work is a blank 2-page PDF so `fitz` page counting is exercised for
real.
"""
import fitz
import pytest
from langchain_core.documents import Document

import main
import src.etl as etl_pkg
import src.rag.image_vectorstore as ivs_mod
import src.rag.vectorstore as vs_mod

OLD_VERSION = "v15_old"
NEW_VERSION = "v16_new"
BOOK = "SGK KHTN8 KNTT.pdf"
NUM_PAGES = 2


def _make_pdf(path, pages=NUM_PAGES):
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    doc.save(str(path))
    doc.close()


class FakeStatus:
    """In-memory stand-in for ProcessingStatus (hash-keyed, version-aware)."""

    def __init__(self):
        self.text_done = set()          # {(pdf_hash, page)}
        self.image_done = {}            # {(pdf_hash, page): version}

    def get_pages_needing_text(self, pdf_hash, total_pages):
        return [p for p in range(1, total_pages + 1) if (pdf_hash, p) not in self.text_done]

    def needs_image_processing_versioned(self, pdf_hash, page_number, required_version=None):
        current = self.image_done.get((pdf_hash, page_number))
        if current is None:
            return True
        if not required_version:
            return False
        return current != required_version

    def mark_text_indexed(self, pdf_hash, page_number, pdf_filename):
        self.text_done.add((pdf_hash, page_number))

    def mark_image_extracted(self, pdf_hash, page_number, pdf_filename, **kwargs):
        self.image_done[(pdf_hash, page_number)] = kwargs.get("image_extraction_version")

    # helpers for tests
    def seed_text(self, pdf_hash, pages=range(1, NUM_PAGES + 1)):
        for p in pages:
            self.text_done.add((pdf_hash, p))

    def seed_images(self, pdf_hash, version, pages=range(1, NUM_PAGES + 1)):
        for p in pages:
            self.image_done[(pdf_hash, p)] = version


class FakeLayoutLoader:
    """Stands in for LayoutOCRLoader: per-page, returns already-chunked docs."""

    instances = []

    def __init__(self):
        self.pages_loaded = []
        FakeLayoutLoader.instances.append(self)

    def load_page(self, pdf_file, index):
        self.pages_loaded.append(index)
        return [Document(
            page_content=f"body text page {index + 1}",
            metadata={"source": BOOK, "page": index + 1, "variant": "kntt",
                      "region_type": "body", "chunk_index": 0},
        )]


class FakeOCRLoader:
    """Stands in for RobustOCRLoader: whole-PDF OCR, used only for image anchors."""

    instances = []

    def __init__(self):
        self.pdfs_loaded = []
        FakeOCRLoader.instances.append(self)

    def load_pdf(self, pdf_file):
        self.pdfs_loaded.append(pdf_file)
        return [Document(page_content=f"ocr page {p}", metadata={"page": p})
                for p in range(1, NUM_PAGES + 1)]


class FakeImageProcessor:
    instances = []

    def __init__(self, version):
        self.image_extraction_version = version
        self.calls = []
        FakeImageProcessor.instances.append(self)

    def extract_images_from_pdf(self, pdf_path, pdf_hash, pdf_filename, ocr_text_per_page):
        self.calls.append({"pdf_hash": pdf_hash, "pdf_filename": pdf_filename,
                           "ocr_pages": sorted(ocr_text_per_page)})
        return [Document(page_content="figure", metadata={"image_id": "img_1"})]


class FakeChroma:
    def __init__(self):
        self.added = []

    def add_documents(self, docs, ids=None):
        self.added.extend(docs)


class FakeTextVDB:
    def __init__(self):
        self.db = FakeChroma()


class FakeImageVDB:
    def __init__(self):
        self.added = []

    def add_documents(self, docs):
        self.added.extend(docs)


class Env:
    """Handles returned to tests so they can assert on what actually ran."""

    def __init__(self, status, pdf_hash_box, text_log, image_log):
        self.status = status
        self._hash = pdf_hash_box
        self.text_log = text_log
        self.image_log = image_log

    def set_hash(self, value):
        self._hash[0] = value

    @property
    def hash(self):
        return self._hash[0]

    def mark_filename_done(self, both=True):
        self.image_log.write_text(BOOK + "\n", encoding="utf-8")
        if both:
            self.text_log.write_text(BOOK + "\n", encoding="utf-8")

    @property
    def layout(self):
        return FakeLayoutLoader.instances

    @property
    def ocr(self):
        return FakeOCRLoader.instances

    @property
    def processor(self):
        return FakeImageProcessor.instances

    @property
    def indexed_text_docs(self):
        return [d for vdb in _text_vdbs for d in vdb.db.added]

    @property
    def image_extract_calls(self):
        return [c for p in FakeImageProcessor.instances for c in p.calls]

    @property
    def ocr_loaded_pdfs(self):
        return [p for inst in FakeOCRLoader.instances for p in inst.pdfs_loaded]

    @property
    def layout_pages_loaded(self):
        return sorted(p for inst in FakeLayoutLoader.instances for p in inst.pages_loaded)


_text_vdbs = []


@pytest.fixture
def env(tmp_path, monkeypatch):
    FakeLayoutLoader.instances.clear()
    FakeOCRLoader.instances.clear()
    FakeImageProcessor.instances.clear()
    _text_vdbs.clear()

    data_dir = tmp_path / "datasources"
    data_dir.mkdir()
    _make_pdf(data_dir / BOOK)

    text_log = tmp_path / "processed_files.txt"
    image_log = tmp_path / "processed_images.txt"

    monkeypatch.setattr(main, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(main, "PERSIST_DIR", tmp_path / "db")
    monkeypatch.setattr(main, "IMAGES_DIR", tmp_path / "db" / "images")
    monkeypatch.setattr(main, "PROCESSED_FILES_LOG", text_log)
    monkeypatch.setattr(main, "PROCESSED_IMAGES_LOG", image_log)

    status = FakeStatus()
    pdf_hash_box = ["hash_v1"]

    monkeypatch.setattr(etl_pkg, "ProcessingStatus", lambda: status)
    monkeypatch.setattr(etl_pkg, "LayoutOCRLoader", FakeLayoutLoader, raising=False)
    monkeypatch.setattr(etl_pkg, "RobustOCRLoader", FakeOCRLoader)
    monkeypatch.setattr(etl_pkg, "compute_file_hash", lambda path: pdf_hash_box[0])
    monkeypatch.setattr(
        etl_pkg, "make_image_processor",
        lambda filename, status_tracker=None: FakeImageProcessor(NEW_VERSION),
    )

    def _text_vdb():
        vdb = FakeTextVDB()
        _text_vdbs.append(vdb)
        return vdb

    monkeypatch.setattr(vs_mod, "VectorDB", _text_vdb)
    monkeypatch.setattr(ivs_mod, "ImageVectorDB", FakeImageVDB)

    return Env(status, pdf_hash_box, text_log, image_log)


# --- run_etl (--etl) -------------------------------------------------------


def test_etl_version_bump_reextracts_despite_filename_log(env):
    """A bumped IMAGE_EXTRACTION_VERSION must re-extract even when the book is
    listed as done in processed_images.txt."""
    env.mark_filename_done()
    env.status.seed_text(env.hash)
    env.status.seed_images(env.hash, OLD_VERSION)

    main.run_etl()

    assert len(env.image_extract_calls) == 1, "version bump must force re-extraction"


def test_etl_replaced_pdf_same_name_new_hash_is_reprocessed(env):
    """Same filename, new content hash -> both sides must run again."""
    env.mark_filename_done()
    env.status.seed_text("hash_v1")
    env.status.seed_images("hash_v1", NEW_VERSION)
    env.set_hash("hash_v2")

    main.run_etl()

    assert env.layout_pages_loaded == [0, 1], "new hash must re-index text pages"
    assert len(env.image_extract_calls) == 1, "new hash must re-extract images"


def test_etl_indexes_text_via_layout_loader(env):
    """--etl must build text chunks with the same layout-aware loader as
    --text-only, so chunks carry variant/region_type/chunk_index."""
    main.run_etl()

    assert env.layout_pages_loaded == [0, 1]
    assert env.indexed_text_docs, "no text chunks were indexed"
    for doc in env.indexed_text_docs:
        assert doc.metadata.get("region_type"), f"chunk lost layout metadata: {doc.metadata}"
        assert doc.metadata.get("variant")
        assert "chunk_index" in doc.metadata


def test_etl_skips_finished_book_without_running_ocr(env):
    """Nothing left to do (per hash+version) -> no OCR at all, even with empty
    filename logs. Guards against paying for a whole book of OCR to discover
    there was nothing to do."""
    env.status.seed_text(env.hash)
    env.status.seed_images(env.hash, NEW_VERSION)

    main.run_etl()

    assert env.ocr_loaded_pdfs == [], "must not OCR a book with nothing to do"
    assert env.layout_pages_loaded == []
    assert env.image_extract_calls == []


# --- run_etl_image_only (--image-only) ------------------------------------


def test_image_only_version_bump_reextracts_despite_filename_log(env):
    env.mark_filename_done()
    env.status.seed_images(env.hash, OLD_VERSION)

    main.run_etl_image_only()

    assert len(env.image_extract_calls) == 1, "version bump must force re-extraction"


def test_image_only_skips_finished_book_without_running_ocr(env):
    env.status.seed_images(env.hash, NEW_VERSION)

    main.run_etl_image_only()

    assert env.ocr_loaded_pdfs == [], "must not OCR a book with nothing to do"
    assert env.image_extract_calls == []


def test_etl_records_both_logs_when_only_one_side_needed_work(env):
    """A book that only needed text must still end up recorded in
    processed_images.txt (and vice versa) — the advisory logs should not drift
    out of sync with what the checkpoint says is done."""
    env.status.seed_images(env.hash, NEW_VERSION)   # images already current

    main.run_etl()

    assert env.image_extract_calls == [], "images were already at the current version"
    assert env.layout_pages_loaded == [0, 1], "text still needed indexing"
    assert BOOK in env.text_log.read_text(encoding="utf-8")
    assert BOOK in env.image_log.read_text(encoding="utf-8"), \
        "image side is done, so it must be logged too"


def test_etl_does_not_duplicate_log_lines_across_runs(env):
    """The logs are append-only; re-running must not pile up duplicates."""
    env.status.seed_text(env.hash)
    env.status.seed_images(env.hash, NEW_VERSION)

    main.run_etl()
    main.run_etl()

    assert env.text_log.read_text(encoding="utf-8").count(BOOK) == 1
    assert env.image_log.read_text(encoding="utf-8").count(BOOK) == 1
