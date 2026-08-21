"""Main entry point for Biology RAG system."""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from src.config import LOG_LEVEL, DATA_DIR, PERSIST_DIR, IMAGES_DIR, PROCESSED_FILES_LOG, PROCESSED_IMAGES_LOG

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


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


def _should_skip_file(filename, pages_needing_text):
    """Skip only when the CONTENT (via hash-based status) has no pages left.
    A replaced same-named file (new hash) will report pages_needing_text and
    therefore NOT be skipped."""
    return len(pages_needing_text) == 0


def _index_pdf_pages(loader, text_db, status_tracker, pdf_file, pdf_hash, filename, pages_to_index):
    """Index only the pages that still need text (resume-safe).

    Loads and adds one page at a time via `loader.load_page` (0-based index),
    using a deterministic id per chunk (`{pdf_hash}_p{page_num}_c{chunk_index}`)
    so re-adding an already-indexed page upserts instead of creating duplicate
    rows. Marks each page as indexed even when it produced no chunks, so it
    isn't retried forever.

    A page that raises is logged and skipped, leaving it unmarked so the next
    run retries it. Isolating the failure per page matters for --etl, where the
    image side of the same book runs after this call and should not be lost to
    one bad page.
    """
    for page_num in pages_to_index:
        try:
            page_docs = loader.load_page(pdf_file, page_num - 1)
            if page_docs:
                ids = [f"{pdf_hash}_p{page_num}_c{d.metadata['chunk_index']}" for d in page_docs]
                text_db.add_documents(page_docs, ids=ids)
            status_tracker.mark_text_indexed(pdf_hash, page_num, filename)
        except Exception as e:
            logger.error(f"[{filename}] page {page_num} text indexing failed: {e}")


def _pdf_page_count(pdf_file) -> int:
    """Page count without OCR - used to size the checkpoint queries cheaply."""
    import fitz

    doc = fitz.open(pdf_file)
    try:
        return len(doc)
    finally:
        doc.close()


def _pages_needing_images(status_tracker, image_processor, pdf_hash, num_pages):
    """Pages whose image extraction is missing or stale for the processor's version."""
    return [
        page_num
        for page_num in range(1, num_pages + 1)
        if status_tracker.needs_image_processing_versioned(
            pdf_hash,
            page_num,
            required_version=image_processor.image_extraction_version,
        )
    ]


def _load_ocr_text_per_page(ocr_loader, pdf_file, filename):
    """Whole-book OCR text keyed by 1-based page, for figure-caption anchoring.

    Returns None when the PDF yielded no text at all, so callers can skip it.
    """
    docs = ocr_loader.load_pdf(pdf_file)
    if not docs:
        logger.warning(f"No text extracted from {filename}")
        return None
    return {
        doc.metadata.get("page", i + 1): doc.page_content
        for i, doc in enumerate(docs)
    }


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
    """Run ETL pipeline for text only: PDF loading, OCR, chunking, and storing to ChromaDB."""
    logger.info("Starting ETL pipeline (TEXT ONLY)...")

    os.makedirs(PERSIST_DIR, exist_ok=True)

    from tqdm import tqdm
    from src.etl import LayoutOCRLoader, ProcessingStatus, compute_file_hash

    loader = LayoutOCRLoader()
    status_tracker = ProcessingStatus()

    from src.rag.vectorstore import VectorDB

    text_vdb = VectorDB()
    text_db = text_vdb.db

    import glob
    import fitz

    pdf_files = glob.glob(f"{DATA_DIR}/*.pdf")

    if not pdf_files:
        logger.error(f"No PDF files found in {DATA_DIR}")
        return

    logger.info(f"Total PDFs in directory: {len(pdf_files)}")

    processed_files = get_processed_files()
    logger.info(f"Previously processed files: {len(processed_files)}")

    for pdf_file in tqdm(pdf_files, desc="Processing PDFs for text"):
        filename = os.path.basename(pdf_file)

        logger.info(f"Processing: {filename}")

        try:
            pdf_hash = compute_file_hash(pdf_file)

            fitz_doc = fitz.open(pdf_file)
            num_pages = len(fitz_doc)
            fitz_doc.close()

            pages_to_index = status_tracker.get_pages_needing_text(
                pdf_hash, num_pages)

            if _should_skip_file(filename, pages_to_index):
                logger.info(
                    f"[{filename}] All pages already indexed, skipping")
                _mark_file_done_once(filename)
                continue

            logger.info(f"[{filename}] Pages to index (1-based PDF index): {pages_to_index}")

            _index_pdf_pages(loader, text_db, status_tracker, pdf_file,
                              pdf_hash, filename, pages_to_index)

            _mark_file_done_once(filename)
            logger.info(f"Completed: {filename}")

        except Exception as e:
            logger.error(f"Error processing {filename}: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")

    logger.info("ETL (TEXT) pipeline completed!")


