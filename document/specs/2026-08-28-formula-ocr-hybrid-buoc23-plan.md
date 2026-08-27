# Hybrid Tesseract + MinerU cho công thức Hoá/Lý — Bước 2+3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gọi MinerU thật để đọc lại các dòng bị Tesseract phá chỉ số dưới công
thức Hoá/Lý (`CO,`→`CO₂`), ghép ĐÚNG VỊ TRÍ vào chunk mà không đụng phần văn bản
còn lại, và chuẩn bị chạy được trên Colab (datasource ở Drive, DB ở session, tải
về sau mỗi quyển).

**Architecture:** Giữ nguyên đường OCR chính (`image_to_string`) cho mọi region;
chỉ khi gate `is_formula_suspect` (D-144, đã có) bắt được lỗ hổng ở text đó mới
gọi `image_to_data` MỘT LẦN THÊM (side-computation hiếm khi chạy) để tìm dòng
chứa lỗ hổng, crop, gọi MinerU, rồi ghép TOKEN (không phải cả dòng) vào đúng vị
trí. Hai tham số M2 đang treo (`LAYOUT_BOX_MIN_SATURATION`, `SINGLE_LINE_MAX_H`)
được hiệu chỉnh per-book và gộp cùng một lượt bump `TEXT_EXTRACTION_VERSION`.

**Tech Stack:** Python, pytesseract, `mineru_vl_utils.MinerUClient` (Colab GPU
only), pytest.

**Spec:** `document/specs/2026-08-27-formula-ocr-hybrid-buoc23-design.md` (đọc
trước — plan này lập luận theo đúng thiết kế đó, kể cả phần "Lịch sử sửa" giải
thích vì sao thiết kế KHÔNG đụng đường OCR chính).

## Global Constraints

- KHÔNG bịa: khi MinerU không đọc được token hợp lệ, hoặc không định vị được
  dòng, GIỮ NGUYÊN Tesseract + gắn cờ trạng thái — không đoán, không tự sửa.
- KHÔNG đụng `image_to_string()` cho region không bị gate nghi — 0 thay đổi
  hành vi trên >99% region hiện có.
- Thay thế vào text region phải qua `apply_line_merge_to_region` (so khớp DÒNG
  NGUYÊN VẸN, đúng 1 lần) — không dùng `str.replace()` toàn cục.
- Hai lượt OCR trên cùng một crop (`image_to_string` chính, `image_to_data`
  phụ) PHẢI dùng cùng `--psm` (qua `_psm_for(crop)`).
- Model MinerU load **một lần duy nhất** cho cả tiến trình (singleton).
- Không đoán ngưỡng số (sàn `min_sat`, `SINGLE_LINE_MAX_H` per-book) — phải có
  script đo + quy tắc quyết định rõ ràng, chạy được ngay.
- `TEXT_EXTRACTION_VERSION` chỉ bump MỘT LẦN, gộp cả 3 thay đổi (hybrid formula
  + 2 tham số M2).
- Không chạy ETL 12 quyển thật trong các task này — máy dev không có GPU. Việc
  cuối cùng của plan chỉ là CHUẨN BỊ file để chạy trên Colab.
- Không thêm `RegionType` mới.
- Commit message: thuần, không `Co-Authored-By`.

---

## Task 1: Chuyển `group_lines` sang production, dùng chung với `ocr_bakeoff.py`

**Files:**
- Create: `src/etl/layout/ocr_lines.py`
- Modify: `src/test/ocr_bakeoff.py` (xoá `group_lines` cục bộ, import từ module mới)
- Test: `tests/layout/test_ocr_lines.py`

**Interfaces:**
- Produces: `group_lines(words: Sequence[dict]) -> List[dict]` (mỗi dict:
  `{"text": str, "bbox": (x0,y0,x1,y1), "conf": float|None}`);
  `image_to_lines(crop: np.ndarray, psm: int) -> List[dict]` (gọi
  `pytesseract.image_to_data` rồi `group_lines`, cùng định dạng trả về).

- [ ] **Step 1: Viết test cho `group_lines` (copy nguyên từ
  `tests/test_ocr_bakeoff.py::TestGroupLines`, đổi import)**

```python
# tests/layout/test_ocr_lines.py
# -*- coding: utf-8 -*-
from src.etl.layout.ocr_lines import group_lines


def _word(text, line=0, left=0, top=0, w=20, h=18, block=1, par=1, conf=90):
    return {"text": text, "block_num": block, "par_num": par, "line_num": line,
            "left": left, "top": top, "width": w, "height": h, "conf": conf}


def test_words_of_one_line_become_one_line_with_union_bbox():
    words = [_word("hấp", left=10, top=100, w=40),
             _word("thụ", left=60, top=100, w=40),
             _word("khí", left=110, top=98, w=40, h=22)]

    lines = group_lines(words)

    assert len(lines) == 1
    assert lines[0]["text"] == "hấp thụ khí"
    assert lines[0]["bbox"] == (10, 98, 150, 120)


def test_two_columns_stay_separate_by_block_num():
    left_col = [_word("cột", block=1, line=0, left=0, top=0),
                _word("trái", block=1, line=0, left=40, top=0)]
    right_col = [_word("cột", block=2, line=0, left=500, top=0),
                 _word("phải", block=2, line=0, left=540, top=0)]

    lines = group_lines(left_col + right_col)

    assert len(lines) == 2
    assert {l["text"] for l in lines} == {"cột trái", "cột phải"}


def test_empty_word_text_is_skipped():
    words = [_word("thật", left=0), _word("  ", left=30), _word("sự", left=60)]

    lines = group_lines(words)

    assert lines[0]["text"] == "thật sự"
```

- [ ] **Step 2: Chạy test, xác nhận FAIL vì `src.etl.layout.ocr_lines` chưa tồn tại**

Run: `python -m pytest tests/layout/test_ocr_lines.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'src.etl.layout.ocr_lines'`

- [ ] **Step 3: Viết `ocr_lines.py`, chuyển nguyên logic `group_lines` từ
  `ocr_bakeoff.py` (KHÔNG đổi hành vi), thêm `image_to_lines`**

```python
# -*- coding: utf-8 -*-
"""Gom word-box của Tesseract (`image_to_data`) thành DÒNG — dùng chung giữa
bake-off (`src/test/ocr_bakeoff.py`) và gate hybrid công thức
(`text_extract.py`, D-56 Bước 2/3). Chuyển từ `ocr_bakeoff.py` (nơi trước đây
là code CHỈ để test) sang production vì `text_extract.py` cần gọi thật khi ETL
chạy — một nguồn sự thật duy nhất cho việc gom dòng.

Thiết kế: `document/specs/2026-08-27-formula-ocr-hybrid-buoc23-design.md` §2.
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import pytesseract

from ...config import TESSERACT_CMD

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


def group_lines(words: Sequence[dict]) -> List[dict]:
    """Gom output `image_to_data` của Tesseract thành dòng, giữ bbox hợp.

    Khoá gom là `(block_num, par_num, line_num)`, **không phải `line_num` một
    mình**: Tesseract đánh `line_num` lại từ 0 trong mỗi block, nên gom theo nó
    sẽ dán hai cột của bố cục hai cột (CTST/CD) vào cùng một dòng.
    """
    theo_dong: Dict[Tuple[int, int, int], List[dict]] = {}
    thu_tu: List[Tuple[int, int, int]] = []
    for w in words:
        text = str(w.get("text", "")).strip()
        if not text:
            continue
        key = (int(w.get("block_num", 0)), int(w.get("par_num", 0)),
               int(w.get("line_num", 0)))
        if key not in theo_dong:
            theo_dong[key] = []
            thu_tu.append(key)
        theo_dong[key].append(w)

    out: List[dict] = []
    for key in thu_tu:
        ws = theo_dong[key]
        x0 = min(int(w["left"]) for w in ws)
        y0 = min(int(w["top"]) for w in ws)
        x1 = max(int(w["left"]) + int(w["width"]) for w in ws)
        y1 = max(int(w["top"]) + int(w["height"]) for w in ws)
        confs = [float(w.get("conf", -1)) for w in ws
                 if str(w.get("conf", "-1")) not in ("-1", "")]
        out.append({
            "text": " ".join(str(w["text"]).strip() for w in ws),
            "bbox": (x0, y0, x1, y1),
            "conf": round(sum(confs) / len(confs), 1) if confs else None,
        })
    return out


def image_to_lines(crop, psm: int) -> List[dict]:
    """`group_lines` áp thẳng lên một ảnh crop, cùng `--psm` với lượt OCR chính.

    Dùng cho gate hybrid công thức: chỉ gọi khi region đã bị `is_formula_suspect`
    bắt được ở text chính — KHÔNG gọi cho mọi region (side-computation hiếm).
    """
    data = pytesseract.image_to_data(
        crop, lang="vie", config=f"--psm {psm}",
        output_type=pytesseract.Output.DICT)
    n = len(data["text"])
    words = [{k: data[k][i] for k in
              ("text", "block_num", "par_num", "line_num", "left", "top",
               "width", "height", "conf")} for i in range(n)]
    return group_lines(words)
```

- [ ] **Step 4: Chạy lại test, xác nhận PASS**

Run: `python -m pytest tests/layout/test_ocr_lines.py -v`
Expected: 3 passed

- [ ] **Step 5: Sửa `src/test/ocr_bakeoff.py` — xoá định nghĩa `group_lines` cục
  bộ (dòng có docstring "Gom output `image_to_data`..."), import từ module mới**

Xoá toàn bộ hàm `group_lines` hiện có trong `ocr_bakeoff.py`, thêm vào khối
import ở đầu file (cạnh import `formula_signals`):

```python
from src.etl.layout.ocr_lines import group_lines  # noqa: E402
```

- [ ] **Step 6: Chạy test cũ của `ocr_bakeoff.py`, xác nhận KHÔNG hồi quy**

Run: `python -m pytest tests/test_ocr_bakeoff.py -v`
Expected: 96 passed (như trước khi sửa)

- [ ] **Step 7: Commit**

```bash
git add src/etl/layout/ocr_lines.py src/test/ocr_bakeoff.py tests/layout/test_ocr_lines.py
git commit -m "refactor(etl): chuyen group_lines sang production, dung chung ocr_bakeoff"
```

---

## Task 2: `formula_merge.py` — ghép token, không cần model để test

**Files:**
- Modify: `src/etl/layout/formula_signals.py` (đổi `_TOKEN_HOA`→`TOKEN_HOA`,
  `_TOKEN_LY`→`TOKEN_LY`, public vì `formula_merge.py` cần dùng riêng từng nhóm)
- Create: `src/etl/layout/formula_merge.py`
- Test: `tests/layout/test_formula_merge.py`

**Interfaces:**
- Consumes: `CONG_THUC_HONG`, `CO_DAU_BANG`, `TOKEN_HOA`, `TOKEN_LY` từ
  `src.etl.layout.formula_signals`
- Produces: `MergeOutcome(text: str, status: str, n_holes: int, n_applied: int)`;
  `merge_formula_line(tesseract_line: str, mineru_text: str) -> MergeOutcome`;
  `apply_line_merge_to_region(region_text: str, original_line: str, merged_line: str) -> tuple[str, str]`
  (trả `(text_moi, status)`, `status` ∈ `{"applied", "line_not_located_in_region_text", "line_ambiguous_in_region_text"}`)

