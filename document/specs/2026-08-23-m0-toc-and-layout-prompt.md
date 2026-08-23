# Prompt cho lượt sau — M0 phần còn lại: MỤC LỤC + đặc trưng layout 12 quyển

> Đọc `CLAUDE.md` RULE #0 trước. Nguồn yêu cầu duy nhất là `document/goal.docx`
> (đề cương ĐỒ ÁN TỐT NGHIỆP, ký 13/07/2026). Thiết kế tổng thể của lượt dựng lại:
> `document/specs/2026-08-22-12books-3publishers-etl-rebuild.md`.

---

## 0. ĐÃ ĐO — dùng luôn, KHÔNG đo lại

### 0.1 Corpus (2026-08-23)

**12 quyển / 3 NXB / 2 399 trang, tên file `page_001.png`…, 0 khoảng trống, mọi
quyển bắt đầu từ 1.** `database/` đã bị xoá — ETL là một lượt chạy mới hoàn toàn.

| quyển | n | kích thước | mode |
|---|---|---|---|
| 6_CD | 179 | 2480×3480 | RGB |
| 7_CD | 171 | 2280×3201 | RGB |
| 8_CD | 207 | 2280×3201 | RGB |
| 9_CD | 215 | 2280×3201 | RGB |
| 6/7/8/9_CTST | 204 / 188 / 223 / 215 | 2280×3201 | RGBA |
| 6/7/8/9_KNTT | 195 / 179 / 196 / 227 | 1094×1536 | RGBA |

**KNTT là bộ ĐỘ PHÂN GIẢI THẤP NHẤT** — kém CD/CTST ~2,1 lần theo cạnh, ~3,5 lần
diện tích. Mọi kết luận OCR cũ trong repo (CER 0,0048; "upscale không đổi gì";
**D-56 mất chỉ số dưới**) đều chỉ đo trên KNTT 1094×1536 → **historical**, chưa
biết có đúng cho CD/CTST không.

### 0.2 M0 phần số trang — ĐÃ XONG, kết luận chốt

Công cụ: `src/etl/book/fingerprint.py`. Kết quả trên 40 trang mẫu/quyển:

**12/12 quyển `offset = 0`** (số trang in == số trong tên file), margin thắng/á
quân **36–39 / 40 phiếu**, không quyển nào bị cờ.

| quyển | khớp | margin | scale |
|---|---|---|---|
| 6_CD | 37/40 | 36 | 2× |
| 7_CD | 38/40 | 36 | 2× |
| 8_CD | 38/40 | 36 | 2× |
| 9_CD | 37/40 | 36 | 2× |
| 6/7/8/9_CTST | 39/39/39/39 | 39/39/38/39 | 2×/1×/1×/1× |
| 6/7/8/9_KNTT | 39/39/39/39 | 39/39/39/39 | 1× |

18/480 trang không đọc được số: **12 là `page_001`** (bìa, thật sự không in số) và
**6 trang CD** — cả 6 đã mở ảnh ra xem, **đều CÓ in số**, tức lỗi đọc chứ không
phải trang thiếu số.

**Đặc trưng chân trang CD đã xác minh bằng ảnh:** `[số] KHOA HỌC TỰ NHIÊN <lớp>`
ở trang chẵn (số bên trái, x≈0,104), `KHOA HỌC TỰ NHIÊN <lớp> [số]` ở trang lẻ
(x≈0,894), y≈0,944. **Số nằm trên một ô màu, màu đổi theo chương.** KNTT: x≈0,074
/ 0,928, y≈0,951. CTST: x≈0,112 / 0,889, y≈0,947.

### 0.3 Bốn giả thuyết ĐÃ BỊ PHÉP ĐO BÁC BỎ — đừng thử lại

1. **Tách từng chữ số rồi OCR `--psm 10`.** Tệ hơn hẳn: đọc `86` thành **`56`** —
   sai mà tự tin, nguy hiểm hơn đọc trượt. Bỏ.
