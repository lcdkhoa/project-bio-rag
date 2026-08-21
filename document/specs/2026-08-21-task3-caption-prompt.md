# Prompt thực thi Task 3 → 7: caption ảnh → eval harness → G3 → notebook → demo → báo cáo

> Prompt cho session Claude Code kế tiếp. Đọc hết §0 trước khi viết dòng code đầu tiên.
>
> **Bắt buộc đọc kèm:** `CLAUDE.md` (mục "Philosophy — 7 nguyên tắc" và "Working rules"),
> `document/decision_log.html` (D-01…D-46), và prompt gốc
> `document/specs/2026-08-21-pending-to-report-prompt.md` (Task 4–7 vẫn còn nguyên giá trị,
> chỉ cần đọc kèm phần cập nhật ở §5 dưới đây).
>
> **Nhánh đang làm:** `feat/bai-spine-toc-table` (3 commit: `e1fd42f`, `884986c`, `2fbe9af`).
> Chưa merge về `master`, chưa push.

---

## 0. Trạng thái hiện tại — ĐÃ ĐO, DÙNG LUÔN, KHÔNG ĐO LẠI

### 0.1 Task 1 — spine Bài: XONG, G1 PASS cả 4 quyển (D-43, D-44)

| Quyển | Bài | Liền mạch `1..k` | ocr_confirmed | Huy hiệu xác nhận |
|---|---|---|---|---|
| KHTN6 | 55 | ✅ | 194/194 (100%) | 43/55 |
| KHTN7 | 42 | ✅ | 178/178 (100%) | 0/42 |
| KHTN8 | 47 | ✅ | 195/195 (100%) | 0/47 |
| KHTN9 | 51 | ✅ | 226/226 (100%) | 0/51 |

- MỤC LỤC nay đọc như một **bảng** (`src/etl/book/toc.py`): tìm hình học bảng bằng CV trước,
  rồi OCR từng ô. `TOC_PAGE_NUMBERS` đã bị xoá — dải trang MỤC LỤC **tự phát hiện** (sách 6
  có BA trang: 5–7).
- **Vai hai nguồn đã ĐẢO:** MỤC LỤC dựng spine, huy hiệu chỉ **xác nhận**, không bao giờ ghi
  đè. Lệch thì ghi `banner_toc_mismatch`.
- Huy hiệu Bài **chỉ đọc được sách 6** (đĩa trắng chữ màu). Sách 7/8/9 in lục giác màu đặc
  chữ trắng, **chưa đọc được** (0/48 và 0/24 qua ba cách). `banner_votes` được ghi vào
  manifest và in ra trong báo cáo G1 nên con số `0/k` là **hiện ra**, không phải im lặng.
- `bai_so` **đã đi vào metadata chunk**, nhưng **có điều kiện**: quyển nào có flag
  `bai_numbers_not_contiguous` / `spine_out_of_order` thì tự động thôi ghi.
- `MANIFEST_VERSION` = 3, `TEXT_EXTRACTION_VERSION` = `v2_bai_spine`.
  **Manifest của 4 quyển đã dựng lại và đã commit** — không cần chạy `--build-manifests` nữa
  trừ khi bạn đổi logic manifest.

### 0.2 Task 2 — M3 hình + cổng G4: ĐẠT (D-45, D-46)

Đo trên **16 Bài / 4 quyển** bằng `python -m src.test.qa_figures --all-books --bai-per-book 4`:

| Bước | Phủ nhãn hình | Gán sai Bài |
|---|---|---|
| Xuất phát | 88,6% | 0 |
| +gộp caption, +ngưỡng bắc cầu | 90,0% | 0 |
| +bỏ vệt nhiễu OCR | 95,7% | 0 |
| +ưu tiên pill / hợp bbox | 97,1% | 0 |
| **Hiện tại** | **98,6% (70/71)** | **0** |

- Cổng G4 **không cần người dán nhãn từng trang**: `Hình A.B` là hình thứ B của **Bài A**,
  nên ghép với spine liền mạch là tự kiểm chứng được. Số "thiếu" là **cận dưới** (hình cuối
  của một Bài bị sót thì `max` tụt theo) — **đừng báo cáo nó như độ đầy đủ tuyệt đối**.
