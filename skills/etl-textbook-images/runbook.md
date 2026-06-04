# Runbook — image ETL ops

Step-by-step playbook for every recurring task.

---

## A. Process a brand-new SGK book

```powershell
# 1. drop the file
copy <wherever>\<book>.pdf datasources\

# 2. quick QA on first 20 pages
python -m src.test_etl.test_image_extraction_full `
  --pdf "datasources/<book>.pdf" `
  --pages 1-20 `
  --out-dir scripts/_out_test_etl_full/<book>

# 3. open the index in a browser and scan visually
start scripts/_out_test_etl_full/<book>/_index.html

# 4. if QA passes, run the production pipeline (writes ChromaDB)
python main.py
```

**What to look for in QA:**
- Every `Hình X.Y` page has at least one `composite_figure` or
  `single_figure` region.
- Every `Em có biết` / `Tìm hiểu thêm` / `Vận dụng` etc. is captured.
- No `Bảng X.Y` row appears as a region.
- Tool grids (instrument rows) are captured as `tool_group` if the page
  has them.

If anything is missing or wrong, go to runbook §D.

---

## B. Reprocess all pages after a detector change

```powershell
# 1. bump the version so the status DB invalidates per-page caches
# edit src/config.py:  IMAGE_EXTRACTION_VERSION = "v8_<your-tag>"

# 2. re-run the QA test on representative pages first
python -m src.test_etl.test_image_extraction_full --pages 6,13,22,30,40,55,70,85,100

# 3. if good, run the pipeline (skips pages already at this version)
python main.py
```

---

## C. Batch QA across many pages

```powershell
# every page
python -m src.test_etl.test_image_extraction_full --all

# subset
python -m src.test_etl.test_image_extraction_full --pages "6,13,22-25,40"
```

Outputs:
- `scripts/_out_test_etl_full/page_NNN/00_page_snapshot.png` – the rendered page
- `…/01_anchors.png` – OCR text anchors colour-coded
- `…/02_visual_regions.png` – OWL-ViT + dashed/framed visual cells
- `…/03_final_regions.png` – final extracted regions
- `…/region_NN__<type>__<caption>.png` – one PNG per emitted crop
- `_summary.csv` – page-by-page anchor / region counts
- `_index.html` – clickable visual index

---

## D. Diagnosing a missed extraction

> **Always work top-down: anchor → visual → geometry.**

### D.1 Anchor missing (`01_anchors.png` has no box where you expected one)
The OCR text didn't match the regex. Either:
- The OCR garbled the line — open the page snapshot, look at the actual
  text. Possible fixes: improve OCR (paddleocr, vietocr), or hard-code an
  override in `_classify_text_anchors`.
- The regex is too strict. Edit one of:
  - `FIG_CAPTION_STRICT_REGEX` (figure caption)
  - `TABLE_CAPTION_STRICT_REGEX` (table caption)
  - `_INFO_BOX_TITLE_KEYS` (info-box titles)
  - `TOOL_GROUP_LABEL_REGEX` (tool group labels)
  - `SUB_FIGURE_LABEL_REGEX` (a, b, c, … sub-figures)

### D.2 Anchor detected but visual cell missing (`02_visual_regions.png` lacks a red box)
OWL-ViT did not return a box for the cell. Options:
- Lower `OWL_VIT_CONFIDENCE_THRESHOLD` in `.env` from `0.1` to `0.05`.
- Add a more specific query to `OWL_VIT_TEXT_QUERIES` describing the
  missed image type ("a line drawing of a ruler", "a measuring scale").
- If the cell sits inside a dashed border, the `dashed_regions` detector
  should still catch it; verify by inspecting purple boxes in `02_*.png`.

### D.3 Visual cell present but final region wrong (`03_final_regions.png` problem)
This is geometry. Common causes and fixes:

| Symptom | File method | Knob |
|---|---|---|
| Composite is too wide / pulls cells from a neighbour caption | `_assign_regions_to_captions` | reduce `dx * 1.4` weight, lower `vgap > page_height * 0.42` |
| Composite top overshoots into question prompt | `_build_figure_composites` | the prompt anchor must be in `question_prompts` AND have horizontal overlap with the composite |
| Info-box bottom too short (cuts off portrait) | `_build_info_panels` | the visual region must overlap the panel y-band; widen `ry1 > panel_y_bottom + 0.04` |
| Sub-figures merged into 1 | `_split_composite_sub_figures` | each visual cell needs a sub-label within `vgap < page_height * 0.06`; if labels are merged in OCR, see runbook §D.4 |
| Tool group bbox cut at right edge | `_build_dashed_tool_groups` | OWL-ViT missed the last cell — the per-tool text labels widen the bbox to compensate; if missing, lower OCR confidence threshold |

### D.4 Merged OCR lines (Tesseract glues neighbours)
- "a) Tìm hiểu … b) Tìm hiểu … c) Tìm kiếm …" merged into one sub_label
  line → handled by per-region label slicing in `_split_composite_sub_figures`.
- "Hình 14.1. Người cổ đại  Hình 14.2. Người hiện đại" merged into one
  figure caption → handled by `_split_merged_figure_caption`.

If a new merge pattern appears, add a similar splitter.

---

## E. Adding a new info-box title (e.g. "Lưu ý")

```python
# src/etl/image_processor.py
_INFO_BOX_TITLE_KEYS: List[Tuple[str, str]] = [
    ...,
    ("luu y", "activity_box"),
]
```

Bump `IMAGE_EXTRACTION_VERSION` and re-run.

---

## F. Reset processing status for a single PDF

The status DB key is `pdf_hash:page_num:version`. To force re-processing:

```python
# In a python shell:
from src.etl.processing_status import ProcessingStatus
status = ProcessingStatus()
# either bump IMAGE_EXTRACTION_VERSION (preferred) or reset the table
```

The `reset_status.py` script in the project root provides a CLI for this.
