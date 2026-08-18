"""Visual QA tool: overlay segmented layout regions on a rendered SGK page.

Manual QA aid for the M1 layout-aware ETL. Renders one PDF page the same way
the real pipeline does (`_render_page` -> `preprocess_page` -> `segment_page`),
then draws each `Region`'s bbox colored by `RegionType` with a small legend
and saves a PNG for eyeballing segmentation quality. This tool makes no
correctness assertions itself -- see tests/layout/test_qa_layout.py for the
smoke test, and eyeball the saved PNG for the actual QA signal.

CLI:
    python -m src.test.qa_layout --pdf "SGK KHTN 7 CTST.pdf" --page 40
    python -m src.test.qa_layout --pdf "datasources/SGK KHTN 7 CTST.pdf" --page 40 --out-dir report/layout_qa
"""
import argparse
import os
from pathlib import Path

import cv2
import numpy as np

from ..etl.layout.loader import _render_page
from ..etl.layout.preprocess import preprocess_page
from ..etl.layout.segmenter import segment_page
from ..etl.layout.regions import RegionType
from ..etl.image_processor import get_pdf_variant
from ..config import RENDER_DPI

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASOURCES_DIR = PROJECT_ROOT / "datasources"

# BGR tuples (cv2 convention). Per the task brief: body=blue, sidebar=green,
# info_box=orange, figure=red, caption=purple, page_artifact=gray.
_REGION_COLORS = {
    RegionType.BODY: (255, 0, 0),
    RegionType.SIDEBAR: (0, 200, 0),
    RegionType.INFO_BOX: (0, 165, 255),
    RegionType.FIGURE: (0, 0, 255),
    RegionType.CAPTION: (200, 0, 200),
    RegionType.PAGE_ARTIFACT: (128, 128, 128),
}
_DEFAULT_COLOR = (0, 0, 0)  # fallback for any region type not in the map above


def _resolve_pdf_path(pdf_name: str) -> str:
    """Accept either a bare filename (resolved under datasources/) or a full path."""
    p = Path(pdf_name)
    if p.is_file():
        return str(p)
    return str(DEFAULT_DATASOURCES_DIR / pdf_name)


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


def render_layout_overlay(pdf_name: str, page_index: int, out_dir: str) -> str:
    """Render one page, segment it, and draw each region's bbox colored by type.

    Mirrors `LayoutOCRLoader.load_page`'s render/preprocess/segment steps so the
    overlay reflects exactly what the real ETL pipeline sees. Saves a PNG named
    "<pdf-stem>_p<page_index>_layout.png" into out_dir (created if missing) and
    returns its path.
    """
    pdf_path = _resolve_pdf_path(pdf_name)
    variant = get_pdf_variant(Path(pdf_path).name)
    img = _render_page(pdf_path, page_index, RENDER_DPI)
    img = preprocess_page(img, variant)
    regions = segment_page(img, variant)

    overlay = img.copy()
    for region in regions:
        color = _REGION_COLORS.get(region.type, _DEFAULT_COLOR)
        x0, y0, x1, y1 = region.bbox
        cv2.rectangle(overlay, (x0, y0), (x1, y1), color, 3)

    _draw_legend(overlay)

    os.makedirs(out_dir, exist_ok=True)
    stem = Path(pdf_path).stem.replace(" ", "_")
    out_path = os.path.join(out_dir, f"{stem}_p{page_index}_layout.png")
    cv2.imwrite(out_path, overlay)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True,
                         help="PDF filename (looked up under datasources/) or a full path")
    parser.add_argument("--page", type=int, required=True, help="0-based page index")
    parser.add_argument("--out-dir", default=str(PROJECT_ROOT / "report" / "layout_qa"))
    args = parser.parse_args()
    out = render_layout_overlay(args.pdf, args.page, args.out_dir)
    print(f"[OK] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
