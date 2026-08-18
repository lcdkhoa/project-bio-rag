# Thiết kế: Rebuild ETL layout-aware + Retrieval reranking (Hướng A)

- **Ngày:** 2026-08-18
- **Trạng thái:** Draft — chờ chủ dự án review
- **Deadline:** 1–2 tuần
- **Hạ tầng chạy ETL:** Google Colab Pro (GPU), DB đổ ra Google Drive (`RAG_DATABASE_DIR`)
- **Quyết định liên quan:** D-01 → D-10 trong `document/decision_log.html`

---

## 1. Bối cảnh & mục tiêu

Hệ RAG trên 12 SGK KHTN (3 NXB: CD/CTST/KNTT) đang gặp 4 lỗi (theo chủ dự án): **cắt hình sai, chunk text trộn/bẩn, retrieve lạc chủ đề, trả lời/trích dẫn sai**. Chẩn đoán (D-01→D-05):

- Text OCR thực chất **tốt (86–94%)** — không phải nút thắt.
- 3/4 lỗi chung một gốc: **pipeline đọc trang như ảnh phẳng, không hiểu bố cục** → sidebar lẫn body → chunk bẩn → embedding bẩn → retrieve lạc → trích dẫn sai.
- Retrieval: nút thắt ở **xếp hạng** (recall production 0.63 vs trần 0.84), MiniLM yếu với câu ngắn/trừu tượng.
- Corpus: đã thay KNTT8 (vốn là Sách giáo viên) & KNTT9 (vốn 2-up) bằng bản SGK học sinh sạch.

**Mục tiêu:** rebuild sạch toàn bộ index; viết lại **có trọng điểm** (giữ phần đang tốt) để cả **số eval** (P/R/MRR + điểm câu trả lời) lẫn **demo** cùng cải thiện.

## 2. Non-goals (YAGNI)

- Không clean-slate toàn bộ codebase; giữ Tesseract OCR, Vintern caption, CLIP, Flask API, khung `AppServices`.
- Không thay LLM sinh (Qwen2.5) trong đợt này (chỉ siết prompt + citation).
- Không làm quiz-generation / pilot trường học / quantization (hướng tương lai của báo cáo).
- Không đặt cược pipeline vào Vision-LLM (Hướng B đã loại); chỉ cân nhắc VLM cho **riêng** ca figure radial nếu còn thời gian.

## 3. Nguyên tắc thiết kế

Mỗi bước ETL là một **module tách biệt, I/O rõ ràng, test độc lập được**. Trả lời được cho từng module: *làm gì / dùng thế nào / phụ thuộc gì*. File phình to = tín hiệu tách nhỏ (đặc biệt `image_processor.py` ~4000 dòng).

---

## 4. Kiến trúc ETL (offline, mỗi trang)

Chuỗi 7 module, dữ liệu chảy tuyến tính:

```
PDF page
  → [1 page_render]      ảnh trang (DPI/variant)
  → [2 preprocess]       ảnh sạch (deskew + xoá watermark/dấu mép)
  → [3 layout_segmenter] danh sách Region{type,bbox,reading_order}
  → [4 text_extractor]   TextUnit{region_type, text, order}   (OCR riêng từng vùng)
  → [4b diacritic_fix]   TextUnit.text đã sửa dấu
  → [5 chunker]          Chunk{text, metadata}   (body theo cấu trúc; box giữ khối)
  → [6 figure_extractor] Figure{crop, caption_text, vintern_caption, clip_vec}
  → [7 indexer]          ghi ChromaDB + checkpoint theo hash
```

### 4.1 `page_render`
- pymupdf rasterize ở DPI cố định theo variant (mặc định ~220 DPI hiệu dụng render). Trả `PIL.Image` + kích thước points.
- Xử lý cuốn ghép-mảnh (CD6/CD8) bằng cách render **nguyên trang** (không extract embedded image trực tiếp).

### 4.2 `preprocess`
- Deskew nhẹ (nếu lệch), grayscale/threshold tuỳ chọn cho OCR.
- **Xoá watermark logo trung tâm** + **dấu cá nhân mép trái KNTT9** (mask vùng cố định theo variant). Watermark logo mờ: làm mờ/nâng nền để giảm lẫn vào figure crop.
- Output: ảnh sạch cho các bước sau. *Không* phá nội dung.

