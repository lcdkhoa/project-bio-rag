# Prompt cho SESSION SONG SONG (Track B) — BM25 + hợp nhất thưa/dày

> Có **hai session làm cùng lúc**. Bạn là **Track B**. Session kia (Track A) đang vá
> `src/test/generate_testsets.py`. **Đọc §"Phân chia quyền sở hữu file" trước khi
> sửa bất cứ file nào** — chạm file của Track A là gây xung đột.

## Đọc trước, theo thứ tự

1. `CLAUDE.md` — RULE #0, mục "Philosophy" (7 nguyên tắc), mục **"Định nghĩa xong"**.
2. `document/specs/2026-08-24-m2-bm25-hybrid-prompt.md` — **prompt M2 đầy đủ**. Việc
   của bạn là **§3.1 (M2.0), §3.2 (M2.1 BM25), §3.3 (M2.2 hợp nhất)**. Đọc cả §0
   (trích nguyên văn đề cương), §1 (mọi số đã đo), §2 (10 quyết định đã chốt), §4
   (11 điều CẤM).
3. `document/decision_log.html` — hiện có **D-01…D-74**. Entry của bạn bắt đầu từ
   **D-76** (D-75 dành cho Track A).

## Tinh thần

Phản biện chính mình. Mỗi con số phải chạy ra được và dán được vào log. Một giả
thuyết chưa đo là **câu hỏi mở**, không được lặng lẽ thành thiết kế. Test pass ≠
đúng: đi tìm trang/ca làm mình sai.

---

## Việc của Track B — ba mốc, mỗi mốc nghiệm thu đo được

### B1. Chốt "sự thật hiện tại" (§3.1 của prompt M2) — làm đầu tiên

Không có bước này thì mọi so sánh sau không có gốc.

```bash
python -m src.test.qa_citation_page          # 0 lượt gọi LLM
python src/test/recall_at_k.py               # 0 lượt gọi LLM
```

**Cảnh báo đã biết:** bộ test 100 câu hiện có là của **4 quyển KNTT corpus CŨ**,
gold key theo `offset −1` trong khi index mới là `offset 0`, và nội dung trang cũng
đã đổi. **Đừng chữa nó.** Chạy, xem nó sập tới đâu, ghi "không đo được vì lý do X"
rồi đi tiếp — bộ test mới là việc của Track A.

Đo thêm hai thứ rẻ mà cần cho B2 (§1.5.3 của prompt M2):

- bao nhiêu chunk trong 16 393 chunk **ngắn hơn 40 ký tự** (`format_docs` bỏ chúng);
- bao nhiêu chunk **thiếu `region_type`** (`citations.py` đọc nó, thiếu thì citation
  suy giảm âm thầm).

**Nghiệm thu:** một bảng "trước M2" trong `decision_log.html`, nói rõ số nào **không**
đo được và vì sao.

### B2. Chỉ mục BM25 trên index đã có — KHÔNG OCR lại

Chi tiết thiết kế + phần phản biện bắt buộc: **§3.2 của prompt M2**. Tóm bốn điều
không được làm sai:

1. Khoá là **chính `chunk_id` của `biology_text`** (`{page_key}_p{page}_c{index}`).
   Hai hệ id là hai nguồn sự thật.
2. Chỉ mục thưa mang **dấu vân của index nguồn** (số chunk + `TEXT_EXTRACTION_VERSION`).
   Cũ hơn index thì **raise**, không tự dùng bản cũ. Chỉ mục thưa cũ hơn index là
   một cách hỏng **âm thầm** — cùng loại D-52 và loại "rerank tắt âm thầm".
