# Thiết kế Bước 2+3 — hybrid Tesseract + MinerU cho công thức Hoá/Lý

**Ngày viết:** 2026-08-27. Tiếp nối `document/specs/2026-08-27-formula-ocr-hybrid-prompt.md`
(Bước 1, D-144 — gate `is_formula_suspect` đã XONG và đo được prec 0,8654/rec 1,0000
trên 89 ô/3 NXB). Bản này thiết kế **Bước 2** (gọi MinerU thật) và **Bước 3** (merge
vào chunk), sau một vòng phản biện đã sửa bản đầu (xem "Lịch sử sửa" cuối file).

## 1. Nguyên tắc thiết kế cốt lõi: KHÔNG đụng đường OCR chính

Bản đầu định đổi `_ocr()` từ `pytesseract.image_to_string()` sang
`image_to_data()` + gom dòng cho **mọi region, mọi trang, cả 12 quyển** — quá tay,
vì mục tiêu thật chỉ cần bbox của một số dòng HIẾM bị gate nghi. Bản này giữ
nguyên `image_to_string()` làm đường chính (0 rủi ro hồi quy trên >99% region
không dính công thức); `image_to_data()` chỉ được gọi **thêm, một lần, chỉ cho
region vừa bị gate bắt được lỗ hổng ở text chính** — một side-computation hiếm khi
chạy, không phải đường nóng.

## 2. Luồng xử lý (trong `extract_text_units`, `src/etl/layout/text_extract.py`)

Cho mỗi region (trừ `FIGURE`/`PAGE_ARTIFACT`, như hiện tại):

1. `text = _ocr(crop)` — **KHÔNG ĐỔI**, vẫn `image_to_string()` với đúng `_psm_for(crop)`.
2. Nếu `FORMULA_HYBRID_ENABLED` và `is_formula_suspect(text)` tìm thấy lỗ hổng ở
   BẤT KỲ đâu trong `text`:
   a. Gọi `pytesseract.image_to_data(crop, config=f"--psm {_psm_for(crop)}")` —
      **BẮT BUỘC dùng cùng `--psm`** như bước 1, để hai lượt đọc cùng một crop
      không lệch nhau vì khác cấu hình.
   b. Gom thành dòng bằng `group_lines()` (chuyển từ `ocr_bakeoff.py` sang
      `src/etl/layout/ocr_lines.py` — production, dùng chung).
   c. Với từng dòng: nếu `is_formula_suspect(dòng)` cũng đúng (tái lập độc lập,
      không suy từ vị trí ký tự của bước 1 — hai lượt OCR không cùng hệ toạ độ
      ký tự) → dòng này là ứng viên gửi MinerU.
   d. **Không dòng nào tái lập được lỗ hổng đã thấy ở bước 1** (VD hai cột dính
      dòng, D-108 nhóm case tương tự): **fail-safe** — giữ nguyên `text`, gắn
      `formula_hybrid_status = "gate_hit_no_line_located"`. KHÔNG được coi là
      "không có gì để làm" rồi bỏ qua lặng lẽ (nguyên tắc 5).
3. Với mỗi dòng ứng viên: crop bbox dòng (pad 8px, như bake-off) → gọi
   `FormulaMinerUClient.read(crop_dong, kind="text")` → `merge_formula_line()`.
4. **Ghép dòng đã sửa trở lại vào `text` của cả region — hai hệ toạ độ khác
   nhau, phải làm cẩn thận (lỗ hổng phát hiện khi tự phản biện bản nháp đầu của
   chính spec này):**
   `merge_formula_line` trả về **TOÀN BỘ dòng đã sửa** (không chỉ span), vì dòng
   này đến từ `image_to_data` (lượt OCR riêng), còn `text` của region đến từ
   `image_to_string` (lượt OCR khác) — hai chuỗi không chung offset ký tự. Ghép
   bằng cách tìm **dòng GỐC (chưa sửa) như một chuỗi con của `text`**:
   - Đếm số lần dòng gốc xuất hiện trong `text`. **Đúng 1 lần** → thay thế đúng
     chỗ đó bằng dòng đã sửa. **0 lần hoặc ≥2 lần** → fail-safe, giữ nguyên
     `text`, gắn `formula_hybrid_status = "line_not_located_in_region_text"`
     (không đoán thay chỗ nào khi mơ hồ — nguyên tắc 1).
   - So khớp chuỗi con MỘT DÒNG NGUYÊN VẸN (10–30 từ) khó trùng ngẫu nhiên hơn
     nhiều so với so khớp một token ngắn (`"CO,"`) — đây là lý do đổi đơn vị so
     khớp từ "span" sang "dòng nguyên" so với bản nháp đầu của spec này.
   - Nhiều dòng ứng viên trong cùng một region: áp dụng **tuần tự**, mỗi lần
     tìm lại vị trí trong `text` đã cập nhật của bước trước (không tính offset
     trước, vì mỗi lần thay là thay CẢ DÒNG nên không có vấn đề offset trôi như
     kiểu thay token ngắn).
