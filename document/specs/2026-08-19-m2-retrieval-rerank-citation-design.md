# M2 — Retrieval reranking + citation (Design Spec)

> Milestone M2 của redesign 2026-08. Tiền đề: M1 (layout-aware text ETL) đã hoàn tất (D-17),
> chạy `--text-only` rebuild trên Colab với `bge-m3` là bước pending song song. Spec gốc:
> `document/specs/2026-08-18-rag-etl-retrieval-redesign-design.md`. Decision log: `document/decision_log.html`.

## Mục tiêu

Nâng chất lượng **xếp hạng** (ranking) của retrieval — nút thắt chẩn đoán trong báo cáo
(recall 0.63 vs trần 0.84) — và trả lời kèm **citation chính xác tuyệt đối** cho học sinh tra cứu.
Ba trục:

1. **Embedding** text → `BAAI/bge-m3` (D-07, đã chốt, không A/B).
2. **Cross-encoder reranker** `BAAI/bge-reranker-v2-m3` cho **cả text và ảnh** (D-08 + mở rộng theo yêu cầu chủ dự án).
3. **Citation xác định** sinh từ metadata chunk thật (không để LLM bịa số trang), **kèm tên mục** cho sidebar/info-box.

## Quyết định khoá (ghi ở decision log)

- **D-07** — Embedding text = `bge-m3`. **M2 chốt: bỏ A/B, commit thẳng bge-m3.** MiniLM giữ làm fallback qua `.env`.
- **D-08** — Thêm cross-encoder reranker; nới `FETCH_K` → rerank → giữ top `MAX_K`; giữ relevance gate làm lưới an toàn.
- **D-11** — `page` metadata = số trang IN TRÊN SÁCH → dùng làm số trang trong citation.
- **D-12** — Reranker an toàn cho cả GPU lẫn CPU (rerank tập nhỏ FETCH_K + đường lui CPU).
- **D-19 (mới, sẽ log khi chốt spec)** — Scope M2: commit bge-m3 (no A/B); reranker cho **text + ảnh**; **citation code chèn từ metadata, không LLM-emit**, kèm tên mục sidebar; prompt giữ nguyên bộ quy tắc nghiêm ngặt.

## Không thuộc phạm vi (Non-goals)

- Cắt hình / redesign image ETL (figure region) — đó là **M3**. M2 chỉ *rerank* ảnh đã index, không đổi cách crop.
- A/B embedding MiniLM vs bge-m3 (đã bỏ, D-19).
- Fine-tune / train model. Chỉ dùng model có sẵn.
- Thay đổi image fusion scorer thủ công hiện có — cross-encoder **bổ sung** một term, có cờ tắt.

## Trạng thái mã hiện tại (điểm nối, đã đọc)

- `src/config.py` — `EMBEDDING_MODEL` mặc định MiniLM; `RETRIEVER_FETCH_K=8`, `RETRIEVER_MAX_K=4`, `RETRIEVER_DISTANCE_MARGIN=0.3`.
- `src/rag/vectorstore.py` — `RelevanceGatedRetriever` (fetch_k → sort theo distance → gate margin tương đối → top max_k). `VectorDB.get_retriever()` tạo retriever này.
- `src/rag/chain.py` — `BiologyRAG.get_chain(retriever)` nối `retriever | format_docs` **trực tiếp vào prompt** → **docs bị vứt**, không có citation. Prompt đã có 5 quy tắc nghiêm ngặt + câu fallback "Thông tin này không được đề cập trong sách giáo khoa."
- `src/app/dependencies.py` — `AppServices.rag_chain = rag.get_chain(vdb.get_retriever())` → chain chat production dùng **text retriever thuần** (KHÔNG HybridRetriever). HybridRetriever/image side dùng riêng ở tầng API.
- `src/rag/image_vectorstore.py` — `_rerank()` đã fusion nhiều tín hiệu (metadata/visual/lexical/phrase/page/quality) rồi lọc theo ngưỡng động. Có sẵn `search_text` (caption+keyword+crop_text hợp nhất) làm "document" cho ảnh.
- `src/test/recall_at_k.py` — đo recall@k bằng `similarity_search_with_score` thô, không qua gate/rerank.

## Kiến trúc & thành phần

### C1. Embedding switch (config)

Đổi default `EMBEDDING_MODEL` → `BAAI/bge-m3` trong `src/config.py`. Không đổi API `VectorDB`.
bge-m3 = 1024-dim (MiniLM 384) → **bắt buộc rebuild collection**; việc rebuild nằm ở lần chạy text-only Colab (D-04), không thuộc code M2. Code M2 test được local trên DB MiniLM hiện có (reranker & citation không phụ thuộc số chiều embedding).

