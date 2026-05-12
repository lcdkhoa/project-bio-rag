"""Biology RAG - Gradio web application."""

import logging
import gradio as gr

from src.config import GRADIO_SERVER_NAME, GRADIO_SERVER_PORT
from src.rag import VectorDB, get_hf_llm, BiologyRAG

logger = logging.getLogger(__name__)


class BiologyAssistantApp:
    """Gradio-based web interface for biology RAG."""

    def __init__(self):
        logger.info("Initializing Biology Assistant App...")
        self.vdb = VectorDB()
        self.retriever = self.vdb.get_retriever()
        self.llm = get_hf_llm()
        self.rag = BiologyRAG(self.llm)
        self.rag_chain = self.rag.get_chain(self.retriever)
        logger.info("App components initialized")

    def answer_question(self, question: str) -> str:
        """Answer a biology question using RAG."""
        logger.info(f"Processing question: {question[:100]}...")
        try:
            # Step 1: Test retriever alone
            logger.info("Step 1: Testing retriever.invoke()...")
            try:
                docs = self.retriever.invoke(question)
                logger.info(f"Step 1 SUCCESS: Retrieved {len(docs)} documents")
            except Exception as e:
                logger.error(f"Step 1 FAILED retriever.invoke: {e}", exc_info=True)
                return f"Lỗi retriever: {str(e)}"

            logger.debug(f"Retrieved docs types: {[type(d) for d in docs]}")
            for i, doc in enumerate(docs):
                doc_type = type(doc)
                if doc_type.__name__ == 'Document':
                    content_type = type(doc.page_content)
                    logger.debug(f"Doc {i}: Document, content_type={content_type}, content_preview={repr(doc.page_content[:50])}")
                    logger.debug(f"  metadata: {doc.metadata}")
                else:
                    logger.warning(f"Doc {i}: NOT a Document, type={doc_type}, value={repr(doc)[:100]}")

            if not docs:
                return "Hệ thống chưa tìm thấy tài liệu nào liên quan đến câu hỏi này."

            context_texts = []
            citations = set()
            for doc in docs:
                if hasattr(doc, 'page_content'):
                    context_texts.append(doc.page_content)
                    source_file = doc.metadata.get("source", "Sách Giáo Khoa") if hasattr(doc, 'metadata') else "Unknown"
                    page_num = doc.metadata.get("page", "Không rõ") if hasattr(doc, 'metadata') else "?"
                else:
                    logger.warning(f"Doc {i} has no page_content attribute, skipping")
                    continue
                citations.add(f"📖 {source_file} (Trang {page_num})")

            logger.debug(f"Context texts combined, {len(context_texts)} docs, citations: {citations}")

            context_str = "\n\n".join(context_texts)

            # Step 2: Test prompt formatting alone
            logger.info("Step 2: Testing prompt.format()...")
            try:
                formatted_prompt = self.rag.prompt.format(context=context_str, question=question)
                logger.info(f"Step 2 SUCCESS: Prompt formatted, length={len(formatted_prompt)}")
            except Exception as e:
                logger.error(f"Step 2 FAILED prompt.format: {e}", exc_info=True)
                return f"Lỗi prompt: {str(e)}"

            # Step 3: Test LLM alone
            logger.info("Step 3: Testing llm.invoke()...")
            try:
                llm_response = self.llm.invoke(formatted_prompt)
                logger.info(f"Step 3 SUCCESS: LLM response type={type(llm_response)}, preview={repr(str(llm_response)[:100])}")
            except Exception as e:
                logger.error(f"Step 3 FAILED llm.invoke: {e}", exc_info=True)
                return f"Lỗi LLM: {str(e)}"

            # Step 4: Parse response
            logger.info("Step 4: Testing answer_parser.parse()...")
            try:
                parsed = self.rag.answer_parser.parse(llm_response)
                logger.info(f"Step 4 SUCCESS: Parsed answer preview={repr(parsed[:100])}")
            except Exception as e:
                logger.error(f"Step 4 FAILED answer_parser.parse: {e}", exc_info=True)
                return f"Lỗi parser: {str(e)}"

            answer = parsed
            logger.debug(f"Final answer type: {type(answer)}, answer: {repr(answer[:200] if len(str(answer)) > 200 else answer)}")

            if "không được đề cập" in answer.lower():
                return answer

            return f"{answer}\n\n📚 Thông tin được tham khảo từ:\n" + "\n".join(citations)
        except Exception as e:
            logger.error(f"Error answering question: {e}", exc_info=True)
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return f"Lỗi hệ thống: {str(e)}"

    def build_ui(self):
        """Build Gradio interface."""
        with gr.Blocks(title="Trợ lý ảo Sinh Học THCS", theme=gr.themes.Soft()) as demo:
            gr.Markdown("# 🧬 Trợ Lý Ảo Hỗ Trợ Học Tập Môn Sinh Học")
            gr.Markdown("*Hệ thống AI RAG xây dựng dựa trên Sách Giáo Khoa Sinh học THCS.*")

            with gr.Row():
                with gr.Column(scale=1):
                    question_input = gr.Textbox(
                        label="Câu hỏi của bạn",
                        placeholder="Ví dụ: Tế bào là gì? Vì sao nói tế bào là đơn vị cơ bản của sự sống?",
                        lines=4,
                    )
                    submit_btn = gr.Button("Gửi câu hỏi", variant="primary")

                with gr.Column(scale=2):
                    answer_output = gr.Textbox(
                        label="Trợ lý AI trả lời",
                        lines=8,
                        interactive=False,
                    )

            submit_btn.click(
                fn=self.answer_question,
                inputs=question_input,
                outputs=answer_output,
            )

        return demo

    def launch(self, share: bool = False):
        """Launch the Gradio app."""
        demo = self.build_ui()
        logger.info(f"Launching Gradio app on {GRADIO_SERVER_NAME}:{GRADIO_SERVER_PORT}")
        demo.launch(server_name=GRADIO_SERVER_NAME, server_port=GRADIO_SERVER_PORT, share=share)
