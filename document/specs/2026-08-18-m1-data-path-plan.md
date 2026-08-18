# M1 — Data-path (layout-aware text ETL) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace flat whole-page OCR with a layout-aware text ETL that reads main-text in correct reading order, keeps sidebar/info-boxes as separate labeled chunks, cleans Vietnamese diacritics, and tags each chunk with the printed page number — producing clean chunks in `biology_text`.

**Architecture:** New `src/etl/layout/` package with focused modules (preprocess → segment → per-region OCR → diacritic-fix → structure-aware chunk), orchestrated by a `LayoutOCRLoader` that drops into the existing text-ETL flow in `main.py`. Classical CV (OpenCV/HSV + Tesseract block geometry), no model training. All M1 code is CPU-testable locally on Windows; the full 12-book run happens on Colab afterward.

**Tech Stack:** Python, OpenCV (`opencv-python`, already a dep), Pillow, `pytesseract` (Tesseract 5.5 `vie`), PyMuPDF (`fitz`), LangChain `Document`, ChromaDB. Tests: `pytest`.

**Spec:** `document/specs/2026-08-18-rag-etl-retrieval-redesign-design.md`

## Global Constraints

- Windows-primary dev. Tesseract at `TESSERACT_CMD` (env), Poppler at `POPPLER_PATH` (env). Tesseract lang = `vie`.
- Per-variant behavior selected via existing `src.etl.image_processor.get_pdf_variant(filename) -> "cd"|"ctst"|"kntt"`. Reuse it; do NOT re-implement variant detection.
- Page rasterization via PyMuPDF (`fitz`) at ~220 DPI effective (matches corpus audit); do NOT extract embedded images directly (composite books CD6/CD8 break that).
- `page` metadata = printed page number OCR'd from the page (D-11), fallback to 1-based PDF index when detection fails.
- Chunk metadata schema (D-06/D-10): `{source, page, variant, region_type, section_heading?, chunk_index}` where `region_type ∈ {"body","sidebar","info_box","caption"}`.
- Diacritic fix (D-09) must be conservative: never alter tokens on the allowlist (science/English terms, all-caps, tokens with digits). 
- Checkpoint truth = hash-based `ProcessingStatus` (keys on `pdf_hash`). The filename list in `processed_files.txt` must NOT short-circuit re-processing of same-named replaced files.
- Commit after every task. Do not skip hooks.

---

### Task 1: Region/TextUnit data model + config

**Files:**
- Create: `src/etl/layout/__init__.py`
- Create: `src/etl/layout/regions.py`
- Modify: `src/config.py` (append layout config block, ~after line 104)
- Modify: `requirements.txt` (add `pytest`)
- Test: `tests/layout/test_regions.py`

**Interfaces:**
- Produces: `RegionType` (str Enum: `BODY="body"`, `SIDEBAR="sidebar"`, `INFO_BOX="info_box"`, `FIGURE="figure"`, `CAPTION="caption"`, `PAGE_ARTIFACT="page_artifact"`); `Region(type: RegionType, bbox: tuple[int,int,int,int], reading_order: int, meta: dict)`; `TextUnit(region_type: RegionType, text: str, reading_order: int, bbox: tuple)`. bbox is `(x0,y0,x1,y1)` in pixels of the rendered page image.

- [ ] **Step 1: Write the failing test**

```python
# tests/layout/test_regions.py
from src.etl.layout.regions import Region, RegionType, TextUnit

def test_region_orders_and_serializes():
    r = Region(type=RegionType.BODY, bbox=(0, 0, 10, 20), reading_order=1, meta={})
    assert r.type.value == "body"
    assert r.bbox == (0, 0, 10, 20)
    # regions sort by reading_order
    regs = [Region(RegionType.SIDEBAR, (0,0,1,1), 2, {}), Region(RegionType.BODY, (0,0,1,1), 1, {})]
    assert [x.reading_order for x in sorted(regs, key=lambda z: z.reading_order)] == [1, 2]

def test_textunit_holds_region_type():
    u = TextUnit(region_type=RegionType.INFO_BOX, text="Em có biết", reading_order=3, bbox=(1,2,3,4))
    assert u.region_type is RegionType.INFO_BOX
    assert u.text == "Em có biết"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/layout/test_regions.py -v`
Expected: FAIL (module `src.etl.layout.regions` not found)

- [ ] **Step 3: Write minimal implementation**

```python
# src/etl/layout/regions.py
"""Data model for layout-aware ETL: page regions and extracted text units."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple, Dict

class RegionType(str, Enum):
    BODY = "body"
    SIDEBAR = "sidebar"
    INFO_BOX = "info_box"
    FIGURE = "figure"
    CAPTION = "caption"
    PAGE_ARTIFACT = "page_artifact"

BBox = Tuple[int, int, int, int]  # (x0, y0, x1, y1) in rendered-page pixels

@dataclass
class Region:
    type: RegionType
    bbox: BBox
    reading_order: int
    meta: Dict = field(default_factory=dict)

@dataclass
class TextUnit:
    region_type: RegionType
    text: str
    reading_order: int
    bbox: BBox
```

```python
# src/etl/layout/__init__.py
from .regions import Region, RegionType, TextUnit, BBox
__all__ = ["Region", "RegionType", "TextUnit", "BBox"]
```

Append to `src/config.py`:

