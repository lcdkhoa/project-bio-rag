# Dựng lại ETL cho 12 quyển / 3 nhà xuất bản (đo, đừng đoán)

Nguồn yêu cầu: `document/goal.docx` (RULE #0). Corpus cũ + `database/` đã bị người dùng
xoá; **không có gì để resume**. Yêu cầu của người dùng, nguyên văn: *"hãy quên hết tất cả
những gì đang có cho việc etl cả text lẫn ảnh, hãy tìm đặc trưng của mỗi sách"*.

## 0. Số đo trên corpus mới (2026-08-22) — dùng luôn, đừng đo lại

12 quyển / **2 403 trang** (đề cương ước ~2 319; chênh 84 trang, không phải lỗi).

| Quyển | n | dải tên file | kích thước | mode |
|---|---|---|---|---|
| 6_CD | 179 | 1..179 | 2480×3480 | RGB |
| 7_CD | 172 | **0..171** | 2280×3201 (tr. đầu 2274×3182) | RGB |
| 8_CD | 208 | **0..207** | 2280×3201 (tr. đầu 2294×3192) | RGB |
| 9_CD | 217 | 1..217 | 2280×3201 (tr. đầu 2300×3201) | RGB |
| 6_CTST | 204 | 1..204 | 2280×3201 | RGBA |
| 7_CTST | 188 | 1..188 | 2280×3201 | RGBA |
| 8_CTST | 223 | 1..223 | 2280×3201 | RGBA |
| 9_CTST | 215 | 1..215 | 2280×3201 | RGBA |
| 6_KNTT | 195 | 1..195 | 1094×1536 | RGBA |
| 7_KNTT | 179 | 1..179 | 1094×1536 | RGBA |
| 8_KNTT | 196 | 1..196 | 1094×1536 | RGBA |
| 9_KNTT | 227 | 1..227 | 1094×1536 | RGBA |

Không quyển nào thiếu số (gaps = 0).

**Ba hệ quả bắt buộc:**

1. **KNTT là quyển ĐỘ PHÂN GIẢI THẤP NHẤT, kém CD/CTST ~2,1 lần theo cạnh** (1094×1536
   vs 2280×3201 ≈ 3,5 lần diện tích; 6_CD còn cao hơn: 2480×3480). Mọi kết luận OCR cũ
   (CER 0,0048; "upscale không đổi gì"; **D-56 mất chỉ số dưới**) đều đo **chỉ trên
   KNTT ở 1094×1536**. Giả thuyết phải kiểm tra sớm: **`O₂`/`H₂SO₄` có thể đọc được ở
   CD/CTST**, tức D-56 là hiện tượng của độ phân giải chứ không phải của Tesseract. Nếu
   đúng thì cách xử lý công thức chia theo nhà xuất bản, không phải một luật chung.
2. **Đánh số file đã đổi và KHÔNG đồng nhất.** 7_CD và 8_CD bắt đầu từ `page_000`, mười
   quyển kia từ `page_001`. Đo thử số trang in ở 4 trang/quyển trên 5 quyển: chỗ nào đọc
   được số thì **lệch = 0** (kể cả KNTT — trước đây là −1, người dùng đã đánh số lại).
   Nhưng 6_CD và 6_CTST **không đọc được số nào** bằng phép dò dải trên/dưới thô → vị trí
   số trang là **đặc trưng riêng của từng quyển**, phải đo, không được giả định offset 0.
3. **Mọi thứ phụ thuộc corpus cũ đều vô hiệu:** `database/` (đã xoá), `database/manifests/*`,
   4 bộ testset 100 câu, gold set G2 24 trang (số trang đã đổi), và mọi số G1/G3/G4/G5.

## 1. Nguyên tắc cho bản dựng lại

- **Không có "biến thể mặc định".** `LAYOUT_VARIANT = "kntt"` và
  `make_image_processor()` luôn trả KnttImageProcessor phải bị gỡ. Mỗi quyển khai báo
  đặc trưng ĐO ĐƯỢC của nó, không suy từ tên file bằng regex.
- **Không khôi phục thẳng `CtsstImageProcessor`** (`git show 75b8377^:src/etl/image_processor.py`):
  nó viết cho render 150 DPI của PDF cũ, chưa từng QA trên nguồn pixel này.
- **Cấm upscale thân bài** vẫn giữ — nhưng lý do cũ (đo trên KNTT) phải được **đo lại**
  trên CD/CTST trước khi áp dụng cho chúng.
- Fail loudly: quyển nào chưa có "layout fingerprint" đã xác minh thì ETL **raise**,
  không chạy bằng tham số của quyển khác.

## 2. M0 — Layout fingerprint cho từng quyển (việc đầu tiên)

Một công cụ đo, xuất `database/fingerprints/{book}.json`, cho mỗi quyển đo:

| Trường | Cách đo | Vì sao cần |
|---|---|---|
| `page_number_zone` | quét 9 dải biên (4 góc, 4 cạnh, giữa đáy) × {1×,2×,3×} × {psm 6,7,11}; giữ dải cho tỉ lệ đọc đúng cao nhất trên ≥40 trang | 6_CD/6_CTST hiện đọc 0/4 |
| `page_offset` | trung vị (số đọc được − số trong tên file), kèm số phiếu | 7_CD/8_CD bắt đầu từ 000 |
| `toc_pages` | dò trang chứa "MỤC LỤC" (không hardcode) | KNTT từng có 3 trang TOC, hằng số cũ làm mất Bài 40–55 |
| `toc_geometry` | cột số trang: đường kẻ dọc / dải màu / gutter | đã đo trên KNTT, CD/CTST chưa biết |
| `body_dpi_est` | px/cm theo khổ 19×26,5 cm | quyết định có được upscale hay không |
| `box_palette` | histogram hue của vùng phẳng ≥2% diện tích trên 30 trang | hộp màu/sidebar khác nhau theo NXB |
| `pill_pattern` | có nhãn `Hình N.M` dạng pill trắng-trên-màu không, và ở đâu | anchor cắt hình của KNTT |
| `figure_caption_regex` | mẫu chú thích thật đọc được từ trang | CD dùng "Hình 1.2." khác KNTT? chưa biết |

Nghiệm thu M0: 12/12 quyển có fingerprint; `page_offset` có ≥95% phiếu đồng thuận, quyển
nào không đạt thì **ghi cờ**, không đoán.

## 3. Thứ tự sau M0

M1 manifest + G1 (12 quyển) → M2 text ETL + chunk (BM25 index dựng cùng lúc, xem §4) →
M3 hình ảnh + G4 theo từng NXB → M4 bộ test 12 quyển có nhãn `phan_mon`/`do_kho` →
M5 thực nghiệm đối chiếu.

## 4. Việc mới do đề cương yêu cầu (không có trong code)

1. **BM25** — chưa tồn tại. Dựng chỉ mục thưa song song với `biology_text`, cùng khoá
   chunk id, để so được từng câu. Tiếng Việt: tách từ + bỏ dấu **chỉ ở phía truy vấn/chỉ
   mục thưa**, tuyệt đối không sửa chữ đã lưu (CẤM #5).
2. **Hợp nhất thưa + dày** (RRF hoặc điểm chuẩn hoá) + giữ nguyên rerank/cổng lọc hiện có.
3. **Đưa caption deterministic vào prompt** (người dùng chọn): ngữ cảnh multi-modal =
   text chunk + `figure_label` + caption đọc từ pill/OCR. **Không** dùng Vintern (D-47).
   Ablation: bật/tắt đúng phần này.
4. **Bảng đối chiếu**: BM25 thuần / dense thuần / hybrid; text-only / multi-modal;
   bật-tắt rerank; bật-tắt cổng lọc.
5. **Bộ test** có `phan_mon` (Lý/Hoá/Sinh), `khoi` (6–9), `bo_sach`, `do_kho`
   (trích xuất trực tiếp / suy luận liên kết / tổng hợp đa ngữ cảnh), phân bố đều.

## 5. Chi phí ước lượng (ngoại suy từ tốc độ ĐÃ ĐO trên KNTT — sẽ cao hơn vì ảnh to gấp 3,5 lần)

Text 3,56 s/trang × 2 403 ≈ **2,4 giờ**; ảnh 8,86 s/trang × 2 403 ≈ **5,9 giờ**. Ảnh
CD/CTST lớn gấp ~3,5 lần diện tích nên **cả hai con số này là cận dưới** — phải đo lại
s/trang trên một quyển CD trước khi hứa lịch.
