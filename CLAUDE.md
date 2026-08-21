# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Vietnamese-language **RAG system over image-only Vietnamese science textbook pages (SGK KHTN, THCS)**. The pipeline OCRs Vietnamese text and crops figures, then serves hybrid text+image retrieval with a local Qwen2.5 LLM answering in Vietnamese with citations.

**Corpus as of 2026-08-21 (measured, not assumed):** the Ministry unified textbooks onto **Kết Nối Tri Thức only** (CD and CTST withdrawn), and the input format changed from PDF to **one PNG per page**. `datasources/` holds **no PDFs at all** — it is exactly 4 folders:

```
datasources/SGK_KHTN_{6,7,8,9}_KNTT/page_001.png … page_NNN.png
196 + 180 + 197 + 228 = 801 pages, all contiguous, 0 duplicate-content files
```

The ETL reads these PNGs directly through `src/etl/page_source.py::PageSource` — there is **no render step and no `fitz` on the main path** (`PdfPageSource` survives only for the legacy PDF-upload endpoint).

Measured on all 801 pages: **1094×1536 px** (`page_001.png` is 1093 wide in every book — never assume uniform width), RGBA with alpha=255 everywhere (drop it), no DPI metadata, publisher watermark baked into every page. **These PNGs are not higher-resolution than the old PDFs** — 1094×1536 is exactly the size of the JPEGs that were inside them; the win is lossless PNG plus no render step, and the pixel ceiling is unchanged with no better source available. (The old "132 DPI" figure assumed A4; against the real SGK trim of 19×26.5 cm the same pixels are ~147 DPI.) 801 rather than the old 809 because the user deliberately deleted 1 back cover + 1 padding page per book. **OCR remains mandatory**, and all per-publisher (CD/CTST/KNTT) branching is dead weight scheduled for deletion. Full evidence and the executable plan: `document/specs/2026-08-21-png-source-etl-prompt.md`.

Most docs (`README.md`, `document/`) are in Vietnamese; code and comments mix English/Vietnamese. Match the surrounding language when editing.

## Philosophy — tư tưởng của repo (đọc trước khi viết bất kỳ dòng code nào)

Đây là **sách giáo khoa cho học sinh**. Một câu trích sai dấu, một số trang sai, một
hình gán sai bài — là dạy sai một đứa trẻ. Toàn bộ repo được thiết kế quanh một câu
hỏi duy nhất: *làm sao để không bao giờ nói điều mình không chứng minh được?*

Bảy nguyên tắc, theo thứ tự ưu tiên. Khi hai nguyên tắc xung đột, nguyên tắc đứng
trước thắng.

1. **Không bịa (no fabrication).** Trang, hình, chú thích, số liệu — tất cả phải truy
   được về pixel/bytes của trang gốc (PNG nguồn). Citations là **deterministic**, dựng từ
   metadata của chunk thật (`src/rag/citations.py`); LLM không bao giờ được sinh số
   trang. Nếu không biết, hệ thống nói "không biết" — không nội suy, không đoán.
2. **Bằng chứng trước khẳng định (evidence before assertion).** Không "chắc là", không
   "thường thì". Trước khi kết luận về corpus: mở trang gốc ra đo. Trước khi nói code chạy
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
- **Decisions:** `document/decision_log.html` (data-driven `DECISIONS[]` log; every decision is recorded here — currently D-01…D-39).
- **Current plan (supersedes the corpus + OCR parts of every older spec):** `document/specs/2026-08-21-png-source-etl-prompt.md` — the PNG-source migration, with every measured number so nothing needs re-measuring. Earlier: `2026-08-20-kntt-only-etl-rebuild-design.md`, `2026-08-18-rag-etl-retrieval-redesign-design.md`, `2026-08-19-m2-*`, `2026-08-19-m3-*`. Implementation plans live alongside in `document/specs/`.

Still locked from the earlier design: full clean rebuild of `database/`; classical-CV layout segmenter spine; text embedding → `BAAI/bge-m3`; `BAAI/bge-reranker-v2-m3` cross-encoder; sidebar/info-box as separate labeled chunks; checkpoint keyed on **content hash** not filename. (Dropped: "Vietnamese diacritic post-correction" — measured useless and it rewrote text, see D-34.)

Measured on the PNG corpus (2026-08-21). Everything marked DONE below is implemented and verified on the real corpus (D-33…D-39); the rest is still open.

