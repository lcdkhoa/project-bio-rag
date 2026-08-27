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
