# Thiết kế: M3 — Cắt hình layout-aware (reuse + layout bridge)

- **Ngày:** 2026-08-19
- **Trạng thái:** Draft — chờ chủ dự án review
- **Milestone:** M3 (mảnh cuối của redesign 2026-08; M1 text ETL + M2 retrieval rerank đã xong & merge master)
- **Nhánh:** `worktree-m3-figure-extraction`
- **Quyết định liên quan:** D-05 (Hướng A), D-10 (sidebar-as-chunk), D-15 (box nhạt màu / cảnh báo radial), D-18 (ảnh làm sau M3). Sẽ log tiếp D-21… khi chốt.
- **Spec tổng:** `document/specs/2026-08-18-rag-etl-retrieval-redesign-design.md` (§4.6 figure_extractor)

---

## 1. Bối cảnh & mục tiêu

Redesign 2026-08 sửa 4 lỗi. M1 (layout text ETL) đã xử **3/4** lỗi — nhưng cả 3 là lỗi **text** (chunk bẩn → retrieve lạc → citation sai), chung gốc "đọc trang như ảnh phẳng". Lỗi thứ 4 — **cắt hình sai** — có gốc **khác**: sự **mong manh của heuristic CV per-variant** trong `image_processor.py`, không phải "phẳng". Bộ detect hiện tại (`detect_regions_anchor_first`) đã khá layout-aware theo cách riêng.

Vì vậy **cái mà tầng layout mang lại cho FIGURE** không phải "thay bộ detect", mà là:
1. **Dùng vùng box (sidebar/info-box) của segmenter làm vùng loại trừ + kiểm chứng** → không cắt nhầm sidebar thành figure.
2. **Đưa figure/caption vào cùng một mô hình `Region`** → QA overlay thấy cả text-box lẫn figure trong một ảnh.

**Mục tiêu M3:** cắt hình đúng hơn (ít over-crop lấn text/box, ít sidebar-thành-figure) **mà không viết lại** 4919 dòng logic per-variant đã trui rèn qua v7→v15; giữ nguyên schema metadata → `biology_images`/`biology_image_metadata`, caption Vintern, CLIP, và vòng human-review.

### Quyết định phạm vi (từ brainstorming, chủ dự án chốt)
- **Nguồn figure = REUSE + layout bridge** (không rewrite, không hybrid-fallback).
- **Validate CD trước** (base `ImageProcessor`), rồi CTST/KNTT.
- **QA gate = trực quan ~5 trang/variant**, có chủ đích các ca khó, đối chiếu regression với output hiện tại.

## 2. Non-goals (YAGNI)

- **KHÔNG** viết lại `detect_regions_anchor_first` hay các builder per-variant (CTST band, KNTT pill, sub-figure splitter). Giữ nguyên.
- **KHÔNG** đổi schema metadata ảnh, `ImageVectorDB.add_documents`, hay JSON semantics của vòng review (`--export/apply/replace-image-review`).
- **KHÔNG** clip (cắt xén) bbox figure theo ranh box trong M3 — chỉ **drop** (xem §4, rủi ro radial). Clip là follow-up nếu QA cho thấy cần.
- **KHÔNG** đổi captioner Vintern, CLIP model, hay OWL-ViT detector phụ.
- **KHÔNG** re-render trang ở DPI khác để reconcile (tránh lệch toạ độ — xem §3).

## 3. Ràng buộc kỹ thuật đã kiểm chứng (nền của thiết kế)

> Đã đọc code thật, không đoán. Các điểm này là trục chống-bug của M3.

