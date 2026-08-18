# Runbook — M1: rebuild the text index (layout-aware ETL)

Clean full rebuild of the **text** side of the RAG index (`biology_text`) with the
new layout-aware pipeline, on **Google Colab Pro** (GPU, DB on Google Drive).
Decisions: see `document/decision_log.html` (D-04 clean rebuild, D-05 Approach A,
D-07 bge-m3, D-13 M1 scope). This runbook is the text pass only; images are M3.

## 0. Prerequisites
- Corpus in `datasources/` — 12 student SGK PDFs. Confirm **KNTT8 and KNTT9 are the
  clean student editions** (not the old teacher-edition / 2-up spreads — see
  [[corpus_audit_2026_07]] / D-02, D-03).
- Tesseract with Vietnamese (`vie`) + Poppler available; `TESSERACT_CMD` /
  `POPPLER_PATH` set (or on PATH).

## 1. `.env`
```env
EMBEDDING_MODEL=BAAI/bge-m3          # D-07: 1024-dim, free; rebuild is required for the new dim
DIACRITIC_FIX_ENABLED=true           # D-09
RAG_DATABASE_DIR=/content/drive/MyDrive/project_bio_rag/database   # DB survives Colab disconnects
# RENDER_DPI=220 (default is fine)
```

## 2. Install (pinned, reproducible)
```bash
pip install -r requirements.txt
```
`requirements.txt` pins `langchain-chroma>=0.2.6,<0.3` + `chromadb>=1.5.0,<2.0`
(the known-good pair; unbounded versions previously resolved an incompatible pair →
`KeyError '_type'` when opening the DB).

## 3. Wipe the old index + checkpoints (clean rebuild — D-04)
The old DB was built with an incompatible ChromaDB and with the old KNTT8/KNTT9.
Delete everything writable under `database/` (or the `RAG_DATABASE_DIR` target):
```bash
rm -rf "$RAG_DATABASE_DIR"/chroma.sqlite3 "$RAG_DATABASE_DIR"/*/ \
       "$RAG_DATABASE_DIR"/processed_files.txt "$RAG_DATABASE_DIR"/processed_images.txt
```
Removing `processed_files.txt` matters: the same-named replaced KNTT PDFs must be
reprocessed. (The skip decision is now hash-based — D-09/Task 9 — but starting clean
avoids any stale state.)

## 4. Run the text ETL
```bash
python main.py --text-only
```
Per page the pipeline runs: render (PyMuPDF, RENDER_DPI) → preprocess (deskew stub +
KNTT left-margin stamp mask) → segment (colored + **pale-tint** boxes, figures/photos
rejected) → detect printed page number → per-region OCR (sidebars excluded from body)
→ diacritic fix → structure-aware chunk. Indexing is **per-page and resume-safe**
(deterministic ids `{pdf_hash}_p{page}_c{idx}` upsert; a Colab disconnect + resume
re-processes only unfinished pages — no duplicate chunks).

## 5. Sanity checks (do these before trusting the index)
```python
# chunk count + region-type mix
from src.rag.vectorstore import VectorDB
col = VectorDB().db._collection
print("biology_text items:", col.count())
g = col.get(include=["metadatas"], limit=5000)
from collections import Counter
print(Counter(m.get("region_type") for m in g["metadatas"]))     # expect mostly 'body' + some 'sidebar'/'info_box'
print(Counter(m.get("source") for m in g["metadatas"]))          # all 12 books present, none dominated by the old KNTT
```
- Spot-check 5 body chunks: **no sidebar-question text mixed into body flow**.
- Visual QA any page: `python -m src.test.qa_layout --pdf "<name>.pdf" --page <0-based> --out-dir report/layout_qa` and eyeball the region overlay.

## 6. Known follow-ups (tracked in the SDD ledger)
- **CD variant** pale-box detection not yet visually validated — run the qa_layout
  overlay on a CD page (e.g. `SGK KHTN8 CD.pdf`) and adjust `segmenter._VARIANT_PARAMS["cd"]`
  if pale boxes are missed or figures are boxed.
- **Page-number OCR** reads 4/5 sampled pages exactly; low-res CD8 (97 DPI) misses and
  falls back to `pdf_index+1` (off by the front-matter offset). Acceptable; revisit if
  citations look wrong.
- **Per-page PDF reopen** in `LayoutOCRLoader.load_page` is a minor perf cost (open the
  doc once if the 12-book run is too slow).
- Next: **M2** (bge-m3 A/B + bge-reranker-v2-m3 + prompt/citation), then **M3** (images).