5. Ghi `formula_hybrid_status` vào metadata của `TextUnit` (field MỚI, tách khỏi
   `review_flags` — xem §5).

## 3. `formula_merge.py` — hàm thuần, không cần model để test

```python
def merge_formula_line(tesseract_line: str, mineru_text: str) -> MergeOutcome:
    ...
```

Thuật toán:
1. Tìm "lỗ hổng" = tất cả match của `CONG_THUC_HONG` (nhóm hoá) và `CO_DAU_BANG`
   (nhóm lý) trong `tesseract_line`, **giữ nguyên `match.span()`** (offset chính
   xác trong CHÍNH dòng này, không phải trong `text` của cả region).
2. Tìm token MinerU tương ứng trong `mineru_text`: nhóm hoá qua `_TOKEN_HOA`
   (loại các token đã nằm trong một `_TOKEN_LY`, như `formula_tokens` đã làm),
   nhóm lý qua `_TOKEN_LY` — theo thứ tự xuất hiện trong `mineru_text`.
3. Ghép theo cặp **CÙNG NHÓM, cùng thứ tự trái→phải**. Chỉ ghép khi
   `len(lỗ hổng nhóm đó) == len(token nhóm đó)` — khớp chặt 1:1. Lệch số lượng
   (dù chỉ 1) → **KHÔNG ghép nhóm đó**, giữ nguyên các lỗ hổng của nhóm đó.
4. Trả về `MergeOutcome(text, status, spans_applied)`:
   - `status = "applied"` nếu ≥1 lỗ hổng được ghép.
   - `status = "unmatched_count"` nếu có lỗ hổng nhưng không nhóm nào ghép được
     (số lượng lệch ở cả hai nhóm, hoặc MinerU trả rỗng).
   - `status = "not_suspect"` nếu dòng không có lỗ hổng (không gọi tới đây thật
     ra, nhưng hàm vẫn xử lý đúng để test độc lập được).
5. **Thay thế theo offset, không theo `str.replace()`**: dựng text mới bằng cách
   cắt-dán quanh từng `span` đã ghép, xử lý spans theo thứ tự **giảm dần vị trí
   bắt đầu** — offset của các span chưa xử lý không bị ảnh hưởng bởi độ dài khác
   nhau của token thay thế.

Test đầy đủ bằng ví dụ tay, không cần model:
- `"hấp thụ khí 0, và thải ra khí (0,"` + MinerU
  `"hấp thụ khí CO₂ và thải ra khí O₂"` → ghép đúng 2 vị trí, phần tiếng Việt
  giữ nguyên bản Tesseract.
- Lệch số lượng: 2 lỗ hổng hoá nhưng MinerU chỉ có 1 token hoá → giữ nguyên cả
  dòng, `status = "unmatched_count"`.
- Chuỗi giống nhau XUẤT HIỆN 2 LẦN trong dòng (`"CO, ... CO,"`, hai lỗ hổng cùng
  literal text) nhưng ứng với 2 token MinerU KHÁC NHAU (`"CO₂ ... CH₄"`) — test
  này khoá lại rằng thay thế theo OFFSET, không theo `str.replace()` (bug đã bắt
  ở vòng phản biện): nếu code sai sẽ thay CẢ HAI lỗ hổng bằng CÙNG MỘT token.

## 4. `FormulaMinerUClient` — `src/etl/layout/formula_ocr.py`

- Lazy-import `mineru_vl_utils`/`transformers` (không phá `import src.etl` trên
  máy dev CPU không có các lib này).
- **Singleton, load model MỘT LẦN cho cả tiến trình** (kiểu `get_reranker()` ở
  `src/rag/reranker.py`) — bản thiết kế đầu KHÔNG nói rõ điều này, load lại mỗi
  lần gọi sẽ tốn ~35s/lần (D-104) × hàng trăm lần gọi, phá hỏng mọi ước lượng
  thời gian.
- `read(crop_bgr, kind="text") -> str` gọi
  `client.content_extract(Image, type="text"|"table")` (API ĐÚNG theo D-104,
  không phải `two_step_extract`).
- **Injectable cho test**: `extract_text_units` nhận tham số
  `formula_client=None` (mặc định lazy-load `FormulaMinerUClient` thật khi
  `FORMULA_HYBRID_ENABLED`), để test truyền vào client giả (hàm Python thuần) mà
  không cần GPU/model.

## 5. Metadata — field riêng, không nhét vào `review_flags`