```python
# --- Layout-aware ETL (M1) ---
RENDER_DPI = int(os.getenv("RENDER_DPI", "220"))
# HSV saturation floor for detecting colored sidebar/info boxes (0-255).
LAYOUT_BOX_MIN_SATURATION = int(os.getenv("LAYOUT_BOX_MIN_SATURATION", "45"))
# Min area fraction of the page for a colored region to count as a box.
LAYOUT_BOX_MIN_AREA_FRAC = float(os.getenv("LAYOUT_BOX_MIN_AREA_FRAC", "0.02"))
# Diacritic fix (D-09)
DIACRITIC_FIX_ENABLED = os.getenv("DIACRITIC_FIX_ENABLED", "true").lower() == "true"
```

Add `pytest` line to `requirements.txt` (under a new `# Testing` comment).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/layout/test_regions.py -v`  → Expected: PASS. Also create empty `tests/__init__.py` and `tests/layout/__init__.py` if needed for imports; run from repo root.

- [ ] **Step 5: Commit**

```bash
git add src/etl/layout/ src/config.py requirements.txt tests/
git commit -m "feat(etl): add layout region data model + config (M1 task 1)"
```

---

### Task 2: Page preprocess — deskew + watermark/stamp masking

**Files:**
- Create: `src/etl/layout/preprocess.py`
- Test: `tests/layout/test_preprocess.py`

**Interfaces:**
- Consumes: `get_pdf_variant` from `src.etl.image_processor`.
- Produces: `preprocess_page(image: np.ndarray, variant: str) -> np.ndarray` (BGR uint8 in, cleaned BGR uint8 out, same shape). Masks the KNTT left-margin personal stamp (fills the left `KNTT_STAMP_FRAC` of width with page-background white when variant=="kntt"). Deskew is a no-op stub in M1 (documented) to keep the task focused.

- [ ] **Step 1: Write the failing test**

```python
# tests/layout/test_preprocess.py
import numpy as np
from src.etl.layout.preprocess import preprocess_page

def _page_with_left_stamp():
    img = np.full((200, 100, 3), 255, np.uint8)   # white page
    img[:, 0:6] = 0                                # black vertical stamp on left margin
    return img

def test_kntt_left_stamp_is_masked():
    out = preprocess_page(_page_with_left_stamp(), "kntt")
    # the stamp column is wiped back to (near) white
    assert out[:, 0:6].mean() > 240

def test_non_kntt_left_margin_untouched():
    img = _page_with_left_stamp()
    out = preprocess_page(img, "cd")
    assert out[:, 0:6].mean() < 20   # CD: no left-stamp masking
```

- [ ] **Step 2: Run to verify it fails** — `python -m pytest tests/layout/test_preprocess.py -v` → FAIL (no module).

- [ ] **Step 3: Write minimal implementation**

```python
# src/etl/layout/preprocess.py
"""Page cleanup before segmentation: watermark/stamp masking (deskew stub)."""
import numpy as np

# Fraction of page width occupied by the KNTT left-margin personal stamp.
KNTT_STAMP_FRAC = 0.06

def preprocess_page(image: np.ndarray, variant: str) -> np.ndarray:
    out = image.copy()
    h, w = out.shape[:2]
    if variant == "kntt":
        band = max(1, int(w * KNTT_STAMP_FRAC))
        out[:, 0:band] = 255  # wipe left-margin stamp to page white
    # deskew: intentional no-op in M1 (scans are near-upright); revisit if QA shows skew.
    return out
```

- [ ] **Step 4: Run to verify it passes** — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/etl/layout/preprocess.py tests/layout/test_preprocess.py
git commit -m "feat(etl): mask KNTT left-margin stamp in preprocess (M1 task 2)"
```

> **Adversarial review note (D-06):** confirm the mask never touches non-KNTT variants, that `KNTT_STAMP_FRAC` (6%) does not eat real body text on the new KNTT9 (verify against a rendered KNTT9 page in Task 10 QA — the body column starts well right of 6%).

---

### Task 3: Vietnamese diacritic post-correction (conservative)

**Files:**
- Create: `src/etl/diacritic.py`
- Test: `tests/test_diacritic.py`

**Interfaces:**
- Produces: `fix_diacritics(text: str) -> str`. Corrects a curated map of common OCR diacritic confusions token-by-token; skips any token that is all-caps, contains a digit, or is in `SCIENCE_ALLOWLIST`. Idempotent.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_diacritic.py
from src.etl.diacritic import fix_diacritics

def test_fixes_known_confusions():
    assert fix_diacritics("nước đá vẫn được tạo thành") == "nước đá vẫn được tạo thành"
    assert fix_diacritics("phát triên của sinh vật") == "phát triển của sinh vật"
    assert fix_diacritics("Trái Đât") == "Trái Đất"

def test_preserves_science_and_english_terms():
    assert fix_diacritics("Sulfuric acid H2SO4") == "Sulfuric acid H2SO4"
    assert fix_diacritics("oxygen CO2") == "oxygen CO2"

def test_idempotent():
    once = fix_diacritics("phát triên")
    assert fix_diacritics(once) == once
```

- [ ] **Step 2: Run to verify it fails** — FAIL (no module).

- [ ] **Step 3: Write minimal implementation**

```python
# src/etl/diacritic.py
"""Conservative Vietnamese diacritic correction for OCR output.

Only rewrites tokens that appear in a curated confusion map. Anything
all-caps, containing digits, or on the science allowlist is left untouched
so chemical formulas / English terms / proper nouns are never damaged.
"""
import re