- Hai crop >40% trang còn lại **đã mở ra xem bằng mắt** và đều ĐÚNG (`Hình 1.12` sách 9 thật
  sự là hình cả trang gồm 8 trang chiếu). **Crop to ≠ crop sai.**
- `IMAGE_EXTRACTION_VERSION` = `v18_m3_g4`.
- QA thị giác `src/test/test_image_extraction_full.py` đã port sang `PageSource`
  (`--book SGK_KHTN_9_KNTT --page 16`), không còn poppler/DPI.
- **Còn đúng 1 hình chưa lấy được:** `Hình 2.3` sách 9 `page_017` — pill cam lồng trong ô nền
  kem và dính liền khối màu minh hoạ. Đã **loại bằng đo** hai giả thuyết: `VAL_MAX` (250 vs
  255 cho kết quả y hệt trên 16 trang) và morphology (CLOSE k=0,3,5,7,9 đều không tách).
  Đây là lớp bài toán D-40 chưa giải (chữ/nhãn trên nền màu lớn), cần thiết kế theo **tương
  phản cục bộ** và một phiên đo riêng. **Không** phải việc của Task 3.

### 0.3 Trạng thái chung

- Test: **202 passed, 3 skipped** (`python -m pytest tests/ -q`).
- `.env` đã đặt `EMBEDDING_MODEL=BAAI/bge-m3` — **bẫy cấu hình 384 vs 1024 chiều đã hết**.
- Máy dev **không có CUDA** (`torch 2.11.0+cpu`, 16 core, 68 GB RAM).
- `datasources/` = 4 thư mục PNG, 801 trang. `database/chroma.sqlite3` và
  `scripts/_out_*` đã được gitignore.

---

## 1. TASK 3 — Caption ảnh Vintern-1B: sửa cho chạy, ĐO, hoặc tắt tường minh

### 1.1 Lỗi, đã tái hiện trong session này (không phải trích lại D-42)

Chạy `ImageCaptioner()._load_model()` cho ra **đúng** thế này:

```
INFO  Loading image caption model: ./models/Vintern-1B-v2
WARNING Image caption model unavailable, continuing without visual captions:
        Unrecognized configuration class <class '...configuration_internvl_chat.InternVLChatConfig'>
        for this kind of AutoModel: AutoModelForImageTextToText.
enabled truoc: True
load_model -> False | enabled sau: False
```

Vị trí chính xác trong `src/etl/image_captioner.py` (325 dòng):

- `_load_model()` — **dòng 78**. Nó gọi `AutoProcessor` + `AutoModelForImageTextToText`
  (fallback `AutoModelForVision2Seq`). Vintern-1B là **InternVL**, đăng ký qua `AutoModel` +
  remote code, nên transformers **4.46.3** raise.
- `except` ở **dòng ~113** nuốt lỗi: `logger.warning(...)` → `self.enabled = False` → `return False`.
  Đây là fallback im lặng mà nguyên tắc 5 cấm, và nó lọt qua vì `IMAGE_CAPTION_ENABLED=true`
  làm mọi thứ **trông như đang bật**.
- `caption()` — **dòng 130** — còn một chỗ nuốt lỗi thứ hai: `except Exception` →
  `logger.warning` → `return empty`.

Hệ quả: **mọi hình đang được index KHÔNG có `caption_vi`.**

### 1.2 Đường sửa — ĐÃ KIỂM CHỨNG là load được

Đã chạy thật trong session này:

```python
AutoModel.from_pretrained("./models/Vintern-1B-v2", trust_remote_code=True,
                          torch_dtype=torch.float32, low_cpu_mem_usage=True).eval()
# -> InternVLChatModel, 938M tham số, hasattr(m, "chat") == True
AutoTokenizer.from_pretrained(..., trust_remote_code=True, use_fast=False)  # OK
```

Nên phần "load được hay không" **không còn là câu hỏi mở**. Việc còn lại:

1. Đổi `_load_model` sang `AutoModel` + `AutoTokenizer` (InternVL **không** dùng
   `AutoProcessor`; nó có tiền xử lý ảnh riêng theo *dynamic patches*).