- [ ] **Step 1: Đổi `_TOKEN_HOA`/`_TOKEN_LY` thành public trong
  `formula_signals.py`**

Trong `src/etl/layout/formula_signals.py`, đổi tên hai regex (giữ nguyên định
nghĩa, chỉ bỏ dấu gạch dưới đầu) và cập nhật chỗ dùng trong `formula_tokens`:

```python
TOKEN_HOA = re.compile(
    r"\(?[A-Z][A-Za-z]{0,2}\)?(?:[₀-₉]|\d)"
    r"(?:\(?[A-Z][A-Za-z]{0,2}\)?(?:[₀-₉]|\d)?)*")
_KY_HIEU = r"(?<![A-Za-zÀ-ỹ])[A-Za-z0-9][A-Za-z0-9₀-₉·./^]*(?![A-Za-zÀ-ỹ])"
TOKEN_LY = re.compile(
    rf"{_KY_HIEU}(?:\s{_KY_HIEU})?\s*=\s*{_KY_HIEU}(?:\s{_KY_HIEU})?")


def formula_tokens(text: str) -> List[str]:
    ...
    s = " ".join(str(text or "").split())
    out = [m.group(0).strip() for m in TOKEN_LY.finditer(s)]
    da_co = " ".join(out)
    for m in TOKEN_HOA.finditer(s):
        tok = m.group(0).strip()
        if not any(c.isalpha() for c in tok) or tok in da_co:
            continue
        out.append(tok)
    return out
```

(Chỉ đổi tên `_TOKEN_HOA`→`TOKEN_HOA`, `_TOKEN_LY`→`TOKEN_LY` ở định nghĩa VÀ
hai chỗ dùng trong `formula_tokens` — không đổi logic, để không ảnh hưởng số CT
đã khoá ở D-108.)

- [ ] **Step 2: Chạy test cũ, xác nhận KHÔNG hồi quy sau khi đổi tên**

Run: `python -m pytest tests/layout/test_formula_signals.py tests/test_ocr_bakeoff.py -v`
Expected: tất cả PASS như trước (đổi tên không đổi hành vi)

- [ ] **Step 3: Viết test cho `merge_formula_line` (chưa có implementation)**

```python
# tests/layout/test_formula_merge.py
# -*- coding: utf-8 -*-
from src.etl.layout.formula_merge import (
    apply_line_merge_to_region,
    merge_formula_line,
)


class TestMergeFormulaLineChemistry:
    def test_two_broken_subscripts_matched_by_two_mineru_tokens(self):
        tesseract = "hấp thụ khí 0, và thải ra khí (0,"
        mineru = "hấp thụ khí CO₂ và thải ra khí O₂"

        out = merge_formula_line(tesseract, mineru)

        assert out.status == "applied"
        assert out.n_holes == 2
        assert out.n_applied == 2
        assert out.text == "hấp thụ khí CO₂ và thải ra khí O₂"

    def test_count_mismatch_keeps_original_line_untouched(self):
        tesseract = "hấp thụ khí 0, và thải ra khí (0,"  # 2 lỗ hổng
        mineru = "hấp thụ khí CO₂"                          # chỉ 1 token

        out = merge_formula_line(tesseract, mineru)

        assert out.status == "unmatched_count"
        assert out.n_holes == 2
        assert out.n_applied == 0
        assert out.text == tesseract

    def test_empty_mineru_reading_keeps_original(self):
        tesseract = "hấp thụ khí 0, và thải ra khí (0,"

        out = merge_formula_line(tesseract, "")

        assert out.status == "unmatched_count"
        assert out.text == tesseract

    def test_repeated_identical_hole_maps_to_different_correct_tokens(self):
        """Khoá lại bug đã bắt khi phản biện thiết kế: hai lỗ hổng CÙNG chuỗi
        (`0,`) nhưng ứng với hai công thức KHÁC NHAU không được ghép nhầm bằng
        nhau — phải ghép theo VỊ TRÍ, không theo str.replace() toàn cục."""
        tesseract = "hấp thụ khí 0, rồi hấp thụ khí 0,"
        mineru = "hấp thụ khí CO₂ rồi hấp thụ khí CH₄"

        out = merge_formula_line(tesseract, mineru)

        assert out.status == "applied"
        assert out.text == "hấp thụ khí CO₂ rồi hấp thụ khí CH₄"


class TestMergeFormulaLinePhysics:
    def test_broken_physics_equation_matched(self):
        tesseract = "công thức 1 J = 1 Ñm"
        mineru = "công thức 1 J = 1 N·m"

        out = merge_formula_line(tesseract, mineru)

        assert out.status == "applied"
        assert "N·m" in out.text


class TestMergeFormulaLineNotSuspect:
    def test_plain_prose_returns_not_suspect_unchanged(self):
        tesseract = "Tế bào là đơn vị cơ bản của sự sống"

        out = merge_formula_line(tesseract, "bất kỳ gì")

        assert out.status == "not_suspect"
        assert out.n_holes == 0
        assert out.text == tesseract


class TestApplyLineMergeToRegion:
    def test_line_found_exactly_once_is_replaced(self):
        region = "Câu 1.\nhấp thụ khí 0, và thải ra khí (0,\nCâu 2."
        original = "hấp thụ khí 0, và thải ra khí (0,"
        merged = "hấp thụ khí CO₂ và thải ra khí O₂"

        new_text, status = apply_line_merge_to_region(region, original, merged)

        assert status == "applied"
        assert new_text == "Câu 1.\nhấp thụ khí CO₂ và thải ra khí O₂\nCâu 2."

    def test_line_not_found_fails_safe(self):
        region = "Câu 1.\ndòng khác hẳn\nCâu 2."
        original = "hấp thụ khí 0, và thải ra khí (0,"

        new_text, status = apply_line_merge_to_region(region, original, "sửa")

        assert status == "line_not_located_in_region_text"
        assert new_text == region

    def test_line_appearing_twice_fails_safe_no_guessing(self):
        region = "0, đầu đoạn.\nvăn khác.\n0, đầu đoạn."
        original = "0, đầu đoạn."

        new_text, status = apply_line_merge_to_region(region, original, "đã sửa")

        assert status == "line_ambiguous_in_region_text"
        assert new_text == region
```

- [ ] **Step 4: Chạy test, xác nhận FAIL vì `formula_merge.py` chưa tồn tại**

Run: `python -m pytest tests/layout/test_formula_merge.py -v`
Expected: FAIL với `ModuleNotFoundError`

- [ ] **Step 5: Viết `formula_merge.py`**

```python
# -*- coding: utf-8 -*-
"""Ghep ket qua MinerU vao dong Tesseract bi gate nghi cong thuc (D-144, Buoc 3).

Hai ham thuan, khong can model that de test — thiet ke day du:
document/specs/2026-08-27-formula-ocr-hybrid-buoc23-design.md §3, §2.4.

`merge_formula_line`: ghep TOKEN vao MOT DONG, giu nguyen phan tieng Viet con
lai cua Tesseract (MinerU thang cong thuc nhung thua dau tieng Viet, D-108).

`apply_line_merge_to_region`: dan dong da sua tro lai vao text CUA CA REGION.
Hai OCR pass (`image_to_string` cho region, `image_to_data` cho dong) khong
chung offset ky tu, nen ghep bang cach tim DONG NGUYEN VEN lam chuoi con, chi
thay khi khop DUNG 1 LAN.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from .formula_signals import CO_DAU_BANG, CONG_THUC_HONG, TOKEN_HOA, TOKEN_LY


@dataclass
class MergeOutcome:
    text: str
    status: str  # "applied" | "unmatched_count" | "not_suspect"
    n_holes: int
    n_applied: int


def _chem_tokens(text: str) -> List[str]:
    """Token hoa trong `text`, LOAI token da nam trong mot phuong trinh ly.

    Tach rieng khoi `formula_tokens` (dung de CHAM, D-108 da khoa so) vi o day
    can biet CHINH XAC vi tri (span), khong phai chi mot list token.
    """
    ly_spans = [m.span() for m in TOKEN_LY.finditer(text)]
    out = []
    for m in TOKEN_HOA.finditer(text):
        if any(a <= m.start() and m.end() <= b for a, b in ly_spans):
            continue
        tok = m.group(0)
        if any(c.isalpha() for c in tok):
            out.append(tok)
    return out


def merge_formula_line(tesseract_line: str, mineru_text: str) -> MergeOutcome:
    hoa_holes = list(CONG_THUC_HONG.finditer(tesseract_line))
    ly_holes = list(CO_DAU_BANG.finditer(tesseract_line))
    if not hoa_holes and not ly_holes:
        return MergeOutcome(tesseract_line, "not_suspect", 0, 0)

    mineru_text = str(mineru_text or "")
    ly_tokens = [m.group(0) for m in TOKEN_LY.finditer(mineru_text)]
    hoa_tokens = _chem_tokens(mineru_text)

    replacements: List[Tuple[int, int, str]] = []
    n_applied = 0
    if hoa_holes and len(hoa_holes) == len(hoa_tokens):
        for hole, tok in zip(hoa_holes, hoa_tokens):
            replacements.append((hole.start(), hole.end(), tok))
        n_applied += len(hoa_holes)
    if ly_holes and len(ly_holes) == len(ly_tokens):
        for hole, tok in zip(ly_holes, ly_tokens):
            replacements.append((hole.start(), hole.end(), tok))
        n_applied += len(ly_holes)

    n_holes = len(hoa_holes) + len(ly_holes)
    if not replacements:
        return MergeOutcome(tesseract_line, "unmatched_count", n_holes, 0)

    # Ap tu CUOI dong len DAU de offset cac vi tri chua xu ly khong bi lech.
    replacements.sort(key=lambda r: r[0], reverse=True)
    out = tesseract_line
    for start, end, tok in replacements:
        out = out[:start] + tok + out[end:]
    status = "applied" if n_applied == n_holes else "unmatched_count"
    return MergeOutcome(out, status, n_holes, n_applied)


def apply_line_merge_to_region(region_text: str, original_line: str,
                                merged_line: str) -> Tuple[str, str]:
    count = region_text.count(original_line)
    if count == 0:
        return region_text, "line_not_located_in_region_text"
    if count >= 2:
        return region_text, "line_ambiguous_in_region_text"
    idx = region_text.index(original_line)
    new_text = (region_text[:idx] + merged_line +
                region_text[idx + len(original_line):])
    return new_text, "applied"
```

- [ ] **Step 6: Chạy test, xác nhận PASS**

Run: `python -m pytest tests/layout/test_formula_merge.py -v`
Expected: 9 passed

- [ ] **Step 7: Commit**

```bash
git add src/etl/layout/formula_signals.py src/etl/layout/formula_merge.py tests/layout/test_formula_merge.py
git commit -m "feat(etl): them formula_merge.py - ghep token MinerU vao dong bi vo"
```

---

## Task 3: `FormulaMinerUClient` — lazy singleton, injectable

**Files:**
- Create: `src/etl/layout/vlm_loader.py` (chuyển từ `scripts/colab_run_ocr_engines.py`)
- Modify: `scripts/colab_run_ocr_engines.py` (xoá phần đã chuyển, import lại)
- Create: `src/etl/layout/formula_ocr.py`
- Test: `tests/layout/test_formula_ocr.py`

