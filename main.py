"""Main entry point for Biology RAG system."""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from src.config import (LOG_LEVEL, DATA_DIR, PERSIST_DIR, IMAGES_DIR,
                        PROCESSED_FILES_LOG, PROCESSED_IMAGES_LOG,
                        PROGRESS_LOG_EVERY_PAGES, PROGRESS_LOG_EVERY_SECONDS,
                        TEXT_EXTRACTION_VERSION)
from src.utils.progress import ProgressLogger, format_duration

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _page_progress(label: str, total: int) -> ProgressLogger:
    """ProgressLogger cho một vòng lặp theo trang, dùng nhịp từ config."""
    return ProgressLogger(
        logger, label, total,
        every_items=PROGRESS_LOG_EVERY_PAGES,
        every_seconds=PROGRESS_LOG_EVERY_SECONDS,
        unit="trang")


def _iter_books(sources, progress):
    """Duyệt từng quyển, tự đánh dấu quyển TRƯỚC đã xong vào `progress`.

    Thân vòng lặp trong `run_etl*` thoát bằng nhiều đường (`continue` khi không
    còn gì làm, `except` khi lỗi), nên không có một chỗ duy nhất để gọi
    `advance()`. Generator này giải quyết đúng chỗ đó mà không phải sửa thân
    vòng lặp: mỗi lần được xin quyển kế tiếp nghĩa là quyển trước đã kết thúc,
    bằng bất cứ đường nào.
    """
    started = False
    for source in sources:
        if started:
            progress.advance()
        started = True
        yield source
    if started:
        progress.advance()


def _book_progress(label: str, total: int) -> ProgressLogger:
    """Tiến trình mức QUYỂN: log ngay khi mỗi quyển xong (every_items=1)."""
    return ProgressLogger(logger, label, total, every_items=1,
                          every_seconds=PROGRESS_LOG_EVERY_SECONDS,
                          unit="quyển")


