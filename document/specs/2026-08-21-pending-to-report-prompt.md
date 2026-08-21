# Prompt thực thi: từ trạng thái hiện tại → chạy ETL trên Colab → demo → báo cáo

> Prompt cho một session Claude Code mới. Đọc hết trước khi viết dòng code đầu tiên.
>
> **Bắt buộc đọc kèm:** `CLAUDE.md` (đặc biệt mục "Philosophy — 7 nguyên tắc" và
> "Working rules"), `document/specs/2026-08-21-png-source-etl-report.md` (đã làm gì,
> đo được gì), `document/decision_log.html` (D-01…D-42).
>
> **Mục tiêu cuối cùng của người dùng, theo thứ tự:**
> 1. Lên Google Colab **chỉ việc chạy ETL** — không phải sửa gì, không phải đoán gì.
> 2. Làm **demo**.
> 3. Nộp **báo cáo** khắc phục được đúng những nhược điểm mà báo cáo lần trước chưa đạt.
>
> Mọi con số trong §1 đã ĐO trong các session trước — **dùng luôn, không đo lại**.
> Cái gì §1 ghi là "chưa đo" thì **chưa được nói như đã biết**.

---

## 0. Nguyên tắc của lượt này (người dùng nhấn mạnh)

- **Không bịa.** Không có số thì nói "chưa đo", không nội suy, không "chắc là".
- **Không code khi chưa có bằng chứng cụ thể.** Trước khi sửa một heuristic: mở trang
  thật ra đo, in ra con số, rồi mới sửa. Sau khi sửa: đo lại, dán output.
- **Phản biện chính code mình vừa viết** trước khi nói xong: off-by-one, lệch hệ toạ
  độ 0-based/1-based, cache cũ, fallback im lặng, test pass nhưng sai thật.
- **Fail loudly.** Không thêm `except: pass`. Bài học vừa xảy ra: caption ảnh tắt im
  lặng suốt một thời gian dài vì một `except` bắt lỗi rồi chỉ `log.warning` (D-42).
- **Xoá code mạnh tay** khi phạm vi hẹp lại (nguyên tắc 7). Còn một nhà xuất bản.
- Mỗi quyết định → `document/decision_log.html`. Không chạy cả test suite khi đang lặp.

---

## 1. Trạng thái hiện tại (đã đo, dùng luôn)

### 1.1 Đã xong & đã verify
| Hạng mục | Số đo |
|---|---|
| Nguồn | 4 thư mục PNG, **801 trang**, liền mạch, 1094×1536 (trang 001 rộng 1093) |
| Định danh trang (G1) | offset **−1** cả 4 quyển; `ocr_confirmed` **793/793 = 100,0%** trên trang có in số; 2 bìa/quyển đúng là không in số |
| Checkpoint | khoá theo **hash từng trang + version**; đổi 1 pixel → chỉ trang đó chạy lại; bump version → làm lại đủ, không nhân bản chunk |
| Recall phân vùng trang | `segment_page` **2,17 → 4,10 vùng/trang** (40 trang/4 quyển), 0 trang giảm |
| OCR vùng | `--psm 6` / `--psm 7`; 6293 → 6535 token (+3,8%) |
| Nhãn hình từ pill | 32 trang mẫu → **13 trang, 17 nhãn `Hình N.M`** (trước ~0) |
| Chi phí trên **CPU** (16 core, không CUDA) | text: OCR ~1,6 s/trang + embedding bge-m3 **251 ms/chunk** → `--text-only` ~**37–40 phút**/801 trang; ảnh ~5 s/trang → ~**70 phút** |

