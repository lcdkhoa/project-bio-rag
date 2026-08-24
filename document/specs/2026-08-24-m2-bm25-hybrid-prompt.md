# Prompt cho lượt sau — M2: BM25 + truy xuất lai (thưa + dày)

> **Đọc trước khi làm bất cứ gì:** `CLAUDE.md` RULE #0 và mục "Định nghĩa xong".
> Nguồn yêu cầu duy nhất là `document/goal.docx` (Đề cương ĐỒ ÁN TỐT NGHIỆP, ký
> 13/07/2026). Thiết kế tổng thể: `2026-08-22-12books-3publishers-etl-rebuild.md`.
> Trạng thái M0/M1: `2026-08-23-m0-report.md`, `2026-08-23-m0-toc-and-layout-prompt.md`.
>
> **Tinh thần bắt buộc:** phản biện chính mình. Mỗi con số phải chạy ra được; mỗi
> giả thuyết chưa đo là một **câu hỏi mở**, không được lặng lẽ thành thiết kế. Khi
> một phép đo bác bỏ điều mình vừa viết, **sửa ngay trong cùng lượt** và ghi rõ nó
> đã sai ở đâu.

---

## 0. Trích nguyên văn đề cương — đây là hợp đồng, không phải diễn giải

**Mục tiêu 3:** "Tối ưu hóa luồng xử lý đa phương thức (văn bản + hình ảnh), cải
thiện các cơ chế **định tuyến truy vấn, truy xuất lai và xếp hạng lại** nhằm thu
hẹp khoảng cách recall và nâng cao độ chính xác."

**Mục tiêu 4:** "…thực hiện so sánh hiệu năng trực tiếp giữa: **Truy xuất lai so
với truy xuất truyền thống dựa trên từ khóa (BM25)**. **Hệ thống RAG đa phương thức
so với hệ thống RAG chỉ sử dụng văn bản**."

**Nội dung 2 — "Nâng cấp kiến trúc Multi-modal RAG và cơ chế truy xuất lai":**
*"Đây là nội dung trọng tâm thể hiện đóng góp phương pháp của đề tài."*

> - Định tuyến theo ý định truy vấn: phân loại câu hỏi để ưu tiên luồng văn bản hay
>   hình ảnh, tránh đưa nhiễu vào ngữ cảnh.
> - Truy xuất lai: kết hợp tìm kiếm theo từ khóa (**BM25 [13]**) và tìm kiếm ngữ
>   nghĩa dày đặc (**dense passage retrieval [14]**) để không bỏ sót các truy vấn
>   chứa **thuật ngữ khoa học đặc thù**.
> - Cổng lọc liên quan kết hợp bổ sung bước xếp hạng lại (re-ranking, ví dụ
>   cross-encoder) nhằm đưa trang chứa nội dung đúng lên đầu danh sách mà vẫn giảm
>   nhiễu ngữ cảnh.
> - Hợp nhất kết quả văn bản và hình ảnh, dựng prompt và sinh câu trả lời bằng LLM
>   (Qwen2.5 [12]).

**Nội dung 4:** "So sánh đối chiếu trên cùng một bộ testset: (i) truy xuất lai so
với **BM25 thuần**, (ii) RAG đa phương thức so với **RAG chỉ văn bản**, kèm nghiên
cứu loại bỏ thành phần **bật/tắt re-ranking và cổng lọc liên quan**."

**Hệ quả đọc kỹ, đừng đọc lướt:**

1. **Ba điểm đều là hợp đồng, không phải hai.** Nội dung 4(i) chỉ viết "truy xuất
   lai so với BM25 thuần", nhưng **bảng Kế hoạch thực hiện — Giai đoạn 3** viết rõ:
   *"thực nghiệm so sánh cấu hình 1: **BM25 thuần túy vs. Vector Retrieval vs.
   Hybrid Search**"*. Vậy dense thuần **cũng** nằm trong hợp đồng. (Bảng kế hoạch là
   một **bảng LỒNG** trong ô "Kế hoạch thực hiện" nên `python-docx` không đọc tới
   nó qua `Document.tables` — phải đọc `word/document.xml`. Lượt viết đầu của file
   này đã bỏ sót nó và kết luận sai rằng chỉ có hai điểm.)
2. Lý do BM25 được nêu là **"thuật ngữ khoa học đặc thù"** — tức chính chỗ mà
   D-56/D-73 đo được là hỏng nặng nhất (`CO2` không khớp `CO,`). Nên BM25 và việc
   chuẩn hoá chỉ số dưới là **cùng một bài toán**, không phải hai việc rời.
3. "Cổng lọc liên quan **kết hợp** re-ranking" — hai thành phần, và Nội dung 4 đòi
   ablation **bật/tắt từng cái**, tức 4 tổ hợp, không phải 2.

**Bảng Kế hoạch thực hiện — trích nguyên văn (bảng LỒNG, đọc từ `word/document.xml`):**

