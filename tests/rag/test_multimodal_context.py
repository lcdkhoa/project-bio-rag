# -*- coding: utf-8 -*-
"""Ngữ cảnh ĐA PHƯƠNG THỨC: text chunk + nhãn/chú thích hình DETERMINISTIC.

Vì sao cần module riêng thay vì ba dòng trong `api.py`: đây là trục ablation của
Mục tiêu 4 ("RAG đa phương thức so với RAG chỉ văn bản"), nên nó phải (a) tắt
được để so, (b) **không** lấy một chữ nào từ model sinh (Vintern đã bị loại —
D-47/D-74), và (c) khi kho ảnh RỖNG thì cho ra ngữ cảnh Y HỆT text-only, nếu
không thì bảng ablation đo cả một nhánh ẩn.
"""
from langchain_core.documents import Document

from src.rag.multimodal_context import build_context, figure_blocks


def _text(page, body):
    return Document(page_content=body,
                    metadata={"source": "SGK_KHTN_6_KNTT", "page": page,
                              "page_index": page, "region_type": "body",
                              "chunk_index": 0})


def _figure(label="Hình 2.3", fig_caption="Cấu tạo tế bào thực vật",
            crop_text="", page=45, **extra):
    meta = {"pdf_filename": "SGK_KHTN_6_KNTT", "page_number": page,
            "figure_label": label, "figure_caption": fig_caption,
            "crop_text": crop_text}
    meta.update(extra)
    return Document(page_content="search text", metadata=meta)


TEXT_DOCS = [_text(10, "Tế bào là đơn vị cơ bản của sự sống."),
             _text(11, "Thành tế bào bảo vệ tế bào thực vật.")]


def test_text_only_mode_ignores_image_docs_entirely():
    only = build_context(TEXT_DOCS, [], multimodal=False)
    with_images = build_context(TEXT_DOCS, [_figure()], multimodal=False)

    assert only == with_images


def test_multimodal_with_empty_image_store_equals_text_only():
    """Tự kiểm bắt buộc của M2C.3: kho ảnh rỗng -> KHÔNG được lệch một byte."""
    assert (build_context(TEXT_DOCS, [], multimodal=True)
            == build_context(TEXT_DOCS, [], multimodal=False))


def test_multimodal_appends_label_caption_and_page():
    ctx = build_context(TEXT_DOCS, [_figure()], multimodal=True)

    assert TEXT_DOCS[0].page_content in ctx
    assert "Hình 2.3" in ctx
    assert "Cấu tạo tế bào thực vật" in ctx
    assert "45" in ctx


def test_model_generated_caption_fields_are_never_read():
    """`visual_caption_vi`/`final_caption_vi` do model SINH ra (D-47). Ngữ cảnh
    này chỉ được mang chữ đọc lại từ pixel: nhãn pill, caption OCR, chữ trong
    crop."""
    bia = "một bác sĩ đang phẫu thuật tai"
    doc = _figure(label="Hình 3.1", fig_caption="", crop_text="",
                  visual_caption_vi=bia, final_caption_vi=bia,
                  caption=bia, caption_vi=bia)

    ctx = build_context(TEXT_DOCS, [doc], multimodal=True)

    assert "phẫu thuật" not in ctx


def test_figure_without_any_deterministic_text_is_dropped():
    assert figure_blocks([_figure(label="", fig_caption="", crop_text="")]) == []


def test_crop_text_alone_is_enough_to_keep_a_figure():
    blocks = figure_blocks([_figure(label="", fig_caption="",
                                    crop_text="Khí oxygen")])

    assert len(blocks) == 1
    assert "Khí oxygen" in blocks[0]


def test_same_figure_label_from_two_channels_is_emitted_once():
    """Kênh CLIP và kênh metadata trả cùng một hình -> một khối, không hai."""
    blocks = figure_blocks([_figure(), _figure()])

    assert len(blocks) == 1


def test_max_figures_caps_the_block_count():
    docs = [_figure(label=f"Hình 1.{i}") for i in range(1, 9)]

    assert len(figure_blocks(docs, max_figures=3)) == 3


def test_block_carries_reader_facing_book_name():
    blocks = figure_blocks([_figure()])

    assert "Khoa học tự nhiên 6 (Kết nối tri thức)" in blocks[0]


def test_selected_figures_returns_exactly_the_docs_that_made_a_block():
    """Bảng ablation phải biết hình NÀO thật sự vào ngữ cảnh, không phải hình
    nào được truy xuất — hai con số đó khác nhau (hình không có chữ bị bỏ)."""
    from src.rag.multimodal_context import selected_figures

    keep = _figure(label="Hình 1.1")
    drop = _figure(label="", fig_caption="", crop_text="")

    got = selected_figures([drop, keep, drop])

    assert got == [keep]


def test_selected_figures_and_blocks_agree_in_count():
    from src.rag.multimodal_context import selected_figures

    docs = [_figure(label=f"Hình 1.{i}") for i in range(1, 6)]

    assert len(selected_figures(docs, max_figures=2)) == \
        len(figure_blocks(docs, max_figures=2)) == 2
