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
