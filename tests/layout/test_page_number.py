import numpy as np, cv2
from src.etl.layout.page_number import detect_printed_page_number

def _page_with_number(txt, corner="left"):
    img = np.full((300, 200, 3), 255, np.uint8)
    org = (10, 285) if corner == "left" else (165, 285)
    cv2.putText(img, txt, org, cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,0,0), 2, cv2.LINE_AA)
    return img

def test_reads_bottom_number():
    assert detect_printed_page_number(_page_with_number("89"), "kntt", pdf_index=91) == 89

def test_falls_back_to_pdf_index_when_absent():
    blank = np.full((300, 200, 3), 255, np.uint8)
    assert detect_printed_page_number(blank, "cd", pdf_index=42) == 42

def test_reads_bottom_right_number():
    # NOTE: uses a 2-digit number, not the coordinator-suggested "144" — see task-4-report.md
    # "Fix report" for why 3 digits at the shared helper's fixed right-corner org clip against
    # the 200px-wide synthetic canvas itself (unrelated to this module's crop fractions).
    assert detect_printed_page_number(_page_with_number("37", corner="right"), "cd", pdf_index=200) == 37

def test_body_text_in_bottom_band_is_not_read_as_number():
    # Scope: locks "pure-letter body text in the band is not misread as a page number."
    # The harder case -- a running footer with BOTH a grade digit and the real page number in
    # the same corner (e.g. "...NHIEN 7   45") -- is real-page calibration, deferred to Task 10.
    img = np.full((300, 200, 3), 255, np.uint8)
    # ink must land INSIDE the left crop box: x in [0,50], y in [255,300].
    # putText org y is the BASELINE (glyphs drawn above it), so org_y ~292 => ink ~y275-292.
    cv2.putText(img, "abc", (4, 292), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    assert detect_printed_page_number(img, "ctst", pdf_index=57) == 57   # fallback, no false digit read
