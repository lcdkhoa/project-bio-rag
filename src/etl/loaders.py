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
    """OCR cả trang (Tesseract, tiếng Việt).

    KHÔNG còn là đường text của hệ thống — đường đó là `LayoutOCRLoader` (OCR
    theo vùng). Cái này chỉ còn cung cấp text cả trang cho phía ẢNH dùng làm
    ngữ cảnh/neo caption.

    `--psm 6` (một khối văn bản) thay cho psm 3 mặc định: đo trên trang thật của
    nguồn PNG (spec §1.3), psm 3 ra 134 từ / psm 11 ra 150 / psm 6 ra 194 trên
    cùng một trang, và cái psm 3 đánh rơi gồm **đúng nhãn pill "Hình N.M"** mà
    phía ảnh dựa vào để neo. Đổi lại, psm 6 không bảo đảm thứ tự đọc trên trang
    hai cột — chấp nhận được cho ngữ cảnh, và ảnh hưởng tới phía ảnh thì CHƯA
    được đo (câu hỏi mở §5).
    """

    PSM = 6

    def ocr_image(self, image) -> str:
        """OCR một trang đã nạp (mảng numpy hoặc PIL) -> text đã làm sạch."""
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        raw = pytesseract.image_to_string(image, lang="vie",
                                          config=f"--psm {self.PSM}")
        return clean_vietnamese_text(raw)

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
