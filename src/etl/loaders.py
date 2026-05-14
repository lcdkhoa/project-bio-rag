"""Document loaders for PDF files."""

import glob
import logging
from pathlib import Path
from typing import List

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document

from ..config import POPPLER_PATH, TESSERACT_CMD
from .cleaner import clean_vietnamese_text

logger = logging.getLogger(__name__)


class SimpleLoader:
    """Load PDFs using PyPDFLoader with image extraction."""

    def load_pdf(self, pdf_file: str) -> List[Document]:
        docs = PyPDFLoader(pdf_file, extract_images=True).load()
        for doc in docs:
            doc.page_content = clean_vietnamese_text(doc.page_content)
        return docs

    def load_dir(self, dir_path: str) -> List[Document]:
        pdf_files = glob.glob(f"{dir_path}/*.pdf")
        if not pdf_files:
            raise ValueError(f"No PDF files found in {dir_path}")

        all_docs = []
        for pdf_file in pdf_files:
            try:
                all_docs.extend(self.load_pdf(pdf_file))
            except Exception as e:
                logger.error(f"Error loading {pdf_file}: {e}")
        return all_docs


class RobustOCRLoader:
    """Load PDFs using OCR (Tesseract) for better Vietnamese support."""

    def load_pdf(self, pdf_file: str) -> List[Document]:
        import time
        from pdf2image import convert_from_path
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

        docs = []
        try:
            images = convert_from_path(pdf_file, poppler_path=POPPLER_PATH)
            total_pages = len(images)
            logger.info(f"[{Path(pdf_file).name}] Starting OCR on {total_pages} pages")

            for i, img in enumerate(images):
                start_time = time.time()
                raw_text = pytesseract.image_to_string(img, lang="vie")
                elapsed = time.time() - start_time

                logger.info(
                    f"[{Path(pdf_file).name}] Page {i + 1}/{total_pages} completed in {elapsed:.2f}s"
                )

                cleaned_text = clean_vietnamese_text(raw_text)
                if cleaned_text and len(cleaned_text) > 10:
                    doc = Document(
                        page_content=cleaned_text,
                        metadata={"source": Path(pdf_file).name, "page": i + 1},
                    )
                    docs.append(doc)
        except Exception as e:
            logger.error(f"OCR error for {pdf_file}: {e}")
        return docs

    def load_dir(self, dir_path: str) -> List[Document]:
        pdf_files = glob.glob(f"{dir_path}/*.pdf")
        all_docs = []
        for pdf_file in pdf_files:
            all_docs.extend(self.load_pdf(pdf_file))
        return all_docs
