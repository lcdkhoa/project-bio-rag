# Báo cáo thực thi: chuyển ETL sang nguồn PNG (KNTT, 801 trang)

> Thực thi prompt `2026-08-21-png-source-etl-prompt.md`. Mọi con số dưới đây là
> **đo được trong lượt thực thi này**, kèm cách đo, để lần sau không phải đo lại
> và để ai đọc cũng phân biệt được *cái đã verify* với *cái chưa*.
> Quyết định tương ứng: **D-33 … D-39** trong `document/decision_log.html`.

---

## 1. Đã làm & đã verify

| Task | Việc | Bằng chứng |
|---|---|---|
| 0 | Đồng bộ CLAUDE.md + decision log | CLAUDE.md mục "Active redesign" chia rõ DONE / OPEN; D-33…D-39 |
| 1 | `PageSource` (`src/etl/page_source.py`) thay `fitz` ở mọi đường ETL; checkpoint theo hash TỪNG TRANG + `TEXT_EXTRACTION_VERSION` | E2E 4 lượt, xem §2.1 |
| 2 | Xoá hẳn `preprocess_page` (cả module, cả test, cả call site) | `git rm src/etl/layout/preprocess.py`; recall segmenter KHÔNG giảm (2,17 → 4,10) |
| 3 | OCR vùng chỉ định `--psm 6` / `--psm 7` (crop < 60 px) | prompt §1.2: 6293 → 6535 token (+3,8%), cùng thời gian |
| 4 | Số trang: hợp crop góc 1× + 3×, nới regex (`"110°"`) | §2.2 — **793/793 = 100,0%** trên toàn bộ 801 trang |
| 5 | `build_page_map` duyệt tập số trang thật; lỗ trang → flag; trang in 0/1 → `role="cover"` | test tổng hợp + G1 thật (2 bìa/quyển đúng như dự đoán) |
| 6 | Xoá `RENDER_DPI` khỏi config, `.env.example`, mọi call site | `grep RENDER_DPI` chỉ còn 1 dòng *giải thích vì sao không còn* |
| 7 | `diacritic.py` → chỉ gắn cờ `needs_review`, không đổi ký tự nào | `tests/test_diacritic.py` mở đầu bằng `assert not hasattr(D, "fix_diacritics")` |
| 8 | Viết lại `segment_page` | §2.3 — 2,17 → 4,10 vùng/trang, 0 trang bị giảm |

Toàn bộ test: **163 passed, 3 skipped**.

### Xoá code (nguyên tắc 7)
`src/etl/layout/preprocess.py`, `src/etl/layout/page_number.py` (chứa fallback
`index + 1` — chính lỗi off-by-one mà spec cấm), `tests/layout/test_preprocess.py`,
`tests/layout/test_page_number.py`, `tests/test_checkpoint_no_filename_skip.py`
(hàm `_should_skip_file` không còn tồn tại: giờ không có đường skip theo tên file
nào để mà test).

---

## 2. Số đo

### 2.1 Checkpoint per-page (Task 1) — E2E thật, DB riêng
Corpus scratch: 12 trang đầu của sách 6, `RAG_DATA_DIR` + `RAG_DATABASE_DIR` trỏ
vào thư mục tạm (không chạm `database/` của dự án).

| Lượt | Điều kiện | Kết quả |
|---|---|---|
| 1 | lần đầu | index trang 1–12, **48 chunk**; trang 1–2 `role=cover` → bỏ, không OCR |
| 2 | không đổi gì | `All pages already indexed, skipping` |
| 3 | `TEXT_EXTRACTION_VERSION=v2_test` | làm lại đủ 12 trang, **vẫn 48 chunk** (upsert, không nhân bản) |
| 4 | giữ `v2_test` | skip toàn bộ |
| 5 | đổi **1 pixel** của `page_010.png` | `Pages to index: [10]` — đúng một trang |

Chunk id thật: `SGK_KHTN_6_KNTT#ac812e47…_p10_c0`. Trang in trong metadata: nguồn
3–12 → in 2–11 (đúng `page_index − 1`), không có chunk nào cho trang in 0/1.

### 2.2 Số trang (Task 4, cổng G1) — toàn bộ 801 trang
Output thật của `python main.py --build-manifests` (lượt cuối, sau khi bỏ dò banner
trên trang MỤC LỤC):
```
=== G1: định danh trang ===
KHTN6-KNTT: 196 trang (2 bìa không in số) | offset -1 (phiếu 194/221) | ocr_confirmed 194/194 (100.0%) | Bài 3  | flag 6  | PASS
KHTN7-KNTT: 180 trang (2 bìa không in số) | offset -1 (phiếu 178/200) | ocr_confirmed 178/178 (100.0%) | Bài 23 | flag 27 | FAIL
    - KHTN7-KNTT: spine_out_of_order — Bài 25 (trang 12) không tăng trước Bài 19 (trang 91)
KHTN8-KNTT: 197 trang (2 bìa không in số) | offset -1 (phiếu 195/220) | ocr_confirmed 195/195 (100.0%) | Bài 24 | flag 27 | PASS
KHTN9-KNTT: 228 trang (2 bìa không in số) | offset -1 (phiếu 226/255) | ocr_confirmed 226/226 (100.0%) | Bài 50 | flag 52 | FAIL
    - KHTN9-KNTT: spine_out_of_order — Bài 13 (trang 65) không tăng trước Bài 1 (trang 68)
```
Tổng **793/793**. Tập trang không xác nhận đúng bằng `{page_001, page_002}` mỗi
quyển — đúng dự đoán của spec §1.6, và hai trang đó **thật sự không in số** (đã
mở `page_002` sách 6 ra xem: trang tên sách). Vượt ngưỡng nghiệm thu ≥ 98,9%.