| Giai đoạn | Thời gian | Nội dung (rút gọn) |
|---|---|---|
| 1 | 15/07 – **29/07/2026** | thu thập + chuẩn hoá dữ liệu **PDF** 12 quyển; ETL text + công thức + OwlViT; **chạy Vintern-1B sinh mô tả ảnh**; lập chỉ mục → *"Kho Vector hoàn chỉnh (Văn bản + **Hình ảnh có chú thích**)"* |
| 2 | 30/07 – **13/08/2026** | **Hybrid Search (BM25 + Vector Dense)**; xếp hạng lại; **sinh testset có nhãn nguồn** → *"Bộ truy xuất Hybrid hoạt động ổn định"* |
| 3 | 14/08 – **28/08/2026** | cấu hình 1: **BM25 thuần vs Vector Retrieval vs Hybrid**; cấu hình 2: **Text-only vs Multi-modal**; LLM-as-a-judge |
| 4 | 29/08 – **12/09/2026** | **prompt engineering cho môn Lý, Hoá, Sinh**; hoàn thiện FE Next.js + hiển thị công thức |
| 5 | 13/09 – **23/09/2026** | tổng hợp số liệu, viết báo cáo, slide + video demo |

**M2 CHÍNH LÀ Giai đoạn 2, đáo hạn 13/08/2026. Hôm nay 23/08 → trễ 10 ngày**, và
Giai đoạn 1 (đáo hạn 29/07) vẫn còn nợ phía ảnh. Khi báo cáo tiến độ phải nói theo
mốc này, không nói theo cảm tính.

---

## 1. ĐÃ ĐO — dùng luôn, TUYỆT ĐỐI KHÔNG đo lại

### 1.1 Corpus và index (2026-08-23, D-65/D-73)

| | số đo |
|---|---|
| corpus | **12 quyển / 3 NXB / 2 399 trang**, 0 khoảng trống, `page_001` trở đi |
| `offset` | **0 ở 12/12 quyển** (`printed_page == số trong tên file`) |
| manifest | **12/12** ở `database/manifests/KHTN{6..9}-{KNTT,CTST,CD}.json` |
| index text | **16 393 chunk**, 2 387 trang có chunk (12 bìa bị bỏ đúng thiết kế) |
| chunk/trang | 5,68 (6_KNTT) → 8,26 (9_CTST) |
| ký tự/chunk | 252–288 (`CHUNK_SIZE=400`, `overlap=120`) |
| thời gian | manifest **49 phút**; `--text-only` **3 giờ 20** = **5,0 s/trang** |
| embedding | `BAAI/bge-m3` (1024 chiều) |

Kích thước ảnh: KNTT **1094×1536**, CTST/CD **2280×3201**, 6_CD **2480×3480**.
KNTT là bộ **phân giải THẤP NHẤT**, không phải bộ tham chiếu.

### 1.2 Chỉ số dưới — phép đo BÁC BỎ giả thuyết cũ (D-73)

Đếm trên **chính chữ đã index** (không cần OCR lại):

| NXB | chunk | token hỏng `X,` | đọc đúng `X2` | `₂` Unicode |
|---|---|---|---|---|
| CD | 5 282 | **256** | 3 | **0** |
| CTST | 6 177 | **377** | 3 | **0** |
| KNTT | 4 934 | **408** | 4 | **0** |

Token hỏng phổ biến, giống nhau ở cả ba NXB: `O,` 78/121/138 · `SO,` 52/48/43 ·
`CO,` 30/49/88 · `H,O` 25/50/44 · `CH,` 30/41/60 · `H,SO,` 5/14/21 · `N,` 36/54/14.

**Kết luận đã chốt:** chỉ số dưới **không sống sót ở bất kỳ độ phân giải nào**
(~85:1 CD, ~126:1 CTST, ~102:1 KNTT). D-56 **không** phải artefact của KNTT
1094×1536 → "bước xử lý đặc thù cho công thức Hoá, Lý" là **MỘT LUẬT CHUNG**, không
chia theo nhà xuất bản. Đừng đo lại điều này.

### 1.3 Hai giới hạn của index hiện tại, phải nhớ khi đọc mọi số

- **`bai_so` chỉ có ở 4 quyển KNTT** (1 086 / 1 037 / 1 212 / 1 522 chunk). 8 quyển
  CTST/CD **không chunk nào** có, vì spine Bài chưa liền mạch (CTST đọc được
  23/17/17/21 Bài, CD 32/24/23/29) → mọi truy vấn/lọc theo Bài chỉ chạy trên **1/3
  kho**. Đây là hệ quả của M1 chưa xong, **không** phải lỗi index.
- **`needs_review` bật ở 57–84% chunk** (9_CD 1 339/1 590 = 84%). Ở mức đó cờ này
  **gần như không mang tin** — không được dùng nó làm điều kiện lọc trong M2 trước
  khi hiệu chỉnh lại ngưỡng, và nếu hiệu chỉnh thì phải có before/after.

### 1.4 Kiến trúc truy xuất hiện có (đọc code trước khi sửa)

