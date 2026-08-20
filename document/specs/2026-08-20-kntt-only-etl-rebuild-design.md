# Thiết kế lại ETL (text + hình) cho corpus KNTT 2026 — 4 quyển, một nhà xuất bản

- **Ngày:** 2026-08-20
- **Trạng thái:** design, chờ review
- **Thay thế phần nào:** phần *corpus assumptions* và *per-variant image ETL* của
  `2026-08-18-rag-etl-retrieval-redesign-design.md` và `2026-08-19-m3-figure-extraction-design.md`.
  Các quyết định về bge-m3 / bge-reranker-v2-m3 / checkpoint-theo-content-hash **giữ nguyên**.
- **Bối cảnh:** Bộ GD thống nhất chỉ dùng **Kết Nối Tri Thức**; CD và CTST bị bãi bỏ.
  Corpus mới: `datasources/SGK-KHTN-Lop-{6,7,8,9}.pdf`.

---

## 1. Sự thật đo được về corpus (không phải giả định)

| Hạng mục | Giá trị đo | Cách đo |
|---|---|---|
| Số quyển / số trang | 4 / **809** (198 + 182 + 199 + 230) | `fitz.page_count` |
| Text layer | **0/809 trang** có text (`avg_chars/page = 0`) | `page.get_text("text")` toàn bộ |
| Producer | `jsPDF 2.5.1`, PDF 1.3, tạo 2026-06-26, 0 bookmark | `doc.metadata`, `get_toc()` |
| Khổ trang | A4 595.28x841.89 pt, rotation 0, **đồng nhất 100%** | `page.rect` toàn bộ |
| Ảnh trang | 1 JPEG/trang, 1094x1536 px = **132 DPI thực** | `extract_image` toàn bộ |
| Ngoại lệ tile | L7: 3 trang, L8: 36 trang ghép từ 3 tile (cùng 132 DPI) | `get_images` + `get_image_bbox` |
| Seam của tile | Không thấy đường ghép khi render 300 DPI xuyên qua y=491pt | crop QA bằng mắt |
| Watermark | "KẾT NỐI TRI THỨC VỚI CUỘC SỐNG" + logo lá, in chìm **mọi trang** | quan sát + nhiễu OCR |
| MỤC LỤC | idx **4–5** ở cả 4 quyển | tìm chuỗi trên idx 0–7 |
| Bìa | idx 0–1 (bìa + lót), idx cuối (bìa sau, barcode/giá) | quan sát |

**Kết luận quan trọng:** đây **không phải** PDF bản in có text — là flipbook web xuất
lại thành PDF. **OCR vẫn bắt buộc.** So với corpus cũ (extract từ git `c327e11`): sạch
hơn về hình học (không lệch, không bóng, không stamp lề) nhưng **DPI thấp hơn**
(132 vs 138–150). Người dùng đã xác nhận **không có bản nào tốt hơn** → 132 DPI là
**ràng buộc cứng**, không phải tham số tối ưu được.

Hai pain point cũ đã tự biến mất: KNTT9 hết dạng landscape 2-up spread; KNTT8 hết là
bản giáo viên.

### 1.1 Định danh trang — đã verify trên toàn bộ 809 trang

Mô hình: đọc token chữ số trong dải đáy 12%, `psm 11`, conf >= 50, chỉ nhận token nằm
trong 22% lề ngoài; rồi lấy **mode của (value - pdf_index)** trên toàn quyển.

| Quyển | offset thắng | phiếu | đối thủ gần nhất | parity (index%2 → lề) |
|---|---|---|---|---|
| L6 | **0** | 180/188 | 1 phiếu | chẵn→trái 90, lẻ→phải 90 |
| L7 | **0** | 149/151 | 1 phiếu | chẵn→trái 68, lẻ→phải 81 |
| L8 | **0** | 167/177 | 2 phiếu | chẵn→trái 82, lẻ→phải 85 |
| L9 | **0** | 199/207 | 1 phiếu | chẵn→trái 94, lẻ→phải 105 |

