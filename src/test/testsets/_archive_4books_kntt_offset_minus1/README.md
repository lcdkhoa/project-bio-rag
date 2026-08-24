# VÔ HIỆU — bộ test 4 quyển KNTT của corpus CŨ (offset −1)

Sinh 2026-08-22 trên corpus **4 quyển KNTT / 801 trang**, nơi
`printed_page == số trong tên file − 1`. Corpus hiện tại là **12 quyển / 2 399
trang** với `offset = 0` (D-65), và **nội dung trang cũng đã đổi** (D-51: cùng một
`page_017` của 9_KNTT nay in `Hình 2.4` chứ không còn `Hình 2.3`).

Nên mọi `source_page` trong các CSV này **trỏ sai trang** trên index hiện tại. Dùng
lại chúng sẽ cho ra recall/MRR thấp **mà không có lỗi nào được raise** — đúng loại
im lặng mà chính `generate_testsets.py` được viết lại để chặn.

**Chuyển vào đây (2026-08-24) vì một lý do cụ thể:** `generate_for_book` bỏ qua
quyển đã có đủ câu trong CSV (`have >= per_book`) để việc "chạy lại là tiếp tục"
hoạt động. Để 4 file này ở `testsets/` thì lượt sinh mới sẽ **bỏ qua im lặng** 4
quyển KNTT và tưởng là đã xong.

Giữ lại để tra cứu số cũ (G3 = 0,99 / G5 judge 4,62–4,76 / recall@10 = 1,00 là
**mốc lịch sử**, KHÔNG phải mục tiêu so sánh — CẤM #7 của prompt M2). Nằm ngoài
glob `*_testset.csv` của `testsets/` nên không script nào nhặt phải.
