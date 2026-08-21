import cv2
import numpy as np

from src.etl.book import page_number_ocr as pno
from src.etl.book.page_number_ocr import read_page_number_candidates

# Synthetic 900x640 canvas. Geometry here is fixture-local; production fractions
# (BAND_TOP_FRAC / OUTER_FRAC) are calibrated on real pages in Task 7's QA run,
# so re-tuning production never breaks these logic tests.
_H, _W = 900, 640


def _page(text=None, org=None):
    img = np.full((_H, _W, 3), 255, np.uint8)
    if text is not None:
        cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3,
                    cv2.LINE_AA)
    return img


def test_reads_an_even_number_in_the_left_margin():
    cands = read_page_number_candidates(_page("20", (20, 870)))
    assert [(c.value, c.side) for c in cands] == [(20, "L")]


def test_reads_an_odd_number_in_the_right_margin():
    cands = read_page_number_candidates(_page("21", (_W - 90, 870)))
    assert [(c.value, c.side) for c in cands] == [(21, "R")]


def test_ignores_digits_in_the_middle_of_the_band():
    # Figure labels and footnote markers live mid-width; only the outer margins
    # carry page numbers.
    assert read_page_number_candidates(_page("42", (_W // 2 - 20, 870))) == []


def test_ignores_content_above_the_band():
    assert read_page_number_candidates(_page("20", (20, 400))) == []


def test_returns_empty_on_a_blank_page():
    assert read_page_number_candidates(_page()) == []


def test_ignores_non_digit_tokens():
    assert read_page_number_candidates(_page("Bai", (20, 870))) == []


# --- Task 7 / ruling 11: union with the corner-crop (psm 6) read path -------
# These stub `pytesseract.image_to_data` directly (keyed on which psm the call
# used) so the two strategies' interaction is deterministic — real OCR
# accuracy on synthetic canvases is not what these tests are checking.

def _stub_image_to_data(sparse_result, corner_result):
    def fake(image, lang=None, config=None, output_type=None):
        return dict(sparse_result if "psm 11" in config else corner_result)
    return fake


def test_corner_crop_finds_a_number_the_sparse_read_missed(monkeypatch):
    sparse_empty = {"text": [], "conf": [], "left": [], "width": []}
    corner_hit = {"text": ["24"], "conf": ["92"]}
    monkeypatch.setattr(pno.pytesseract, "image_to_data",
                        _stub_image_to_data(sparse_empty, corner_hit))

    cands = read_page_number_candidates(np.zeros((900, 640, 3), np.uint8))

    assert (24, "L") in [(c.value, c.side) for c in cands]


def test_union_dedupes_same_value_and_side_keeping_higher_confidence(monkeypatch):
    sparse_hit = {"text": ["24"], "conf": ["60"], "left": [10], "width": [30]}
    corner_hit = {"text": ["24"], "conf": ["92"]}
    monkeypatch.setattr(pno.pytesseract, "image_to_data",
                        _stub_image_to_data(sparse_hit, corner_hit))

    cands = read_page_number_candidates(np.zeros((900, 640, 3), np.uint8))

    left_matches = [c for c in cands if c.value == 24 and c.side == "L"]
    assert len(left_matches) == 1
    assert left_matches[0].conf == 92.0


def test_corner_crop_still_respects_min_conf(monkeypatch):
    sparse_empty = {"text": [], "conf": [], "left": [], "width": []}
    corner_low_conf = {"text": ["24"], "conf": ["10"]}
    monkeypatch.setattr(pno.pytesseract, "image_to_data",
                        _stub_image_to_data(sparse_empty, corner_low_conf))

    cands = read_page_number_candidates(np.zeros((900, 640, 3), np.uint8))

    assert cands == []