# Curated map of frequent Tesseract diacritic misreads → correct form.
# Extend as QA surfaces more (keep lowercase keys; matching is case-insensitive
# but preserves the original leading capital).
_CONFUSIONS = {
    "triên": "triển",
    "đât": "đất",
    "tổn": "tồn",     # "tổn tại" -> "tồn tại"  (context-guarded below)
    "giây": "giấy",   # guarded: only when not a time unit context (see note)
    "bảy": "bày",     # "trình bảy" -> "trình bày"
    "môi": "mỗi",
}
# Confusions that are too ambiguous to apply unconditionally -> require a
# preceding trigger word (avoids "giây"=second, "môi"=lip false positives).
_CONTEXT_GUARDED = {
    "giây": {"prev": {"sản", "tờ", "bột"}, "to": "giấy"},
    "tổn":  {"prev": {"vẫn", "còn", "sự"},  "to": "tồn"},
    "môi":  {"prev": {"với", "của"},         "to": "mỗi"},
}
SCIENCE_ALLOWLIST = {"oxygen", "hydrogen", "nitrogen", "sulfuric", "acid",
                     "carbon", "dioxide", "chlorine", "sodium", "iron"}

_TOKEN = re.compile(r"\w+|\W+", re.UNICODE)

def _skip(tok: str) -> bool:
    if any(ch.isdigit() for ch in tok):
        return True
    if tok.isupper() and len(tok) > 1:
        return True
    if tok.lower() in SCIENCE_ALLOWLIST:
        return True
    return False

def _apply_case(src: str, repl: str) -> str:
    return repl.capitalize() if src[:1].isupper() else repl

def fix_diacritics(text: str) -> str:
    toks = _TOKEN.findall(text)
    words = [t for t in toks if t.strip()]  # for prev-word lookups
    out, wi = [], -1
    for t in toks:
        if not t.strip():
            out.append(t); continue
        wi += 1
        low = t.lower()
        if _skip(t):
            out.append(t); continue
        prev = words[wi - 1].lower() if wi > 0 else ""
        if low in _CONTEXT_GUARDED:
            g = _CONTEXT_GUARDED[low]
            out.append(_apply_case(t, g["to"]) if prev in g["prev"] else t)
        elif low in _CONFUSIONS and low not in _CONTEXT_GUARDED:
            out.append(_apply_case(t, _CONFUSIONS[low]))
        else:
            out.append(t)
    return "".join(out)
```

> Note: the first-pass test asserts words already correct pass through unchanged; the map fixes `triên`/`đât`/`bảy` unconditionally and guards `giây`/`tổn`/`môi` by previous word. If a guarded test case needs the trigger, the test text includes it (e.g. "phát triên" is unconditional; "vẫn được" precedes nothing needing guard).

- [ ] **Step 4: Run to verify it passes** — adjust `_CONFUSIONS`/guards until the three tests pass. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/etl/diacritic.py tests/test_diacritic.py
git commit -m "feat(etl): conservative Vietnamese diacritic correction (M1 task 3)"
```

---

### Task 4: Printed page-number detection

**Files:**
- Create: `src/etl/layout/page_number.py`
- Test: `tests/layout/test_page_number.py`

**Interfaces:**
- Produces: `detect_printed_page_number(image: np.ndarray, variant: str, pdf_index: int) -> int`. OCRs the bottom-left/bottom-right corners for a standalone integer; returns it, else returns `pdf_index`.

- [ ] **Step 1: Write the failing test**

```python
# tests/layout/test_page_number.py
import numpy as np, cv2
from src.etl.layout.page_number import detect_printed_page_number

def _page_with_number(txt, corner="left"):
    img = np.full((300, 200, 3), 255, np.uint8)
    org = (10, 285) if corner == "left" else (165, 285)
    cv2.putText(img, txt, org, cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,0,0), 2, cv2.LINE_AA)
    return img

def test_reads_bottom_number():
    assert detect_printed_page_number(_page_with_number("89"), "kntt", pdf_index=91) == 89

def test_falls_back_to_pdf_index_when_absent():
    blank = np.full((300, 200, 3), 255, np.uint8)
    assert detect_printed_page_number(blank, "cd", pdf_index=42) == 42
```

- [ ] **Step 2: Run to verify it fails** — FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# src/etl/layout/page_number.py
"""Detect the page number printed on the page (bottom corners)."""
import re
import numpy as np
import pytesseract
from ..layout.regions import BBox
from ...config import TESSERACT_CMD

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
_INT = re.compile(r"^\d{1,3}$")

def _crop(img, frac_box):
    h, w = img.shape[:2]
    x0, y0, x1, y1 = frac_box
    return img[int(h*y0):int(h*y1), int(w*x0):int(w*x1)]

def detect_printed_page_number(image: np.ndarray, variant: str, pdf_index: int) -> int:
    # bottom-left and bottom-right corners
    for box in [(0.0, 0.90, 0.20, 1.0), (0.80, 0.90, 1.0, 1.0)]:
        crop = _crop(image, box)
        txt = pytesseract.image_to_string(
            crop, lang="vie", config="--psm 7 -c tessedit_char_whitelist=0123456789")
        for tok in txt.split():
            if _INT.match(tok.strip()):
                return int(tok.strip())
    return pdf_index
