# Báo cáo đánh giá RAG theo từng bộ sách

Tổng số bộ sách: 12/12 | Tổng số câu: 240 | Judge: qwen/qwen3.8-27b | Số câu/sách: 20

- Đo ở lượt NÀY: SGK_KHTN_9_CD

- Lấy từ `*_result.csv` CÓ SẴN của lượt trước: SGK_KHTN_6_CD, SGK_KHTN_6_CTST, SGK_KHTN_6_KNTT, SGK_KHTN_7_CD, SGK_KHTN_7_CTST, SGK_KHTN_7_KNTT, SGK_KHTN_8_CD, SGK_KHTN_8_CTST, SGK_KHTN_8_KNTT, SGK_KHTN_9_CTST, SGK_KHTN_9_KNTT


## Xếp hạng tổng thể

| Hạng | Sách | Overall | Recall@k(page) | MRR(page) | Precision(page) | Correct/5 | Faithful/5 | Relevancy/5 |
|---|---|---|---|---|---|---|---|---|
| 1 | SGK_KHTN_6_CTST | 0.836 | 0.95 | 0.93 | 0.48 | 4.30 | 4.45 | 4.55 |
| 2 | SGK_KHTN_8_KNTT | 0.806 | 0.95 | 0.88 | 0.48 | 4.05 | 4.25 | 4.35 |
| 3 | SGK_KHTN_6_CD | 0.796 | 1.00 | 0.87 | 0.42 | 4.00 | 4.30 | 4.15 |
| 4 | SGK_KHTN_7_KNTT | 0.767 | 0.95 | 0.90 | 0.40 | 3.75 | 4.05 | 3.95 |
| 5 | SGK_KHTN_8_CD | 0.755 | 0.85 | 0.82 | 0.37 | 4.00 | 4.15 | 4.30 |
| 6 | SGK_KHTN_6_KNTT | 0.747 | 0.90 | 0.85 | 0.40 | 3.75 | 3.85 | 4.05 |
| 7 | SGK_KHTN_9_KNTT | 0.744 | 0.85 | 0.74 | 0.38 | 3.95 | 4.30 | 4.20 |
| 8 | SGK_KHTN_7_CD | 0.738 | 0.95 | 0.71 | 0.40 | 3.85 | 4.00 | 4.00 |
| 9 | SGK_KHTN_9_CD | 0.731 | 0.85 | 0.76 | 0.37 | 3.80 | 4.10 | 4.15 |
| 10 | SGK_KHTN_8_CTST | 0.723 | 0.90 | 0.77 | 0.43 | 3.55 | 3.80 | 3.85 |
| 11 | SGK_KHTN_7_CTST | 0.676 | 0.70 | 0.65 | 0.37 | 3.80 | 3.95 | 3.95 |
| 12 | SGK_KHTN_9_CTST | 0.675 | 0.75 | 0.60 | 0.30 | 3.95 | 4.00 | 4.05 |

## Recall@k tăng theo k (top-k thô, bỏ qua relevance gate)

Cho thấy embedding tìm được trang vàng ở mức nào; tăng k thì recall tăng đơn điệu. Recall@10 là 'trần recall'. So với **Recall(prod)** (chỉ ~3 chunk sau gate) để thấy nút thắt nằm ở khâu gate/cắt-k, không phải embedding.

| Sách | Recall@3 | Recall@5 | Recall@10 | Recall(prod) |
|---|---|---|---|---|
| SGK_KHTN_6_CTST | 0.90 | 0.90 | 1.00 | 0.95 |
| SGK_KHTN_8_KNTT | 0.90 | 0.90 | 0.95 | 0.95 |
| SGK_KHTN_6_CD | 0.80 | 0.85 | 0.90 | 1.00 |
| SGK_KHTN_7_KNTT | 0.80 | 0.90 | 0.95 | 0.95 |
| SGK_KHTN_8_CD | 0.55 | 0.60 | 0.75 | 0.85 |
| SGK_KHTN_6_KNTT | 0.75 | 0.90 | 0.95 | 0.90 |
| SGK_KHTN_9_KNTT | 0.75 | 0.80 | 0.85 | 0.85 |
| SGK_KHTN_7_CD | 0.75 | 0.90 | 0.95 | 0.95 |
| SGK_KHTN_9_CD | 0.80 | 0.85 | 0.90 | 0.85 |
| SGK_KHTN_8_CTST | 0.90 | 0.95 | 0.95 | 0.90 |
| SGK_KHTN_7_CTST | 0.65 | 0.80 | 0.95 | 0.70 |
| SGK_KHTN_9_CTST | 0.60 | 0.70 | 0.75 | 0.75 |
| **TRUNG BÌNH** | 0.76 | 0.84 | 0.90 | 0.88 |

## Ghi chú số liệu
- **Recall@k(page)** = hit@k: tỷ lệ câu hỏi mà hệ truy xuất đúng trang nguồn (top-k thực tế).
- **MRR(page)** = điểm rank: trung bình 1/thứ-hạng của chunk đúng đầu tiên.
- **Precision(page)** = tỷ lệ chunk truy xuất là đúng trang nguồn.
- **Recall@(3, 5, 10)** (top-k thô) đo khả năng embedding tìm thấy trang vàng; **Recall(prod)** là recall thực tế sau relevance gate (~3 chunk). Khoảng cách giữa hai cái định lượng phần recall mất đi do khâu rank/cắt-k.
- **Correct/Faithful/Relevancy** do LLM thứ 2 chấm lại câu trả lời của Qwen 2.5, thang 1-5.
- `overall_score = (retrieval_score + answer_score)/2`, dùng để xếp hạng.