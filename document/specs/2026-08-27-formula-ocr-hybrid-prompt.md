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
- `MinerUClient` / `two_step_extract()` / `json2md()` (D-104) chỉ tồn tại trong
  **notebook Colab dùng cho bake-off**, không phải trong `src/etl/`. Cần tìm lại
  notebook đó (hỏi người dùng đường dẫn nếu không thấy trong repo) để lấy đúng cách
  gọi API đã verify hoạt động.
- `src/etl/layout/text_extract.py` là nơi Tesseract chạy theo dòng/box
  (`SINGLE_LINE_MAX_H`, psm 6/7). Đây là điểm cần chèn logic mới.
- Gold set công thức duy nhất đang có là 97 ô / 15 trang **CHỈ CỦA KNTT** (độ phân
  giải THẤP NHẤT trong 3 NXB, D-65) — xem mục "G2 dùng để làm gì" trong CLAUDE.md,
  đoạn khuyến nghị thu hẹp G2 thành gold set công thức theo NXB VẪN CHƯA LÀM.

## 3. Việc phải làm — 3 bước, KHÔNG chạy ETL 12 quyển cho tới hết bước 1

### Bước 1 — Xây + đo gate phát hiện vùng nghi công thức (RẺ, làm trước)

Không cần detector CV mới phức tạp: dùng chính tín hiệu OCR-hỏng đã đo ở D-56 làm
gợi ý — dòng Tesseract ra `0,`/`(0,`/mẫu chữ+số dính liền kiểu `H,O`/`CO,`, hoặc mật
độ ký hiệu hoá học/vật lý cao trong ngữ cảnh xung quanh (`=`, số mũ, đơn vị). Đo
ngưỡng trên gold set 97 ô — **KHÔNG đoán ngưỡng**, quét như D-57 đã làm với
`COVERAGE_MIN` (sweep + đo agreement). Tiêu chí nghiệm thu bước này: precision/recall
của gate đo được trên 97 ô, ghi vào decision log kèm số liệu quét.

Việc mở rộng gold set theo NXB (CLAUDE.md đã khuyến nghị, chưa làm) nên cân nhắc ở
đây: gate đo trên gold set KNTT-only có nguy cơ không tổng quát cho CD/CTST (độ phân
giải cao hơn — xem mục "KNTT is the LOWEST-resolution set" ở đầu CLAUDE.md).

### Bước 2 — Gọi MinerU CHỈ trên crop vùng công thức, qua Colab GPU

Không có CUDA trên máy dev (`torch 2.11.0+cpu`) — đây LÀ việc của người dùng chạy
trên Colab, không phải việc chạy được trong phiên làm việc CLI này (giống ràng buộc
đã ghi ở `[[ocr_bakeoff]]`/`[[colab_runbook_and_env]]`). Lấy lại API
`MinerUClient.two_step_extract()` + `json2md()` đã verify ở D-104; ghim
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

## 5. Trạng thái file khi bàn giao (2026-08-27, khớp `git status --short`)

```
 M CLAUDE.md
 M document/decision_log.html
 M src/rag/image_vectorstore.py
?? tests/rag/test_image_fish_false_friends.py
```

Ba thay đổi trên **không liên quan đến việc này** — đó là fix lỗi truy vấn ảnh "cho
tôi hình con cá" (D-141..D-143), đã xong và đã kiểm bằng `pytest tests/ -q` → 715
pass / 3 skip. Session mới nên `git add` + commit chỗ đó riêng (hoặc hỏi người dùng)
trước khi bắt đầu việc công thức, để không lẫn hai việc trong một commit.

**Môi trường:** nếu gặp `ImportError: tokenizers>=0.20,<0.21 is required ... found
tokenizers==X`, xem `[[dev_env_tokenizers_conflict]]` trong memory — đã có cách vá.
