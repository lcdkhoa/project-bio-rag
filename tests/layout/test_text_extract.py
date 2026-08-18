import numpy as np, cv2
from src.etl.layout.segmenter import segment_page
from src.etl.layout.text_extract import extract_text_units
from src.etl.layout.regions import RegionType

def _page():
    img = np.full((1000, 800, 3), 255, np.uint8)
    cv2.putText(img, "quang hop la qua trinh", (40, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0,0,0), 2)
    cv2.rectangle(img, (560, 120), (770, 480), (120, 200, 120), -1)
    cv2.putText(img, "cau hoi", (580, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0,0,0), 2)
    return img

def test_body_text_excludes_sidebar():
    img = _page()
    regs = segment_page(img, "ctst")
    units = extract_text_units(img, regs, "ctst")
    body = " ".join(u.text for u in units if u.region_type == RegionType.BODY).lower()
    assert "quang hop" in body.replace("  ", " ") or "quang" in body
    assert "cau hoi" not in body   # sidebar text must NOT leak into body

def test_units_sorted_by_reading_order():
    img = _page()
    regs = segment_page(img, "ctst")
    units = extract_text_units(img, regs, "ctst")
    assert [u.reading_order for u in units] == sorted(u.reading_order for u in units)
