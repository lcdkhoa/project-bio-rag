# Biology RAG — Trợ lý hỏi đáp SGK Khoa học tự nhiên (Text + Image)

Hệ thống **RAG (Retrieval-Augmented Generation)** trả lời câu hỏi dựa trên Sách giáo khoa
Khoa học tự nhiên (SGK KHTN) bậc THCS. Người dùng hỏi bằng tiếng Việt, hệ thống truy xuất
**đoạn văn bản** và **hình ảnh minh họa** liên quan từ SGK rồi sinh câu trả lời có trích nguồn.

Dữ liệu nguồn là PDF SGK scan (ảnh chụp trang), nên hệ thống tự OCR tiếng Việt và trích xuất
hình ảnh theo bố cục của từng nhà xuất bản (Cánh Diều, Chân Trời Sáng Tạo, Kết Nối Tri Thức).

> Người mới tiếp nhận dự án nên đọc theo thứ tự: **README này → [document/technical_handover_rag.md](document/technical_handover_rag.md) (kiến trúc) → [document/phat_trien_mo_rong.md](document/phat_trien_mo_rong.md) (cách mở rộng)**.

---

## 1) Hệ thống làm gì

- **ETL text**: OCR tiếng Việt từng trang PDF → chia chunk → index vào ChromaDB.
- **ETL image**: phát hiện/cắt ảnh theo từng trang (anchor-first + OWL-ViT, theo từng NXB) →
  sinh caption/keyword bằng mô hình thị giác → index ảnh + metadata.
- **Retrieval lai (hybrid)**: gộp truy xuất text + ảnh, định tuyến theo ý định câu hỏi
  (câu hỏi đòi ảnh sẽ ưu tiên kênh ảnh).
- **Sinh câu trả lời**: LLM Qwen2.5 trả lời bằng tiếng Việt, chỉ dựa trên ngữ cảnh SGK, kèm trích nguồn.
- **Human-in-the-loop**: export metadata ảnh ra file để người dùng sửa caption/loại ảnh sai,
  rồi apply ngược lại nhằm tăng độ chính xác của image retrieval.
- **Flask API**: phục vụ chat (có streaming), upload PDF chạy ETL, và CRUD metadata ảnh cho frontend.

---

## 2) Kiến trúc tổng quan

```
                 ┌─────────────────────────── ETL (offline) ───────────────────────────┐
  PDF SGK  ─────▶│  OCR (Tesseract vie)                                                  │
 datasources/    │     │                                                                 │
                 │     ├─▶ TextSplitter ──▶ ChromaDB: biology_text                        │
                 │     │                                                                  │
                 │     └─▶ ImageProcessor (anchor-first + OWL-ViT, per-variant)           │
                 │            │   └─▶ ImageCaptioner (VLM) ──▶ caption_vi / keywords_vi    │
                 │            └─▶ ChromaDB: biology_images (CLIP) + biology_image_metadata │
                 │                 └─▶ image_review_manifest.jsonl ◀── human review CRUD   │
                 └───────────────────────────────────────────────────────────────────────┘
                                                  │
                 ┌──────────────────────── Truy vấn (online) ──────────────────────────┐
  Câu hỏi  ─────▶│  HybridRetriever ──┬─▶ text store (RelevanceGatedRetriever)          │
  (Flask API)    │   (query_intent)   └─▶ image store (CLIP + metadata + rerank)        │
                 │        │                                                             │
                 │        └─▶ BiologyRAG (prompt) ──▶ Qwen2.5 LLM ──▶ answer + gallery   │
                 └─────────────────────────────────────────────────────────────────────┘
```

**4 khối chính** (chi tiết: [document/technical_handover_rag.md](document/technical_handover_rag.md)):

| Khối | Module chính | Vai trò |
|---|---|---|
| Ingestion + ETL text | `src/etl/loaders.py`, `text_splitter.py`, `cleaner.py` | OCR + chunk + index text |
| ETL image + review | `src/etl/image_processor.py`, `image_captioner.py`, `image_review.py` | Cắt ảnh, caption, CRUD metadata |
| Storage + retrieval | `src/rag/vectorstore.py`, `image_vectorstore.py`, `hybrid_retriever.py`, `query_intent.py` | Vector store + truy xuất lai |
| QA chain + API | `src/rag/chain.py`, `llm.py`, `src/app/api.py`, `dependencies.py` | Prompt + LLM + Flask API |

