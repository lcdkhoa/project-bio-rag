import pytest
from src.etl.book.page_map import (
    NumberCandidate, OffsetFit, PageMapError,
    keep_parity, fit_offset, build_page_map,
)


def C(value, side, conf=90.0):
    return NumberCandidate(value=value, conf=conf, side=side)


def test_keep_parity_keeps_even_on_left_and_odd_on_right():
    kept = keep_parity([C(20, "L"), C(21, "R")])
    assert [c.value for c in kept] == [20, 21]


def test_keep_parity_drops_even_on_right_and_odd_on_left():
    # Measured on the real corpus: even printed pages are ALWAYS in the left
    # margin, odd ones always right (695/695). A digit token on the wrong side
    # is a figure label or body text, not a page number.
    assert keep_parity([C(20, "R"), C(21, "L")]) == []


def test_fit_offset_picks_the_dominant_offset_and_reports_votes():
    reads = {i: [C(i, "L" if i % 2 == 0 else "R")] for i in range(10)}
    reads[3] = [C(177, "R")]          # single noisy read
    fit = fit_offset(reads)
    assert fit.offset == 0
    assert fit.votes == 9
    assert fit.total == 10
    assert fit.ratio == pytest.approx(0.9)


def test_fit_offset_handles_a_nonzero_offset():
    # A book with 4 unnumbered cover pages would fit offset -4; the model must
    # derive it, not assume 0.
    reads = {i: [C(i - 4, "L" if (i - 4) % 2 == 0 else "R")] for i in range(6, 12)}
    fit = fit_offset(reads)
    assert fit.offset == -4
    assert fit.votes == 6


def test_fit_offset_ignores_parity_violating_candidates():
    reads = {2: [C(2, "L")], 3: [C(3, "R")], 4: [C(4, "R")]}   # idx4 wrong side
    fit = fit_offset(reads)
    assert fit.votes == 2 and fit.total == 2


def test_fit_offset_raises_when_no_candidate_survives():
    with pytest.raises(PageMapError):
        fit_offset({0: [], 1: [C(7, "L")]})


def test_build_page_map_marks_confirmed_and_inferred():
    reads = {0: [C(0, "L")], 1: [], 2: [C(2, "L")]}
    fit = OffsetFit(offset=0, votes=2, total=2)
    recs = build_page_map(3, reads, fit)
    assert [r.printed_page for r in recs] == [0, 1, 2]
    assert [r.source for r in recs] == [
        "ocr_confirmed", "model_inferred", "ocr_confirmed"]
    assert recs[1].side is None and recs[1].conf is None
    assert recs[0].conf == 90.0


def test_build_page_map_never_falls_back_to_index_plus_one():
    # The bug this whole task exists to kill: page_number.py used index + 1.
    fit = OffsetFit(offset=0, votes=5, total=5)
    recs = build_page_map(3, {}, fit)
    assert [r.printed_page for r in recs] == [0, 1, 2]


def test_build_page_map_applies_offset_to_inferred_pages():
    fit = OffsetFit(offset=-4, votes=6, total=6)
    recs = build_page_map(8, {}, fit)
    assert recs[7].printed_page == 3


def test_build_page_map_rejects_a_weak_offset_consensus():
    # Fail loudly rather than index a book on a coin-flip page map.
    fit = OffsetFit(offset=0, votes=5, total=20)
    with pytest.raises(PageMapError):
        build_page_map(20, {}, fit)


def test_build_page_map_ignores_a_confirmed_looking_candidate_on_the_wrong_side():
    reads = {4: [C(4, "R")]}
    fit = OffsetFit(offset=0, votes=9, total=10)
    recs = build_page_map(5, reads, fit)
    assert recs[4].source == "model_inferred"
