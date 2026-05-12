"""RAG chain assembly for biology question answering."""

import re
import logging
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger(__name__)


class FocusedAnswerParser(StrOutputParser):
    """Parse and clean LLM responses."""

    def parse(self, text: str) -> str:
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
Bạn là trợ lý AI môn Sinh học THCS. Bạn PHẢI trả lời hoàn toàn bằng TIẾNG VIỆT.<|im_end|>
<|im_start|>user
[TÀI LIỆU SÁCH GIÁO KHOA]:
{context}

[CÂU HỎI]:
{question}

[QUY TẮC NGHIÊM NGẶT]:
1. CHỈ dùng thông tin trong tài liệu trên. KHÔNG tự suy diễn.
2. Nếu tài liệu không chứa câu trả lời, hãy trả lời ĐÚNG CÂU SAU: "Thông tin này không được đề cập trong sách giáo khoa."<|im_end|>
<|im_start|>assistant
"""
        )
        self.answer_parser = FocusedAnswerParser()

    def get_chain(self, retriever):
        def format_docs(docs):
            formatted = []
            seen = set()
            for doc in docs:
                content = doc.page_content.strip()
                if content and len(content) > 40 and content not in seen:
                    formatted.append(content)
                    seen.add(content)
            return "\n\n".join(formatted)

        rag_chain = (
            {"context": retriever | format_docs, "question": RunnablePassthrough()}
            | self.prompt
            | self.llm
            | self.answer_parser
        )
        return rag_chain
