# Hướng dẫn mở rộng & phát triển

Tài liệu dành cho người muốn tiếp tục phát triển dự án: thêm sách, thêm biến thể nhà xuất bản,
tinh chỉnh truy xuất, thêm endpoint API, hoặc đổi mô hình. Mỗi mục nêu rõ **đụng vào file nào**
và **cần kiểm chứng ra sao**.

Trước khi đọc tài liệu này nên nắm kiến trúc tổng thể ở
[technical_handover_rag.md](technical_handover_rag.md).

---

## 1) Thêm một cuốn sách mới

1. Đặt file PDF vào `datasources/`. **Tên file quyết định biến thể NXB**:
   - chứa `CTST` → xử lý theo Chân Trời Sáng Tạo,
   - chứa `KNTT` → Kết Nối Tri Thức,
   - còn lại → mặc định Cánh Diều (CD).

   (Logic ở `get_pdf_variant()` / `make_image_processor()` trong `src/etl/image_processor.py`;
   nhận diện cả tên cách nhau bằng dấu cách lẫn gạch dưới.)
2. Chạy ETL — checkpoint resume sẽ bỏ qua sách đã xử lý, chỉ làm sách mới:
   ```bash
   python main.py --etl
   ```
3. (Tùy chọn) Export review ảnh của riêng cuốn đó để tinh chỉnh metadata:
   ```bash
   python main.py --export-image-review database/review_new.json --review-pdf "<tên file>.pdf"
   ```
4. Sinh test set + đánh giá cho cuốn mới: xem [src/test/README.md](../src/test/README.md).

Không cần sửa code nếu cuốn mới thuộc một trong 3 NXB đã hỗ trợ.

---

## 2) Thêm/điều chỉnh biến thể nhà xuất bản

ETL ảnh dùng kiến trúc **anchor-first deterministic**, tinh chỉnh riêng cho từng NXB bằng cách
kế thừa lớp `ImageProcessor` (base = Cánh Diều) trong `src/etl/image_processor.py`:

- `ImageProcessor` — base class, theo quy ước CD.
- `CtsstImageProcessor` — override cho Chân Trời Sáng Tạo.
- `KnttImageProcessor` — override cho Kết Nối Tri Thức (nhãn "pill" nằm **trên** hình).

Các bước thêm một NXB mới:
1. Thêm hằng `_VARIANT_xxx` và nhánh trong `get_pdf_variant()` + `make_image_processor()`.
2. Tạo lớp con kế thừa `ImageProcessor`, override các hook cần thiết (ví dụ
   `detect_regions_anchor_first()`, `_classify_text_anchors()`, `_build_figure_composites()`).
3. Bump `IMAGE_EXTRACTION_VERSION` trong `.env` để buộc reprocess.
4. QA bằng công cụ trực quan **không đụng DB**:
   ```bash
   python src/test/test_image_extraction_full.py   # render page + overlay anchor/region + crop PNG
   ```

Quy ước bố cục từng NXB, tín hiệu anchor và playbook chi tiết nằm trong
[../skills/etl-textbook-images/](../skills/etl-textbook-images/) (`SKILL.md`, `page-taxonomy.md`, `runbook.md`).

---

## 3) Tinh chỉnh truy xuất (retrieval)

Mọi tham số nằm trong `src/config.py` và có thể override qua `.env`:

**Text retrieval** (`src/rag/vectorstore.py`):
- `RETRIEVER_FETCH_K` — số ứng viên kéo ra trước khi lọc.
- `RETRIEVER_MAX_K` — số chunk tối đa giữ lại (giới hạn kích thước context).
- `RETRIEVER_DISTANCE_MARGIN` — "relevance gate": chỉ giữ chunk có khoảng cách trong
  `(1 + margin) * best_distance`, để loại chunk lạc đề.

**Image retrieval** (`src/rag/image_vectorstore.py`):
- `IMAGE_RETRIEVER_K`, `IMAGE_RETRIEVER_FETCH_K`, `IMAGE_METADATA_FETCH_K` — độ rộng truy xuất.
- `IMAGE_RELEVANCE_THRESHOLD` — ngưỡng giữ ảnh.
- Trọng số rerank (visual / metadata / lexical / phrase / page-boost) nằm trong hàm `_rerank()`.

**Định tuyến ý định** (`src/rag/query_intent.py`): điều chỉnh các từ khóa nhận diện
"câu hỏi đòi ảnh" / "chỉ cần ảnh" (`has_image_intent`, `is_image_only_query`).

Sau khi đổi, đo lại bằng `python src/test/recall_at_k.py` (nhanh, không gọi LLM) rồi
`python src/test/evaluator.py` (đầy đủ).

---

## 4) Đổi mô hình (LLM / embedding / caption)

Tất cả khai báo trong `src/config.py` (đọc từ `.env`):

| Biến | Mặc định | Dùng ở |
|---|---|---|
| `EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | text + metadata embedding |
| `LLM_MODEL` | `Qwen/Qwen2.5-3B-Instruct` | sinh câu trả lời (`src/rag/llm.py`) |
| `CLIP_MODEL` | `openai/clip-vit-base-patch16` | embedding thị giác cho ảnh |
| `OWL_VIT_MODEL` | `google/owlvit-base-patch32` | phát hiện vùng ảnh trong ETL |
| `IMAGE_CAPTION_MODEL` | `5CD-AI/Vintern-1B-v2` | caption ảnh (`src/etl/image_captioner.py`) |

Đổi embedding hoặc tăng/giảm chiều embedding **bắt buộc rebuild** vector DB (xóa `database/`
và ETL lại). Chạy offline thì tải sẵn model: `python src/utils/download_models.py`.

---

## 5) Thêm endpoint API

API định nghĩa trong `src/app/api.py` (Flask). Các thành phần nặng (vector DB, LLM,
retriever, chain) được nạp **một lần** qua singleton `AppServices` trong
`src/app/dependencies.py` — endpoint mới nên lấy service từ đây thay vì khởi tạo lại.

Quy ước:
- Trả JSON, bật sẵn CORS.
- Việc nặng/chạy lâu (ETL) nên đẩy sang background thread như `/api/etl`.
- Stream câu trả lời theo mẫu SSE ở `create_chat_stream_response()`.

Cập nhật [api_server_docs.md](api_server_docs.md) khi thêm/đổi endpoint.

---

## 6) Quy ước & lưu ý chung

- **Checkpoint theo version**: đổi thuật toán ETL ảnh thì phải bump `IMAGE_EXTRACTION_VERSION`,
  nếu không hệ thống coi page là "đã xử lý" và bỏ qua.
- **CRUD metadata ảnh** đi qua `ImageReviewManager` (`src/etl/image_review.py`) — đừng sửa tay
  Chroma/SQLite, dùng `--upsert-image-review-item` / `--apply-image-review` / `--replace-image-db`.
- `database/` được sinh ra khi chạy và bị `.gitignore` (riêng `chroma.sqlite3` theo dõi qua Git LFS).
- Tài liệu QA ảnh không bao giờ ghi vào status DB — an toàn để chạy thử nhiều lần.
