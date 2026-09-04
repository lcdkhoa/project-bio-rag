# Thiết kế — làm lại từ đầu pipeline sinh bộ test + đánh giá LLM-as-Judge

> Ngày chốt: **2026-09-03**. Người dùng đã chốt qua hỏi-đáp trong hội thoại:
> (1) xóa TOÀN BỘ code sinh test + đánh giá cũ, kể cả `ablation.py` vừa viết lại
> sáng nay theo D-181 — viết lại từ 0, không vá tiếp; (2) tổng bộ test vẫn là
> **240 câu**, gồm cả 3 nhóm Văn bản/Hình/Ngoài-phạm-vi cộng lại; (3) "ngẫu nhiên"
> nghĩa là chọn ngẫu nhiên TRANG/HÌNH NGUỒN trước rồi LLM soạn câu từ đó, **không**
> ràng buộc phủ đều 12 quyển (khác hẳn quy ước cũ 16-20 câu/quyển); (4) có mục
> tiêu/khoảng cho từng nhóm (không random cả tỉ lệ 3 nhóm); (5) bảng so sánh 4
> phương pháp truy xuất (P/R/F1@K, K=3/5/10/20) theo yêu cầu CBHD **vẫn giữ**,
> chỉ viết lại logic dùng bộ test mới; (6) bắt buộc người duyệt tay trước khi một
> bộ test được coi là chính thức; (7) giữ nguyên logic `eval_llm.py` (JudgePool
> xoay 4 model, đã mất 3 vòng debug — D-163/D-168/D-173) nhưng đổi tên để tránh
> nhầm với bộ cũ; (8) mọi script khác đang phụ thuộc `testsets/` (bộ 100 câu cũ)
> — `ablation_multimodal.py`, `bm25_sweep.py`, `review_testset.py`,
> `prompt_scope_probe.py`, `qa_citation_page.py` — **xóa luôn**, không giữ lại.
>
> Deadline bảo vệ: **23/09/2026**.

---

## 1. Vì sao làm lại thay vì vá tiếp D-181

D-181 (chỉ đạo CBHD, code xong + chạy xong sáng nay, xem `document/decision_log.html`
và `CLAUDE.md` mục "Cấu trúc đánh giá mới") dựng một bộ 240 câu **cố định theo
quyển** (192 văn bản = 16/quyển × 12, 48 hình = 4/quyển × 12) và giữ nguyên cách
chọn câu cũ (rút mẫu từ pool 300 câu do `gemini-3.5-flash-lite` sinh 2026-08-22,
`build_image_questions.py` chọn ảnh theo tiêu chí thủ công). Khi soát lại kết quả
chạy sáng nay (`src/test/eval_240_results/`), phát hiện thêm: nhóm Hình chấm
Correct chỉ 2,06/5 so với Văn bản 4,36/5 — một dấu hiệu chất lượng đáng nghi mà
cấu trúc cố định "đều 4 câu/quyển" không giúp chẩn đoán được vì mẫu quá nhỏ và
không ngẫu nhiên thật.

Người dùng quyết định: bỏ hẳn ràng buộc "đều theo quyển" (vốn không phải yêu cầu
của `goal.docx` — đề cương chỉ yêu cầu Precision@k/Recall@k/MRR, không yêu cầu
phân bổ đều theo quyển), chuyển sang lấy mẫu ngẫu nhiên thật trên toàn corpus, và
nhân dịp này dọn sạch luôn phần code cũ (nhiều tầng vá chồng lên nhau: generate →
build_testset_240 rút mẫu từ generate → build_image_questions chọn tay → D-181 vá
lại evaluator/ablation) thay vì vá thêm một tầng nữa.

**Không đổi**: pipeline RAG sản xuất (`src/rag/*`, `src/etl/*`), corpus, cấu hình
`RERANK_SCORE_MIN=0,59` (D-180). Việc này CHỈ đổi cách đo, không đổi cái được đo.

---

## 2. Phạm vi xóa / giữ

### Xóa hoàn toàn

| File/thư mục | Lý do |
|---|---|
| `src/test/generate_testsets.py` | sinh pool 300 câu cũ — thay bằng lấy mẫu trực tiếp trong `build_testset.py` |
| `src/test/build_testset_240.py` | rút mẫu 192 câu đều-quyển từ pool cũ |
| `src/test/build_image_questions.py` | chọn ảnh thủ công cho 48 câu hình cũ |
| `src/test/evaluator.py` | đánh giá đầu-cuối cũ (cả bản trước D-181 lẫn bản D-181) |
| `src/test/metrics.py` | `evaluate_retrieval`/`make_page_relevance` — viết lại trong `retrieval_benchmark.py` |
| `src/test/ablation.py` | vừa viết lại sáng nay theo D-181, nhưng đọc bộ test cố định-theo-quyển — thay bằng `retrieval_benchmark.py` |
| `src/test/ablation_multimodal.py` | phụ thuộc `testsets/`, quyết định xóa luôn theo yêu cầu |
| `src/test/bm25_sweep.py` | phụ thuộc `testsets/`, quyết định xóa luôn |
| `src/test/review_testset.py` | phụ thuộc `testsets/`, quyết định xóa luôn |
| `src/test/prompt_scope_probe.py` | phụ thuộc `testsets/`, quyết định xóa luôn |
| `src/test/qa_citation_page.py` | cổng G3, phụ thuộc `testsets/`, quyết định xóa luôn — **đánh đổi đã biết** (phản biện lần 3): đây là cổng đo DETERMINISTIC duy nhất "trang được trích có chứa câu trả lời không" (IDF-weighted token coverage, không cần LLM) — khác hẳn LLM-judge của `run_eval.py`. Xóa nó = mất hẳn năng lực này, không có gì thay thế trong 3 script mới. Ghi lại ở mục 7 để không bị hiểu nhầm là bỏ sót. |
| `scripts/run_ablation.ps1` | gọi `src/test/bm25_sweep.py`+`ablation.py` (dòng 108/114/133, grep xác nhận) — script vận hành thật đã dùng đo M2 (D-80+), không phải code chết, nhưng gọi 2 module đã xóa nên không còn chạy được — quyết định xóa luôn (phản biện lần 4) |
| `scripts/run_testsets.ps1` | gọi `src/test/generate_testsets.py` (dòng 62/81) — cùng lý do trên |
| `scripts/sau_etl_anh.ps1` | gọi `src/test/build_image_questions.py` (dòng 36/40/41) — cùng lý do trên |
| `src/test/testsets/` | pool 100 câu/4 quyển KNTT cũ |
| `src/test/testsets_240/` | bộ 240 câu cố định-theo-quyển + `_selection_meta.json`, `_ngoai_pham_vi_meta.json` |
| `src/test/eval_240_results/` | output lượt chạy sáng nay (chưa commit — `git status` hiện `??`) |