---

## 3) Cấu trúc thư mục

```
main.py                  # Entry CLI: ETL, review CRUD, chạy API
requirements.txt
.env.example             # Mẫu cấu hình — copy thành .env
datasources/             # PDF SGK đầu vào (12 cuốn)
database/                # Sinh ra khi chạy: Chroma DB, ảnh crop, manifest, checkpoint
windows_tools/           # poppler.zip, tesseract-ocr.zip (tiện cài trên Windows)
src/
  config.py              # Cấu hình tập trung, đọc từ .env
  etl/                   # Pipeline ETL text + image
  rag/                   # Vector store, retriever, LLM, QA chain
  app/                   # Flask API + dependency singleton
  utils/download_models.py  # Tải sẵn model để chạy offline
  test/                  # Bộ đánh giá RAG (IR metrics + LLM judge) & QA ETL ảnh
document/                # Tài liệu kỹ thuật & vận hành (xem document/README.md)
skills/etl-textbook-images/  # Runbook chi tiết cho ETL ảnh theo NXB
```

---

## 4) Cài đặt

```bash
pip install -r requirements.txt
cp .env.example .env
```

Thiết lập tối thiểu trong `.env`:
- `HF_TOKEN=<your_token>` — bắt buộc để tải model từ Hugging Face.
- `USE_GPU=true` — nếu máy có GPU (CUDA).

### OCR trên Windows

Cần Poppler (render PDF) và Tesseract (OCR tiếng Việt). Khai báo trong `.env`:

```env
TESSERACT_CMD=C:/Program Files/Tesseract-OCR/tesseract.exe
POPPLER_PATH=C:/poppler/Library/bin
```

Repo có sẵn `windows_tools/poppler.zip` và `windows_tools/tesseract-ocr.zip`.
Hướng dẫn giải nén và khai báo path: [document/windows_tools_setup.md](document/windows_tools_setup.md).

### OCR trên Google Colab / Linux

```bash
apt-get update
apt-get install -y poppler-utils tesseract-ocr tesseract-ocr-vie
```

Trên Colab nên trỏ database vào Google Drive để không mất dữ liệu khi runtime ngắt:

```python
from google.colab import drive; drive.mount("/content/drive")
import os
os.environ["RAG_DATABASE_DIR"] = "/content/drive/MyDrive/project_bio_rag/database"
```

Chi tiết Colab/Drive & xử lý sự cố: [document/huong_dan_van_hanh_rag.md](document/huong_dan_van_hanh_rag.md).

---

## 5) Quy trình sử dụng (khuyến nghị)

```bash
# 1. Build text index
python main.py --text-only

# 2. Build image index (cắt ảnh + caption)
python main.py --image-only

# 3. Export metadata ảnh để người dùng review
python main.py --export-image-review database/review_images.json

# 4. (Thủ công) sửa caption / loại ảnh sai trong file JSON

# 5. Apply review trở lại DB
python main.py --apply-image-review database/review_images.json --review-user charlie

# 6. Chạy API
python main.py --api --port 5000
```

Muốn build nhanh text + image trong một lệnh: `python main.py --etl`.

> ETL có **checkpoint resume**: chạy lại sẽ bỏ qua trang đã xử lý. Muốn ép trích xuất ảnh lại,
> đổi `IMAGE_EXTRACTION_VERSION` trong `.env` (xem mục 6 của [huong_dan_van_hanh_rag.md](document/huong_dan_van_hanh_rag.md)).

---

## 6) Bảng lệnh CLI

| Lệnh | Mục đích |
|---|---|
| `python main.py --text-only` | ETL text (OCR + chunk + index text) |
| `python main.py --image-only` | ETL image (cắt ảnh + metadata + index image) |
| `python main.py --etl` | ETL full text + image |
| `python main.py --import-images-dir <dir>` | Import ảnh từ thư mục local, bỏ qua PDF |
| `python main.py --export-image-review <path.json>` | Export ảnh để reviewer chỉnh caption/loại ảnh sai |
| `python main.py --export-image-db <path.json>` | Export snapshot toàn bộ metadata DB (manifest) |
| `python main.py --upsert-image-review-item <item.json> --review-user <name>` | Upsert 1 item metadata theo `image_id` |
| `python main.py --apply-image-review <path.json> --review-user <name>` | Apply batch review vào DB + sync image index |
| `python main.py --replace-image-db <path.json> --review-user <name>` | Replace toàn bộ manifest + rebuild image index theo snapshot |
| `python main.py --api --port <port>` | Chạy Flask API server (mặc định 5000) |

