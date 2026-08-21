# Prompt thực thi: chuyển ETL sang nguồn PNG (KNTT, 801 trang)

> Đây là prompt để một session Claude Code mới thực thi. Đọc hết trước khi viết dòng code
> đầu tiên. Mọi con số trong mục "Bằng chứng" đã ĐO trên corpus thật ngày 2026-08-20/21 —
> **không đo lại**, chỉ dùng. Cái gì chưa đo thì ghi rõ là chưa đo.
>
> Bắt buộc đọc kèm: `CLAUDE.md` (đặc biệt mục "Philosophy — 7 nguyên tắc") và
> `document/specs/2026-08-20-kntt-only-etl-rebuild-design.md`.

---

## 0. Bối cảnh: nguồn dữ liệu đã thay đổi hoàn toàn

`datasources/` **không còn file PDF nào**. Nguồn mới là PNG tải từ Bộ Giáo dục, một thư
mục mỗi quyển, một file mỗi trang:

```
datasources/SGK_KHTN_6_KNTT/page_001.png … page_196.png   (196 file)
datasources/SGK_KHTN_7_KNTT/page_001.png … page_180.png   (180 file)
datasources/SGK_KHTN_8_KNTT/page_001.png … page_197.png   (197 file)
datasources/SGK_KHTN_9_KNTT/page_001.png … page_228.png   (228 file)
```

**Tổng 801 trang.** Cả 4 quyển liền mạch, không lỗ (đã verify sau khi user tải bù 19 trang
thiếu của sách 9). Không có file trùng nội dung (md5 toàn bộ). Người dùng đã chủ động xoá
1 bìa sau + 1 trang đệm mỗi quyển — nên 801 (không phải 809 như CLAUDE.md đang ghi) là con
số ĐÚNG và đầy đủ.

### Quy tắc trang — đã kiểm chứng, dùng làm bất biến

**`printed_page == (số trong tên file) − 1`.** `page_001.png` là trang in 0 (bìa trước).

Đây không phải giả định: chạy `read_page_number_candidates` + `fit_offset` của repo trên
782 file (trước khi bù) cho `offset = 0` ở cả 4 quyển, đồng thuận 96,3–98,9%; 19 file bù
của sách 9 verify riêng, 19/19 khớp. Parity **chẵn → lề trái, lẻ → lề phải** không có
ngoại lệ nào trong toàn bộ candidate hợp lệ.

Hệ quả quan trọng: **tên file do nguồn đánh theo chỉ số trang thật của họ, không theo thứ
tự tải.** Vì vậy neo mọi thứ vào *số trong tên file*, tuyệt đối không vào *thứ tự
enumerate directory*. Nếu về sau thiếu/bù trang, mọi thứ vẫn khớp.

---

## 1. Bằng chứng đã đo (KHÔNG đo lại — dùng luôn)

### 1.1 Thuộc tính ảnh
- **1094×1536 px mọi trang**, trừ `page_001.png` của cả 4 quyển là **1093×1536** (cover
  hụt 1 px). Code không được giả định chiều rộng đồng nhất.
- Mode **RGBA**, alpha = 255 ở mọi pixel (12 trang mẫu) → alpha là byte rác, drop an toàn.
  `cv2.imread(..., IMREAD_COLOR)` xử lý đúng; đường PIL phải `.convert('RGB')` tường minh.
- PNG **không có metadata DPI**.
- **Không cao hơn nguồn PDF cũ về pixel**: 1094×1536 đúng bằng JPEG nhúng trong PDF cũ.
  Cái được là lossless + bỏ hẳn bước render. Cái không được: không thêm pixel nào.
  "132 DPI" trong CLAUDE.md là giả định khổ A4; theo khổ SGK thật (19×26,5 cm) cùng số
  pixel đó là ~147 DPI. Dù sao **không đổi**, và **không có nguồn tốt hơn** (user xác nhận).
- Watermark "KẾT NỐI TRI THỨC VỚI CUỘC SỐNG" **vẫn in chìm mọi trang**.
- Chiều cao box chữ thân bài: **19 px** (p10 = 16, p90 = 20).

