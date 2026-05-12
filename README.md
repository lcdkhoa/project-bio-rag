# Biology RAG

Hệ thống RAG (Retrieval-Augmented Generation) cho môn Sinh học THCS, xây dựng trên Sách Giáo Khoa.

## Cài đặt

```bash
pip install -r requirements.txt
```

Sao chép file môi trường:

```bash
cp .env.example .env
```

Chỉnh sửa `.env` và điền `HF_TOKEN` của bạn.

## Chạy hệ thống

### ETL - Trích xuất dữ liệu từ PDF vào ChromaDB

```bash
python main.py --etl
```

### Chạy ứng dụng Gradio

```bash
python main.py --app
```

## Cấu trúc thư mục

```
project_rag/
├── main.py                 # Entry point
├── requirements.txt        # Dependencies
├── .env                    # Environment variables
├── .env.example           # Sample env file
├── data/                   # PDF textbooks
│   ├── SGK KHTN 6 CD.pdf
│   └── ...
├── biology_db_rag/         # ChromaDB persistence
│   └── chroma.sqlite3
└── src/
    ├── config.py           # Shared configuration
    ├── etl/
    │   ├── __init__.py
    │   ├── cleaner.py      # Vietnamese text cleaning
    │   ├── loaders.py      # PDF loaders (PyPDF & OCR)
    │   └── text_splitter.py
    ├── rag/
    │   ├── __init__.py
    │   ├── vectorstore.py  # ChromaDB wrapper
    │   ├── llm.py          # HuggingFace LLM setup
    │   └── chain.py        # RAG chain assembly
    └── app/
        ├── __init__.py
        └── assistant.py    # Gradio web UI
```

## Tài liệu hóa các cải tiến

### Kiến trúc mới

1. **Module hóa (Decoupling)**: Tách logic thành các package riêng biệt:
   - `src/etl/` - Xử lý PDF, OCR, text cleaning, splitting
   - `src/rag/` - VectorDB, LLM, RAG chain
   - `src/app/` - Gradio UI

2. **Quản lý cấu hình tập trung**: Toàn bộ đường dẫn và tham số trong `src/config.py` và `.env`

3. **Entry point duy nhất**: `main.py` với argparse cho `--etl` và `--app`

4. **Logging**: Thay `print()` bằng `logging` module chuẩn

5. **DRY principle**: Tránh lặp lại code xử lý text, OCR, prompt giữa 2 file gốc

### Loại bỏ code đặc thù Colab

- Xóa `!pip install`, `!apt-get`
- Xóa `google.colab import drive`
- Xóa đường dẫn Google Drive cứng

### Khả năng mở rộng

- Checkpoint tracking cho ETL resume
- Có thể chạy `--etl` và `--app` độc lập
- Dễ dàng thêm loader mới hoặc LLM khác