**Interfaces:**
- Produces: `vlm_loader._load_vlm(model_id: str, torch) -> model` (chuyển
  nguyên từ `scripts/colab_run_ocr_engines.py`, D-99/D-101); `FormulaMinerUClient`
  (class), `get_formula_client() -> FormulaMinerUClient` (module-level singleton
  getter, kiểu `get_reranker()` ở `src/rag/reranker.py`),
  method `.read(crop_bgr, kind: str = "text") -> str`

- [ ] **Step 1: Viết test — client KHÔNG được load model thật khi test (dùng
  patch để đếm số lần "load" xảy ra)**

```python
# tests/layout/test_formula_ocr.py
# -*- coding: utf-8 -*-
import numpy as np
import pytest

from src.etl.layout.formula_ocr import FormulaMinerUClient, get_formula_client


def test_client_raises_clear_error_without_mineru_installed(monkeypatch):
    """Máy dev không cài `mineru_vl_utils` — client phải báo lỗi RÕ, không
    silently disable (nguyên tắc 5)."""
    client = FormulaMinerUClient(model_id="fake/model")

    with pytest.raises(Exception) as exc_info:
        client._load()  # noqa: SLF001 — test trực tiếp việc load lười

    assert "mineru" in str(exc_info.value).lower() or \
        isinstance(exc_info.value, ImportError)


def test_read_calls_load_only_once_across_multiple_calls(monkeypatch):
    """Model phải load MỘT LẦN cho cả tiến trình — load lại mỗi lần gọi là bug
    đã bắt khi phản biện thiết kế (D-104: nạp model ~35s/lần)."""
    n_loads = {"count": 0}

    class FakeInnerClient:
        def content_extract(self, image, type="text"):
            return "CO₂"

    def fake_load(self):
        n_loads["count"] += 1
        self._client = FakeInnerClient()

    monkeypatch.setattr(FormulaMinerUClient, "_load", fake_load)
    client = FormulaMinerUClient(model_id="fake/model")
    crop = np.zeros((30, 100, 3), dtype=np.uint8)

    client.read(crop, kind="text")
    client.read(crop, kind="text")
    client.read(crop, kind="text")

    assert n_loads["count"] == 1


def test_get_formula_client_returns_same_instance(monkeypatch):
    import src.etl.layout.formula_ocr as mod
    monkeypatch.setattr(mod, "_singleton", None)

    a = get_formula_client()
    b = get_formula_client()

    assert a is b
```

- [ ] **Step 2: Chạy test, xác nhận FAIL vì module chưa tồn tại**

Run: `python -m pytest tests/layout/test_formula_ocr.py -v`
Expected: FAIL với `ModuleNotFoundError`

- [ ] **Step 3: Chuyển bộ nạp VLM AN TOÀN (tie-weights check, D-99/D-101) từ
  `scripts/colab_run_ocr_engines.py` sang production — KHÔNG viết lại một bản
  nạp ngây thơ**

**Vì sao bắt buộc bước này:** `scripts/colab_run_ocr_engines.py::_load_vlm`
(hàm đã có, đã verify chạy thật trên Colab ở D-99/D-101/D-104) tự động thử
nhiều auto-class, và quan trọng nhất — **kiểm và tự vá `lm_head` chưa được buộc
với embedding** khi `transformers>=5` nạp model họ Qwen2-VL (đúng kiến trúc
MinerU2.5 dùng). Thiếu bước này, model sẽ **sinh token rác thay vì đọc kém**
(đã đo 3 lượt liên tiếp cho 3 chuỗi rác khác nhau dù `do_sample=False`, D-101)
— và bảng kết quả sẽ trông như "MinerU đọc tệ" trong khi thật ra là lỗi nạp
model, đúng cái bẫy D-99→D-102 đã cảnh báo. Một bản `_load()` viết lại từ đầu
(gọi thẳng `AutoModelForImageTextToText.from_pretrained`) sẽ lặp lại đúng lỗi
đó trên Colab thật.

Tạo `src/etl/layout/vlm_loader.py`, CHUYỂN NGUYÊN (không đổi logic) 5 định
nghĩa sau từ `scripts/colab_run_ocr_engines.py` (dòng ~75–229 của file đó —
đọc file thật để copy chính xác, không gõ lại theo trí nhớ):
`_AUTO_CLASSES`, `_tie_da_xay_ra`, `_lm_head_sau`, `_khai_bao_tie`, `_load_vlm`.
Giữ nguyên tên hàm, nguyên docstring tiếng Việt giải thích D-99/D-101 (đó là
tri thức đo được, xoá đi là mất bằng chứng). Đổi TÊN MODULE-LEVEL duy nhất:
đường dẫn import ở đầu các hàm này giữ nguyên (`transformers`, không import gì
từ `scripts/`).

Sau khi tạo `vlm_loader.py`, sửa `scripts/colab_run_ocr_engines.py`: xoá 5
định nghĩa đó khỏi file, thay bằng:

```python
from src.etl.layout.vlm_loader import _load_vlm
```

(Executor: các hàm `_tie_da_xay_ra`/`_lm_head_sau`/`_khai_bao_tie`/`_AUTO_CLASSES`
chỉ được `_load_vlm` gọi nội bộ, `colab_run_ocr_engines.py` chỉ cần import
`_load_vlm` — kiểm lại bằng `grep -n "_tie_da_xay_ra\|_lm_head_sau\|_khai_bao_tie\|_AUTO_CLASSES" scripts/colab_run_ocr_engines.py`
sau khi sửa để chắc không còn tham chiếu treo.)

- [ ] **Step 4: Kiểm `scripts/colab_run_ocr_engines.py` vẫn import được sau khi
  chuyển (không cần GPU để kiểm cú pháp/import)**

Run: `python -c "import ast; ast.parse(open('scripts/colab_run_ocr_engines.py', encoding='utf-8').read())"`
Expected: không lỗi (script vẫn là Python hợp lệ)

Run: `python -c "import sys; sys.path.insert(0, '.'); import scripts.colab_run_ocr_engines"`
Expected: import thành công (các lib `mineru_vl_utils`/`paddleocr` được import
LƯỜI bên trong hàm, không ở top-level, nên máy dev không cài vẫn import được
module — nếu lỗi ImportError ở bước này, đó là dấu hiệu một import bị đẩy lên
top-level nhầm, phải sửa lại).

- [ ] **Step 5: Viết `formula_ocr.py`, dùng `vlm_loader._load_vlm` thay vì tự
  gọi `AutoModelForImageTextToText`**

```python
# -*- coding: utf-8 -*-
"""Client goi MinerU2.5 that qua `content_extract` (D-104) - CHI chay tren
Colab GPU. May dev (CPU, khong co `mineru_vl_utils`) khong tu chay duoc phan
nay; test dung client gia (dependency injection qua `formula_client` param cua
`extract_text_units`).

API DUNG (D-104, KHONG phai `two_step_extract` - da do rong 3/3 o tren crop
mot dong):
    MinerUClient(backend="transformers", model=model, processor=proc)
        .content_extract(PIL.Image, type="text"|"table")

Dung `vlm_loader._load_vlm` (chuyen tu scripts/colab_run_ocr_engines.py, D-99/
D-101) de nap model - KHONG tu goi AutoModelForImageTextToText truc tiep, vi
transformers>=5 nap HONG lm_head cua ho Qwen2-VL neu khong co buoc kiem tie-
weights (da do: sinh token rac thay vi doc kem).

Thiet ke day du: document/specs/2026-08-27-formula-ocr-hybrid-buoc23-design.md §4.
"""
from __future__ import annotations

from ...config import FORMULA_MINERU_MODEL


class FormulaMinerUClient:
    """Load MODEL MOT LAN cho ca tien trinh (nguyen tac 4/D-104: nap ~35s/lan).

    `read()` lazy-load o LAN GOI DAU TIEN, khong phai luc __init__ - de import
    module nay tren may khong co GPU khong fail ngay.
    """

    def __init__(self, model_id: str = FORMULA_MINERU_MODEL):
        self.model_id = model_id
        self._client = None

    def _load(self) -> None:
        import torch
        from mineru_vl_utils import MinerUClient
        from transformers import AutoProcessor

        from .vlm_loader import _load_vlm

        proc = AutoProcessor.from_pretrained(self.model_id, use_fast=True)
        model = _load_vlm(self.model_id, torch)
        model.eval()
        self._client = MinerUClient(backend="transformers", model=model,
                                     processor=proc)

    def read(self, crop_bgr, kind: str = "text") -> str:
        if self._client is None:
            self._load()
        from PIL import Image
        import cv2

        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        loai = "table" if kind == "table" else "text"
        res = self._client.content_extract(image, type=loai)
        return "" if res is None else str(res).strip()


_singleton: "FormulaMinerUClient | None" = None


def get_formula_client() -> FormulaMinerUClient:
    global _singleton
    if _singleton is None:
        _singleton = FormulaMinerUClient()
    return _singleton
```

- [ ] **Step 6: Chạy test, xác nhận PASS**

Run: `python -m pytest tests/layout/test_formula_ocr.py -v`
Expected: 3 passed

Lưu ý: `test_client_raises_clear_error_without_mineru_installed` PASS trên máy
dev vì `mineru_vl_utils` thật sự chưa cài (raise `ImportError` tự nhiên khi
`from mineru_vl_utils import MinerUClient` chạy, TRƯỚC khi tới `_load_vlm`) —
đây là hành vi ĐÚNG cần giữ, không phải test cần mock để pass giả.

- [ ] **Step 7: Commit**

```bash
git add src/etl/layout/formula_ocr.py src/etl/layout/vlm_loader.py scripts/colab_run_ocr_engines.py tests/layout/test_formula_ocr.py
git commit -m "refactor(etl): chuyen bo nap VLM an toan sang production, them FormulaMinerUClient"
```

---

## Task 4: Config + `TextUnit.formula_hybrid_status`

**Files:**
- Modify: `src/config.py` (thêm `FORMULA_HYBRID_ENABLED`, `FORMULA_MINERU_MODEL`)
- Modify: `src/etl/layout/regions.py` (thêm field `formula_hybrid_status`)
- Test: `tests/layout/test_regions.py` (thêm test)

**Interfaces:**
- Produces: `config.FORMULA_HYBRID_ENABLED: bool`, `config.FORMULA_MINERU_MODEL: str`;
  `TextUnit.formula_hybrid_status: List[str]` (mặc định `[]`)

- [ ] **Step 1: Đọc `tests/layout/test_regions.py` hiện có để giữ đúng style**

Run: `python -c "print(open('tests/layout/test_regions.py', encoding='utf-8').read())"` để xem style hiện tại trước khi thêm test.

- [ ] **Step 2: Thêm test cho field mới**

Thêm vào cuối `tests/layout/test_regions.py`:

```python
def test_text_unit_formula_hybrid_status_defaults_to_empty_list():
    unit = TextUnit(RegionType.BODY, "text", 0, (0, 0, 10, 10))

    assert unit.formula_hybrid_status == []
```

(Kiểm import `RegionType`, `TextUnit` đã có sẵn ở đầu file — nếu chưa, thêm
`from src.etl.layout.regions import RegionType, TextUnit`.)

- [ ] **Step 3: Chạy test, xác nhận FAIL (field chưa tồn tại → AttributeError)**

Run: `python -m pytest tests/layout/test_regions.py -v`
Expected: FAIL với `AttributeError: 'TextUnit' object has no attribute 'formula_hybrid_status'`

