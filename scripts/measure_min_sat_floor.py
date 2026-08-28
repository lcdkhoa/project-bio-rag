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
# D-146: 45/35/30/25/20/15 da do xong tren 11/12 quyen (thieu 9_CD) o luot truoc -
# giu 15 lam cau noi doi chieu, chi quet them dai THAP (14..9) dang dung that
# (MIN_SAT_FLOOR=9) de khong phai chay lai tu dau.
CANDIDATE_FLOORS = [15, 14, 12, 10, 9]

for book in BOOKS:
    fp_path = FINGERPRINT_DIR / f"{book}.json"
    fp = json.loads(fp_path.read_text(encoding="utf-8"))
    p10 = fp["box_palette"]["sat_percentiles"]["p10"]
    pages = fp["box_palette"]["pages_probed"][:6]  # 6 trang - giam de chay het 12/12
    source = find_page_source(DATA_DIR, book)
    images = [source.load(pn) for pn in pages]
    row = [f"{book:16s} p10={p10:6.1f}"]
    for floor in CANDIDATE_FLOORS:
        min_sat = max(floor, round(p10))
        params = dict(_BOX_DEFAULTS)
        params["min_sat"] = min_sat
        total = sum(len(_colored_boxes(img, params)) for img in images)
        row.append(f"floor{floor}(sat={min_sat})={total}")
    print("  ".join(row), flush=True)