2. Port `_generate_caption` (**dòng 167**) sang API `.chat(tokenizer, pixel_values, question,
   generation_config)`. Bản hiện tại dựng `messages` + `processor(...)` + `model.generate(...)`
   — sai API, sẽ không chạy dù model đã load.
3. `_build_prompt` (dòng 211) đang yêu cầu model trả **JSON**; `_parse_caption` (259) và
   `_extract_json` (279) parse JSON đó. **Phải đo** xem Vintern-1B có trả JSON ổn định không —
   nếu không thì đổi sang prompt trả văn xuôi rồi tự tách, **đừng** để `_extract_json` fail
   âm thầm rồi trả caption rỗng.

### 1.3 Phải ĐO (không đo thì không được kết luận)

Trên **≥ 10 crop hình THẬT** (lấy từ `scripts/_out_test_etl_full/` hoặc chạy
`python -m src.test.test_image_extraction_full --book ... --page ...` để sinh crop):

- **Chất lượng caption tiếng Việt** — đọc từng cái và tự chấm: caption có mô tả đúng thứ
  trong ảnh không, có bịa chi tiết không (một caption bịa còn tệ hơn không có caption).
  Dán bảng kết quả vào báo cáo, đừng chỉ nói "ổn".
- **Tốc độ trên CPU** (giây/crop). Nhân với số hình để ra chi phí thật cho 801 trang.
  Máy dev không có CUDA — nếu quá chậm thì đó là dữ kiện quyết định, không phải bất tiện.
- **Có trả JSON không** — tỉ lệ parse được / 10.

### 1.4 Nghiệm thu Task 3 — MỘT TRONG HAI, không có cửa thứ ba

**(A) Dùng được:** caption đúng và đủ nhanh →
- `_load_model` + `_generate_caption` chạy thật, có test nhỏ;
- dán bảng ≥10 caption đã đo;
- ghi decision log số đo (chất lượng + s/crop + chi phí ước tính cho toàn corpus).

**(B) Không dùng được** (caption sai/bịa, hoặc quá chậm) →
- đổi default `IMAGE_CAPTION_ENABLED` thành **`false`** trong `src/config.py` và `.env.example`;
- `_load_model` thất bại phải **`raise`**, KHÔNG `warning` rồi đi tiếp — bật mà hỏng thì phải ồn;
- bỏ luôn `except Exception` nuốt lỗi trong `caption()` (dòng 130), hoặc để nó re-raise;
- ghi rõ trong decision log + CLAUDE.md: **đã đo, không dùng, vì con số này**.

**Cấm tuyệt đối cửa thứ ba:** để nguyên trạng "trông như bật mà thật ra tắt".

---

## 2. CẤM (mỗi dòng đều có lý do đã đo)

1. **Không upscale ảnh thân bài / crop lưu trữ.** CER không đổi ở 1×/2×/3×/4×. Ngoại lệ đã
   được phép: crop góc số trang (1×+3×), crop pill (nhiều scale×psm), ô số MỤC LỤC.
2. **Không binarize/Otsu toàn trang** (đo: conf 93,4 → 92,0).
3. **Không đánh số lại / xoá file PNG nguồn.** Bỏ trang khỏi index bằng `role`.
4. **Không `index + 1`** hay bất kỳ hằng số nào làm fallback số trang.
5. **Không tự sửa chữ** (OCR, dấu, caption). Bước tự động chỉ được **drop** hoặc **flag**.
6. **Không lọc dòng OCR bằng ngưỡng confidence** — D-38 đã đo là xoá cả chữ thật
   ("Em có biết?" conf 56). Muốn lọc nhiễu thì dùng tín hiệu **tự hiệu chỉnh** (ví dụ chiều
   cao so với trung vị của chính dòng đó — cách đã dùng ở D-46).
7. **Không `except` im lặng.** Model/bước không dùng được thì phải ồn.
8. **Không so số mới với báo cáo cũ như cùng điều kiện** — corpus đã đổi 12 → 4 quyển (§5.4).
9. **Không thêm `Co-Authored-By` / "Generated with"** vào commit message.
10. **Không chạy cả test suite khi đang lặp** — chỉ chạy test của phần đang sửa.

---

## 3. Bài học phương pháp từ hai task vừa rồi (đọc, sẽ tiết kiệm rất nhiều thời gian)