### 1.2 OCR text — đo được gì
| Điều đo | Kết quả |
|---|---|
| CER thân bài, gold do người đọc từ ảnh | **0,0048** (1 lỗi / 208 ký tự), lỗi là **dấu** (`chế`→`ché`) |
| CER ở scale 1× / 2× / 3× / 4× | **không đổi** — phóng to thân bài vô ích |
| mean word-conf, 8 trang, RGB gốc | **93,4**; chỉ 2,0% từ conf < 60 |
| Otsu binarize | **tệ hơn**: conf 92,0; 3,5% từ conf < 60 → **cấm dùng** |
| grayscale | 93,1 (không hơn RGB) |
| OCR vùng: mặc định (psm 3) vs `--psm 6` | 6293 → **6535 token (+3,8%)**, cùng thời gian |
| OCR vùng: `--psm 6` + upscale 2× | +0,3% token, **+70% thời gian** → không đáng |
| token lẫn chữ-số (kiểu `kh6ng`, `1a`) | 0,10–0,15% |
| `fix_diacritics` sửa được | **3 token / ~6500** |
| Thời gian | OCR vùng ~1,26 s/trang + số trang ~0,4 s/trang → **~26 phút / 801 trang, 1 luồng CPU** |

### 1.3 Chỗ đau thật: MẤT CHỮ do phân vùng, không phải sai ký tự
OCR cả trang bằng psm 3 (mặc định) trên `SGK_KHTN_6/page_010.png`: 13 dòng / 134 từ, so
với psm 11 = 150 từ, psm 6 = 194 từ. Cái bị mất **không ngẫu nhiên**:
- mất sạch câu hỏi trong hộp vàng ("Dựa vào Hình 1.2, hãy so sánh…");
- mất sạch nhãn hộp "Thông tin liên lạc" / "Sản xuất" / "Giao thông vận tải" / "Hiện nay";
- **mất nhãn pill "Hình 1.2" / "Hình 1.3"** — tức mất chính cái neo mà thiết kế figure dựa vào;
- mất số trang "9";
- tệ nhất: sidebar phải ra `"dụng khoa học tự / trong Hình 1.3 / con người và / môi trường
  sống."` — **câu bị cắt đầu nhưng đọc vẫn trôi**. Đúng loại fallback im lặng mà nguyên tắc
  5 cấm: chunk này vào index thì học sinh được trích một câu thiếu nửa mà không ai biết.

Đo rộng 6 trang: psm 3 mất 4% số từ so với psm 11, nhưng lệch cực mạnh — **13% trên trang
nhiều hộp/hình, 2–3% trên trang đặc chữ.**

### 1.4 `segment_page` recall thấp — đây là điểm yếu số một
40 trang mẫu: **2,30 vùng/trang** (min 1, max 5) = 40 body + 43 info_box + 9 sidebar.
Riêng `page_010` đã có ≥4 hộp màu. OCR theo vùng chỉ tốt bằng segmenter.

### 1.5 `preprocess_page` đang PHÁ dữ liệu, không có lý do tồn tại
Nó xoá trắng 6% lề trái vì "KNTT left-margin personal stamp". Median pixel của dải lề trái
12% trên **100 trang/quyển**: tối nhất 181–209, **0% pixel < 200** → **không có con dấu cố
định nào trên nguồn này**. Trong khi 6% đó *có* nội dung thật: viền màu info-box, icon, và
**số trang lề trái của mọi trang chẵn** (centre x ≈ 0,079).

### 1.6 Đọc số trang: nguyên nhân gốc + cách sửa, đã đo toàn corpus
Crop góc ở phân giải gốc chỉ 153×115 px nên tesseract cắt mất chữ số:
`"11" → "1"` (conf 83), `"110" → "10"` (conf 45, bị MIN_CONF loại). Phóng crop góc **3×**:
`→ "11"` (conf 95), `→ "110"` (conf 62).

| | baseline | corner 3× |
|---|---|---|
| Sách 6 | 98,98% · thiếu {1,2} | 98,98% · thiếu {1,2} |
| Sách 7 | 97,78% · thiếu {1,2,12,111} | **98,89%** · thiếu {1,2} |
| Sách 8 | 98,48% · thiếu {1,2,12} | **98,98%** · thiếu {1,2} |
| Sách 9 | 98,56% · thiếu {1,2,12} | 98,56% · thiếu {1,2,**165**} |