2. **"Ô màu tím quá tối nên nuốt chữ số"** (6_CD tr.171/175). Bác bỏ: median gray
   **255**, tỉ lệ pixel tối **0,05** — y hệt trang đọc được. Nguyên nhân thật là
   cụm mực rộng **355 px** thay vì 33 px, tức đã dính chữ chân trang.
3. **Bỏ whitelist chữ số** cho dễ đọc hơn. Không cải thiện ca nào.
4. **Upscale cubic thêm** cho 3 trang có chữ "7". cubic 2/3/4 sửa **0/3**;
   **lanczos 6/8 sửa 2/3** và giữ 4/4 đối chứng; nearest kém hơn cả hai.

### 0.4 Ba cái bẫy hạ tầng đã cắn thật trong lượt trước

1. **`PngFolderPageSource` cache danh sách file lúc `__init__`.** Sửa/xoá file
   giữa lượt chạy dài → `PageSourceError` khi load. Nếu người dùng đổi
   `datasources/` thì phải **khởi động lại** lượt đo, không chạy tiếp.
2. **Pipe qua `tail` làm output bị đệm** → không xem được tiến độ suốt 30 phút.
   Ghi thẳng ra file bằng `>` và `tail -f` file đó, hoặc để `--verbose` in trực tiếp.
3. **Giết tiến trình giữa lượt chạy làm hỏng artifact.** Tesseract con chết → mỗi
   quyển raise `TesseractError` → nhánh cô lập lỗi **ghi đè 11/12 file đo tốt**
   bằng bản `offset=None`. Đã vá (`run()` giờ giữ nguyên file cũ khi lần đo hỏng),
   nhưng **`database/fingerprints/*.json` hiện tại đang là bản HỎNG** — xem §1.

---

## 1. VIỆC ĐẦU TIÊN — dựng lại `fingerprints/*.json` (gộp vào lượt đo MỤC LỤC)

11/12 file JSON hiện chứa `offset: null` + cờ `loi_khi_do:TesseractError`. Con số
thật đã có ở §0.2. **Không chép tay số vào JSON** — chạy lại phép đo:

```bash
python -m src.etl.book.fingerprint --all --sample 40 --verbose > fp.log 2>&1 &
tail -f fp.log
```

**Nghiệm thu:** 12/12 `offset=0`, không cờ, và hai bản vá mới (tái-tách cụm rộng +
lanczos 6/8) phải nâng số trang đọc được — kỳ vọng 6_CD 37→39, 7_CD 38→39,
9_CD 37→39, 8_CD 38→39. **Nếu KHÔNG nâng thì báo cáo đúng như đo được**, đừng sửa
ngưỡng cho đẹp số.

Chạy chung một lượt với phép đo MỤC LỤC ở §2 để chỉ tốn một lần quét.

---

## 2. M0 phần còn lại — bốn trường đặc trưng, mỗi trường một phép đo

Bổ sung vào `src/etl/book/fingerprint.py`, ghi cùng file JSON mỗi quyển.

### 2.1 `toc_pages` — trang MỤC LỤC, DÒ chứ không hardcode

Hằng số cũ `TOC_PAGE_NUMBERS = (5, 6)` đã từng **âm thầm làm mất Bài 40–55** của
KNTT lớp 6 vì quyển đó có **ba** trang MỤC LỤC. Không được lặp lại.

Cách đo: OCR 15 trang đầu mỗi quyển (psm 6), tìm trang chứa `MỤC LỤC` / `MUC LUC`
(so khớp đã bỏ dấu, chịu được lỗi OCR), rồi **mở rộng sang các trang liền kề** nếu
trang đó cũng mang đặc trưng bảng mục lục (nhiều dòng kết thúc bằng số trang, hoặc
có cột số ở lề phải). Ghi cả danh sách trang lẫn **bằng chứng vì sao** mỗi trang
được nhận.