→ **`printed_page == pdf_index` (0-based), cả 4 quyển.** Mọi offset khác chỉ có 1–2
phiếu = nhiễu. Quy tắc parity **không có một ngoại lệ nào** trong 695 lần đọc.

Kiểm chứng độc lập thứ hai: MỤC LỤC L6 ghi "Bài 6. Đo khối lượng — 20", và idx 20
đúng là trang mở đầu Bài 6.

13 trang "unconfirmed" đã soi bằng mắt (L8 119/175/76, L9 119/164, L7 71/27, L6
41/43/56, L7 34, L8 56, L9 64): **tất cả đều in đúng số = index**. Nguyên nhân là OCR
sparse-mode bỏ sót, **không phải sách thiếu số trang**.

Lỗi hiện có trong code: `detect_printed_page_number(..., pdf_index=index+1)` → fallback
lệch **+1 trang**. Đây là loại sai lặng lẽ nguy hiểm nhất với mục tiêu "đúng trang".

### 1.2 Chất lượng OCR hiện tại — đo được

Tesseract `vie`, cùng một trang (L6 tr.20), 4 mức render: **300 DPI tốt nhất**; 132 và
200 kém hơn; 400 xấu đi do upsample sinh nhiễu. `RENDER_DPI` đang là **220** — không
phải mức tối ưu đo được.

Lỗi mang tính hệ thống, **tập trung vào dấu của từ nội dung**:
`đầy→đây`, `tầm→tằm`, `giống→giỗng`, `để→đề/đỗ`, `khối→khôi`, `số→sô`,
`đồng hồ→đồng hò`, `y tế→y té`, `0,001→0.001`. Khung **in nghiêng** tệ nhất:
3 lỗi dấu / 24 từ.

Throughput trên PC dev (i7-10700, 8C/16T): render 0.23 s + OCR 1.26 s = **1.5 s/trang**
→ 809 trang **20 phút 1-thread, ~3–4 phút với 8 worker**. Nghĩa là chạy **2 engine đối
chiếu vẫn rẻ** (~8 phút/lần re-ETL).

Engine khác đã thử tại chỗ:
- `rapidocr-onnxruntime`: rec model **xoá sạch dấu tiếng Việt** → không dùng được để
  đọc; nhưng detector tốt (36 line-box/trang, 6.5 s CPU).
- `Vintern-1B-v2` (đang dùng caption): **không chạy được trên CPU** (remote code
  hardcode `.cuda()`), và load code từ HF cache chứ không từ `models/`.

### 1.3 MỤC LỤC cũng KHÔNG đáng tin

Parse TOC bằng `psm 4` trên 4 quyển: thiếu bài (20, 25, 33, 41…), sai số trang
("Bài 24 | tr. 90" trong khi Bài 23 đã ở tr. 95), sai số bài ("Bài 3" thay vì 31,
"Bài 4" thay vì 41), có quyển `psm 4` trả về 0 dòng.

→ **Không nguồn đơn lẻ nào đủ tin.** Chỉ có *đối chiếu chéo + mô hình toàn cục* là
đáng tin. Đây là nguyên lý trung tâm của thiết kế này.

### 1.4 Pipeline hiện tại vỡ ở đâu (chạy thật, L6 idx 20)

1. `get_pdf_variant("SGK-KHTN-Lop-6.pdf")` → **`'cd'`** (tên file mới không chứa
   `kntt`) → cả 4 quyển bị đẩy sang processor Cánh Diều.
2. `preprocess_page` nhánh `kntt` **xoá trắng 6% lề trái** (tẩy stamp của scan cũ) —
   sách mới không có stamp, mà số trang chẵn nằm ở ~6.3% chiều rộng → sẽ xoá mất số trang.