`review_flags` hiện chỉ mang token đáng ngờ từ `diacritic_review_flags()` và đã
đo được bật ở **69,3% chunk toàn kho** (CLAUDE.md: "MẤT TÁC DỤNG"). Nhét thêm cờ
formula vào đó làm tín hiệu đã loãng càng loãng hơn. Thêm field MỚI:

```python
@dataclass
class TextUnit:
    ...
    formula_hybrid_status: str | None = None  # "applied" | "unmatched_count" |
                                               # "gate_hit_no_line_located" | None
```

`chunker.py::chunk_units` phải truyền field này vào metadata chunk (như đã làm
với `region_type`/`needs_review`) — **thiếu sót của bản thiết kế đầu**, chưa xét
`chunker.py` tới.

## 6. Hai tham số M2 gộp cùng version bump (theo CẤM #4)

### 6a. `LAYOUT_BOX_MIN_SATURATION` per-book

`segmenter._params_for(book_id)` đọc `database/fingerprints/{book_id}.json →
box_palette.sat_percentiles.p10` làm `min_sat`. **Sàn tối thiểu KHÔNG được đoán
(bản đầu đề "ví dụ 20" — bịa)**: quét sàn ứng viên (ví dụ 0/10/15/20/25) bằng
`qa_layout.py --pages ... --report` trên vài trang thật mỗi NXB, đo số hộp màu
tìm được so với đếm bằng mắt trên trang chuẩn đã có (`page_010` KNTT + một trang
tương đương CD/CTST), chọn sàn theo số đo. Không có fingerprint cho một quyển
(không xảy ra với 12 quyển hiện tại, nhưng vẫn phải xử lý cho đường PDF upload)
→ **WARN rõ ràng** (không im lặng) rồi dùng lại hằng số 45 cũ.

`book_id` được truyền xuống từ `loader.py::load_page` (đã có sẵn `source.name`
→ `book_id_from_source_name(source.name)`), qua `segment_page(img, variant,
book_id)`.

### 6b. `SINGLE_LINE_MAX_H` theo chiều rộng trang

**Không giả định tuyến tính `60 × width/1094` đúng** (bản đầu suy từ một con số
"~136px" mà chính CLAUDE.md ghi là CHƯA ĐO). Đo thật: chạy `image_to_data` trên
vài trang CD/CTST/KNTT thật (`datasources/` có sẵn trên máy dev), gom dòng bằng
`group_lines`, lấy phân bố chiều cao dòng THÂN BÀI (loại dòng quá ngắn/quá dài
bất thường), tính percentile per-book. Nếu tỉ lệ theo chiều rộng khớp số đo (as
`toc.geom_for_width`/`pill.bounds_for_width` đã làm) thì dùng công thức tỉ lệ;
nếu không khớp, dùng bảng hằng số per-book đo trực tiếp — quyết định SAU KHI có
số, không trước.

## 7. `TEXT_EXTRACTION_VERSION` — bump một lần

Giá trị mới (ví dụ `v3_formula_hybrid`) gộp CẢ BA thay đổi (hybrid formula +
`SINGLE_LINE_MAX_H` mới + `LAYOUT_BOX_MIN_SATURATION` per-book) — đúng CẤM #4,
chỉ một lượt OCR lại toàn bộ.

## 8. Ước lượng chi phí TRƯỚC khi chạy Colab thật

Không đoán số lần gọi MinerU. Dùng số ĐÃ CÓ (D-73, không cần OCR lại): tổng
"hỏng:đúng" trên chỉ số dưới = CD 256:3, CTST 377:3, KNTT 408:4 (tổng ~1041 lần
xuất hiện trên toàn kho). Viết một script đếm nhanh (đọc lại `biology_text` hiện
có, áp `is_formula_suspect` theo DÒNG sau khi tách bằng `\n`) để ra số **DÒNG**
ước tính cần gọi MinerU (thấp hơn số lần xuất hiện, vì nhiều lỗ hổng nằm chung
một dòng) — chạy được ngay trên máy dev, không cần Colab. Từ đó ước ETA thật:
số dòng × ~2,6 s/dòng (D-108, đo bằng `content_extract`).

## 9. Colab: datasource ở Drive, DB ở session, tải về SAU MỖI QUYỂN

**Rủi ro vận hành đã bỏ sót ở bản đầu:** DB session-local mất checkpoint-resume
khi Colab rớt phiên (khác bản Drive hiện tại "bền qua các phiên"). Job nhiều giờ
trên 2399 trang mà rớt giữa chừng sẽ mất sạch nếu tải về chỉ một lần ở cuối.

**Giảm thiểu:** chạy **từng quyển một** bằng `--book` (đã có, D-84), zip +
`google.colab.files.download()` **sau mỗi quyển** (không phải sau cả 12 quyển).
Rớt phiên giữa chừng chỉ mất tối đa 1 quyển đang xử lý dở, không mất toàn bộ.

