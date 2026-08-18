"""Classical-CV page layout segmentation: colored boxes + main text column.

Colored sidebar/info boxes are found by an HSV mask (strongly-saturated fills
AND pale bright tints), then filtered so only regions with a *uniform, genuinely
tinted* background survive. That filter is what separates a real coloured box
from a figure/photo sitting on white (which is uniform but not tinted) — the
failure mode surfaced by real-page QA on CTST/KNTT (pale sidebars were missed,
colourful photos were wrongly boxed).
"""
import cv2
import numpy as np
from .regions import Region, RegionType, BBox
from ...config import LAYOUT_BOX_MIN_SATURATION, LAYOUT_BOX_MIN_AREA_FRAC

# Per-variant layout params. Identical across publishers for now; real-page QA
# calibrates any divergence. Threading `variant` here makes the parameter live
# and gives per-variant tuning one home.
_BOX_DEFAULTS = {
    "min_sat": LAYOUT_BOX_MIN_SATURATION,       # HSV saturation of a strongly-coloured fill
    "min_area_frac": LAYOUT_BOX_MIN_AREA_FRAC,  # min box area as a fraction of the page
    "close_kernel": 25,                         # morphology-close kernel (px)
    "pale_sat_min": 12,                         # lower sat bound for a PALE tint fill
    "pale_val_min": 200,                        # min brightness for a pale tint (excludes dark text)
    "uniform_min": 0.45,                        # min fraction of the region near its median colour
    "tint_white_max": 232,                      # median this bright (all channels) => white => reject
    "tint_min_spread": 10,                      # median max-min channel spread => a real colour tint
    "uniform_tol": 40,                          # per-pixel L1 distance from median counted as "background"
}
_VARIANT_PARAMS = {v: dict(_BOX_DEFAULTS) for v in ("cd", "ctst", "kntt")}


def _params_for(variant: str) -> dict:
    return _VARIANT_PARAMS.get(variant, _VARIANT_PARAMS["cd"])


def _candidate_mask(image: np.ndarray, p: dict) -> np.ndarray:
    """Pixels belonging to a coloured box: strongly saturated OR a pale bright tint."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    s, v = hsv[:, :, 1], hsv[:, :, 2]
    strong = s >= p["min_sat"]
    pale = (s >= p["pale_sat_min"]) & (s < p["min_sat"]) & (v >= p["pale_val_min"])
    return ((strong | pale).astype(np.uint8)) * 255


def _is_box(roi: np.ndarray, p: dict) -> bool:
    """True if `roi` looks like a coloured box, not a figure/photo.

    A box has a UNIFORM background (most pixels near one colour) that is a real
    TINT (not white / near-white / gray). A figure on white is uniform but its
    background median is white; a photo is tinted but not uniform. Requiring both
    rejects each.
    """
    flat = roi.reshape(-1, 3).astype(np.int16)
    med = np.median(flat, axis=0)
    uniform = float((np.abs(flat - med).sum(axis=1) < p["uniform_tol"]).mean())
    if uniform < p["uniform_min"]:
        return False
    near_white = int(med.min()) >= p["tint_white_max"]
    spread = int(med.max() - med.min())
    return (not near_white) and spread >= p["tint_min_spread"]


def _colored_boxes(image: np.ndarray, p: dict) -> list[BBox]:
    mask = _candidate_mask(image, p)
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE, np.ones((p["close_kernel"], p["close_kernel"]), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = image.shape[:2]
    min_area = p["min_area_frac"] * h * w
    boxes = []
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw * bh >= min_area and bw > 0.08 * w and bh > 0.05 * h:
            if _is_box(image[y:y + bh, x:x + bw], p):
                boxes.append((x, y, x + bw, y + bh))
    return boxes


def _classify_box(bbox: BBox, image_w: int) -> RegionType:
    # Right-column tall box => sidebar; wide banner box => info_box.
    x0, y0, x1, y1 = bbox
    width_frac = (x1 - x0) / image_w
    return RegionType.INFO_BOX if width_frac > 0.5 else RegionType.SIDEBAR


def segment_page(image: np.ndarray, variant: str) -> list[Region]:
    h, w = image.shape[:2]
    boxes = _colored_boxes(image, _params_for(variant))
    regions: list[Region] = []
    # Main body = the whole page minus box columns; first in reading order.
    regions.append(Region(RegionType.BODY, (0, 0, w, h), reading_order=0,
                          meta={"excludes": boxes}))
    for i, b in enumerate(sorted(boxes, key=lambda z: (z[1], z[0]))):
        regions.append(Region(_classify_box(b, w), b, reading_order=i + 1, meta={}))
    return regions
