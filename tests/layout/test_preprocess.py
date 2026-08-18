import numpy as np
from src.etl.layout.preprocess import preprocess_page

def _page_with_left_stamp():
    img = np.full((200, 100, 3), 255, np.uint8)   # white page
    img[:, 0:6] = 0                                # black vertical stamp on left margin
    return img

def test_kntt_left_stamp_is_masked():
    out = preprocess_page(_page_with_left_stamp(), "kntt")
    # the stamp column is wiped back to (near) white
    assert out[:, 0:6].mean() > 240

def test_non_kntt_left_margin_untouched():
    img = _page_with_left_stamp()
    out = preprocess_page(img, "cd")
    assert out[:, 0:6].mean() < 20   # CD: no left-stamp masking