```
src/rag/hybrid_retriever.py::HybridRetriever.search(query) -> SearchResult
  ├─ query_intent.is_image_only_query()   # ĐỊNH TUYẾN: câu chỉ-ảnh bỏ hẳn text
  ├─ text:  RelevanceGatedRetriever (vectorstore.py:30) -> RerankedRetriever (:79)
  └─ image: CLIP + metadata + kênh cụm từ (accent-sensitive) + rerank
src/rag/chain.py::BiologyRAG            # prompt + Qwen2.5
src/app/api.py                          # gắn citations deterministic
```

Tham số mặc định đang chạy (`src/config.py`): `RETRIEVER_FETCH_K=8`,
`RETRIEVER_MAX_K=4`, `RETRIEVER_DISTANCE_MARGIN=0.3`, `RERANK_ENABLED=true`,
`RERANK_MODEL=BAAI/bge-reranker-v2-m3`, `RERANK_FETCH_K=20`, `RERANK_SCORE_MIN=0.2`.

**"Hybrid" trong tên `HybridRetriever` là lai TEXT+ẢNH, KHÔNG phải lai THƯA+DÀY.**
`grep -riE "bm25|rank_bm25|sparse" src/` = **0 kết quả**. `rank_bm25` **chưa** có
trong môi trường (`import rank_bm25` → ImportError); `underthesea` và `pyvi` cũng
**chưa** có. `sklearn` thì có.

### 1.5 Ba khiếm khuyết đã đọc thấy trong code, chưa sửa — chúng thuộc M2

1. **`chain.py` khoá cứng "trợ lý AI môn Sinh học THCS"** trong system prompt, trong
   khi phạm vi hợp đồng là **cả Lý – Hoá – Sinh** (Mục tiêu 2). Một câu hỏi Vật lý
   đang được trả lời bởi một trợ lý tự nhận là dạy Sinh học.
2. **`api.py:95` dựng ngữ cảnh CHỈ từ `text_docs`**; `image_docs` chỉ ra gallery.
   Nên ablation "**đa phương thức vs chỉ văn bản**" của Nội dung 4(ii) hiện sẽ ra
   chênh lệch **bằng 0 THEO CẤU TRÚC** — không phải vì đa phương thức vô ích.
3. **`chain.py::format_docs` bỏ mọi đoạn ngắn hơn 40 ký tự** (`len(content) > 40`).
   Với chunk trung bình ~250 ký tự thì phần lớn không ảnh hưởng, nhưng một định
   nghĩa ngắn hoặc một dòng công thức có thể bị **bỏ im lặng**. Phải đo xem có bao
   nhiêu chunk trong index ngắn hơn 40 ký tự trước khi kết luận là vô hại.

---

## 2. MƯỜI QUYẾT ĐỊNH ĐÃ CHỐT (D-74, 2026-08-24) — không mở lại

Người dùng đã quyết mọi chỗ đề cương cấn với số đo. **Không được tự ý làm khác;
nếu một phép đo mới lật một quyết định thì HỎI LẠI, đừng tự đổi.**

| # | Chốt | Việc phải làm trong báo cáo / code |
|---|---|---|
| 1 | **Bỏ Vintern-1B** | Xem §2.1 — chẩn đoán lại đúng bệnh, và bốn đường thay thế |
| 2 | **Giữ `bge-m3` 1024 chiều** | Báo cáo ghi rõ đã đổi khỏi "384 chiều" của đề cương **kèm lý do** (bge-m3 mạnh hơn trên tiếng Việt; đổi lại = dựng lại index 3 giờ 20, hai số chiều không dùng chung collection). Đổi số chiều là hệ quả hiển nhiên của đổi model |
| 3 | **Nguồn là PNG một trang/file**, không phải PDF | Sửa mọi câu "dữ liệu PDF" trong báo cáo. Ưu điểm thật: lossless, không có bước render, không mất chi tiết |
| 4 | **Báo cáo recall theo NHÓM CÂU HỎI** | Ngoài recall tổng, thêm recall trên nhóm **có công thức / thuật ngữ đặc thù** — đúng lý do đề cương nêu BM25. Nếu recall tổng đã sát trần thì bảng "hybrid vs BM25" sẽ chênh rất nhỏ và **đóng góp thật bị che** |
| 5 | **Sửa cách đo precision** | Xem §2.2 |
| 6 | **Người duyệt tay ~50 câu** của bộ test | Công bố tỉ lệ gold key sai kèm **mọi** bảng số. Biến một điểm yếu thành một con số |
| 7 | "Chứng minh sự vượt trội" là **định hướng** | Phải có cải tiến thật, nhưng **báo cáo đúng số đo** — kể cả khi một phân môn không thắng. Không nắn số cho khớp đề cương |
| 8 | **Chạy liên tục**, ưu tiên việc không cần trông | Xem §2.3 |
| 9 | **Thu hẹp phía ảnh** (ảnh là mục đích kèm thêm) | Ablation multi-modal chạy trên **4 quyển KNTT** và **NÓI RÕ là 4 quyển**, không pha loãng bằng 8 quyển không có caption |
| 10 | **Chấp nhận nợ spine Bài** của 8 quyển CTST/CD | Làm BM25 (Giai đoạn 2) trước; quay lại spine sau |

