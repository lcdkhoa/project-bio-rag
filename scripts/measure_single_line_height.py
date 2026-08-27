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
HARD_CAP_MAX = 85  # Tran an toan: 2 dong chu SGK co chieu cao ~85-90px, khong the dat single-line > 85px


def get_lines_info(crop) -> list[dict]:
    """Tra ve danh sach cac dong tim duoc trong crop va chieu cao tung dong."""
    if crop.size == 0:
        return []
    data = pytesseract.image_to_data(crop, lang="vie", config="--psm 6",
                                      output_type=pytesseract.Output.DICT)
    theo_dong = {}
    for i in range(len(data["text"])):
        text = str(data["text"][i]).strip()
        if not text:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        if key not in theo_dong:
            theo_dong[key] = []
        theo_dong[key].append({
            "top": data["top"][i],
            "height": data["height"][i],
            "text": text,
        })
    
    lines = []
    for key, ws in theo_dong.items():
        y0 = min(w["top"] for w in ws)
        y1 = max(w["top"] + w["height"] for w in ws)
        lines.append({
            "top": y0,
            "bottom": y1,
            "height": y1 - y0,
            "text": " ".join(w["text"] for w in ws),
        })
    return lines


for book in BOOKS:
    fp_path = FINGERPRINT_DIR / f"{book}.json"
    fp = json.loads(fp_path.read_text(encoding="utf-8"))
    pages = fp["box_palette"]["pages_probed"]
    variant = "kntt" if "KNTT" in book else ("ctst" if "CTST" in book else "cd")
    source = find_page_source(DATA_DIR, book)
    heights = []
    for pn in pages:
        img = source.load(pn)
        for r in segment_page(img, variant, book=book):
            if r.type in (RegionType.FIGURE, RegionType.PAGE_ARTIFACT, RegionType.BODY):
                continue
            x0, y0, x1, y1 = r.bbox
            h = y1 - y0
            if h <= 0 or h > 400:
                continue
            crop = img[y0:y1, x0:x1]
            lines = get_lines_info(crop)
            # Chi lay crop neu chua dung 1 dong chu va chieu cao hop li cho 1 dong
            if len(lines) == 1:
                line_h = lines[0]["height"]
                # Box cao khong qua 2.5 lan line_h va <= HARD_CAP_MAX
                if line_h >= 15 and h <= min(HARD_CAP_MAX, int(2.5 * line_h)):
                    heights.append(h)
    arr = np.array(heights)
    if len(arr) >= 5:
        p90 = float(np.percentile(arr, 90))
        chosen = max(CURRENT_DEFAULT, min(HARD_CAP_MAX, round(p90)))
        fp.setdefault("text_layout", {})["single_line_max_h_p90"] = chosen
        fp["text_layout"]["single_line_max_h_n_samples"] = len(arr)
        print(f"{book:16s} n={len(arr):3d} p90={p90:6.1f} -> ghi {chosen}", flush=True)
    else:
        print(f"{book:16s} n={len(arr):3d} < 5 mau -> KHONG du tin cay, "
              f"GIU {CURRENT_DEFAULT} (khong ghi key moi)", flush=True)
        continue
    fp_path.write_text(json.dumps(fp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
