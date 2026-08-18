"""Classical-CV page layout segmentation: colored boxes + main text column."""
import cv2
import numpy as np
from .regions import Region, RegionType, BBox
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
