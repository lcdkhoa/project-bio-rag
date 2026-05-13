# Hướng Dẫn Vận Hành Project RAG

Tài liệu này mô tả:
- Các bước chạy hệ thống từ đầu đến cuối.
- Ý nghĩa từng lệnh CLI.
- Quy trình review ảnh thủ công (khuyến nghị cho chất lượng image retrieval tốt hơn).

---

## 1) Mục tiêu hệ thống

Project xử lý dữ liệu SGK thành 2 lớp:
1. `Text index`: phục vụ trả lời nội dung văn bản.
2. `Image index`: phục vụ tìm ảnh minh họa liên quan câu hỏi.

Ngoài ra có cơ chế:
- Extract ảnh từ page.
- Export ảnh ra file review.
- Người dùng sửa caption/xóa ảnh không phù hợp.
- Apply lại vào vector DB.

---

## 2) Chuẩn bị môi trường

### 2.1 Cài dependencies

```bash
pip install -r requirements.txt
```

### 2.1b Nếu chạy trên Google Colab

Cần cài thêm thư viện hệ thống cho `pdf2image` và OCR tiếng Việt:

```python
!apt-get update
!apt-get install -y poppler-utils
!apt-get install -y tesseract-ocr tesseract-ocr-vie
```

### 2.2 Tạo file `.env`

```bash
cp .env.example .env
```

### 2.3 Biến quan trọng

- `HF_TOKEN`: bắt buộc để tải model từ Hugging Face.
- `USE_GPU=true|false`: bật/tắt GPU.
- `IMAGE_CAPTION_ENABLED=true|false`: bật/tắt caption model cho ảnh.
- `IMAGE_EXTRACTION_VERSION=v2`: version thuật toán extract ảnh, đổi version sẽ buộc reprocess image page.
- `IMAGE_REVIEW_MANIFEST_PATH=database/image_review_manifest.jsonl`: nơi lưu manifest review ảnh.

---

## 3) Danh sách lệnh và mục đích

## `python main.py --text-only`
- Chạy ETL cho text.
- Dùng khi:
  - bạn mới tạo DB.
  - hoặc chỉ cần cập nhật văn bản.

## `python main.py --image-only`
- Chạy ETL cho image.
- Dùng khi:
  - bạn cần extract/index ảnh.
  - vừa nâng version extract ảnh.

## `python main.py --etl`
- Chạy full pipeline text + image trong 1 lệnh.
- Dùng cho build nhanh, không cần tách bước.

## `python main.py --export-image-review <output.json>`
- Export danh sách ảnh đã extract để con người review.
- File output là JSON array để sửa trực tiếp:
  - `caption_vi_manual`
  - `keywords_vi_manual`
  - `review_status` (`pending|approved|edited|rejected`)
  - `is_active` (`true|false`)

## `python main.py --apply-image-review <review.json> --review-user <name>`
- Áp các chỉnh sửa review vào DB:
  - ảnh `rejected`/`is_active=false` sẽ bị loại khỏi retrieval.
  - ảnh approved/edited sẽ được upsert metadata mới.

## `python main.py --export-image-review <output.json> --review-pdf "<file.pdf>"`
- Export review theo 1 PDF cụ thể.

## `python main.py --export-image-review <output.json> --review-include-completed`
- Export cả ảnh đã review trước đó.
- Mặc định chỉ export ảnh pending.

## `python main.py --app`
- Mở Gradio app để hỏi đáp và xem ảnh.

---

## 4) Quy trình khuyến nghị

## Kịch bản A: Khởi tạo mới hoàn toàn

1. Xóa DB cũ:

```powershell
Remove-Item -Recurse -Force "D:\personal_repo\project_rag\database"
New-Item -ItemType Directory -Path "D:\personal_repo\project_rag\database" | Out-Null
```

2. ETL text:

```bash
python main.py --text-only
```

3. ETL image:

```bash
python main.py --image-only
```

4. Export file review:

```bash
python main.py --export-image-review database/review_images.json
```

5. Người dùng cập nhật thủ công `database/review_images.json`.

6. Apply review:

```bash
python main.py --apply-image-review database/review_images.json --review-user charlie
```

7. Chạy app:

```bash
python main.py --app
```

## Kịch bản B: Build nhanh 1 lệnh

```bash
python main.py --etl
```

## Kịch bản C: Chỉ review một tài liệu

```bash
python main.py --export-image-review database/review_sgk6.json --review-pdf "SGK KHTN 6 CD.pdf"
python main.py --apply-image-review database/review_sgk6.json --review-user charlie
```

---

## 5) Reset và xử lý sự cố

Script `reset_status.py`:

## Reset trạng thái image cho tất cả page
```bash
python reset_status.py --all
```

## Xóa image vector collections
```bash
python reset_status.py --image-index
```

## Reset cả status + image index
```bash
python reset_status.py --images-full
```

## Reset image status theo 1 file PDF
```bash
python reset_status.py "D:/personal_repo/project_rag/data/SGK KHTN 6 CD.pdf"
```

---

## 6) Kiểm tra sau khi chạy

Xác nhận các file/thư mục:
- `database/chroma.sqlite3`
- `database/images/...`
- `database/image_review_manifest.jsonl`

Kiểm tra nhanh CLI:

```bash
python main.py --help
```

---

## 7) Gợi ý vận hành ổn định

- Nếu muốn tăng tốc ETL ảnh: tạm để `IMAGE_CAPTION_ENABLED=false` và dùng flow review thủ công.
- Khi đổi thuật toán extract ảnh, tăng `IMAGE_EXTRACTION_VERSION` để hệ thống tự biết cần reprocess page image.
- Nên chạy theo thứ tự: `text-only` -> `image-only` -> `export/apply review` -> `app`.
