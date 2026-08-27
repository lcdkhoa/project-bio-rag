# Prompt bàn giao — Hybrid Tesseract + MinerU cho vùng công thức Hoá/Lý

**Ngày viết:** 2026-08-27. **Người chốt:** người dùng, chấp nhận du di deadline (đề
cương đã ký `document/goal.docx`) để ETL lại 12 quyển nếu cần.

## 0. Đọc trước, theo thứ tự

1. `CLAUDE.md` RULE #0 + Philosophy (7 nguyên tắc) — **bắt buộc**, đặc biệt nguyên
   tắc 1 (không bịa), 3 (đo đừng đoán), 5 (fail loudly).
2. `document/decision_log.html` — lọc theo tag hoặc tìm `D-56`, `D-63`, `D-92`,
   `D-96`, `D-99`, `D-101`, `D-102`, `D-104`, `D-108`, `D-141`, `D-142`, `D-143`.
   D-108 là quyết định NỀN của phiên này: bake-off đã KẾT LUẬN xong, không lặp lại.
3. `document/review/ocr_gold/` — gold set 97 ô / 15 trang đã được người duyệt tay
   (`phieu_nguoi.json`, KHÔNG được sửa file này).
4. `src/test/ocr_bakeoff.py` — cách chấm CT (công thức) / DẤU (lỗi dấu) / BẢNG, và
   hai bẫy đã vá (D-96 engine thiếu ô, D-108 LaTeX làm hai cột đều bị đánh giá thấp).

## 1. Vì sao (đừng suy diễn lại — đã có câu trả lời)

Người dùng đọc báo cáo và cho rằng OCR bằng Tesseract thuần làm mất chỉ số dưới của
công thức Hoá (`O₂`→`0,`, `CO₂`→`CO,`) là **không chấp nhận được**, vì sai công thức
là sai kiến thức dạy cho học sinh (nguyên tắc 1). Bake-off (D-108) đã đo: MinerU2.5
đọc công thức tốt hơn Tesseract **9,2 lần** (CT 0,441 vs 0,048) nhưng lỗi dấu tiếng
Việt tệ hơn (DẤU 0,037 vs 0,016) — nên **không thể thay Tesseract toàn trang**, luật
chốt D-108 đã loại phương án đó. Hướng còn lại, CHƯA làm, được người dùng CHỐT bắt
đầu hôm nay: **dùng MinerU CHỈ cho vùng công thức, giữ Tesseract cho văn xuôi.**

## 2. Đang có gì, thiếu gì (đo bằng grep + đọc code, không đoán)

- `src/etl/layout/regions.py::RegionType` hiện có `BODY / FIGURE / PAGE_ARTIFACT /
  SIDEBAR / ...` — **không có loại "formula"**. Không có detector vùng công thức nào
  trong pipeline ETL.
- ~~`MinerUClient` chỉ tồn tại trong notebook Colab~~ — **SAI, sửa ở D-144**: nó đã
  nằm trong repo ở `scripts/colab_run_ocr_engines.py::_mineru25()` (D-104), chạy
  trên Colab bằng `python scripts/colab_run_ocr_engines.py --engine mineru25 ...`,
  không phải trong `src/etl/`. Vẫn cần PORT logic gọi này vào `src/etl/layout/`
  cho Bước 2/3 (ETL thật, không phải bake-off), nhưng KHÔNG cần "tìm lại notebook"
  — API đã có sẵn, đã verify chạy thật (đọc đúng `CO₂`/`O₂`, D-104/D-108).
- `src/etl/layout/text_extract.py` là nơi Tesseract chạy theo dòng/box
  (`SINGLE_LINE_MAX_H`, psm 6/7). Đây là điểm cần chèn logic mới.
- ~~Gold set công thức duy nhất đang có là 97 ô / 15 trang CHỈ CỦA KNTT~~ — **SAI,
  sửa ở D-144**: mở `src/test/ocr_bakeoff_pages.json` ra đếm thì 15 trang đã cân đối
  **5/5/5 theo NXB** (KNTT/CTST/CD) từ lúc chọn (2026-08-25). Câu trên là suy diễn
  chưa kiểm, không phải phép đo — đã tồn tại đủ lâu để lọt vào cả CLAUDE.md, nay đã
  sửa ở đó (bảng tiến độ + gạch đầu dòng D-56). Đoạn khuyến nghị thu hẹp G2 thành
  gold set công thức theo NXB trong CLAUDE.md coi như ĐÃ CÓ (gold set này vốn đã đủ
  3 NXB), không cần làm thêm.

