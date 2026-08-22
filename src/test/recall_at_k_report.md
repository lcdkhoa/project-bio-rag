# Recall@k theo từng bộ sách — baseline (distance) vs rerank (cross-encoder)

Chứng minh: **tăng k thì recall tăng đơn điệu**; rerank không tăng recall@max_k (chỉ đảo thứ tự trong tập đã fetch) nhưng cải thiện recall@k nhỏ và MRR — đúng luận điểm D-08 "nút thắt ở xếp hạng".

| Sách | Recall@3 (base\|rer) | Recall@5 (base\|rer) | Recall@10 (base\|rer) | MRR (base\|rer) |
|---|---|---|---|---|
| SGK_KHTN_6_KNTT | 0.96\|0.96 | 1.00\|1.00 | 1.00\|1.00 | 0.85\|0.91 |
| SGK_KHTN_7_KNTT | 0.92\|1.00 | 1.00\|1.00 | 1.00\|1.00 | 0.87\|1.00 |
| SGK_KHTN_8_KNTT | 0.96\|1.00 | 0.96\|1.00 | 1.00\|1.00 | 0.90\|1.00 |
| SGK_KHTN_9_KNTT | 0.96\|1.00 | 1.00\|1.00 | 1.00\|1.00 | 0.86\|0.89 |
| **TRUNG BÌNH** | 0.95\|0.99 | 0.99\|1.00 | 1.00\|1.00 | 0.87\|0.95 |