### Test cũ (`tests/`, KHÁC `src/test/`) đang import các module sắp xóa — tìm ra ở
phản biện lần 3 (subagent độc lập), spec 2 lượt trước bỏ sót hoàn toàn

Grep `from src.test.X import` / `from src.test import X` trên `tests/` xác nhận
**9 file** phụ thuộc trực tiếp module sắp xóa. Nếu xóa mà không xử lý các file
này, `pytest tests/` vỡ ngay ở bước collection (ImportError) — phá bất biến "Test
suite XANH" (781 passed hiện tại). Xử lý theo đúng tinh thần "xóa toàn bộ, không
vá tiếp" mà người dùng đã chốt, chia hai nhóm:

**Xóa cùng lúc với module chúng test** (logic bị test không còn tồn tại sau khi
xóa, không có gì để giữ lại):
| Test cũ | Test module đã xóa |
|---|---|
| `tests/rag/test_ablation_multimodal_score.py` | `ablation_multimodal.py` |
| `tests/test_g3_matcher.py` | `qa_citation_page.py` |
| `tests/test_eval_gold_keys.py` | `metrics.py` + `generate_testsets.py` |
| `tests/test_evaluator_cli.py` | `evaluator.py` |
| `tests/test_build_testset_240.py` | `build_testset_240.py` |
| `tests/test_build_image_questions.py` | `build_image_questions.py` |
| `tests/test_generate_testsets_resume.py` | `generate_testsets.py` |

(`test_eval_gold_keys.py`/`test_evaluator_cli.py`/`test_build_testset_240.py`
kiểm những khái niệm mà mục 5 đã có test tương đương cho code MỚI — xóa bản cũ
không mất năng lực kiểm thử, chỉ mất bản kiểm cho code không còn tồn tại.)

**Sửa import, KHÔNG xóa** (logic được mang sang module mới nguyên vẹn — xem mục
3.3 đã sửa dưới đây để thêm MRR):
| Test cũ | Import cũ | Import mới |
|---|---|---|
| `tests/test_mrr_metric.py` | `from src.test.ablation import reciprocal_rank` | `from src.test.retrieval_benchmark import reciprocal_rank` |
| `tests/rag/test_ablation_cache.py` | `from src.test import ablation` (dùng nhiều hơn `Cache`/`load_cache` — xem chi tiết dưới) | `from src.test import retrieval_benchmark` |

