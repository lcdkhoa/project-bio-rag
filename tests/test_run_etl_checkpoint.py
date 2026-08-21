"""Regression tests: `--etl` / `--image-only` phải tuân checkpoint (hash trang + version).

Các bug bị khoá lại ở đây:

1. `run_etl()` / `run_etl_image_only()` từng short-circuit theo
   `filename in processed_files.txt / processed_images.txt`. Điều đó làm một lần
   bump `IMAGE_EXTRACTION_VERSION` trở thành no-op im lặng, và bỏ qua một quyển
   bị thay nội dung dưới cùng tên. Nguồn sự thật duy nhất là `ProcessingStatus`.
2. `run_etl()` từng index text bằng `RobustOCRLoader` + `TextSplitter` thay vì
   `LayoutOCRLoader` mà `--text-only` dùng, nên `--etl` sinh chunk không có
   `variant`/`region_type`/`chunk_index` và citation mất nhãn sidebar/info-box.
3. `run_etl()` từng OCR cả quyển TRƯỚC khi hỏi checkpoint, nên một quyển không
   còn gì để làm vẫn phải trả giá OCR cả quyển.
4. (mới, nguồn PNG) checkpoint khoá theo hash TỪNG TRANG: thay đúng một file
   trang phải chỉ re-process trang đó, không phải cả quyển.

Mọi thứ nặng (OCR, embedding, ChromaDB, image processor) đều là fake; phần thật
duy nhất là các file PNG nhỏ trên đĩa, để `PngFolderPageSource` và cơ chế hash
theo trang được chạy thật.
"""
import cv2
import numpy as np
import pytest
from langchain_core.documents import Document

import main
import src.etl as etl_pkg
import src.rag.image_vectorstore as ivs_mod
import src.rag.vectorstore as vs_mod
from src.etl.page_source import page_checkpoint_key

OLD_VERSION = "v15_old"
NEW_VERSION = "v16_new"
BOOK = "SGK_KHTN_8_KNTT"
PAGE_NUMBERS = (1, 2)


def _write_page(folder, number, tint):
    image = np.full((40, 30, 3), 255, dtype=np.uint8)
    image[0, 0] = tint
    cv2.imwrite(str(folder / f"page_{number:03d}.png"), image)


class FakeStatus:
    """Bản in-memory của ProcessingStatus: khoá theo page_key + version."""

    def __init__(self):
        self.text_done = {}             # {(page_key, page): version}
        self.image_done = {}            # {(page_key, page): version}

    def _needs(self, done, page_key, page_number, required_version):
        current = done.get((page_key, page_number))
        if current is None:
            return True
        if not required_version:
            return False
        return current != required_version

    def needs_text_processing(self, page_key, page_number, required_version=None):
        return self._needs(self.text_done, page_key, page_number, required_version)

    def needs_image_processing_versioned(self, page_key, page_number,
                                         required_version=None):
        return self._needs(self.image_done, page_key, page_number, required_version)

    def pages_needing_text(self, source, required_version=None):
        return [n for n in source.page_numbers()
                if self.needs_text_processing(
                    page_checkpoint_key(source, n), n,
                    required_version or main.TEXT_EXTRACTION_VERSION)]

    def pages_needing_images(self, source, required_version=None):
        return [n for n in source.page_numbers()
                if self.needs_image_processing_versioned(
                    page_checkpoint_key(source, n), n, required_version)]

    def mark_text_indexed(self, page_key, page_number, pdf_filename,
                          text_extraction_version=None):
        self.text_done[(page_key, page_number)] = text_extraction_version

    def mark_image_extracted(self, page_key, page_number, pdf_filename, **kwargs):
        self.image_done[(page_key, page_number)] = kwargs.get(
            "image_extraction_version")

    # helpers cho test
    def seed_text(self, source, pages=PAGE_NUMBERS):
        for page in pages:
            self.text_done[(page_checkpoint_key(source, page), page)] = \
                main.TEXT_EXTRACTION_VERSION

    def seed_images(self, source, version, pages=PAGE_NUMBERS):
        for page in pages:
            self.image_done[(page_checkpoint_key(source, page), page)] = version