### 2.1 Vintern: chẩn đoán lại — bệnh KHÔNG phải "thiếu caption"

Ca người dùng nêu: chú thích SGK ghi *"đại dương"* nhưng ảnh là **con cá mập**; học
sinh hỏi *"cho tôi hình cá mập trong bài học"*.

**Đọc code ra bệnh thật:** `src/config.py:88` đặt
`CLIP_MODEL = openai/clip-vit-base-patch16` — tháp text của nó **chỉ tiếng Anh**, mà
`image_vectorstore._encode_text` đưa **thẳng truy vấn tiếng Việt** vào tokenizer đó.
Cây cầu Việt–Anh duy nhất là `VIETNAMESE_TO_ENGLISH_VISUAL_HINTS`: **14 mục viết
cứng** (`ca`→fish, `trau`→buffalo, `hoa`→flower, `re`→root…). "cá mập" không có
trong đó, và một từ điển 14 mục **không bao giờ** phủ nổi 12 quyển KHTN.

Vậy **Vintern là cách đi đường vòng quanh một CLIP tiếng-Anh**: biến pixel thành
chữ tiếng Việt bằng một model **SINH** — và sinh là chỗ ảo giác chui vào (D-47: bịa
4/12 crop). Sửa đúng bệnh thì **không cần sinh**.

**Phép đo rẻ đã chạy, và nó đổi thứ tự ưu tiên** (đếm trên 16 393 chunk đã index):

| thuật ngữ | số lần trong chữ đã index |
|---|---|
| `cá mập` | **5** |
| `san hô` | 29 |
| `cá voi` | 8 |
| `đại dương` | 28 |
| `ròng rọc` | 4 |
| `nam châm` | 605 |
| `tế bào` | 1 794 |

**Vốn từ CÓ trong sách** — chỉ không nằm trong *chú thích hình*. Nên cách rẻ nhất
có thể giải quyết phần lớn ca này **mà không cần model nào**.

**Bốn đường, xếp theo giá và rủi ro. Không đường nào là "sinh mở":**

| | cách | vì sao an toàn | giá |
|---|---|---|---|
| **(a)** | đánh chỉ mục hình **kèm chữ của TRANG/BÀI** chứa nó | không có model, không sinh gì | rẻ nhất, đi kèm M3 |
| **(b)** | **CLIP đa ngữ** (tháp text hiểu tiếng Việt) → truy vấn tiếng Việt đập thẳng vào pixel | là model **truy xuất**: có thể xếp hạng sai nhưng **không thể bịa** | đổi model + dựng lại index ảnh (chỉ phía ảnh) |
| **(c)** | gán nhãn **zero-shot trên VỐN TỪ ĐÓNG lấy từ chính quyển sách**: *"trong N thuật ngữ của Bài này, cái nào khớp ảnh?"* thay vì *"hãy mô tả ảnh"* | đầu ra **thuộc vốn từ của sách** → bịa là **bất khả về cấu trúc**; và kiểm được vì đưa được danh sách ứng viên cho giáo viên xem | công việc mới |
| **(d)** | **human-in-the-loop** | chính đề cương Nội dung 1 đòi nó, và repo **ĐÃ CÓ** (`--export-image-review` / `--apply-image-review`) | công của người |

**Khuyến nghị:** (a) + (d) làm nền → (b) là phép đo để viết vào báo cáo (thay một
model sinh bằng một encoder truy xuất đa ngữ, có số trước/sau) → (c) **chỉ khi** (b)
chưa đủ. **Đừng làm cả bốn một lượt.**

**Phải đo trước khi đổi model:** dựng ~20 câu hỏi dạng *"cho tôi hình X"* trong đó
X là **vật được vẽ nhưng KHÔNG có trong chú thích**, rồi đo recall theo từng kênh
(caption deterministic / chữ trang-Bài / CLIP hiện tại / CLIP đa ngữ). Nếu (a) đã
giải quyết hết thì **không đổi model** — code ít hơn = ít chỗ sai hơn.

**Một điểm đúng đắn phải ghi vào báo cáo:** nếu một thuật ngữ **không xuất hiện ở
đâu trong sách**, thì *"không có trong sách giáo khoa"* là câu trả lời **ĐÚNG**,
không phải thất bại. Hệ thống không được dạy quá sách.

### 2.2 Cách đo precision — đề xuất tốt hơn "giải thích 0,55"

`precision_page` = 0,55 thấp **theo thiết kế**: cổng lọc giữ ~3 chunk, chunk của
trang lân cận vẫn hữu ích nhưng không phải trang vàng. Chỉ giải thích bằng lời thì
người đọc vẫn thấy 0,55. Hai việc **đo được**, làm cả hai:

