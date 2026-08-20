# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Vietnamese-language **RAG system over image-only Vietnamese science textbook PDFs (SGK KHTN, THCS)**. The pipeline OCRs Vietnamese text and crops figures, then serves hybrid text+image retrieval with a local Qwen2.5 LLM answering in Vietnamese with citations.

**Corpus as of 2026-08-20 (measured, not assumed):** the Ministry unified textbooks onto **Kết Nối Tri Thức only** — CD and CTST are withdrawn. The corpus is now exactly 4 books, `datasources/SGK-KHTN-Lop-{6,7,8,9}.pdf`, **809 pages**. They are *not* born-digital PDFs: producer `jsPDF 2.5.1`, **0/809 pages carry a text layer**, one JPEG per page at 1094×1536 px = **132 DPI effective** (lower than the old scans' 138–150). A publisher watermark is baked into every page. So **OCR remains mandatory**, 132 DPI is a hard ceiling (the user confirmed no better source exists), and all per-publisher (CD/CTST/KNTT) branching is now dead weight scheduled for deletion. Full evidence: `document/specs/2026-08-20-kntt-only-etl-rebuild-design.md`.

Most docs (`README.md`, `document/`) are in Vietnamese; code and comments mix English/Vietnamese. Match the surrounding language when editing.

## Philosophy — tư tưởng của repo (đọc trước khi viết bất kỳ dòng code nào)

Đây là **sách giáo khoa cho học sinh**. Một câu trích sai dấu, một số trang sai, một
hình gán sai bài — là dạy sai một đứa trẻ. Toàn bộ repo được thiết kế quanh một câu
hỏi duy nhất: *làm sao để không bao giờ nói điều mình không chứng minh được?*

Bảy nguyên tắc, theo thứ tự ưu tiên. Khi hai nguyên tắc xung đột, nguyên tắc đứng
trước thắng.

1. **Không bịa (no fabrication).** Trang, hình, chú thích, số liệu — tất cả phải truy
   được về pixel/bytes của file PDF gốc. Citations là **deterministic**, dựng từ
   metadata của chunk thật (`src/rag/citations.py`); LLM không bao giờ được sinh số
   trang. Nếu không biết, hệ thống nói "không biết" — không nội suy, không đoán.
2. **Bằng chứng trước khẳng định (evidence before assertion).** Không "chắc là", không
   "thường thì". Trước khi kết luận về corpus: mở PDF ra đo. Trước khi nói code chạy
   đúng: chạy nó và dán output. Một giả định chưa đo là một **câu hỏi mở**, phải ghi
   ra rõ ràng, không được lặng lẽ biến thành thiết kế.
3. **Đo, đừng đoán (measure, don't assume).** Mọi lựa chọn kỹ thuật ảnh hưởng độ chính
   xác (OCR engine, render DPI, chunk size, ngưỡng threshold) phải được chọn bằng số
   trên một **gold set do người xác nhận**, không bằng trực giác hay mặc định của thư
   viện. Đổi tham số mà không có phép đo trước/sau là hồi quy chờ xảy ra.
4. **Phản biện chính code của mình (adversarial self-review).** Test pass ≠ đúng. Với
   mỗi thay đổi: truy edge case, off-by-one, lệch hệ toạ độ/hệ chỉ số (0-based vs
   1-based), cache cũ, fallback âm thầm. Chủ động đi tìm trang làm mình sai — QA thật
   trên trang thật, không chỉ unit test trên fixture tổng hợp.
5. **Fail loudly, never silently.** Một trang OCR lỗi phải được **để lại chưa xử lý**
   và log ra, để lần chạy sau làm lại — không được ghi vào index một nửa dữ liệu. Một
   fallback im lặng (ví dụ đoán số trang = index+1) tệ hơn một lỗi ồn ào, vì nó đẩy
   sai lệch xuống tới câu trả lời cho học sinh. Bước "sửa" tự động phải là **drop-only**
   hoặc **flag-for-review**, không tự bịa thêm dữ liệu.
6. **Một nguồn sự thật duy nhất (single source of truth).** Checkpoint là
   `processing_status` (khoá theo **content hash** + version), không phải file log.
   Cấu trúc sách là MỤC LỤC của chính quyển sách, không phải hằng số hardcode. Khi hai
   nguồn độc lập không khớp → không chọn bừa, mà **flag** để người xem.
7. **Xoá code mạnh tay khi phạm vi hẹp lại (delete aggressively).** Heuristic tồn tại
   để phục vụ một thực tế đo được. Khi thực tế đó biến mất (một nhà xuất bản thay vì
   ba), heuristic đó là nợ, không phải tài sản. Code ít hơn = ít chỗ để sai hơn. Ưu
   tiên deterministic (CV/regex có anchor) hơn "model magic" ở mọi chỗ mà kết quả phải
   giải thích được cho giáo viên.

Hệ quả vận hành: mỗi quyết định ghi vào `document/decision_log.html`; mỗi thay đổi
đúng-sai được đo bằng eval trong `src/test/`; test nhỏ và nhắm đúng chỗ (đừng chạy cả
suite khi đang lặp); và khi báo cáo, nói thẳng cái gì đã verify, cái gì chưa.

## Active redesign (2026-08) — read this first

A layout-aware ETL + retrieval-reranking rebuild is **in progress** (deadline-driven). Source of truth:
- **Decisions:** `document/decision_log.html` (data-driven `DECISIONS[]` log; every decision is recorded here — currently D-01…D-28).
- **Current spec (supersedes the corpus + image-ETL parts of the older ones):** `document/specs/2026-08-20-kntt-only-etl-rebuild-design.md`. Earlier: `2026-08-18-rag-etl-retrieval-redesign-design.md`, `2026-08-19-m2-*`, `2026-08-19-m3-*`. Implementation plans live alongside in `document/specs/`.

Still locked from the earlier design: full clean rebuild of `database/`; classical-CV layout segmenter spine; text embedding → `BAAI/bge-m3`; `BAAI/bge-reranker-v2-m3` cross-encoder; Vietnamese diacritic post-correction; sidebar/info-box as separate labeled chunks; checkpoint keyed on **content hash** not filename.

New in the 2026-08-20 rebuild (KNTT-only corpus), all of it evidence-backed in the spec:
- **Page identity is verified, never guessed.** `printed_page == pdf_index` (0-based) holds for all 4 books — established by a global `mode(value − index)` offset model over digit tokens plus a parity rule (even index → left margin, odd → right), which held 695/695 reads. A `BookManifest` JSON per book (page map + Chương/Bài spine) becomes the single source of truth. The existing `index + 1` fallback in `page_number.py` is an **off-by-one bug**.
- **MỤC LỤC is a hypothesis, not truth** (measured: missing bài, wrong page numbers). The Bài spine comes from TOC + in-page "Bài N" banner detection + a strict-monotonic global constraint; disagreements are flagged, not resolved by guessing.
- **Text OCR = dual-engine consensus per line**, labelled `agree` / `conflict_diacritic` / `conflict_text` / `single_engine`, feeding a per-chunk confidence and `needs_review`. Engine B (PaddleOCR VN candidate) is chosen by a measured bake-off, not assumed. `RENDER_DPI=220` is not the measured optimum (300 was best of 132/200/300/400).
- **Figures anchor on the caption pill** (solid coloured rounded rect + white `Hình N.M`), and completeness is *proved* per Bài by checking the figure numbers form a continuous `1..k` — gaps mean missing figures.
- **Add `TEXT_EXTRACTION_VERSION`** to the checkpoint key: today only images have a version gate, so changing OCR logic cannot force a re-OCR.
- Quality gates G1–G5, including **G3 page-accuracy** (does the cited page really contain the answer) — a metric the repo never had.

## Working rules (always)

- **Adversarially review every code change for hidden bugs before claiming done** — trace edge cases, off-by-ones, coordinate/index mismatches, stale caches; don't trust that a passing test means correct.
- **Do NOT run the full test suite while iterating.** Run only the focused test(s) for the code you changed (e.g. `python -m pytest tests/layout/test_segmenter.py -v`). Run the whole suite only when explicitly asked or right before finishing a milestone.
- **Keep tests small and targeted.** Avoid large/slow/expensive tests unless they're truly necessary; prefer focused unit tests with synthetic fixtures over heavy end-to-end runs.
- **Commit messages: NO `Co-Authored-By` trailer** (and no "Generated with" lines). Plain messages only.
- Log each decision in `document/decision_log.html`; keep spec/plan in `document/specs/`; keep CLAUDE.md + memory current.

## Commands

All commands run through `main.py` (from repo root). There is no build step — it's a Python app.

```bash
pip install -r requirements.txt
cp .env.example .env          # then set HF_TOKEN (required) and USE_GPU

# ETL (offline indexing) — has checkpoint resume; re-runs skip processed pages
python main.py --text-only    # layout-aware OCR + chunk + index text → ChromaDB
python main.py --image-only   # crop figures + caption + index images
python main.py --etl          # both (same text path as --text-only)

# Image metadata human-review cycle (see README §6 for exact JSON semantics)
python main.py --export-image-review database/review_images.json
python main.py --apply-image-review database/review_images.json --review-user <name>   # upsert-by-item, NOT full sync
python main.py --replace-image-db database/snapshot.json --review-user <name>          # JSON is source of truth (deletes missing)

# Serve
python main.py --api --port 5000
```

### Evaluation (in `src/test/`)

Requires `EVAL_LLM_*` in `.env` (any OpenAI-compatible endpoint — Groq/OpenRouter/MiMo/vLLM). Split cleanly into deterministic IR metrics vs. LLM-judged answer quality:

```bash
python src/test/generate_testsets.py            # build ground-truth testsets for the 12 books
python src/test/evaluator.py                    # run real RAG, measure P/R/MRR + LLM judge (1–5)
python src/test/recall_at_k.py                  # fast recall benchmark, no LLM calls
python src/test/test_image_extraction_full.py   # canonical VISUAL QA for image cropping (draws boxes on pages)
```

## Architecture

Two phases: **ETL (offline)** builds the indexes; **query (online)** serves via Flask.

### Storage — four ChromaDB collections (`src/config.py`)
- `biology_text` — OCR'd text chunks (bge-m3 embeddings, `CHUNK_SIZE=400/overlap=120`)
- `biology_images` — figure crops (CLIP embeddings)
- `biology_image_metadata` — caption/keyword metadata for figures (separately searchable)
- `processing_status` — per-page checkpoint state enabling resumable ETL

**Checkpoint semantics (all three ETL entrypoints agree):** `processing_status` is the single truth source. It is keyed on the PDF's **content hash** and, for images, on `IMAGE_EXTRACTION_VERSION`, so replacing a PDF under the same filename or bumping the extraction version re-processes it. `database/processed_files.txt` / `processed_images.txt` are **advisory progress logs only** — nothing skips work because of them (they used to, which silently defeated version bumps). Each entrypoint queries the checkpoint *before* doing any OCR, so a book with nothing left to do costs one file hash plus a `fitz` page count.

Everything writable lives under `database/` (`PERSIST_DIR`), overridable via `RAG_DATABASE_DIR` (point at Google Drive on Colab). `datasources/` holds input PDFs.

### Text ETL (`src/etl/layout/loader.py`)
`LayoutOCRLoader.load_page()` is the M1 layout spine and the **only** text path: render page → `preprocess_page` → `segment_page` → `detect_printed_page_number` → `extract_text_units` → `chunk_units`. It returns already-chunked Documents (body split by `TextSplitter`, each sidebar/info-box kept atomic) carrying `source`/`page`/`variant`/`region_type`/`chunk_index`. `citations.py` reads `region_type` for the section label, so a chunk missing it silently degrades to a body-only citation. `--etl` and `--text-only` both go through `_index_pdf_pages()` in `main.py`, one page at a time with deterministic ids (`{hash}_p{page}_c{idx}`) so a resume upserts instead of duplicating; a page that raises is logged, left unmarked, and retried next run. The legacy whole-page `RobustOCRLoader` is **not** a text path any more — it survives only to supply full-page OCR text for figure-caption anchoring on the image side.

### Retrieval flow (`src/rag/`)
1. `hybrid_retriever.py::HybridRetriever.search()` is the entry. It calls `query_intent.py::is_image_only_query()` to **route**: image-only queries (e.g. "cho tôi hình con X") skip text retrieval entirely.
2. Text side uses a **RelevanceGatedRetriever** — a relative-distance gate (`RETRIEVER_DISTANCE_MARGIN`) drops chunks far from the best match, fetching `FETCH_K` then keeping ≤`MAX_K`.
3. Image side combines CLIP similarity + metadata search + a **lexical phrase channel** (accent-sensitive; distinguishes e.g. "trâu" vs "trầu") + rerank, gated by `IMAGE_RELEVANCE_THRESHOLD`.
4. `chain.py::BiologyRAG` builds the prompt and calls the Qwen2.5 LLM (`llm.py`), returning answer + image gallery.

### Image ETL — the complex, actively-evolving part (`src/etl/image_processor.py`, ~4000 lines)
- **Per-variant subclasses**: `make_image_processor(pdf_filename)` → `get_pdf_variant()` inspects the filename for `ctst`/`kntt`/`cd` keywords and returns the matching processor (`CtsstImageProcessor`, `KnttImageProcessor`, base `ImageProcessor` for CD). Each publisher has its own caption-regex / layout heuristics — changes are almost always variant-scoped, not global.
- Detection is **anchor-first + deterministic** (find figure-caption text anchors, then crop the band above), with OWL-ViT as a secondary detector. When touching this, verify against the visual QA tool above, not just unit output.
- **M3 layout reconcile**: right after `detect_regions_anchor_first`, `extract_images_from_pdf` runs `src/etl/layout/figure_bridge.py::reconcile_with_layout` — a **drop-only** step that removes a region sitting ≥`FIGURE_IN_BOX_DROP_RATIO` (0.80) inside a segmenter colour box (sidebar/info-box false positive). It runs `segment_page` on the detector's **own 150-DPI RGB array (converted to BGR)** so bboxes share one coordinate space; it never clips/grows a figure. **Only generic/unanchored types (`panel`/`figure`) are drop-eligible** — caption/label-anchored figures (`single_figure`/`composite_figure`/`sub_figure`) are trusted and never dropped (real-page QA showed a legit coloured sub-figure was otherwise eaten when its flat background tripped the box detector), and `textbook_info_box`/`activity_box`/`tool_group` are legit boxes, also never dropped. Fail-open on segmentation error. QA overlay `04_reconciled.png` shows kept=green / dropped=red.
- **Entrypoints use `make_image_processor(filename)` per book** (`run_etl`/`run_etl_image_only`) so CTST/KNTT get their subclasses — previously the batch path used base `ImageProcessor()` for every book.
- `IMAGE_EXTRACTION_VERSION` in `.env` gates the crop cache: **bump it to force re-extraction** after changing crop logic (otherwise the per-page checkpoint skips already-processed pages). Current default `v16_layout_reconcile` (M3). A bump is honoured by `--etl` and `--image-only` alike — see the checkpoint-semantics note under Storage.

### API + app (`src/app/`)
- `dependencies.py::AppServices` is a **singleton** that loads all heavy models once (VectorDB, HybridRetriever, LLM, RAG chain). Never instantiate models per-request; go through this.
- `api.py` exposes chat (+SSE stream at `/api/chat/stream`), background ETL upload, and image-metadata CRUD for the review UI.

## Key conventions

- **Models are configured via `.env` / `src/config.py`**, not hardcoded. Defaults: `BAAI/bge-m3` (text embeddings, M2), Qwen2.5-3B-Instruct (LLM), CLIP-ViT (image), OWL-ViT (detection), Vintern-1B (captioning). `src/utils/download_models.py` pre-fetches them for offline runs.
- **Cross-encoder reranker** `BAAI/bge-reranker-v2-m3` (`src/rag/reranker.py::CrossEncoderReranker`/`get_reranker()`, shared singleton, GPU/CPU-safe) reranks both sides: text via `RerankedRetriever` (`src/rag/vectorstore.py`, toggle `RERANK_ENABLED`, fetch width `RERANK_FETCH_K`, absolute floor `RERANK_SCORE_MIN`) and images as an additive scoring term (`src/rag/image_vectorstore.py`, toggle `IMAGE_RERANK_ENABLED`, `IMAGE_RERANK_TOP_N`, `IMAGE_RERANK_WEIGHT`) — never a replacement for the existing image fusion.
- **Citations are deterministic, not LLM-generated**: `src/rag/citations.py` builds them from real chunk metadata (page/section, including sidebar labels) and `src/app/api.py` attaches them to chat + stream responses — the LLM never invents page numbers.
- **Windows is the primary dev environment.** OCR needs Poppler + Tesseract (`vie`); paths set via `TESSERACT_CMD` / `POPPLER_PATH`. Prebuilt zips are in `windows_tools/`.
- **Image-review JSON semantics are subtle and easy to get wrong**: `--apply-image-review` upserts per-item (removing an item from the array does NOT delete it from the DB); only `--replace-image-db` treats the file as the full source of truth. To remove a figure from retrieval, set `review_status=rejected|deleted` / `is_active=false` / `delete=true`. See README §6.
- Detailed per-variant image-ETL runbook: `skills/etl-textbook-images/runbook.md`.
