"""Bộ dựng 240 câu — khoá lại ba tính chất, không khoá số liệu.

Số câu và tỉ lệ nhãn là chuyện của dữ liệu; ba thứ dưới đây là chuyện của
THIẾT KẾ và nếu vỡ thì bảng đo sau này sai mà không ai biết.
"""
import csv
import random

import pytest

from src.test import build_testset_240 as B


def _row(page, do_kho="truc_tiep", phan_mon="sinh", q="q"):
    return {"question": q, "ground_truth": "gt", "source_book": "b",
            "source_page": str(page), "do_kho": do_kho, "phan_mon": phan_mon}


def test_spreads_across_gold_pages_before_taking_a_second_from_one():
    """Trải theo TRANG trước — đây là điểm khác biệt so với rút mẫu ngẫu nhiên.

    Pool cảnh báo "3 câu chung một trang vàng nên tương quan". Lấy 3 câu mà rơi
    hết vào 1 trang thì sức phân biệt thống kê ~1 trang, không phải 3 câu.
    """
    rows = [_row(p, q=f"p{p}-{i}") for p in (10, 20, 30) for i in range(3)]
    chosen = B.select_text_rows(rows, 3, random.Random("x"))
    assert len({r["source_page"] for r in chosen}) == 3


def test_never_invents_rows_when_the_pool_is_too_small():
    """Thiếu thì trả ít, KHÔNG lặp lại câu cho đủ số (nguyên tắc 1)."""
    rows = [_row(10, q="a"), _row(20, q="b")]
    chosen = B.select_text_rows(rows, 16, random.Random("x"))
    assert len(chosen) == 2
    assert len({r["question"] for r in chosen}) == 2


def test_selection_is_deterministic_across_runs():
    rows = [_row(p, q=f"p{p}-{i}") for p in range(10, 25) for i in range(3)]
    a = B.select_text_rows(rows, 16, random.Random("42:X"))
    b = B.select_text_rows(rows, 16, random.Random("42:X"))
    assert [r["question"] for r in a] == [r["question"] for r in b]


def test_one_book_choice_does_not_shift_when_another_book_is_added(tmp_path):
    """rng seed theo TÊN QUYỂN, nên thêm quyển 13 không xáo lại quyển 1..12.

    Nếu dùng một rng chung thì thêm/bớt một quyển sẽ đổi lựa chọn của mọi quyển
    khác, và hai lần chạy "cùng seed" cho hai bộ test khác nhau — im lặng.
    """
    def write(d, name, n_pages=9):
        p = d / f"{name}_testset.csv"
        rows = [_row(pg, q=f"{name}-{pg}-{i}") for pg in range(10, 10 + n_pages)
                for i in range(3)]
        with p.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    d1 = tmp_path / "pool1"; d1.mkdir()
    d2 = tmp_path / "pool2"; d2.mkdir()
    for d in (d1, d2):
        write(d, "AAA"); write(d, "BBB")
    write(d2, "ZZZ")                      # pool2 có thêm một quyển

    B.build(d1, tmp_path / "out1", 16, 42)
    B.build(d2, tmp_path / "out2", 16, 42)

    def read(p):
        with p.open(encoding="utf-8-sig", newline="") as f:
            return [r["question"] for r in csv.DictReader(f)]

    assert read(tmp_path / "out1" / "AAA_testset.csv") == \
           read(tmp_path / "out2" / "AAA_testset.csv")


def test_output_marks_the_question_source(tmp_path):
    """Không phân biệt được câu VĂN BẢN với câu HÌNH thì bảng MT4 vô nghĩa."""
    d = tmp_path / "pool"; d.mkdir()
    rows = [_row(p, q=f"p{p}") for p in range(10, 30)]
    p = d / "AAA_testset.csv"
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    B.build(d, tmp_path / "out", 16, 42)
    with (tmp_path / "out" / "AAA_testset.csv").open(encoding="utf-8-sig") as f:
        out = list(csv.DictReader(f))
    assert all(r["nguon_cau_hoi"] == "van_ban" for r in out)
    assert all(r["figure_label"] == "" for r in out)


def test_real_pool_gives_192_text_questions_over_all_gold_pages():
    """Chốt trên POOL THẬT: 12 quyển × 16 câu, và phủ HẾT trang vàng của pool.

    Con số 9/9 trang không phải trang trí: nó là bằng chứng rằng chiến lược trải
    đều thực sự chạy trên dữ liệu thật, chứ không chỉ trên fixture tổng hợp.
    """
    if not (B.POOL_DIR / "SGK_KHTN_6_CD_testset.csv").exists():
        pytest.skip("chưa có pool 300 câu")
    import json
    meta = json.loads((B.OUT_DIR / "_selection_meta.json").read_text(encoding="utf-8"))
    assert meta["n_van_ban"] == 192
    assert meta["n_tong_du_kien"] == 240
    for book, d in meta["per_book"].items():
        assert d["n_van_ban"] == 16, book
        assert d["n_trang_vang"] == d["n_trang_vang_trong_pool"], book