class FakeLayoutLoader:
    """Thay LayoutOCRLoader: từng trang, trả về chunk đã dựng sẵn."""

    instances = []

    def __init__(self):
        self.pages_loaded = []
        self.manifests_checked = []
        FakeLayoutLoader.instances.append(self)

    def manifest_for(self, source):
        """Thật: raise nếu chưa dựng manifest. Ở đây chỉ ghi lại lượt gọi."""
        self.manifests_checked.append(source.name)
        return {}

    def load_page(self, source, page_number):
        self.pages_loaded.append(page_number)
        return [Document(
            page_content=f"body text page {page_number}",
            metadata={"source": source.name, "page": page_number - 1,
                      "page_index": page_number, "variant": "kntt",
                      "region_type": "body", "chunk_index": 0},
        )]


class FakeOCRLoader:
    """Thay RobustOCRLoader: OCR cả trang, chỉ dùng để neo caption hình."""

    instances = []

    def __init__(self):
        self.pages_ocred = []
        FakeOCRLoader.instances.append(self)

    def ocr_image(self, image):
        self.pages_ocred.append(getattr(image, "shape", None))
        return "ocr text"


class FakeImageProcessor:
    instances = []

    def __init__(self, version):
        self.image_extraction_version = version
        self.calls = []
        FakeImageProcessor.instances.append(self)

    def extract_images_from_source(self, source, ocr_text_per_page, pages=None):
        self.calls.append({"source": source.name, "pages": list(pages or []),
                           "ocr_pages": sorted(ocr_text_per_page)})
        return [Document(page_content="figure", metadata={"image_id": "img_1"})]


class FakeChroma:
    def __init__(self):
        self.added = []
        self.deletes = []

    def add_documents(self, docs, ids=None):
        self.added.extend(docs)

    def delete(self, where=None):
        self.deletes.append(where)


class FakeTextVDB:
    def __init__(self):
        self.db = FakeChroma()


class FakeImageVDB:
    def __init__(self):
        self.added = []

    def add_documents(self, docs):
        self.added.extend(docs)


_text_vdbs = []


class Env:
    def __init__(self, folder, text_log, image_log, status):
        self.folder = folder
        self.status = status
        self.text_log = text_log
        self.image_log = image_log

    @property
    def source(self):
        from src.etl.page_source import PngFolderPageSource
        return PngFolderPageSource(self.folder)

    def rewrite_page(self, number, tint=(9, 9, 9)):
        """Thay nội dung một file trang -> hash trang đổi -> phải re-process."""
        _write_page(self.folder, number, tint)

    def mark_filename_done(self, both=True):
        self.image_log.write_text(BOOK + "\n", encoding="utf-8")
        if both:
            self.text_log.write_text(BOOK + "\n", encoding="utf-8")

    @property
    def indexed_text_docs(self):
        return [d for vdb in _text_vdbs for d in vdb.db.added]

    @property
    def image_extract_calls(self):
        return [c for p in FakeImageProcessor.instances for c in p.calls]

    @property
    def pages_ocred(self):
        return [p for inst in FakeOCRLoader.instances for p in inst.pages_ocred]

    @property
    def layout_pages_loaded(self):
        return sorted(p for inst in FakeLayoutLoader.instances
                      for p in inst.pages_loaded)