1. **Tập trang liên quan thay vì một trang vàng duy nhất** — dựng bằng **chính bộ
   so khớp IDF của G3** (`src/test/qa_citation_page.py`, IDF đo trên chính index,
   `COVERAGE_MIN = 0.50` đã hiệu chỉnh bằng phép đo — D-57): một trang được coi là
   liên quan nếu chữ đã index của nó **phủ được đáp án** ở mức đó. **Deterministic,
   không cần LLM**, và tái dùng code đã có phép đo đứng sau.
2. **Trần đạt được của từng câu** — với một trang vàng có `m` chunk và top-`k`,
   precision không thể vượt `min(k, m)/k`. Báo cáo precision **cạnh trần của chính
   nó**, để người đọc thấy 0,55 so với trần 0,6 chứ không phải so với 1,0.

Nói rõ trong báo cáo: cách (1) làm precision **cao lên** so với định nghĩa cũ, nên
**phải báo cáo cả hai định nghĩa** — đổi thước đo rồi chỉ báo con số đẹp là tự lừa.

### 2.3 "Chạy liên tục" nghĩa là gì trong thực tế

Người dùng muốn tận dụng máy 24/24. Việc chia thành hai loại, đừng lẫn:

- **Chạy được không cần trông** (đưa vào máy chạy đêm): dựng chỉ mục BM25 (phút),
  quét `k1 × b`, chạy bảng **12 cấu hình** ablation (CPU, nhiều giờ), và **một
  lượt** OCR lại khi đã gom đủ thay đổi tham số (3 giờ 20).
- **Bị chặn bởi hạn mức ngoài**: sinh bộ test (OpenRouter — hạn mức/ngày **chưa đo
  được**) và LLM-as-a-judge. Việc này **không** chạy 24/24 được; phải chia lô theo
  quyển và kiểm sau mỗi lô.

