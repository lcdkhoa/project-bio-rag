# -*- coding: utf-8 -*-
"""Prompt hệ thống phải nói đúng PHẠM VI HỢP ĐỒNG: cả Lý – Hoá – Sinh.

`goal.docx` Mục tiêu 2: kho vector phủ **toàn bộ KHTN Lý–Hoá–Sinh, 12 quyển /
3 bộ sách**. Nhưng `chain.py` khoá cứng *"Bạn là trợ lý AI môn Sinh học THCS"*,
nên một câu hỏi Vật lý đang được trả lời bởi một trợ lý tự nhận là dạy Sinh học
— và câu "chỉ dùng thông tin trong tài liệu" đứng cạnh một lời tự nhận sai phạm
vi là một mâu thuẫn ngay trong prompt.

Test này KHÔNG chứng minh câu trả lời tốt hơn (đó là phép đo before/after trên
câu Lý và câu Hoá, ghi trong decision log). Nó chỉ khoá lại phạm vi để lần sau
không ai lặng lẽ thu nó về một phân môn.
"""
from src.rag.chain import BiologyRAG


class _Llm:
    """LLM giả: `BiologyRAG.__init__` chỉ giữ tham chiếu, không gọi gì."""


def _prompt_text() -> str:
    return BiologyRAG(_Llm()).prompt.template


def test_system_prompt_names_the_whole_khtn_subject():
    text = _prompt_text()

    assert "Khoa học tự nhiên" in text
    assert "Sinh học THCS" not in text


def test_system_prompt_still_forbids_answering_outside_the_documents():
    """Sửa phạm vi KHÔNG được làm mất luật chống bịa (nguyên tắc 1)."""
    text = _prompt_text()

    assert "KHÔNG bịa" in text
    assert "Thông tin này không được đề cập trong sách giáo khoa." in text


def test_prompt_still_takes_exactly_context_and_question():
    """`api.py` gọi `prompt.format(context=…, question=…)` — đổi tên biến là
    một TypeError lúc chạy, không phải lúc test."""
    assert set(BiologyRAG(_Llm()).prompt.input_variables) == {"context",
                                                             "question"}
