# Báo cáo đánh giá RAG theo từng bộ sách

Tổng số bộ sách: 12/12 | Tổng số câu: 233 | Judge: qwen/qwen3.8-27b | Số câu/sách: 19

- Đo ở lượt NÀY: SGK_KHTN_6_KNTT

- Lấy từ `*_result.csv` CÓ SẴN của lượt trước: SGK_KHTN_6_CD, SGK_KHTN_6_CTST, SGK_KHTN_7_CD, SGK_KHTN_7_CTST, SGK_KHTN_7_KNTT, SGK_KHTN_8_CD, SGK_KHTN_8_CTST, SGK_KHTN_8_KNTT, SGK_KHTN_9_CD, SGK_KHTN_9_CTST, SGK_KHTN_9_KNTT


## Xếp hạng tổng thể

| Hạng | Sách | Overall | Recall@k(page) | MRR(page) | Precision(page) | Correct/5 | Faithful/5 | Relevancy/5 |
|---|---|---|---|---|---|---|---|---|
| 1 | SGK_KHTN_8_KNTT | 0.879 | 1.00 | 0.94 | 0.52 | 4.44 | 4.89 | 4.72 |
| 2 | SGK_KHTN_6_CTST | 0.862 | 1.00 | 0.94 | 0.53 | 4.26 | 4.53 | 4.74 |
| 3 | SGK_KHTN_8_CD | 0.821 | 0.95 | 0.87 | 0.42 | 4.30 | 4.55 | 4.60 |
| 4 | SGK_KHTN_6_CD | 0.812 | 0.95 | 0.89 | 0.40 | 4.05 | 4.45 | 4.65 |
| 5 | SGK_KHTN_8_CTST | 0.804 | 0.95 | 0.81 | 0.43 | 4.10 | 4.40 | 4.65 |
| 6 | SGK_KHTN_9_KNTT | 0.798 | 0.94 | 0.85 | 0.44 | 3.94 | 4.39 | 4.39 |
| 7 | SGK_KHTN_9_CD | 0.788 | 0.85 | 0.77 | 0.38 | 4.25 | 4.45 | 4.95 |
| 8 | SGK_KHTN_7_KNTT | 0.786 | 0.95 | 0.89 | 0.38 | 3.90 | 4.20 | 4.35 |
| 9 | SGK_KHTN_6_KNTT | 0.773 | 0.89 | 0.84 | 0.39 | 3.95 | 4.11 | 4.53 |
| 10 | SGK_KHTN_7_CD | 0.756 | 0.95 | 0.72 | 0.39 | 3.68 | 4.21 | 4.53 |
| 11 | SGK_KHTN_9_CTST | 0.701 | 0.80 | 0.62 | 0.33 | 3.75 | 4.15 | 4.35 |
| 12 | SGK_KHTN_7_CTST | 0.697 | 0.65 | 0.62 | 0.32 | 4.10 | 4.30 | 4.55 |

## Recall@k tăng theo k (top-k thô, bỏ qua relevance gate)

Cho thấy embedding tìm được trang vàng ở mức nào; tăng k thì recall tăng đơn điệu. Recall@10 là 'trần recall'. So với **Recall(prod)** (chỉ ~3 chunk sau gate) để thấy nút thắt nằm ở khâu gate/cắt-k, không phải embedding.

| Sách | Recall@3 | Recall@5 | Recall@10 | Recall(prod) |
|---|---|---|---|---|
| SGK_KHTN_8_KNTT | 0.89 | 0.89 | 0.94 | 1.00 |
| SGK_KHTN_6_CTST | 0.89 | 0.89 | 1.00 | 1.00 |
| SGK_KHTN_8_CD | 0.60 | 0.65 | 0.75 | 0.95 |
| SGK_KHTN_6_CD | 0.80 | 0.80 | 0.90 | 0.95 |
| SGK_KHTN_8_CTST | 0.85 | 0.95 | 0.95 | 0.95 |
| SGK_KHTN_9_KNTT | 0.83 | 0.89 | 0.89 | 0.94 |
| SGK_KHTN_9_CD | 0.75 | 0.75 | 0.80 | 0.85 |
| SGK_KHTN_7_KNTT | 0.85 | 0.90 | 0.95 | 0.95 |
| SGK_KHTN_6_KNTT | 0.79 | 0.89 | 0.95 | 0.89 |
| SGK_KHTN_7_CD | 0.89 | 0.95 | 0.95 | 0.95 |
| SGK_KHTN_9_CTST | 0.55 | 0.65 | 0.80 | 0.80 |
| SGK_KHTN_7_CTST | 0.60 | 0.75 | 0.90 | 0.65 |
| **TRUNG BÌNH** | 0.78 | 0.83 | 0.90 | 0.91 |

## Ghi chú số liệu
- **Recall@k(page)** = hit@k: tỷ lệ câu hỏi mà hệ truy xuất đúng trang nguồn (top-k thực tế).
- **MRR(page)** = điểm rank: trung bình 1/thứ-hạng của chunk đúng đầu tiên.
- **Precision(page)** = tỷ lệ chunk truy xuất là đúng trang nguồn.
- **Recall@(3, 5, 10)** (top-k thô) đo khả năng embedding tìm thấy trang vàng; **Recall(prod)** là recall thực tế sau relevance gate (~3 chunk). Khoảng cách giữa hai cái định lượng phần recall mất đi do khâu rank/cắt-k.
- **Correct/Faithful/Relevancy** do LLM thứ 2 chấm lại câu trả lời của Qwen 2.5, thang 1-5.
- `overall_score = (retrieval_score + answer_score)/2`, dùng để xếp hạng.