- **DONE — page identity is verified, never guessed:** `printed_page == (number in the filename) − 1`. `page_001.png` = printed 0 = front cover. Measured over all 801 pages: offset **−1** in all 4 books (the model *derives* it), parity (even value → left margin, odd → right) with zero exceptions, and `ocr_confirmed` **793/793 = 100.0%** of the pages that print a number (194/194, 178/178, 195/195, 226/226); the unconfirmed set is exactly `{page_001, page_002}` per book, which genuinely print no number. Filenames carry the source's own page index, not download order, so a re-downloaded page slots straight back in. The `BookManifest` JSON per book is the single source of truth and `LayoutOCRLoader` **raises** without it — there is no `index + 1` fallback anywhere any more (`layout/page_number.py` was deleted). Never renumber or delete source PNGs — cover pages get `role="cover"` and are skipped at chunk time.
- **DONE — page-number reading = union of the 1× and 3× corner crops.** The corner crop is 153×115 px at native size, where Tesseract clips digits (`"11"→"1"` conf 83, `"110"→"10"` conf 45). 3× fixes those but is *not* strictly better (`page_165` of book 9 reads only at 1×), so both scales are read and the candidates unioned, deduped by `(value, side)`. **This is the only place upscaling is allowed** — body text CER is identical at 1×/2×/3×/4×.
- **DONE — preprocessing: none.** `preprocess_page` is deleted, not stubbed. Otsu/binarization measurably *hurts* (conf 93.4 → 92.0); the left-6% wipe had no stamp to remove on this source (median of 100 pages/book: 0% pixels < 200) and destroyed real content, including the left-margin page number of every even page. `RENDER_DPI` is gone from config; the legacy PDF path keeps its own `PDF_RENDER_DPI` constant.
- **DONE — region OCR states its psm:** `--psm 6`, or `--psm 7` for crops under 60 px tall. Default psm 3 lost 3.8% of tokens (6293 → 6535 on 14 pages). Whole-page OCR (`RobustOCRLoader`, image-side context only) also moved to `--psm 6`: on a real page psm 3 = 134 words, psm 11 = 150, psm 6 = 194.
- **DONE — `segment_page` recall was the top defect and is rebuilt: 2.17 → 4.10 regions/page** on the same 40-page/4-book sample, 0 pages regressed. Two root causes, both design errors: a single mask + `CLOSE(25)` glued the question box, the panel and every photo into one 39%-of-page blob that then failed the flatness test (so `page_010` yielded **0 boxes**), and flatness was measured over the *bbox* instead of the region's own pixels (the lavender sidebar scored 0.42 vs a 0.45 floor because its bbox included white gaps). Now: small close, flatness over the component's own pixels, and hue-band splitting of a component that fails — hue bands derived from the region's pixels, no hard-coded publisher palette. Verified on `page_010`: the yellow question box comes out in full and the right sidebar reads `"Chỉ ra những lợi ích…"` with its head intact (the exact head-truncation defect of D-32).
- **DONE — checkpoint is keyed on the hash of EACH PAGE plus `TEXT_EXTRACTION_VERSION`** (`page_key = {book}#{md5 of the page}`), so re-downloading 19 pages re-processes 19 pages and changing OCR logic can finally force a re-OCR. Chunks of a page are deleted before the page is re-indexed, so a version bump leaves no orphans.
- **DONE — automatic "fixes" never rewrite text.** `diacritic.py` now only sets `needs_review` / `review_tokens` on the chunk (`DIACRITIC_REVIEW_ENABLED`). It catches structural impossibilities (letter+digit tokens, invalid onsets/codas, two tone marks, a stop-coda syllable with no sắc/nặng such as `mat`); it cannot catch `chế`→`ché` and does not pretend to.
- **OPEN — OCR junk from figure areas is kept on purpose.** Both candidate filters were measured to delete real text: a per-line confidence floor kills `"Em có biết?"` (conf 56) and `"Gai glycoprotein"` (54); "drop lines with no 3+-letter word" kills `"e Ở 20 °C, 100 mL"`. Junk is noise, not fabrication — the chunk carrying it is flagged `needs_review` instead (D-38).
- **DONE (partly) — white-on-colour labels: `src/etl/layout/pill.py`.** Crop the pill → invert → OCR `--psm 7` → accept only what matches `Hình N.M`; wired into both the text units and the image-side anchors. This is **not** a resolution problem: the labels read at no scale (1×, 1.134× = the old 150-DPI render size, 1.5×, 2×) and inverting a whole crop does not help either (Tesseract binarizes locally). Measured: 32 sample pages / 4 books → **13 pages, 17 `Hình N.M` labels** where there were essentially none, and the Bài numbers cross-check against page position. **Still unread:** a pill nested inside an already-tinted cell (the three comparison labels) — no saturation threshold can separate it (`page_010`: the pill is sat **82** on a sat **157** purple band) and hue-band splitting was tried and is not better. Needs a local-contrast design (D-40).
- **OPEN — the Bài spine is broken and `bai_so` is therefore NOT written into chunk metadata** (it stays in the manifest as a flagged hypothesis). Measured: book 6 resolves **3 Bài** for ~55, its MỤC LỤC OCRs to 0 entries, and the banner detector was firing on the MỤC LỤC page itself ("Bài 20 at page 6", which is why it used to report 4); banner detection now skips `TOC_PAGE_NUMBERS`, and a spine whose Bài numbers are not `1..k` raises `bai_numbers_not_contiguous`. `TOC_PAGE_NUMBERS = (5, 6)` (source page numbers, = `page_005/006`) is confirmed correct.
- **OPEN — the image path RUNS but its output is not trustworthy yet (D-41).** Ported to `PageSource` (no poppler, no DPI) with `IMAGE_EXTRACTION_VERSION` → `v17_png_source`, and a real 4-page `--image-only` run produces crops and indexes them without crashing. But 3 of those 4 pages are measurably wrong: `figure_label='Em có biết'` on an info-box, `label='quan sát'` instead of `Hình 21.3` **even though the pill anchor read that label correctly**, and one crop spanning nearly half the page. So the anchor→region assignment and crop geometry need re-measuring on this source — that is the **M3 figures milestone**, not a parameter tweak. Completeness is still meant to be *proved* per Bài by checking figure numbers form a continuous `1..k`; not implemented.
- Quality gates G1–G5, including **G3 page-accuracy** (does the cited page really contain the answer) — a metric the repo never had. G1 currently PASSes page identity on all 4 books; two books FAIL G1 on `spine_out_of_order`, which is the spine problem above, not page identity.
- Cost: OCR is ~26 min for 801 pages single-threaded. There is **no CUDA** in the project's python env despite `USE_GPU=true`, so embedding is the bottleneck, not OCR.

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

