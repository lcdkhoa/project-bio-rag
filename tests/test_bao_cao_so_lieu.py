# -*- coding: utf-8 -*-
"""Khoá số liệu của báo cáo vào phép đo, thay vì vào trí nhớ người viết.

Bài học của D-129: chữa từng chỗ mà bộ lint bắt được rồi coi phần còn lại là
đúng thì vẫn còn số cũ sống sót. Bộ lint `report/kiem_tra_tex.py` chỉ chặn được
những chuỗi mà ai đó ĐÃ NGHĨ RA để cấm. Các test dưới đây chặn chiều ngược lại:
số trong `.tex` phải khớp với số tính lại từ tệp kết quả, nên khi dữ liệu đổi
mà `.tex` không đổi thì test đỏ chứ không im lặng.
"""
from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

import pytest

GOC = Path(__file__).resolve().parent.parent
CSV_EVAL = GOC / "src" / "test" / "evaluation_report_240.csv"
TEX_CH4 = GOC / "report" / "tex_source" / "src" / "chapters" / "4.hien_thuc_danh_gia_thao_luan.tex"


def _nap(ten: str, duong: Path):
    spec = importlib.util.spec_from_file_location(ten, duong)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[ten] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ve_hinh():
    return _nap("ve_hinh_chuong4", GOC / "report" / "ve_hinh_chuong4.py")


@pytest.fixture(scope="module")
def lint():
    return _nap("kiem_tra_tex", GOC / "report" / "kiem_tra_tex.py")


def test_gop_can_theo_so_cau_khong_phai_theo_quyen(ve_hinh):
    """Gộp theo CÂU khác trung bình theo QUYỂN khi số câu mỗi quyển lệch nhau.

    Đây chính là chỗ dễ sai nhất của bảng tổng hợp: 12 quyển có 17--20 câu, nên
    hai cách tính ra hai con số khác nhau ở hàng thập phân thứ ba.
    """
    import pandas as pd
    d = pd.DataFrame({"num_questions": [10, 90], "x": [0.0, 1.0]})
    assert ve_hinh._gop(d, "x") == pytest.approx(0.9)
    assert d["x"].mean() == pytest.approx(0.5)   # cách SAI, để đối chứng


def test_so_thap_phan_dung_dau_phay_tieng_viet(ve_hinh):
    assert ve_hinh._so(0.9091, 4) == "0,9091"
    assert ve_hinh._so(4.0649, 2) == "4,06"


@pytest.mark.skipif(not CSV_EVAL.exists(), reason="chưa có tệp kết quả đánh giá")
def test_so_trong_chuong_4_khop_voi_tep_ket_qua(ve_hinh):
    """Mỗi độ đo tổng hợp in trong Chương 4 phải bằng số tính lại từ CSV."""
    import pandas as pd
    d = pd.read_csv(CSV_EVAL)
    tex = io.open(TEX_CH4, encoding="utf-8").read()

    can_kiem = {
        "recall_page": 4,
        "mrr_page": 4,
        "precision_page": 4,
        "recall_book": 4,
        "precision_book": 4,
        "recall@3_raw": 4,
        "recall@5_raw": 4,
        "recall@10_raw": 4,
        "judge_correctness": 3,
        "judge_faithfulness": 3,
        "judge_relevancy": 3,
    }
    thieu = []
    for cot, n in can_kiem.items():
        gia_tri = ve_hinh._so(ve_hinh._gop(d, cot), n)
        # LaTeX viết dấu phẩy thập phân là `{,}` để giữ đúng khoảng cách.
        if gia_tri.replace(",", "{,}") not in tex and gia_tri not in tex:
            thieu.append(f"{cot} = {gia_tri}")
    assert not thieu, "Chương 4 không chứa số đã đo: " + "; ".join(thieu)


@pytest.mark.skipif(not CSV_EVAL.exists(), reason="chưa có tệp kết quả đánh giá")
def test_tong_so_cau_la_231(ve_hinh):
    """231 = 192 văn bản + 39 hình. Cấm cả '240' lẫn '120' — xem CẤM #6."""
    import pandas as pd
    d = pd.read_csv(CSV_EVAL)
    assert int(d["num_questions"].sum()) == 231
    tex = io.open(TEX_CH4, encoding="utf-8").read()
    assert "231" in tex


def test_lint_tex_sach(lint):
    """Bộ lint `.tex` phải sạch — máy này không có trình biên dịch LaTeX."""
    loi = lint.kiem_tra()
    assert loi == [], "\n".join(loi)
