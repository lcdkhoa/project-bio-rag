# Báo cáo đánh giá RAG theo từng bộ sách

Tổng số bộ sách: 4 | Judge: gemini-3.5-flash-lite | Số câu/sách: 25

## Xếp hạng tổng thể

| Hạng | Sách | Overall | Recall@k(page) | MRR(page) | Precision(page) | Correct/5 | Faithful/5 | Relevancy/5 |
|---|---|---|---|---|---|---|---|---|
| 1 | SGK_KHTN_7_KNTT | 0.918 | 1.00 | 1.00 | 0.61 | 4.76 | 4.80 | 4.92 |
| 2 | SGK_KHTN_8_KNTT | 0.912 | 1.00 | 1.00 | 0.56 | 4.80 | 4.88 | 4.88 |
| 3 | SGK_KHTN_9_KNTT | 0.871 | 1.00 | 0.89 | 0.55 | 4.52 | 4.68 | 4.72 |
| 4 | SGK_KHTN_6_KNTT | 0.838 | 0.96 | 0.89 | 0.48 | 4.40 | 4.56 | 4.52 |

## Recall@k tăng theo k (top-k thô, bỏ qua relevance gate)

Cho thấy embedding tìm được trang vàng ở mức nào; tăng k thì recall tăng đơn điệu. Recall@10 là 'trần recall'. So với **Recall(prod)** (chỉ ~3 chunk sau gate) để thấy nút thắt nằm ở khâu gate/cắt-k, không phải embedding.

| Sách | Recall@3 | Recall@5 | Recall@10 | Recall(prod) |
|---|---|---|---|---|
| SGK_KHTN_7_KNTT | 0.92 | 1.00 | 1.00 | 1.00 |
| SGK_KHTN_8_KNTT | 0.96 | 0.96 | 1.00 | 1.00 |
| SGK_KHTN_9_KNTT | 0.96 | 1.00 | 1.00 | 1.00 |
| SGK_KHTN_6_KNTT | 0.96 | 1.00 | 1.00 | 0.96 |
| **TRUNG BÌNH** | 0.95 | 0.99 | 1.00 | 0.99 |

## Ghi chú số liệu
- **Recall@k(page)** = hit@k: tỷ lệ câu hỏi mà hệ truy xuất đúng trang nguồn (top-k thực tế).
- **MRR(page)** = điểm rank: trung bình 1/thứ-hạng của chunk đúng đầu tiên.
- **Precision(page)** = tỷ lệ chunk truy xuất là đúng trang nguồn.
- **Recall@(3, 5, 10)** (top-k thô) đo khả năng embedding tìm thấy trang vàng; **Recall(prod)** là recall thực tế sau relevance gate (~3 chunk). Khoảng cách giữa hai cái định lượng phần recall mất đi do khâu rank/cắt-k.
- **Correct/Faithful/Relevancy** do LLM thứ 2 chấm lại câu trả lời của Qwen 2.5, thang 1-5.
- `overall_score = (retrieval_score + answer_score)/2`, dùng để xếp hạng.