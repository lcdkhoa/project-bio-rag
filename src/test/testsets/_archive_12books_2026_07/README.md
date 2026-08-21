# Lưu trữ — bộ test của corpus 12 quyển (đã ngừng dùng)

Các CSV ở đây thuộc corpus **12 PDF / 3 nhà xuất bản** trước 2026-08. Chúng
KHÔNG dùng được cho corpus hiện tại (4 quyển KNTT, PNG-per-page) vì hai khoá vàng
đều không khớp metadata chunk hiện hành:

- `source_book` = `"SGK KHTN 6 KNTT.pdf"`, metadata chunk = `"SGK_KHTN_6_KNTT"`;
- `source_page` = số trong tên file, metadata `page` = số trang **IN** (lệch 1).

Giữ lại để truy nguyên số liệu trong báo cáo cũ, **không** để chạy lại. Thư mục
này nằm ngoài glob `testsets/*_testset.csv` nên các script eval không quét tới.
Bộ test mới sinh bằng: `python src/test/generate_testsets.py`.
