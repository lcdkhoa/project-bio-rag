import fitz
import pytest

import main as main_module
from src.etl.book.page_map import NumberCandidate


@pytest.fixture
def two_books(tmp_path, monkeypatch):
    for grade in (6, 7):
        doc = fitz.open()
        for _ in range(6):
            doc.new_page(width=595, height=842)
        doc.save(str(tmp_path / f"SGK-KHTN-Lop-{grade}.pdf"))
        doc.close()
    monkeypatch.setattr(main_module, "DATA_DIR", tmp_path)
    return tmp_path


def _fake_reader():
    def read(image_bgr):
        index = read.calls
        read.calls += 1
        value = index % 6
        return [NumberCandidate(value=value, conf=90.0,
                                side="L" if value % 2 == 0 else "R")]
    read.calls = 0
    return read


def test_build_manifests_writes_one_json_per_book(two_books, tmp_path, capsys):
    code = main_module.run_build_manifests(
        read_candidates=_fake_reader(),
        read_toc=lambda path: ["Bài 1. A 2"],
        detect_banner=lambda img: None,
        manifest_dir=tmp_path / "manifests",
    )

    assert code == 0
    written = sorted(p.name for p in (tmp_path / "manifests").glob("*.json"))
    assert written == ["KHTN6-KNTT.json", "KHTN7-KNTT.json"]
    assert "G1" in capsys.readouterr().out


def test_build_manifests_can_target_one_book(two_books, tmp_path):
    main_module.run_build_manifests(
        "SGK-KHTN-Lop-7.pdf",
        read_candidates=_fake_reader(),
        read_toc=lambda path: [],
        detect_banner=lambda img: None,
        manifest_dir=tmp_path / "manifests",
    )

    assert [p.name for p in (tmp_path / "manifests").glob("*.json")] == \
        ["KHTN7-KNTT.json"]


def test_build_manifests_returns_nonzero_when_g1_fails(two_books, tmp_path):
    # No page number anywhere -> fit_offset raises PageMapError -> the command
    # must exit nonzero instead of quietly writing a guessed page map.
    code = main_module.run_build_manifests(
        read_candidates=lambda image_bgr: [],
        read_toc=lambda path: [],
        detect_banner=lambda img: None,
        manifest_dir=tmp_path / "manifests",
    )
    assert code == 1
    assert list((tmp_path / "manifests").glob("*.json")) == []


def test_build_manifests_returns_nonzero_when_confirmation_is_too_low(two_books,
                                                                     tmp_path):
    # Exactly one page numbered per book: the offset model is unanimous (1/1) but
    # only 1/6 pages are ocr_confirmed -> G1 fails on the ratio, not on the fit.
    def read(image_bgr):
        read.calls += 1
        return [NumberCandidate(value=0, conf=90.0, side="L")] \
            if (read.calls - 1) % 6 == 0 else []
    read.calls = 0

    code = main_module.run_build_manifests(
        read_candidates=read,
        read_toc=lambda path: [],
        detect_banner=lambda img: None,
        manifest_dir=tmp_path / "manifests",
    )
    assert code == 1