def run_etl_image_only():
    """Run ETL pipeline for images only: extract, filter, caption, and store images."""
    logger.info("Starting ETL pipeline (IMAGE ONLY)...")

    os.makedirs(IMAGES_DIR, exist_ok=True)
    os.makedirs(PERSIST_DIR, exist_ok=True)

    from tqdm import tqdm
    from src.etl import RobustOCRLoader, ProcessingStatus, compute_file_hash, make_image_processor

    ocr_loader = RobustOCRLoader()
    status_tracker = ProcessingStatus()

    from src.rag.image_vectorstore import ImageVectorDB

    image_vdb = ImageVectorDB()

    import glob

    pdf_files = glob.glob(f"{DATA_DIR}/*.pdf")

    if not pdf_files:
        logger.error(f"No PDF files found in {DATA_DIR}")
        return

    logger.info(f"Total PDFs in directory: {len(pdf_files)}")

    # processed_images.txt is advisory (progress reporting) only. The skip
    # decision comes from ProcessingStatus, which is keyed on content hash AND
    # extraction version, so a bumped IMAGE_EXTRACTION_VERSION or a replaced
    # same-name PDF is acted on instead of being masked by the filename log.
    logger.info(
        f"Previously processed files for images: {len(get_processed_images())}")

    for pdf_file in tqdm(pdf_files, desc="Processing PDFs for images"):
        filename = os.path.basename(pdf_file)

        logger.info(f"Processing: {filename}")

        # Per-variant processor (CTST/KNTT get their subclasses); shares the
        # single status_tracker so the versioned checkpoint stays consistent.
        image_processor = make_image_processor(filename, status_tracker=status_tracker)

        try:
            pdf_hash = compute_file_hash(pdf_file)
            num_pages = _pdf_page_count(pdf_file)

            pages_to_process = _pages_needing_images(
                status_tracker, image_processor, pdf_hash, num_pages)

            if not pages_to_process:
                logger.info(
                    f"[{filename}] All pages already processed for images, skipping")
                _mark_image_done_once(filename)
                continue

            logger.info(
                f"[{filename}] Pages to extract images: {pages_to_process}")

            # OCR runs only once there is work to do: the image processor needs
            # whole-page text to anchor figure captions.
            ocr_text_per_page = _load_ocr_text_per_page(ocr_loader, pdf_file, filename)
            if ocr_text_per_page is None:
                continue

            image_docs = image_processor.extract_images_from_pdf(
                pdf_path=pdf_file,
                pdf_hash=pdf_hash,
                pdf_filename=filename,
                ocr_text_per_page=ocr_text_per_page,
            )

            if image_docs:
                image_vdb.add_documents(image_docs)
                logger.info(
                    f"[{filename}] Added {len(image_docs)} images to ImageVectorDB")

            _mark_image_done_once(filename)
            logger.info(f"Completed images for: {filename}")

        except Exception as e:
            logger.error(f"Error processing {filename}: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")

    logger.info("ETL (IMAGE) pipeline completed!")