`src/test/ablation.py` hiện có comment tự giải thích ràng buộc này (dòng 489-490:
*"Giữ lại từ `recall_at_k.py`... `tests/test_mrr_metric.py` import thẳng tên
này."*) — bài học: khi "viết lại từ 0" một module, phải đọc trước AI đang import
ngược vào nó, không chỉ đọc nó export gì.

**SỬA SAU PHẢN BIỆN LẦN 4**: bản trước chỉ liệt kê `Cache`/`load_cache` — ĐỌC
THẬT `tests/rag/test_ablation_cache.py` (70 dòng) cho thấy nó còn dùng
`ablation.Config` (dataclass cấu hình), `ablation.rank_for(...)`, và quan trọng
nhất là **monkeypatch trực tiếp cấp module** `ablation.chunk_ids_digest` và
`ablation.TEXT_EXTRACTION_VERSION` (dòng 45, 54-55: `monkeypatch.setattr(ablation,
"chunk_ids_digest", ...)`). `retrieval_benchmark.py` phải export ĐỦ 6 tên ở cấp
module: `Cache`, `load_cache`, `Config`, `rank_for`, `chunk_ids_digest`,
`TEXT_EXTRACTION_VERSION` — và `chunk_ids_digest`/`TEXT_EXTRACTION_VERSION` phải
được `from ... import` vào namespace của module (không phải gọi qua
`config.TEXT_EXTRACTION_VERSION` mỗi lần dùng), nếu không cơ chế monkeypatch của
test sẽ không có tác dụng (patch nhầm chỗ, `load_cache`/`rank_for` bên trong vẫn
đọc giá trị gốc). Đây là chi tiết dễ "viết lại tương đương nhưng khác cấu trúc"
mà vẫn làm test vỡ `AttributeError` hoặc im lặng bỏ qua monkeypatch — kiểm bằng
cách CHẠY test này ngay sau khi viết `retrieval_benchmark.py`, không chỉ đọc lại
bảng ánh xạ.

### Đổi tên, giữ nguyên logic

| Cũ | Mới | Lý do giữ |
|---|---|---|
| `src/test/eval_llm.py` | `src/test/llm_client.py` | `JudgePool` (xoay 4 model Groq, chống TPM/TPD, retry JSON hỏng qua `force_rotate()`) không phải logic sinh-test/chấm-điểm — là hạ tầng gọi LLM đã mất 3 vòng debug thật (D-163, D-168, D-173). Viết lại từ đầu = lặp lại debug rate-limit đã xong. |

Đổi tên xong, cập nhật MỌI chỗ import `from src.test.eval_llm import ...` (chỉ còn
trong các file bị xóa ở trên, nên sau khi xóa xong sẽ 0 tham chiếu còn treo — xác
nhận bằng grep trước khi coi bước này xong).

### Không đụng — ngoài phạm vi việc này

`qa_layout.py`, `qa_figure_coverage.py`, `ocr_bakeoff.py`, `report_numbers.py`,
`tests/test_decision_log.py`, `test_image_extraction_full.py`, mọi thứ dưới
`src/rag/`, `src/etl/`, `src/app/` — đo/QA corpus và ETL, không liên quan sinh
test hay LLM-judge.

**Ngoài phạm vi lượt này (nợ lại, không phải quên)**: `report/tex_source/`
chương 4/5 và `report/ve_hinh_chuong4.py`, `tests/test_bao_cao_so_lieu.py` vẫn
khóa cứng theo schema CSV cũ (9-cột D-175 hoặc 3-cột D-181) — sẽ hỏng ngay khi
chạy vì file input không còn tồn tại. Chỉ sửa các file này SAU khi có số đo thật
từ pipeline mới, không sửa trước (tránh viết báo cáo theo số chưa có).
`document/colab_runtime_eval.ipynb` cũng phải vá theo tên script mới trước khi
chạy trên Colab — liệt kê ở mục 6. `report_numbers.py` (giữ nguyên logic) có
`--testset-dir` mặc định trỏ vào `testsets_240/` (dòng ~170) — sau khi thư mục
đó bị xóa, chạy không truyền cờ sẽ báo lỗi đường dẫn không tồn tại thay vì thông
báo rõ ràng; không sửa trong lượt này (đúng "ngoài phạm vi"), chỉ ghi chú để
không ai ngỡ ngàng khi gặp.

---

## 3. Ba script mới, `src/test/`

### 3.1 `build_testset.py` — sinh bộ test 240 câu

```
python -m src.test.build_testset                       # sinh nháp, seed 42
python -m src.test.build_testset --n 240 --n-ngoai-pham-vi 30 --seed 42
python -m src.test.build_testset --mark-reviewed        # xác nhận ĐÃ duyệt tay xong
```

**Nguồn dữ liệu**: `chromadb.PersistentClient(path=PERSIST_DIR)` đọc trực tiếp
(nhẹ, giống `report_numbers.py` — KHÔNG khởi tạo `AppServices` đầy đủ vì không
cần retriever/reranker ở bước này).

**Xác định N cho từng nhóm** (tại thời điểm chạy, không hardcode):
1. `n_ngoai_pham_vi = args.n_ngoai_pham_vi` (mặc định 30).
2. `n_con_lai = args.n - n_ngoai_pham_vi` (mặc định 210).
3. **SỬA SAU PHẢN BIỆN LẦN 4**: bản trước viết "đếm `.count()`... chỉ đếm doc có
   `is_active=True` và `review_status` không phải rejected/deleted" — bất khả
   thi, đã xác nhận bằng `help(Collection.count)`: `count()` KHÔNG nhận tham số
   lọc, chỉ trả tổng số bản ghi thô. Cách đúng: `n_chunk =
   len(collection("biology_text").get(include=[])["ids"])` (không cần lọc gì
   thêm cho text), còn `n_anh` phải áp **ĐÚNG CÙNG bộ lọc** sẽ dùng ở bước lấy
   mẫu bên dưới (is_active/review_status VÀ có figure_label/crop_text không
   rỗng) rồi đếm `len(ids_da_loc)` — không đếm bằng bộ lọc khác rồi lấy mẫu bằng
   bộ lọc khác (bất nhất đã có ở bản trước: bước đếm chỉ lọc is_active/
   review_status, còn bước lấy mẫu lọc thêm cả figure_label/crop_text — đo thật
   trên corpus hôm nay hai bộ lọc lệch nhau 101/3881 ảnh = 2,6%, không đủ lớn để
   gây lỗi ngưỡng hôm nay nhưng là chỗ tự mâu thuẫn nội bộ cần tránh khi viết
   code, không phải chỉ khi viết spec).
4. `p_hinh = n_anh / (n_chunk + n_anh)`; `n_hinh = round(n_con_lai * p_hinh)`;
   `n_van_ban = n_con_lai - n_hinh`.
   Đo hôm nay (đã re-verify bằng truy vấn DB thật ở phản biện lần 4):
   `n_chunk=16515, n_anh=3881` → `p_hinh≈0,190` → trên 210 câu:
   `n_hinh≈40, n_van_ban≈170` (tỉ lệ khác con số cứng 192/48 cũ nhưng KHÔNG cố
   tình khớp — đây là hệ quả tự nhiên của việc đếm, không phải mục tiêu).
5. In rõ 4 số này ra console + ghi vào `meta.json` — không được lặng lẽ dùng một
   tỉ lệ khác tỉ lệ đã in (nguyên tắc 6: một nguồn sự thật).

**Lấy mẫu (`random.Random(seed)`, KHÔNG chia theo quyển)**:
- Văn bản: `collection("biology_text").get(include=["documents", "metadatas"])`
  (16 515 phần tử — PHẢI xin `documents` ngay từ lệnh `get()` này, không phải chỉ
  `ids`, vì bước lọc độ dài dưới đây cần đọc `document` của từng chunk); lọc bỏ
  chunk có `len(document) < 200` ký tự (chunk quá ngắn — tiêu đề/mẩu vụn, không đủ
  nội dung để hỏi một câu có nghĩa; ngưỡng 200 tham khảo `CHUNK_SIZE=400` hiện có,
  không phải số đo mới); `random.sample(ids_loc, n_van_ban)` không lặp.
- Hình: tương tự trên `biology_image_metadata` — `get(include=["metadatas"])` —
  lọc `is_active=True`, `review_status not in ("rejected", "deleted")` — đúng hai
  giá trị thật đang dùng để loại ảnh khỏi truy xuất sản xuất
  (`src/rag/image_vectorstore.py:768-770`, đã grep xác nhận, không đoán tên
  trường) — và có `figure_label` hoặc `crop_text` không rỗng (ảnh trắng thông tin
  thì không hỏi được).
  **ÁNH XẠ TRƯỜNG SANG CSV (SỬA SAU PHẢN BIỆN LẦN 4 — thiếu ở 3 lượt trước, lỗi
  nghiêm trọng nhất tìm được):** `biology_image_metadata` **KHÔNG có** khoá
  `source`/`page` như `biology_text` — đã truy vấn DB thật (`database/`) xác
  nhận metadata ảnh dùng khoá **`pdf_filename`** (giá trị ví dụ `SGK_KHTN_6_CD`,
  cùng format với `source` bên text) và **`page_number`** (số trang in, cùng
  ngữ nghĩa với `page` bên text). Cột CSV `source_book`/`source_page` của một
  dòng `hinh` PHẢI lấy từ `metadata["pdf_filename"]`/`metadata["page_number"]`,
  KHÔNG được suy đoán theo tên trường bên text. Nếu bỏ sót ánh xạ này (ví dụ đọc
  nhầm `metadata.get("source")` — trả `None` vì trường không tồn tại), toàn bộ
  ~40 câu `hinh` sẽ có `source_book`/`source_page` rỗng → `_gold_key()` (mục 3.3)
  coi nhầm CẢ NHÓM HÌNH là `ngoai_pham_vi`, sai âm thầm và không có gì trong
  `retrieval_benchmark.py` phát hiện ra (khác hẳn ca `suy_bien` đã được xử lý kỹ
  — đây là một lớp lỗi mới, xảy ra TRƯỚC khi `_gold_key()` được gọi).
- Ngoài phạm vi: `random.choice` trên danh sách môn cố định (giữ nguyên danh sách
  D-181: Sử/Địa/GDCD/Toán/Văn/Anh/Tin/Thể dục/Âm nhạc/Mỹ thuật), lặp `n_ngoai_pham_vi`
  lần — mỗi lần một môn ngẫu nhiên (có lặp môn, không lặp câu vì LLM soạn mới).

**Hai chỗ chặn input/dữ liệu bất thường, PHẢI có trước khi gọi `random.sample`**
(tìm ra ở phản biện lần 2 — thiếu ở bản trước):
- `args.n_ngoai_pham_vi >= args.n` (hoặc âm) → báo lỗi rõ ràng ngay từ đầu
  ("`--n-ngoai-pham-vi` phải nhỏ hơn `--n`"), không để `n_con_lai` âm rồi
  `random.sample` ném `ValueError` khó hiểu ở tận bước lấy mẫu.
- Pool đủ điều kiện (sau lọc độ dài/`is_active`/nhãn) **nhỏ hơn** số cần rút
  (`len(ids_loc) < n_van_ban`, tương tự cho hình) → báo lỗi rõ ràng nêu đúng 2 con
  số (cần bao nhiêu, có bao nhiêu) — KHÔNG lặng lẽ hạ `n_van_ban` xuống bằng pool
  rồi dồn phần thiếu sang nhóm khác (thay đổi âm thầm tỉ lệ đã in ở bước "Xác
  định N", vi phạm đúng nguyên tắc 6 mục 5 đã nêu). Trên corpus hôm nay
  (16 515 chunk, 3 881 ảnh, N cần ~170/~40) khả năng chạm ngưỡng này gần như
  không có, nhưng hành vi khi chạm phải rõ ràng, không phải một `IndexError`
  ngẫu nhiên từ `random.sample`.

**Soạn câu bằng LLM** (dùng `llm_client.py`, tức CÙNG Groq JudgePool sẽ dùng để
chấm điểm ở bước 3.2 — không cần hạ tầng LLM riêng, không tốn `AppServices`):
- Văn bản: đưa nguyên `document` (text chunk thật) + `metadata` (source/page) vào
  prompt, yêu cầu 1 câu hỏi tiếng Việt tự nhiên mà câu trả lời nằm TRỌN trong đoạn
  này, kèm `ground_truth` (diễn giải lại, không copy nguyên văn 1:1).
- Hình: đưa `figure_label` + `figure_caption` + `crop_text` + `context_text` vào
  prompt tương tự.
- Ngoài phạm vi: đưa tên môn, yêu cầu 1 câu hỏi kiến thức phổ thông thuộc môn đó;
  `ground_truth` là một câu mô tả kỳ vọng hệ thống trả lời "không có trong sách",
  giữ đúng mẫu đang dùng (đã xác nhận đúng ở lượt chạy sáng nay — 30/30 câu ra
  điểm 5,0/5,0/5,0 vì hệ thống từ chối đúng).
- Lỗi/rỗng từ LLM: thử lại tối đa 2 lần cùng item; hết 2 lần vẫn lỗi thì **bỏ qua
  item đó, rút một item ngẫu nhiên khác thay thế** (không được để trống một dòng
  trong CSV) — log rõ bao nhiêu lần phải thay, không im lặng. Item thay thế rút
  từ một **tập id đã loại trừ toàn cục** (gồm mọi id đã dùng/đã thử-và-fail trong
  CHÍNH lượt chạy này) để không bao giờ trùng câu hỏi trong cùng một bộ test.
  **THÊM SAU PHẢN BIỆN LẦN 4**: bản trước không có trần tổng — nếu Groq lỗi hệ
  thống xuyên suốt (đúng kịch bản đã xảy ra thật, D-173: TPD cạn giữa lượt), cơ
  chế thay-thế có thể duyệt qua rất nhiều ứng viên trong pool trước khi ai đó
  nhận ra, dù không phải vòng lặp vô hạn (pool hữu hạn). Thêm một trần: nếu tỉ lệ
  lỗi vượt 30% trên 20 lệnh gọi liên tiếp gần nhất (cửa sổ trượt), **dừng hẳn
  toàn bộ script** với thông báo rõ ràng thay vì tiếp tục rút thay thế — đúng
  triết lý "fail loudly" thay vì âm thầm đốt quota.

**Output**:
- `src/test/testset/draft.csv` — cột: `question, loai, source_book, source_page,
  figure_label, ground_truth`. `loai ∈ {van_ban, hinh, ngoai_pham_vi}`.
  `source_book`/`source_page` rỗng cho `ngoai_pham_vi` (không ép kiểu int — lặp
  đúng bug đã né ở D-181, xem `_ngoai_pham_vi_meta.json` cũ).
- `src/test/testset/meta.json` — `{seed, n_total, n_van_ban, n_hinh,
  n_ngoai_pham_vi, p_hinh_do_duoc, tao_luc (ISO timestamp), human_reviewed: false}`.
- `--mark-reviewed`: đọc `meta.json`, hỏi xác nhận (in ra đường dẫn CSV, yêu cầu
  gõ `xac-nhan-da-doc` để tránh bấm nhầm), rồi set `human_reviewed: true` +
  `reviewed_at`. KHÔNG có flag tự động bỏ qua bước này.

### 3.2 `run_eval.py` (thay `evaluator.py`) — đánh giá đầu-cuối bằng LLM-judge

```
python -m src.test.run_eval                    # raise nếu meta.json human_reviewed=false
python -m src.test.run_eval --allow-draft       # chạy tạm trên nháp CHƯA duyệt, chỉ để tự kiểm code — in cảnh báo đỏ mỗi dòng
```

- Đọc `src/test/testset/draft.csv` (đã duyệt) + `meta.json`.
- Với mỗi câu: gọi đúng pipeline RAG thật (`AppServices` đầy đủ — cần retriever
  thật) → `judge_correctness/faithfulness/relevancy` qua `llm_client.py`.
- Tổng hợp theo **LOẠI câu hỏi** (`van_ban`/`hinh`/`ngoai_pham_vi`) — giữ đúng
  hướng D-181 của CBHD (trục = loại câu hỏi, không theo quyển).
- Output: `src/test/testset/eval_result.csv` (chi tiết từng câu) +
  `src/test/testset/eval_report.md` (bảng tổng hợp).
- **THÊM SAU PHẢN BIỆN LẦN 4**: cảnh báo console của `--allow-draft` không đủ —
  nếu output bị redirect vào log hoặc file CSV được mở lại sau này mà không kèm
  console, không có cách phân biệt kết quả nháp với kết quả chính thức chỉ bằng
  nhìn file, trong khi đúng các con số này (Correct/Faithful/Relevancy) sẽ được
  trích thẳng vào báo cáo tốt nghiệp. Bắt buộc: khi chạy `--allow-draft`, MỌI
  file output (`eval_result.csv`, `eval_report.md`, và tương tự cho
  `retrieval_benchmark.py`) phải có hậu tố `_NHAP_CHUA_DUYET` trong tên file
  (không phải chỉ một cột `is_draft` dễ bị bỏ sót khi đọc lướt) — để không ai
  nhầm một bảng nháp thành số liệu chính thức khi mở lại file nhiều ngày sau.

### 3.3 `retrieval_benchmark.py` (thay `ablation.py`) — bảng 4 phương pháp × P/R/F1@K

```
python -m src.test.retrieval_benchmark --build-cache    # dựng đệm dense/sparse (resume-safe, giữ nguyên cơ chế Cache của ablation.py)
python -m src.test.retrieval_benchmark
```

- 4 cấu hình đúng ánh xạ D-181 (không đổi): `keyword`=bm25 rerank=off gate=off,
  `dense`=dense rerank=off gate=off, `truyen_thong`=hybrid rerank=off gate=off,
  `de_xuat`=hybrid rerank=on gate=off (đúng `.env` production sau D-180).
- **SỬA SAU PHẢN BIỆN LẦN 3**: bản trước chỉ có P/R/F1@K, LÀM MẤT MRR — sai. Giữ
  nguyên `KS = (1, 3, 5, 10, 20)` và `reciprocal_rank()` y hệt `ablation.py` hiện
  tại (dòng 111, 489). Ba lý do bắt buộc phải giữ, không phải tùy chọn:
  1. `goal.docx` (RULE #0, thắng mọi chỉ đạo khác) yêu cầu đích danh
     "Precision@k/Recall@k/**MRR**" — P/R/F1@K là CBHD bổ sung thêm (D-181),
     không phải thay thế yêu cầu MRR của đề cương.
  2. `tests/test_mrr_metric.py` import thẳng `reciprocal_rank()` (xem mục 2) —
     xóa hàm này làm vỡ test đó.
  3. Toàn bộ `CLAUDE.md`/decision log hiện tại báo cáo MRR và R@1 (K=1) làm số
     liệu đầu bảng (D-180: "MRR 0,8038→0,7972", "R@1 0,7083"; D-82: "hybrid hoà
     tuyệt đối với BM25 ở R@1") — bỏ mất nghĩa là không tái lập được các phát
     hiện này cho báo cáo.
  MRR tính trên cùng vòng lặp per-câu như P/R/F1 (không phải bảng riêng), in
  cùng dòng mỗi cấu hình trong `retrieval_report.csv`/`.md`.
- K ∈ {1, 3, 5, 10, 20}. Với mỗi câu `van_ban`/`hinh`: gold = tập chunk hiện có
  trong index cùng `(source_book, source_page)` — đếm TẠI THỜI ĐIỂM CHẠY (không
  lưu cứng lúc sinh test, tránh lệch nếu index đổi giữa hai lượt).
  `Precision@K = |gold ∩ top-K| / K`, `Recall@K = |gold ∩ top-K| / |gold|`,
  `F1@K` điều hòa từ hai số trên.
  **SỬA SAU PHẢN BIỆN LẦN 2**: bản thiết kế trước ghi "gold rỗng ở `van_ban`/
  `hinh` → raise ngay" — SAI, và thoái lui so với logic ĐÃ KIỂM CHỨNG trong
  chính `ablation.py` sắp xóa (`_gold_key()`/dòng ~500-520,
  `git show f24ad4e4:src/test/ablation.py`). Code cũ phân biệt **BA** trường hợp,
  không phải hai, và không raise ở trường hợp nào:
  1. `_gold_key(row) is None` (không có `source_book`/`source_page`) → nhóm
     `ngoai_pham_vi`, đúng thiết kế.
  2. Có gold key nhưng trang đó **0 chunk trong index hiện tại** → nhóm
     **`suy_bien`** (khuyết dữ liệu — khác `ngoai_pham_vi`, KHÔNG được gộp
     chung, xem lý do dưới). Loại khỏi mẫu tính P/R/F1/MRR (mẫu số `so_cau` chỉ
     đếm nhóm 3), nhưng đếm và **báo cáo rõ số lượng** qua cột
     `suy_bien_gold_0_chunk` — không raise, không im lặng.
  3. Có gold key và ≥1 chunk → tính P/R/F1/MRR bình thường.
     Chính comment gốc trong code cũ giải thích vì sao KHÔNG được gộp (2) vào
     (1): *"`_n_gold_chunks == 0` cho cả hai thì ca thứ hai bị ÂM THẦM đổi nhãn
     thành 'ngoài phạm vi' và chui vào mẫu số của tỉ lệ từ chối đúng, đồng thời
     `so_cau` tụt đi mà không ai biết — đúng loại fallback im lặng Nguyên tắc 5
     cấm."* Giữ nguyên logic này khi viết `retrieval_benchmark.py` — đây là quy
     tắc đã được nghĩ kỹ và đo đúng (0/270 câu rơi vào `suy_bien` trên corpus
     hôm nay), không phải chỗ để tự sáng tạo lại từ đầu.
- `ngoai_pham_vi`: tách hẳn khỏi bảng P/R/F1 (không có gold) — đo riêng **tỉ lệ
  từ chối đúng ở tầng truy xuất**. **Còn mở, cần quyết định lúc lập kế hoạch
  triển khai**: bảng `ablation_report_240.csv` cũ có cột này cho cả 4 cấu hình
  (kể cả rerank=off), nhưng `RERANK_SCORE_MIN` chỉ có nghĩa khi rerank BẬT —
  chưa rõ cơ chế cũ định nghĩa "từ chối đúng" thế nào cho cấu hình rerank=off
  (điểm BM25/dense thô không cùng thang với điểm rerank). Đề xuất tạm: chỉ tính
  tỉ lệ này cho `de_xuat` (cấu hình production, có `RERANK_SCORE_MIN` làm mốc
  rõ ràng); 3 cấu hình còn lại ghi `n/a` thay vì bịa một ngưỡng chưa có căn cứ đo
  — **không lặp lại đúng lỗi mà `_ngoai_pham_vi_meta.json` cũ đã tự phát hiện và
  sửa** (một cảnh báo viết theo phỏng đoán thay vì phép chạy thật).
- Output: `src/test/testset/retrieval_report.csv` + `.md`.

---

## 4. Cổng người duyệt (bắt buộc, dùng chung cho cả `run_eval.py` và
`retrieval_benchmark.py`)

Hàm này sống ở `src/test/testset_common.py` (module dùng chung, KHÔNG thuộc
`build_testset.py` — hai script đọc-CSV không nên import lẫn nhau qua entrypoint
của script kia). `src/test/llm_client.py` cũng có thể ở cùng module này hoặc
đứng riêng — bên triển khai quyết định, miễn không tạo import vòng.

```python
def require_human_reviewed(meta_path: Path, allow_draft: bool = False) -> None:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if not meta.get("human_reviewed") and not allow_draft:
        raise SystemExit(
            f"{meta_path} chưa được duyệt tay (human_reviewed=false).\n"
            f"Đọc lại src/test/testset/draft.csv, sửa câu/ground_truth sai, "
            f"rồi chạy: python -m src.test.build_testset --mark-reviewed\n"
            f"(Chỉ dùng --allow-draft để tự kiểm code của CHÍNH BẠN, không dùng "
            f"số ra từ --allow-draft cho báo cáo.)")
```

Giống hệt tinh thần cổng review ảnh đã có (`--export-image-review` /
`--apply-image-review`) và quy trình 48 câu hình D-170 (người đối chiếu trực
tiếp, sửa 70,8% câu) — không phải cơ chế mới, chỉ áp dụng lại cho bộ test toàn
bộ thay vì riêng phần hình.

---

## 5. Kế hoạch test (cho code MỚI, không phải bộ test 240 câu)

**SỬA SAU PHẢN BIỆN LẦN 4**: bản trước đặt test mới ở `tests/test/...` — thư mục
này KHÔNG tồn tại và không khớp quy ước hiện có. Đã kiểm `tests/`: mọi test liên
quan `src/test/` từ trước tới nay nằm PHẲNG ở gốc `tests/`
(`tests/test_build_testset_240.py`, `tests/test_mrr_metric.py`,
`tests/test_evaluator_cli.py`...), các subdir hiện có chỉ là `tests/app`,
`tests/book`, `tests/etl`, `tests/js`, `tests/layout`, `tests/rag` — không có
tiền lệ `tests/test/`. Đặt 3 file test mới PHẲNG ở gốc `tests/`, đúng quy ước:

- `tests/test_build_testset_sampling.py`: mock `chromadb` client trả về
  N id giả; assert `n_van_ban + n_hinh + n_ngoai_pham_vi == n_total`, tỉ lệ
  `p_hinh` tính đúng công thức, cùng `seed` ra cùng tập id (tái lập được), seed
  khác ra tập khác (không phải hardcode). Thêm case: ánh xạ trường ảnh
  `pdf_filename`/`page_number` → `source_book`/`source_page` (mục 3.1, sửa sau
  phản biện lần 4) — assert một dòng `hinh` giả không bao giờ có
  `source_book`/`source_page` rỗng khi metadata nguồn có `pdf_filename`/
  `page_number` hợp lệ.
- `tests/test_review_gate.py`: `human_reviewed=false` → `require_human_reviewed`
  raise; `=true` → không raise; `--allow-draft` bỏ qua nhưng phải in cảnh báo
  (assert cảnh báo có trong stdout/log) VÀ file output mang hậu tố
  `_NHAP_CHUA_DUYET` (mục 3.2, sửa sau phản biện lần 4).
- `tests/test_retrieval_benchmark_metrics.py`: P/R/F1@K trên fixture tự tạo
  (không cần ChromaDB thật) — case tay: gold ⊆ top-K (P/R/F1 = giá trị tay tính
  trước), gold ∩ top-K = ∅ (P/R/F1 = 0.0). Test riêng cho phân loại 3 nhóm
  (mục 3.3 đã sửa sau phản biện lần 2): `_gold_key(row) is None` → `ngoai_pham_vi`;
  có gold key + `_n_gold_chunks == 0` → `suy_bien`, loại khỏi mẫu P/R/F1, có mặt
  trong `suy_bien_gold_0_chunk`; có gold key + `_n_gold_chunks > 0` → tính bình
  thường. Không có case nào raise ở đây.
- KHÔNG viết test end-to-end gọi Groq/Qwen thật (tốn quota, chậm) — việc đó xác
  nhận bằng một lượt `--n 6` chạy tay trước khi chạy `--n 240` thật, giống thói
  quen `--dry-run` cũ.

---

## 6. Dọn dẹp đi kèm (làm SAU khi code xong + chạy thử `--n 6` thành công, đúng
"định nghĩa xong" của CLAUDE.md — không làm trước)

1. **`document/decision_log.html`**: thêm `D-182` — ghi rõ: hủy cấu trúc
   240-câu-cố-định-theo-quyển của D-181 (lý do: phát hiện nhóm Hình chấm thấp bất
   thường mà mẫu nhỏ không đủ chẩn đoán + quyết định của người dùng chuyển sang
   lấy mẫu ngẫu nhiên thật), liệt kê file đã xóa/đổi tên, số đo lượt `--n 6` thử
   nghiệm.
2. **`CLAUDE.md`**: viết lại toàn bộ mục "Cấu trúc đánh giá mới theo yêu cầu CBHD
   (D-181)" theo thiết kế này (đổi tiêu đề thành D-182 hoặc nối thêm), cập nhật
   mục "Lệnh" (`## Đánh giá (trong src/test/)`) — thay hết lệnh cũ trỏ tới bất kỳ
   file nào đã xóa ở mục 2 (`generate_testsets.py`, `evaluator.py`, `ablation.py`,
   `recall_at_k.py`, `build_testset_240.py`, `build_image_questions.py`,
   `ablation_multimodal.py`, `bm25_sweep.py`, `review_testset.py`,
   `prompt_scope_probe.py`, `qa_citation_page.py`) bằng 3 lệnh mới hoặc xóa dòng
   lệnh nếu chức năng không còn. Cập nhật
   bảng "Trạng thái tiến độ" — dòng "Bộ test câu hỏi", "Đánh giá đầu-cuối", ghi rõ
   số 240/270 câu cũ đã lỗi thời, đang chờ lượt đo mới.
3. **Memory** (`C:\Users\lcdkhoa\.claude\projects\D--personal-repo-project-rag\memory\`)
   — theo đúng quy tắc "sửa file cũ, đánh dấu HISTORICAL, đừng tạo file 2":
   - `eval_structure_revision_2026_09.md` — nội dung mô tả TOÀN BỘ D-181 cũ đã bị
     thay thế hoàn toàn bởi thiết kế này → viết lại nội dung file này để mô tả
     quyết định MỚI (D-182), không tạo file mới.
   - `rag_eval_harness.md` — phần mô tả `evaluator.py --book/--bo-qua-da-co` và
     bảng 231 câu cần đánh dấu `HISTORICAL:`; phần G1-G5 (gates ETL, không liên
     quan LLM-judge) giữ nguyên.
   - `demo_and_eval_constraints.md` — constraint TPM/TPD của Groq vẫn đúng (không
     đổi hạ tầng), chỉ sửa tên file `eval_llm.py` → `llm_client.py` ở mọi chỗ
     nhắc tới.
   - `multimodal_ablation_m2c.md` — dùng `ablation_multimodal.py` (đã xóa) →
     đánh dấu `HISTORICAL:` toàn file.
   - `m2_plan_two_tracks.md` — phần nhắc `ablation.py`/bộ 300 câu cũ → đánh dấu
     `HISTORICAL:` đoạn liên quan, giữ phần còn lại (quyết định hybrid mặc định
     D-82 vẫn đúng, không đổi).
   - `thesis_report_and_goals.md` — thêm một dòng: số liệu 240/270 câu (D-173..
     D-175) đã lỗi thời do D-182, chờ lượt đo mới trước khi viết lại báo cáo.
   - `colab_runbook_and_env.md` — mô tả lịch sử bug D-166..D-174 của
     `colab_runtime_eval.ipynb` khi nó còn gọi `evaluator.py`/`build_testset_240.py`
     cũ; các bài học về giới hạn TPM/TPD và mtime-drift vẫn đúng (giữ), nhưng phần
     mô tả CELL/SCRIPT cụ thể cần cập nhật theo notebook đã vá ở mục 4 dưới đây.
   - Cập nhật `MEMORY.md` (index) cho khớp mô tả mới của từng file.
4. **`document/colab_runtime_eval.ipynb`**: sửa mọi cell gọi
   `evaluator.py`/`ablation.py`/`build_testset_240.py`/`build_image_questions.py`
   sang `build_testset.py`/`run_eval.py`/`retrieval_benchmark.py`. Đây là runbook
   người dùng THỰC SỰ chạy — một dòng sai ở đây đắt hơn sai trong spec.
5. **`src/test/README.md`** (tìm ra ở phản biện lần 3, bỏ sót ở 2 lượt trước):
   mô tả chi tiết toàn bộ pipeline cũ (`generate_testsets.py`, `evaluator.py`,
   `metrics.py`, `eval_llm.py`, `testsets/`, `ablation_report.csv`...). Sau khi
   xóa hết các file nó mô tả, README trở thành một nguồn sự thật thứ hai hoàn
   toàn sai (vi phạm nguyên tắc 6) — và đây là file đầu tiên ai đó mở khi vào
   `src/test/`, nên sai ở đây dễ gây nhầm hơn một dòng CLAUDE.md sai. Viết lại
   theo 3 script mới trong cùng lượt dọn dẹp này.

Rồi mới **commit** (message thuần, không `Co-Authored-By`, theo quy tắc repo).

---

## 7. Rủi ro đã cân nhắc

- **Mất hẳn cổng đo deterministic G3** (tìm ra ở phản biện lần 3): xóa
  `qa_citation_page.py` (mục 2) làm repo mất năng lực duy nhất đo "trang được
  trích dẫn có thực sự chứa câu trả lời không" bằng phương pháp KHÔNG cần LLM
  (IDF-weighted token coverage). `run_eval.py` mới chỉ có LLM-judge
  (correctness/faithfulness/relevancy) — khác chiều đo, không thay thế được G3.
  CHẤP NHẬN theo quyết định người dùng (mục 2, item 8 blockquote đầu file), ghi
  lại ở đây để không ai hiểu nhầm là bỏ sót khi trình bày với CBHD.

- **Quota Groq**: sinh câu (≤240 lệnh gọi) + chấm điểm (240 lệnh) dùng chung
  `llm_client.py` (4 model × 200k token/ngày = 800k/ngày) — nhỏ hơn nhiều so với
  lượt 240 câu từng dùng hết TPD ở D-173 (lượt đó chỉ có 2 model). Vẫn nên chạy
  sinh câu và chấm điểm ở hai buổi khác nhau nếu lo ngại, không bắt buộc một lượt.
- **Câu hỏi/ground_truth chất lượng thấp do rút ngẫu nhiên trúng đoạn/ảnh nghèo
  nội dung**: đã có bộ lọc độ dài chunk (≥200 ký tự) + lọc ảnh có nhãn/chữ, và
  quan trọng nhất là **cổng người duyệt bắt buộc** (mục 4) — không dùng thẳng
  nháp LLM như một phần của D-181 cũ đã làm với 30 câu ngoài-phạm-vi.
  (`_ngoai_pham_vi_meta.json` cũ ghi rõ `human_reviewed: false` — đúng bài học
  cần tránh lặp lại.)
- **Không ràng buộc phủ quyển** có thể ra một lượt mà 1-2 quyển nhỏ không có câu
  nào — CHẤP NHẬN theo quyết định của người dùng; đây là test-set coverage, khác
  với corpus coverage (12/12 quyển vẫn nằm trong index, không đổi).
- **Thời gian chạy `run_eval.py --n 240`**: không đổi so với `evaluator.py` cũ vì
  vẫn gọi đúng pipeline RAG thật cho từng câu — máy dev (GPU 4 GB) từng đo
  ~3-3,5 phút/câu → 240 câu ước **12-14 giờ**; Colab nhanh hơn nhiều (xem
  `document/colab_runtime_eval.ipynb`). Không phải rủi ro MỚI do thiết kế này,
  nhưng cần tính vào lịch trước hạn 23/09.
- **Gold page mất chunk sau khi sinh test** (index bị OCR lại/reset): KHÔNG làm
  `retrieval_benchmark.py` dừng cả lượt (đã sửa ở mục 3.3, phản biện lần 2) —
  câu đó rơi vào `suy_bien`, bị loại khỏi mẫu P/R/F1 nhưng vẫn hiện số lượng rõ
  ràng trong báo cáo. Nếu số này lớn bất thường (nhiều hơn vài câu), đó là dấu
  hiệu nên sinh lại test set sau khi bump `TEXT_EXTRACTION_VERSION`/
  `IMAGE_EXTRACTION_VERSION`, nhưng đây là quyết định của người đọc báo cáo, script
  không tự raise.

---

## 8. Trạng thái bàn giao / việc còn lại

Tại thời điểm viết spec này: **CHƯA CÓ FILE CODE NÀO được tạo/xóa** — đây là bước
thiết kế, chưa triển khai. `git status` vẫn như đầu hội thoại
(`?? src/test/eval_240_results/`).

Việc còn lại theo đúng thứ tự:
1. ~~Phản biện spec~~ XONG — 3 lượt:
   - Lượt 1 (tự phản biện): 6 vấn đề — đã sửa inline.
   - Lượt 2 (tự phản biện): 1 vấn đề nghiêm trọng (mục 3.3: bản trước bịa ra
     "raise khi gold rỗng", thoái lui so với logic `suy_bien` đã kiểm chứng
     trong `ablation.py` cũ) + 4 vấn đề nhỏ — đã sửa inline.
   - **Lượt 3 (subagent độc lập, đọc trực tiếp nội dung thật của mọi file sắp
     xóa + grep import trên `tests/`)**: 2 vấn đề nghiêm trọng mới — (a) 9 file
     trong `tests/` import thẳng các module sắp xóa, chưa từng được nhắc tới ở
     2 lượt trước, sẽ làm `pytest tests/` vỡ ImportError; (b) thiết kế
     `retrieval_benchmark.py` làm mất hẳn MRR/K=1 dù `goal.docx` (RULE #0) yêu
     cầu đích danh MRR — cả hai đã sửa inline (mục 2, mục 3.3). Cộng 2 vấn đề
     trung bình (mất cổng G3 không ghi nhận là đánh đổi; `src/test/README.md`
     thiếu trong danh sách dọn dẹp) + 1 vấn đề nhỏ (`report_numbers.py` default
     path) — đã sửa inline (mục 6, mục 7).
   - **Lượt 4 (subagent độc lập thứ hai, truy vấn trực tiếp DB Chroma thật thay
     vì tin mô tả)**: 2 vấn đề nghiêm trọng mới — (a) `biology_image_metadata`
     dùng khoá `pdf_filename`/`page_number`, KHÔNG PHẢI `source`/`page` như
     `biology_text` — bản trước chưa đặc tả ánh xạ này, rủi ro làm cả nhóm Hình
     bị gán nhầm `ngoai_pham_vi` một cách âm thầm; (b) 3 script `scripts/*.ps1`
     (`run_ablation.ps1`, `run_testsets.ps1`, `sau_etl_anh.ps1`) gọi thẳng module
     sắp xóa qua dòng lệnh PowerShell — lớp phụ thuộc mà grep `import` Python của
     lượt 3 không bắt được. Cộng 3 vấn đề trung bình (bảng ánh xạ import
     `test_ablation_cache.py` thiếu 4/6 tên cần export + chi tiết monkeypatch;
     thiếu trần tổng cho cơ chế rút-thay-thế khi LLM lỗi liên tục; file
     `--allow-draft` không tự đánh dấu trong tên file) + 2 vấn đề nhỏ (đường dẫn
     test mới `tests/test/` không tồn tại, đúng ra là `tests/` phẳng;
     `.count()` không nhận filter + hai bước đếm/lấy-mẫu dùng bộ lọc lệch nhau).
     Tất cả đã sửa inline (mục 2, mục 3.1, mục 3.2, mục 5).
   Bài học xuyên suốt cả 4 lượt: "viết lại từ 0" không có nghĩa bỏ qua logic đã
   đúng trong code cũ, bỏ qua AI đang phụ thuộc ngược vào nó (kể cả qua dòng lệnh
   PowerShell, không chỉ `import` Python), hay suy đoán schema thay vì truy vấn
   DB thật. Phải đọc trực tiếp `git show <commit>:<path>`, grep TOÀN REPO (không
   chỉ thư mục "rõ ràng liên quan"), và truy vấn artefact thật trước khi coi một
   file là an toàn để xóa hoặc một trường dữ liệu là tồn tại.
2. **Bước dùng-chung, làm TRƯỚC khi chia subagent** (khoảng trống tìm ra ở lượt
   phản biện này): đổi tên `eval_llm.py` → `llm_client.py` + xóa toàn bộ file ở
   mục 2 là việc CẢ HAI agent ở bước 4 đều đụng tới (`llm_client.py` dùng chung
   cho sinh câu VÀ chấm điểm) — nếu để mỗi agent tự làm sẽ đụng nhau/làm hai lần.
   Làm bước này một lần, tuần tự, TRƯỚC khi tách việc, không giao cho subagent.
3. `writing-plans` → kế hoạch triển khai chi tiết.
4. Triển khai phần còn lại (đúng quy tắc CLAUDE.md: việc lớn ≥2 phần độc lập
   theo file → tối đa 2 subagent Sonnet 5 song song + 1 Opus 5 phản biện trước
   khi báo xong — `build_testset.py` và `retrieval_benchmark.py`+`run_eval.py`+
   `testset_common.py` là hai phần tách file rõ ràng, có thể chia SAU bước 2).
5. Chạy thử `--n 6`, xác nhận bằng mắt.
6. Chạy thật `--n 240`, người dùng duyệt tay.
7. Mục 6 (dọn dẹp decision log/CLAUDE.md/memory/notebook) + commit.