# STEP 0 — page map + Bài spine per book. REQUIRED before any text indexing:
# the text loader refuses to guess a printed page number and raises without it.
# Prints the G1 report and exits nonzero when G1 fails.
python main.py --build-manifests
python main.py --build-manifests --book SGK_KHTN_6_KNTT   # one book only

# ETL (offline indexing) — checkpoint resume is per PAGE, keyed on page content
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
python src/test/generate_testsets.py            # build ground-truth testsets (still written for the old 12 books - needs regenerating for the 4 KNTT books)
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

**Checkpoint semantics (all three ETL entrypoints agree):** `processing_status` is the single truth source. Every record is keyed on **`page_key` = `{book name}#{md5 of that page's bytes}`** (`page_source.page_checkpoint_key`) plus a version — `TEXT_EXTRACTION_VERSION` for text, `IMAGE_EXTRACTION_VERSION` for images. So: replacing one page file re-processes **only that page**; bumping either version re-processes everything on that side. Chunk ids are `{page_key}_p{page_number}_c{chunk_index}`, and `_index_source_pages` deletes a page's existing chunks before writing the new ones, so a version bump never leaves orphaned chunks behind. `database/processed_files.txt` / `processed_images.txt` are **advisory progress logs only** — nothing skips work because of them. Each entrypoint queries the checkpoint *before* doing any OCR, so a book with nothing left to do costs one md5 per page.

Everything writable lives under `database/` (`PERSIST_DIR`), overridable via `RAG_DATABASE_DIR` (point at Google Drive on Colab). `database/manifests/{book_id}.json` holds the per-book `BookManifest`, overridable **separately** via `RAG_MANIFEST_DIR` so manifests can travel with the repo while the index sits on Drive. `datasources/` holds the input page PNGs, one folder per book (see "What this is") — no PDFs; override with `RAG_DATA_DIR`.

### Page source (`src/etl/page_source.py`)
`PageSource` is the only way page pixels enter the system: `page_numbers()` (the numbers **in the filenames**, never `enumerate` order), `load(page_number)` → BGR uint8, `content_hash(page_number)`. `PngFolderPageSource` is the real corpus; `PdfPageSource` exists only for the legacy `/api/etl` upload. `discover_page_sources(DATA_DIR)` returns every book (PNG folders first, then any legacy PDFs). Anything that needs a page must go through this — do not re-add `fitz`/poppler calls to the ETL.

