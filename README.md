# Biology RAG (Text + Image)

Dự án RAG cho SGK KHTN/Sinh học, gồm 2 pipeline chính:
- ETL text: OCR tiếng Việt -> chunk -> index vào Chroma.
- ETL image: detect/crop ảnh theo từng page -> enrich metadata -> index image + metadata.

Hệ thống hỗ trợ thêm human-review cho ảnh để tăng chất lượng retrieval (đặc biệt với tiếng Việt).

## 1) Cài đặt

```bash
pip install -r requirements.txt
cp .env.example .env
```

Thiết lập tối thiểu trong `.env`:
- `HF_TOKEN=<your_token>`
- `USE_GPU=true` (nếu có GPU)

Nếu chạy trên Google Colab, cài thêm system libs trước khi ETL:

```python
!apt-get update
!apt-get install -y poppler-utils
!apt-get install -y tesseract-ocr tesseract-ocr-vie
```

## 2) Lệnh chính

| Lệnh | Mục đích |
|---|---|
| `python main.py --text-only` | ETL text (OCR + chunk + index text) |
| `python main.py --image-only` | ETL image (extract/crop + metadata + index image) |
| `python main.py --etl` | ETL full text + image |
| `python main.py --export-image-review <path.json>` | Export danh sách ảnh để reviewer chỉnh caption/xóa ảnh sai |
| `python main.py --apply-image-review <path.json> --review-user <name>` | Apply review vào DB và đồng bộ image index |
| `python main.py --app` | Chạy Gradio app |

## 3) Flow khuyến nghị khi làm mới DB

1. Xóa DB cũ và tạo lại thư mục `database`.
2. Chạy `python main.py --text-only`.
3. Chạy `python main.py --image-only`.
4. Export review: `python main.py --export-image-review database/review_images.json`.
5. Reviewer chỉnh `caption_vi_manual`, `keywords_vi_manual`, `review_status`, `is_active`.
6. Apply review: `python main.py --apply-image-review database/review_images.json --review-user <name>`.
7. Chạy app: `python main.py --app`.

## 4) Tài liệu bàn giao kỹ thuật

- Technical handover (Markdown): `document/technical_handover_rag.md`
- Technical handover (HTML): `document/technical_handover_rag.html`
- Vận hành nhanh (Markdown): `document/huong_dan_van_hanh_rag.md`
- Vận hành nhanh (HTML): `document/huong_dan_van_hanh_rag.html`

## 5) Reset tiện ích

```bash
python reset_status.py --all
python reset_status.py --image-index
python reset_status.py --images-full
python reset_status.py "D:/personal_repo/project_rag/data/SGK KHTN 6 CD.pdf"
```