## 3. Việc phải làm — 3 bước, KHÔNG chạy ETL 12 quyển cho tới hết bước 1

### Bước 1 — Xây + đo gate phát hiện vùng nghi công thức (RẺ, làm trước) — **XONG (D-144)**

Đã xây `src/etl/layout/formula_gate.py::is_formula_suspect()` + module dùng chung
`src/etl/layout/formula_signals.py` (tách từ `ocr_bakeoff.py` để một nguồn sự thật
duy nhất với số CT đã khoá ở D-108). Đo bằng
`python -m src.test.measure_formula_gate`, quét ngưỡng 0,00→1,04 bước 0,02 (kiểu
D-57) trên gold set **89 ô / 3 NXB** (97 ô trừ 8 ô `bang`) — **KHÔNG chỉ KNTT như
dòng cũ ở mục 2 tưởng, đã sửa**.

Kết quả quét: recall đạt tối đa (1,000) NGAY ở ngưỡng "có ≥1 khớp", ngưỡng cao hơn
chỉ làm recall rơi mà precision không đổi đáng kể → **gate chốt là quy tắc NHỊ PHÂN**
(OR của `CONG_THUC_HONG`/`CO_DAU_BANG`, hai tín hiệu D-56/D-73 đã có sẵn), không phải
một tham số cần tinh chỉnh. Số đo: **precision 0,8654 (45 TP / 7 FP) · recall 1,0000
(0 FN)**. Mở tay cả 7/7 ca FP (CẤM #11): 6/7 là giới hạn của cách đo (ground truth
`formula_tokens` bỏ sót công thức có ngoặc/ký hiệu Unicode lạ, một đáp án người
không hợp lệ, một ca dòng Tesseract dài hơn crop cho người xem), chỉ 1/7 là mơ hồ
THẬT không phân biệt được bằng một dòng (`Mg, Al, Zn, Fe` — liệt kê nguyên tố đọc
giống chỉ số dưới bị phá). Theo NXB: KNTT prec 1,000, CD 0,929, CTST 0,727 — recall
1,000 đều cả 3. Chi tiết đầy đủ: `document/decision_log.html` D-144.

Test khoá số liệu: `tests/layout/test_formula_gate.py`,
`tests/layout/test_formula_signals.py`, `tests/test_measure_formula_gate.py` (17
test mới, `pytest tests/ -q` → 732 pass / 3 skip).

**Việc mở rộng gold set theo NXB coi như ĐÃ CÓ** — gold set này vốn đã cân đối
5/5/5 theo NXB từ lúc chọn (2026-08-25), không cần làm thêm.

### Bước 2 — Gọi MinerU CHỈ trên crop vùng công thức, qua Colab GPU

Không có CUDA trên máy dev (`torch 2.11.0+cpu`) — đây LÀ việc của người dùng chạy
trên Colab, không phải việc chạy được trong phiên làm việc CLI này (giống ràng buộc
đã ghi ở `[[ocr_bakeoff]]`/`[[colab_runbook_and_env]]`).

~~Lấy lại API `MinerUClient.two_step_extract()` + `json2md()` đã verify ở D-104~~ —
**SAI, sửa ở D-144**: D-104 đo được `two_step_extract()` trả RỖNG 3/3 ô trên crop một
dòng (bước 1 của nó phân tích bố cục CẢ TRANG, một crop một dòng không có bố cục nào
để tìm). API đúng, đã verify chạy thật, là
`MinerUClient(backend="transformers", model=model, processor=proc).content_extract(image, type="text"|"table")`
— xem `scripts/colab_run_ocr_engines.py::_mineru25()` (D-104), file này ĐÃ TỒN TẠI
trong repo, không chỉ có trong notebook như câu cũ ở đây tưởng. Ghim
`transformers>=4.49,<5` trên Colab (D-101, tránh bẫy `lm_head.weight MISSING`).

### Bước 3 — Merge có kiểm soát vào chunk, không đụng phần còn lại

Text MinerU trả về (có thể là LaTeX, D-108 đã ghi nhận) thay thế ĐÚNG vị trí dòng
công thức trong chunk đã có. Khi MinerU không đọc được token công thức hợp lệ: **giữ
nguyên bản Tesseract + gắn `needs_review`**, không bịa (nguyên tắc 1, 5). Đo
before/after trên cùng gold set trước khi coi là xong.

## 4. Cấm (nhắc lại từ CLAUDE.md, đọc đủ 7 nguyên tắc để hiểu vì sao)