3. **Chuẩn hoá chỉ số dưới CHỈ ở phía truy vấn/chỉ mục thưa** (`CO2` ↔ `CO,` ↔ `CO₂`).
   **CẤM sửa chữ đã lưu trong `biology_text`** (CẤM #5, nguyên tắc 1). Đo riêng:
   recall của **nhóm câu có công thức** trước/sau khi bật chuẩn hoá — đây là điểm
   đề cương nêu tên BM25 ("thuật ngữ khoa học đặc thù"), nên nó là **số để báo cáo**.
4. Tách từ tiếng Việt: `underthesea`/`pyvi` **chưa cài**. **Đo trước khi thêm phụ
   thuộc**: (a) khoảng trắng + hạ chữ thường, (b) tách từ có dấu, (c) thêm bỏ dấu.
   (b) không hơn (a) bằng số thì **không thêm phụ thuộc** (nguyên tắc 7).

Ba phép đo phản biện **bắt buộc** (đừng bỏ, mỗi cái có thể lật thiết kế):

- `overlap=120` trên `CHUNK_SIZE=400` → **~30% chữ lặp** giữa hai chunk kề, làm
  **lệch IDF**. Đo: IDF trên 16 393 chunk chồng lấn vs trên **văn bản theo trang**
  (2 387 trang) — khác bao nhiêu, có đổi thứ hạng không?
- BM25 rất nhạy `k1`/`b`. Quét `k1 ∈ {0.9, 1.2, 1.5}` × `b ∈ {0.3, 0.5, 0.75}`,
  **báo cáo bảng**, chọn bằng số. Không lấy mặc định rồi coi là xong.
- Chunk ngắn và rác OCR từ vùng hình (D-38 **cố ý** giữ lại) sẽ ăn điểm BM25 cao một
  cách sai. Đo xem chúng có lọt top-k không.

**Nghiệm thu:** một lệnh dựng chỉ mục cho **16 393 chunk**; một truy vấn trả top-k
có `chunk_id` **khớp `biology_text`**; test nhỏ chứng minh (a) khoá trùng khớp,
(b) chỉ mục cũ hơn index thì **raise**, (c) hàm chuẩn hoá **không** đổi text đã lưu.

### B3. Hợp nhất thưa + dày + công tắc ablation

Chi tiết: **§3.3 của prompt M2**. Ba điều dễ sai nhất:

1. **Thứ tự bắt buộc**: hợp nhất → **cổng lọc liên quan** → **rerank**. Không thay
   rerank bằng điểm hợp nhất.
2. **BẪY LỚN NHẤT:** `RETRIEVER_DISTANCE_MARGIN = 0.3` là cổng theo **khoảng cách
   dày**. Sau khi hợp nhất, thứ tự **không còn do khoảng cách quyết định** → cổng
   này có thể **vô nghĩa hoặc cắt sai** mà vẫn chạy êm. Phải đo cụ thể nó còn cắt
   đúng không; nếu phải đổi định nghĩa cổng thì **ghi rõ đã đổi**.
3. **Tự kiểm bắt buộc:** cấu hình "hybrid" mà tắt kênh thưa phải cho ra **đúng** kết
   quả của dense thuần. Không đúng thì đường ống có nhánh ẩn.

Mọi thành phần bật/tắt bằng `.env`. **12 cấu hình** = {BM25 thuần, dense thuần,
hybrid} × rerank{on,off} × cổng lọc{on,off}. Cắt bớt thì phải **in ra** là đã cắt
gì — CẤM #6, không im lặng.

**Lưu ý hợp đồng (§0 của prompt M2):** Giai đoạn 3 của đề cương đòi **BA** điểm so
sánh — *"BM25 thuần túy vs. Vector Retrieval vs. Hybrid Search"* — nên dense thuần
**cũng** là hợp đồng, không phải phần thêm cho vui.

**Nghiệm thu:** `scripts/run_ablation.ps1` chạy không cần trông, xuất bảng
recall@{1,3,5,10} + MRR + precision cho **12 cấu hình**, cùng bộ test, cùng seed, in
kèm số câu hỏi và cách tính; kèm một dòng nói cấu hình nào là "đề xuất" và **vì sao**.

Bảng này cần bộ test của **Track A**. Trong lúc chờ, chạy trên bất cứ bộ test nào có
sẵn để **chứng minh đường ống chạy**, và ghi rõ số đó là số **của bộ test tạm**.

---

## Phân chia quyền sở hữu file — chạm file của người khác là gây xung đột

**Track B (bạn) SỞ HỮU:**

```
src/rag/               (bm25 mới, hybrid_retriever.py, vectorstore.py)
src/config.py
requirements.txt
scripts/run_ablation.ps1
tests/rag/
```

**Track A SỞ HỮU — ĐỪNG SỬA:**

```
src/test/generate_testsets.py
src/test/testsets/
scripts/run_testsets.ps1
tests/test_eval_gold_keys.py
```

**File dùng chung — sửa ĐÚNG phần của mình, commit nhỏ, `git pull --rebase` trước
mỗi commit:**

- `document/decision_log.html` — bạn dùng **D-76 trở lên** (D-75 của Track A). Đây là
  một mảng JS; xung đột dễ giải: đọc lại rồi chèn lại entry của mình.
- `CLAUDE.md` — bạn chỉ sửa các dòng **BM25** và **Hợp nhất thưa+dày** trong bảng
  "Trạng thái tiến độ", cộng gạch đầu dòng tương ứng ở "Active redesign".

**Git:** `git pull --rebase origin master` trước mỗi commit; commit nhỏ và thường.
Message thuần, **không** `Co-Authored-By`, không "Generated with".

---

## CẤM (rút từ §4 của prompt M2 — đọc bản đầy đủ ở đó)

1. Không sửa chữ đã lưu trong `biology_text`.
2. Không bật `IMAGE_CAPTION_ENABLED` (Vintern đã bị loại — D-47, D-74).
3. Không đổi `EMBEDDING_MODEL` / `CHUNK_SIZE` / `CHUNK_OVERLAP`.
4. **Không bump `TEXT_EXTRACTION_VERSION`** — mọi tham số OCR còn nợ gom vào MỘT
   lượt sau. Bump là OCR lại **3 giờ 20**.
5. Không chạy `--image-only` (~6 giờ, và kênh pill đọc 0 nhãn trên 8/12 quyển).
6. Không `except` im lặng, không fallback im lặng — **raise** và **in ra**.
7. Không so số mới với số corpus cũ như cùng điều kiện (G3 0,99 / recall@10 1,00 là
   mốc lịch sử trên 4 quyển KNTT).
8. Không dùng `needs_review` làm điều kiện lọc (đang bật ở **57–84%** chunk).
9. Không chạy cả test suite khi đang lặp — chạy đúng test của phần vừa sửa.
10. Không xoá `database/` — index 16 393 chunk là **3 giờ 20** không lấy lại được rẻ.

## "Xong" nghĩa là (mục "Định nghĩa xong" trong CLAUDE.md)

`decision_log.html` (D-76+, số đo thật + giả thuyết đã bị bác bỏ) → `CLAUDE.md`
(dòng bị lật + bảng tiến độ) → memory (chỉ thứ không suy được từ code/git) → spec
`*-report.md` → **rồi mới commit**. Chạm ETL thì vá luôn
`document/colab_runtime_etl.ipynb` (D-69).

## Bối cảnh: sát deadline

M2 là **Giai đoạn 2 của đề cương, đáo hạn 13/08/2026**; hôm nay 24/08 → **trễ 11
ngày**; deadline cuối **23/09**. Ưu tiên: **B2 → B3** (bảng ablation là hạng mục hợp
đồng và **không cần LLM**, nên không bị chặn bởi hạn mức OpenRouter). B1 làm nhanh,
đừng sa vào chữa bộ test cũ.