**3× KHÔNG thắng tuyệt đối**: `page_165` sách 9 đọc "164" (conf 96) ở 1× nhưng **không đọc
được gì** ở 3×. → Cách đúng là **HỢP cả hai lần đọc (1× và 3×)** rồi khử trùng theo
`(value, side)` như code đang làm. Vì mọi biến thể đều cho offset 0, hợp hai tập candidate
là superset → mọi trang mà *một* biến thể xác nhận được thì hợp cũng xác nhận được. Suy ra:
**thiếu đúng {1,2} ở cả 4 quyển → 793/793 trang có in số đều `ocr_confirmed`.** Hai trang
bìa mỗi quyển (`page_001`, `page_002` = trang in 0 và 1) **thật sự không in số** → phải là
`model_inferred`, không phải lỗi.

Thêm một defect nhỏ đã xác định: `"110°"` bị `^\d{1,3}$` loại oan ở đường sparse.

### 1.7 Môi trường
- `torch.cuda.is_available() == False` ở env này (dù `.env` đặt `USE_GPU=true`). OCR không
  phải cổ chai; **embedding bge-m3 trên CPU mới là chỗ tốn**.
- Chưa cài `paddleocr` / `easyocr` / `vietocr`. Chỉ có `rapidocr_onnxruntime` (model CN/EN,
  **không dùng được cho dấu tiếng Việt**).
- Tesseract 5.5.0, có `vie`. Đường dẫn qua `TESSERACT_CMD`.

---

## 2. CẤM (mỗi dòng đều có bằng chứng ở trên)

1. **Không binarize / Otsu / adaptive threshold.** Đo được là tệ hơn (1.2).
2. **Không upscale ảnh thân bài.** CER không đổi, tốn 70% thời gian (1.2). *Ngoại lệ duy
   nhất*: crop góc số trang, nơi 3× là quyết định (1.6).
3. **Không đánh số lại file PNG.** Toàn bộ page identity neo vào số trong tên file (0).
4. **Không xoá trang nguồn khỏi `datasources/`** (kể cả bìa). Muốn bỏ bìa khỏi index thì
   gắn `role="cover"` trong manifest rồi skip ở bước chunk — reversible.
5. **Không dùng `index + 1` (hay bất kỳ hằng số nào) làm fallback số trang.** Số trang lấy
   từ `BookManifest`; không có manifest thì **fail loudly**, không đoán.
6. **Không để `fix_diacritics` ghi lại chữ.** Nguyên tắc 5: bước sửa tự động phải là
   drop-only hoặc flag-for-review.
7. **Không chạy cả test suite khi đang lặp.** Chỉ test nhắm đúng file vừa sửa.
8. **Không thêm `Co-Authored-By` / "Generated with" vào commit message.**

---

## 3. Việc phải làm, theo thứ tự

### Task 0 — Đồng bộ tài liệu sự thật (làm trước, rẻ, chống nhầm cho chính bạn)
- `CLAUDE.md`: sửa mục corpus — nguồn giờ là **4 thư mục PNG, 801 trang**, không còn PDF;
  1094×1536 lossless; `RENDER_DPI` sắp thành config chết; bỏ câu "809 pages" và
  "producer jsPDF"; ghi rõ `printed_page == filenum − 1`.
- `document/decision_log.html`: thêm decision cho việc đổi nguồn PNG (D-29…) và cho từng
  quyết định kỹ thuật ở Task 1–5 bên dưới.
- **Chấp nhận: chỉ sửa mô tả sự thật đã đo, không hứa hẹn thiết kế chưa làm.**

### Task 1 — `PageSource` abstraction (thay đổi cấu trúc chính)
Toàn bộ đường ETL đang buộc vào `fitz`. Tạo abstraction nhỏ nhất đủ dùng:

```python
class PageSource(Protocol):
    book_id: str
    def page_numbers(self) -> list[int]: ...      # SỐ TRONG TÊN FILE, tăng dần
    def load(self, page_number: int) -> np.ndarray: ...   # BGR uint8, đã drop alpha
    def content_hash(self, page_number: int) -> str: ...  # hash TỪNG TRANG
```

Hai hiện thực: `PngFolderPageSource` (mới, dùng cho corpus hiện tại) và `PdfPageSource`
(giữ `fitz` cho đường upload ở `src/app/api.py:233`).

