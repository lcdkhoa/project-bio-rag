"""Classical-CV page layout segmentation: colored boxes + main text column."""
import cv2
import numpy as np
from .regions import Region, RegionType, BBox
from ...config import LAYOUT_BOX_MIN_SATURATION, LAYOUT_BOX_MIN_AREA_FRAC

# Per-variant layout params. Identical across publishers for now; Task 10
# (real-page QA) calibrates any divergence. Threading `variant` here makes the
# parameter live and gives per-variant tuning one home.
_VARIANT_PARAMS = {
    "cd":   {"min_sat": LAYOUT_BOX_MIN_SATURATION, "min_area_frac": LAYOUT_BOX_MIN_AREA_FRAC, "close_kernel": 25},
    "ctst": {"min_sat": LAYOUT_BOX_MIN_SATURATION, "min_area_frac": LAYOUT_BOX_MIN_AREA_FRAC, "close_kernel": 25},
    "kntt": {"min_sat": LAYOUT_BOX_MIN_SATURATION, "min_area_frac": LAYOUT_BOX_MIN_AREA_FRAC, "close_kernel": 25},
}


def _params_for(variant: str) -> dict:
    return _VARIANT_PARAMS.get(variant, _VARIANT_PARAMS["cd"])


def _colored_boxes(image: np.ndarray, min_sat: int, min_area_frac: float,
                    close_kernel: int = 25) -> list[BBox]:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    mask = (sat >= min_sat).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((close_kernel, close_kernel), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = image.shape[:2]
    min_area = min_area_frac * h * w
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
    params = _params_for(variant)
    boxes = _colored_boxes(image, params["min_sat"], params["min_area_frac"],
                            params.get("close_kernel", 25))
    regions: list[Region] = []
    # Main body = the whole page minus box columns; first in reading order.
    regions.append(Region(RegionType.BODY, (0, 0, w, h), reading_order=0,
                          meta={"excludes": boxes}))
    for i, b in enumerate(sorted(boxes, key=lambda z: (z[1], z[0]))):
        regions.append(Region(_classify_box(b, w), b, reading_order=i + 1, meta={}))
    return regions