### 1.2 Chưa xong — đây là danh sách việc
| # | Vấn đề | Bằng chứng đã có |
|---|---|---|
| A | **Spine Bài sai nặng** | sách 6 dựng được **3 Bài** cho ~55; MỤC LỤC sách 6 OCR ra **0 entry**; sách 7 & 9 FAIL G1 vì `spine_out_of_order`. Vì vậy `bai_so` **không** được ghi vào index (D-39) |
| B | **M3 (hình, cổng G4) chưa làm** | QA 4 trang thật: `figure_label='Em có biết'` (info-box bị nhận là hình); `label='quan sát'` thay vì `Hình 21.3` **dù pill đã đọc đúng nhãn đó**; một crop rộng 454..1094 × 391..1323 (gần nửa trang) |
| C | **Caption ảnh tắt im lặng** | `AutoModelForImageTextToText` không nhận `InternVLChatConfig` (transformers 4.46.3) → `except` → `enabled=False` → mọi hình vào index **không có `caption_vi`** (D-42) |
| D | **Pill lồng trong ô có tông màu chưa đọc được** | pill "Giao thông vận tải" sat **82** trên dải tím sat **157** → ngưỡng saturation toàn cục không tách được; tách theo dải hue đã thử, **không khá hơn** (D-40) |
| E | **Eval harness còn của corpus cũ** | `generate_testsets.py` duyệt `DATA_DIR/*.pdf` → **tìm được 0 sách**; nó đọc ảnh trang từ `PERSIST_DIR/images/<book>/pages/` tức **phụ thuộc ETL ảnh phải chạy trước**; testset hiện có 8 file, **10 câu/sách**, `source_book` ghi `"SGK KHTN 6 KNTT.pdf"` trong khi metadata chunk giờ là `"SGK_KHTN_6_KNTT"` → **không khớp** |
| F | **G3 (đúng trang) chưa từng đo** | Đây là **mục tiêu #1** của người dùng theo thiết kế; ngưỡng ≥ 95% |
| G | **Nhãn citation trông máy móc** | `format_book_name("SGK_KHTN_6_KNTT")` → `"SGK_KHTN_6 (KNTT)"` → citation ra `"SGK_KHTN_6 (KNTT), tr. 9"` |
| H | **Bẫy cấu hình** | `.env` máy dev: `EMBEDDING_MODEL=./models/paraphrase-multilingual-MiniLM-L12-v2` (384 chiều) vs notebook Colab bge-m3 (1024 chiều) — phải chọn MỘT (bge-m3, D-19) |

---

## 2. CẤM (mỗi dòng đều có lý do đã đo)

1. **Không upscale ảnh thân bài / crop lưu trữ.** CER không đổi ở 1×/2×/3×/4×. Ngoại
   lệ duy nhất đã được phép: crop góc số trang (1×+3×) và crop pill (2×).
2. **Không binarize/Otsu toàn trang.** Đo được là tệ hơn (conf 93,4 → 92,0).
3. **Không đánh số lại / xoá file PNG nguồn.** Bỏ trang khỏi index bằng `role`.
4. **Không `index + 1`** hay bất kỳ hằng số nào làm fallback số trang.
5. **Không tự sửa chữ** (OCR, dấu, caption). Bước tự động chỉ được **drop** hoặc
   **flag-for-review**.
6. **Không lọc bỏ dòng OCR bằng ngưỡng conf hay "không có từ ≥3 chữ cái"** — cả hai
   đã đo là xoá cả chữ thật (D-38).
7. **Không ghi `bai_so` vào index** trước khi spine qua được kiểm tra liền mạch `1..k`.
8. **Không so sánh số mới với số của báo cáo cũ như thể cùng điều kiện** — corpus đã
   đổi (12 quyển → 4 quyển). Xem §4.
9. **Không `except` im lặng.** Nếu một model/bước không dùng được thì phải ồn.
10. **Không thêm `Co-Authored-By` / "Generated with"** vào commit message.

---

## 3. Việc phải làm, theo thứ tự (thứ tự này là bắt buộc — có phụ thuộc)

### Task 1 — Spine Bài (mở đường cho G4)
**Vì sao trước:** cổng G4 đòi "**0 hình gán sai Bài**" và độ đầy đủ tính **theo từng
Bài** (số hiệu `Hình <bài>.<số>` phải liền `1..k`). Không có spine đúng thì G4 **không
đo được**. Đây là lý do Task 1 đứng trước Task 2, không phải vì spine quan trọng hơn.