### 4.3 `layout_segmenter` ⭐ (module trục)
- **Input:** ảnh sạch. **Output:** `List[Region]`, mỗi region có `type ∈ {main_text, sidebar_box, info_box, figure, caption, page_artifact}`, `bbox`, `reading_order`.
- **Phương pháp (CV cổ điển, không train):**
  1. **Phát hiện box màu:** sidebar/info-box có nền bão hoà màu (xanh CTST, hồng "Em có biết", vàng/tím CD) → mask theo saturation/hue trong HSV + tìm contour hình chữ nhật lớn.
  2. **Tách cột & thứ tự đọc:** dùng `pytesseract image_to_data` (level block/par) lấy geometry khối text; chiếu histogram theo trục X để phát hiện ranh cột (main vs sidebar). Sắp thứ tự đọc: cột chính trên→dưới trước, box đọc sau theo vị trí.
  3. **Vùng figure:** vùng lớn *không phải* text-block và *không phải* box màu, nằm gần một **anchor caption** ("Hình X.Y" theo regex per-variant hiện có) → figure region.
  4. **page_artifact:** số trang, header/footer, toolbar sót (an toàn kép cho KNTT9) → loại.
- **Per-variant:** regex caption & vị trí sidebar khác nhau giữa CD/CTST/KNTT → tham số hoá theo variant (tái dùng `get_pdf_variant`).
- **Kiểm chứng:** overlay trực quan (xem §7), không chỉ unit test.

### 4.4 `text_extractor`
- OCR **từng region text riêng** (Tesseract vie) theo reading_order → `TextUnit`.
- `main_text` các cột nối lại thành thân bài đúng thứ tự; mỗi `sidebar_box`/`info_box` là một unit riêng, gắn `region_type`.
- Giữ tên riêng khoa học nguyên trạng (không "sửa" oxygen/sulfuric...).

### 4.4b `diacritic_fix` (D-09)
- Pass hậu xử lý sửa dấu tiếng Việt: từ điển tần suất + luật (vd "tổn tại"→"tồn tại", "giây"→"giấy" theo ngữ cảnh). Thận trọng: **không** đụng thuật ngữ khoa học/tiếng Anh, danh từ riêng. Có allowlist. Đo tỉ lệ sửa đúng trên mẫu.

### 4.5 `chunker`
- **Body:** chunk theo cấu trúc (ranh heading/đoạn) với target ~`CHUNK_SIZE` + overlap, nhưng **không cắt giữa câu/ý** nếu tránh được.
- **Box:** giữ nguyên khối (atomic), không gộp vào body.
- **Metadata mỗi chunk:** `source` (book), `page` (trang sách thật), `region_type`, `section_heading` (nếu có), `variant`.

### 4.6 `figure_extractor`
- Với mỗi `figure` region: crop + padding; dedupe; gắn caption text ("Hình X.Y ...") + Vintern caption tiếng Việt; CLIP embed.
- Ca khó (radial CD8 / multi-panel a/b/c/d): pad rộng + **flag review** (giữ human-in-the-loop hiện có). Tuỳ chọn: gọi VLM mô tả cho riêng ca flagged nếu còn thời gian.
- Ghi `biology_images` + `biology_image_metadata` với `page`, `bbox`, `caption`, `figure_label`.

### 4.7 `indexer` + checkpoint
- Ghi text chunk → `biology_text`; figure → image collections.
- **Sửa bẫy trùng tên (quan trọng):** checkpoint key theo **hash nội dung file**, không theo tên. Khi rebuild: xoá `processed_files.txt`/`processed_images.txt` + `processing_status`. File mới trùng tên nhưng khác hash → xử lý lại đúng.

---

## 5. Kiến trúc Retrieval (online)