Thay đổi cụ thể trong `document/colab_runtime_etl.ipynb` (phải vá — CẤM #5):
- Cell path env: `RAG_DATABASE_DIR` → `/content/database` (session-local, KHÔNG
  Drive). `RAG_DATA_DIR` giữ nguyên trỏ Drive. `RAG_MANIFEST_DIR`/
  `RAG_FINGERPRINT_DIR` giữ nguyên (theo repo).
- Thêm cell cài `mineru_vl_utils`, ghim `transformers>=4.49,<5` (D-101), set
  `FORMULA_HYBRID_ENABLED=true`, `TEXT_EXTRACTION_VERSION=v3_formula_hybrid`.
- Thêm cell ước lượng chi phí (§8) chạy TRƯỚC vòng lặp ETL thật.
- Vòng lặp: với mỗi quyển trong 12 quyển → `main.py --text-only --book <quyển>`
  → zip `/content/database` (CỘNG DỒN — chứa cả các quyển trước, vì Chroma là
  một SQLite file, không tách được theo quyển sau khi ghi) → `files.download`.
  Zip sau lớn hơn zip trước là bình thường; chỉ cần GIỮ bản tải cuối cùng, các
  bản giữa chừng chỉ để phòng rớt phiên.

## 10. Kiểm thử (không cần Colab)

- `tests/layout/test_formula_merge.py` — thuần, các ca ở §3, kể cả ca "cùng
  chuỗi lặp lại nhưng khác token đúng" (bắt bug offset).
- Test riêng cho bước ghép dòng-vào-region (§2.4): dòng gốc xuất hiện đúng 1 lần
  trong `text` → thay đúng chỗ; dòng gốc **0 lần** (hai lượt OCR đọc lệch nhau
  nhiều) → fail-safe + `line_not_located_in_region_text`; dòng gốc **≥2 lần**
  (dòng lặp lại, ví dụ tiêu đề lặp) → fail-safe, KHÔNG đoán thay chỗ nào.
- `tests/layout/test_formula_ocr.py` — `FormulaMinerUClient` với client giả
  (không load model thật); test singleton chỉ load một lần.
- `tests/layout/test_text_extract_formula_hybrid.py` — tích hợp
  `extract_text_units` với `formula_client` giả trên **ảnh THẬT** (trang 121
  sách 7 KNTT, ca `CO₂`/`O₂` đã biết ở D-56/D-63) để bắt lỗi off-by-one giữa
  bbox dòng và bbox region trước khi chạm GPU thật.
- Test "region không có lỗ hổng thì KHÔNG gọi `image_to_data`" — đo bằng
  mock/counter, khoá lại nguyên tắc §1 (không đụng đường chính khi không cần).
- Test fail-safe "gate bắt ở text chính nhưng không dòng nào tái lập được" (giả
  lập bằng text tổng hợp có lỗ hổng bị `image_to_data` giả trả về gom dòng khác
  đi) → `formula_hybrid_status = "gate_hit_no_line_located"`, text KHÔNG đổi.
- `tests/layout/test_segmenter_min_sat.py` — per-book min_sat đọc từ fingerprint
  giả, fallback WARN khi thiếu fingerprint.
- Chạy lại `qa_layout.py --report` trên vài trang thật mỗi NXB SAU khi đổi
  `min_sat`/`SINGLE_LINE_MAX_H` — so trước/sau, không chỉ tin test đơn vị.

## 11. Ngoài phạm vi (không làm)

- Không thêm `RegionType` mới.
- Không gửi cả REGION (nhiều dòng) cho MinerU — chỉ dòng đơn, đúng granularity
  đã đo ở D-104/D-108.
- Không đụng ETL ảnh (`--image-only`).
- Không tự chạy ETL 12 quyển thật trong phiên CLI này (không có GPU).

## Lịch sử sửa

Bản đầu (không lưu thành file) bị phản biện và sửa 5 nhóm vấn đề: (A) đổi đường
OCR chính cho mọi region thay vì chỉ side-call khi cần; (B) bug `str.replace()`
toàn cục thay vì offset, thiếu ràng buộc cùng `--psm` giữa hai lượt OCR, thiếu
fail-safe khi không dòng nào tái lập được lỗ hổng; (C) hằng số bịa (sàn sat "20",
công thức tuyến tính SINGLE_LINE_MAX_H chưa đo); (D) rủi ro mất checkpoint khi DB
ở session Colab; (E) thiếu singleton model, thiếu ước lượng chi phí trước khi
chạy, thiếu `chunker.py`, nhét metadata vào `review_flags` đã loãng. Bản này là
kết quả sau khi sửa cả 5 nhóm.
