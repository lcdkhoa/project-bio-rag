import pytest

import main as main_module
from src.etl.book.page_map import NumberCandidate

from .conftest import make_png_book, page_of

PAGES = 6


@pytest.fixture
def two_books(tmp_path):
    for grade in (6, 7):
        make_png_book(tmp_path, list(range(1, PAGES + 1)),
                      name=f"SGK_KHTN_{grade}_KNTT")
    return tmp_path


def _fake_reader():
    """Đọc được số trang in = page_index - 1 cho mọi trang (offset -1)."""
    def read(image_bgr):
        value = page_of(image_bgr) - 1
        return [NumberCandidate(value=value, conf=90.0,
                                side="L" if value % 2 == 0 else "R")]
    return read


def test_build_manifests_writes_one_json_per_book(two_books, tmp_path, capsys):
    code = main_module.run_build_manifests(
        read_candidates=_fake_reader(),
        read_toc=lambda source: ["Bài 1. A 2"],
        detect_banner=lambda img: None,
        manifest_dir=tmp_path / "manifests",
        data_dir=two_books,
    )

    assert code == 0
    written = sorted(p.name for p in (tmp_path / "manifests").glob("*.json"))
    assert written == ["KHTN6-KNTT.json", "KHTN7-KNTT.json"]
    assert "G1" in capsys.readouterr().out


def test_build_manifests_can_target_one_book(two_books, tmp_path):
    main_module.run_build_manifests(
        "SGK_KHTN_7_KNTT",
        read_candidates=_fake_reader(),
        read_toc=lambda source: [],
        detect_banner=lambda img: None,
        manifest_dir=tmp_path / "manifests",
        data_dir=two_books,
    )

    assert [p.name for p in (tmp_path / "manifests").glob("*.json")] == \
        ["KHTN7-KNTT.json"]


def test_build_manifests_returns_nonzero_when_g1_fails(two_books, tmp_path):
    # No page number anywhere -> fit_offset raises PageMapError -> the command
    # must exit nonzero instead of quietly writing a guessed page map.
    code = main_module.run_build_manifests(
        read_candidates=lambda image_bgr: [],
        read_toc=lambda source: [],
        detect_banner=lambda img: None,
        manifest_dir=tmp_path / "manifests",
        data_dir=two_books,
    )
    assert code == 1
    assert list((tmp_path / "manifests").glob("*.json")) == []


def test_build_manifests_returns_nonzero_when_confirmation_is_too_low(two_books,
                                                                     tmp_path):
    # Đúng một trang đọc được số mỗi quyển: mô hình offset nhất trí (1/1) nhưng
    # chỉ 1/4 trang CÓ IN SỐ là ocr_confirmed -> G1 fail vì tỉ lệ, không vì fit.
    # (2 trang đầu là bìa, đứng ngoài mẫu số.)
    def read(image_bgr):
        read.calls += 1
        return [NumberCandidate(value=2, conf=90.0, side="L")] \
            if (read.calls - 1) % PAGES == 2 else []
    read.calls = 0

    code = main_module.run_build_manifests(
        read_candidates=read,
        read_toc=lambda source: [],
        detect_banner=lambda img: None,
        manifest_dir=tmp_path / "manifests",
        data_dir=two_books,
    )
    assert code == 1
