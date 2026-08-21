"""Cổng G4 — hình có ĐỦ và có gán ĐÚNG Bài hay không.

## Vì sao đo được mà không cần người dán nhãn từng trang

Số hiệu hình trong SGK **tự mang thông tin kiểm chứng**: `Hình A.B` nghĩa là hình
thứ B của **Bài A**. Ghép với spine Bài đã liền mạch (D-43) ta có hai phép thử
không cần ground truth do người gõ tay:

1. **Gán đúng Bài** — mọi crop mang nhãn `Hình A.B` tìm thấy trên một trang thuộc
   Bài X phải có `A == X`. Lệch là gán sai, đếm được chính xác.
2. **Đủ hình** — với mỗi Bài, tập B thu được phải là `1..max(B)` liền mạch. Thiếu
   một số ở giữa là **bằng chứng** một hình bị bỏ sót, không phải phỏng đoán.
3. **Không cắt lấn chữ** — một crop hình thật gần như không có chữ ngoài dòng
   chú thích. Đo `text_line_coverage` của chính crop: hình thật ở corpus này đo
   được **0,00–0,10**, còn một crop nuốt cả đoạn văn/bảng lên tới **0,22+**.
   Ngưỡng cảnh báo đặt ở **0,20** và diện tích **> 40% trang**; cả hai chỉ là
   CỜ để người xem, không tự xoá vùng nào.

Phép (2) chỉ cho **cận dưới** của số hình bỏ sót: nếu hình cuối cùng của một Bài
bị bỏ sót thì `max(B)` tụt xuống và không ai biết. Vì vậy script in cả hai con
số và nói rõ nó là cận dưới — không được báo cáo như tỉ lệ đầy đủ tuyệt đối.

## Cách chạy

    python -m src.test.qa_figures --book SGK_KHTN_6_KNTT --bai 1,2,3
    python -m src.test.qa_figures --book SGK_KHTN_6_KNTT --pages 8,9,10,11
    python -m src.test.qa_figures --all-books --bai-per-book 3

Script KHÔNG ghi vào ChromaDB và KHÔNG gọi captioner — chạy lại bao nhiêu lần
cũng được.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path

try:  # xem chú thích trong test_image_extraction_full.py
    import pyarrow  # noqa: F401
except Exception:
    pass

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import DATA_DIR, MANIFEST_DIR  # noqa: E402
from src.etl.book.manifest import book_id_from_source_name, load_manifest  # noqa: E402
from src.etl.image_processor import make_image_processor  # noqa: E402
from src.etl.page_source import discover_page_sources  # noqa: E402

logging.basicConfig(level=logging.WARNING,
                    format="%(levelname)-7s | %(name)s | %(message)s")
logger = logging.getLogger("qa_figures")

FIGURE_LABEL = re.compile(r"H[iìíỉĩị]nh\s*(\d{1,2})\s*[.,]\s*(\d{1,2})")


def figure_number(text: str):
    """`"Hình 21.3 Sơ đồ …"` -> `(21, 3)`; không khớp -> None."""
    match = FIGURE_LABEL.search(str(text or ""))
    return (int(match.group(1)), int(match.group(2))) if match else None


AREA_FLAG = 0.40          # crop chiếm > 40% trang -> nghi cắt lấn
TEXT_FLAG = 0.20          # crop có > 20% diện tích là chữ -> nghi nuốt văn bản


def page_regions(processor, source, page_number: int):
    """(vùng, chiều rộng, chiều cao, text_lines) — không crop, không index."""
    bgr = source.load(page_number)
    pil_img = Image.fromarray(bgr[:, :, ::-1]).convert("RGB")
    img_array = np.array(pil_img)
    text_lines = processor._collect_page_text_lines(pil_img)
    detection = processor.detect_regions_anchor_first(
        pil_img, img_array, text_lines=text_lines)
    width, height = pil_img.size
    return list(detection["regions"]), width, height, text_lines


def scan(source, manifest, pages: list) -> dict:
    processor = make_image_processor(source.name)
    bai_of_page = {int(p["page_index"]): p.get("bai_so")
                   for p in manifest.pages}
    found = defaultdict(set)          # bai_so -> {số thứ tự hình}
    misassigned, unlabelled, rows = [], 0, []
    oversized, crop_stats = [], []
    for page in pages:
        page_bai = bai_of_page.get(page)
        try:
            regions, width, height, text_lines = page_regions(
                processor, source, page)
        except Exception as exc:                      # noqa: BLE001
            logger.warning("trang %s lỗi: %s", page, exc)
            continue
        page_area = float(max(1, width * height))
        for region in regions:
            bbox = tuple(int(v) for v in region.get("bbox", (0, 0, 0, 0)))
            area_frac = ((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) / page_area
            text_cov = processor._text_line_coverage(bbox, text_lines)
            if area_frac > AREA_FLAG or text_cov > TEXT_FLAG:
                oversized.append({"page": page, "bbox": list(bbox),
                                  "area_frac": round(area_frac, 3),
                                  "text_cov": round(text_cov, 3),
                                  "image_type": region.get("image_type"),
                                  "label": str(region.get("caption_text", ""))[:24]})
            crop_stats.append((round(area_frac, 3), round(text_cov, 3)))
            number = figure_number(region.get("caption_text", ""))
            if number is None:
                unlabelled += 1
                rows.append({"page": page, "bai": page_bai, "label": None,
                             "image_type": region.get("image_type"),
                             "bbox": list(region.get("bbox", []))})
                continue
            bai, index = number
            found[bai].add(index)
            rows.append({"page": page, "bai": page_bai,
                         "label": f"Hình {bai}.{index}",
                         "image_type": region.get("image_type"),
                         "bbox": list(region.get("bbox", []))})
            if page_bai is not None and bai != page_bai:
                misassigned.append(
                    {"page": page, "page_bai": page_bai,
                     "label": f"Hình {bai}.{index}"})
    gaps = {}
    for bai, indices in found.items():
        missing = [n for n in range(1, max(indices) + 1) if n not in indices]
        if missing:
            gaps[bai] = missing
    return {"found": {b: sorted(v) for b, v in sorted(found.items())},
            "gaps": gaps, "misassigned": misassigned,
            "unlabelled": unlabelled, "rows": rows,
            "oversized": oversized, "crop_stats": crop_stats,
            "pages_scanned": len(pages)}


def pages_for_bai(manifest, bai_numbers: list) -> list:
    wanted = set(bai_numbers)
    return [int(p["page_index"]) for p in manifest.pages
            if p.get("bai_so") in wanted]


def report(book: str, result: dict) -> str:
    found = result["found"]
    total = sum(len(v) for v in found.values())
    missing = sum(len(v) for v in result["gaps"].values())
    lines = [f"\n=== G4 {book}",
             f"  hình có nhãn đọc được : {total}",
             f"  hình KHÔNG có nhãn    : {result['unlabelled']}",
             f"  gán SAI Bài           : {len(result['misassigned'])}",
             f"  thiếu (cận dưới)      : {missing}",
             f"  crop nghi cắt lấn     : {len(result['oversized'])}"
             f" / {len(result['crop_stats'])} crop"]
    for bai, indices in found.items():
        gap = result["gaps"].get(bai)
        mark = f"   THIẾU {gap}" if gap else ""
        lines.append(f"    Bài {bai:2d}: {indices}{mark}")
    for item in result["misassigned"]:
        lines.append(f"    SAI BÀI: {item['label']} nằm ở trang "
                     f"{item['page']} (Bài {item['page_bai']})")
    for item in result["oversized"]:
        lines.append(f"    CẮT LẤN: trang {item['page']} {item['label']!r} "
                     f"{item['image_type']} dt={item['area_frac']} "
                     f"chữ={item['text_cov']} bbox={item['bbox']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", default="SGK_KHTN_6_KNTT")
    parser.add_argument("--all-books", action="store_true")
    parser.add_argument("--bai", default="", help="danh sách số Bài, ví dụ 1,2,3")
    parser.add_argument("--bai-per-book", type=int, default=3)
    parser.add_argument("--pages", default="", help="danh sách trang nguồn")
    parser.add_argument("--out", type=Path, default=None, help="ghi JSON kết quả")
    args = parser.parse_args()

    sources = {s.name: s for s in discover_page_sources(DATA_DIR)}
    books = sorted(sources) if args.all_books else [args.book]
    payload, text = {}, []
    for book in books:
        source = sources.get(book)
        if source is None:
            print(f"[ERR] không có quyển {book!r}; có: {sorted(sources)}")
            return 1
        manifest = load_manifest(
            Path(MANIFEST_DIR) / f"{book_id_from_source_name(book)}.json")
        if args.pages:
            pages = [int(x) for x in args.pages.split(",") if x.strip()]
        else:
            numbers = ([int(x) for x in args.bai.split(",") if x.strip()]
                       if args.bai else
                       sorted({p["bai_so"] for p in manifest.pages
                               if p.get("bai_so")})[:args.bai_per_book])
            pages = pages_for_bai(manifest, numbers)
        result = scan(source, manifest, pages)
        payload[book] = result
        text.append(report(book, result))
        print(report(book, result), flush=True)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                            encoding="utf-8")
        print(f"\n[OK] JSON -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