Lưu ý cách tính: tỉ lệ lấy trên **trang có in số** (loại `role="cover"` khỏi mẫu
số). Để bìa trong mẫu số là bắt OCR "xác nhận" một con số không tồn tại, và trộn
hai thứ khác nhau vào một phép đo (D-36).

**Hai quyển FAIL G1 vì SPINE BÀI, không vì định danh trang** — xem §3.2.

### 2.3 Recall segmenter (Task 8) — 40 trang, 4 quyển, cùng mẫu cho cả hai bản
```
CU  (HEAD): 2,17 vùng/trang | body 40, info_box 40, sidebar 7
MOI       : 4,10 vùng/trang | body 40, info_box 83, sidebar 41
trang bị GIẢM số vùng: 0
```
(Bản cũ đo lại được 2,17 — khớp với 2,30 đã ghi trong spec, khác chút vì mẫu trang khác.)

Nguyên nhân gốc đã đo được trước khi sửa, trên `page_010` (trang chuẩn):
- close kernel 3/7/15/25 **đều** cho một blob 975×672 = 39% trang, độ phẳng 0,06 → loại → **0 hộp**;
- sidebar tím: độ phẳng **0,42** < ngưỡng 0,45 vì đo trên bbox (bao khe trắng + đuôi bong bóng thoại).

QA text thật trên `page_010` sau khi sửa:
- `'dua vao hinh 1.2, hay so sanh'` → **OK** (trước: mất sạch)
- `'chi ra nhung loi ich'` → **OK** (trước: câu bị **cắt đầu** thành `'dụng khoa học tự…'`)
- `'hinh 1.2'`, `'hinh 1.3'` → OK
- `'thong tin lien lac'`, `'san xuat'`, `'giao thong van tai'` → **vẫn MẤT** (§3)