Hai nguồn hiện đều yếu, phải đo trước khi sửa:
- **MỤC LỤC**: sách 6 ra 0 entry. Mở `page_005/006` ra xem OCR trả về gì (đã biết
  `TOC_PAGE_NUMBERS = (5, 6)` là đúng trang), rồi mới quyết định sửa gì — có thể là
  psm, có thể là regex `_BAI`, có thể MỤC LỤC sách 6 trình bày khác.
- **Banner "Bài N"**: chỉ bắt được 3 banner/196 trang ở sách 6. Đo `detect_bai_banner`
  trên các trang mà TOC nói là trang mở bài.

**Nghiệm thu:** mỗi quyển dựng được spine có số Bài **liền mạch `1..k`** (flag
`bai_numbers_not_contiguous` biến mất), 0 `spine_out_of_order`; G1 PASS cả 4 quyển.
Chỉ khi đó mới mở lại việc ghi `bai_so` vào metadata chunk (bỏ chặn của D-39) — và
phải nói rõ trong decision log là dựa trên bằng chứng nào.

### Task 2 — M3: hình + cổng G4
Đọc `document/specs/2026-08-19-m3-figure-extraction-design.md` §3 (ràng buộc toạ độ đã
kiểm chứng) trước khi sửa. Ba defect đã đo (§1.2 B) phải sửa:
1. **Dùng nhãn pill làm nguồn nhãn hình.** `pill.py` đã đọc đúng `Hình 21.3` mà region
   vẫn mang `label='quan sát'` → chỗ gán anchor → vùng đang bỏ qua nó. Sửa ở đó.
2. **Không nhận info-box làm hình** (`figure_label='Em có biết'`).
3. **Khung crop**: crop nửa trang là sai; đo lại `_FIG_ASSIGN_MAX_VGAP` / logic
   grow-top trên nguồn PNG (tham số cũ tune trên render 150 DPI, hình học đã đổi).

**Nghiệm thu (G4):** trên ≥ 20 trang có hình do người chọn (rải 4 quyển):
≥ 98% số hiệu `Hình` mong đợi có crop, **0 hình gán sai Bài**; và QA thị giác bằng
`src/test/test_image_extraction_full.py` (cập nhật cho nguồn PNG nếu cần) không còn
crop lấn nửa trang. Bump `IMAGE_EXTRACTION_VERSION`.

### Task 3 — Caption ảnh: sửa hoặc tắt tường minh
Sửa `ImageCaptioner._load_model` cho Vintern-1B (InternVL: `AutoModel` +
`trust_remote_code`, và `_generate_caption` phải dùng API `.chat()` của nó, không phải
`processor + generate`). **Đo chất lượng caption tiếng Việt trên ≥ 10 crop thật** rồi
mới kết luận.

Nếu đo ra không dùng được (hoặc quá chậm trên Colab free): **tắt tường minh** —
`IMAGE_CAPTION_ENABLED=false` là default, và `_load_model` thất bại phải **raise**,
không `warning` rồi đi tiếp. Cấm để nguyên trạng "trông như bật mà thật ra tắt".

### Task 4 — Dựng lại eval harness cho corpus 4 quyển
Đây là điều kiện để có bất kỳ con số nào cho báo cáo.
1. `generate_testsets.py` đọc trang qua **`PageSource`** (bỏ phụ thuộc `DATA_DIR/*.pdf`
   và bỏ phụ thuộc ETL ảnh phải chạy trước).
2. `source_book` trong CSV phải khớp **đúng** giá trị metadata `source`
   (`SGK_KHTN_6_KNTT`), và `source_page` phải là **số trang IN** (cùng hệ với metadata
   `page`). Nếu không khớp thì mọi metric IR đều bằng 0 vì so sai khoá — kiểm tra
   bằng một test nhỏ, đừng tin bằng mắt.
3. **Số câu**: hiện 10 câu/sách = 40 câu cho cả corpus. Với 40 câu, chênh lệch
   recall ±0,05 là nhiễu. Nâng lên **≥ 25 câu/sách (≥ 100 câu)** và ghi rõ trong báo
   cáo là bao nhiêu câu — đừng báo một con số 2 chữ số thập phân trên mẫu 40.