1. **Không psm/scale nào thắng ở mọi ô.** Ba lần liên tiếp lỗi có cùng hình dạng này: số trang
   góc (D-33), ô số MỤC LỤC (D-43), nhãn pill (D-45). Cách đúng: **hợp ứng viên** qua nhiều
   biến thể rồi để một **ràng buộc kiểm chứng được** (đơn điệu, regex `Hình N.M`) phán xử.
2. **Mở đúng trang bị sai ra xem.** Mọi lỗi ở Task 2 đều tìm ra bằng cách render trang, vẽ
   bbox, rồi nhìn — không cái nào tìm ra bằng đọc code.
3. **Sửa một chỗ có thể chỉ ĐỔI CHỖ lỗi.** Ở D-46 bước (2), tổng số hình trước và sau đều là
   67, chỉ khác *con nào* mất. Nếu chỉ nhìn con số tổng thì đã tưởng là hoà; phải so **danh
   sách**, không so tổng.
4. **Đo trước/sau bằng cùng một script, lưu JSON.** `qa_figures.py --out` làm việc đó; nhờ
   vậy mới dựng được bảng 5 bước ở §0.2.
5. **Sẵn sàng REVERT.** Một sửa nghe rất hợp lý ("bỏ khung bao chứa nhiều hình") đo ra **tệ
   hơn** (4 vùng còn 2) và đã bị revert. Đo rồi mới giữ.

---

## 4. Việc còn lại sau Task 3 (thứ tự bắt buộc)

### Task 4 — Dựng lại eval harness cho corpus 4 quyển

1. `src/test/generate_testsets.py` hiện duyệt `DATA_DIR/*.pdf` → **tìm được 0 sách**. Phải
   đọc trang qua **`PageSource`** (bỏ luôn phụ thuộc "ETL ảnh phải chạy trước").
2. `source_book` trong CSV phải khớp **đúng** giá trị metadata `source` (`SGK_KHTN_6_KNTT`),
   `source_page` phải là **số trang IN** (cùng hệ với metadata `page`). Testset cũ ghi
   `"SGK KHTN 6 KNTT.pdf"` → **không khớp**, mọi metric IR sẽ bằng 0 vì so sai khoá.
   **Viết một test nhỏ chứng minh khoá khớp với chunk thật trong DB** — đừng tin bằng mắt.
3. Nâng lên **≥ 25 câu/sách (≥ 100 câu)**. Với 40 câu thì chênh recall ±0,05 là nhiễu.
4. **Người dùng đã trả lời: KHÔNG duyệt tay testset.** Vậy báo cáo **phải ghi rõ** testset do
   LLM sinh, chưa qua kiểm tra người. Đừng viết mập mờ.
5. **Người dùng đã trả lời: key MiMo hết token** (`EVAL_LLM_BASE_URL=...xiaomimimo.com`,
   `EVAL_LLM_MODEL=mimo-v2.5-pro`) và **nhờ tìm giúp một LLM free** tương thích OpenAI.
   → **Phải TRA CỨU và kiểm chứng free tier hiện hành**, không trả lời từ trí nhớ; rồi hỏi
   người dùng chốt trước khi đăng ký/đổi cấu hình.

### Task 5 — G3: đo "trang được trích dẫn có thực sự chứa câu trả lời"

Metric **chưa từng có** trong repo và là **mục tiêu #1** của người dùng. Thiết kế tối giản:
với mỗi câu hỏi, chạy RAG thật, lấy citation trả về, kiểm tra `ground_truth` có nằm trong
text của **đúng trang đó trong index** không (so khớp bỏ dấu, hoặc LLM judge yes/no + nêu
bằng chứng). Nghiệm thu: một script trong `src/test/` in tỉ lệ G3 và **liệt kê từng ca fail**
kèm câu hỏi + trang được trích + trang đúng. Ngưỡng thiết kế ≥ 95%; **chưa đạt thì báo con số
thật**, không làm tròn lên.

### Task 6 — Dọn nợ (chỉ khi Task 3–5 xong)

- Xoá machinery per-variant CD/CTST trong `image_processor.py` (còn một nhà xuất bản).
  Cẩn thận: `KnttImageProcessor` có builder riêng đang mang phần lớn logic G4 — **đừng xoá nhầm**.