1. Không tự đoán ngưỡng gate — phải quét + đo trên gold set.
2. Không rewrite text bằng suy đoán khi MinerU đọc hỏng — chỉ merge khi có bằng
   chứng đọc đúng, còn lại giữ Tesseract + `needs_review`.
3. Không chạy ETL 12 quyển trước khi bước 1 có số đo xong.
4. Không gộp bump `TEXT_EXTRACTION_VERSION` nhiều lần — gộp CÙNG LƯỢT với các tham
   số M2 khác chưa hiệu chỉnh (`SINGLE_LINE_MAX_H` cho CD cao ~136px,
   `LAYOUT_BOX_MIN_SATURATION` per-book — xem bảng M0 fingerprint trong CLAUDE.md).
5. Nếu chạm tới ETL (chắc chắn sẽ chạm) → phải vá `document/colab_runtime_etl.ipynb`
   **trong cùng lượt** — đây là runbook người dùng THỰC SỰ chạy.
6. Kết thúc mỗi quyết định/phép đo: ghi `document/decision_log.html` (chạy
   `pytest tests/test_decision_log.py` sau khi sửa), cập nhật `CLAUDE.md`, cập nhật
   memory, cập nhật spec — RỒI MỚI commit (message thuần, không `Co-Authored-By`).

## 5. Trạng thái file khi bàn giao lượt 1 (2026-08-27 sáng, khớp `git status --short`)

```
 M CLAUDE.md
 M document/decision_log.html
 M src/rag/image_vectorstore.py
?? tests/rag/test_image_fish_false_friends.py
```

Ba thay đổi trên **không liên quan đến việc này** — đó là fix lỗi truy vấn ảnh "cho
tôi hình con cá" (D-141..D-143). Đã được commit (`78c501d2`) trước khi Bước 1 bắt
đầu, nên không lẫn vào commit của việc công thức.

## 6. Bàn giao tiếp (2026-08-27 chiều, sau D-144) — Bước 1 XONG, Bước 2/3 còn lại

**Đã làm, đã commit:**
- `src/etl/layout/formula_signals.py`, `src/etl/layout/formula_gate.py` (gate mới)
- `ocr_bakeoff.py` sửa để import tín hiệu dùng chung thay vì định nghĩa lại
- `src/test/measure_formula_gate.py` (script đo, tái lập số D-144)
- `tests/layout/test_formula_gate.py`, `tests/layout/test_formula_signals.py`,
  `tests/test_measure_formula_gate.py`
- `document/decision_log.html` D-144, `CLAUDE.md` (sửa nhận định sai "gold set
  KNTT-only", cập nhật bảng tiến độ MT1)

**Việc tiếp theo (session mới, CẦN Colab GPU — không chạy được trong CLI này):**
1. Port logic gọi MinerU từ `scripts/colab_run_ocr_engines.py::_mineru25()` vào
   `src/etl/layout/` — gọi qua `MinerUClient.content_extract(image, type=...)`,
   KHÔNG phải `two_step_extract()` (xem mục 3, Bước 2 đã sửa).
2. Cần line-level bbox để crop đúng vùng nghi công thức: `text_extract.py::_ocr()`
   hiện chỉ gọi `pytesseract.image_to_string()` (trả một khối chữ, không có bbox
   từng dòng) — phải đổi sang `image_to_data()` (như `ocr_bakeoff._ocr_words` đã
   làm) rồi mới áp `is_formula_suspect()` theo TỪNG DÒNG và cắt crop từ bbox dòng
   đó. Đây là thay đổi cấu trúc, không phải chỉ thêm gọi hàm.
3. `RegionType` (`src/etl/layout/regions.py`) chưa có biến thể "formula" — cân
   nhắc có cần không, hay chỉ cần gắn cờ lên `TextUnit` hiện có.
4. Bước 3 (merge): so token MinerU đọc được với `formula_tokens()` (đã có, dùng
   chung `formula_signals.py`) — chỉ thay dòng khi MinerU trả về ≥1 token hợp lệ,
   còn lại giữ nguyên Tesseract + `needs_review` (CẤM #2).
5. Nếu bất kỳ bước nào chạm ETL thật → vá `document/colab_runtime_etl.ipynb` CÙNG
   LƯỢT (CẤM #5), và gộp `TEXT_EXTRACTION_VERSION` bump với các tham số M2 khác
   chưa hiệu chỉnh (CẤM #4).

**Môi trường:** nếu gặp `ImportError: tokenizers>=0.20,<0.21 is required ... found
tokenizers==X`, xem `[[dev_env_tokenizers_conflict]]` trong memory — đã có cách vá.