4. Câu hỏi phải **do người xác nhận** ở mức tối thiểu: đọc qua và loại câu mà chính
   người cũng không trả lời được từ trang đó (LLM sinh testset sẽ có câu rác).

**Nghiệm thu:** `recall_at_k.py` chạy được, in ra bảng, và một test nhỏ chứng minh
khoá `(source_book, source_page)` khớp với metadata chunk thật trong DB.

### Task 5 — G3: đo "trang được trích dẫn có thực sự chứa câu trả lời"
Metric **chưa từng có** trong repo và là mục tiêu #1. Thiết kế tối giản, đừng phát minh
thêm: với mỗi câu trong testset, chạy RAG thật, lấy citation trả về, rồi kiểm tra
`ground_truth` có nằm trong **text của đúng trang đó trong index** hay không (so khớp
bỏ dấu, hoặc để LLM judge quyết định với prompt yes/no + nêu bằng chứng).

**Nghiệm thu:** một script trong `src/test/` in ra tỉ lệ G3 trên toàn testset, và
liệt kê **từng ca fail** kèm câu hỏi + trang được trích + trang đúng. Ngưỡng thiết kế
≥ 95%; nếu chưa đạt thì **báo cáo con số thật**, không làm tròn lên.

### Task 6 — Dọn nợ nhỏ (chỉ khi Task 1–5 đã xong)
- Xoá machinery per-variant CD/CTST trong `image_processor.py` (còn một nhà xuất bản).
- Nhãn citation cho người đọc: `"SGK_KHTN_6 (KNTT)"` → dạng người đọc được, ví dụ
  `"Khoa học tự nhiên 6 (Kết nối tri thức)"`. Có test khoá lại.
- Pill lồng trong ô màu (§1.2 D) — cần thiết kế theo **tương phản cục bộ**; chỉ làm khi
  còn thời gian, và phải đo trước/sau.

### Task 7 — Chốt "Colab chỉ việc chạy ETL"
Cập nhật `document/colab_runtime_etl.ipynb` (đây là runbook DUY NHẤT, không tạo file
song song) và **tự chạy thử một lượt nhỏ** để chứng minh:
1. clone master → cài deps → `--profile text-etl` (hoặc `all` nếu chạy cả ảnh);
2. **không phải chạy `--build-manifests`** (manifest đã commit) — trừ khi Task 1 làm
   manifest đổi, lúc đó phải **commit manifest mới**;
3. `.env`/env trên Colab đặt **bge-m3** (bẫy H);
4. `--etl` chạy hết không cần can thiệp; bị ngắt thì chạy lại là tiếp tục.

**Nghiệm thu:** chạy thật `--etl` trên một corpus scratch 8–12 trang với DB riêng, dán
log. Không được "chắc là chạy được".

---

## 4. Báo cáo — khắc phục đúng những gì lần trước chưa đạt

Báo cáo cũ: `report/main_chuyende_totnghiep.pdf` (chuyên đề tốt nghiệp UIT, RAG cho
KHTN THCS). **Số liệu nền của nó** (đọc từ Ch.4/Ch.5, dùng làm mốc lịch sử):

| Metric | Báo cáo cũ | Nút thắt mà nó tự chẩn đoán |
|---|---|---|
| Recall@10 | **0,63** (trần 0,84 khi bỏ relevance gate) | nút thắt ở **ranking/cut-k**, không phải embedding |
| MRR | **0,51** | trang đúng thường ở hạng 2–3 |
| Precision (trang) | **0,38** | chủ yếu do **trùng chủ đề giữa các quyển** |
| Answer (LLM judge) | correctness 3,76 · faithfulness 4,25 · relevancy 4,36 / 5 | |

Hai nhược điểm người dùng muốn khắc phục: **(1) chất lượng cắt hình**, **(2) ngữ nghĩa
retrieval**. Và báo cáo cũ có một **lỗi lệch giữa mô tả và code**: nó viết cắt hình bằng
OWL-ViT detect-then-crop, trong khi code thật đã là anchor-first deterministic.