def run_etl():
    """Run full ETL pipeline: both text and images."""
    logger.info("Starting ETL pipeline (FULL)...")

    os.makedirs(IMAGES_DIR, exist_ok=True)
    os.makedirs(PERSIST_DIR, exist_ok=True)

    from tqdm import tqdm
    from src.etl import (
        LayoutOCRLoader,
        RobustOCRLoader,
        ProcessingStatus,
        compute_file_hash,
        make_image_processor,
    )

    # Text goes through the layout-aware loader, exactly like --text-only, so
    # both entrypoints produce the same index: chunks carrying
    # variant/region_type/chunk_index, with sidebar/info-boxes kept as separate
    # labeled chunks (citations read region_type). RobustOCRLoader is still
    # needed for whole-page OCR text, which anchors figure captions.
    layout_loader = LayoutOCRLoader()
    ocr_loader = RobustOCRLoader()
    status_tracker = ProcessingStatus()

    from src.rag.vectorstore import VectorDB
    from src.rag.image_vectorstore import ImageVectorDB

    text_vdb = VectorDB()
    text_db = text_vdb.db
    image_vdb = ImageVectorDB()

    import glob

    pdf_files = glob.glob(f"{DATA_DIR}/*.pdf")

    if not pdf_files:
        logger.error(f"No PDF files found in {DATA_DIR}")
        return

    logger.info(f"Total PDFs in directory: {len(pdf_files)}")

    # Both logs are advisory (progress reporting) only - ProcessingStatus is the
    # truth source, keyed on content hash and extraction version.
    logger.info(
        f"Previously processed files: text={len(get_processed_files())}, "
        f"images={len(get_processed_images())}")

    for pdf_file in tqdm(pdf_files, desc="Processing PDFs"):
        filename = os.path.basename(pdf_file)

        logger.info(f"Processing: {filename}")

        # Per-variant processor (CTST/KNTT get their subclasses); shares the
        # single status_tracker so the versioned checkpoint stays consistent.
        image_processor = make_image_processor(filename, status_tracker=status_tracker)

        try:
            pdf_hash = compute_file_hash(pdf_file)
            num_pages = _pdf_page_count(pdf_file)

            pages_needing_text = status_tracker.get_pages_needing_text(
                pdf_hash, num_pages)
            pages_needing_images = _pages_needing_images(
                status_tracker, image_processor, pdf_hash, num_pages)

            if not pages_needing_text and not pages_needing_images:
                logger.info(
                    f"[{filename}] Already processed for both text and images, skipping")
                _mark_file_done_once(filename)
                _mark_image_done_once(filename)
                continue

            if pages_needing_text:
                logger.info(
                    f"[{filename}] Indexing {len(pages_needing_text)} pages for text")
                _index_pdf_pages(layout_loader, text_db, status_tracker, pdf_file,
                                 pdf_hash, filename, pages_needing_text)

            if pages_needing_images:
                logger.info(
                    f"[{filename}] Extracting images from {len(pages_needing_images)} pages")
                ocr_text_per_page = _load_ocr_text_per_page(
                    ocr_loader, pdf_file, filename)
                if ocr_text_per_page is None:
                    continue

                image_docs = image_processor.extract_images_from_pdf(
                    pdf_path=pdf_file,
                    pdf_hash=pdf_hash,
                    pdf_filename=filename,
                    ocr_text_per_page=ocr_text_per_page,
                )
                if image_docs:
                    image_vdb.add_documents(image_docs)
                    logger.info(
                        f"[{filename}] Added {len(image_docs)} images to ImageVectorDB")

            # Advisory logs are written for both sides once this book's work for
            # the run finished, so a book that only needed one side still ends up
            # recorded on both and the two logs don't drift apart.
            _mark_file_done_once(filename)
            _mark_image_done_once(filename)
            logger.info(f"Completed: {filename}")

        except Exception as e:
            logger.error(f"Error processing {filename}: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")

    logger.info("ETL (FULL) pipeline completed!")


def run_build_manifests(pdf_filename: str = "", *,
                        read_candidates=None, read_toc=None,
                        detect_banner=None, manifest_dir=None) -> int:
    """Dựng BookManifest cho từng PDF rồi in báo cáo cổng G1.

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
    from src.etl.book.toc import read_toc_lines

    read_candidates = read_candidates or read_page_number_candidates
    read_toc = read_toc or read_toc_lines
    detect_banner = detect_banner or detect_bai_banner
    target_dir = Path(manifest_dir) if manifest_dir else MANIFEST_DIR

    pdfs = sorted(Path(DATA_DIR).glob("*.pdf"))
    if pdf_filename:
        pdfs = [p for p in pdfs if p.name == pdf_filename]
    if not pdfs:
        print(f"Không tìm thấy PDF nào trong {DATA_DIR}")
        return 1

    manifests, failures = [], []
    for pdf in pdfs:
        print(f"[manifest] {pdf.name} …")
        try:
            manifest = build_manifest(
                str(pdf),
                read_candidates=read_candidates,
                read_toc=read_toc,
                detect_banner=detect_banner,
            )
        except PageMapError as exc:
            failures.append(f"{pdf.name}: {exc}")
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
    etl_group.add_argument("--build-manifests", action="store_true",
                           help="Dựng BookManifest (bản đồ trang + spine Bài) rồi báo cáo G1")
    etl_group.add_argument("--book", type=str, default="",
                           help="Chỉ xử lý một PDF theo tên file (dùng với --build-manifests)")

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
    ):
        parser.print_help()
        sys.exit(1)

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