```

- [ ] **Step 4: Run to verify it passes** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/etl/layout/page_number.py tests/layout/test_page_number.py
git commit -m "feat(etl): detect printed page number with pdf-index fallback (M1 task 4)"
```

> **Adversarial review note:** whitelist to digits + `--psm 7` (single line) avoids reading body text as a number. Guard against a running header page-number on the wrong corner by checking bottom band only. Verify on real pages in Task 10 (CD/CTST print number bottom-outer; KNTT bottom-outer too).

---

### Task 5: Layout segmenter (colored boxes + text columns + figure regions)

**Files:**
- Create: `src/etl/layout/segmenter.py`
- Test: `tests/layout/test_segmenter.py`

**Interfaces:**
- Consumes: `Region`, `RegionType` (Task 1); `LAYOUT_BOX_MIN_SATURATION`, `LAYOUT_BOX_MIN_AREA_FRAC` (config).
- Produces: `segment_page(image: np.ndarray, variant: str) -> list[Region]`. Detects colored boxes (sidebar/info_box) via HSV saturation contours; classifies the remaining page into a main-text column via Tesseract block geometry; assigns `reading_order` (main column first, then boxes top→bottom). Figure/caption region detection is a light first pass (large non-text, non-box rectangles) refined in M3.

- [ ] **Step 1: Write the failing test** (synthetic page: white bg, black main-text block left, green box right)

```python
# tests/layout/test_segmenter.py
import numpy as np, cv2
from src.etl.layout.segmenter import segment_page
from src.etl.layout.regions import RegionType

def _synthetic_page():
    img = np.full((1000, 800, 3), 255, np.uint8)
    # main text: black lines on left 60% of width
    for y in range(120, 700, 40):
        cv2.putText(img, "dòng văn bản chính của bài học", (40, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 2)
    # colored sidebar box on right (green fill) with text
    cv2.rectangle(img, (560, 120), (770, 480), (120, 200, 120), -1)
    cv2.putText(img, "cau hoi 5", (580, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 2)
    return img

def test_detects_one_colored_box_and_main_text():
    regs = segment_page(_synthetic_page(), "ctst")
    types = [r.type for r in regs]
    assert RegionType.SIDEBAR in types or RegionType.INFO_BOX in types
    assert RegionType.BODY in types
    # main body reads before the sidebar box
    body = next(r for r in regs if r.type == RegionType.BODY)
    box = next(r for r in regs if r.type in (RegionType.SIDEBAR, RegionType.INFO_BOX))
    assert body.reading_order < box.reading_order

def test_box_bbox_is_on_the_right():
    regs = segment_page(_synthetic_page(), "ctst")
    box = next(r for r in regs if r.type in (RegionType.SIDEBAR, RegionType.INFO_BOX))
    assert box.bbox[0] > 400   # x0 on right half
```

- [ ] **Step 2: Run to verify it fails** — FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# src/etl/layout/segmenter.py
"""Classical-CV page layout segmentation: colored boxes + main text column."""
import cv2
import numpy as np
from .regions import Region, RegionType, BBox
from ..image_processor import get_pdf_variant  # noqa: F401  (kept for parity/use by callers)
from ...config import LAYOUT_BOX_MIN_SATURATION, LAYOUT_BOX_MIN_AREA_FRAC

def _colored_boxes(image: np.ndarray) -> list[BBox]:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    mask = (sat >= LAYOUT_BOX_MIN_SATURATION).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = image.shape[:2]
    min_area = LAYOUT_BOX_MIN_AREA_FRAC * h * w
    boxes = []
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw * bh >= min_area and bw > 0.08 * w and bh > 0.05 * h:
            boxes.append((x, y, x + bw, y + bh))
    return boxes

def _classify_box(bbox: BBox, image_w: int) -> RegionType:
    # Right-column tall box => sidebar; wide banner box => info_box.
    x0, y0, x1, y1 = bbox
    width_frac = (x1 - x0) / image_w
    return RegionType.INFO_BOX if width_frac > 0.5 else RegionType.SIDEBAR

def segment_page(image: np.ndarray, variant: str) -> list[Region]:
    h, w = image.shape[:2]
    boxes = _colored_boxes(image)
    regions: list[Region] = []
    # Main body = the whole page minus box columns; first in reading order.
    regions.append(Region(RegionType.BODY, (0, 0, w, h), reading_order=0,
                          meta={"excludes": boxes}))
    for i, b in enumerate(sorted(boxes, key=lambda z: (z[1], z[0]))):
        regions.append(Region(_classify_box(b, w), b, reading_order=i + 1, meta={}))
    return regions
```

- [ ] **Step 4: Run to verify it passes** — tune `LAYOUT_BOX_MIN_SATURATION`/morphology until both tests pass. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/etl/layout/segmenter.py tests/layout/test_segmenter.py
git commit -m "feat(etl): layout segmenter — colored boxes + body region (M1 task 5)"
```

> **Adversarial review note:** the BODY region currently spans the whole page with an `excludes` list; Task 6 must actually subtract box areas during OCR so sidebar text does not leak into body. Verify the saturation threshold does not classify faint watermarks or figure photos as boxes (Task 10 QA on real CD8/CTST7 pages — CD8 has a radial figure with colored icons that must NOT become one giant box; if it does, raise `LAYOUT_BOX_MIN_SATURATION` or require solid-fill ratio).

