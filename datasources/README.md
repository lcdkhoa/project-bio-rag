# `datasources/` — dữ liệu nguồn, KHÔNG nằm trong git

Thư mục này chứa **ảnh trang sách giáo khoa** (PNG, một file một trang). Nó **cố ý
không được commit** (D-68): đã đo được 4,1 GB / 2 399 trang, và `.git` của repo đã
11 GB; riêng lô Cánh Diều + CTST ~3,4 GB vượt hạn mức 2 GB mỗi lần push của GitHub.
Chỉ file README này được theo dõi để thư mục còn tồn tại sau khi clone.

## Bố cục mà code mong đợi

```
datasources/SGK_KHTN_{6,7,8,9}_{KNTT,CTST,CD}/page_001.png … page_NNN.png
```

12 thư mục, 2 399 trang, **không có khoảng trống**, và mọi quyển bắt đầu từ
`page_001`. Số trong tên file **là số trang in** (`offset = 0`, đo trên 12/12 quyển
— D-65); `page_source.PngFolderPageSource` đọc số từ tên file, **không bao giờ**
`enumerate`. Vì vậy:

- **Không đánh số lại, không xoá file PNG nguồn.** Bỏ một trang khỏi index bằng
  `role` trong `BookManifest`, không phải bằng cách xoá file.
- Tải lại một trang thì nó tự khớp lại đúng chỗ; checkpoint khoá theo **md5 của
  từng trang** nên chỉ trang đó bị xử lý lại.

## Trỏ code sang chỗ khác (Colab / ổ ngoài)

```bash
RAG_DATA_DIR=/content/drive/MyDrive/sgk_khtn      # ảnh trang
RAG_DATABASE_DIR=/content/drive/MyDrive/rag_db    # index ChromaDB
RAG_MANIFEST_DIR=./database/manifests             # manifest đi theo repo
```

Cả ba đọc trong `src/config.py`. Nếu `RAG_DATA_DIR` trỏ vào chỗ trống thì
`--build-manifests`, `--etl`, `--text-only`, `--image-only` đều **thoát với mã lỗi
2** kèm thông báo — không có đường nào "chạy xong mà không làm gì".