### Text ETL (`src/etl/layout/loader.py`)
`LayoutOCRLoader.load_page(source, page_number)` is the layout spine and the **only** text path: manifest lookup (printed page + role) → `source.load()` → `segment_page` → `extract_text_units` → `chunk_units`. There is no preprocess step and no page-number detection here: the **printed page number comes from the `BookManifest`**, and a missing manifest / unknown page / absent `printed_page` raises `ManifestMissing` rather than guessing. Pages with `role="cover"` return no chunks (the source file is never touched or deleted).

Chunks carry `source`/`page` (printed) /`page_index` (source page number) /`variant`/`region_type`/`chunk_index`/`needs_review`/`review_tokens`. `page` and `page_index` differ by exactly 1 on this corpus, so never conflate them: citations use `page`, tracing back to a file uses `page_index`. `citations.py` reads `region_type` for the section label, so a chunk missing it silently degrades to a body-only citation. Body text is split by `TextSplitter`; a sidebar/info-box stays atomic unless it exceeds `BOX_ATOMIC_MAX_CHARS` (1.5 × `CHUNK_SIZE`), in which case it is split but keeps its `region_type`.

`--etl` and `--text-only` both go through `_index_source_pages()` in `main.py`, one page at a time; a page that raises is logged, left unmarked, and retried next run. The legacy whole-page `RobustOCRLoader` is **not** a text path any more — `ocr_image()` survives only to supply full-page OCR text for figure-caption anchoring on the image side.

### Retrieval flow (`src/rag/`)
1. `hybrid_retriever.py::HybridRetriever.search()` is the entry. It calls `query_intent.py::is_image_only_query()` to **route**: image-only queries (e.g. "cho tôi hình con X") skip text retrieval entirely.
2. Text side uses a **RelevanceGatedRetriever** — a relative-distance gate (`RETRIEVER_DISTANCE_MARGIN`) drops chunks far from the best match, fetching `FETCH_K` then keeping ≤`MAX_K`.
3. Image side combines CLIP similarity + metadata search + a **lexical phrase channel** (accent-sensitive; distinguishes e.g. "trâu" vs "trầu") + rerank, gated by `IMAGE_RELEVANCE_THRESHOLD`.
4. `chain.py::BiologyRAG` builds the prompt and calls the Qwen2.5 LLM (`llm.py`), returning answer + image gallery.

### Image ETL — the complex, actively-evolving part (`src/etl/image_processor.py`, ~4000 lines)
- **Entry point is `extract_images_from_source(source, ocr_text_per_page, pages=…)`** — it takes a `PageSource` and a list of **source page numbers**, and loads each page via `_load_page_image()` (PNG → RGB array + PIL image). No poppler, no DPI: the detector now sees the native 1094×1536 pixels instead of a 150-DPI render, which is why `IMAGE_EXTRACTION_VERSION` was bumped to `v17_png_source`. **The crop geometry has not been re-QA'd on this source** — run the visual QA tool before trusting it.
- **Per-variant subclasses**: `make_image_processor(name)` → `get_pdf_variant()` inspects the name for `ctst`/`kntt`/`cd` keywords and returns the matching processor (`CtsstImageProcessor`, `KnttImageProcessor`, base `ImageProcessor` for CD). The folder name `SGK_KHTN_6_KNTT` resolves to `kntt`. Only KNTT exists in the corpus now, so the CD/CTST branches are scheduled for deletion.
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
- **Windows is the primary dev environment.** OCR needs Tesseract (`vie`) via `TESSERACT_CMD`; Poppler (`POPPLER_PATH`) is only still needed by the legacy PDF paths. Prebuilt zips are in `windows_tools/`.
- **Visual QA for layout**: `python -m src.test.qa_layout --book SGK_KHTN_6_KNTT --page 10` draws the segmented regions; `--pages 10,11,12 --report` prints regions-per-page (the recall metric). `SGK_KHTN_6_KNTT/page_010.png` is the reference page — a human counts ≥4 coloured boxes on it.
- **Running the ETL on Colab**: `document/colab_runtime_etl.ipynb` is the single runbook (the user's working notebook) — mandatory `--build-manifests` step, `RAG_MANIFEST_DIR` (manifests travel with the repo while the DB lives on Drive), version-gate semantics, and which side of the pipeline is trustworthy today. Keep it in sync when the ETL CLI changes; don't start a parallel runbook doc.
- **Image-review JSON semantics are subtle and easy to get wrong**: `--apply-image-review` upserts per-item (removing an item from the array does NOT delete it from the DB); only `--replace-image-db` treats the file as the full source of truth. To remove a figure from retrieval, set `review_status=rejected|deleted` / `is_active=false` / `delete=true`. See README §6.
- Detailed per-variant image-ETL runbook: `skills/etl-textbook-images/runbook.md`.