@pytest.fixture
def env(tmp_path, monkeypatch):
    FakeLayoutLoader.instances.clear()
    FakeOCRLoader.instances.clear()
    FakeImageProcessor.instances.clear()
    _text_vdbs.clear()

    data_dir = tmp_path / "datasources"
    folder = data_dir / BOOK
    folder.mkdir(parents=True)
    for number in PAGE_NUMBERS:
        _write_page(folder, number, (number, 1, 2))

    text_log = tmp_path / "processed_files.txt"
    image_log = tmp_path / "processed_images.txt"

    monkeypatch.setattr(main, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(main, "PERSIST_DIR", tmp_path / "db")
    monkeypatch.setattr(main, "IMAGES_DIR", tmp_path / "db" / "images")
    monkeypatch.setattr(main, "PROCESSED_FILES_LOG", text_log)
    monkeypatch.setattr(main, "PROCESSED_IMAGES_LOG", image_log)

    status = FakeStatus()

    monkeypatch.setattr(etl_pkg, "ProcessingStatus", lambda: status)
    monkeypatch.setattr(etl_pkg, "LayoutOCRLoader", FakeLayoutLoader, raising=False)
    monkeypatch.setattr(etl_pkg, "RobustOCRLoader", FakeOCRLoader)
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

    return Env(folder, text_log, image_log, status)


# --- run_etl (--etl) -------------------------------------------------------


def test_etl_version_bump_reextracts_despite_filename_log(env):
    env.mark_filename_done()
    env.status.seed_text(env.source)
    env.status.seed_images(env.source, OLD_VERSION)

    main.run_etl()

    assert len(env.image_extract_calls) == 1, "version bump must force re-extraction"


def test_etl_replaced_page_same_name_new_content_is_reprocessed(env):
    """Thay đúng MỘT file trang: chỉ trang đó được làm lại, không phải cả quyển."""
    env.status.seed_text(env.source)
    env.status.seed_images(env.source, NEW_VERSION)
    env.rewrite_page(2)

    main.run_etl()

    assert env.layout_pages_loaded == [2], \
        "chỉ trang bị thay nội dung được index lại"
    assert env.image_extract_calls[0]["pages"] == [2]


def test_etl_indexes_text_via_layout_loader(env):
    main.run_etl()

    # manifest được hỏi MỘT lần cho cả quyển, trước khi index trang nào
    assert [c for inst in FakeLayoutLoader.instances
            for c in inst.manifests_checked] == [BOOK]
    assert env.layout_pages_loaded == [1, 2]
    assert env.indexed_text_docs, "no text chunks were indexed"
    for doc in env.indexed_text_docs:
        assert doc.metadata.get("region_type"), f"chunk lost layout metadata: {doc.metadata}"
        assert doc.metadata.get("variant")
        assert "chunk_index" in doc.metadata
        assert "page_index" in doc.metadata


def test_etl_skips_finished_book_without_running_ocr(env):
    env.status.seed_text(env.source)
    env.status.seed_images(env.source, NEW_VERSION)

    main.run_etl()

    assert env.pages_ocred == [], "must not OCR a book with nothing to do"
    assert env.layout_pages_loaded == []
    assert env.image_extract_calls == []


def test_etl_only_ocrs_the_pages_the_image_side_needs(env):
    """OCR cả trang là để neo caption; chỉ chạy cho trang phía ảnh còn cần."""
    env.status.seed_images(env.source, NEW_VERSION, pages=[1])

    main.run_etl()

    assert len(env.pages_ocred) == 1
    assert env.image_extract_calls[0]["ocr_pages"] == [2]


# --- run_etl_image_only (--image-only) ------------------------------------


def test_image_only_version_bump_reextracts_despite_filename_log(env):
    env.mark_filename_done()
    env.status.seed_images(env.source, OLD_VERSION)

    main.run_etl_image_only()

    assert len(env.image_extract_calls) == 1, "version bump must force re-extraction"


def test_image_only_skips_finished_book_without_running_ocr(env):
    env.status.seed_images(env.source, NEW_VERSION)

    main.run_etl_image_only()

    assert env.pages_ocred == [], "must not OCR a book with nothing to do"
    assert env.image_extract_calls == []


# --- run_etl_text_only (--text-only) --------------------------------------


def test_text_only_ignores_the_filename_log(env):
    """Quyển đã có tên trong processed_files.txt nhưng trang chưa index -> vẫn
    phải index. Log tên file là advisory, không phải checkpoint."""
    env.mark_filename_done()

    main.run_etl_text_only()

    assert env.layout_pages_loaded == [1, 2]


def test_etl_records_both_logs_when_only_one_side_needed_work(env):
    env.status.seed_images(env.source, NEW_VERSION)

    main.run_etl()

    assert env.image_extract_calls == [], "images were already at the current version"
    assert env.layout_pages_loaded == [1, 2], "text still needed indexing"
    assert BOOK in env.text_log.read_text(encoding="utf-8")
    assert BOOK in env.image_log.read_text(encoding="utf-8"), \
        "image side is done, so it must be logged too"


def test_etl_does_not_duplicate_log_lines_across_runs(env):
    env.status.seed_text(env.source)
    env.status.seed_images(env.source, NEW_VERSION)

    main.run_etl()
    main.run_etl()

    assert env.text_log.read_text(encoding="utf-8").count(BOOK) == 1
    assert env.image_log.read_text(encoding="utf-8").count(BOOK) == 1