### 2.4 Hai bộ lọc rác OCR — đo rồi **không** dùng (D-38)
- **Ngưỡng conf theo dòng.** Trên 25 trang / 913 dòng / 35 288 ký tự: 58,3% dòng ở
  conf 90–99, 18,8% ở 80–89. Dải 50–70 là **hỗn hợp**: rác (`'HÌÀ `'`, `'T M (,, \'`)
  lẫn chữ thật (`'Em có biết?'` 56,3 · `'Gai glycoprotein'` 54,0 · `'bảo toàn năng lượng'` 60,7).
- **Bỏ dòng không có từ nào ≥ 3 chữ cái.** Bỏ 654/35 288 ký tự (1,85%) trên 123 dòng;
  gần hết là rác, **nhưng** casualty gồm `'e Ở 20 °C, 100 mL'` và `'e Ở 100 °C, 100 mL'`
  (số liệu độ tan thật) và `'1 mồ = 1000 L sp'`.

→ Mọi ngưỡng đủ để cắt rác đều cắt cả chữ thật. Mất chữ tệ hơn nhiễu, và rác
**không bịa** ra điều gì, nên giữ rác + gắn cờ `needs_review` cho chunk chứa nó.
Đo được: 21/48 chunk của lượt E2E mang `needs_review=True`, phần lớn vì chính mấy
token rác đó — cờ đang chỉ đúng chỗ.

### 2.5 Độ dài hộp (D-39)
25 trang, 67 hộp: **22,4%** dài hơn `CHUNK_SIZE` (400), **10,4%** dài hơn 600,
7,5% dài hơn 800, dài nhất **1 607** ký tự. → cắt hộp dài hơn 1,5 × `CHUNK_SIZE`,
vẫn giữ nhãn `region_type`; hộp thường vẫn nguyên khối.

---

### 2.6 Nhãn chữ trắng trên nền màu — `src/etl/layout/pill.py` (D-40)

Bổ sung sau khi người dùng nhắc lại mục tiêu thật (code để ETL cả text lẫn hình
trên Colab): nhãn `Hình N.M` **chính là anchor mà đường crop hình dựa vào**, và nó
là chữ trắng trên pill cam nên OCR cả trang đọc ra rỗng → detector mất neo.

Loại bỏ hai giả thuyết sai của chính mình, bằng số:
- **Không phải vấn đề độ phân giải**: nhãn không đọc được ở 1× / 1,134× (đúng kích
  thước bản render 150 DPI cũ) / 1,5× / 2×.
- **Đảo màu cả crop không cứu**: tesseract tự binarize cục bộ nên vẫn đọc phần chữ tối.

Cách chạy được: khoanh đúng pill (khối màu đặc, lấp ≥ 0,80 bbox, có lỗ 5–55%, cỡ
một nhãn) → đảo màu → `--psm 7` → **chỉ nhận khi khớp `Hình N.M`**.

| | trước | sau |
|---|---|---|
| 32 trang mẫu / 4 quyển | ~0 nhãn từ pill | **13 trang, 17 nhãn** |
| `page_010` anchor | 0 Hình caption | 1 |
| `page_075` anchor | 0 | 2 (`Hình 21.3`, `Hình 21.4`) |

Kiểm tra chéo miễn phí: số Bài trong nhãn khớp vị trí trang (`Hình 34.12` ở trang
123 sách 6, nơi Bài 34 nằm).

---

## 3. Chưa làm / chưa verify (nói thẳng)

1. **Pill LỒNG trong ô đã có tông màu vẫn không đọc được** (`Thông tin liên lạc`,
   `Sản xuất`, `Giao thông vận tải`): nó dính vào ô rồi bị loại vì quá to. Không
   sửa được bằng ngưỡng saturation — đo trên `page_010`, pill "Giao thông vận tải"
   có sat **82** trong khi dải tím nó nằm trên có sat **157**. Đã thử tách theo dải
   hue: **không khá hơn** (cùng kết quả trên `page_010`, thêm rác trên `page_011`),
   nên dừng sau 2 lần thử và ghi lại thay vì đào tiếp. Cần thiết kế dựa trên tương
   phản CỤC BỘ.
2. **Spine Bài còn sai nặng** → `bai_so` **không** vào metadata chunk (D-39). Đo:
   sách 6 dựng được **3 Bài** cho ~55 và MỤC LỤC sách 6 OCR ra **0 entry**; sách 7
   và 9 FAIL G1 vì `spine_out_of_order`. Trước khi sửa còn tệ hơn: banner detector
   fire trên chính trang MỤC LỤC nên sách 6 có một "Bài 20" trải trang 6–90 và sách
   7 có "Bài 19 ở trang 6". Đã sửa bug đó (không dò banner trên `TOC_PAGE_NUMBERS`)
   và thêm flag `bai_numbers_not_contiguous`,
   nhưng dựng lại TOC OCR + độ nhạy banner là **việc của milestone spine**, không
   nằm trong prompt này.
3. **Đường ảnh CHẠY được nhưng output chưa tin được (D-41).** Smoke test thật 4
   trang (`--image-only`, captioning tắt): không crash, sinh 5 crop, index được.
   Nhưng 3/4 trang sai nhãn/khung: `figure_label='Em có biết'` (info-box bị nhận là
   hình), `label='quan sát'` thay vì `Hình 21.3` **dù anchor pill đã đọc đúng hai
   nhãn đó**, và một crop rộng gần nửa trang (454..1094 × 391..1323). Tức bước gán
   anchor → vùng và hình học crop phải đo lại trên nguồn này = **milestone M3**.
   Đường captioning (Vintern) không bị thay đổi nên không chạy trong smoke test.
4. **False positive nhãn loại vùng.** Segmenter mới nhận nửa biểu đồ tròn ở
   `page_174` là "sidebar" (đúng là hình). Không mất chữ, không bịa — chunk đó chỉ
   bị gán nhãn `region_type` sai, và citation sẽ ghi "mục bên lề" cho một nhãn biểu
   đồ. Đã thử lọc theo tỉ lệ lấp bbox: **không dùng được** (hộp thật có tỉ lệ lấp
   0,07–0,97 vì mask chỉ đếm pixel có tông màu).
5. **Gold set CER vẫn hẹp** (4 vùng trên 1 trang + confidence trên 8 trang từ lượt
   trước). Muốn kết luận mạnh về chất lượng OCR toàn corpus thì cần gold set rộng
   hơn do người xác nhận.
6. **Dual-engine OCR consensus**: vẫn hoãn (cần PaddleOCR VN + bake-off trên gold set).
7. **Regenerate eval testsets** cho 4 quyển: chưa làm.
8. **`--text-only` trên toàn bộ 801 trang**: chưa chạy (E2E chỉ 12 trang). Embedding
   trên CPU là chỗ tốn, không phải OCR.

---

## 4. Thứ tự khuyến nghị cho lượt sau

0. Cách chạy trên Colab: **`document/colab_runtime_etl.ipynb`** (notebook người dùng
   đang dùng — đã cập nhật: bước `--build-manifests` MỚI và bắt buộc,
   `RAG_MANIFEST_DIR` để manifest đi theo repo, ô kiểm tra nguồn/manifest/tiến độ,
   và cảnh báo trạng thái phía ảnh). Không tạo file runbook song song.
1. M3 figures: gán anchor → vùng + hình học crop (mục 3.3) — đang là vùng tối lớn nhất.
2. Dựng lại spine Bài (mục 3.2) — có nó thì `bai_so` mới được vào index, và G3
   (page-accuracy) mới đo được theo Bài.
3. Dò pill chữ trắng (mục 3.1) — nhỏ hơn nhưng là chữ thật đang mất.
4. Chạy `--text-only` toàn corpus rồi đo lại retrieval (P/R/MRR) trên testset mới.