3. Taxonomy vùng sai: banner "Bài 6 – ĐO KHỐI LƯỢNG" → `info_box`; dải chú thích hình
   → `info_box`; khung "MỤC TIÊU" (nền trắng) bị hút vào `body`. **5/7 chunk sai nhãn.**
4. Chữ trong pill **`Hình 6.1` bị bỏ hẳn** → mất liên kết hình ↔ chú thích.
5. Chunk body bị nhiễm watermark (`"Km. ..a"`, `"hy ớnớng mm mrsx…"`) và **lọt số
   trang "20"** vào nội dung.
6. Không có metadata Bài/Chương → citation chỉ ra được "tr. 20".
7. Text ETL **không có version gate** (chỉ hình có `IMAGE_EXTRACTION_VERSION`) → sửa
   logic OCR xong, checkpoint vẫn skip, **không có cách buộc re-OCR**.

---

## 2. Nguyên tắc thiết kế (kế thừa Philosophy trong CLAUDE.md)

1. Mỗi chunk mang **provenance + confidence**, không chỉ nội dung.
2. Hai nguồn độc lập lệch nhau → **flag**, không chọn bừa, không nội suy.
3. Bước tự động chỉ được **drop** hoặc **flag**, không được **thêm** dữ liệu.
4. Mọi ngưỡng/tham số ảnh hưởng độ chính xác phải có phép đo trước/sau.
5. Phạm vi hẹp lại (3 NXB → 1) ⇒ **xoá** heuristic đã chết, không giữ "cho chắc".

---

## 3. Kiến trúc

### 3.1 Cây module (mới / viết lại)

```
src/etl/book/
  manifest.py        # BookManifest: page map + bài spine; build 1 lần, lưu JSON, người review được
  page_number.py     # đọc token theo hình học + parity + mô hình offset toàn cục
  toc.py             # parse MỤC LỤC (idx 4–5) -> HYPOTHESIS, không phải sự thật
  bai_spine.py       # detect banner "Bài N" trong trang + reconcile với TOC + sửa theo đơn điệu
src/etl/layout/
  blocks.py          # word/line box, phát hiện cột, reading order (projection profile)
  segmenter.py       # VIẾT LẠI: vùng theo design system KNTT (màu khung + pill tiêu đề + icon)
  taxonomy.py        # lexicon nhãn khung; khung lạ -> box_unlabeled (thà thiếu hơn sai)
src/etl/ocr/
  engine.py          # protocol OcrEngine; tesseract.py; paddle.py
  consensus.py       # đối chiếu 2 engine theo DÒNG -> nhãn agreement + needs_review
  postfix.py         # sửa dấu theo từ điển, CHỈ khi không mơ hồ (gộp diacritic.py cũ)
src/etl/figures/
  pill.py            # detect pill chú thích (màu + hình học) -> "Hình N.M"
  crop.py            # suy ra thân hình từ pill + biên khung + whitespace (drop-only)
  completeness.py    # audit 1..k liên tục theo từng Bài
src/etl/chunker.py   # region -> chunk có nhãn + heading path
```

**Xoá** (phạm vi đã hẹp lại): `get_pdf_variant`, `make_image_processor`,
`CtsstImageProcessor`, `KnttImageProcessor` và phần lớn heuristic trong
`image_processor.py` (4 926 dòng); nhánh xoá stamp trong `preprocess.py`;
`_VARIANT_PARAMS`; `citations._PUBLISHER`; test variant tương ứng.
Giữ lại và *di trú* sang `figures/`: logic dựng band, projection whitespace, nhãn
sub-figure a)/b)/c) — những phần này vẫn đúng và đã qua QA.

### 3.2 BookManifest — nguồn sự thật duy nhất về trang & bài

Build một lần cho mỗi quyển, lưu `database/manifests/<book_id>.json`, commit vào repo,
người đọc được bằng mắt:

```json
{ "book_id": "KHTN6-KNTT", "pdf_hash": "...", "n_pages": 198,
  "page_offset": 0, "offset_votes": [180, 188],
  "pages": [ {"pdf_index": 20, "printed_page": 20,
              "source": "ocr_confirmed", "side": "L", "conf": 91.2,
              "chuong": "I", "bai_so": 6, "role": "content"} ],
  "bai": [ {"bai_so": 6, "title": "Đo khối lượng", "start": 20, "end": 21,
            "title_source": "banner+toc"} ],
  "flags": [ {"pdf_index": 41, "kind": "page_number_not_read"} ] }
```

`pdf_hash` dùng đúng `processing_status.compute_file_hash` (MD5) để khoá manifest và
khoá checkpoint là **một** giá trị, không phải hai hệ băm khác nhau.

Thuật toán số trang:
1. Dải đáy 12%, `image_to_data psm 11`, giữ token `^\d{1,3}$` conf >= 50 trong 22% lề ngoài.
2. Áp **parity trên GIÁ TRỊ đọc được, không trên index**: candidate giá trị chẵn phải
   nằm ở lề trái, giá trị lẻ phải ở lề phải (đo: 695/695 đúng). Ràng buộc theo giá trị
   nên **không vòng tròn** — không cần biết trước số trang mới lọc được candidate.
3. `offset = mode(value - index)`; **yêu cầu >= 80% phiếu đồng thuận**, nếu không → dừng
   quyển đó và báo lỗi to (đo được 96–99% nên ngưỡng này an toàn).
4. Trang có token khớp `index + offset` → `ocr_confirmed`; ngược lại → `model_inferred`
   + ghi flag. Vẫn index được (song ánh đã chứng minh), nhưng **provenance khác nhau
   được lưu lại**, không bị xoá dấu vết.
5. Fallback tuyệt đối là `index + offset`, **không bao giờ là `index + 1`**.

Thuật toán spine Bài:
1. TOC (idx 4–5) → giả thuyết `(bai_so, title, start_page)`.
2. Detect banner "Bài N" trong từng trang: badge bo tròn + banner màu ở đỉnh trang;
   đọc chữ số trên crop đảo màu (tương phản cao).
3. Ràng buộc toàn cục: `bai_so` phải **tăng ngặt** và `start_page` phải **tăng ngặt**.
   Lỗi lẻ được sửa bằng láng giềng (ví dụ "Bài 3" nằm giữa 30 và 32 → 31) **và ghi flag**.
4. Banner thắng TOC khi lệch (banner là trang thật). Lệch nào không giải được → flag,
   không đoán.
5. Mỗi trang nội dung thừa hưởng `(chuong, bai_so, bai_title)` theo khoảng trang.

### 3.3 OCR consensus (hướng B đã chốt)

Mỗi **dòng** trong mỗi region được đọc bởi 2 engine: engine A = Tesseract `vie`;
engine B = **ứng viên chính PaddleOCR rec-VN (CPU, 16 thread), chốt bằng số ở M1**
(xem §7.1 — chưa đo thì chưa được coi là đã chốt). Kiến trúc consensus dưới đây
không phụ thuộc vào engine B là ai. Phân loại:

| So sánh | Nhãn | Xử lý |
|---|---|---|
| Trùng khớp tuyệt đối | `agree` | nhận, conf cao |
| Chỉ khác **dấu** (trùng sau khi bỏ dấu) | `conflict_diacritic` | **vùng nguy hiểm nhất**: chọn theo conf + kiểm từ điển tiếng Việt; `needs_review=true`; lưu cả 2 phương án |
| Khác cả chữ | `conflict_text` | `needs_review=true`, lưu cả 2, ưu tiên engine thắng bake-off |
| Chỉ 1 engine đọc được | `single_engine` | nhận, hạ conf |

- Chunk-level: `agreement_ratio` = % dòng `agree` → dùng làm confidence của chunk.
- Book-level: báo cáo "% văn bản hai engine đồng thuận" — con số này là thước đo trung
  thực duy nhất về việc "text ETL có đúng không".
