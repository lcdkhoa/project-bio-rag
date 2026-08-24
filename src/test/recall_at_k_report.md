# Recall@k theo từng bộ sách — baseline (distance) vs rerank (cross-encoder)

Chứng minh: **tăng k thì recall tăng đơn điệu**; rerank không tăng recall@max_k (chỉ đảo thứ tự trong tập đã fetch) nhưng cải thiện recall@k nhỏ và MRR — đúng luận điểm D-08 "nút thắt ở xếp hạng".

| Sách | Recall@3 (base\|rer) | Recall@5 (base\|rer) | Recall@10 (base\|rer) | MRR (base\|rer) |
|---|---|---|---|---|
| SGK_KHTN_6_KNTT | 0.76\|0.92 | 0.96\|0.92 | 1.00\|1.00 | 0.72\|0.83 |
| SGK_KHTN_7_KNTT | 0.88\|1.00 | 0.92\|1.00 | 1.00\|1.00 | 0.83\|1.00 |
| SGK_KHTN_8_KNTT | 0.88\|0.96 | 0.96\|0.96 | 0.96\|0.96 | 0.77\|0.92 |
| SGK_KHTN_9_KNTT | 0.72\|0.84 | 0.92\|0.88 | 0.96\|0.96 | 0.59\|0.78 |
| **TRUNG BÌNH** | 0.81\|0.93 | 0.94\|0.94 | 0.98\|0.98 | 0.73\|0.88 |