> bge-m3 khuyến nghị prefix/hướng dẫn tối thiểu; dùng qua `HuggingFaceEmbeddings` như hiện tại. Nếu cần, thêm `encode_kwargs={"normalize_embeddings": True}` — quyết định lúc implement bằng smoke test, không đổi interface.

### C2. `src/rag/reranker.py` — CrossEncoderReranker (dùng chung text + ảnh)

- Bọc `BAAI/bge-reranker-v2-m3` qua `sentence_transformers.CrossEncoder` (hoặc HF `AutoModelForSequenceClassification` nếu ST không khả dụng — quyết định lúc implement, giữ interface bên dưới).
- **Lazy singleton**: nạp model một lần, tái dùng cho cả text và ảnh (không nạp 2 lần).
- **Device-safe (D-12)**: `cuda` nếu `torch.cuda.is_available()` và `USE_GPU`, ngược lại CPU. Chỉ chấm `FETCH_K` (~20) cặp/truy vấn → CPU chịu được. Batch các cặp.
- Interface:
  ```python
  class CrossEncoderReranker:
      def score(self, query: str, texts: list[str]) -> list[float]:
          """Trả điểm liên quan ∈ [0,1] (sigmoid của logit) theo đúng thứ tự texts."""
      def rerank(self, query: str, docs: list[Document], text_of=lambda d: d.page_content,
                 top_k: int | None = None) -> list[tuple[Document, float]]:
          """Chấm rồi sort giảm dần; cắt top_k nếu có. text_of cho phép ảnh dùng caption."""
  ```
- Lỗi model/nạp thất bại → log + trả điểm rỗng để caller **fallback về đường không-rerank** (không sập request).

### C3. Text — `RerankedRetriever` (trong `src/rag/vectorstore.py`)

Retriever mới song song với `RelevanceGatedRetriever`:

1. `scored = vectorstore.similarity_search_with_score(query, k=RERANK_FETCH_K)` — nới rộng (mặc định ~20).
2. `reranked = reranker.rerank(query, [doc for doc,_ in scored])` → sort giảm theo cross-encoder score.
3. Giữ **top `RETRIEVER_MAX_K`**.
4. **Gate an toàn (D-08):** loại chunk có score < `RERANK_SCORE_MIN` (ngưỡng tuyệt đối, đủ thấp để khi không có gì liên quan thì trả **rỗng** → LLM sinh câu fallback). Đây là lưới lui thay cho relative-distance gate khi rerank bật.
5. Gắn `rerank_score` vào `doc.metadata` để debug/eval.

Chọn retriever qua cờ:
- `RERANK_ENABLED=true` → `VectorDB.get_retriever()` trả `RerankedRetriever`.
- `RERANK_ENABLED=false` → giữ `RelevanceGatedRetriever` cũ (đường lui / A/B một dòng env).

> **Không** xoá `RelevanceGatedRetriever` — giữ làm baseline eval và fallback.

### C4. Ảnh — cross-encoder term trong `ImageVectorDB._rerank`

- Sau khi fusion thủ công tính `final_score` và sort, **chấm cross-encoder cho top-N ứng viên** (N = `IMAGE_RERANK_TOP_N`, ~12) — KHÔNG chấm cả kho (recall vẫn do lexical/metadata/CLIP lo).
- `text_of` cho ảnh = identity text của figure: ưu tiên `search_text` (đã hợp nhất caption/keywords/crop_text). Trống thì ghép caption thủ công.
- Gộp có trọng số: `final_score += IMAGE_RERANK_WEIGHT * cross_encoder_score` rồi **sort lại** trước bước lọc ngưỡng hiện có. Không đổi logic gate động (per-page limit, score_window, min_score) — chỉ đổi thứ hạng đầu vào.
- Cờ `IMAGE_RERANK_ENABLED` (mặc định true) để tắt nếu làm hại tập tinh chỉnh thủ công. Khi tắt → hành vi y hệt hiện tại.

> **Rủi ro cần phản biện (D-06):** cross-encoder có thể đè tín hiệu `phrase_score` (khớp chính xác "con trâu" ở nhãn OCR). Trọng số `IMAGE_RERANK_WEIGHT` phải đủ nhỏ để không lật một exact phrase match; kiểm bằng QA ảnh (`test_image_extraction_full.py`) + vài truy vấn "cho tôi hình con X".

### C5. Citation xác định — `src/rag/citations.py` + tái cấu trúc chain