- Nhãn citation cho người đọc: `format_book_name("SGK_KHTN_6_KNTT")` đang ra
  `"SGK_KHTN_6 (KNTT)"` → đổi thành `"Khoa học tự nhiên 6 (Kết nối tri thức)"`, có test khoá lại.
- `Hình 2.3` sách 9 (§0.2) — pill lồng trong ô màu, cần thiết kế theo tương phản cục bộ.

### Task 7 — Chốt "Colab chỉ việc chạy ETL"

Cập nhật `document/colab_runtime_etl.ipynb` (runbook DUY NHẤT, đừng tạo file song song) và
**tự chạy thử một lượt nhỏ** để chứng minh: clone → cài deps → `.env` đặt **bge-m3** → `--etl`
chạy hết không cần can thiệp, ngắt rồi chạy lại là tiếp tục. **Không cần** `--build-manifests`
(manifest đã commit) — trừ khi bạn đổi logic manifest, lúc đó phải commit manifest mới.
Nghiệm thu: chạy thật trên corpus scratch 8–12 trang với DB riêng, **dán log**.

---

## 5. Báo cáo — ràng buộc trung thực

### 5.1 Người dùng đã trả lời (2026-08-21)

- **Frontend demo nằm ở REPO KHÁC.** `project_rag` chỉ có Flask API (`--api`, CORS,
  `document/api_server_docs.md`). **Đừng dựng FE mới trong repo này**; tới bước demo thì hỏi
  người dùng repo/URL của FE.
- **Hình thức báo cáo chưa chốt** — người dùng chọn "làm số liệu trước". Cứ làm G3 + G4 +
  bảng ablation, chốt hình thức sau.

### 5.2 Ràng buộc quan trọng nhất

Corpus đã đổi **12 quyển → 4 quyển**. **Không được** viết "recall tăng từ 0,63 lên X" — hai
tập dữ liệu khác nhau. Cách đúng: **ablation trên CÙNG corpus 4 quyển, cùng testset**:

| Cấu hình | Ý nghĩa |
|---|---|
| (a) MiniLM, không rerank, không gate | tái lập cấu hình báo cáo cũ |
| (b) bge-m3, không rerank | tách riêng đóng góp của embedding |
| (c) bge-m3 + cross-encoder rerank + gate | cấu hình hiện tại |

Số 0,63 của báo cáo cũ nêu như **mốc lịch sử trên corpus khác**, nói rõ không so trực tiếp được.

### 5.3 Báo cáo mới PHẢI có mà báo cáo cũ không có

1. **G3** — độ đúng trang trích dẫn (Task 5).
2. **G4** — hình đủ & đúng: **98,6% phủ, 0 hình gán sai Bài** (§0.2), kèm ghi chú "thiếu" là
   cận dưới và 1 hình còn lại chưa lấy được vì lý do gì.
3. **G1** — định danh trang có bằng chứng: **793/793 = 100%** `ocr_confirmed`, cơ chế
   `ocr_confirmed` vs `model_inferred`, và **spine Bài 195/195 liền mạch** (§0.1).
4. **Sửa lệch mô tả–code**: báo cáo cũ viết cắt hình bằng OWL-ViT detect-then-crop, code thật
   là anchor-first deterministic. Viết đúng kiến trúc hiện tại: PageSource, segmenter theo
   vùng + tách hue, pill anchor, MỤC LỤC-dạng-bảng, checkpoint theo hash trang, citation
   deterministic.
5. **Nói ra giới hạn còn lại**: huy hiệu Bài 0/k ở 3 quyển; `Hình 2.3` chưa lấy được; testset
   do LLM sinh chưa qua kiểm tra người; caption ảnh (kết luận của Task 3).

### 5.4 Demo

Trên Colab, serve Qwen2.5-3B cần GPU; trên máy dev (không CUDA) generation sẽ rất chậm —
**đo trước khi hứa demo trực tiếp**.

---

## 6. Thứ tự chốt lại (một dòng)

Caption (T3) → eval harness (T4) → G3 (T5) → dọn nợ (T6) → chốt notebook (T7) →
**người dùng chạy `--etl` trên Colab** → demo → báo cáo theo §5.