- [ ] **Step 4: Thêm field vào `TextUnit` (`src/etl/layout/regions.py`)**

```python
@dataclass
class TextUnit:
    region_type: RegionType
    text: str
    reading_order: int
    bbox: BBox
    review_flags: List[str] = field(default_factory=list)
    # Trạng thái ghép hybrid MinerU (D-144 Bước 2/3), TÁCH khỏi `review_flags`
    # vì review_flags đã đo được bật ở 69,3% chunk toàn kho (CLAUDE.md) — nhét
    # thêm cờ mới vào đó làm tín hiệu đã loãng càng loãng hơn.
    formula_hybrid_status: List[str] = field(default_factory=list)
```

- [ ] **Step 5: Chạy test, xác nhận PASS**

Run: `python -m pytest tests/layout/test_regions.py -v`
Expected: PASS toàn bộ (test cũ + test mới)

- [ ] **Step 6: Thêm config vào `src/config.py`**

Thêm cạnh các flag khác (ví dụ cạnh `DIACRITIC_REVIEW_ENABLED`):

```python
# Buoc 2/3 hybrid Tesseract+MinerU cho cong thuc (D-56, D-144). Mac dinh FALSE:
# may dev khong co GPU/mineru_vl_utils. Chi bat tren Colab.
FORMULA_HYBRID_ENABLED = os.getenv(
    "FORMULA_HYBRID_ENABLED", "false").lower() == "true"
FORMULA_MINERU_MODEL = os.getenv(
    "FORMULA_MINERU_MODEL", "opendatalab/MinerU2.5-Pro-2605-1.2B")
```

- [ ] **Step 7: Chạy toàn bộ test layout để chắc không hồi quy**

Run: `python -m pytest tests/layout/ -q`
Expected: tất cả PASS

- [ ] **Step 8: Commit**

```bash
git add src/config.py src/etl/layout/regions.py tests/layout/test_regions.py
git commit -m "feat(config): them FORMULA_HYBRID_ENABLED + TextUnit.formula_hybrid_status"
```

---

## Task 5: Nối hybrid flow vào `extract_text_units`

**Files:**
- Modify: `src/etl/layout/text_extract.py`
- Test: `tests/layout/test_text_extract.py` (thêm test), tạo mới
  `tests/layout/test_text_extract_formula_hybrid.py`

**Interfaces:**
- Consumes: `is_formula_suspect` (từ `formula_gate.py`, đã có, D-144),
  `image_to_lines` (Task 1), `merge_formula_line`/`apply_line_merge_to_region`
  (Task 2), `FormulaMinerUClient`/`get_formula_client` (Task 3),
  `FORMULA_HYBRID_ENABLED` (Task 4)
- Produces: `extract_text_units(image, regions, variant, formula_client=None) -> list[TextUnit]`
  (thêm tham số MỚI `formula_client`, mặc định `None` = dùng
  `get_formula_client()` khi `FORMULA_HYBRID_ENABLED`, không gọi gì khi tắt)

- [ ] **Step 1: Viết test đơn vị cho hàm nội bộ `_maybe_apply_formula_hybrid`
  bằng ẢNH THẬT (trang 121, sách 7 KNTT — ca `CO₂`/`O₂` đã biết ở D-56/D-63) và
  client GIẢ (không cần GPU)**

```python
# tests/layout/test_text_extract_formula_hybrid.py
# -*- coding: utf-8 -*-
"""Tich hop hybrid formula vao text_extract.py, client MinerU GIA (khong can
GPU). Anh that de bat loi off-by-one giua bbox dong va bbox region TRUOC khi
cham GPU that tren Colab."""
import numpy as np
import pytest

from src.config import DATA_DIR
from src.etl.page_source import find_page_source
from src.etl.layout.regions import Region, RegionType
from src.etl.layout.text_extract import extract_text_units


class _FakeClient:
    """Tra loi CO doc dung cho crop bat ky - du de test luong ghep end-to-end
    ma khong can biet truoc bbox chinh xac cua tung dong."""

    def read(self, crop_bgr, kind="text"):
        return "hấp thụ khí CO₂ và thải ra khí O₂ vào ban đêm"


def test_formula_hybrid_applies_on_real_broken_page():
    pytest.importorskip("cv2")
    try:
        source = find_page_source(DATA_DIR, "SGK_KHTN_7_KNTT")
        img = source.load(121)
    except Exception as exc:
        pytest.skip(f"trang mau khong co tren may nay: {exc}")

    h, w = img.shape[:2]
    # Vung chua dong bi vo o trang 121 (do o D-63/D-144): gan het chieu rong
    # trang, mot dai ngang o phan giua trang.
    region = Region(RegionType.BODY, (0, int(h * 0.2), w, int(h * 0.6)),
                     reading_order=0, meta={"excludes": []})

    units = extract_text_units(img, [region], "kntt",
                                formula_client=_FakeClient())

    assert len(units) == 1
    joined = units[0].text
    # Truoc khi co hybrid, vung nay chua "0," (chi so bi vo, D-63). Sau khi
    # ghep, PHAI khong con dang "0," dinh lien nua O IT NHAT mot cho — bang
    # chung ro rang nhat la text chua "CO₂" that (Unicode subscript).
    assert "CO₂" in joined or "O₂" in joined
    assert units[0].formula_hybrid_status, (
        "phai co it nhat mot trang thai hybrid duoc ghi lai")


def test_formula_hybrid_off_by_default_leaves_text_untouched():
    """`formula_client=None` va `FORMULA_HYBRID_ENABLED=false` (mac dinh may
    dev) -> hanh vi y het truoc khi co hybrid, khong goi gi ca."""
    pytest.importorskip("cv2")
    try:
        source = find_page_source(DATA_DIR, "SGK_KHTN_7_KNTT")
        img = source.load(121)
    except Exception as exc:
        pytest.skip(f"trang mau khong co tren may nay: {exc}")

    h, w = img.shape[:2]
    region = Region(RegionType.BODY, (0, int(h * 0.2), w, int(h * 0.6)),
                     reading_order=0, meta={"excludes": []})

    units = extract_text_units(img, [region], "kntt")  # formula_client mac dinh

    assert units[0].formula_hybrid_status == []
```

- [ ] **Step 2: Chạy test, xác nhận FAIL (tham số `formula_client` chưa tồn tại)**

Run: `python -m pytest tests/layout/test_text_extract_formula_hybrid.py -v`
Expected: FAIL với `TypeError: extract_text_units() got an unexpected keyword argument 'formula_client'`

- [ ] **Step 3: Viết test cho hàm thuần `_maybe_apply_formula_hybrid` bằng dữ
  liệu tổng hợp (không cần ảnh thật) — bắt ca fail-safe "gate bắt ở text chính
  nhưng không dòng nào tái lập được"**

Thêm vào `tests/layout/test_text_extract.py`:

```python
def test_maybe_apply_formula_hybrid_fail_safe_when_no_line_reproduces_hit(monkeypatch):
    from src.etl.layout import text_extract as mod

    # Gia lap image_to_lines tra ve cac dong KHONG co dong nao chua lo hong,
    # trong khi text chinh (tham so `text`) CO lo hong - mo phong ca hai cot
    # dinh dong (D-108-style).
    monkeypatch.setattr(mod, "image_to_lines",
                         lambda crop, psm: [{"text": "khong lien quan gi ca",
                                              "bbox": (0, 0, 10, 10), "conf": 90}])

    crop = np.zeros((80, 200, 3), dtype=np.uint8)
    text = "hấp thụ khí 0, và thải ra khí (0,"

    new_text, statuses = mod._maybe_apply_formula_hybrid(crop, text, object())

    assert new_text == text
    assert statuses == ["gate_hit_no_line_located"]


def test_maybe_apply_formula_hybrid_returns_empty_when_not_suspect():
    from src.etl.layout import text_extract as mod

    crop = np.zeros((80, 200, 3), dtype=np.uint8)
    text = "Tế bào là đơn vị cơ bản của sự sống"

    new_text, statuses = mod._maybe_apply_formula_hybrid(crop, text, object())

    assert new_text == text
    assert statuses == []
```

(Cần `import numpy as np` ở đầu `test_text_extract.py` nếu chưa có.)

- [ ] **Step 4: Chạy test, xác nhận FAIL (hàm chưa tồn tại)**

Run: `python -m pytest tests/layout/test_text_extract.py -k formula_hybrid -v`
Expected: FAIL với `AttributeError: module '...text_extract' has no attribute '_maybe_apply_formula_hybrid'`

- [ ] **Step 5: Sửa `text_extract.py` — thêm import, hàm nội bộ, và nối vào
  `extract_text_units`**

Thêm vào đầu file (cạnh các import hiện có):

```python
from .formula_gate import is_formula_suspect
from .formula_merge import apply_line_merge_to_region, merge_formula_line
from .formula_ocr import get_formula_client
from .ocr_lines import image_to_lines
from ...config import FORMULA_HYBRID_ENABLED
```

Thêm hàm mới (sau `_mask_out`, trước `extract_text_units`):

```python
def _maybe_apply_formula_hybrid(crop, text, formula_client):
    """Neu `text` (da OCR xong bang duong chinh) bi gate nghi cong thuc: goi
    them `image_to_data` (side-computation, chi khi can) de tim DONG chua lo
    hong, crop rieng dong do, goi MinerU, ghep TOKEN vao dung vi tri.

    KHONG doi `text` neu khong co gi de ghep — tra ve nguyen ban + list trang
    thai rong. Xem thiet ke: document/specs/2026-08-27-formula-ocr-hybrid-buoc23-design.md §2.
    """
    if not is_formula_suspect(text):
        return text, []

    h, w = crop.shape[:2]
    psm = _psm_for(crop)
    lines = image_to_lines(crop, psm)

    statuses: list[str] = []
    new_text = text
    found_candidate_line = False
    for line in lines:
        line_text = line["text"]
        if not is_formula_suspect(line_text):
            continue
        found_candidate_line = True
        x0, y0, x1, y1 = line["bbox"]
        pad = 8
        cx0, cy0 = max(0, x0 - pad), max(0, y0 - pad)
        cx1, cy1 = min(w, x1 + pad), min(h, y1 + pad)
        line_crop = crop[cy0:cy1, cx0:cx1]
        if line_crop.size == 0:
            continue
        mineru_text = formula_client.read(line_crop, kind="text")
        outcome = merge_formula_line(line_text, mineru_text)
        if outcome.status == "not_suspect":
            continue
        statuses.append(outcome.status)
        if outcome.n_applied > 0:
            new_text, splice_status = apply_line_merge_to_region(
                new_text, line_text, outcome.text)
            statuses.append(splice_status)

    if not found_candidate_line:
        statuses.append("gate_hit_no_line_located")
    return new_text, statuses
```

Sửa `extract_text_units` (thêm tham số `formula_client=None`, gọi hàm mới sau
khi ghép pill, trước khi tạo `TextUnit`):