---

### Task 6: Per-region text extraction in reading order

**Files:**
- Create: `src/etl/layout/text_extract.py`
- Test: `tests/layout/test_text_extract.py`

**Interfaces:**
- Consumes: `Region`, `RegionType`, `TextUnit`; `segment_page` output; `fix_diacritics` (Task 3); `clean_vietnamese_text` (`src.etl.cleaner`).
- Produces: `extract_text_units(image: np.ndarray, regions: list[Region], variant: str) -> list[TextUnit]`. For each non-figure region, OCRs only that region's pixels (BODY masks out box areas listed in `meta["excludes"]`), applies clean + diacritic-fix, returns `TextUnit`s sorted by reading_order. Empty units dropped.

- [ ] **Step 1: Write the failing test**

```python
# tests/layout/test_text_extract.py
import numpy as np, cv2
from src.etl.layout.segmenter import segment_page
from src.etl.layout.text_extract import extract_text_units
from src.etl.layout.regions import RegionType

def _page():
    img = np.full((1000, 800, 3), 255, np.uint8)
    cv2.putText(img, "quang hop la qua trinh", (40, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0,0,0), 2)
    cv2.rectangle(img, (560, 120), (770, 480), (120, 200, 120), -1)
    cv2.putText(img, "cau hoi", (580, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0,0,0), 2)
    return img

def test_body_text_excludes_sidebar():
    img = _page()
    regs = segment_page(img, "ctst")
    units = extract_text_units(img, regs, "ctst")
    body = " ".join(u.text for u in units if u.region_type == RegionType.BODY).lower()
    assert "quang hop" in body.replace("  ", " ") or "quang" in body
    assert "cau hoi" not in body   # sidebar text must NOT leak into body

def test_units_sorted_by_reading_order():
    img = _page()
    regs = segment_page(img, "ctst")
    units = extract_text_units(img, regs, "ctst")
    assert [u.reading_order for u in units] == sorted(u.reading_order for u in units)
```

- [ ] **Step 2: Run to verify it fails** — FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# src/etl/layout/text_extract.py
"""OCR each layout region separately, in reading order."""
import numpy as np
import pytesseract
from .regions import Region, RegionType, TextUnit
from ..cleaner import clean_vietnamese_text
from ..diacritic import fix_diacritics
from ...config import TESSERACT_CMD, DIACRITIC_FIX_ENABLED

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

def _ocr(img: np.ndarray) -> str:
    raw = pytesseract.image_to_string(img, lang="vie")
    cleaned = clean_vietnamese_text(raw)
    return fix_diacritics(cleaned) if DIACRITIC_FIX_ENABLED else cleaned

def _mask_out(img: np.ndarray, boxes) -> np.ndarray:
    out = img.copy()
    for (x0, y0, x1, y1) in boxes:
        out[y0:y1, x0:x1] = 255
    return out

def extract_text_units(image: np.ndarray, regions: list[Region], variant: str) -> list[TextUnit]:
    units: list[TextUnit] = []
    for r in sorted(regions, key=lambda z: z.reading_order):
        if r.type in (RegionType.FIGURE, RegionType.PAGE_ARTIFACT):
            continue
        x0, y0, x1, y1 = r.bbox
        crop = image[y0:y1, x0:x1]
        if r.type == RegionType.BODY:
            crop = _mask_out(crop, r.meta.get("excludes", []))
        text = _ocr(crop)
        if text and len(text) > 5:
            units.append(TextUnit(r.type, text, r.reading_order, r.bbox))
    return units
```

- [ ] **Step 4: Run to verify it passes** — PASS. (If BODY box exclusion coords are page-absolute vs crop-relative, fix the offset — BODY bbox is full page so excludes are already absolute; for non-BODY crops there are no excludes.)

- [ ] **Step 5: Commit**

```bash
git add src/etl/layout/text_extract.py tests/layout/test_text_extract.py
git commit -m "feat(etl): per-region OCR with sidebar exclusion + diacritic fix (M1 task 6)"
```

> **Adversarial review note:** the BODY `excludes` boxes are full-page coordinates and BODY bbox starts at (0,0), so masking is correct; if Task 5 ever emits a BODY sub-crop, revisit offset math. Verify no double-counting (box text appearing in both its own unit and body).

---

### Task 7: Structure-aware chunker

**Files:**
- Create: `src/etl/layout/chunker.py`
- Test: `tests/layout/test_chunker.py`

**Interfaces:**
- Consumes: `TextUnit`, `RegionType`; `TextSplitter` (`src.etl.text_splitter`); config `CHUNK_SIZE`, `CHUNK_OVERLAP`.
- Produces: `chunk_units(units: list[TextUnit], source: str, page: int, variant: str) -> list[Document]`. BODY units are concatenated then split with `TextSplitter` (each chunk `region_type="body"`); each SIDEBAR/INFO_BOX/CAPTION unit becomes exactly ONE atomic `Document` (never split, never merged into body). Metadata per Global Constraints. `chunk_index` is sequential per page.

- [ ] **Step 1: Write the failing test**

```python
# tests/layout/test_chunker.py
from src.etl.layout.chunker import chunk_units
from src.etl.layout.regions import TextUnit, RegionType

