# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Vietnamese-language **RAG system over scanned Vietnamese science textbooks (SGK KHTN, THCS)**. Source data is scanned-image PDFs, so the pipeline OCRs Vietnamese text and crops figures per publisher layout, then serves hybrid text+image retrieval with a local Qwen2.5 LLM answering in Vietnamese with citations. Scaling target is ~12 books across three publishers: **Cánh Diều (CD), Chân Trời Sáng Tạo (CTST), Kết Nối Tri Thức (KNTT)**.

Most docs (`README.md`, `document/`) are in Vietnamese; code and comments mix English/Vietnamese. Match the surrounding language when editing.

## Active redesign (2026-08) — read this first

A layout-aware ETL + retrieval-reranking rebuild is **in progress** (deadline-driven). Source of truth:
- **Decisions:** `document/decision_log.html` (data-driven `DECISIONS[]` log; every decision is recorded here).
- **Spec:** `document/specs/2026-08-18-rag-etl-retrieval-redesign-design.md`. Implementation plan lives alongside in `document/specs/`.

Key locked choices: full clean rebuild of `database/` (re-ETL all 12 books on Colab Pro); new `layout_segmenter` spine (classical CV) separating main-text / sidebar / figure regions; text embedding → `BAAI/bge-m3`; add `BAAI/bge-reranker-v2-m3` cross-encoder; Vietnamese diacritic post-correction; sidebar/info-box as separate labeled chunks; checkpoint keyed on **content hash** not filename.

**Operating rules for this work:** log each decision in `document/decision_log.html`; keep spec/plan in `document/specs/`; keep CLAUDE.md + memory current; **adversarially review every code change for hidden bugs before claiming done.**

## Commands

All commands run through `main.py` (from repo root). There is no build step — it's a Python app.

```bash
pip install -r requirements.txt
cp .env.example .env          # then set HF_TOKEN (required) and USE_GPU

# ETL (offline indexing) — has checkpoint resume; re-runs skip processed pages
python main.py --text-only    # OCR + chunk + index text → ChromaDB
python main.py --image-only   # crop figures + caption + index images
python main.py --etl          # both

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
- `biology_text` — OCR'd text chunks (MiniLM embeddings, `CHUNK_SIZE=400/overlap=120`)
- `biology_images` — figure crops (CLIP embeddings)
- `biology_image_metadata` — caption/keyword metadata for figures (separately searchable)
- `processing_status` — per-page checkpoint state enabling resumable ETL

Everything writable lives under `database/` (`PERSIST_DIR`), overridable via `RAG_DATABASE_DIR` (point at Google Drive on Colab). `datasources/` holds input PDFs.

### Retrieval flow (`src/rag/`)
1. `hybrid_retriever.py::HybridRetriever.search()` is the entry. It calls `query_intent.py::is_image_only_query()` to **route**: image-only queries (e.g. "cho tôi hình con X") skip text retrieval entirely.
2. Text side uses a **RelevanceGatedRetriever** — a relative-distance gate (`RETRIEVER_DISTANCE_MARGIN`) drops chunks far from the best match, fetching `FETCH_K` then keeping ≤`MAX_K`.
3. Image side combines CLIP similarity + metadata search + a **lexical phrase channel** (accent-sensitive; distinguishes e.g. "trâu" vs "trầu") + rerank, gated by `IMAGE_RELEVANCE_THRESHOLD`.
4. `chain.py::BiologyRAG` builds the prompt and calls the Qwen2.5 LLM (`llm.py`), returning answer + image gallery.

### Image ETL — the complex, actively-evolving part (`src/etl/image_processor.py`, ~4000 lines)
- **Per-variant subclasses**: `make_image_processor(pdf_filename)` → `get_pdf_variant()` inspects the filename for `ctst`/`kntt`/`cd` keywords and returns the matching processor (`CtsstImageProcessor`, `KnttImageProcessor`, base `ImageProcessor` for CD). Each publisher has its own caption-regex / layout heuristics — changes are almost always variant-scoped, not global.
- Detection is **anchor-first + deterministic** (find figure-caption text anchors, then crop the band above), with OWL-ViT as a secondary detector. When touching this, verify against the visual QA tool above, not just unit output.
- `IMAGE_EXTRACTION_VERSION` in `.env` gates the crop cache: **bump it to force re-extraction** after changing crop logic (otherwise checkpoints skip already-processed pages).

### API + app (`src/app/`)
- `dependencies.py::AppServices` is a **singleton** that loads all heavy models once (VectorDB, HybridRetriever, LLM, RAG chain). Never instantiate models per-request; go through this.
- `api.py` exposes chat (+SSE stream at `/api/chat/stream`), background ETL upload, and image-metadata CRUD for the review UI.

## Key conventions

- **Models are configured via `.env` / `src/config.py`**, not hardcoded. Defaults: MiniLM (embeddings), Qwen2.5-3B-Instruct (LLM), CLIP-ViT (image), OWL-ViT (detection), Vintern-1B (captioning). `src/utils/download_models.py` pre-fetches them for offline runs.
- **Windows is the primary dev environment.** OCR needs Poppler + Tesseract (`vie`); paths set via `TESSERACT_CMD` / `POPPLER_PATH`. Prebuilt zips are in `windows_tools/`.
- **Image-review JSON semantics are subtle and easy to get wrong**: `--apply-image-review` upserts per-item (removing an item from the array does NOT delete it from the DB); only `--replace-image-db` treats the file as the full source of truth. To remove a figure from retrieval, set `review_status=rejected|deleted` / `is_active=false` / `delete=true`. See README §6.
- Detailed per-variant image-ETL runbook: `skills/etl-textbook-images/runbook.md`.
