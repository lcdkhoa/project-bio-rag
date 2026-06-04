---
name: etl-textbook-images
description: |
  Anchor-first, column-aware image ETL for scanned Vietnamese textbook PDFs.
  Use this skill when (a) adding a new textbook PDF to `datasources/`,
  (b) extraction quality regresses on existing books, or
  (c) tuning the detection rules in `src/etl/image_processor.py`.
metadata:
  type: etl-pipeline
  language: python
  applies_to: scanned-vietnamese-sgk
---

# ETL — Textbook image extraction (v8 column-aware anchor-first)

## v8 changes (column-awareness + robust info boxes)

v8 keeps the v7 anchor-first philosophy but fixes the multi-column and
robustness problems found on dense pages (e.g. page 70):

1. **OCR gutter split** (`_collect_page_text_lines`) — a tesseract line is
   split wherever two words are separated by a gap wider than ~5.5 % page
   width. Without this, a left-column cell label and a right-column question
   prompt on the same scan row merged into one full-width line, which made
   figures/info boxes span both columns.
2. **Colour-detected info headers** (`_detect_colored_info_headers`) — info
   boxes are marked by a pink/blue header. When the header is a filled tab
   with white text, page-level OCR misses it entirely. v8 finds the coloured
   header directly and re-OCRs it (white-text-on-colour preprocessing) to
   recover "Em có biết" / "Tìm hiểu thêm". This is merged with the OCR-title
   anchors.
3. **Column-aware panels & tables** — `_build_info_panels` and
   `_build_table_zones` accumulate a column and refuse text from the other
   column, so a right-column box never swallows the left column.
4. **Info/table zones built BEFORE figures** and passed as exclusion +
   column-separator inputs to figure assignment — a figure never absorbs a
   cell that lies inside an info box / table.
5. **Two-tier caption assignment** (`_assign_regions_to_captions`) — a cell
   prefers a caption it horizontally overlaps (splits side-by-side figures,
   page 85); only if none overlaps does it fall back to a centred caption
   within tolerance and not separated by an other-column anchor.
6. **Text-region filter** (`_filter_text_visual_regions`) — OWL-ViT
   false-positives on headings/paragraphs (no colour + ≥2 alphabetic words)
   are dropped so they can't be assigned to a caption and balloon a figure.
   Wide line-drawings (rulers, aspect ≥ 3) are kept.
7. **Visual-ceiling + narrow-label top-growth** (`_grow_figure_top`,
   `_snap_figure_to_column`) — a tall list-figure (page 70 Hình 12.6) whose
   interior cells OWL-ViT missed is rescued by growing UP through its own
   narrow cell-labels, bounded by the topmost visual cell and the gutter.
   Full-width body paragraphs are never absorbed.

Smoke status after v8: pages 6, 70, 85, 30, 40, 55 correct. Thin
line-drawing rulers (page 22) remain limited by OWL-ViT recall.

# ETL — Textbook image extraction (v7 anchor-first, baseline rules)

The pipeline turns a scanned SGK page into a normalised set of image crops:

```
PDF page  →  OCR text lines  →  anchor classification  →  region builders  →  final crops
                                       │                       │
                                       ▼                       ▼
                                  Hình X.Y caption       composite_figure
                                  Bảng X.Y caption       (rejected)
                                  Em có biết / ...       textbook_info_box
                                  a) b) c) labels        sub_figure splits
                                  Dụng cụ ... labels     tool_group
                                  Hãy quan sát ...       (rejected)
```

Every emitted region is whitelisted by an anchor — the detector never
returns a free-standing illustration that lacks a caption or panel
title, except labelled dashed-frame tool groups (page-13 case).

---

## 1. Rule book

### 1.1 KEEP
| Category | Anchor | Bbox derivation |
|---|---|---|
| `composite_figure` | `^Hình X.Y` caption **AND** ≥2 visual cells **AND** at least one `a)`/`b)`/… label inside | bbox grows UP from caption to cover assigned visual regions; ceiling is the nearest blocker (other caption, info-title, question prompt) above |
| `single_figure` | `^Hình X.Y` caption with no sub-labels (or only one visual cell) | same as composite, but no sub-figure splitting |
| `sub_figure` | `a)…h)` label below a visual cell inside a `composite_figure` | one crop per cell, with its label slice |
| `textbook_info_box` | OCR line starting with `Em có biết` | grows DOWN from title through continuous text lines; widens to absorb adjacent visual cell (e.g. portrait inside the panel) |
| `activity_box` | `Tìm hiểu thêm` / `Mở rộng` / `Kiến thức mới` / `Thực hành` / `Vận dụng` / `Luyện tập` | same as info-box |
| `tool_group` | `Dụng cụ đo …` / `Một số dụng cụ` / `Hộp dụng cụ` label sitting above a row of ≥2 visual cells | bbox = label ∪ row cells ∪ per-tool name labels just below; dashed-border outer box widens bbox when present |