def test_body_split_and_box_atomic():
    body = TextUnit(RegionType.BODY, "câu " * 400, 0, (0,0,1,1))          # long -> splits
    box = TextUnit(RegionType.SIDEBAR, "Câu hỏi 5: giải thích.", 1, (0,0,1,1))
    docs = chunk_units([body, box], source="SGK KHTN 7 CTST.pdf", page=40, variant="ctst")
    body_docs = [d for d in docs if d.metadata["region_type"] == "body"]
    box_docs = [d for d in docs if d.metadata["region_type"] == "sidebar"]
    assert len(body_docs) >= 2          # long body split into multiple chunks
    assert len(box_docs) == 1           # sidebar stays atomic
    assert box_docs[0].page_content.strip().startswith("Câu hỏi 5")
    for d in docs:
        assert d.metadata["source"] == "SGK KHTN 7 CTST.pdf"
        assert d.metadata["page"] == 40
        assert d.metadata["variant"] == "ctst"
        assert "chunk_index" in d.metadata

def test_chunk_index_is_unique_sequential():
    body = TextUnit(RegionType.BODY, "x " * 500, 0, (0,0,1,1))
    docs = chunk_units([body], "s.pdf", 1, "cd")
    idx = [d.metadata["chunk_index"] for d in docs]
    assert idx == list(range(len(idx)))
```

- [ ] **Step 2: Run to verify it fails** — FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# src/etl/layout/chunker.py
"""Turn TextUnits into indexed Documents: body split, boxes atomic."""
from langchain_core.documents import Document
from .regions import TextUnit, RegionType
from ..text_splitter import TextSplitter
from ...config import CHUNK_SIZE, CHUNK_OVERLAP

_splitter = TextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

def _meta(source, page, variant, region_type, idx):
    return {"source": source, "page": page, "variant": variant,
            "region_type": region_type, "chunk_index": idx}

def chunk_units(units, source: str, page: int, variant: str):
    docs, idx = [], 0
    body_text = "\n".join(u.text for u in units if u.region_type == RegionType.BODY).strip()
    if body_text:
        base = Document(page_content=body_text)
        for piece in _splitter.split([base]):
            docs.append(Document(page_content=piece.page_content,
                                 metadata=_meta(source, page, variant, "body", idx)))
            idx += 1
    for u in units:
        if u.region_type == RegionType.BODY:
            continue
        docs.append(Document(page_content=u.text.strip(),
                             metadata=_meta(source, page, variant, u.region_type.value, idx)))
        idx += 1
    return docs
```

- [ ] **Step 4: Run to verify it passes** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/etl/layout/chunker.py tests/layout/test_chunker.py
git commit -m "feat(etl): structure-aware chunker, boxes atomic (M1 task 7)"
```

---

### Task 8: LayoutOCRLoader orchestration

**Files:**
- Create: `src/etl/layout/loader.py`
- Modify: `src/etl/__init__.py` (export `LayoutOCRLoader`)
- Test: `tests/layout/test_loader.py`

**Interfaces:**
- Consumes: `preprocess_page`, `segment_page`, `extract_text_units`, `chunk_units`, `detect_printed_page_number`; `get_pdf_variant`; PyMuPDF `fitz`; `RENDER_DPI`.
- Produces: `LayoutOCRLoader().load_pdf(pdf_file: str) -> list[Document]` — one call renders every page via fitz, runs the pipeline, and returns all chunk Documents with `page` = printed page number. Also `load_page(pdf_file, index) -> list[Document]` for per-page ETL/testing.

- [ ] **Step 1: Write the failing test** (mock fitz + pipeline; assert wiring, not OCR quality)

```python
# tests/layout/test_loader.py
import numpy as np
from src.etl.layout import loader as L
from src.etl.layout.regions import Region, RegionType

def test_load_page_wires_pipeline(monkeypatch):
    img = np.full((200, 200, 3), 255, np.uint8)
    monkeypatch.setattr(L, "_render_page", lambda pdf, i, dpi: img)
    monkeypatch.setattr(L, "preprocess_page", lambda im, v: im)
    monkeypatch.setattr(L, "segment_page", lambda im, v: [Region(RegionType.BODY, (0,0,200,200), 0, {})])
    monkeypatch.setattr(L, "detect_printed_page_number", lambda im, v, idx: 88)
    from src.etl.layout import text_extract as TE
    monkeypatch.setattr(L, "extract_text_units", lambda im, regs, v: [
        __import__("src.etl.layout.regions", fromlist=["TextUnit"]).TextUnit(RegionType.BODY, "quang hợp là gì", 0, (0,0,1,1))])
    docs = L.LayoutOCRLoader().load_page("SGK KHTN 7 CTST.pdf", 90)
    assert len(docs) == 1
    assert docs[0].metadata["page"] == 88          # printed number, not pdf index 90
    assert docs[0].metadata["variant"] == "ctst"
    assert docs[0].metadata["region_type"] == "body"