1. **Không gian toạ độ / màu của detector:** `ImageProcessor._extract_page_image` render bằng **poppler `dpi=150`**, trả `img_array = np.array(PIL)` → **RGB** HxWx3, và `pil_img` (PIL RGB). `detect_regions_anchor_first(pil_img, img_array, text_lines)` làm việc trong **không gian 150-DPI, RGB** này.
2. **`segment_page` kỳ vọng BGR** (`cv2.cvtColor(image, COLOR_BGR2HSV)`), và tham số box của nó được tune trên render **fitz 220-DPI** của M1 (QA CTST7 p40 / KNTT8 p60). → Bridge phải **đổi RGB→BGR** trước khi gọi `segment_page`, và chạy nó **trên chính mảng của detector** để hai tập bbox chung một hệ toạ độ. Tham số phân số (min_area_frac, width-frac) chuyển được; tham số **tuyệt đối `close_kernel=25px`** lệch giữa 150/220 DPI → cần QA, tham số hoá theo DPI nếu lệch.
3. **Lỗ hổng entrypoint (bug thật):** `run_etl_image_only` và `run_etl` tạo `image_processor = ImageProcessor()` — **lớp base**, nên đường ETL loạt **không bao giờ áp routing per-variant**. Sách CTST/KNTT hiện chạy bằng logic base của CD. (QA tool thì dùng `make_image_processor` → QA lệch production.)
4. **`ocr_text_per_page`** trong entrypoint lấy từ `RobustOCRLoader().load_pdf` (OCR phẳng cũ), key theo `doc.metadata.get("page", i+1)`; dùng làm context text cho ảnh. M3 **không cần** đổi (ngoài phạm vi; đây không phải chunk index text của M1).
5. **`RegionType.FIGURE`/`CAPTION`** đã có sẵn trong enum (`src/etl/layout/regions.py`) nhưng `segment_page` **chưa bao giờ phát ra**; `text_extract.py` đã `continue` khi gặp FIGURE. → Bridge lấp chỗ này ở tầng QA/observability, không đụng đường text.
6. **Vòng lặp phụ thuộc import:** `layout.loader`/`layout.segmenter` hiện KHÔNG import `image_processor` (chỉ config/regions). Bridge sẽ import từ `layout.segmenter`/`layout.regions`. `image_processor` gọi bridge qua **local import trong method** để tránh chu trình `image_processor → bridge → segmenter → image_processor`.

## 4. Kiến trúc — chèn một bước reconcile, giữ nguyên phần còn lại

Đường ảnh hiện tại (giữ nguyên toàn bộ trừ 1 bước chèn):

```
_extract_page_image (150 DPI, RGB)
  → detect_regions_anchor_first  → detected_regions [{bbox, image_type}]
  → [MỚI] reconcile_with_layout(detected_regions, img_array_rgb, variant)
  → crop + _ocr_crop_text + Vintern caption + CLIP + metadata schema  (KHÔNG đổi)
  → Document(page_content=search_text, metadata={...})  → image_vdb.add_documents
```

### 4.1 `reconcile_with_layout(regions, img_array_rgb, variant) -> regions`
1. `boxes = segment_page(cv2.cvtColor(img_array_rgb, COLOR_RGB2BGR), variant)` → lấy các Region `SIDEBAR`/`INFO_BOX` (bỏ BODY). **Cùng hệ toạ độ** với `regions` vì cùng mảng.
2. **Drop** một figure region **chỉ khi** phần diện tích của nó nằm trong một box ≥ `FIGURE_IN_BOX_DROP_RATIO` (mặc định **0.80**). Tức figure gần như-toàn-bộ nằm trong sidebar/info-box → là dương-tính-giả.
3. **Bảo thủ, chỉ-drop, ngưỡng cao, KHÔNG clip.** Lý do (D-15): figure **radial CD8** (Hình 8.3/8.4: phân tử trung tâm + các icon-spoke bão hoà màu) có thể bị box-detector nhận nhầm là box; ngưỡng cao + chỉ-drop bảo vệ figure thật khỏi bị ăn. Ngưỡng tính theo **diện tích figure nằm trong box / diện tích figure** (containment), KHÔNG phải IoU đối xứng — để một box lớn bao trùm không "loãng" chỉ số.

