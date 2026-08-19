"""Bridge: reconcile anchor-first figure regions against the layout segmenter.

The per-variant detector in image_processor.py stays the source of figure
regions (all v7-v15 logic intact). This bridge only *removes* figure regions
that the segmenter shows are actually a coloured sidebar/info box — a
conservative, drop-only reconciliation. It never clips or grows a figure, so a
radial figure whose coloured icons might trip the box detector is protected by
a high containment threshold (a real figure is not ~entirely inside one box).

Only FIGURE-typed regions are drop candidates: the detector also emits
textbook_info_box / activity_box / tool_group regions that ARE coloured boxes
by design and must never be dropped.
"""
import logging
from typing import List

import cv2
import numpy as np

from .regions import Region, RegionType
from .segmenter import segment_page
from ...config import FIGURE_IN_BOX_DROP_RATIO

logger = logging.getLogger(__name__)

_BOX_TYPES = (RegionType.SIDEBAR, RegionType.INFO_BOX)
_FIGURE_TYPES = {"single_figure", "composite_figure", "sub_figure", "panel", "figure"}


def _containment(fig_bbox, box_bbox) -> float:
    """Fraction of the FIGURE's area that lies inside box_bbox (0..1)."""
    fx0, fy0, fx1, fy1 = fig_bbox
    bx0, by0, bx1, by1 = box_bbox
    fig_area = max(0, fx1 - fx0) * max(0, fy1 - fy0)
    if fig_area <= 0:
        return 0.0
    ix0, iy0 = max(fx0, bx0), max(fy0, by0)
    ix1, iy1 = min(fx1, bx1), min(fy1, by1)
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    return inter / fig_area


def reconcile_with_layout(regions: List[dict], image_rgb: np.ndarray, variant: str) -> List[dict]:
    """Drop figure-type regions sitting ~entirely inside a segmenter colour box.

    ``image_rgb`` is the detector's own page array (poppler, RGB); segment_page
    is fed the BGR view of that very array so the boxes share the SAME
    coordinate space as ``regions`` (no re-render). Fail-open: any segmentation
    error keeps all regions.
    """
    if not regions:
        return regions
    try:
        image_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
        layout = segment_page(image_bgr, variant)
    except Exception as e:
        logger.warning("reconcile_with_layout: segmentation failed (%s); keeping all regions", e)
        return regions
    boxes = [r.bbox for r in layout if r.type in _BOX_TYPES]
    if not boxes:
        return regions

    kept: List[dict] = []
    for region in regions:
        image_type = str(region.get("image_type", "")).lower()
        bbox = tuple(region["bbox"])
        if image_type in _FIGURE_TYPES and any(
            _containment(bbox, box) >= FIGURE_IN_BOX_DROP_RATIO for box in boxes
        ):
            logger.info("reconcile: drop %s figure %s inside colour box", image_type, bbox)
            continue
        kept.append(region)
    return kept


def to_layout_regions(regions: List[dict]) -> List[Region]:
    """Represent detector regions as layout Region objects for the QA overlay.

    Figure types -> RegionType.FIGURE; everything else (info/activity/tool) ->
    RegionType.INFO_BOX. The original label is carried in meta["image_type"].
    """
    out: List[Region] = []
    for i, region in enumerate(regions):
        image_type = str(region.get("image_type", "")).lower()
        rtype = RegionType.FIGURE if image_type in _FIGURE_TYPES else RegionType.INFO_BOX
        out.append(Region(rtype, tuple(region["bbox"]), reading_order=i,
                          meta={"image_type": image_type}))
    return out
