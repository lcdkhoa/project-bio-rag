"""RAG chain assembly for biology question answering."""

import re
import logging
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger(__name__)


class FocusedAnswerParser(StrOutputParser):
    """Parse and clean LLM responses."""

    def parse(self, text: str) -> str:
        logger.debug(f"Parser received type: {type(text)}, value: {repr(text)[:300]}")
        if isinstance(text, dict):
            logger.warning(f"Parser received dict, keys: {text.keys()}")
            text = text.get("answer") or text.get("text") or str(text)
            logger.warning(f"Parser dict converted to: {repr(text)[:200]}")
        text = str(text).strip()
        text = text.strip()
        if "<|im_start|>assistant" in text:
            text = text.split("<|im_start|>assistant")[-1]
        text = text.replace("<|im_end|>", "").strip()
        text = re.sub(r"^\s*[\-\*]\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\n+", " ", text)
        lines = [line.strip() for line in text.split(".") if line.strip() and len(line.strip()) > 5]
        return ". ".join(lines[:6]) + ("." if lines else "")


class BiologyRAG:
    """RAG chain for biology question answering."""

    def __init__(self, llm):
        self.llm = llm
        self.prompt = PromptTemplate.from_template(
            """<|im_start|>system
Bạn là trợ lý AI môn Khoa học tự nhiên (Vật lí – Hoá học – Sinh học) bậc THCS. Bạn PHẢI trả lời hoàn toàn bằng TIẾNG VIỆT.<|im_end|>
<|im_start|>user
[TÀI LIỆU SÁCH GIÁO KHOA]:
{context}

[CÂU HỎI]:
{question}

[QUY TẮC NGHIÊM NGẶT]:
1. CHỈ dùng thông tin trong tài liệu trên. KHÔNG tự suy diễn, KHÔNG bịa.
2. CHỈ trả lời ĐÚNG nội dung được hỏi. KHÔNG thêm thông tin không liên quan đến câu hỏi.
3. KHÔNG ghép nối các thông tin rời rạc từ những đoạn khác chủ đề để tạo câu trả lời.
4. Nếu một đoạn tài liệu không liên quan đến câu hỏi, hãy BỎ QUA đoạn đó.
5. Nếu tài liệu không chứa câu trả lời, hãy trả lời ĐÚNG CÂU SAU: "Thông tin này không được đề cập trong sách giáo khoa."<|im_end|>
<|im_start|>assistant
"""
        )
        self.answer_parser = FocusedAnswerParser()

    # ĐÃ XOÁ `get_chain` + `format_docs` (2026-08-25, D-86). Chúng là code
    # CHẾT trong đường phục vụ: `grep -rn rag_chain src/ main.py` chỉ trúng
    # đúng một chỗ dựng nó ở `dependencies.py` và KHÔNG chỗ nào gọi. Đường thật
    # là `api.py::prepare_chat_payload` -> `prompt.format(...)` ->
    # `stream_llm_text` -> `answer_parser`.
    #
    # Hệ quả đo được: bộ lọc "bỏ mọi đoạn <= 40 ký tự" của `format_docs` CHƯA
    # TỪNG chạm một câu trả lời nào. Nên con số 1 090/16 393 = 6,65% chunk ngắn
    # (đo lại 2026-08-25, khớp D-76) KHÔNG phải là mất mát ở production — và
    # "hạ ngưỡng 40" là một bản vá cho code chết. Ngữ cảnh thật do
    # `src/rag/multimodal_context.py::build_context` dựng, không lọc theo độ dài.