### 4.2 `to_layout_regions(regions) -> list[Region]`
Chuyển output detector thành `Region(FIGURE/CAPTION, bbox, reading_order, meta={label,image_type})` cho QA overlay vẽ figure + text-box trong một ảnh. Thuần hàm, không phụ thuộc I/O.

### 4.3 Điểm cắm trong `image_processor.py`
Trong `extract_images_from_pdf`, ngay sau khi có `detected_regions = detection["regions"]`:
```python
from .layout.figure_bridge import reconcile_with_layout  # local import, tránh cycle
detected_regions = reconcile_with_layout(detected_regions, img_array, self.variant)
```
`self.variant` = `get_pdf_variant(pdf_filename)` (đặt trong `__init__` hoặc suy ra tại chỗ). Phần dựng `panel_lookup`, crop, metadata giữ **nguyên** — chỉ tập region đầu vào bị lọc bớt.

## 5. Sửa entrypoint + cache

- `run_etl_image_only` & `run_etl`: trong vòng lặp PDF, đổi `image_processor = ImageProcessor()` (một lần, ngoài loop) → `image_processor = make_image_processor(filename)` **trong loop** cho từng cuốn. Sửa lỗ hổng §3.3. (Các field `status_tracker`/`image_extraction_version`/`captioner` do `make_image_processor` khởi tạo giống base — kiểm khi implement.)
- **Bump `IMAGE_EXTRACTION_VERSION`** (mặc định mới `v16_layout_reconcile`, vẫn override được qua `.env`) để checkpoint theo-version **re-extract mọi trang** thay vì skip cache cũ. Không bump = crop logic đổi nhưng trang cũ bị bỏ qua → QA sai.

## 6. Sửa lỗ hổng `đ`-fold (gộp vào M3, nhỏ, độc lập)

`strip_accents` (dùng bởi kênh **lexical phrase** ảnh trong `image_vectorstore.py`) **không fold `đ`** (U+0111) → truy vấn "cho tôi hình con **đ**om đóm" lệch điểm phrase-match. `citations.py` (M2) đã lập helper `_fold` làm mẫu. M3 áp cùng cách vào kênh lexical ảnh: một fix + test nhắm đích, **không** đụng phần fusion/CLIP. Độc lập với bridge (task riêng).

## 7. Data model / interface (chuẩn hoá)

Bridge — `src/etl/layout/figure_bridge.py`:
```
reconcile_with_layout(regions: list[dict], image_rgb: np.ndarray, variant: str) -> list[dict]
to_layout_regions(regions: list[dict]) -> list[Region]
_containment(fig_bbox, box_bbox) -> float   # dt(giao)/dt(figure), ∈ [0,1]
```
- `regions` giữ đúng shape detector: mỗi phần tử có ít nhất `{"bbox": (x0,y0,x1,y1), "image_type": str}`. Bridge **không thêm/bớt khoá**, chỉ **lọc danh sách**.
- Bridge **thuần** (trừ `segment_page` gọi OpenCV) → unit test bằng fixture tổng hợp, không cần PDF.

Metadata figure (`biology_images`/`biology_image_metadata`): **KHÔNG đổi** so với hiện tại.

## 8. Chiến lược test & phản biện (D-06)

- **Unit (tổng hợp, nhanh):**
  - `reconcile_with_layout`: (a) figure gần-trọn trong box → **drop**; (b) figure chỉ chồng lấn nhẹ box → **giữ**; (c) figure trên nền trắng (không box) → **giữ**; (d) không có box → trả nguyên; (e) hệ toạ độ: khẳng định bridge gọi `segment_page` trên mảng đã RGB→BGR (dùng fake/monkeypatch `segment_page` để chặn phụ thuộc OpenCV nặng và kiểm đúng đối số/định hướng màu).
  - `to_layout_regions`: map `image_type`→`RegionType` đúng, reading_order tăng dần.
  - `đ`-fold: "đom đóm"/"cá đuối" fold khớp biến thể không dấu.