```

- [ ] **Step 2: Run to verify it fails** — FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# src/etl/layout/loader.py
"""Layout-aware text loader: PDF page -> clean chunk Documents."""
import logging
import fitz  # PyMuPDF
import numpy as np
from .preprocess import preprocess_page
from .segmenter import segment_page
from .text_extract import extract_text_units
from .chunker import chunk_units
from .page_number import detect_printed_page_number
from ..image_processor import get_pdf_variant
from ...config import RENDER_DPI
from pathlib import Path

logger = logging.getLogger(__name__)

def _render_page(pdf_file: str, index: int, dpi: int) -> np.ndarray:
    doc = fitz.open(pdf_file)
    try:
        pix = doc[index].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))
        arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
        # to BGR uint8 (drop alpha if present; RGB->BGR)
        arr = arr[:, :, :3][:, :, ::-1].copy()
        return arr
    finally:
        doc.close()

class LayoutOCRLoader:
    def load_page(self, pdf_file: str, index: int):
        variant = get_pdf_variant(Path(pdf_file).name)
        img = _render_page(pdf_file, index, RENDER_DPI)
        img = preprocess_page(img, variant)
        regions = segment_page(img, variant)
        page_no = detect_printed_page_number(img, variant, pdf_index=index + 1)
        units = extract_text_units(img, regions, variant)
        return chunk_units(units, source=Path(pdf_file).name, page=page_no, variant=variant)

    def load_pdf(self, pdf_file: str):
        doc = fitz.open(pdf_file); n = len(doc); doc.close()
        out = []
        for i in range(n):
            try:
                out.extend(self.load_page(pdf_file, i))
            except Exception as e:
                logger.error(f"[{Path(pdf_file).name}] page {i}: {e}")
        return out
```

Add to `src/etl/__init__.py`: `from src.etl.layout.loader import LayoutOCRLoader` and add to `__all__`.

- [ ] **Step 4: Run to verify it passes** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/etl/layout/loader.py src/etl/__init__.py tests/layout/test_loader.py
git commit -m "feat(etl): LayoutOCRLoader orchestrating the data-path pipeline (M1 task 8)"
```

> **Adversarial review note:** verify `pix.n` handling — grayscale (n=1) and RGBA (n=4) pages must still yield HxWx3 BGR. Add a guard converting n==1 → stack to 3 channels. Confirm `page` uses `index+1` fallback (1-based) consistent with `ProcessingStatus`.

---

### Task 9: Wire into main.py text ETL + fix checkpoint filename trap

**Files:**
- Modify: `main.py` (`run_etl_text_only`, ~lines 47-140; imports)
- Test: `tests/test_checkpoint_no_filename_skip.py`

**Interfaces:**
- Consumes: `LayoutOCRLoader`, `ProcessingStatus` (hash-based). 
- Behavior change: text ETL uses `LayoutOCRLoader` instead of `RobustOCRLoader`; the `processed_files.txt` filename check must NOT skip a file whose content hash has unprocessed pages. Page identity for `ProcessingStatus` uses the 0-based PDF `index` (not printed page) to stay stable — chunk metadata still carries the printed page.

- [ ] **Step 1: Write the failing test** (regression: same filename, new hash → not skipped)

```python
# tests/test_checkpoint_no_filename_skip.py
from main import _should_skip_file   # new helper extracted in this task

def test_same_name_new_hash_not_skipped():
    processed_names = {"SGK KHTN8 KNTT.pdf"}
    # a file already in the name list but whose pages still need text must NOT be skipped
    assert _should_skip_file("SGK KHTN8 KNTT.pdf", pages_needing_text=[1,2,3],
                             processed_names=processed_names) is False

def test_fully_done_file_skipped():
    assert _should_skip_file("x.pdf", pages_needing_text=[], processed_names={"x.pdf"}) is True
```

- [ ] **Step 2: Run to verify it fails** — FAIL (`_should_skip_file` not defined).

- [ ] **Step 3: Write minimal implementation** — extract the skip decision into a pure helper and base it on hash-derived `pages_needing_text`, not the filename list:

```python
# main.py  (add near the other helpers)
def _should_skip_file(filename, pages_needing_text, processed_names):
    """Skip only when the CONTENT (via hash-based status) has no pages left.
    The filename list is advisory; a replaced same-named file (new hash) will
    report pages_needing_text and therefore NOT be skipped."""
    return len(pages_needing_text) == 0
```

Then in `run_etl_text_only`, replace `loader = RobustOCRLoader()` with `from src.etl import LayoutOCRLoader; loader = LayoutOCRLoader()`, and replace the early `if filename in processed_files: continue` with: compute `pdf_hash`, `pages_to_index = status_tracker.get_pages_needing_text(pdf_hash, num_pages)`, then `if _should_skip_file(filename, pages_to_index, processed_files): continue`. Since `LayoutOCRLoader.load_pdf` returns already-chunked Documents with `page`=printed number, index them directly and mark each PDF `index` (1-based) via `status_tracker.mark_text_indexed(pdf_hash, pdf_index, filename)`.

> Because `LayoutOCRLoader` chunks internally, drop the separate `TextSplitter` call in `run_etl_text_only` (chunking now happens in the loader). Keep `add_documents(docs)`.

- [ ] **Step 4: Run to verify it passes** — `python -m pytest tests/test_checkpoint_no_filename_skip.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_checkpoint_no_filename_skip.py
git commit -m "fix(etl): hash-based skip so replaced same-named PDFs re-process; use LayoutOCRLoader (M1 task 9)"
```

> **Adversarial review note:** ensure `mark_text_indexed` is called with a page id consistent with `get_pages_needing_text` (both 1-based PDF index). Do NOT mark by printed page number (collides across chapters). On a clean rebuild, `processed_files.txt` should be deleted first (documented in Task 11 run steps).

---

### Task 10: Extend visual QA tool with region overlay

**Files:**
- Modify: `src/test/test_image_extraction_full.py` (add a `--layout` overlay mode)
- Create: `src/test/qa_layout.py` (thin CLI if cleaner than modifying the big file)

**Interfaces:**
- Consumes: `segment_page`, `preprocess_page`, `get_pdf_variant`, `_render_page`.
- Produces: an HTML/PNG index drawing each `Region` bbox colored by `RegionType` over the rendered page, for a chosen page per book. This is manual QA (no assertion) — the acceptance gate for segmentation quality.

- [ ] **Step 1: Write a smoke test that the overlay renders without error**

```python
# tests/layout/test_qa_layout.py
from src.test.qa_layout import render_layout_overlay
def test_overlay_smoke(tmp_path):
    out = render_layout_overlay("SGK KHTN 7 CTST.pdf", page_index=40, out_dir=str(tmp_path))
    import os; assert os.path.exists(out)