**Nguyên tắc chính xác tuyệt đối:** citation **chỉ** sinh từ metadata các chunk **thực sự đưa vào context** của câu trả lời; LLM không bao giờ tự sinh số trang.

Tái cấu trúc `BiologyRAG.get_chain`:
- Dùng `RunnableParallel` để giữ `source_documents` (danh sách chunk đã retrieve) **song song** với `answer`. Trả về `{"answer": str, "sources": list[Citation], "source_documents": list[Document]}`.
- `format_docs` giữ nguyên (dedup content) nhưng **cùng tập docs** được đưa sang citation builder.

`build_citations(docs) -> list[Citation]`:
- Mỗi citation: `{book, page, region_type, section?}`.
- `book` = `format_book_name(source)`: lấy stem filename, chuẩn hoá đuôi NXB (`cd`/`ctst`/`kntt` qua `get_pdf_variant`) thành `(CD)`/`(CTST)`/`(KNTT)`. VD `"SGK KHTN 7 CTST.pdf"` → `"SGK KHTN 7 (CTST)"`.
- `page` = `metadata["page"]` (số trang IN, D-11).
- **Tên mục (theo yêu cầu chủ dự án):** với `region_type != body`, rút `section`:
  - Heuristic từ **dòng đầu** của `doc.page_content` khớp từ khoá không dấu: `em co biet`→`Em có biết`, `cau hoi`/`?`→`Câu hỏi`, `hoat dong`→`Hoạt động`, `luyen tap`→`Luyện tập`, `van dung`→`Vận dụng`, `tim hieu them`→`Tìm hiểu thêm`.
  - Không khớp → nhãn generic theo `region_type`: `sidebar`→`mục bên lề`, `info_box`→`khung thông tin`, `caption`→`chú thích hình`.
- **Dedup** theo `(book, page, section)`; sort theo (book, page).
- Format chuỗi hiển thị:
  - body: `SGK KHTN 7 (CTST), tr. 40`
  - box: `SGK KHTN 7 (CTST), tr. 40 — mục "Em có biết"`

**Suppress khi fallback:** nếu `answer` là câu fallback `"Thông tin này không được đề cập trong sách giáo khoa."` (so khớp chuẩn hoá) → trả `sources = []` (không xuất nguồn). Cùng vậy khi `docs` rỗng.

**Điểm nối (đã đọc lại code — CHỈNH so với bản đầu):** đường chat production **không dùng LCEL chain** — `api.py::prepare_chat_payload` gọi `hybrid_retriever.search()` → tự `prompt.format()` → `llm.invoke()`, và **đã có citation thô** (dòng ~97–116: set `"Trang {page} - {source}"` + `append_citations` đã suppress khi "không được đề cập"). Do đó:
- **Không** restructure `chain.py` (LCEL `rag_chain` không nằm trên đường chat → YAGNI, để nguyên).
- Reranker cắm qua `VectorDB.get_retriever()` → tự chảy vào `HybridRetriever._text_retriever` → `prepare_chat_payload`. Một điểm nối.
- Citation: thay khối dòng 97–102 + `append_citations` bằng `citations.py` (build từ `text_docs` thật, thêm tên mục + chuẩn hoá tên sách). Sửa cả 2 call site (stream ~201, non-stream ~297) và key payload `citations_str` → `citations`.

### C6. Prompt (`chain.py`)

- **Giữ nguyên** bộ 5 quy tắc nghiêm ngặt + câu fallback (đã phù hợp "không bịa").
- **Không** yêu cầu LLM tự cite (citation do code lo → tránh LLM sai số trang, đúng ý "chính xác tuyệt đối").
- Chỉ tinh chỉnh nhẹ nếu test trên câu thật lộ vấn đề; không mở rộng scope prompt.

### C7. Eval — mở rộng `src/test/recall_at_k.py`

- Chuyển sang bge-m3 (qua config).
- Thêm chế độ đo **reranker on vs off** trên cùng testset sạch: cột `recall@k (baseline)` vs `recall@k (rerank)` + **MRR**. Không cần LLM/judge.
- Xuất báo cáo CSV/MD như hiện tại → số liệu chứng minh D-08 cho báo cáo/thesis.
- Giữ nguyên `evaluator.py` (LLM-judge) cho đợt đo chất lượng câu trả lời sau khi có DB bge-m3.

## Config bổ sung (`src/config.py`)

