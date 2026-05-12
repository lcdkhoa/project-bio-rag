"""Main entry point for Biology RAG system."""

import argparse
import logging
import os
import sys

from src.config import LOG_LEVEL, DATA_DIR, PERSIST_DIR, PROCESSED_FILES_LOG

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


def run_etl():
    """Run ETL pipeline: PDF loading, OCR, chunking, and storing to ChromaDB."""
    logger.info("Starting ETL pipeline...")

    os.makedirs(PERSIST_DIR, exist_ok=True)

    from tqdm import tqdm
    from src.etl import RobustOCRLoader, TextSplitter
    from src.rag.vectorstore import VectorDB

    loader = RobustOCRLoader()
    text_splitter = TextSplitter()

    vdb = VectorDB()
    db = vdb.db

    import glob
    pdf_files = glob.glob(f"{DATA_DIR}/*.pdf")
    processed_files = get_processed_files()

    if not pdf_files:
        logger.error(f"No PDF files found in {DATA_DIR}")
        return

    logger.info(f"Total PDFs in directory: {len(pdf_files)}")
    logger.info(f"Previously processed: {len(processed_files)}")

    files_to_process = [f for f in pdf_files if os.path.basename(f) not in processed_files]
    logger.info(f"Files to process: {len(files_to_process)}")

    for pdf_file in tqdm(files_to_process, desc="Processing PDFs"):
        filename = os.path.basename(pdf_file)
        logger.info(f"Processing: {filename}")

        try:
            file_docs = loader.load_pdf(pdf_file)
            if file_docs:
                split_docs = text_splitter.split(file_docs)
                logger.info(f"Split into {len(split_docs)} chunks")

                db.add_documents(split_docs)
                mark_file_as_processed(filename)
                logger.info(f"Completed: {filename}")
            else:
                logger.warning(f"No text extracted from {filename}")
                mark_file_as_processed(filename)
        except Exception as e:
            logger.error(f"Error processing {filename}: {e}")

    logger.info("ETL pipeline completed!")


def run_app():
    """Launch Gradio web application."""
    logger.info("Starting Gradio app...")
    from src.app import BiologyAssistantApp

    app = BiologyAssistantApp()
    app.launch(share=False)


def main():
    parser = argparse.ArgumentParser(description="Biology RAG System")
    parser.add_argument("--etl", action="store_true", help="Run ETL pipeline")
    parser.add_argument("--app", action="store_true", help="Launch Gradio web app")
    args = parser.parse_args()

    if not args.etl and not args.app:
        parser.print_help()
        sys.exit(1)

    if args.etl:
        run_etl()
    if args.app:
        run_app()


if __name__ == "__main__":
    main()
