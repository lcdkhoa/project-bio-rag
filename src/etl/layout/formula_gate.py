# -*- coding: utf-8 -*-
"""Bước 1 của kế hoạch hybrid Tesseract + MinerU cho công thức (D-56/D-144):
gate quyết định một DÒNG chữ Tesseract có NGHI là công thức Hoá/Lý bị hỏng hay
không, để sau này (Bước 2, cần Colab GPU — chưa làm trong session này) crop
đúng vùng đó gửi cho MinerU thay vì gửi cả trang.

Thiết kế: `document/specs/2026-08-27-formula-ocr-hybrid-prompt.md` §3 Bước 1.
Số đo: `document/decision_log.html` D-144, sinh lại bằng
`python -m src.test.measure_formula_gate`.

## Vì sao là quy tắc BOOLEAN, không phải một ngưỡng liên tục

Thiết kế ban đầu định dùng một điểm số liên tục (mật độ tín hiệu-hỏng / số từ)
rồi quét ngưỡng như D-57 đã làm với `COVERAGE_MIN`. Quét thật trên 89 ô (97 ô
gold trừ 8 ô loại `bang`, đủ cả 3 NXB KNTT/CTST/CD chứ KHÔNG chỉ KNTT như dòng
cũ ở CLAUDE.md tưởng — D-144 đã sửa) cho kết quả: recall = 1,000 đạt được ngay
từ ngưỡng "có ít nhất MỘT khớp" (điểm số > 0), và tăng ngưỡng chỉ làm recall
rơi tự do (0,978 rồi 0,778 rồi thấp dần) mà không đổi precision đáng kể. Nghĩa
là điểm liên tục không mua được gì — quét ra vẫn chọn đúng điểm biên "có khớp
hay không", nên gate là quy tắc nhị phân của chính hai tín hiệu đã đo ở D-56,
không phải một tham số cần tinh chỉnh thêm.
"""
from __future__ import annotations

from .formula_signals import CO_DAU_BANG, CONG_THUC_HONG


def is_formula_suspect(text: str) -> bool:
    """Dòng `text` (chữ Tesseract đọc được) có nghi là công thức Hoá/Lý bị hỏng.

    Đo trên gold set 89 ô / 3 NXB (D-144, sinh lại bằng
    `python -m src.test.measure_formula_gate`): precision 0,8654 (45 TP / 7 FP)
    · recall 1,0000 (0 FN) khi dùng đúng logic này (khớp `CONG_THUC_HONG` HOẶC
    `CO_DAU_BANG`). Recall = 1,0 là ưu tiên: một dòng lọt lưới (false negative)
    nghĩa là công thức đó tiếp tục hỏng y như hiện tại — không tệ hơn hiện
    trạng, chỉ là bỏ lỡ cơ hội sửa. Một dòng vào nhầm (false positive) chỉ tốn
    một lượt gọi MinerU thừa ở Bước 2 (rẻ hơn nhiều so với đọc cả trang), và
    Bước 3 chỉ merge khi MinerU đọc được token công thức hợp lệ nên không có
    rủi ro bịa từ việc gate quá tay.

    Mở tay xem cả 7/7 ca false-positive đo được (CẤM #11, không kết luận mà
    chưa mở ra đọc) — precision nhìn con số thô có vẻ thấp, nhưng 6/7 KHÔNG
    phải gate sai:
    4 ca là giới hạn của CHÍNH `formula_tokens` (nhãn đúng dùng để đo) — nó bỏ
    sót công thức có ngoặc (`KLPT(NₓOᵧ) = 44`, `%A = [KLNT(A) × x /
    KLPT(AₓBᵧ)] × 100%`) hoặc ký hiệu Unicode ngoài tập đã tính (`tₛ° = 78,3`,
    `⇒ x ≈ 2`) — tức gate ĐÚNG khi thấy dấu hiệu công thức, chỉ là thước đo
    không công nhận; 1 ca là đáp án người không hợp lệ (gõ "không thấy rõ" thay
    vì `???` theo đúng quy ước phiếu); 1 ca là dòng Tesseract (`may_doc`) dài
    hơn phần ảnh crop cho người xem nên chứa thêm một công thức thật (`SO,`)
    người không có cơ hội thấy. Chỉ **1/7** là mơ hồ THẬT không thể phân biệt
    bằng một dòng: liệt kê ký hiệu nguyên tố trong câu văn thường (`Mg, Al, Zn,
    Fe`) đọc giống hệt chỉ số dưới bị phá. Không cố xử lý ca đó ở đây — cần
    ngữ cảnh nhiều hơn một dòng (ví dụ: nhiều token liền nhau cách nhau bằng
    dấu phẩy là danh sách, một token đơn lẻ giữa câu là nghi công thức), để
    lại như câu hỏi mở.
    """
    t = str(text or "")
    return bool(CONG_THUC_HONG.search(t) or CO_DAU_BANG.search(t))