### 4.1 Ràng buộc trung thực khi báo cáo (quan trọng nhất mục này)
Corpus đã đổi **12 quyển → 4 quyển**. Vì vậy **không được** viết "recall tăng từ 0,63
lên X" — đó là hai tập dữ liệu khác nhau. Cách làm đúng, phải làm:

**Ablation trên CÙNG corpus 4 quyển, cùng testset:**

| Cấu hình | Ý nghĩa |
|---|---|
| (a) MiniLM, không rerank, không relevance gate | tái lập **cấu hình của báo cáo cũ** |
| (b) bge-m3, không rerank | tách riêng đóng góp của embedding |
| (c) bge-m3 + cross-encoder rerank + gate | **cấu hình hiện tại** |

Báo Recall@k / MRR / Precision cho cả ba, trên cùng testset ≥ 100 câu. Lúc đó câu
"đóng góp của rerank là bao nhiêu" mới có bằng chứng. Số 0,63 của báo cáo cũ được nêu
như **mốc lịch sử trên corpus khác**, nói rõ là không so trực tiếp được.

### 4.2 Những thứ báo cáo mới PHẢI có mà báo cáo cũ không có
1. **G3 — độ đúng trang trích dẫn** (Task 5). Đây là điều báo cáo cũ không đo mà lại
   là thứ quyết định "học sinh mở đúng trang có thấy câu trả lời không".
2. **G4 — hình đủ & đúng** (Task 2): % số hiệu `Hình` có crop, số hình gán sai Bài.
   Đây là câu trả lời định lượng cho nhược điểm (1).
3. **Định danh trang có bằng chứng**: 793/793 = 100,0%, kèm cơ chế `ocr_confirmed` vs
   `model_inferred` — chống lại đúng loại lỗi "citation lệch một trang".
4. **Sửa lệch mô tả–code**: viết đúng kiến trúc hiện tại (PageSource, segmenter theo
   vùng + tách hue, pill anchor, checkpoint theo hash trang, citation deterministic).
5. **Nói ra giới hạn còn lại** (mục §1.2 nào chưa xong thì ghi vào Limitations) —
   báo cáo có phần hạn chế trung thực đáng tin hơn báo cáo tô hồng.

### 4.3 Demo
Repo **chỉ có Flask API** (`--api`, có CORS, tài liệu ở `document/api_server_docs.md`);
**không có frontend trong repo này** — nếu demo cần UI thì phải hỏi người dùng FE nằm
ở đâu, đừng tự dựng một cái mới rồi coi như xong. Trên Colab, serve Qwen2.5-3B cần GPU;
trên máy dev (không CUDA) generation sẽ rất chậm — đo trước khi hứa demo trực tiếp.

---

## 5. Câu hỏi mở — phải hỏi hoặc đo, KHÔNG được đoán
1. **Frontend cho demo nằm ở đâu?** (repo này không có)
2. **Báo cáo mới là bản cập nhật của `report/main_chuyende_totnghiep.pdf` hay viết
   mới?** Có deadline không? Có yêu cầu định dạng/mục lục bắt buộc của trường không?
3. **Vintern-1B có chạy được với transformers trên Colab hay không** — chưa đo. Đừng
   giả định là được chỉ vì Colab mới hơn.
4. **Testset ≥ 100 câu có được người xác nhận không?** Nếu không có người duyệt thì
   phải ghi rõ trong báo cáo là testset do LLM sinh, chưa qua kiểm tra người.
5. Gold set CER hiện chỉ 4 vùng/1 trang + confidence 8 trang. Muốn báo cáo con số OCR
   toàn corpus thì cần gold set rộng hơn **do người xác nhận**.

---

## 6. Thứ tự chốt lại (một dòng)

Spine (T1) → hình + G4 (T2) → caption (T3) → eval harness (T4) → G3 (T5) → dọn nợ (T6)
→ chốt notebook (T7) → **người dùng chạy `--etl` trên Colab** → demo → báo cáo theo §4.
