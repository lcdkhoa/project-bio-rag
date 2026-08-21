"""Visual QA tool: vẽ các vùng layout đã phân đoạn lên một trang SGK thật.

Đây là công cụ QA bằng mắt cho đường ETL layout-aware. Nó nạp đúng trang PNG mà
pipeline thật nạp (không render, không preprocess — xem `LayoutOCRLoader`), chạy
`segment_page`, rồi vẽ bbox từng `Region` theo màu của `RegionType` kèm chú giải
và lưu PNG để soi. Công cụ này KHÔNG tự khẳng định gì về tính đúng — xem
`tests/layout/test_qa_layout.py` cho smoke test, còn tín hiệu QA thật là mắt
người trên file PNG đã lưu.

Kèm theo: `--report` in số vùng tìm được theo loại, để đo recall của segmenter
trên nhiều trang (2,30 vùng/trang là con số đo được và là điểm yếu số một).

CLI:
    python -m src.test.qa_layout --book SGK_KHTN_6_KNTT --page 10
    python -m src.test.qa_layout --book SGK_KHTN_6_KNTT --pages 10,11,25 --out-dir report/layout_qa
"""
import argparse
import os
from pathlib import Path

import cv2
import numpy as np

from ..etl.layout.segmenter import segment_page
from ..etl.layout.regions import RegionType
from ..etl.image_processor import get_pdf_variant
from ..etl.page_source import find_page_source
from ..config import DATA_DIR

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# BGR tuples (cv2 convention): body=blue, sidebar=green, info_box=orange,
# figure=red, caption=purple, page_artifact=gray.
_REGION_COLORS = {
    RegionType.BODY: (255, 0, 0),
    RegionType.SIDEBAR: (0, 200, 0),
    RegionType.INFO_BOX: (0, 165, 255),
    RegionType.FIGURE: (0, 0, 255),
    RegionType.CAPTION: (200, 0, 200),
    RegionType.PAGE_ARTIFACT: (128, 128, 128),
}
_DEFAULT_COLOR = (0, 0, 0)  # fallback for any region type not in the map above


def _draw_legend(image: np.ndarray) -> None:
    """Draw a small color-key legend in the page's top-left corner, in place."""
    entries = list(_REGION_COLORS.items())
    pad, swatch, line_h = 8, 16, 22
    box_w, box_h = 150, pad * 2 + line_h * len(entries)
    cv2.rectangle(image, (0, 0), (box_w, box_h), (255, 255, 255), -1)
    cv2.rectangle(image, (0, 0), (box_w, box_h), (0, 0, 0), 1)
    x, y = pad, pad
    for region_type, color in entries:
        cv2.rectangle(image, (x, y), (x + swatch, y + swatch), color, -1)
        cv2.putText(image, region_type.value, (x + swatch + 6, y + swatch - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
        y += line_h


def render_layout_overlay(book: str, page_number: int, out_dir: str,
                          data_dir=None) -> str:
    """Nạp một trang nguồn, phân đoạn, vẽ bbox từng vùng theo loại.

    `page_number` là SỐ TRANG NGUỒN (số trong tên file `page_NNN.png`), giống
    hệ toạ độ của cả ETL. Lưu PNG "<book>_p<page_number>_layout.png" vào
    `out_dir` và trả về đường dẫn.
    """
    source = find_page_source(data_dir or DATA_DIR, book)
    variant = get_pdf_variant(source.name)
    img = source.load(page_number)
    regions = segment_page(img, variant)

    overlay = img.copy()
    for region in regions:
        color = _REGION_COLORS.get(region.type, _DEFAULT_COLOR)
        x0, y0, x1, y1 = region.bbox
        cv2.rectangle(overlay, (x0, y0), (x1, y1), color, 3)

    _draw_legend(overlay)

    os.makedirs(out_dir, exist_ok=True)
    stem = source.name.replace(" ", "_")
    out_path = os.path.join(out_dir, f"{stem}_p{page_number}_layout.png")
    cv2.imwrite(out_path, overlay)
    return out_path


def region_counts(book: str, page_numbers, data_dir=None) -> dict:
    """{số trang: {loại vùng: số lượng}} — để đo recall của segmenter."""
    source = find_page_source(data_dir or DATA_DIR, book)
    variant = get_pdf_variant(source.name)
    out = {}
    for page_number in page_numbers:
        regions = segment_page(source.load(page_number), variant)
        counts: dict = {}
        for region in regions:
            counts[region.type.value] = counts.get(region.type.value, 0) + 1
        out[page_number] = counts
    return out


def _parse_pages(args) -> list:
    if args.pages:
        return [int(p) for p in args.pages.split(",") if p.strip()]
    return [args.page]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", required=True,
                        help="Tên thư mục quyển trong datasources/ (vd SGK_KHTN_6_KNTT)")
    parser.add_argument("--page", type=int, default=10,
                        help="SỐ TRANG NGUỒN (số trong tên file page_NNN.png)")
    parser.add_argument("--pages", default="",
                        help="Danh sách số trang, cách nhau bằng dấu phẩy")
    parser.add_argument("--out-dir", default=str(PROJECT_ROOT / "report" / "layout_qa"))
    parser.add_argument("--report", action="store_true",
                        help="Chỉ in số vùng theo loại, không vẽ overlay")
    args = parser.parse_args()

    pages = _parse_pages(args)
    if args.report:
        counts = region_counts(args.book, pages)
        total = 0
        for page_number, per_type in counts.items():
            n = sum(per_type.values())
            total += n
            print(f"trang {page_number}: {n} vùng {per_type}")
        print(f"trung bình {total / max(1, len(counts)):.2f} vùng/trang "
              f"trên {len(counts)} trang")
        return 0

    for page_number in pages:
        out = render_layout_overlay(args.book, page_number, args.out_dir)
        print(f"[OK] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