Điểm phải sửa:
- `src/etl/layout/loader.py` — `_render_page`, `load_page`, `load_pdf`
- `src/etl/book/manifest.py` — `_render`, `build_manifest` (callable đã DI sẵn nên nhẹ)
- `src/etl/book/toc.py` — `read_toc_lines(pdf_path)` → nhận source.
  **`TOC_PAGE_INDICES = (4, 5)` VẪN ĐÚNG** → `page_005.png` / `page_006.png`; đã xác nhận
  là MỤC LỤC ở cả sách 6 và sách 9.
- `main.py` — `_pdf_page_count`, `_index_pdf_pages`, `_should_skip_file`
- `src/etl/image_processor.py:3753` — đường crop hình
- `get_pdf_variant("SGK_KHTN_6_KNTT")` trả `"kntt"` do tên chứa "KNTT" → **không cần sửa**,
  nhưng thêm test khoá hành vi này lại kẻo vô tình đổi tên thư mục.
- `src/rag/citations.py:35` strip `.pdf` → xem lại nhãn nguồn cho hiển thị trích dẫn.

**Checkpoint (quan trọng):** hash hiện tính trên 1 file PDF; nay phải **hash từng file
PNG**. Đây đúng tinh thần "khoá theo content hash" hơn hẳn — tải bù 19 trang chỉ
re-process 19 trang. Đồng thời **thêm `TEXT_EXTRACTION_VERSION`** vào khoá checkpoint (spec
đã yêu cầu; hôm nay chỉ ảnh có version gate nên đổi logic OCR không ép re-OCR được).

**Nghiệm thu:** `python main.py --build-manifests` chạy được trên cả 4 thư mục PNG;
`--text-only` index được ít nhất 1 quyển; chạy lại lần 2 skip toàn bộ (checkpoint hoạt động);
sửa `TEXT_EXTRACTION_VERSION` → chạy lại re-process toàn bộ.

### Task 2 — Xoá `preprocess_page` cho kntt
Bỏ hẳn dòng wipe 6% lề trái (bằng chứng 1.5). Nếu sau khi bỏ mà hàm chỉ còn `return
image.copy()` thì **xoá luôn cả hàm và call site** (nguyên tắc 7), đừng để lại no-op.
**Nghiệm thu:** `tests/layout/test_preprocess.py` (nếu có) cập nhật theo; số vùng
`segment_page` tìm được trên 40 trang mẫu **không giảm** so với 2,30/trang.

### Task 3 — Sửa OCR vùng: chỉ định psm
`src/etl/layout/text_extract.py::_ocr` đang gọi `image_to_string(img, lang="vie")` → psm 3
mặc định, sai cho crop nhỏ. Đổi thành:
- `--psm 6` cho vùng thường;
- `--psm 7` cho crop cao < 60 px (dòng đơn, caption);
- **không upscale.**

**Nghiệm thu:** trên 14 trang mẫu, số token ≥ 6535 (baseline psm 3 là 6293) và thời gian
không tăng quá 10%.

### Task 4 — Đọc số trang: hợp 1× + 3×, và nới regex
Trong `src/etl/book/page_number_ocr.py`:
- `_read_corner` chạy **hai lần: scale 1 và scale 3**, gộp vào tập candidate (dedup theo
  `(value, side)` giữ conf cao hơn — cơ chế dedup đã có sẵn).
- Đường sparse: thay `^\d{1,3}$` bằng trích dãy số trong token (để `"110°"` không bị loại),
  giữ nguyên `MIN_CONF = 50` và **không nới `outer`**. Parity + majority offset là lưới an
  toàn; nếu `wrong_votes` tăng vọt thì rollback.

**Nghiệm thu (đây là gate G1, phải đạt):** chạy trên cả 801 trang →
`confirm_rate` mỗi quyển ≥ 98,9%, và tập trang không xác nhận **đúng bằng
`{page_001, page_002}` của mỗi quyển** — không nhiều hơn. Ghi số thật vào decision log.