- **`embeddings` (D-07):** `BAAI/bge-m3` (1024-dim, free). Giữ MiniLM làm fallback nếu A/B (recall_at_k) không thắng. → rebuild collection (đã nằm trong kế hoạch).
- **`retriever` (D-08):** nới `FETCH_K` (vd 8→20) → **`BAAI/bge-reranker-v2-m3`** rerank → giữ top `MAX_K`. Giữ `RelevanceGatedRetriever` làm lưới an toàn sau rerank.
- **Sidebar (D-10):** chunk box vẫn index, phân biệt bằng `region_type` → có thể ưu tiên body cho câu lý thuyết, dùng box khi liên quan; không nhiễu body.
- **Image side:** giữ CLIP + metadata + lexical + gate (đang ổn).
- **`generation`:** siết prompt (bám ngữ cảnh, đóng vai GV Sinh học, trả lời tiếng Việt) + **trích dẫn `[Sách, trang]`** dùng metadata đã đúng + gate hình để không kèm hình lệch.

---

## 6. Data model / metadata (chuẩn hoá)

Chunk text (`biology_text`):
```
{ text, source, page, variant, region_type, section_heading?, chunk_index }
```
Figure (`biology_images` / `biology_image_metadata`):
```
{ image_id, source, page, variant, bbox, figure_label, caption_text, vintern_caption,
  review_status, is_active }
```

## 7. Chiến lược test & phản biện

- **`layout_segmenter`:** mở rộng `src/test/test_image_extraction_full.py` để vẽ **overlay loại-vùng** (màu theo type) trên trang đại diện mỗi variant → QA mắt. Đây là công cụ QA chính.
- **`chunker`:** fixture pages → assert "không có text sidebar trong body chunk"; snapshot chunk.
- **`diacritic_fix`:** đo precision sửa trên mẫu gán nhãn tay (không được làm hỏng text đúng).
- **Retrieval:** `recall_at_k.py` before/after; A/B embedding (bge-m3 vs MiniLM) và reranker on/off; `evaluator.py` cho điểm câu trả lời.
- **Phản biện code (D-06):** sau mỗi module, một lượt review đối kháng tìm bug ẩn (off-by-one bbox, reading-order sai, rò watermark, sai metadata trang, cache/checkpoint stale).

## 8. Lộ trình (milestones)

- **M0 — Reset sạch:** wipe `database/` + checkpoint; verify 2 file KNTT mới (đã xong phần verify).
- **M1 — Data path (tuần 1):** `preprocess` + `layout_segmenter` + `text_extractor` + `diacritic_fix` + `chunker` → re-ETL text 12 cuốn trên Colab. *Hết chunk bẩn.*
- **M2 — Retrieval (tuần 1):** bge-m3 + reranker + prompt/citation → chạy eval. *Cú nhảy số lớn nhất.*
- **M3 — Images (tuần 2):** `figure_extractor` theo layout + caption + review. *Demo hình đúng.*
- **M4 — Eval & docs (tuần 2):** eval đầy đủ, cập nhật số cho báo cáo, update CLAUDE.md + memory + decision log.

## 9. Rủi ro & giảm thiểu

| Rủi ro | Giảm thiểu |
|---|---|
| Layout segmenter sai trên bố cục lạ | QA overlay từng variant; fallback: cả trang là 1 main_text nếu không phát hiện box |
| bge-m3/reranker chậm khi serve demo | rerank chỉ trên FETCH_K nhỏ; cân nhắc GPU demo hoặc cache |
| diacritic_fix làm hỏng thuật ngữ | allowlist + đo precision, chỉ sửa khi độ tin cao |
| ETL Colab đứt phiên | checkpoint theo hash + DB trên Drive (đã có cơ chế) |
| Radial figure vẫn khó | pad rộng + flag review; VLM chỉ cho ca flagged |

## 10. Quyết định đã chốt (từ open questions)

1. **`page` metadata = số trang IN TRÊN SÁCH** (OCR từ góc/chân trang), fallback index PDF nếu OCR số fail. Trích dẫn khớp sách giấy học sinh cầm. (D-11)
2. **Demo thiết kế an toàn cho cả GPU lẫn CPU:** reranker chạy trên FETCH_K nhỏ + có đường lui CPU (cache/giới hạn ứng viên); chốt hạ tầng demo sau. (D-12)