```python
def extract_text_units(image: np.ndarray, regions: list[Region], variant: str,
                        formula_client=None) -> list[TextUnit]:
    units: list[TextUnit] = []
    pill_bounds = bounds_for_width(image.shape[1])
    client = formula_client
    if client is None and FORMULA_HYBRID_ENABLED:
        client = get_formula_client()
    for r in sorted(regions, key=lambda z: z.reading_order):
        if r.type in (RegionType.FIGURE, RegionType.PAGE_ARTIFACT):
            continue
        x0, y0, x1, y1 = r.bbox
        crop = image[y0:y1, x0:x1]
        if crop.size == 0:
            continue
        if r.type == RegionType.BODY:
            crop = _mask_out(crop, r.meta.get("excludes", []))
        text = _ocr(crop)
        pills = _pill_text_missing_from(crop, text, pill_bounds)
        if pills:
            text = (text + "\n" + "\n".join(pills)).strip()
        formula_statuses: list[str] = []
        if client is not None and text:
            text, formula_statuses = _maybe_apply_formula_hybrid(
                crop, text, client)
        if text and len(text) > 5:
            flags = diacritic_review_flags(text) if DIACRITIC_REVIEW_ENABLED else []
            units.append(TextUnit(r.type, text, r.reading_order, r.bbox,
                                  review_flags=flags,
                                  formula_hybrid_status=formula_statuses))
    return units
```

**Lưu ý quan trọng:** `client is not None` là điều kiện gọi — trên máy dev,
`formula_client=None` VÀ `FORMULA_HYBRID_ENABLED=False` (mặc định) → `client`
vẫn `None` → `_maybe_apply_formula_hybrid` KHÔNG BAO GIỜ được gọi → 0 thay đổi
hành vi so với trước Task 5 trên đường mặc định (đúng Global Constraint "không
đụng `image_to_string()` cho region không bị gate nghi", và ở đây còn mạnh hơn:
không đụng gì cả khi tắt cờ).

- [ ] **Step 6: Chạy lại tất cả test của Task 5**

Run: `python -m pytest tests/layout/test_text_extract.py tests/layout/test_text_extract_formula_hybrid.py -v`
Expected: tất cả PASS. Nếu `test_formula_hybrid_applies_on_real_broken_page`
SKIP (không có `datasources/` trên máy chạy CI) — chấp nhận được, đã có
`pytest.skip` rõ lý do; nhưng PHẢI chạy PASS được trên máy dev có
`datasources/` trước khi coi task này xong.

- [ ] **Step 7: Chạy toàn bộ test layout để chắc không hồi quy**

Run: `python -m pytest tests/layout/ -q`
Expected: tất cả PASS, không giảm số lượng test cũ

- [ ] **Step 8: Commit**

```bash
git add src/etl/layout/text_extract.py tests/layout/test_text_extract.py tests/layout/test_text_extract_formula_hybrid.py
git commit -m "feat(etl): noi hybrid MinerU vao extract_text_units (D-144 Buoc 2/3)"
```

---

## Task 6: `chunker.py` + `loader.py` — truyền `formula_hybrid_status` và `book_id`

**Files:**
- Modify: `src/etl/layout/chunker.py`
- Modify: `src/etl/layout/loader.py`
- Test: `tests/layout/test_chunker.py` (thêm test)

**Interfaces:**
- Consumes: `TextUnit.formula_hybrid_status` (Task 4)
- Produces: chunk metadata field mới `"formula_hybrid_status": str` (comma-
  joined, giống `review_tokens`); `loader.py::load_page` gọi
  `extract_text_units(..., formula_client=...)` (client thật khi
  `FORMULA_HYBRID_ENABLED`, mặc định `None` khi không)

- [ ] **Step 1: Viết test cho metadata mới trong `chunker.py`**

Thêm vào `tests/layout/test_chunker.py`:

```python
def test_formula_hybrid_status_propagates_to_body_chunk_metadata():
    from src.etl.layout.chunker import chunk_units
    from src.etl.layout.regions import RegionType, TextUnit

    units = [
        TextUnit(RegionType.BODY, "một đoạn văn bản đủ dài để không bị bỏ qua",
                 0, (0, 0, 10, 10), formula_hybrid_status=["applied"]),
    ]

    docs = chunk_units(units, source="SGK_KHTN_7_KNTT", page=121, variant="kntt")

    assert docs[0].metadata["formula_hybrid_status"] == "applied"


def test_formula_hybrid_status_empty_when_no_unit_has_it():
    from src.etl.layout.chunker import chunk_units
    from src.etl.layout.regions import RegionType, TextUnit

    units = [
        TextUnit(RegionType.BODY, "một đoạn văn bản đủ dài để không bị bỏ qua",
                 0, (0, 0, 10, 10)),
    ]

    docs = chunk_units(units, source="SGK_KHTN_7_KNTT", page=121, variant="kntt")

    assert docs[0].metadata["formula_hybrid_status"] == ""


def test_formula_hybrid_status_dedupes_across_body_units():
    from src.etl.layout.chunker import chunk_units
    from src.etl.layout.regions import RegionType, TextUnit

    units = [
        TextUnit(RegionType.BODY, "đoạn một " * 10, 0, (0, 0, 10, 10),
                 formula_hybrid_status=["applied"]),
        TextUnit(RegionType.BODY, "đoạn hai " * 10, 1, (0, 10, 10, 20),
                 formula_hybrid_status=["applied", "unmatched_count"]),
    ]

    docs = chunk_units(units, source="SGK_KHTN_7_KNTT", page=121, variant="kntt")

    assert docs[0].metadata["formula_hybrid_status"] == "applied,unmatched_count"
```

- [ ] **Step 2: Chạy test, xác nhận FAIL (KeyError, chưa có field)**

Run: `python -m pytest tests/layout/test_chunker.py -k formula_hybrid -v`
Expected: FAIL với `KeyError: 'formula_hybrid_status'`

- [ ] **Step 3: Sửa `chunker.py` — thêm `formula_hybrid_status` vào `_meta`,
  gom từ các `TextUnit` giống cách `review_tokens`/`body_flags` đã làm**

```python
def _meta(source, page, variant, region_type, idx, page_index, bai_so, flags,
          formula_statuses):
    meta = {"source": source, "page": page, "variant": variant,
            "region_type": region_type, "chunk_index": idx,
            "needs_review": bool(flags),
            "review_tokens": ",".join(flags),
            "formula_hybrid_status": ",".join(formula_statuses)}
    if page_index is not None:
        meta["page_index"] = page_index
    if bai_so is not None:
        meta["bai_so"] = bai_so
    return meta

def chunk_units(units, source: str, page: int, variant: str,
                page_index: int = None, bai_so: int = None):
    docs, idx = [], 0
    body_units = [u for u in units if u.region_type == RegionType.BODY]
    body_text = "\n".join(u.text for u in body_units).strip()
    if body_text:
        body_flags = _dedupe(f for u in body_units for f in u.review_flags)
        body_formula = _dedupe(
            s for u in body_units for s in u.formula_hybrid_status)
        base = Document(page_content=body_text)
        for piece in _splitter.split([base]):
            docs.append(Document(page_content=piece.page_content,
                                 metadata=_meta(source, page, variant, "body",
                                                idx, page_index, bai_so,
                                                body_flags, body_formula)))
            idx += 1
    for u in units:
        if u.region_type == RegionType.BODY:
            continue
        text = u.text.strip()
        flags = _dedupe(u.review_flags)
        formula_statuses = _dedupe(u.formula_hybrid_status)
        pieces = [text]
        if len(text) > BOX_ATOMIC_MAX_CHARS:
            pieces = [p.page_content for p in
                      _splitter.split([Document(page_content=text)])]
        for piece in pieces:
            docs.append(Document(page_content=piece,
                                 metadata=_meta(source, page, variant,
                                                u.region_type.value, idx,
                                                page_index, bai_so, flags,
                                                formula_statuses)))
            idx += 1
    return docs
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `python -m pytest tests/layout/test_chunker.py -v`
Expected: tất cả PASS (cũ + mới)

- [ ] **Step 5: Sửa `loader.py::load_page` — truyền `formula_client` thật khi
  bật cờ**

Sửa dòng gọi `extract_text_units` trong `load_page` (giữ `segment_page(img,
variant)` nguyên như hiện tại — per-book `min_sat` là Task 7, KHÔNG làm ở đây):

```python
from ...config import FORMULA_HYBRID_ENABLED
from .formula_ocr import get_formula_client

...

def load_page(self, source, page_number: int):
    meta = self.page_meta(source, page_number)
    if meta.get("role") in SKIP_ROLES:
        logger.info(
            f"[{source.name}] trang {page_number}: role={meta['role']} "
            f"-> không index (nguồn vẫn giữ nguyên)")
        return []
    variant = get_pdf_variant(source.name)
    img = source.load(page_number)
    regions = segment_page(img, variant)
    formula_client = get_formula_client() if FORMULA_HYBRID_ENABLED else None
    units = extract_text_units(img, regions, variant,
                               formula_client=formula_client)
    bai_so = meta.get("bai_so") if self.spine_is_trusted(source) else None
    return chunk_units(units, source=source.name,
                       page=int(meta["printed_page"]), variant=variant,
                       page_index=int(page_number),
                       ...)  # giữ nguyên phần còn lại của lệnh gọi hiện có