### Task 5 — `build_page_map` phải chịu được lỗ trang, và đánh dấu bìa
Hiện `build_page_map(n_pages, ...)` duyệt `range(n_pages)` → **giả định trang liên tục**.
Corpus lúc này liền mạch, nhưng giả định đó là bug chờ xảy ra (đã từng có lỗ 19 trang ở
sách 9). Đổi sang duyệt **tập số file thật** từ `PageSource.page_numbers()`, và:
- nếu phát hiện lỗ trong dãy → **flag ra** trong manifest (`flags`), **không lấp im lặng**;
- `page_001`/`page_002` (trang in 0, 1) gắn `role="cover"` → skip ở bước chunk. **Đây là
  cách bỏ bìa khỏi index; KHÔNG xoá file** (xem CẤM #4).

**Nghiệm thu:** test tổng hợp với một dãy có lỗ → manifest có flag, không có record bịa cho
trang không tồn tại. Test với dãy đủ → không flag.

### Task 6 — `RENDER_DPI` thành config chết → xoá
Không còn bước render. Xoá khỏi `src/config.py`, `.env.example`, và mọi call site. Để lại
là mời người sau tưởng còn tinh chỉnh được.

### Task 7 — Thay `diacritic.py` bằng cơ chế FLAG (không rewrite)
Bằng chứng: sửa được 3/6500 token, và nó *ghi lại* chữ → vi phạm nguyên tắc 5. Thay bằng
kiểm tra âm tiết tiếng Việt hợp lệ, **chỉ gắn `needs_review` trên chunk, không sửa ký tự
nào**. Giữ allowlist công thức hoá học / thuật ngữ Anh như bản cũ để không flag nhiễu.
`DIACRITIC_FIX_ENABLED` đổi nghĩa (hoặc đổi tên) cho khớp hành vi mới.

### Task 8 — Điểm yếu số một: recall của `segment_page` (việc lớn nhất, làm sau cùng)
2,30 vùng/trang là quá thấp (1.4). Đây là nơi mất dữ liệu thật, không phải engine OCR.
**Phải QA trên trang thật, không chỉ unit test trên fixture tổng hợp** — dùng
`src/test/qa_layout.py` (cần cập nhật cho nguồn PNG) và trang chuẩn
`SGK_KHTN_6_KNTT/page_010.png`, nơi mắt thường đếm được ≥4 hộp màu.
**Nghiệm thu:** trên `page_010`, segmenter tìm được cả hộp câu hỏi vàng, 3 hộp so sánh
(cam/xanh/tím) và sidebar xanh phải; và text các vùng đó **có mặt đầy đủ** trong chunk
output — đặc biệt câu sidebar phải **không bị cắt đầu** (xem 1.3).

---

## 4. Không làm trong session này (ưu tiên thấp hơn, có lý do)
- **Dual-engine OCR consensus.** Ở CER 0,0048, chunk 400 ký tự mang ~2 ký tự sai, gần như
  luôn là dấu — vô hại cho retrieval, có hại cho câu trích. Nhưng **mất trọn câu (1.3) tệ
  hơn sai một dấu**, nên Task 8 phải xong trước. Muốn làm thì phải cài PaddleOCR VN và
  bake-off trên gold set do người xác nhận, không chọn bằng trực giác.
- **Regenerate eval testsets** cho 4 quyển (bản cũ dựng cho 12 quyển) — việc riêng, làm sau
  khi đường text ổn định.

## 5. Câu hỏi mở / chưa verify (đừng khẳng định là đã xong)
- Chưa chạy end-to-end đường text trên nguồn PNG (chưa có adapter) → Task 1.
- Chưa đo lại phía crop hình (`image_processor`) trên nguồn PNG. Anchor caption pill trông
  còn nguyên trên `page_010` nhưng **chưa đo**.
- Gold set CER hiện chỉ 4 vùng trên 1 trang + confidence trên 8 trang. Muốn kết luận mạnh
  về chất lượng OCR toàn corpus thì cần gold set rộng hơn do người xác nhận.
- `IMAGE_EXTRACTION_VERSION` hiện `v16_layout_reconcile`; đổi nguồn ảnh **bắt buộc phải
  bump** nếu logic crop thay đổi — kiểm tra và ghi quyết định.

## 6. Quy tắc làm việc (nhắc lại từ CLAUDE.md)
- Phản biện chính code mình vừa viết trước khi nói "xong": off-by-one, lệch hệ 0-based vs
  1-based, cache cũ, fallback âm thầm.
- Test nhỏ, nhắm đúng file vừa sửa. Không chạy cả suite khi đang lặp.
- Mỗi quyết định → `document/decision_log.html`. Spec/plan → `document/specs/`.
- Báo cáo thì nói thẳng cái gì đã verify (kèm output thật), cái gì chưa.