- `postfix.py` chỉ sửa dấu khi **kết quả là từ tiếng Việt có thật và duy nhất**; không
  bao giờ để LM viết lại tự do (đó là bịa).

### 3.4 Taxonomy vùng theo design system KNTT

Nhận diện khung bằng (a) màu nền uniform-tint (giữ bộ lọc HSV hiện có — vẫn cần vì
watermark), (b) **lexicon pill tiêu đề**, (c) icon glyph, (d) hình học.

`bai_banner`, `muc_tieu`, `mo_dau`, `hoat_dong`, `thi_nghiem`, `cau_hoi`, `luyen_tap`,
`van_dung`, `em_da_hoc`, `em_co_the`, `em_co_biet`, `figure_caption`, `table`,
`footnote`, `page_number`, `body`.

Khung không khớp lexicon nào → **`box_unlabeled`**, không gán nhãn gần đúng.
`page_number` là một region **riêng và bị loại khỏi text** — trực tiếp sửa lỗi "số 20
lọt vào chunk body".

### 3.5 Hình

- **Anchor = pill chú thích**: chữ nhật bo góc, nền màu đặc, tỉ lệ ~2.5–4:1, chứa chữ
  trắng đậm khớp `Hình\s+\d+\.\d+` (đọc trên crop đảo màu). Bền hơn nhiều so với OCR
  chữ xám — cũng áp dụng cho `Bảng\s+\d+\.\d+`.
- **Thân hình** suy ra từ pill lên trên, chặn bởi dòng text/biên khung/cột, rồi trim
  whitespace. Bước reconcile với segmenter giữ nguyên tinh thần **drop-only**.
- **Chứng minh tính "đủ"**: số hình đánh theo Bài (đo: Hình 6.1 thuộc Bài 6, Hình 9.1
  thuộc Bài 9, Hình 3.4 thuộc Bài 3). Với mỗi Bài, tập số hình phải liên tục `1..k`;
  **hở số = thiếu hình** → QA fail, có danh sách cụ thể phải đi soi.
- Sub-figure a)/b)/c) trong cùng một Hình: 1 crop + danh sách nhãn con.
- **Trần độ phân giải**: crop ở 132 DPI native (chỉ upscale khi OCR, không upscale khi
  lưu). Hình 1/4 trang ~ 550x400 px — đây là trần cứng, phải nói thẳng, không "cải
  thiện" bằng nội suy (nội suy = bịa pixel).
- Caption VLM (Vintern) trở thành **làm giàu tuỳ chọn**, không phải nguồn sự thật, vì
  caption thật đã đọc được từ pill + dòng chú thích.

### 3.6 Metadata mỗi chunk

```
source, book_id, grade, pdf_index, printed_page, page_number_source,
chuong, bai_so, bai_title, heading_path, region_type, chunk_index,
ocr_agreement, ocr_conf, needs_review, text_extraction_version
```

`heading_path` (ví dụ `"Bài 6 › II – Dụng cụ đo khối lượng"`) được **prefix vào text
đem đi embed** — đòn recall đã biết, và cũng làm citation giàu hơn:
`"SGK KHTN 6, Bài 6 Đo khối lượng, tr. 20 — mục Câu hỏi"`.

### 3.7 Checkpoint

Thêm **`TEXT_EXTRACTION_VERSION`** vào khoá checkpoint (hiện chỉ hình có version gate —
lỗ hổng thật). Khoá: text = `(content_hash, text_version)`, hình =
`(content_hash, image_version)`, manifest = `content_hash`. Giữ nguyên nguyên tắc
`processing_status` là nguồn sự thật duy nhất; `processed_*.txt` chỉ là log.

---

## 4. Cổng chất lượng (không đạt thì không gọi là xong)