```

(Executor: mở `src/etl/layout/loader.py` thật để copy chính xác phần tham số
còn lại của lời gọi `chunk_units` hiện có — KHÔNG được đoán, chỉ thêm 2 dòng
`formula_client = ...` và tham số `formula_client=formula_client` vào lời gọi
`extract_text_units`.)

- [ ] **Step 6: Chạy test loader hiện có, xác nhận không hồi quy**

Run: `python -m pytest tests/layout/test_loader.py tests/layout/test_loader_real_page.py -v`
Expected: tất cả PASS

- [ ] **Step 7: Commit**

```bash
git add src/etl/layout/chunker.py src/etl/layout/loader.py tests/layout/test_chunker.py
git commit -m "feat(etl): truyen formula_hybrid_status vao metadata chunk"
```

---

## Task 7: `LAYOUT_BOX_MIN_SATURATION` per-book (đo + wiring)

**Files:**
- Create: `scripts/measure_min_sat_floor.py`
- Modify: `src/etl/layout/segmenter.py`
- Modify: `src/etl/layout/loader.py` (truyền `source.name` xuống `segment_page`)
- Test: `tests/layout/test_segmenter.py` (thêm test)

**Interfaces:**
- Produces: `segmenter._params_for(book: str | None = None) -> dict` (đọc
  `box_palette.sat_percentiles.p10` từ fingerprint của `book`, sàn tối thiểu
  ĐÃ ĐO — điền sau Step 1); `segment_page(image, variant, book=None)`

- [ ] **Step 1: Đo sàn tối thiểu bằng script (KHÔNG đoán số, chạy thật trước
  khi viết code chính)**

Viết `scripts/measure_min_sat_floor.py`:

```python
# -*- coding: utf-8 -*-
"""Quet san toi thieu cho `min_sat` per-book: so sanh so hop mau tim duoc voi
hang so cu (45) tren cung mau trang cua fingerprint (`box_palette.pages_probed`),
KHONG doan (nguyen tac 3). Chay: python scripts/measure_min_sat_floor.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import DATA_DIR, FINGERPRINT_DIR
from src.etl.page_source import find_page_source
from src.etl.layout.segmenter import _colored_boxes, _BOX_DEFAULTS

BOOKS = ["SGK_KHTN_6_KNTT", "SGK_KHTN_7_KNTT", "SGK_KHTN_8_KNTT", "SGK_KHTN_9_KNTT",
         "SGK_KHTN_6_CTST", "SGK_KHTN_7_CTST", "SGK_KHTN_8_CTST", "SGK_KHTN_9_CTST",
         "SGK_KHTN_6_CD", "SGK_KHTN_7_CD", "SGK_KHTN_8_CD", "SGK_KHTN_9_CD"]
CANDIDATE_FLOORS = [45, 35, 30, 25, 20, 15]

for book in BOOKS:
    fp_path = FINGERPRINT_DIR / f"{book}.json"
    fp = json.loads(fp_path.read_text(encoding="utf-8"))
    p10 = fp["box_palette"]["sat_percentiles"]["p10"]
    pages = fp["box_palette"]["pages_probed"][:10]  # 10 trang cho nhanh
    source = find_page_source(DATA_DIR, book)
    row = [f"{book:16s} p10={p10:6.1f}"]
    for floor in CANDIDATE_FLOORS:
        min_sat = max(floor, round(p10))
        params = dict(_BOX_DEFAULTS)
        params["min_sat"] = min_sat
        total = 0
        for pn in pages:
            img = source.load(pn)
            boxes = _colored_boxes(img, params)
            total += len(boxes)
        row.append(f"floor{floor}(sat={min_sat})={total}")
    print("  ".join(row))
```

Run: `python scripts/measure_min_sat_floor.py`

Ghi lại output THẬT (không phải giả định) — quy tắc chọn: với mỗi quyển, chọn
`min_sat = max(floor, p10)` sao cho tổng số hộp tìm được **KHÔNG THẤP HƠN** số
hộp tìm được ở `floor=45` (hàng đầu tiên, baseline hiện tại) trên cùng 10 trang.
Nếu nhiều floor thoả, chọn floor NHỎ NHẤT (bắt được nhiều hộp nhạt màu hơn mà
không mất hộp cũ). Ghi số đo và floor đã chọn vào
`document/decision_log.html` (entry mới, tiếp theo D-144) TRƯỚC KHI sang Step 2.

- [ ] **Step 2: Viết test cho `_params_for(book)` per-book (dùng số ĐÃ ĐO ở
  Step 1, KHÔNG dùng số ví dụ)**

```python
def test_params_for_reads_min_sat_from_fingerprint(tmp_path, monkeypatch):
    import json
    from src.etl.layout import segmenter as mod

    fp_dir = tmp_path / "fingerprints"
    fp_dir.mkdir()
    (fp_dir / "SGK_KHTN_9_CD.json").write_text(json.dumps(
        {"box_palette": {"sat_percentiles": {"p10": 12.0}}}), encoding="utf-8")
    monkeypatch.setattr(mod, "FINGERPRINT_DIR", fp_dir)

    params = mod._params_for(book="SGK_KHTN_9_CD")

    assert params["min_sat"] == mod.MIN_SAT_FLOOR  # p10=12 duoi san -> dung san


def test_params_for_falls_back_to_default_when_fingerprint_missing(tmp_path, monkeypatch, caplog):
    from src.etl.layout import segmenter as mod

    monkeypatch.setattr(mod, "FINGERPRINT_DIR", tmp_path)  # thu muc rong

    params = mod._params_for(book="SGK_KHTN_KHONG_TON_TAI")

    assert params["min_sat"] == 45
    assert "fingerprint" in caplog.text.lower()


def test_params_for_no_book_keeps_old_constant_behaviour():
    from src.etl.layout import segmenter as mod

    params = mod._params_for()

    assert params["min_sat"] == 45
```

(`MIN_SAT_FLOOR` là hằng số điền theo số đo Step 1 — KHÔNG được để trống, sửa
Step 3 để định nghĩa đúng giá trị đã đo.)

- [ ] **Step 3: Sửa `segmenter.py` — đọc fingerprint per-book, dùng
  `MIN_SAT_FLOOR` đã đo ở Step 1**

```python
import json
import logging
from ...config import FINGERPRINT_DIR

logger = logging.getLogger(__name__)

# SAN toi thieu cho min_sat per-book - DA DO (scripts/measure_min_sat_floor.py,
# ghi vao decision log D-<so_thu_tu_tiep_theo>). Executor: thay so nay bang so
# THAT tu Step 1, dung comment giai thich vi sao.
MIN_SAT_FLOOR = 45  # placeholder - PHAI thay bang so do that o Step 1


def _params_for(variant: str = "", book: str | None = None) -> dict:
    params = dict(_BOX_DEFAULTS)
    if not book:
        return params
    fp_path = FINGERPRINT_DIR / f"{book}.json"
    if not fp_path.exists():
        logger.warning(
            f"[{book}] không có fingerprint tại {fp_path} -> dùng min_sat mặc "
            f"định {params['min_sat']} (không phải giá trị per-book đã đo)")
        return params
    try:
        fp = json.loads(fp_path.read_text(encoding="utf-8"))
        p10 = fp["box_palette"]["sat_percentiles"]["p10"]
    except (OSError, ValueError, KeyError) as exc:
        logger.warning(f"[{book}] fingerprint hỏng/thiếu box_palette: {exc} "
                       f"-> dùng min_sat mặc định {params['min_sat']}")
        return params
    params["min_sat"] = max(MIN_SAT_FLOOR, round(p10))
    return params
```

**QUAN TRỌNG:** `MIN_SAT_FLOOR = 45` ở trên là placeholder CỐ Ý ghi rõ để
executor không thể bỏ qua — PHẢI thay bằng con số thật từ Step 1 trước khi coi
task này xong. Nếu tự đo Step 1 chưa xong, KHÔNG được đoán 45 hay bất kỳ số nào
khác; dừng lại và chạy Step 1 trước.

Sửa `segment_page` để nhận `book`:

```python
def segment_page(image: np.ndarray, variant: str, book: str | None = None) -> list[Region]:
    h, w = image.shape[:2]
    boxes = _colored_boxes(image, _params_for(variant, book))
    ...  # phần còn lại giữ nguyên
```

- [ ] **Step 4: Chạy test, xác nhận PASS với số đã đo**

Run: `python -m pytest tests/layout/test_segmenter.py -v`
Expected: tất cả PASS

- [ ] **Step 5: Sửa `loader.py::load_page` — truyền `source.name` (KHÔNG PHẢI
  `book_id_from_source_name(source.name)`) xuống `segment_page`**

**Bẫy đã kiểm trước (đừng lặp lại):** fingerprint file tên là `source.name`
(vd `SGK_KHTN_6_KNTT.json`), KHÔNG PHẢI `book_id` (`KHTN6-KNTT` — dạng
`book_id_from_source_name` trả về, dùng cho MANIFEST, khác mục đích).

```python
regions = segment_page(img, variant, book=source.name)
```

- [ ] **Step 6: Chạy lại test loader + segmenter + qa_layout smoke**

Run: `python -m pytest tests/layout/ -q`
Expected: tất cả PASS

Run trên vài trang thật để xác nhận không hồi quy trực quan (đã ghi trong
CLAUDE.md là cổng bắt buộc trước khi tin số đo):
`python -m src.test.qa_layout --book SGK_KHTN_6_KNTT --pages 10,11,12 --report`
Expected: số vùng/trang không giảm so với trước khi sửa (so với con số đã ghi
trong CLAUDE.md cho các trang này, nếu có).

- [ ] **Step 7: Commit**

```bash
git add scripts/measure_min_sat_floor.py src/etl/layout/segmenter.py src/etl/layout/loader.py tests/layout/test_segmenter.py
git commit -m "feat(etl): min_sat per-book tu fingerprint, thay hang so 45"
```

---

## Task 8: `SINGLE_LINE_MAX_H` per-book (đo + wiring)

**Files:**
- Create: `scripts/measure_single_line_height.py`
- Modify: `src/etl/layout/text_extract.py`
- Test: `tests/layout/test_text_extract.py` (thêm test)

**Interfaces:**
- Produces: `single_line_max_h_for_book(book: str | None) -> int` (đọc từ
  fingerprint nếu có key `text_layout.single_line_max_h_p90`, fallback về hằng
  số `60` hiện tại nếu thiếu — KHÔNG BAO GIỜ thấp hơn 60, chỉ tăng lên khi có
  bằng chứng)

**Phạm vi cố ý thu hẹp so với bản nháp đầu của thiết kế:** không xây một stage
mới trong `fingerprint.py` (chi phí ~70 phút OCR/12 quyển cho MỘT tham số phụ là
không tương xứng). Thay vào đó: dùng LẠI mẫu trang đã có sẵn trong fingerprint
(`box_palette.pages_probed`, 30-40 trang/quyển, không tốn OCR mới để CHỌN mẫu),
đo riêng chiều cao crop MỘT DÒNG THẬT trên mẫu đó, rồi GHI KẾT QUẢ NGƯỢC vào
chính file fingerprint JSON đó (thêm key mới, không đụng key cũ).

- [ ] **Step 1: Đo thật (KHÔNG đoán số) — chạy script trên mẫu 30-40 trang/quyển
  đã có sẵn trong fingerprint**

Viết `scripts/measure_single_line_height.py`:

```python
# -*- coding: utf-8 -*-
"""Do chieu cao THAT cua cac crop MOT DONG DUY NHAT (segment_page + dem so dong
Tesseract trong tung box) tren dung mau trang da co san trong fingerprint M0
(box_palette.pages_probed) - khong ton OCR moi de CHON mau. Ghi ket qua NGUOC
vao chinh file fingerprint (them key moi `text_layout`, khong dung key cu).

Chay: python scripts/measure_single_line_height.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytesseract
from src.config import DATA_DIR, FINGERPRINT_DIR, TESSERACT_CMD
from src.etl.page_source import find_page_source
from src.etl.layout.segmenter import segment_page
from src.etl.layout.regions import RegionType

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

BOOKS = ["SGK_KHTN_6_KNTT", "SGK_KHTN_7_KNTT", "SGK_KHTN_8_KNTT", "SGK_KHTN_9_KNTT",
         "SGK_KHTN_6_CTST", "SGK_KHTN_7_CTST", "SGK_KHTN_8_CTST", "SGK_KHTN_9_CTST",
         "SGK_KHTN_6_CD", "SGK_KHTN_7_CD", "SGK_KHTN_8_CD", "SGK_KHTN_9_CD"]
CURRENT_DEFAULT = 60


def n_lines_in_crop(crop) -> int:
    if crop.size == 0:
        return 0
    data = pytesseract.image_to_data(crop, lang="vie", config="--psm 6",
                                      output_type=pytesseract.Output.DICT)
    keys = {(data["block_num"][i], data["par_num"][i], data["line_num"][i])
            for i in range(len(data["text"])) if str(data["text"][i]).strip()}
    return len(keys)