- **Gate trực quan (CD trước, rồi CTST/KNTT):** mở rộng `src/test/test_image_extraction_full.py` (hoặc overlay QA) vẽ figure đã-reconcile + box. **~5 trang/variant** nhắm ca khó:
  - CD: CD8 radial (Hình 8.3/8.4 — KHÔNG bị drop), CD6 grid (giữ nguyên), sidebar-cạnh-figure (sidebar bị drop đúng), composite a/b/c/d, trang 97-DPI.
  - CTST: band/full-width caption (builder riêng vẫn chạy sau khi routing đúng).
  - KNTT: pill caption + builder riêng.
  - **Pass:** không figure over-crop text/box; không sidebar bị box-thành-figure; caption gắn đúng figure. **Đối chiếu diff** với output `image_processor` hiện tại → chứng minh không regression (bridge chỉ được phép **bớt** dương-tính-giả, không được **mất** figure thật).
- **Phản biện code:** sau mỗi task, một lượt tìm bug ẩn — lệch toạ độ (150 vs 220 DPI), đảo RGB/BGR, ngưỡng containment sai chiều, drop nhầm radial, cache không bump, cycle import, `make_image_processor` thiếu field so với base.

## 9. Rủi ro & giảm thiểu

| Rủi ro | Giảm thiểu |
|---|---|
| **Radial CD8 bị box-detector nhận nhầm là box → drop nhầm figure** (D-15) | Chỉ-drop + ngưỡng containment cao (0.80) + KHÔNG clip; **QA target #1** trên CD8 Hình 8.3/8.4; nếu vẫn drop nhầm, nâng ngưỡng hoặc thêm guard "figure có anchor caption thì không bao giờ drop" |
| Box params tune ở 220 DPI, detector chạy 150 DPI | QA ở 150; tham số hoá `close_kernel` theo DPI nếu lệch; chỉ dùng box để **loại trừ**, không để bound |
| Routing per-variant lần đầu áp ở batch → CTST/KNTT đổi hành vi | Đúng ý (fix §3.3); QA overlay CTST/KNTT xác nhận builder riêng kích hoạt đúng, không hồi quy so với QA tool (vốn đã dùng make_image_processor) |
| Cache version không bump → trang cũ bị skip | Bump `IMAGE_EXTRACTION_VERSION`; runbook nhắc xoá/để checkpoint versioned tự lo |
| Cycle import image_processor↔layout | Local import trong method; bridge không import image_processor |

## 10. Lộ trình task (TDD, ~6 task — chi tiết ở plan riêng)

1. **Config + version bump:** `FIGURE_IN_BOX_DROP_RATIO=0.80`, `IMAGE_EXTRACTION_VERSION` default `v16_layout_reconcile`. Test default.
2. **`figure_bridge.reconcile_with_layout` + `_containment`:** unit tổng hợp (drop/giữ/no-box/màu). `segment_page` monkeypatched.
3. **`to_layout_regions` + cắm vào `extract_images_from_pdf`** (local import, `self.variant`). Test map + smoke wiring.
4. **Entrypoint `make_image_processor` per book** trong `run_etl_image_only`/`run_etl`. Test helper chọn processor đúng lớp theo tên file.
5. **`đ`-fold fix** trong kênh lexical ảnh (`image_vectorstore.py`). Test fold.
6. **QA overlay + validate CD/CTST/KNTT + docs:** mở rộng test_image_extraction_full vẽ reconcile; chạy tay ~5 trang/variant; cập nhật CLAUDE.md, decision log (D-21…), memory. Focused suite pass.

## 11. Câu hỏi mở (không chặn implement)

- Ngưỡng `FIGURE_IN_BOX_DROP_RATIO` cuối cùng chốt sau QA CD (0.80 là điểm khởi đầu bảo thủ).
- Có cần guard "figure gắn anchor caption thì miễn-drop" hay không — quyết theo QA radial. Nếu cần, thêm ở task 2 mà không đổi interface.
- `close_kernel` theo-DPI: chỉ tham số hoá nếu QA 150-DPI cho thấy box detection lệch.
