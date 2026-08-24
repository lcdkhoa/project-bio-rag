# -*- coding: utf-8 -*-
"""Định tuyến "chỉ ảnh" KHÔNG được ăn câu hỏi cần chữ.

`HybridRetriever.search` bỏ HẲN phía text khi `is_image_only_query` trả True, nên
một câu bị định tuyến sai không nhận được câu trả lời — nó nhận
"Mình tìm thấy N hình ảnh liên quan". Đo trên bộ test 300 câu (mọi câu đều là câu
hỏi CẦN CHỮ, gold key là một trang văn bản): **3/300 câu bị định tuyến thành chỉ
ảnh**, tức 3 câu trả lời sai mà không có lỗi nào được log.

Ba câu đó, và vì sao chúng lọt:

1. *"Hình 22.3 minh hoạ sự tạo mạch carbon gồm những loại mạch nào?"* — chứa
   "minh hoa" (gợi ý ảnh) và bắt đầu bằng "hình" nên tiền tố rỗng ⊆ tập động từ.
2. *"Ảnh không hứng được trên màn gọi là ảnh gì? …thấu kính phân kì…"* — trong
   **Vật lí**, "ảnh" là ảnh quang học, không phải bức ảnh. Đúng cái bẫy của phạm
   vi KHTN: bộ định tuyến được viết cho môn Sinh.
3. *"Hình ảnh bánh mì bị mốc… cho thấy đặc điểm gì của lương thực - thực phẩm?"*

Luật thêm vào: **câu có từ hỏi nội dung ("gì", "nào", "vì sao", …) thì không phải
truy vấn chỉ-ảnh.** Và nó phải so trên dạng CÒN DẤU: bỏ dấu thì "nào" đụng
"não" (bộ não) — đúng loại đụng độ đã cắn ở D-49 ("khí"→"khi", "đo"/"độ"→"do").
"""
import pytest

from src.rag.query_intent import is_image_only_query

CAU_HOI_CAN_CHU = [
    "Hình 22.3 minh hoạ sự tạo mạch carbon gồm những loại mạch nào?",
    "Ảnh không hứng được trên màn gọi là ảnh gì? Ảnh đó của vật qua thấu kính "
    "phân kì được tạo thành bởi cái gì?",
    "Hình ảnh bánh mì bị mốc và quả dâu tây bị hỏng cho thấy đặc điểm gì của "
    "lương thực - thực phẩm?",
]

TRUY_VAN_CHI_ANH = [
    "cho tôi hình con hổ",
    "cho xem ảnh tế bào thực vật",
    "hình thôi",
    "chỉ cần hình quang hợp",
]


@pytest.mark.parametrize("cau", CAU_HOI_CAN_CHU)
def test_question_asking_for_information_is_not_image_only(cau):
    assert is_image_only_query(cau) is False


@pytest.mark.parametrize("cau", TRUY_VAN_CHI_ANH)
def test_real_image_only_request_still_routes_to_images(cau):
    assert is_image_only_query(cau) is True


def test_brain_figure_request_is_not_broken_by_the_accent_trap():
    """"não" (bộ não) KHÔNG được nhầm thành từ hỏi "nào" — nếu so trên dạng bỏ
    dấu thì mọi yêu cầu hình về bộ não sẽ mất đường ảnh."""
    assert is_image_only_query("cho tôi hình bộ não người") is True


def test_explicit_image_only_wins_over_a_question_word():
    """"chỉ cần hình" là ý muốn NÓI RÕ — nó phải thắng luật từ hỏi."""
    assert is_image_only_query("chỉ cần hình, loại nào cũng được") is True