for book in BOOKS:
    fp_path = FINGERPRINT_DIR / f"{book}.json"
    fp = json.loads(fp_path.read_text(encoding="utf-8"))
    pages = fp["box_palette"]["pages_probed"]
    variant = "kntt" if "KNTT" in book else ("ctst" if "CTST" in book else "cd")
    source = find_page_source(DATA_DIR, book)
    heights = []
    for pn in pages:
        img = source.load(pn)
        for r in segment_page(img, variant):
            if r.type in (RegionType.FIGURE, RegionType.PAGE_ARTIFACT, RegionType.BODY):
                continue
            x0, y0, x1, y1 = r.bbox
            h = y1 - y0
            if h <= 0 or h > 400:
                continue
            crop = img[y0:y1, x0:x1]
            if n_lines_in_crop(crop) == 1:
                heights.append(h)
    arr = np.array(heights)
    if len(arr) >= 5:
        p90 = float(np.percentile(arr, 90))
        chosen = max(CURRENT_DEFAULT, round(p90))
        fp.setdefault("text_layout", {})["single_line_max_h_p90"] = chosen
        fp["text_layout"]["single_line_max_h_n_samples"] = len(arr)
        print(f"{book:16s} n={len(arr):3d} p90={p90:6.1f} -> ghi {chosen}")
    else:
        print(f"{book:16s} n={len(arr):3d} < 5 mau -> KHONG du tin cay, "
              f"GIU {CURRENT_DEFAULT} (khong ghi key moi)")
        continue
    fp_path.write_text(json.dumps(fp, ensure_ascii=False, indent=1), encoding="utf-8")
```

Run: `python scripts/measure_single_line_height.py`

Ghi lại output thật vào `document/decision_log.html` (cùng entry với Task 7
hoặc entry riêng, tuỳ số liệu). Quy tắc quyết định: `max(60, p90)` — KHÔNG BAO
GIỜ hạ threshold xuống dưới 60 (tránh hồi quy các quyển đã hoạt động đúng ở mức
đó); sách mẫu ít hơn 5 mẫu single-line thì GIỮ NGUYÊN 60, không ghi.

- [ ] **Step 2: Viết test cho `single_line_max_h_for_book`**

```python
def test_single_line_max_h_for_book_reads_from_fingerprint(tmp_path, monkeypatch):
    import json
    from src.etl.layout import text_extract as mod

    fp_dir = tmp_path
    (fp_dir / "SGK_KHTN_9_CD.json").write_text(json.dumps(
        {"text_layout": {"single_line_max_h_p90": 118}}), encoding="utf-8")
    monkeypatch.setattr(mod, "FINGERPRINT_DIR", fp_dir)

    assert mod.single_line_max_h_for_book("SGK_KHTN_9_CD") == 118


def test_single_line_max_h_falls_back_to_default_without_key(tmp_path, monkeypatch):
    import json
    from src.etl.layout import text_extract as mod

    (tmp_path / "SGK_KHTN_6_KNTT.json").write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setattr(mod, "FINGERPRINT_DIR", tmp_path)

    assert mod.single_line_max_h_for_book("SGK_KHTN_6_KNTT") == mod.SINGLE_LINE_MAX_H


def test_single_line_max_h_none_book_keeps_default():
    from src.etl.layout import text_extract as mod

    assert mod.single_line_max_h_for_book(None) == mod.SINGLE_LINE_MAX_H
```

- [ ] **Step 3: Chạy test, xác nhận FAIL (hàm chưa tồn tại)**

Run: `python -m pytest tests/layout/test_text_extract.py -k single_line_max_h -v`
Expected: FAIL với `AttributeError`

- [ ] **Step 4: Sửa `text_extract.py` — thêm hàm đọc fingerprint, sửa `_psm_for`
  và `_ocr` để nhận ngưỡng theo book (mặc định giữ nguyên `SINGLE_LINE_MAX_H`
  khi không truyền `max_h`, KHÔNG đổi hành vi của lời gọi cũ nào)**

```python
import json
from ...config import FINGERPRINT_DIR

def single_line_max_h_for_book(book: str | None) -> int:
    if not book:
        return SINGLE_LINE_MAX_H
    fp_path = FINGERPRINT_DIR / f"{book}.json"
    if not fp_path.exists():
        return SINGLE_LINE_MAX_H
    try:
        fp = json.loads(fp_path.read_text(encoding="utf-8"))
        return int(fp.get("text_layout", {}).get(
            "single_line_max_h_p90", SINGLE_LINE_MAX_H))
    except (OSError, ValueError):
        return SINGLE_LINE_MAX_H


def _psm_for(crop: np.ndarray, max_h: int = SINGLE_LINE_MAX_H) -> int:
    return 7 if crop.shape[0] < max_h else 6


def _ocr(img: np.ndarray, max_h: int = SINGLE_LINE_MAX_H) -> str:
    raw = pytesseract.image_to_string(
        img, lang="vie", config=f"--psm {_psm_for(img, max_h)}")
    return clean_vietnamese_text(raw)
```

- [ ] **Step 5: Nối `book` xuyên suốt `extract_text_units` — BẮT BUỘC, không
  phải mở rộng tuỳ chọn (per-book `SINGLE_LINE_MAX_H` vô nghĩa nếu không dùng
  thật). Sửa 3 chỗ trong `text_extract.py` (đã tồn tại từ Task 5) và 1 chỗ
  trong `loader.py` (đã tồn tại từ Task 7 Step 5):**

Trong `text_extract.py`, thêm tham số `book=None` vào cả hai hàm, và dùng
`single_line_max_h_for_book(book)` ở đúng hai nơi gọi `_ocr`/`_psm_for`:

```python
def _maybe_apply_formula_hybrid(crop, text, formula_client, book=None):
    if not is_formula_suspect(text):
        return text, []

    h, w = crop.shape[:2]
    max_h = single_line_max_h_for_book(book)
    psm = _psm_for(crop, max_h)
    lines = image_to_lines(crop, psm)
    ...  # phần còn lại giữ NGUYÊN như Task 5 đã viết


def extract_text_units(image: np.ndarray, regions: list[Region], variant: str,
                        formula_client=None, book: str | None = None) -> list[TextUnit]:
    units: list[TextUnit] = []
    pill_bounds = bounds_for_width(image.shape[1])
    max_h = single_line_max_h_for_book(book)
    client = formula_client
    if client is None and FORMULA_HYBRID_ENABLED:
        client = get_formula_client()
    for r in sorted(regions, key=lambda z: z.reading_order):
        if r.type in (RegionType.FIGURE, RegionType.PAGE_ARTIFACT):
            continue
        x0, y0, x1, y1 = r.bbox
        crop = image[y0:y1, x0:x1]
        if crop.size == 0:
            continue
        if r.type == RegionType.BODY:
            crop = _mask_out(crop, r.meta.get("excludes", []))
        text = _ocr(crop, max_h)
        pills = _pill_text_missing_from(crop, text, pill_bounds)
        if pills:
            text = (text + "\n" + "\n".join(pills)).strip()
        formula_statuses: list[str] = []
        if client is not None and text:
            text, formula_statuses = _maybe_apply_formula_hybrid(
                crop, text, client, book=book)
        if text and len(text) > 5:
            flags = diacritic_review_flags(text) if DIACRITIC_REVIEW_ENABLED else []
            units.append(TextUnit(r.type, text, r.reading_order, r.bbox,
                                  review_flags=flags,
                                  formula_hybrid_status=formula_statuses))
    return units
```

Trong `loader.py::load_page` (dòng đã sửa ở Task 7 Step 5), thêm tham số `book`:

```python
units = extract_text_units(img, regions, variant,
                           formula_client=formula_client, book=source.name)
