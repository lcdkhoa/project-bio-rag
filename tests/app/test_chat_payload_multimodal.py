# -*- coding: utf-8 -*-
"""`prepare_chat_payload` phải NỐI được nhãn/chú thích hình vào prompt.

Chỗ này là nguyên nhân "đa phương thức vs chỉ văn bản chênh 0 theo cấu trúc":
`api.py` dựng `context_str` chỉ từ `text_docs`, còn `image_docs` chỉ đi ra
gallery. Test khoá lại cả hai chiều của cờ.
"""
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

import src.app.api as api_mod


class FakePrompt:
    def format(self, context, question):
        return f"CTX<<{context}>>Q<<{question}>>"


@pytest.fixture
def fake_services(monkeypatch):
    text_docs = [Document(
        page_content="Tế bào là đơn vị cơ bản của sự sống.",
        metadata={"source": "SGK_KHTN_6_KNTT", "page": 30, "page_index": 30,
                  "region_type": "body", "chunk_index": 0})]
    image_docs = [Document(
        page_content="search text",
        metadata={"pdf_filename": "SGK_KHTN_6_KNTT", "page_number": 45,
                  "figure_label": "Hình 2.3",
                  "figure_caption": "Cấu tạo tế bào thực vật",
                  "crop_text": "", "image_path": __file__})]
    services = SimpleNamespace(
        hybrid_retriever=SimpleNamespace(
            search=lambda q: SimpleNamespace(text_docs=text_docs,
                                             image_docs=image_docs,
                                             image_only_query=False)),
        rag=SimpleNamespace(prompt=FakePrompt()),
    )
    monkeypatch.setattr(api_mod.AppServices, "get_instance",
                        staticmethod(lambda: services))
    return services


def test_text_only_prompt_has_no_figure_label(fake_services, monkeypatch):
    monkeypatch.setattr(api_mod, "MULTIMODAL_CONTEXT_ENABLED", False)

    payload = api_mod.prepare_chat_payload("Tế bào là gì?")

    assert "Tế bào là đơn vị cơ bản" in payload["formatted_prompt"]
    assert "Hình 2.3" not in payload["formatted_prompt"]


def test_multimodal_prompt_carries_figure_label_and_caption(fake_services,
                                                            monkeypatch):
    monkeypatch.setattr(api_mod, "MULTIMODAL_CONTEXT_ENABLED", True)

    payload = api_mod.prepare_chat_payload("Tế bào là gì?")

    assert "Hình 2.3" in payload["formatted_prompt"]
    assert "Cấu tạo tế bào thực vật" in payload["formatted_prompt"]


def test_citations_are_built_from_text_docs_in_both_modes(fake_services,
                                                          monkeypatch):
    """Trích dẫn vẫn deterministic từ chunk text — hình không được chen vào."""
    monkeypatch.setattr(api_mod, "MULTIMODAL_CONTEXT_ENABLED", True)
    mm = api_mod.prepare_chat_payload("Tế bào là gì?")["citations"]
    monkeypatch.setattr(api_mod, "MULTIMODAL_CONTEXT_ENABLED", False)
    text = api_mod.prepare_chat_payload("Tế bào là gì?")["citations"]

    assert mm == text