### 1.2 REJECT
- `^Bảng X.Y` captions and the rows continuously below them (table exclusion zone).
- Lines matched by `QUESTION_PROMPT_PATTERNS` (Hãy quan sát, Em đã thấy, …) — used only as composite-ceiling blockers.
- Free-standing illustrations with no caption, info title or tool label.
- "Học xong bài học này, em có thể:" / "Em có thể:" learning-objective headers (explicitly excluded from info-box matcher).

### 1.3 OCR edge cases the rules already handle
- Tesseract often glues two side-by-side captions into one line; the
  classifier splits any line that carries multiple `Hình X.Y` markers
  into one anchor per marker (see `_split_merged_figure_caption`).
- "Trong phòng thực hành" body text used to false-match the info-box
  regex; `_match_info_box_title` now requires `Em có biết` / `Tìm hiểu
  thêm` / … to *start* the line and be followed by ≤30 chars.

---

## 2. File map

```
src/etl/image_processor.py                 ← the detector (v8)
  Anchors / regex
  ├─ FIG_CAPTION_STRICT_REGEX               Hình X.Y anchor
  ├─ TABLE_CAPTION_STRICT_REGEX             Bảng X.Y reject
  ├─ INFO_BOX_TITLE_REGEX / _INFO_BOX_TITLE_KEYS
  ├─ TOOL_GROUP_LABEL_REGEX                 dụng cụ … / một số …
  OCR + anchors
  ├─ _collect_page_text_lines               OCR, with 2-column GUTTER SPLIT
  ├─ _classify_text_anchors                 lines → buckets
  ├─ _match_info_box_title                  strict, start-of-line
  ├─ _detect_colored_info_headers           pink/blue header + re-OCR (v8)
  Visual detection
  ├─ _detect_regions_with_owlvit            zero-shot regions
  ├─ _detect_framed_regions / _detect_dashed_frame_regions
  ├─ _detect_object_blobs                   CC fallback for object photos (v8)
  ├─ _filter_text_visual_regions            drop OWL text false-positives (v8)
  Region builders (order matters: tables+info BEFORE figures)
  ├─ _build_table_zones                     exclusion zone (column-aware)
  ├─ _build_info_panels                     panel (column-aware)
  ├─ _assign_regions_to_captions            two-tier hov / centred (v8)
  ├─ _build_figure_composites
  │    ├─ _grow_figure_top                  narrow-label top-growth
  │    └─ _snap_figure_to_column            gutter clip + label widen
  ├─ _build_dashed_tool_groups
  ├─ _split_composite_sub_figures
  └─ detect_regions_anchor_first            top-level entrypoint
src/test_etl/test_image_extraction_full.py  ← single / batch / --sample-books QA
src/config.py                               ← IMAGE_EXTRACTION_VERSION (v8)
```

### Multi-book QA sampling

```powershell
# 5 random pages from EVERY pdf in datasources/, deterministic by --seed
python -m src.test_etl.test_image_extraction_full --sample-books 5 --seed 42
start scripts/_out_test_etl_full/_sample/_index.html
```

## 3. Publisher routing (v8 multi-publisher)

All entry-points now use `make_image_processor(pdf_filename)` to get the
right processor class.  Add the book name to the dispatching table if a new
publisher needs customisation.

```python
from src.etl.image_processor import make_image_processor

proc = make_image_processor("SGK KHTN 6 CTST.pdf")   # → CtsstImageProcessor
proc = make_image_processor("SGK KHTN 7 CD.pdf")     # → ImageProcessor (CD)
```

| Keyword in filename | Variant key | Class |
|---|---|---|
| `_CTST` (or `<space>CTST`) | `ctst` | `CtsstImageProcessor` |
| `_KNTT` / `<space>KNTT` | `kntt` | `ImageProcessor` (same as CD for now) |
| anything else | `cd` | `ImageProcessor` |

### CTST differences (`CtsstImageProcessor`)

| Aspect | CD behaviour | CTST behaviour |
|---|---|---|
| Figure caption | `^Hình X.Y` | `^[ÀÁ▲.]? Hình X.Y` — prefix `▲` OCR'd as `À`/`Á` |
| Triangle strip | — | Strips prefix before storing metadata so caption reads "Hình X.Y …" |
| Info-box titles | Em có biết, Tìm hiểu thêm, … | Bài tập, Khám phá, Vận dụng, Tổng kết, Ôn tập, Thực hành, Thí nghiệm |
| Sub-figure labels | `a)`, `b)` … | identical |
| Composite grouping | v8 column-aware | identical (inherited) |

### Adding a new publisher

1. Identify the figure caption format and any publisher-specific info-box titles.
2. Subclass `ImageProcessor`.
3. Override `_classify_text_anchors` and `_INFO_BOX_TITLE_KEYS`.
4. Add a keyword check in `get_pdf_variant`.
5. Return the new class from `make_image_processor`.
6. Add a smoke-test page set to the runbook.