def get_processed_files():
    """Read list of processed files from checkpoint log."""
    if not os.path.exists(PROCESSED_FILES_LOG):
        return set()
    with open(PROCESSED_FILES_LOG, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def mark_file_as_processed(filename: str):
    """Mark a file as processed in checkpoint log."""
    with open(PROCESSED_FILES_LOG, "a", encoding="utf-8") as f:
        f.write(f"{filename}\n")


def get_processed_images():
    """Read list of processed files for images from checkpoint log."""
    if not os.path.exists(PROCESSED_IMAGES_LOG):
        return set()
    with open(PROCESSED_IMAGES_LOG, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def mark_image_as_processed(filename: str):
    """Mark a file as processed for images in checkpoint log."""
    with open(PROCESSED_IMAGES_LOG, "a", encoding="utf-8") as f:
        f.write(f"{filename}\n")


def _index_source_pages(loader, text_db, status_tracker, source,
                        pages_to_index):
    """Index đúng những trang còn thiếu text (resume-safe), từng trang một.

    Id chunk là `{page_key}_p{page_number}_c{chunk_index}` với `page_key` mang
    **hash nội dung của chính trang đó** (`page_checkpoint_key`), nên:
    - chạy lại một trang đã index = upsert, không nhân bản;
    - thay nội dung một trang = id mới, không ghi đè bản cũ một cách mù mờ (bản
      cũ được xoá tường minh ngay trước khi add, xem dưới).

    Trang raise thì được log và **để lại chưa mark**, lần chạy sau làm lại
    (nguyên tắc 5: không index một nửa dữ liệu, không im lặng).
    """
    from src.etl.page_source import page_checkpoint_key

    progress = _page_progress(f"[{source.name}] text", len(pages_to_index))
    with progress:
        for page_number in pages_to_index:
            _index_one_page(loader, text_db, status_tracker, source,
                            page_number, page_checkpoint_key, progress)


def _index_one_page(loader, text_db, status_tracker, source, page_number,
                    page_checkpoint_key, progress) -> None:
    """Một trang text: lỗi thì log + đếm vào `fail`, KHÔNG mark, không chặn quyển."""
    try:
        page_key = page_checkpoint_key(source, page_number)
        page_docs = loader.load_page(source, page_number)
        # Chunk cũ của ĐÚNG trang này (kể cả từ version/nội dung trước) phải
        # đi trước khi ghi bản mới: nếu không, đổi TEXT_EXTRACTION_VERSION
        # hoặc thay trang sẽ để lại chunk mồ côi và học sinh có thể được
        # trích một đoạn không còn tồn tại trên trang.
        _delete_page_chunks(text_db, source.name, page_number)
        if page_docs:
            ids = [f"{page_key}_p{page_number}_c{d.metadata['chunk_index']}"
                   for d in page_docs]
            text_db.add_documents(page_docs, ids=ids)
        status_tracker.mark_text_indexed(
            page_key, page_number, source.name,
            text_extraction_version=TEXT_EXTRACTION_VERSION)
        progress.advance(chunks=len(page_docs) if page_docs else 0,
                         trang_rong=0 if page_docs else 1)
    except Exception as e:
        logger.error(f"[{source.name}] page {page_number} text indexing failed: {e}")
        progress.advance(fail=1)


def _delete_page_chunks(text_db, source_name: str, page_number: int) -> None:
    """Xoá mọi chunk text của một trang nguồn. Lỗi thì log, không chặn ETL."""
    try:
        text_db.delete(where={"$and": [{"source": {"$eq": source_name}},
                                       {"page_index": {"$eq": page_number}}]})
    except Exception as e:
        logger.warning(
            f"[{source_name}] page {page_number}: không xoá được chunk cũ: {e}")


def _load_ocr_text_per_page(ocr_loader, source, pages):
    """OCR cả trang, khoá theo SỐ TRANG NGUỒN — dùng để neo caption hình.

    Chỉ OCR những trang phía ảnh thật sự cần (`pages`), không cả quyển. Trả None
    khi không trang nào ra chữ, để caller bỏ qua quyển đó.
    """
    out = {}
    with _page_progress(f"[{source.name}] OCR neo caption", len(pages)) as progress:
        for page_number in pages:
            try:
                text = ocr_loader.ocr_image(source.load(page_number))
            except Exception as e:
                logger.warning(
                    f"[{source.name}] page {page_number} OCR failed: {e}")
                progress.advance(fail=1)
                continue
            if text:
                out[page_number] = text
            progress.advance(khong_chu=0 if text else 1)
    if not out:
        logger.warning(f"No text extracted from {source.name}")
        return None
    return out


def _mark_file_done_once(filename: str):
    """Record text completion, skipping the write if already logged.

    The logs are append-only and no longer gate processing, so writing on every
    run would just pile up duplicate lines.
    """
    if filename not in get_processed_files():
        mark_file_as_processed(filename)


def _mark_image_done_once(filename: str):
    """Record image completion, skipping the write if already logged."""
    if filename not in get_processed_images():
        mark_image_as_processed(filename)


def run_etl_text_only():
    """ETL text: nguồn trang -> OCR theo vùng -> chunk -> ChromaDB."""
    logger.info("Starting ETL pipeline (TEXT ONLY)...")

    os.makedirs(PERSIST_DIR, exist_ok=True)

    from src.etl import LayoutOCRLoader, ProcessingStatus
    from src.etl.page_source import discover_page_sources

    loader = LayoutOCRLoader()
    status_tracker = ProcessingStatus()

    from src.rag.vectorstore import VectorDB

    text_vdb = VectorDB()
    text_db = text_vdb.db

    sources = discover_page_sources(DATA_DIR)
    if not sources:
        # Thoát KHÁC 0: từ 2026-08-23 `datasources/` không nằm trong git (D-68) nên
        # "không thấy quyển nào" là cách hỏng phổ biến nhất của một bản clone mới.
        # `return` cho exit code 0, tức một cell Colab / CI sẽ trông như đã chạy
        # xong mà không xử lý gì — đúng kiểu im lặng nguyên tắc 5 cấm.
        logger.error(f"Không thấy quyển nào trong {DATA_DIR} — "
                     f"trỏ RAG_DATA_DIR vào thư mục chứa các folder "
                     f"SGK_KHTN_*/page_NNN.png (xem datasources/README.md)")
        sys.exit(2)

    logger.info(f"Total books in directory: {len(sources)}")
    logger.info(f"Previously processed files: {len(get_processed_files())}")

    books = _book_progress("ETL text: tiến trình quyển", len(sources))
    for source in _iter_books(sources, books):
        logger.info(f"Processing: {source.name}")

        try:
            # Hỏi manifest MỘT lần cho cả quyển: không có manifest thì fail ở đây
            # với một dòng lỗi rõ ràng, thay vì 196 dòng lỗi giống nhau ở từng
            # trang (loud, nhưng đừng ồn vô ích).
            loader.manifest_for(source)
            pages_to_index = status_tracker.pages_needing_text(source)

            if not pages_to_index:
                logger.info(f"[{source.name}] All pages already indexed, skipping")
                _mark_file_done_once(source.name)
                continue

            logger.info(
                f"[{source.name}] Pages to index (source page numbers): "
                f"{_summarise(pages_to_index)}")

            _index_source_pages(loader, text_db, status_tracker, source,
                                pages_to_index)

            _mark_file_done_once(source.name)
            logger.info(f"Completed: {source.name}")

        except Exception as e:
            logger.error(f"Error processing {source.name}: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")

    books.finish()
    logger.info("ETL (TEXT) pipeline completed!")


def _summarise(pages, limit=12):
    """In gọn danh sách trang dài (801 trang thì đừng dump hết vào log)."""
    if len(pages) <= limit:
        return str(pages)
    return f"{pages[:limit]} … (+{len(pages) - limit} trang)"


def run_etl_image_only():
    """ETL ảnh: crop hình, caption, index. Cùng nguồn trang với đường text."""
    logger.info("Starting ETL pipeline (IMAGE ONLY)...")

    os.makedirs(IMAGES_DIR, exist_ok=True)
    os.makedirs(PERSIST_DIR, exist_ok=True)

    from src.etl import RobustOCRLoader, ProcessingStatus, make_image_processor
    from src.etl.page_source import discover_page_sources

    ocr_loader = RobustOCRLoader()
    status_tracker = ProcessingStatus()

    from src.rag.image_vectorstore import ImageVectorDB

    image_vdb = ImageVectorDB()

    sources = discover_page_sources(DATA_DIR)
    if not sources:
        # Thoát KHÁC 0: từ 2026-08-23 `datasources/` không nằm trong git (D-68) nên
        # "không thấy quyển nào" là cách hỏng phổ biến nhất của một bản clone mới.
        # `return` cho exit code 0, tức một cell Colab / CI sẽ trông như đã chạy
        # xong mà không xử lý gì — đúng kiểu im lặng nguyên tắc 5 cấm.
        logger.error(f"Không thấy quyển nào trong {DATA_DIR} — "
                     f"trỏ RAG_DATA_DIR vào thư mục chứa các folder "
                     f"SGK_KHTN_*/page_NNN.png (xem datasources/README.md)")
        sys.exit(2)

    logger.info(f"Total books in directory: {len(sources)}")
    # processed_images.txt là log tiến độ (advisory) — quyết định skip nằm ở
    # ProcessingStatus, khoá theo hash TỪNG TRANG + version.
    logger.info(
        f"Previously processed files for images: {len(get_processed_images())}")

    books = _book_progress("ETL ảnh: tiến trình quyển", len(sources))
    for source in _iter_books(sources, books):
        logger.info(f"Processing: {source.name}")

        image_processor = make_image_processor(source.name,
                                              status_tracker=status_tracker)

        try:
            pages_to_process = status_tracker.pages_needing_images(
                source, required_version=image_processor.image_extraction_version)

            if not pages_to_process:
                logger.info(
                    f"[{source.name}] All pages already processed for images, skipping")
                _mark_image_done_once(source.name)
                continue

            logger.info(
                f"[{source.name}] Pages to extract images: "
                f"{_summarise(pages_to_process)}")

            ocr_text_per_page = _load_ocr_text_per_page(
                ocr_loader, source, pages_to_process)
            if ocr_text_per_page is None:
                continue

            image_docs = image_processor.extract_images_from_source(
                source=source,
                pages=pages_to_process,
                ocr_text_per_page=ocr_text_per_page,
            )

            # Xoá doc ảnh CŨ của đúng những trang vừa crop lại, TRƯỚC khi ghi bản
            # mới — đối xứng với `_delete_page_chunks` của đường text. Chạy sau khi
            # extraction đã thành công (extraction raise thì không xoá gì, lần sau
            # làm lại). Xoá cả khi `image_docs` rỗng: một trang giờ không còn hình
            # thì doc cũ của nó cũng phải đi, không được sống sót thành mồ côi.
            image_vdb.delete_page_documents(source.name, pages_to_process)

            if image_docs:
                image_vdb.add_documents(image_docs)
                logger.info(
                    f"[{source.name}] Added {len(image_docs)} images to ImageVectorDB")

            _mark_image_done_once(source.name)
            logger.info(f"Completed images for: {source.name}")

        except Exception as e:
            logger.error(f"Error processing {source.name}: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")

    books.finish()
    logger.info("ETL (IMAGE) pipeline completed!")


def run_etl():
    """ETL đầy đủ: text + ảnh, cùng một nguồn trang."""
    logger.info("Starting ETL pipeline (FULL)...")

    os.makedirs(IMAGES_DIR, exist_ok=True)
    os.makedirs(PERSIST_DIR, exist_ok=True)

    from src.etl import (
        LayoutOCRLoader,
        RobustOCRLoader,
        ProcessingStatus,
        make_image_processor,
    )
    from src.etl.page_source import discover_page_sources

    # Text đi qua loader layout-aware, đúng như --text-only, nên hai entrypoint
    # sinh ra cùng một index. RobustOCRLoader chỉ còn để lấy text cả trang cho
    # việc neo caption hình.
    layout_loader = LayoutOCRLoader()
    ocr_loader = RobustOCRLoader()
    status_tracker = ProcessingStatus()

    from src.rag.vectorstore import VectorDB
    from src.rag.image_vectorstore import ImageVectorDB

    text_vdb = VectorDB()
    text_db = text_vdb.db
    image_vdb = ImageVectorDB()

    sources = discover_page_sources(DATA_DIR)
    if not sources:
        # Thoát KHÁC 0: từ 2026-08-23 `datasources/` không nằm trong git (D-68) nên
        # "không thấy quyển nào" là cách hỏng phổ biến nhất của một bản clone mới.
        # `return` cho exit code 0, tức một cell Colab / CI sẽ trông như đã chạy
        # xong mà không xử lý gì — đúng kiểu im lặng nguyên tắc 5 cấm.
        logger.error(f"Không thấy quyển nào trong {DATA_DIR} — "
                     f"trỏ RAG_DATA_DIR vào thư mục chứa các folder "
                     f"SGK_KHTN_*/page_NNN.png (xem datasources/README.md)")
        sys.exit(2)

    logger.info(f"Total books in directory: {len(sources)}")
    logger.info(
        f"Previously processed files: text={len(get_processed_files())}, "
        f"images={len(get_processed_images())}")

    books = _book_progress("ETL full: tiến trình quyển", len(sources))
    for source in _iter_books(sources, books):
        logger.info(f"Processing: {source.name}")

        image_processor = make_image_processor(source.name,
                                              status_tracker=status_tracker)

        try:
            pages_needing_text = status_tracker.pages_needing_text(source)
            pages_needing_images = status_tracker.pages_needing_images(
                source, required_version=image_processor.image_extraction_version)

            if not pages_needing_text and not pages_needing_images:
                logger.info(
                    f"[{source.name}] Already processed for both text and images, skipping")
                _mark_file_done_once(source.name)
                _mark_image_done_once(source.name)
                continue

            if pages_needing_text:
                logger.info(
                    f"[{source.name}] Indexing {len(pages_needing_text)} pages for text")
                layout_loader.manifest_for(source)   # fail sớm, một lần/quyển
                _index_source_pages(layout_loader, text_db, status_tracker,
                                    source, pages_needing_text)

            if pages_needing_images:
                logger.info(
                    f"[{source.name}] Extracting images from "
                    f"{len(pages_needing_images)} pages")
                ocr_text_per_page = _load_ocr_text_per_page(
                    ocr_loader, source, pages_needing_images)
                if ocr_text_per_page is None:
                    continue

                image_docs = image_processor.extract_images_from_source(
                    source=source,
                    pages=pages_needing_images,
                    ocr_text_per_page=ocr_text_per_page,
                )
                # Xem chú thích ở `run_etl_image_only`: doc ảnh cũ của đúng những
                # trang này phải đi trước khi ghi bản mới, kể cả khi không còn hình.
                image_vdb.delete_page_documents(source.name, pages_needing_images)
                if image_docs:
                    image_vdb.add_documents(image_docs)
                    logger.info(
                        f"[{source.name}] Added {len(image_docs)} images to ImageVectorDB")

            _mark_file_done_once(source.name)
            _mark_image_done_once(source.name)
            logger.info(f"Completed: {source.name}")

        except Exception as e:
            logger.error(f"Error processing {source.name}: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")

    books.finish()
    logger.info("ETL (FULL) pipeline completed!")


def run_build_manifests(book_name: str = "", *,
                        read_candidates=None, read_toc=None,
                        detect_banner=None, manifest_dir=None,
                        data_dir=None) -> int:
    """Dựng BookManifest cho từng quyển rồi in báo cáo cổng G1.

    Trả 0 nếu G1 PASS, 1 nếu FAIL — để script/CI dùng được mà không phải đọc log
    bằng mắt. Một quyển lỗi KHÔNG giết cả lượt chạy: nó vào phần failures của báo
    cáo, các quyển còn lại vẫn chạy tiếp — nhưng exit code vẫn là 1.

    Ba adapter OCR nhận qua keyword để test bơm fake vào được (main.py import
    lazy nên monkeypatch biến module không dùng được ở đây).
    """
    from src.etl.book.banner import detect_bai_banner
    from src.etl.book.manifest import MANIFEST_DIR, build_manifest, save_manifest
    from src.etl.book.page_map import PageMapError
    from src.etl.book.page_number_ocr import read_page_number_candidates
    from src.etl.book.report import g1_check, g1_report
    from src.etl.book.toc import read_toc as read_toc_default
    from src.etl.page_source import discover_page_sources

    read_candidates = read_candidates or read_page_number_candidates
    read_toc = read_toc or read_toc_default
    detect_banner = detect_banner or detect_bai_banner
    target_dir = Path(manifest_dir) if manifest_dir else MANIFEST_DIR

    sources = discover_page_sources(data_dir or DATA_DIR)
    if book_name:
        sources = [s for s in sources
                   if s.name == book_name or Path(s.name).stem == book_name]
    if not sources:
        print(f"Không tìm thấy quyển nào trong {data_dir or DATA_DIR}")
        return 1

    manifests, failures = [], []
    for source in sources:
        print(f"[manifest] {source.name} …")
        try:
            manifest = build_manifest(
                source,
                read_candidates=read_candidates,
                read_toc=read_toc,
                detect_banner=detect_banner,
            )
        except (PageMapError, ValueError) as exc:
            failures.append(f"{source.name}: {exc}")
            continue
        path = save_manifest(manifest, target_dir)
        print(f"[manifest] -> {path}")
        manifests.append(manifest)

    print(g1_report(manifests))
    for failure in failures:
        print(f"    - {failure}")

    all_ok = bool(manifests) and not failures and all(
        g1_check(m)[0] for m in manifests)
    return 0 if all_ok else 1


def run_build_bm25() -> int:
    """Dựng chỉ mục THƯA (BM25) trên chính `biology_text`. KHÔNG OCR lại.

    Trả 0 khi dựng xong, 1 khi index dày rỗng/không mở được — để chạy trong
    script không cần trông mà vẫn biết kết quả.
    """
    from src.rag.sparse_store import build_sparse_index

    try:
        index = build_sparse_index()
    except Exception as exc:
        print(f"[bm25] LỖI: {exc}")
        return 1
    fp = index.fingerprint
    print(f"[bm25] {len(index.ids)} chunk, {len(index.vocab)} từ vựng, "
          f"độ dài TB {index.avg_len:.1f} token")
    print(f"[bm25] dấu vân: n_chunks={fp.n_chunks} ids_digest={fp.ids_digest[:12]}… "
          f"text_version={fp.text_extraction_version} tokenizer={fp.tokenizer} "
          f"normalizer={fp.normalizer_version}")
    return 0


def run_flask_api(port=5000):
    """Launch Flask API server."""
    logger.info(f"Starting Flask API server on port {port}...")
    from src.app.api import run_api
    run_api(port=port)


def run_export_image_review(output_path: str, pdf_filename: str = "", include_completed: bool = False):
    """Export extracted image metadata for human review/editing."""
    from src.etl import ImageReviewManager

    manager = ImageReviewManager()
    count = manager.export_for_review(
        output_path=output_path,
        pdf_filename=pdf_filename.strip() or None,
        only_pending=not include_completed,
    )
    logger.info(f"Exported {count} image review rows to {output_path}")


def run_export_image_db(output_path: str, pdf_filename: str = ""):
    """Export full image metadata DB snapshot from manifest records."""
    from src.etl import ImageReviewManager

    manager = ImageReviewManager()
    count = manager.export_db_snapshot(
        output_path=output_path,
        pdf_filename=pdf_filename.strip() or None,
    )
    logger.info(f"Exported {count} image DB rows to {output_path}")


def run_upsert_image_review_item(item_path: str, reviewed_by: str = "human"):
    """Upsert a single image metadata JSON object into review DB + vector DB."""
    from src.etl import ImageReviewManager

    payload = json.loads(Path(item_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("--upsert-image-review-item expects a JSON object file")

    manager = ImageReviewManager()
    result = manager.upsert_review_item(item=payload, reviewed_by=reviewed_by)
    logger.info(f"Upserted image review item: {result}")


def run_apply_image_review(review_path: str, reviewed_by: str = "human", pdf_filename: str = ""):
    """Apply human-edited image metadata and sync image vector DB."""
    from src.etl import ImageReviewManager

    manager = ImageReviewManager()
    result = manager.apply_review_updates(
        review_path=review_path,
        reviewed_by=reviewed_by,
        pdf_filename=pdf_filename.strip() or None,
    )
    logger.info(f"Applied image review updates: {result}")


def run_replace_image_db(snapshot_path: str, reviewed_by: str = "human"):
    """Replace image metadata manifest and image vector DB from a snapshot JSON array."""
    from src.etl import ImageReviewManager

    manager = ImageReviewManager()
    result = manager.replace_image_db(snapshot_path=snapshot_path, reviewed_by=reviewed_by)
    logger.info(f"Replaced image DB from snapshot: {result}")


def run_import_images_dir(directory: str):
    """Import a local directory of images, bypassing PDF extraction."""
    from src.etl.local_image_importer import LocalImageImporter
    from src.rag.image_vectorstore import ImageVectorDB

    logger.info(f"Starting local image import from {directory}...")
    importer = LocalImageImporter()
    image_docs = importer.import_directory(directory)
    
    if image_docs:
        logger.info(f"Adding {len(image_docs)} images to ImageVectorDB...")
        image_vdb = ImageVectorDB()
        image_vdb.add_documents(image_docs)
        logger.info("Import completed successfully.")
    else:
        logger.warning("No images imported.")


def main():
    parser = argparse.ArgumentParser(description="Biology RAG System")

    etl_group = parser.add_argument_group("ETL Options")
    etl_group.add_argument("--etl", action="store_true",
                           help="Run full ETL pipeline (text + images)")
    etl_group.add_argument(
        "--text-only",
        action="store_true",
        help="Run ETL for text only. Skips pages already indexed.",
    )
    etl_group.add_argument(
        "--image-only",
        action="store_true",
        help="Run ETL for images only. Skips pages already processed.",
    )
    etl_group.add_argument(
        "--export-image-review",
        type=str,
        default="",
        help="Export image metadata review file (JSON) to this path.",
    )
    etl_group.add_argument(
        "--export-image-db",
        type=str,
        default="",
        help="Export full image metadata DB snapshot (JSON) to this path.",
    )
    etl_group.add_argument(
        "--apply-image-review",
        type=str,
        default="",
        help="Apply reviewed image metadata from a JSON file.",
    )
    etl_group.add_argument(
        "--replace-image-db",
        type=str,
        default="",
        help="Replace image metadata DB from a JSON snapshot and rebuild image index.",
    )
    etl_group.add_argument(
        "--upsert-image-review-item",
        type=str,
        default="",
        help="Upsert one image review item from a JSON object file.",
    )
    etl_group.add_argument(
        "--import-images-dir",
        type=str,
        default="",
        help="Import images directly from a local directory, bypassing PDF extraction.",
    )
    etl_group.add_argument(
        "--review-pdf",
        type=str,
        default="",
        help="Optional PDF filename filter for --export-image-review, --export-image-db, and --apply-image-review.",
    )
    etl_group.add_argument(
        "--review-user",
        type=str,
        default="human",
        help="Reviewer name used by review/apply/upsert/replace commands.",
    )
    etl_group.add_argument(
        "--review-include-completed",
        action="store_true",
        help="Include approved/rejected rows when exporting review file.",
    )
    etl_group.add_argument("--build-bm25", action="store_true",
                           help="Dựng chỉ mục thưa BM25 từ biology_text (không OCR lại)")
    etl_group.add_argument("--build-manifests", action="store_true",
                           help="Dựng BookManifest (bản đồ trang + spine Bài) rồi báo cáo G1")
    etl_group.add_argument("--book", type=str, default="",
                           help="Chỉ xử lý một quyển theo tên thư mục/file (dùng với --build-manifests)")

    parser.add_argument("--api", action="store_true",
                        help="Launch Flask API server")
    parser.add_argument("--port", type=int, default=5000,
                        help="Port for Flask API server (default: 5000)")

    args = parser.parse_args()

    if (
        not args.etl
        and not args.text_only
        and not args.image_only
        and not args.api
        and not args.export_image_review
        and not args.export_image_db
        and not args.apply_image_review
        and not args.replace_image_db
        and not args.upsert_image_review_item
        and not args.import_images_dir
        and not args.build_manifests
        and not args.build_bm25
    ):
        parser.print_help()
        sys.exit(1)

    if args.build_bm25:
        sys.exit(run_build_bm25())

    if args.build_manifests:
        sys.exit(run_build_manifests(args.book))

    if args.import_images_dir:
        run_import_images_dir(args.import_images_dir)

    if args.text_only:
        run_etl_text_only()
    elif args.image_only:
        run_etl_image_only()
    elif args.etl:
        run_etl()

    if args.export_image_review:
        run_export_image_review(
            output_path=args.export_image_review,
            pdf_filename=args.review_pdf,
            include_completed=args.review_include_completed,
        )

    if args.export_image_db:
        run_export_image_db(
            output_path=args.export_image_db,
            pdf_filename=args.review_pdf,
        )

    if args.apply_image_review:
        run_apply_image_review(
            review_path=args.apply_image_review,
            reviewed_by=args.review_user,
            pdf_filename=args.review_pdf,
        )

    if args.replace_image_db:
        run_replace_image_db(snapshot_path=args.replace_image_db, reviewed_by=args.review_user)

    if args.upsert_image_review_item:
        run_upsert_image_review_item(item_path=args.upsert_image_review_item, reviewed_by=args.review_user)

    if args.api:
        run_flask_api(port=args.port)


if __name__ == "__main__":
    main()