### 2.2 `toc_geometry` — cột số trang trong bảng MỤC LỤC

Đã đo trên KNTT: cột số trang là dải giữa **hai đường kẻ dọc cuối** (quyển 6/9, có
kẻ) hoặc **nhóm mực phải nhất sau một gutter ≥ 8 px** (quyển 7/8, dùng dải màu).
**CD và CTST chưa biết** — phải đo, không được mượn.

Ba cái bẫy đã đo trên KNTT, kiểm lại cho CD/CTST:
- cột số của KNTT lớp 8 chỉ rộng **29 px** → crop cắt cụt chữ số đầu (`180`→`80`);
- **đệm crop chỉ khi cột đến từ gutter** — đệm một cột có kẻ sẽ liếm phải đường kẻ
  và ô chương trống OCR ra số ma;
- không psm nào thắng mọi ô → hợp nhất pad × scale × psm, rồi ràng buộc **đơn điệu
  không giảm**; không khớp thì **bỏ mục đó và gắn cờ**, tuyệt đối không đoán.

### 2.3 `box_palette` — bảng màu hộp / sidebar

Histogram hue của các vùng phẳng ≥2% diện tích trên 30 trang/quyển. Dùng để tách
sidebar, hộp thông tin, hộp hoạt động ở bước segmenter. **Không hardcode màu của
NXB** — bảng màu là kết quả đo của từng quyển.

### 2.4 `pill_pattern` + `figure_caption_regex` — nhãn hình

KNTT dùng nhãn `Hình N.M` dạng **pill trắng trên nền màu**, đọc bằng
`src/etl/layout/pill.py` (invert + psm 7, hợp nhất `CLOSE_KERNELS = (3, 5, 9)`).
**CD/CTST chưa biết dùng kiểu gì.** Đo: lấy 30 trang có hình/quyển, tìm mẫu chuỗi
chú thích thật (`Hình 1.2`, `Hình 1.2.`, `H.1.2`…) và xem nhãn nằm trong pill,
trong caption dưới hình, hay cả hai.

**Nghiệm thu M0:** 12/12 quyển có đủ 5 trường (`page_number`, `toc_pages`,
`toc_geometry`, `box_palette`, `pill_pattern`), quyển nào thiếu thì ETL **raise**
chứ không mượn tham số quyển khác.

---

## 3. Phép đo nên chen vào sớm (rẻ, và nó đổi thiết kế)

**Chỉ số dưới ở độ phân giải CD/CTST.** D-56 kết luận `O₂`→`0,`, `H₂SO₄`→`H,SO,`
— nhưng đo **chỉ trên KNTT 1094×1536**. CD/CTST lớn gấp ~3,5 lần diện tích. Lấy
~10 trang Hoá/Lý của một quyển CD và một quyển CTST, OCR, đếm công thức đọc đúng
so với hỏng. **Nếu chỉ số dưới sống sót ở CD/CTST thì "bước xử lý đặc thù cho công
thức Hoá, Lý" (Nội dung 1 của đề cương) chia theo NXB, không phải một luật chung**
— đây là kết quả có thể viết thẳng vào báo cáo.

---

## 4. Sau M0 — thứ tự đã chốt

M1 manifest + G1 (12 quyển) → M2 text ETL + chunk, **dựng chỉ mục BM25 cùng lúc**
→ M3 hình ảnh + G4 theo từng NXB → M4 bộ test 12 quyển có nhãn
`phan_mon`/`khoi`/`bo_sach`/`do_kho` → M5 thực nghiệm đối chiếu.

Bốn hạng mục đề cương đòi mà repo **chưa có dòng nào**:

1. **BM25** — `grep -riE "bm25|rank_bm25|sparse"` trên `src/` cho 0 kết quả.
   `HybridRetriever` hiện là lai **text+ảnh**, KHÔNG phải lai **thưa+dày**.