| Gate | Nội dung | Ngưỡng |
|---|---|---|
| **G1** định danh trang | mọi trang có `printed_page`; tỉ lệ `ocr_confirmed`; conflict chưa giải | 100% có số; >= 95% confirmed; **0** conflict treo |
| **G2** OCR | gold set 24 trang (4 lớp x 6 archetype) **do người xác nhận**; đo CER / WER / **tỉ lệ lỗi riêng phần dấu** cho từng engine + consensus | consensus phải **tốt hơn cả 2 engine đơn lẻ**; diacritic-ER <= 2% |
| **G3** đúng trang | 100 cặp Q-A: trang được trích dẫn có thực sự chứa câu trả lời | >= 95% |
| **G4** hình đủ & đúng | % số hiệu `Hình` mong đợi thực sự có crop; số hình gán sai Bài | >= 98%; **0** sai Bài |
| **G5** không hồi quy | recall@k so với baseline hiện tại | >= baseline |

G3 là metric **chưa từng có** trong repo và chính là mục tiêu #1 của người dùng.

---

## 5. Lộ trình (mỗi mốc có cổng riêng)

- **M0 — Manifest.** `book/` + gate G1. Chưa index gì. Sản phẩm: 4 file manifest JSON
  commit được, người đọc được.
- **M1 — Bake-off OCR.** Cài PaddleOCR VN, dựng gold set 24 trang, đo G2, chốt engine
  thứ hai + `RENDER_DPI` tối ưu bằng số.
- **M2 — Text ETL.** `blocks` + `segmenter` viết lại + `taxonomy` + `consensus` +
  `chunker`; rebuild collection text; gate G3 + G5. Xoá machinery variant.
- **M3 — Hình.** `figures/` (pill anchor + completeness); gate G4. Xoá phần lớn
  `image_processor.py`.
- **M4 — Retrieval & eval.** Citation mới, testset 4 quyển, chạy lại toàn bộ eval.

---

## 6. Kiểm thử

Unit test nhỏ, fixture tổng hợp, cho đúng phần logic dễ sai:
`page_number` (parity / offset / fallback), `bai_spine` (sửa theo đơn điệu, lệch → flag),
`consensus` (4 nhãn, đặc biệt phân biệt `conflict_diacritic` vs `conflict_text`),
`pill` (regex + hình học), `completeness` (phát hiện hở số), `chunker` (heading path).
Cộng thêm **3 fixture trang thật/quyển** dạng crop PNG nhỏ cho QA thị giác.
Không chạy cả suite khi đang lặp.

---

## 7. Rủi ro & câu hỏi còn mở (chưa có bằng chứng — không được biến thành thiết kế)

1. **Độ chính xác PaddleOCR VN ở 132 DPI: CHƯA ĐO.** Toàn bộ hướng B dựa vào việc nó
   khác-lỗi so với Tesseract. Nếu bake-off cho thấy nó tệ hơn hẳn, engine thứ hai sẽ
   phải là VLM trên Colab (hướng C) — quyết định bằng số ở M1, không phải bây giờ.
2. **PyTorch bản mới có còn kernel cho sm_61 (GTX 1050 Ti)?** Chưa verify. Ảnh hưởng
   tới việc chạy bge-m3 / reranker / Vintern trên GPU tại nhà. Pascal fp16 rất chậm
   (1:64) — GPU chỉ giúp *vừa chỗ*, không giúp *nhanh*.
3. **Pill chú thích có luôn là nền màu đặc?** Mới thấy trên 3 quyển; phải quét toàn bộ
   ở M3 và báo cáo tỉ lệ.
4. **Tần suất bảng & công thức** trên 809 trang: chưa đo (mới xem 8 trang). Ở v2:
   bảng → detect + OCR theo cell; **công thức → chỉ đánh dấu**, không cố dịch sang
   LaTeX (tránh bịa). Sẽ đo tần suất ở M1 để biết có cần leo thang không.
5. Watermark: việc làm mờ watermark **phải chứng minh làm CER giảm** trước khi bật;
   không giảm thì không làm.