```

- [ ] **Step 6: Chạy test, xác nhận PASS — kể cả test cũ của Task 5/6 (đổi chữ
  ký hàm không được làm hồi quy các test đã pass trước đó, vì mọi tham số mới
  đều có default)**

Run: `python -m pytest tests/layout/ -q`
Expected: tất cả PASS, không giảm số lượng test

- [ ] **Step 7: Commit**

```bash
git add scripts/measure_single_line_height.py src/etl/layout/text_extract.py src/etl/layout/loader.py tests/layout/test_text_extract.py database/fingerprints/*.json
git commit -m "feat(etl): do va noi single_line_max_h_for_book xuyen suot pipeline"
```

---

## Task 9: Bump version + script ước lượng chi phí Colab

**Files:**
- Modify: `.env`, `.env.example` (nếu có `TEXT_EXTRACTION_VERSION`)
- Create: `src/test/estimate_formula_hybrid_cost.py`

**Interfaces:**
- Produces: script CLI in ra số dòng ước tính cần gọi MinerU + ETA

- [ ] **Step 1: Bump `TEXT_EXTRACTION_VERSION`**

Tìm dòng `TEXT_EXTRACTION_VERSION` trong `.env` (và `.env.example` nếu có),
đổi giá trị hiện tại (`v2_bai_spine`) thành `v3_formula_hybrid` — gộp CẢ BA
thay đổi (Task 5 hybrid + Task 7 min_sat + Task 8 single_line_max_h), đúng
Global Constraint (một lượt bump duy nhất).

- [ ] **Step 2: Viết `estimate_formula_hybrid_cost.py` — đếm số DÒNG nghi công
  thức trên index hiện có, KHÔNG cần OCR lại, KHÔNG cần Colab**

```python
# -*- coding: utf-8 -*-
"""Uoc luong so lan phai goi MinerU tren CA 12 QUYEN, doc thang tu index
`biology_text` DA CO (khong OCR lai) - de biet ETA that truoc khi chay Colab.

Chay: python -m src.test.estimate_formula_hybrid_cost
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.etl.layout.formula_gate import is_formula_suspect
from src.rag.sparse_store import open_text_collection

SECONDS_PER_CALL = 2.6  # do that o D-108 (content_extract, khong phai two_step_extract)


def main() -> int:
    # `open_text_collection()` mo Chroma THUAN, KHONG nap bge-m3 (sparse_store.py
    # da ghi ro: nap embedding model chi de doc chu la ~1 phut CPU doi lay dung 0
    # thong tin). Dung lai ham co san thay vi VectorDB() de script nay chay nhanh.
    coll = open_text_collection()
    data = coll.get(include=["documents"], limit=1_000_000)
    docs = data.get("documents") or []

    n_lines_suspect = 0
    n_docs_with_hit = 0
    for text in docs:
        lines = str(text or "").split("\n")
        hit_lines = [l for l in lines if is_formula_suspect(l)]
        if hit_lines:
            n_docs_with_hit += 1
            n_lines_suspect += len(hit_lines)

    eta_seconds = n_lines_suspect * SECONDS_PER_CALL
    print(f"Tổng chunk: {len(docs)}")
    print(f"Chunk có ≥1 dòng nghi công thức: {n_docs_with_hit}")
    print(f"Tổng số DÒNG nghi công thức (ước số lần gọi MinerU): {n_lines_suspect}")
    print(f"ETA gọi MinerU (@ {SECONDS_PER_CALL}s/dòng, D-108): "
          f"{eta_seconds:.0f}s ≈ {eta_seconds / 60:.1f} phút")
    print("Lưu ý: đây là số đếm trên index CŨ (chưa hybrid) — số THẬT khi ETL "
          "chạy lại có thể khác vì gate chạy trên OCR MỚI, không phải trên "
          "text cũ này. Coi đây là CẬN TRÊN thô để ước ETA Colab, không phải "
          "số chính xác.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Chạy thử trên index hiện có (nếu máy dev có `database/`), ghi
  số vào decision log**

Run: `python -m src.test.estimate_formula_hybrid_cost`

Nếu máy dev KHÔNG có `database/` (đã xoá theo README), ghi rõ vào decision log
là "chưa chạy được trên máy dev, sẽ chạy lần đầu trên Colab trước vòng lặp ETL
thật" — không giả lập số.

- [ ] **Step 4: Commit**

```bash
git add .env .env.example src/test/estimate_formula_hybrid_cost.py
git commit -m "feat(etl): bump TEXT_EXTRACTION_VERSION v3, them script uoc luong chi phi"
```

---

## Task 10: Vá `document/colab_runtime_etl.ipynb`

**Files:**
- Modify: `document/colab_runtime_etl.ipynb`

- [ ] **Step 1: Đọc notebook hiện có bằng Python (không sửa tay JSON thô — dễ
  hỏng cú pháp, bài học D-136)**

```python
import json
p = "document/colab_runtime_etl.ipynb"
nb = json.load(open(p, encoding="utf-8"))
for i, c in enumerate(nb["cells"]):
    print(i, c["cell_type"], "".join(c["source"])[:60].replace("\n", " "))
```

Xác định lại đúng chỉ số cell path-env (§5, quan sát trước đó là cell 12) và
cell zip/download (§12, quan sát trước đó là cell 42-43) — chỉ số có thể lệch
nếu notebook đã đổi từ lượt trước, PHẢI xác nhận lại bằng lệnh trên, không dùng
số cũ mù quáng.

- [ ] **Step 2: Sửa cell path-env — `RAG_DATABASE_DIR` sang session-local**

Đổi dòng:
```python
os.environ["RAG_DATABASE_DIR"] = "/content/drive/MyDrive/project_bio_rag/database"
```
thành:
```python
# D-56 Bước 2/3 (2026-08-28): Drive đầy — DB nay ở SESSION, KHÔNG Drive.
# RỦI RO: mất checkpoint-resume nếu Colab rớt phiên (khác bản Drive cũ "bền
# qua các phiên"). Giảm thiểu: chạy TỪNG QUYỂN MỘT (mục 9b), tải zip về SAU
# MỖI QUYỂN — rớt phiên giữa chừng chỉ mất tối đa 1 quyển.
os.environ["RAG_DATABASE_DIR"] = "/content/database"
```

Thêm dòng set env cho hybrid (cùng cell hoặc cell mới ngay sau):
```python
os.environ["FORMULA_HYBRID_ENABLED"] = "true"
os.environ["TEXT_EXTRACTION_VERSION"] = "v3_formula_hybrid"
```

- [ ] **Step 3: Thêm cell cài `mineru_vl_utils` + ghim `transformers` (D-101)**

Thêm markdown cell mới trước bước ETL thật:
```markdown
### 5c. Cài MinerU cho hybrid công thức (D-56 Bước 2/3)

Ghim `transformers>=4.49,<5` — D-101 đo được 5.x nạp HỎNG lm_head của model họ
Qwen2-VL (MinerU dùng kiến trúc này), sinh token rác thay vì đọc kém.
```

Thêm code cell:
```python
!pip install -q mineru_vl_utils "transformers>=4.49,<5"
import transformers
print("transformers:", transformers.__version__)
assert transformers.__version__.split(".")[0] != "5" or \
    int(transformers.__version__.split(".")[1]) == 0, \
    "Ghim sai — kiểm lại 'transformers>=4.49,<5' có hiệu lực chưa"
```

- [ ] **Step 4: Thêm cell ước lượng chi phí (§8 spec), chạy TRƯỚC vòng lặp ETL
  thật**

```python
!python -m src.test.estimate_formula_hybrid_cost
```

- [ ] **Step 5: Đổi vòng lặp ETL — chạy TỪNG QUYỂN, zip+tải SAU MỖI QUYỂN**

Tìm cell chạy `main.py --text-only` (không có `--book`, chạy cả 12 quyển cùng
lúc) — thay bằng vòng lặp:

```python
import subprocess

BOOKS = ["SGK_KHTN_6_KNTT", "SGK_KHTN_7_KNTT", "SGK_KHTN_8_KNTT", "SGK_KHTN_9_KNTT",
         "SGK_KHTN_6_CTST", "SGK_KHTN_7_CTST", "SGK_KHTN_8_CTST", "SGK_KHTN_9_CTST",
         "SGK_KHTN_6_CD", "SGK_KHTN_7_CD", "SGK_KHTN_8_CD", "SGK_KHTN_9_CD"]

for book in BOOKS:
    print(f"\n=== {book} ===")
    r = subprocess.run(["python", "main.py", "--text-only", "--book", book])
    print(f"{book} exit code: {r.returncode}")
    if r.returncode != 0:
        print(f"!! {book} THẤT BẠI (mã {r.returncode}) — DỪNG, kiểm log trước "
              "khi sang quyển tiếp theo (đừng chạy tiếp che lấp lỗi).")
        break
    !zip -r -q /content/database_backup.zip /content/database
    from google.colab import files
    files.download('/content/database_backup.zip')
    print(f"Đã tải zip sau khi xong {book} (zip CỘNG DỒN các quyển trước đó).")
```

- [ ] **Step 6: Đổi §12 (zip cuối) — không còn "tuỳ chọn", ghi rõ đã gộp vào
  vòng lặp ở §9**

Sửa markdown §12 thành:
```markdown
## 12. Sao lưu DB — ĐÃ GỘP vào vòng lặp §9 (D-56 Bước 2/3, DB session-local)

DB nay nằm ở `/content/database` (session, KHÔNG Drive) — zip + tải về xảy ra
SAU MỖI QUYỂN trong vòng lặp §9, không phải một lần ở cuối. Cell dưới đây chỉ
còn dùng khi cần tải lại thủ công (ví dụ notebook bị ngắt giữa vòng lặp).
```

- [ ] **Step 7: Chạy `python report/kiem_tra_tex.py` KHÔNG áp dụng ở đây (đó là
  lint .tex) — thay vào đó validate JSON hợp lệ của chính notebook**

Run: `python -c "import json; json.load(open('document/colab_runtime_etl.ipynb', encoding='utf-8')); print('JSON hợp lệ')"`
Expected: in ra "JSON hợp lệ", không exception

- [ ] **Step 8: Commit**

```bash
git add document/colab_runtime_etl.ipynb
git commit -m "docs(colab): DB session-local + tung quyen + tai ve sau moi quyen (D-56 Buoc 2/3)"
```

---

## Task 11: Decision log + CLAUDE.md + memory + spec — "định nghĩa xong"

**Files:**
- Modify: `document/decision_log.html`
- Modify: `CLAUDE.md`
- Modify: memory files liên quan (`ocr_bakeoff.md`, `MEMORY.md`)
- Modify: `document/specs/2026-08-27-formula-ocr-hybrid-buoc23-design.md` (đánh
  dấu trạng thái implement)

- [ ] **Step 1: Chạy toàn bộ test suite, lấy số pass/skip thật**

Run: `python -m pytest tests/ -q`
Expected: ghi lại số thật (không đoán) để đưa vào decision log

- [ ] **Step 2: Thêm entry decision log (D-<số tiếp theo>) tổng kết Bước 2/3**

Mở `document/decision_log.html`, tìm ID lớn nhất hiện có
(`grep -oE "id: \"D-[0-9]+\"" document/decision_log.html | sort -V | tail -1`),
thêm entry mới NGAY TRƯỚC dòng `];` đóng mảng `DECISIONS`, theo đúng format các
entry trước đó (`id`, `date`, `decision`, `notes`, `tags`). Nội dung `notes`
phải nêu: số đo Task 7 (floor `min_sat` đã chọn + bằng chứng), số đo Task 8
(per-book `single_line_max_h_p90`, quyển nào không đủ mẫu), số dòng ước lượng
Task 9, kết quả `pytest tests/ -q` (Step 1), và rõ ràng "CHƯA chạy ETL 12 quyển
thật — việc đó cần Colab GPU, thuộc phiên khác".

Chạy: `python -m pytest tests/test_decision_log.py -q` sau khi sửa — PHẢI pass
trước khi đi tiếp (bài học D-136: một chuỗi JS xuống dòng giữa chừng làm hỏng
cả trang mà không lỗi cú pháp Python nào bắt được).

- [ ] **Step 3: Cập nhật CLAUDE.md**

- Đổi dòng bảng tiến độ MT1 (`Xử lý công thức Hoá/Lý (MT1)`) từ "BƯỚC 1/3" sang
  "BƯỚC 2+3/3 — CODE XONG, CHƯA CHẠY ETL THẬT" kèm entry decision log mới.
- Cập nhật bullet D-56 (gạch đầu dòng dài trong "Active redesign") — thêm đoạn
  mô tả code đã có (`formula_merge.py`, `formula_ocr.py`, `ocr_lines.py`, wiring
  vào `text_extract.py`/`chunker.py`/`loader.py`), và nói rõ **việc còn lại chỉ
  là chạy trên Colab** (không còn là "chưa có detector nào").
- Cập nhật dòng test suite count (`pytest tests/ -q` → số mới từ Task 11 Step 1).
- Cập nhật `TEXT_EXTRACTION_VERSION` nếu CLAUDE.md có nhắc giá trị cũ
  (`v2_bai_spine`) ở đâu đó — grep trước khi sửa:
  `grep -n "v2_bai_spine\|TEXT_EXTRACTION_VERSION" CLAUDE.md`

- [ ] **Step 4: Cập nhật memory**

Sửa `C:\Users\lcdkhoa\.claude\projects\D--personal-repo-project-rag\memory\ocr_bakeoff.md`
— mục "Việc còn lại, CẦN Colab GPU" đổi thành: code Bước 2/3 đã viết xong và
test (mock client) đầy đủ; việc còn lại CHỈ là chạy `document/colab_runtime_etl.ipynb`
đã vá trên Colab thật, không còn việc viết code nào nữa. Cập nhật dòng
`description` trong frontmatter cho khớp. Cập nhật dòng tương ứng trong
`MEMORY.md`.

- [ ] **Step 5: Đánh dấu trạng thái trong spec thiết kế**

Thêm vào cuối `document/specs/2026-08-27-formula-ocr-hybrid-buoc23-design.md`
một mục `## Trạng thái implement (ngày chạy Task 11)`:
liệt kê Task 1–10 đã XONG + đường dẫn commit tương ứng (`git log --oneline`
lấy 10 commit gần nhất của plan này), và nói rõ việc DUY NHẤT còn lại là chạy
Colab.

- [ ] **Step 6: Commit cuối**

```bash
git add document/decision_log.html CLAUDE.md
git commit -m "docs: tong ket Buoc 2/3 hybrid MinerU - code xong, cho chay Colab"
```

(Memory không nằm trong git của repo này — sửa trực tiếp, không cần commit ở
bước này.)

---

## Self-review (đã chạy khi viết plan này)

- **Phủ hết thiết kế:** §1(Task 5 nguyên tắc không đụng đường chính) · §2(Task 5) ·
  §3(Task 2) · §4(Task 3) · §5(Task 4+6) · §6a(Task 7) · §6b(Task 8) · §7(Task 9) ·
  §8(Task 9) · §9(Task 10) · §10(rải trong từng Task) · §11(Global Constraints).
- **Không placeholder ẩn:** `MIN_SAT_FLOOR = 45` ở Task 7 Step 3 là placeholder
  CỐ Ý, có dòng CẢNH BÁO executor phải thay bằng số đo thật — không phải placeholder
  bị bỏ sót.
- **Tên hàm/kiểu nhất quán xuyên task:** `formula_client` (Task 5/6),
  `formula_hybrid_status: List[str]` (Task 4/5/6), `MergeOutcome` (Task 2/5),
  `book` param tên giống nhau ở `segment_page`/`_params_for` (Task 7) — đã kiểm
  khớp qua các Task.
