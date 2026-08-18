"""Data model for layout-aware ETL: page regions and extracted text units."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple, Dict

class RegionType(str, Enum):
    BODY = "body"
    SIDEBAR = "sidebar"
    INFO_BOX = "info_box"
    FIGURE = "figure"
    CAPTION = "caption"
    PAGE_ARTIFACT = "page_artifact"

BBox = Tuple[int, int, int, int]  # (x0, y0, x1, y1) in rendered-page pixels

@dataclass
class Region:
    type: RegionType
    bbox: BBox
    reading_order: int
    meta: Dict = field(default_factory=dict)

@dataclass
class TextUnit:
    region_type: RegionType
    text: str
    reading_order: int
    bbox: BBox
