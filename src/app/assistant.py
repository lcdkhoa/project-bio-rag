"""Biology RAG - Gradio web application with hybrid text + image retrieval."""

import logging
import os
from pathlib import Path

import gradio as gr

from src.config import GRADIO_SERVER_NAME, GRADIO_SERVER_PORT, IMAGES_DIR
from src.rag import VectorDB, get_hf_llm, BiologyRAG, HybridRetriever, SearchResult

logger = logging.getLogger(__name__)


class BiologyAssistantApp:
    """Gradio-based web interface for biology RAG with hybrid text + image search."""

    def __init__(self):
        logger.info("Initializing Biology Assistant App...")
        self.vdb = VectorDB()
        self.hybrid_retriever = HybridRetriever()
        self.llm = get_hf_llm()
        self.rag = BiologyRAG(self.llm)
        self.rag_chain = self.rag.get_chain(self.vdb.get_retriever())
        logger.info("App components initialized")

    def _build_citations(self, docs) -> str:
        """Build citation string from documents."""
        citations = set()
        for doc in docs:
            if hasattr(doc, "metadata"):
                source = doc.metadata.get("source", "Sách Giáo Khoa")
                page = doc.metadata.get("page", "?")
            else:
                source, page = "Sách Giáo Khoa", "?"
            citations.add(f"Trang {page} - {source}")
        return " | ".join(sorted(citations)) if citations else ""

    def _format_image_gallery(self, image_docs) -> list:
        """Format image documents for Gradio gallery display."""
        if not image_docs:
            logger.debug("No image docs to format")
            return []

        gallery_items = []
        for doc in image_docs:
            if hasattr(doc, "metadata"):
                image_path = doc.metadata.get("image_path", "")
                caption = doc.page_content or doc.metadata.get("caption", "")
                page = doc.metadata.get("page_number", "?")
                pdf = doc.metadata.get("pdf_filename", "Sách Giáo Khoa")
                logger.debug(f"Image doc metadata: image_path={image_path}, page={page}, pdf={pdf}")
                logger.debug(f"Image exists check: {os.path.exists(image_path) if image_path else 'No path'}")
            else:
                logger.warning("Image doc has no metadata")
                continue

            if image_path and os.path.exists(image_path):
                label = f"{caption[:80]}... (Trang {page}, {pdf})" if caption else f"Trang {page} - {pdf}"
                gallery_items.append((image_path, label))
            else:
                logger.warning(f"Image path missing or file not found: {image_path}")

        logger.info(f"Formatted {len(gallery_items)} images for gallery (from {len(image_docs)} retrieved)")
        return gallery_items

    def answer_question(self, question: str) -> tuple:
        """
        Answer a biology question using hybrid RAG (text + images).

        Returns:
            Tuple of (answer_text, image_gallery)
        """
        logger.info(f"Processing question: {question[:100]}...")
        try:
            result: SearchResult = self.hybrid_retriever.search(question)

            text_docs = result.text_docs
            image_docs = result.image_docs

            logger.info(f"Retrieved {len(text_docs)} text docs, {len(image_docs)} image docs")

            if not text_docs and not image_docs:
                return (
                    "Hệ thống chưa tìm thấy tài liệu nào liên quan đến câu hỏi này.",
                    None,
                )

            if text_docs:
                context_texts = []
                for doc in text_docs:
                    if hasattr(doc, "page_content"):
                        context_texts.append(doc.page_content)

                context_str = "\n\n".join(context_texts)
                citations = self._build_citations(text_docs)

                try:
                    formatted_prompt = self.rag.prompt.format(context=context_str, question=question)
                    llm_response = self.llm.invoke(formatted_prompt)
                    parsed = self.rag.answer_parser.parse(llm_response)
                    answer = parsed
                except Exception as e:
                    logger.error(f"RAG chain failed: {e}")
                    answer = "Xin lỗi, đã xảy ra lỗi khi tạo câu trả lời."

                if "không được đề cập" not in answer.lower():
                    answer = f"{answer}\n\n📚 Thông tin được tham khảo từ: {citations}"
            else:
                answer = "Không tìm thấy thông tin dạng văn bản liên quan. Vui lòng thử câu hỏi khác."

            gallery = self._format_image_gallery(image_docs)
            logger.info(f"Returning answer and {len(gallery)} gallery images")
            return answer, gallery

        except Exception as e:
            logger.error(f"Error answering question: {e}", exc_info=True)
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            return f"Lỗi hệ thống: {str(e)}", None

    def build_ui(self):
        """Build Gradio interface with text + image output."""
        with gr.Blocks(title="Trợ lý ảo Sinh Học THCS", theme=gr.themes.Soft()) as demo:
            gr.Markdown("# 🧬 Trợ Lý Ảo Hỗ Trợ Học Tập Môn Sinh Học")
            gr.Markdown(
                "*Hệ thống AI RAG xây dựng dựa trên Sách Giáo Khoa Sinh học THCS. "
                "Hỗ trợ tìm kiếm hình ảnh minh họa.*"
            )

            with gr.Row():
                with gr.Column(scale=1):
                    question_input = gr.Textbox(
                        label="Câu hỏi của bạn",
                        placeholder="Ví dụ: Tế bào là gì? Vì sao nói tế bào là đơn vị cơ bản của sự sống?",
                        lines=4,
                    )
                    submit_btn = gr.Button("Gửi câu hỏi", variant="primary")
                    clear_btn = gr.Button("Xóa", variant="secondary")

                with gr.Column(scale=2):
                    answer_output = gr.Textbox(
                        label="Trợ lý AI trả lời",
                        lines=8,
                        interactive=False,
                    )
                    image_gallery = gr.Gallery(
                        label="Hình ảnh liên quan",
                        columns=3,
                        height="auto",
                        object_fit="contain",
                    )

            submit_btn.click(
                fn=self.answer_question,
                inputs=question_input,
                outputs=[answer_output, image_gallery],
            )

            clear_btn.click(
                fn=lambda: ("", None),
                outputs=[answer_output, image_gallery],
            )

            gr.Markdown(
                "---"
            )
            gr.Markdown(
                "**Mẹo:** Hỏi về hình ảnh bằng cách nói 'tìm hình...' hoặc 'cho xem ảnh...' "
                "để hiển thị hình minh họa từ sách giáo khoa."
            )

        return demo

    def launch(self, share: bool = False):
        """Launch the Gradio app."""
        demo = self.build_ui()
        logger.info(f"Launching Gradio app on {GRADIO_SERVER_NAME}:{GRADIO_SERVER_PORT}")
        demo.launch(server_name=GRADIO_SERVER_NAME, server_port=GRADIO_SERVER_PORT, share=share)