Cờ phụ: `--review-pdf "<file.pdf>"` lọc theo 1 cuốn; `--review-include-completed` export cả item đã duyệt.

**Quy tắc apply/upsert/replace (quan trọng):**
1. `--apply-image-review` là **upsert theo item** trong file JSON, không phải sync full.
2. Xóa item khỏi array JSON **không** đồng nghĩa xóa item khỏi DB (trừ `--replace-image-db`).
3. Loại ảnh khỏi retrieval: đặt `review_status=rejected|deleted`, hoặc `is_active=false`, hoặc `delete=true`.
4. `--replace-image-db` coi file JSON là nguồn sự thật: item không còn trong file sẽ bị xóa khỏi manifest và image index.

Ví dụ JSON cho từng kịch bản (upsert 1 item, replace toàn bộ DB...) xem
[document/huong_dan_van_hanh_rag.md](document/huong_dan_van_hanh_rag.md) mục 5.

---

## 7) Flask API

```bash
python main.py --api --port 5000
```

| Endpoint | Method | Mô tả |
|---|---|---|
| `/api/chat` | POST | Hỏi đáp RAG, trả answer + gallery ảnh |
| `/api/chat/stream` | POST | Trả lời dạng SSE stream (render từng phần) |
| `/api/etl` | POST | Upload PDF và chạy ETL nền |
| `/api/etl/status` | GET | Poll tiến trình ETL theo `filename` |
| `/api/images` | GET / PUT / POST | Lấy / thay thế metadata ảnh (cho UI review) |
| `/images/<path>` | GET | Serve file ảnh tĩnh |

Chi tiết request/response & ví dụ frontend: [document/api_server_docs.md](document/api_server_docs.md).

---

## 8) Đánh giá chất lượng

Bộ đánh giá trong `src/test/` đo **chất lượng truy xuất** (Precision/Recall/F1/MRR@K — số liệu
IR xác định) và **chất lượng câu trả lời** (một LLM thứ 2 chấm 1–5).

```bash
python -m src.test.build_testset                       # sinh bộ test (cần EVAL_LLM_* trong .env), rồi --mark-reviewed
python -m src.test.run_eval                             # chạy RAG thật, LLM thứ 2 chấm, gộp theo LOẠI câu hỏi (D-182)
python -m src.test.retrieval_benchmark --build-cache    # bảng đối chiếu 4 phương pháp truy vấn, không gọi LLM (D-182)
```

Chi tiết: [src/test/README.md](src/test/README.md).

---

## 9) Mở rộng & phát triển

Hướng dẫn dành cho người muốn thêm sách mới, thêm biến thể NXB, tinh chỉnh retrieval,
hay thêm endpoint API: **[document/phat_trien_mo_rong.md](document/phat_trien_mo_rong.md)**.

---

## 10) Tài liệu

| Tài liệu | Nội dung |
|---|---|
| [document/technical_handover_rag.md](document/technical_handover_rag.md) | Kiến trúc, code flow, schema metadata ảnh |
| [document/huong_dan_van_hanh_rag.md](document/huong_dan_van_hanh_rag.md) | Vận hành chi tiết, CRUD metadata, reset & sự cố |
| [document/image_etl_technical.md](document/image_etl_technical.md) | Thuật toán ETL ảnh (anchor-first, OWL-ViT) |
| [document/api_server_docs.md](document/api_server_docs.md) | Tham chiếu Flask API |
| [document/phat_trien_mo_rong.md](document/phat_trien_mo_rong.md) | Hướng dẫn mở rộng/phát triển |
| [document/windows_tools_setup.md](document/windows_tools_setup.md) | Cài Poppler/Tesseract trên Windows |
| [skills/etl-textbook-images/](skills/etl-textbook-images/) | Runbook chi tiết cho ETL ảnh theo NXB |

Xem [document/README.md](document/README.md) để có bản đồ tài liệu đầy đủ.
