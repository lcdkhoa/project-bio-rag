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
        try:
            docs = self.retriever.invoke(question)
            if not docs:
                return "Hệ thống chưa tìm thấy tài liệu nào liên quan đến câu hỏi này."

            context_texts = []
            citations = set()
            for doc in docs:
                context_texts.append(doc.page_content)
                source_file = doc.metadata.get("source", "Sách Giáo Khoa")
                page_num = doc.metadata.get("page", "Không rõ")
                citations.add(f"📖 {source_file} (Trang {page_num})")

            context_str = "\n\n".join(context_texts)
            answer = self.rag_chain.invoke({"context": context_str, "question": question})

            if "không được đề cập" in answer.lower():
                return answer

            return f"{answer}\n\n📚 Thông tin được tham khảo từ:\n" + "\n".join(citations)
        except Exception as e:
            logger.error(f"Error answering question: {e}")
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