2. **Hợp nhất thưa + dày** (RRF hoặc điểm chuẩn hoá), giữ nguyên rerank + cổng lọc.
3. **Caption deterministic vào prompt** — người dùng đã chọn phương án này. Hiện
   `src/app/api.py` dựng ngữ cảnh **chỉ từ `text_docs`**, `image_docs` chỉ ra
   gallery → ablation "multi-modal vs text-only" hiện sẽ ra chênh lệch **bằng 0
   theo cấu trúc**. Nguồn caption phải là pill/OCR deterministic, **không dùng
   Vintern** (D-47: bịa 4/12 crop).
4. **Bộ test 12 quyển** cân bằng Lý–Hoá–Sinh × 4 khối × 3 bộ sách × 3 mức độ khó.

---

## 5. CẤM (mỗi dòng đều có lý do đã đo)

1. Không upscale thân bài / crop lưu trữ. Ngoại lệ đã được phép: crop số trang,
   crop pill, ô số MỤC LỤC.
2. Không binarize/Otsu toàn trang (đo trên KNTT: conf 93,4 → 92,0).
3. Không đánh số lại / xoá file PNG nguồn. Bỏ trang khỏi index bằng `role`.
4. Không `index + 1` hay bất kỳ hằng số nào làm fallback số trang.
5. Không tự sửa chữ (OCR, dấu, caption). Bước tự động chỉ được **drop** hoặc **flag**.
6. Không lọc dòng OCR bằng ngưỡng confidence (D-38: xoá cả chữ thật).
7. Không `except` im lặng. Cô lập lỗi thì phải **in ra** và **gắn cờ**.
8. Không ghi đè một phép đo tốt bằng một lần đo hỏng (§0.4.3).
9. Không khôi phục thẳng `CtsstImageProcessor` (`git show 75b8377^`) — viết cho
   render 150 DPI của PDF cũ, chưa từng QA trên nguồn pixel này.
10. Không so số mới với báo cáo chuyên đề cũ như cùng điều kiện.
11. Không thêm `Co-Authored-By` / "Generated with" vào commit message.
12. Không chạy cả test suite khi đang lặp.

---

## 6. Phải HỎI, không được đoán

1. **G2 gold set cũ (24 trang KNTT) đã vô hiệu** vì số trang đổi. Làm lại trên
   corpus mới hay bỏ G2? Kèm cảnh báo: 23/24 file gold cũ **trùng từng từ** với
   `read_claude.txt`, nên cảnh báo `sua_tay*3 < may2` của cổng G2 **không bao giờ
   kích hoạt được nữa** — nếu làm lại thì phải sửa chỗ đó.
2. **Bộ test 100 câu cũ** — sinh lại toàn bộ trên 12 quyển (người dùng đã chọn
   "làm lại hết trên data mới"); xác nhận quota Gemini trước khi chạy (15 req/phút).
3. **Repo/URL của Frontend** và demo là quay video hay chạy GPU Colab.
4. **Push `master`?** Đang ahead nhiều commit, chưa push.

---

## 7. Trạng thái file khi bàn giao

- `CLAUDE.md` — RULE #0 + mục corpus đã viết lại theo số đo (chưa commit).
- `document/decision_log.html` — đã có **D-64** (đổi sang đồ án tốt nghiệp). Phần
  M0 (offset 12 quyển, 4 giả thuyết bị bác bỏ) **chưa được ghi** → ghi D-65.
- `document/specs/2026-08-22-12books-3publishers-etl-rebuild.md` — thiết kế tổng thể.
- `src/etl/book/fingerprint.py` — công cụ M0, phần số trang xong.
- `tests/book/test_fingerprint.py` — 18 test, pass.
- `database/fingerprints/*.json` — **11/12 đang HỎNG**, dựng lại theo §1.
- Chưa commit gì; `src/test/gold_ocr/*` còn sửa đổi từ lượt G2 (nay đã vô hiệu).
