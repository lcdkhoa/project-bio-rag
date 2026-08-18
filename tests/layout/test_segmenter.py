import numpy as np, cv2
from src.etl.layout.segmenter import segment_page
from src.etl.layout.regions import RegionType

def _synthetic_page():
    img = np.full((1000, 800, 3), 255, np.uint8)
    # main text: black lines on left 60% of width
    for y in range(120, 700, 40):
        cv2.putText(img, "dòng văn bản chính của bài học", (40, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 2)
    # colored sidebar box on right (green fill) with text
    cv2.rectangle(img, (560, 120), (770, 480), (120, 200, 120), -1)
    cv2.putText(img, "cau hoi 5", (580, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 2)
    return img

def test_detects_one_colored_box_and_main_text():
    regs = segment_page(_synthetic_page(), "ctst")
    types = [r.type for r in regs]
    assert RegionType.SIDEBAR in types or RegionType.INFO_BOX in types
    assert RegionType.BODY in types
    # main body reads before the sidebar box
    body = next(r for r in regs if r.type == RegionType.BODY)
    box = next(r for r in regs if r.type in (RegionType.SIDEBAR, RegionType.INFO_BOX))
    assert body.reading_order < box.reading_order

def test_box_bbox_is_on_the_right():
    regs = segment_page(_synthetic_page(), "ctst")
    box = next(r for r in regs if r.type in (RegionType.SIDEBAR, RegionType.INFO_BOX))
    assert box.bbox[0] > 400   # x0 on right half
