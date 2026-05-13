"""Main entry point for Biology RAG system."""

import argparse
import logging
import os
import sys
from pathlib import Path

from src.config import LOG_LEVEL, DATA_DIR, PERSIST_DIR, IMAGES_DIR, PROCESSED_FILES_LOG

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


def run_etl_text_only():
    """Run ETL pipeline for text only: PDF loading, OCR, chunking, and storing to ChromaDB."""
    logger.info("Starting ETL pipeline (TEXT ONLY)...")

    os.makedirs(PERSIST_DIR, exist_ok=True)

    from tqdm import tqdm
    from src.etl import RobustOCRLoader, TextSplitter, ProcessingStatus, compute_file_hash

    loader = RobustOCRLoader()
    text_splitter = TextSplitter()
    status_tracker = ProcessingStatus()

    from src.rag.vectorstore import VectorDB

    text_vdb = VectorDB()
    text_db = text_vdb.db

    import glob

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

            docs = loader.load_pdf(pdf_file)
            if not docs:
                logger.warning(f"No text extracted from {filename}")
                continue

            ocr_text_per_page = {doc.metadata.get(
                "page", i + 1): doc.page_content for i, doc in enumerate(docs)}

            pages_to_index = status_tracker.get_pages_needing_text(
                pdf_hash, len(docs))
            if not pages_to_index:
                logger.info(
                    f"[{filename}] All pages already indexed, skipping")
                mark_file_as_processed(filename)
                continue

            logger.info(f"[{filename}] Pages to index: {pages_to_index}")

            docs_to_add = [doc for doc in docs if doc.metadata.get(
                "page") in pages_to_index]

            if docs_to_add:
                split_docs = text_splitter.split(docs_to_add)
                logger.info(f"Split into {len(split_docs)} chunks")
                text_db.add_documents(split_docs)

                for page_num in pages_to_index:
                    status_tracker.mark_text_indexed(
                        pdf_hash, page_num, filename)

            mark_file_as_processed(filename)
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
    from src.etl import RobustOCRLoader, ImageProcessor, ProcessingStatus, compute_file_hash

    loader = RobustOCRLoader()
    image_processor = ImageProcessor()
    status_tracker = ProcessingStatus()

    from src.rag.image_vectorstore import ImageVectorDB

    image_vdb = ImageVectorDB()

    import glob

    pdf_files = glob.glob(f"{DATA_DIR}/*.pdf")

    if not pdf_files:
        logger.error(f"No PDF files found in {DATA_DIR}")
        return

    logger.info(f"Total PDFs in directory: {len(pdf_files)}")

    for pdf_file in tqdm(pdf_files, desc="Processing PDFs for images"):
        filename = os.path.basename(pdf_file)
        logger.info(f"Processing: {filename}")

        try:
            pdf_hash = compute_file_hash(pdf_file)

            docs = loader.load_pdf(pdf_file)
            if not docs:
                logger.warning(f"No text extracted from {filename}")
                continue

            ocr_text_per_page = {doc.metadata.get(
                "page", i + 1): doc.page_content for i, doc in enumerate(docs)}

            pages_to_process = status_tracker.get_pages_needing_images(
                pdf_hash, len(docs))
            if not pages_to_process:
                logger.info(
                    f"[{filename}] All pages already processed for images, skipping")
                continue

            logger.info(
                f"[{filename}] Pages to extract images: {pages_to_process}")

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
    from src.etl import RobustOCRLoader, TextSplitter, ImageProcessor, ProcessingStatus, compute_file_hash

    loader = RobustOCRLoader()
    text_splitter = TextSplitter()
    image_processor = ImageProcessor()
    status_tracker = ProcessingStatus()

    from src.rag.vectorstore import VectorDB
    from src.rag.image_vectorstore import ImageVectorDB

    text_vdb = VectorDB()
    image_vdb = ImageVectorDB()

    import glob

    pdf_files = glob.glob(f"{DATA_DIR}/*.pdf")

    if not pdf_files:
        logger.error(f"No PDF files found in {DATA_DIR}")
        return

    logger.info(f"Total PDFs in directory: {len(pdf_files)}")

    for pdf_file in tqdm(pdf_files, desc="Processing PDFs"):
        filename = os.path.basename(pdf_file)
        logger.info(f"Processing: {filename}")

        try:
            pdf_hash = compute_file_hash(pdf_file)

            docs = loader.load_pdf(pdf_file)
            if not docs:
                logger.warning(f"No text extracted from {filename}")
                continue

            ocr_text_per_page = {doc.metadata.get(
                "page", i + 1): doc.page_content for i, doc in enumerate(docs)}

            pages_needing_text = status_tracker.get_pages_needing_text(
                pdf_hash, len(docs))
            if pages_needing_text:
                logger.info(
                    f"[{filename}] Indexing {len(pages_needing_text)} pages for text")
                docs_to_add = [doc for doc in docs if doc.metadata.get(
                    "page") in pages_needing_text]
                if docs_to_add:
                    split_docs = text_splitter.split(docs_to_add)
                    text_vdb.db.add_documents(split_docs)
                    for page_num in pages_needing_text:
                        status_tracker.mark_text_indexed(
                            pdf_hash, page_num, filename)

            pages_needing_images = status_tracker.get_pages_needing_images(
                pdf_hash, len(docs))
            if pages_needing_images:
                logger.info(
                    f"[{filename}] Extracting images from {len(pages_needing_images)} pages")
                image_docs = image_processor.extract_images_from_pdf(
                    pdf_path=pdf_file,
                    pdf_hash=pdf_hash,
                    pdf_filename=filename,
                    ocr_text_per_page=ocr_text_per_page,
                )
                if image_docs:
                    image_vdb.add_documents(image_docs)

            mark_file_as_processed(filename)
            logger.info(f"Completed: {filename}")

        except Exception as e:
            logger.error(f"Error processing {filename}: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")

    logger.info("ETL (FULL) pipeline completed!")


def run_app():
    """Launch Gradio web application."""
    logger.info("Starting Gradio app...")
    from src.app import BiologyAssistantApp

    app = BiologyAssistantApp()
    app.launch(share=True)


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

    parser.add_argument("--app", action="store_true",
                        help="Launch Gradio web app")

    args = parser.parse_args()

    if not args.etl and not args.text_only and not args.image_only and not args.app:
        parser.print_help()
        sys.exit(1)

    if args.text_only:
        run_etl_text_only()
    elif args.image_only:
        run_etl_image_only()
    elif args.etl:
        run_etl()

    if args.app:
        run_app()


if __name__ == "__main__":
    main()
