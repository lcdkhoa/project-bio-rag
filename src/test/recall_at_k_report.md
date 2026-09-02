# Recall@k theo từng bộ sách — baseline (distance) vs rerank (cross-encoder)

Chứng minh: **tăng k thì recall tăng đơn điệu**; rerank không tăng recall@max_k (chỉ đảo thứ tự trong tập đã fetch) nhưng cải thiện recall@k nhỏ và MRR — đúng luận điểm D-08 "nút thắt ở xếp hạng".

| Sách | Recall@3 (base\|rer) | Recall@5 (base\|rer) | Recall@10 (base\|rer) | MRR (base\|rer) |
|---|---|---|---|---|
| SGK_KHTN_6_CD | 0.80\|0.90 | 0.85\|0.90 | 0.90\|0.90 | 0.76\|0.79 |
| SGK_KHTN_6_CTST | 0.90\|1.00 | 0.90\|1.00 | 1.00\|1.00 | 0.84\|0.94 |
| SGK_KHTN_6_KNTT | 0.75\|0.90 | 0.90\|0.90 | 0.95\|0.95 | 0.67\|0.80 |
| SGK_KHTN_7_CD | 0.75\|0.90 | 0.90\|0.95 | 0.95\|0.95 | 0.66\|0.68 |
| SGK_KHTN_7_CTST | 0.65\|0.70 | 0.80\|0.95 | 0.95\|0.95 | 0.66\|0.70 |
| SGK_KHTN_7_KNTT | 0.80\|0.95 | 0.90\|0.95 | 0.95\|0.95 | 0.80\|0.90 |
| SGK_KHTN_8_CD | 0.55\|0.55 | 0.60\|0.65 | 0.75\|0.75 | 0.50\|0.58 |
| SGK_KHTN_8_CTST | 0.90\|0.90 | 0.95\|0.95 | 0.95\|0.95 | 0.86\|0.79 |
| SGK_KHTN_8_KNTT | 0.90\|0.95 | 0.90\|0.95 | 0.95\|0.95 | 0.79\|0.90 |
| SGK_KHTN_9_CD | 0.80\|0.75 | 0.85\|0.85 | 0.90\|0.90 | 0.69\|0.71 |
| SGK_KHTN_9_CTST | 0.60\|0.65 | 0.70\|0.65 | 0.75\|0.75 | 0.52\|0.59 |
| SGK_KHTN_9_KNTT | 0.75\|0.80 | 0.80\|0.85 | 0.85\|0.85 | 0.66\|0.73 |
| **TRUNG BÌNH** | 0.76\|0.83 | 0.84\|0.88 | 0.90\|0.90 | 0.70\|0.76 |