```python
# --- M2: reranker + citation ---
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() == "true"
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
RERANK_FETCH_K = int(os.getenv("RERANK_FETCH_K", "20"))     # ứng viên trước rerank
RERANK_SCORE_MIN = float(os.getenv("RERANK_SCORE_MIN", "0.2"))  # gate an toàn (0..1), tune lúc impl
IMAGE_RERANK_ENABLED = os.getenv("IMAGE_RERANK_ENABLED", "true").lower() == "true"
IMAGE_RERANK_TOP_N = int(os.getenv("IMAGE_RERANK_TOP_N", "12"))
IMAGE_RERANK_WEIGHT = float(os.getenv("IMAGE_RERANK_WEIGHT", "0.25"))
```
Đổi default: `EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")`.

## Luồng dữ liệu (chat text)

```
query
 → RerankedRetriever: similarity_search_with_score(k=RERANK_FETCH_K)
   → CrossEncoderReranker.rerank → top MAX_K → gate score≥RERANK_SCORE_MIN
 → docs ──┬─ format_docs → prompt → LLM → answer
          └─ build_citations → sources  (suppress nếu answer=fallback | docs rỗng)
 → {answer, sources}
```

Ảnh (tầng API, song song): HybridRetriever → ImageVectorDB.similarity_search → `_rerank`
(fusion + cross-encoder term nếu `IMAGE_RERANK_ENABLED`) → gallery.

## Xử lý lỗi & suy biến

- Reranker nạp/chấm lỗi → log, **fallback**: text về top `MAX_K` theo distance (như baseline), ảnh giữ fusion thủ công. Không sập request.
- CPU-only: chỉ rerank FETCH_K/TOP_N nhỏ; batch. Demo chạy được không cần GPU (D-12).
- bge-m3 chưa có trong DB (chưa chạy Colab) → code vẫn chạy trên DB MiniLM; eval số thật hoãn tới khi có DB bge-m3.

## Chiến lược test (theo working rules: nhỏ, tập trung, có phản biện)

- `tests/rag/test_reranker.py` — `score`/`rerank` sort đúng theo điểm (mock model, không nạp bge thật); `rerank` cắt top_k đúng.
- `tests/rag/test_reranked_retriever.py` — với reranker giả (điểm định sẵn): giữ đúng top MAX_K, loại chunk < `RERANK_SCORE_MIN`, trả rỗng khi tất cả dưới ngưỡng.
- `tests/rag/test_citations.py` — `format_book_name` (cả 3 NXB); dedup (book,page,section); tên mục từ dòng đầu box (Em có biết / Câu hỏi / generic); **suppress khi answer=fallback và khi docs rỗng**; body không có suffix mục.
- `tests/rag/test_image_rerank.py` — `_rerank` cộng term cross-encoder khi bật; khi tắt cho kết quả y hệt baseline; exact `phrase_score=1.0` không bị cross-encoder lật (chọn trọng số an toàn).
- Integration skip-if-model-absent: nạp bge-reranker thật, chấm 1 cặp rõ liên quan > 1 cặp không liên quan; `recall_at_k` reranked ≥ baseline trên testset nhỏ.
- **KHÔNG** chạy full suite khi lặp; chỉ chạy test của phần đang sửa (CLAUDE.md). Chạy toàn bộ trước khi đóng milestone.

## Phản biện chống bug ẩn (bắt buộc, D-06) — điểm cần soi

- Hướng điểm: cross-encoder logit cao = liên quan cao (ngược chiều distance). Đảm bảo sort **giảm dần** theo score, không nhầm chiều.
- `RERANK_SCORE_MIN` quá cao → giết hết chunk → luôn fallback "không được đề cập"; quá thấp → gate vô dụng. Tune trên câu thật, ghi lại giá trị.
- Citation phải khớp **đúng tập docs** nuôi answer (sau dedup của `format_docs`), không phải toàn bộ fetch_k — tránh cite chunk đã bị loại.
- Suppress fallback phải so khớp **chuẩn hoá** (bỏ dấu câu/space) để không lọt biến thể.
- Image cross-encoder không được đè `phrase_score` exact match (trọng số nhỏ + kiểm QA).
- Tên mục: dòng đầu box có thể là số trang/nhiễu → chỉ nhận khi khớp từ khoá, else generic.

## Thứ tự triển khai & phụ thuộc

1. Code M2 (C1–C7) build/test **local**, độc lập lần chạy Colab.
2. Chạy text-only rebuild bge-m3 trên Colab (bước pending) → có DB bge-m3.
3. Eval số thật (recall reranked vs baseline + MRR) trên DB bge-m3 → chốt `RERANK_SCORE_MIN`/trọng số, ghi vào decision log.

## Self-review (điền khi viết plan)

Plan chi tiết theo TDD sẽ ở `document/specs/2026-08-19-m2-plan.md` (skill writing-plans), một task/commit, mỗi task có bước phản biện.
