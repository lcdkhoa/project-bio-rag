# M3 — ETL hình cho 8 quyển CD/CTST + bộ test 240 câu + báo cáo

Ngày: 2026-08-25. Chốt với người dùng trong cùng phiên (ba lựa chọn ở §0).
Nguồn yêu cầu: `document/goal.docx` (RULE #0) — MT1 phần hình, MT4 đối chiếu đa
phương thức. Format báo cáo: `report/main_chuyende_totnghiep.pdf` (chuyên đề cũ).

## 0. Ba lựa chọn người dùng đã chốt

1. **Cổng G4 cho CD/CTST = bản RÚT GỌN + QA mắt.** Không chờ M1 spine.
   Bỏ nửa kiểm "A = Bài của trang" (cần spine liền mạch, CD/CTST chưa có),
   giữ nửa "B liên tục 1..max" + độ phủ + cờ crop nghi cắt lấn, rồi mở
   20 trang/NXB xem bằng mắt. Báo cáo PHẢI ghi rõ đây là cổng rút gọn.
2. **Bộ test 240 câu = 200 câu văn bản + 40 câu sinh từ HÌNH.** Chia 3 bộ SGK
   = 80 câu/bộ (thầy kê 240 để chia chẵn cho 3 bộ). Bản chuyên đề cũ là
   120 câu = 12 quyển × 10.
3. **Báo cáo: người dùng sẽ cung cấp source `.tex` của chuyên đề cũ**, copy vào
   repo sau. Trong lúc chờ chỉ chuẩn bị SỐ LIỆU, không dựng preamble mới.

## 1. Vì sao M3 rẻ hơn CLAUDE.md đang mô tả

CLAUDE.md viết M3 là "caption chữ đen cho CD/CTST" như thể phải viết bộ đọc
mới. Đo lại code hôm nay thì không phải:

- `src/etl/image_processor.py:155` — docstring của lớp cơ sở nói thẳng:
  *"This base class implements the Cánh Diều (CD) conventions."* Các núm chỉnh
  theo NXB đã có sẵn: `_FIG_CAPTION_ABOVE_OK = False` (CD/CTST caption nằm DƯỚI
  hình, KNTT pill nằm trên), `_SPLIT_SUBFIGURES_BY_TITLE`, `_SUBFIG_TITLE_MAX_ROWS`,
  `_DETECT_TEXTURED_PHOTOS`, `_DETECT_PHOTO_RECTANGLES`.
- `document/specs/2026-08-23-m0-report.md` §157–170 — CD/CTST **in nhãn
  `Hình N.M` bằng chữ đen thường và OCR ĐỌC ĐƯỢC**: 42/32/30/40 (CD) và
  65/49/42/41 (CTST) nhãn trên 30 trang mẫu. Kênh pill đọc 0 ở cả 8 quyển,
  nhưng kênh anchor thường thì mạnh hơn KNTT.

Nên M3 chủ yếu là **gỡ hardcode + ĐO**, không phải viết bộ đọc caption mới.

## 2. Bug im lặng đo được trước khi sửa gì (D-109)

`get_pdf_variant()` trả hằng số `LAYOUT_VARIANT = "kntt"`, và `variant` đó đi
thẳng vào metadata chunk. Đếm trên index 12 quyển đang chạy:

```
('CD',   'kntt') 5 282 chunk
('CTST', 'kntt') 6 177 chunk
('KNTT', 'kntt') 4 934 chunk
```

**11 459 chunk của CD/CTST đang mang nhãn NXB SAI**, 0 chunk mang nhãn đúng.
Không test nào bắt được vì hằng số luôn tự nhất quán với chính nó. Đây là đúng
loại lỗi nguyên tắc 5 cảnh báo: một fallback im lặng đẩy sai lệch xuống dưới.

## 3. Thiết kế P1 — ETL hình 8 quyển CD/CTST

### Bước 0 — spike đo trước khi cam kết giờ chạy (BẮT BUỘC)

CLAUDE.md ước "~4 giờ cho 8 quyển". Con số đó CHƯA ĐO và nhiều khả năng thấp:
KNTT đo 6,51–11,11 s/trang ở **1094×1536**, còn CD/CTST là **2280×3201**
(6_CD 2480×3480) — gấp ~3,5× diện tích. 8 quyển = 1 602 trang.

Đo trên 30 trang `6_CD` + 30 trang `7_CTST` bằng lớp cơ sở, lấy 3 số:
`s/trang` thật · crop/trang · số `Hình N.M` anchor bắt được. Ba số này quyết
định chạy một lượt hay chia đêm, và có cần hạ kích thước hay không.

Ngưỡng hình học của `image_processor` là **phân số theo chiều trang**
(`_FIG_ASSIGN_MAX_VGAP = 0.20`, `_FIG_TOP_GROW_MAX_GAP = 0.045`, …) nên
không lệ thuộc px — khác `toc.py`/`pill.py` vốn phải tỉ lệ theo `REF_WIDTH`.

### Bước 1 — gỡ `LAYOUT_VARIANT = "kntt"` (`image_processor.py:4105`)

`make_image_processor(book_name)` đọc hậu tố `_CD` / `_CTST` / `_KNTT` và
**raise khi không khớp cả ba** — không có nhánh đoán. Đó chính là lý do dòng
comment hiện tại giữ hằng số ("đưa một quyển CTST vào thì hệ thống sẽ gán nhãn
'kntt' … mà không ai biết"); cách chữa đúng là fail loudly, không phải đóng băng.

| NXB | Lớp | Căn cứ |
|---|---|---|
| CD | `ImageProcessor` (base) | base CHÍNH LÀ bản CD (`:155`) |
| KNTT | `KnttImageProcessor` | đã QA, 938 doc, G4 pass (D-87) |
| CTST | base trước, ĐO rồi mới quyết | `CtsstImageProcessor` đã xoá; CLAUDE.md CẤM khôi phục (viết cho render 150 DPI, chưa QA). Chỉ tách lớp con khi số đo đòi, và chỉ override núm |

`get_pdf_variant(book_name)` trả `cd` / `ctst` / `kntt` để metadata chunk hết sai
(§2). Chunk văn bản đã dựng vẫn mang nhãn cũ cho tới lượt bump version kế tiếp —
ghi rõ điều đó, không lặng lẽ để người đọc tưởng đã sửa xong dữ liệu cũ.

### Bước 2 — chạy

`python main.py --image-only --book <tên>` từng quyển (cờ lọc đúng từ D-84).
Đọc `s/trang` từ progress log, KHÔNG tin ước lượng.

### Bước 3 — G4 rút gọn + QA mắt

Thêm chế độ cho `src/test/qa_figures.py`: bỏ kiểm "A = Bài của trang", giữ
"B liên tục 1..max", độ phủ, và cờ `crop nghi cắt lấn`. Rồi mở 20 trang/NXB
bằng `src/test/test_image_extraction_full.py`.

## 4. Thiết kế P2 — bộ test 240 câu

Giữ nguyên **Algorithm 1** của chuyên đề (trang seed cố định → OCR → LLM sinh
câu + gold, gắn `(source_book, source_page)`), thêm 4 nhãn `phan_mon` /
`khoi` / `bo_sach` / `do_kho` mà bản cũ không có.

- 200 câu văn bản: 12 quyển, ~17 câu/quyển. **Không bị P1 chặn** — index text
  12 quyển đã có (16 393 chunk), nên chạy SONG SONG với ETL hình.
- 40 câu từ hình: gold lấy từ `figure_label` + `figure_caption` + `crop_text`
  (ba trường đọc lại từ pixel, KHÔNG phải trường model sinh — D-47/D-85).
  Sinh SAU khi P1 xong để chia đều 3 bộ.
- Tổng 240 = 3 bộ × 80.

**Duyệt tay bắt buộc.** D-90 đo gold key sai **4,1%** (2/49, KTC Wilson
1,1–13,7%) trên bộ 300 cũ. Xuất phiếu ≥50 câu cho người duyệt;
`_generation_meta.json` ghi đúng tỉ lệ đo được, không ghi `false` chung chung.

**Ràng buộc lịch:** OpenRouter free chỉ còn hết tuần này → sinh 200 câu SỚM.

## 5. Thiết kế P3 — báo cáo

Chờ source `.tex`. Cấu trúc Chương 4 của bản cũ để bám:

| mục | nội dung | thay đổi cho bản mới |
|---|---|---|
| 4.1 | môi trường & công cụ | — |
| 4.2 + Bảng 4.2 | thống kê per-quyển: trang / chunk / vector hình | cũ 2 319 trang & 13 754 chunk & 2 408 vector hình → nay **2 399 trang & 16 393 chunk**; vector hình phải ghi "4/12 quyển" cho tới khi P1 xong |
| 4.3 + Alg. 1 + Bảng 4.3 | sinh testset có gắn nhãn nguồn | 120 → **240**; Bảng 4.3 thêm cột phân môn |
| 4.4 | P@k, R@k, MRR + LLM-judge 3 tiêu chí; `overall = ½(retrieval+answer)` | cũ dùng dung sai ±1 trang; **nay `PAGE_TOLERANCE = 0`** (±1 thổi phồng recall) — phải nói rõ vì nó làm số mới thấp hơn số cũ một cách hợp lệ |
| 4.5 | kết quả + xếp hạng 12 quyển | thêm bảng hybrid vs BM25 vs dense (D-82) |
| 4.6 | thảo luận | thêm giới hạn trần 0,104 của bộ test đa phương thức |

## 6. Điều CẤM trong công việc này

1. **Cấm khôi phục `CtsstImageProcessor` cũ** (`git show 75b8377^`) — nó viết cho
   render 150 DPI và chưa từng QA trên nguồn pixel.
2. **Cấm thêm regex tên quyển để đoán NXB.** Không khớp thì raise.
3. **Cấm công bố số G4 rút gọn như thể là G4 đầy đủ.**
4. **Cấm sửa `phieu_nguoi.json`** hay bất kỳ nhãn người đã duyệt.
5. **Cấm chạy 8 quyển trước khi Bước 0 cho ra `s/trang` thật.**
6. **Cấm ghi `human_reviewed: true`** khi chưa có người duyệt thật.

## 7. KẾT QUẢ Bước 0 (chạy 2026-08-25, D-110)

15 trang rải đều/quyển, `force=True`, DB scratch, **OWL-ViT bật** (`OWL-ViT
detection failed = 0`):

| quyển | lớp | px | s/trang | crop/trang | doc có `figure_label` | `image_type` |
|---|---|---|---|---|---|---|
| 6_CD | base | 2480×3480 | **22,44** | 2,53 | 35/38 | — |
| 8_CD | base | 2280×3201 | **7,59** | 1,40 | 20/21 | single 9 · activity 6 · composite 2 · sub 4 |
| 7_CTST | base | 2280×3201 | **7,70** | 0,87 | 11/13 | single 11 · activity 2 |
| 7_CTST | KNTT | 2280×3201 | 8,95 | 0,80 | 10/12 | single 10 · activity 2 |
| 9_CTST | base | 2280×3201 | **8,27** | 0,80 | 11/12 | single 10 · activity 2 |

**Ba kết luận:**

1. **ETA ≈ 4 h 13**, không phải 6 h: `6_CD` là **ngoại lệ** (to hơn 1,4× diện
   tích *và* 2,53 crop/trang), ba quyển CD còn lại chạy như CTST. Chi tiết:
   1 h 07 (6_CD) + 1 h 15 (7/8/9_CD) + 1 h 51 (CTST). `7_CD`/`9_CD` **chưa đo**.
2. **CTST dùng lớp cơ sở** — thắng `KnttImageProcessor` trên cả hai trục
   (11 vs 10 nhãn, 7,70 vs 8,95 s/trang). §3 Bước 1 chốt theo số này.
3. **Kênh anchor chữ đen đủ mạnh**, đúng như M0 dự báo → không viết bộ đọc mới.

**Câu còn mở, chuyển sang Bước 3:** CTST ra **0** `composite_figure`/`sub_figure`
trong khi CD ra 6. Chưa biết CTST đang bỏ sót hay sách vốn ít hình con — phải
mở trang ra xem, không suy từ con số.

**Cái bẫy đã dính, ghi để lượt sau không mất một lượt đo:** OWL-ViT nạp từ
`./models/owlvit-base-patch32` — **đường dẫn tương đối**. Chạy từ cwd khác repo
root thì nó fail-open im lặng, mọi `s/trang` thiếu và mọi so sánh lớp vô hiệu
(bắt được nhờ đọc log, không nhờ test). Script đo nay ném ngay nếu OWL không nạp.
Cùng họ với D-69.

## 8. Trạng thái khi bàn giao

- Bước 0 XONG. Chưa động vào code sản xuất.
- Index: 16 393 chunk văn bản (12 quyển) · 938 doc hình (4 quyển KNTT).
- Việc kế tiếp: Bước 1 — gỡ `LAYOUT_VARIANT` (§3).