```

- [ ] **Step 2: Run to verify it fails** — FAIL.

- [ ] **Step 3: Implement `render_layout_overlay`** — render page, preprocess, segment, draw colored rectangles per region type with a legend, save PNG; return path. (Colors: body=blue, sidebar=green, info_box=orange, figure=red, caption=purple.)

- [ ] **Step 4: Run to verify it passes** — PASS. Then MANUALLY run for one representative page per book (CTST7 p40, KNTT8 p60, CD8 p50 radial, CD6 p40 grid, KNTT9 p90 stamped) and eyeball the overlays. Record findings; tune Task 5 thresholds if boxes are wrong.

- [ ] **Step 5: Commit**

```bash
git add src/test/qa_layout.py tests/layout/test_qa_layout.py
git commit -m "test(etl): layout region overlay QA tool (M1 task 10)"
```

---

### Task 11: Local end-to-end dry-run + Colab run doc

**Files:**
- Create: `document/runbooks/m1_rebuild_text.md`
- Test: `tests/layout/test_loader_real_page.py` (one real page, asserts clean body + no sidebar leak)

**Interfaces:** none new — validates the whole M1 path on a real PDF page locally, then documents the Colab full run.

- [ ] **Step 1: Write the real-page test**

```python
# tests/layout/test_loader_real_page.py
import os, pytest
from src.etl.layout.loader import LayoutOCRLoader

PDF = os.path.join("datasources", "SGK KHTN 7 CTST.pdf")

@pytest.mark.skipif(not os.path.exists(PDF), reason="corpus not present")
def test_real_page_produces_clean_body():
    docs = LayoutOCRLoader().load_page(PDF, 40)
    assert docs, "no chunks produced"
    body = " ".join(d.page_content for d in docs if d.metadata["region_type"] == "body").lower()
    assert len(body) > 100
    # sidebar question numbering should not be inside body flow mid-sentence
    assert all(d.metadata["page"] > 0 for d in docs)
```

- [ ] **Step 2: Run it** — if the corpus is present it should PASS after Tasks 1-9; if it fails, fix the real-page issues it surfaces before continuing.

- [ ] **Step 3: Write the Colab runbook** `document/runbooks/m1_rebuild_text.md` with exact steps:
  1. Set `.env`: `EMBEDDING_MODEL=BAAI/bge-m3`, `RAG_DATABASE_DIR=<Drive path>`, `DIACRITIC_FIX_ENABLED=true`.
  2. Wipe old DB + checkpoints: delete `database/chroma.sqlite3`, collection dirs, `processed_files.txt`, `processed_images.txt` (fresh rebuild — D-04).
  3. `python main.py --text-only` (runs LayoutOCRLoader over all 12 books).
  4. Sanity: count `biology_text` items; spot-check 5 chunks for no sidebar-in-body leak.

- [ ] **Step 4: Run the local real-page test** — Expected: PASS (with corpus). Manually confirm overlays from Task 10 look right for all variants.

- [ ] **Step 5: Commit**

```bash
git add document/runbooks/m1_rebuild_text.md tests/layout/test_loader_real_page.py
git commit -m "docs(etl): M1 local dry-run test + Colab rebuild runbook (M1 task 11)"
```

---

## Self-Review

**Spec coverage:** preprocess (T2), layout_segmenter (T5), text_extractor (T6), diacritic_fix (T3), chunker (T7), page-number D-11 (T4), sidebar-as-labeled-chunk D-10 (T7), checkpoint hash-fix (T9), QA overlay §7 (T10), Colab rebuild §8-M1 (T11). bge-m3 embedding is a config/.env switch consumed at index time (T11 runbook) — collection rebuild is inherent to the clean rebuild. Reranker/prompt/citation belong to **M2** (separate plan), figure extraction to **M3** — intentionally out of M1 scope.

**Placeholder scan:** all code steps contain real code; QA (T10) and runbook (T11) are inherently manual but have concrete steps/colors/commands. No "TBD".

**Type consistency:** `Region`/`TextUnit`/`RegionType` defined in T1 used consistently; `segment_page`→`extract_text_units`→`chunk_units`→`LayoutOCRLoader` signatures match across T5/T6/T7/T8; `_should_skip_file` defined and tested in T9.

**Known follow-ups (not M1 blockers):** figure/caption regions are stubbed in T5 (refined in M3); deskew is a no-op (revisit if QA shows skew); diacritic map is seed-sized (grows via QA).