`IMAGE_EXTRACTION_VERSION` gates the per-page status DB — bump it whenever
the detector logic changes so pages are reprocessed on next run.

---

## 3. Workflows

### 3.1 Adding a new textbook PDF
1. Drop the file in `datasources/`.
2. Run a quick visual QA:
   ```powershell
   python -m src.test_etl.test_image_extraction_full `
     --pdf "datasources/<new-book>.pdf" `
     --pages 1-20 `
     --out-dir scripts/_out_test_etl_full
   start scripts/_out_test_etl_full/_index.html
   ```
3. Scan the HTML index. For each page:
   - Confirm every `Hình X.Y` is captured as `composite_figure`/`single_figure`.
   - Confirm `Em có biết` / `Tìm hiểu thêm` panels are intact (incl. embedded portraits).
   - Confirm `Bảng X.Y` rows are NOT extracted.
   - Spot-check that any dashed-bordered tool grid is captured as `tool_group`.
4. If everything passes, run the full pipeline (writes to DB):
   ```powershell
   python main.py            # or whichever entry the project uses
   ```

### 3.2 Tuning when extraction breaks on a new layout
- Re-run `test_image_extraction_full` on the offending page(s).
- Open `01_anchors.png` first. **If the right anchor is missing, the rule fails before any geometry.** Most regressions are anchor-detection issues:
  - tighten / loosen one of the regexes at the top of `image_processor.py`,
  - or add a new helper to `_classify_text_anchors`.
- Open `02_visual_regions.png` next. If OWL-ViT missed a cell, options:
  - lower `OWL_VIT_CONFIDENCE_THRESHOLD` in `.env` (default 0.1),
  - add a more specific query to `OWL_VIT_TEXT_QUERIES`,
  - or rely on the dashed/framed detectors which work on HSV strokes.
- Open `03_final_regions.png` last for geometry / merging issues.

### 3.3 Adding a new info-box title
Append the keyword (normalised, no accents) to `_INFO_BOX_TITLE_KEYS`:
```python
_INFO_BOX_TITLE_KEYS = [
    ("em co biet", "textbook_info_box"),
    ("tim hieu them", "activity_box"),
    ...,
    ("new key here", "activity_box"),
]
```
Then bump `IMAGE_EXTRACTION_VERSION` so processed pages are re-evaluated.

### 3.4 Adding a new tool-group label pattern
Extend `TOOL_GROUP_LABEL_REGEX`. The regex anchors at line start and
matches noun phrases that always head a row of instruments.

---

## 4. Calibration knobs

| Knob | File | Default | Effect |
|---|---|---|---|
| `OWL_VIT_CONFIDENCE_THRESHOLD` | `.env` / `config.py` | 0.1 | lower → more cells but more noise |
| `OWL_VIT_TEXT_QUERIES` | `image_processor.py` | 20 phrases | controls what OWL-ViT looks for |
| `IMAGE_EXTRACTION_VERSION` | `config.py` | `v7_anchor_first` | bump to force re-processing |
| margin in `_build_figure_composites` (`page_height * 0.42` vertical, `1.0 + 1.4` weights) | `image_processor.py` | tuned for A4@150dpi | adjust if a new book uses a different paper size |
| `max_gap = page_height * 0.055` in `_build_info_panels` | `image_processor.py` | 5.5% | raise if a panel has unusually large internal padding |
| `_dedupe_visual_regions` `iou_threshold` | `image_processor.py` | 0.55 (visual), 0.65 (tool cells) | lower → more merging |

---

## 5. Known limitations
- Tesseract sometimes garbles the small "Em có biết" header (e.g. page 22).
  When OCR fails on the anchor, the panel is not detected. Mitigations:
  upgrade the OCR (paddle-OCR / VietOCR), or maintain a per-PDF override map.
- Line-drawing figures (rulers, microscopes in pencil sketch) are below
  OWL-ViT's `0.1` confidence for some queries. If a new book has many of
  these, add `"a black and white line drawing"` to `OWL_VIT_TEXT_QUERIES`.
- `_split_merged_figure_caption` partitions the merged line linearly by
  character count. Works for normal Vietnamese spacing; if a book uses
  exotic kerning, re-OCR the page with `--psm 4` (single column) and feed
  results back.

---

## 6. Smoke-test pages (per book)

When validating a new run, always inspect these layouts at minimum:

| Page type | Example in SGK KHTN 6 CD |
|---|---|
| Composite figure with a–g sub-labels | page 6 (Hình 1.1) |
| Dashed-border tool grid w/o caption | page 13 |
| Two captions stacked (single + composite) | page 22 (Hình 3.3 + 3.4) |
| Side-by-side captions on same OCR line | page 85 (Hình 14.1 + 14.2) |
| Bảng X.Y to be rejected | page 55 (Bảng 9.1), page 70 (Bảng 12.1) |
| Em có biết panel with embedded portrait | page 6 (Marie Curie) |

For each new book, identify the analogous pages and rebuild the
smoke-test list before running the full pipeline.