Thứ tự đề xuất để máy không bao giờ rỗi: dựng BM25 → **trong lúc đó** người duyệt
50 câu (§2, #6) → quét tham số → sinh bộ test theo lô → chạy ablation.

## 3. VIỆC CỦA M2 — theo thứ tự, mỗi việc một tiêu chí nghiệm thu ĐO ĐƯỢC

### 3.1 M2.0 — Chốt lại "sự thật hiện tại" trước khi sửa gì (bắt buộc, ~30 phút)

Không có bước này thì mọi so sánh sau đó không có gốc.

- Chạy `python src/test/recall_at_k.py` và `python -m src.test.qa_citation_page` trên
  index 12 quyển **với bộ test hiện có**, và **ghi rõ** rằng bộ test 100 câu là của
  **4 quyển KNTT corpus CŨ**: gold key của nó trỏ vào số trang theo `offset −1`,
  trong khi index mới là `offset 0`. **Dự đoán phải kiểm chứng, không được giả
  định:** hoặc nó sập gần hết, hoặc nó khớp nhờ trùng hợp — mở ra xem, đừng đoán.
- Nếu bộ test cũ không dùng được (rất có thể), **không** chữa nó. Ghi số "không đo
  được vì lý do X" rồi đi tiếp: bộ test 12 quyển là §3.6.
- Đếm phân bố độ dài chunk (bao nhiêu chunk < 40 ký tự — xem §1.5.3), và số chunk
  có `region_type` rỗng (`citations.py` đọc `region_type`, thiếu nó thì citation
  suy giảm âm thầm).

**Nghiệm thu:** một bảng số "trước M2" được dán vào `document/decision_log.html`,
kèm câu nói rõ số nào **không** đo được và vì sao.

### 3.2 M2.1 — Chỉ mục BM25 (việc chính, dựng ĐƯỢC từ index hiện có, KHÔNG cần OCR lại)

**Thiết kế bắt buộc:**

- Khoá của chỉ mục thưa là **chính `chunk_id` của `biology_text`**
  (`{page_key}_p{page}_c{index}`), để so được **từng chunk một** giữa hai kênh. Không
  được dựng một tập tài liệu riêng với id riêng — hai hệ id là hai nguồn sự thật.
- Chỉ mục thưa là **artefact sinh ra được**, không phải nguồn: nó phải dựng lại từ
  `biology_text` bằng một lệnh, và phải mang **dấu vân của index nguồn** (số chunk +
  `TEXT_EXTRACTION_VERSION`) để phát hiện khi nó cũ hơn index. **Chỉ mục thưa cũ hơn
  index là một cách hỏng âm thầm** — đúng loại D-52 (image doc mồ côi) và loại
  "rerank tắt âm thầm". Phải **fail loudly**, không tự động dùng bản cũ.
- Tách từ tiếng Việt: `underthesea`/`pyvi` **chưa cài**. **Đo trước khi thêm phụ
  thuộc:** so BM25 với (a) tách theo khoảng trắng + hạ chữ thường, (b) tách từ có
  dấu bằng thư viện, (c) thêm bỏ dấu. Nếu (b) không hơn (a) bằng số trên bộ test thì
  **không thêm phụ thuộc** — code ít hơn = ít chỗ sai hơn (nguyên tắc 7).
- **Chuẩn hoá chỉ số dưới CHỈ Ở PHÍA TRUY VẤN VÀ CHỈ MỤC THƯA** (`CO2` ↔ `CO,` ↔
  `CO₂`). **CẤM tuyệt đối sửa chữ đã lưu trong `biology_text`** — đoán lại một chỉ
  số dưới là bịa (CẤM #5, nguyên tắc 1). Phải là một hàm chuẩn hoá **thuận nghịch
  được giải thích**, áp cùng một cách cho cả tài liệu và truy vấn, và phải có phép
  đo riêng: recall của các câu hỏi **có công thức** trước/sau khi bật chuẩn hoá.
  Đây chính là chỗ đề cương nói "không bỏ sót các truy vấn chứa thuật ngữ khoa học
  đặc thù".

**Phản biện phải tự làm trước khi nói xong:**

- Chunk có `overlap=120` trên `CHUNK_SIZE=400`, tức **~30% chữ bị lặp** giữa hai
  chunk kề. BM25 dùng IDF nên phần lặp **làm lệch IDF**. Hãy đo: IDF tính trên
  16 393 chunk chồng lấn so với tính trên **văn bản theo trang** (2 387 trang) khác
  nhau bao nhiêu, và điều đó đổi thứ hạng không?
- BM25 rất nhạy với **độ dài tài liệu** (`b`, `k1`). Không được lấy tham số mặc định
  rồi coi là xong: quét `k1 ∈ {0.9, 1.2, 1.5}` × `b ∈ {0.3, 0.5, 0.75}` trên bộ test
  và **báo cáo bảng**, chọn bằng số.
- Chunk ngắn (< 40 ký tự) và chunk toàn rác OCR từ vùng hình (D-38 cố ý giữ lại) sẽ
  ăn điểm BM25 cao một cách sai. Đo xem chúng có xuất hiện trong top-k không.

**Nghiệm thu:** `python main.py --build-bm25` (hoặc tên tương đương) dựng chỉ mục
cho 16 393 chunk; một lệnh truy vấn trả về top-k **có chunk_id khớp `biology_text`**;
test đơn vị nhỏ chứng minh (a) khoá trùng khớp, (b) chỉ mục cũ hơn index thì **raise**,
(c) hàm chuẩn hoá chỉ số dưới **không** làm thay đổi text đã lưu.

### 3.3 M2.2 — Hợp nhất thưa + dày, giữ nguyên cổng lọc và rerank

- Hợp nhất bằng **RRF** hoặc **điểm chuẩn hoá** — chọn bằng số trên bộ test, không
  chọn bằng cảm tính. RRF không cần chuẩn hoá thang điểm (điểm dày là *khoảng cách*,
  điểm BM25 là *điểm*, hai thang khác bản chất) nên nó là mặc định hợp lý; nhưng
  phải **đo cả hai** rồi mới chốt.
- Thứ tự bắt buộc giữ nguyên: **hợp nhất → cổng lọc liên quan → rerank**. Không được
  thay rerank bằng điểm hợp nhất (đúng như luật đã ghi cho phía ảnh trong CLAUDE.md).
- **Cổng lọc `RETRIEVER_DISTANCE_MARGIN=0.3` là cổng theo KHOẢNG CÁCH DÀY.** Sau khi
  hợp nhất, thứ tự không còn do khoảng cách quyết định → **cổng này có thể trở thành
  vô nghĩa hoặc cắt sai**. Đây là cái bẫy dễ bỏ sót nhất của M2.2: phải đo cụ thể
  cổng lọc còn cắt đúng không, và nếu phải đổi định nghĩa cổng thì ghi rõ đã đổi.
- Mọi thành phần phải **bật/tắt được bằng cấu hình** (`.env`), vì Nội dung 4 đòi
  ablation. Bốn tổ hợp: rerank {on, off} × cổng lọc {on, off}. Cộng ba chế độ truy
  xuất {BM25 thuần, dense thuần, hybrid} → **12 cấu hình**; nếu cắt bớt thì phải
  `log()` ra là đã cắt cái gì, **không được im lặng**.
- **Tự kiểm bắt buộc:** một cấu hình "hybrid" mà tắt cả hai kênh phụ phải cho ra
  **đúng** kết quả của dense thuần. Nếu không thì đường ống có nhánh ẩn.

**Nghiệm thu:** bảng recall@{1,3,5,10} + MRR + precision cho **12 cấu hình** trên
cùng một bộ test, cùng một seed, in kèm số câu hỏi và cách tính; và một dòng nói rõ
cấu hình nào là "đề xuất" và vì sao.

### 3.4 M2.3 — Caption deterministic vào ngữ cảnh (mở đường cho Nội dung 4(ii))

Không có bước này thì ablation "đa phương thức vs chỉ văn bản" **bằng 0 theo cấu
trúc** (§1.5.2), tức một con số **sai mà trông hợp lý** — đúng loại lỗi mà repo này
sợ nhất.

- Ngữ cảnh multi-modal = text chunk + `figure_label` + caption đọc từ **pill/OCR
  deterministic**. **KHÔNG dùng Vintern** (D-47, §2).
- Phải bật/tắt bằng cấu hình, và **đo cả hai chiều**: nó có thể làm *tệ hơn* (thêm
  nhiễu vào ngữ cảnh — chính điều đề cương cảnh báo ở phần định tuyến). Báo cáo cả
  khi nó tệ hơn.
- Cảnh báo phạm vi: caption pill **chỉ đọc được ở 4 quyển KNTT** (kênh pill ra **0
  nhãn** trên 8/12 quyển — D-65). Nên nếu chạy ablation này trên cả 12 quyển thì 2/3
  kho **không có caption** và số đo sẽ bị pha loãng. Hoặc chạy trên 4 quyển KNTT và
  **nói rõ là 4 quyển**, hoặc chờ M3. **Phải chọn có ý thức và ghi ra**, không được
  chạy 12 quyển rồi báo cáo như thể có caption đủ.

### 3.5 M2.4 — Sửa hai khiếm khuyết chặn chất lượng câu trả lời

- **`chain.py`: bỏ "môn Sinh học"** khỏi system prompt, đổi thành KHTN (Lý–Hoá–Sinh)
  theo Mục tiêu 2. Phải có **before/after trên câu hỏi Lý và Hoá** — đừng sửa chuỗi
  rồi tuyên bố cải thiện.
- **`format_docs` bỏ đoạn < 40 ký tự**: đo trước (bao nhiêu chunk bị ảnh hưởng), rồi
  quyết định. Nếu là 0 chunk thì để yên và ghi lại là đã kiểm.

### 3.6 M2.5 — Bộ test 12 quyển (Nội dung 3) — điều kiện để mọi số ở trên có nghĩa

Đây là việc **đứng chắn** trước Nội dung 4: không có bộ test đúng corpus thì mọi
bảng so sánh đều vô nghĩa.

- Nhãn bắt buộc theo đề cương: `phan_mon` (Lý/Hoá/Sinh), `khoi` (6–9), `bo_sach`
  (KNTT/CTST/CD), `do_kho` (trích xuất trực tiếp / suy luận liên kết / tổng hợp đa
  ngữ cảnh), **phân bố đều**.
- Gold key lấy từ **metadata chunk thật** (`source`, `page`) như `_page_payload` đang
  làm, `PAGE_TOLERANCE = 0`. Kiểm 100% gold key trỏ vào trang **có chunk**.
- **RỦI RO ĐÃ BIẾT, phải xử lý trước khi chạy:** OpenRouter free tier — phản hồi
  **không có header `x-ratelimit-*`** và `/api/v1/key` trả `limit: null`, nên **hạn
  mức/ngày là CHƯA ĐO ĐƯỢC** (D-67). 10 lượt liên tiếp không 429 **không chứng minh**
  300 câu sẽ qua. `generate_testsets` hiện chỉ resume theo **quyển**, không theo câu
  → một lần 429 giữa quyển là mất cả quyển. **Hoặc** thêm resume theo câu, **hoặc**
  chạy từng quyển một và kiểm tra sau mỗi quyển. Đừng phóng 300 request rồi hy vọng.
- `.env` hiện tại: `EVAL_LLM_BASE_URL=https://openrouter.ai/api/v1` (**dừng ở `/v1`**
  — để nguyên đuôi `/chat/completions` là 404), `EVAL_LLM_MODEL=stealth/ox-alpha`,
  **CẤM đặt `max_tokens`** (completion_tokens đo được ~5× số token chữ dù API báo
  `reasoning_tokens: 0`), timeout **≥ 120 s** (đo được có ca 59 s và 63 s).
- Bộ test là **LLM sinh, chưa có người duyệt** → `_generation_meta.json` phải ghi
  `human_reviewed: false`, và **mọi báo cáo dùng số này phải nói ra điều đó**.

---

## 4. CẤM — mỗi dòng có một phép đo hoặc một nguyên tắc đứng sau

1. **Không sửa chữ đã lưu trong `biology_text`.** Chuẩn hoá chỉ số dưới chỉ ở phía
   truy vấn/chỉ mục thưa. Đoán lại một chỉ số dưới là bịa (CẤM #5).
2. **Không bật `IMAGE_CAPTION_ENABLED`.** Đã chốt bỏ Vintern (D-74); thay bằng bốn
   đường ở §2.1, không đường nào là sinh mở.
3. **Không đổi `EMBEDDING_MODEL`, `CHUNK_SIZE`, `CHUNK_OVERLAP`** trong M2 — mỗi cái
   là một lượt dựng lại 3 giờ 20 và làm mọi số trước đó không so được.
4. **Không bump `TEXT_EXTRACTION_VERSION`** trong M2. Các tham số OCR còn nợ
   (`SINGLE_LINE_MAX_H = 60`, `LAYOUT_BOX_MIN_SATURATION = 45`, ngưỡng
   `needs_review`) phải gom vào **MỘT** lượt sau, khi đã đo được mỗi thay đổi đáng
   bao nhiêu.
5. **Không chạy `--image-only`** trong M2 (~6 giờ, và kênh pill đọc 0 nhãn trên 8/12
   quyển → kết quả đã biết là sai; chờ M3).
6. **Không `except` im lặng, không fallback im lặng.** Chỉ mục thưa cũ hơn index →
   raise. Thiếu tham số → raise. Đây là loại lỗi đã cắn thật hai lần (D-52 image doc
   mồ côi; rerank tắt âm thầm dưới `HF_HUB_OFFLINE=1`).
7. **Không so số mới với số của corpus cũ như cùng điều kiện.** G3 = 0,99 / G5 judge
   4,62–4,76 / recall@10 = 1,00 là **mốc lịch sử trên 4 quyển KNTT**, corpus đã đổi.
8. **Không dùng `needs_review` làm điều kiện lọc** trước khi hiệu chỉnh (đang bật ở
   57–84% chunk).
9. **Không chạy cả test suite khi đang lặp**; chạy đúng test của phần vừa sửa.
10. **Không `Co-Authored-By` / "Generated with"** trong commit message.
11. **Không tuyên bố "xong"** khi chưa đồng bộ 4 chỗ + notebook (mục "Định nghĩa
    xong" trong CLAUDE.md, D-69): decision log → CLAUDE.md (kèm bảng tiến độ) →
    memory → spec → `document/colab_runtime_etl.ipynb` nếu chạm ETL. Rồi mới commit.

---

## 5. Năm câu hỏi cũ — BỐN ĐÃ CÓ TRẢ LỜI (D-74), một còn mở

1. ~~384 chiều vs bge-m3~~ → **giữ bge-m3**, giải thích trong báo cáo (§2, #2).
2. ~~Ablation multi-modal 4 quyển hay 12~~ → **4 quyển KNTT**, nói rõ là 4 (§2, #9).
3. ~~Làm lại G2 hay không~~ → không làm lại bộ 24 trang tổng quát; thay bằng
   **người duyệt ~50 câu của bộ test** (§2, #6). Nếu cần số OCR cho MT1 thì làm
   **gold set CÔNG THỨC** như CLAUDE.md khuyến nghị.
4. ~~Spine Bài của 8 quyển CTST/CD~~ → **chấp nhận nợ**, làm BM25 trước (§2, #10).
5. **CÒN MỞ: hạn mức/ngày của OpenRouter free tier.** API **không trả header
   `x-ratelimit-*`** và `/api/v1/key` trả `limit: null` (D-67) → **chưa đo được**.
   Phải xác minh bằng một lô nhỏ **trước** khi sinh 300 câu, và phải có resume theo
   câu (hiện chỉ resume theo quyển → một lần 429 giữa quyển là mất cả quyển).

## 6. Trạng thái file khi bàn giao (khớp `git status` thật, commit `fa16181`)

- `master` **đã push**, sạch. Chuỗi commit của lượt trước: `8f076f3` (M0 fingerprint)
  → `cf41c8e` (bảng tiến độ + định nghĩa xong) → `3f0b1eb` (bỏ `datasources/` khỏi
  git) → `7525461` (notebook + `RAG_FINGERPRINT_DIR`) → `8d8897b` (M1 `toc_lines` +
  D-70..D-72) → `0c1807d` (script treo máy) → `9c94a46` (index 12 quyển + D-73) →
  `4effc19` (`.dockerignore`).
- `document/decision_log.html`: **D-01…D-74** (D-74 = 10 quyết định ở §2). M2 bắt đầu từ **D-75**.
- Index text 12 quyển **có thật** trong `database/` (16 393 chunk) — **đừng xoá**;
  M2 dựng chỉ mục thưa **trên nó**, không OCR lại.
- `database/manifests/*.json` 12/12 và `database/fingerprints/*.json` 12/12, đều đã
  commit và đi theo repo (`RAG_MANIFEST_DIR`, `RAG_FINGERPRINT_DIR`).
- `datasources/` **không** trong git (D-68) — chạy bằng `RAG_DATA_DIR`.
- `pytest tests/ -q` → **350 passed, 3 skipped**.
- Log lượt ETL: `etl_run_20260823_105618.log` (bị `.gitignore`, encoding UTF-16 —
  đọc bằng Python, `grep` sẽ báo "binary file").
- `scripts/run_etl_local.ps1` — lệnh treo máy, đã commit.
- **Chưa làm và biết là chưa:** phía ảnh 12 quyển; spine Bài của 8 quyển CTST/CD;
  bộ test 12 quyển; BM25; hợp nhất thưa+dày; caption vào prompt; hiệu chỉnh
  `needs_review`; tỉ lệ đọc số trang ở đường manifest (6_CD `ocr_confirmed` 37,1%).
