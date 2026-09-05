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
# D-182 xoá evaluation_report_240.csv (trục "theo quyển", 12 hàng). Nguồn hiện
# hành là src/test/eval_results/eval_report.csv (trục "theo LOẠI câu hỏi",
# 3 hàng: van_ban/hinh/ngoai_pham_vi), sinh bởi run_eval.py::aggregate_by_loai(),
# và đã COMMIT (D-187/D-188) nên luôn tồn tại — không còn cần skipif.
CSV_EVAL = GOC / "src" / "test" / "eval_results" / "eval_report.csv"
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


def test_sap_xep_theo_thu_tu_co_dinh_va_bo_loai_la(ve_hinh):
    """D-181: trục hình vẽ là LOẠI câu hỏi, thứ tự cố định văn_bản/hình/ngoài_phạm_vi/
    không_rõ; một `loai_cau_hoi` không nằm trong 4 loại đã biết bị LOẠI khỏi hình
    (không vẽ một cột không giải thích được), không được đoán vị trí cho nó."""
    import pandas as pd
    d = pd.DataFrame({
        "loai_cau_hoi": ["ngoai_pham_vi", "van_ban", "gia_tri_la", "hinh"],
        "num_questions": [30, 192, 1, 48],
    })
    out = ve_hinh._sap_xep(d)
    assert list(out["loai_cau_hoi"]) == ["van_ban", "hinh", "ngoai_pham_vi"]


def test_ve_phan_bo_loai_va_judge_scores_khong_nem(ve_hinh, tmp_path, monkeypatch):
    """Smoke test hai hình mới bằng dữ liệu tổng hợp, không cần chạy evaluator
    thật (tốn quota Groq) — chỉ xác nhận không crash, kể cả khi có NaN (nhóm
    `khong_ro` do dữ liệu cũ trước D-181 chưa khôi phục được điểm giám khảo)."""
    import pandas as pd
    d = pd.DataFrame({
        "loai_cau_hoi": ["van_ban", "hinh", "ngoai_pham_vi", "khong_ro"],
        "num_questions": [192, 48, 30, 5],
        "judge_correctness": [4.1, 3.9, 4.5, float("nan")],
        "judge_faithfulness": [4.3, 4.0, 4.6, float("nan")],
        "judge_relevancy": [4.2, 4.1, 4.4, float("nan")],
    })
    monkeypatch.setattr(ve_hinh, "THU_MUC_HINH", tmp_path)
    ve_hinh._dat_kieu()
    p1 = ve_hinh.ve_phan_bo_loai(d)
    p2 = ve_hinh.ve_judge_scores(d)
    assert p1.exists() and p1.stat().st_size > 0
    assert p2.exists() and p2.stat().st_size > 0


def test_doc_eval_bao_loi_ro_rang_khi_csv_con_schema_cu(ve_hinh, tmp_path, monkeypatch):
    """CSV schema CŨ (trước D-181, không có `loai_cau_hoi`/`num_questions` đúng
    nghĩa mới) phải báo lỗi RÕ RÀNG khi vẽ, không được âm thầm vẽ sai hoặc ném
    KeyError khó hiểu (nguyên tắc 5: fail loudly)."""
    import pandas as pd
    csv_cu = tmp_path / "evaluation_report_240.csv"
    pd.DataFrame({"book": ["SGK_KHTN_6_CD"], "recall_page": [0.9]}).to_csv(csv_cu, index=False)
    monkeypatch.setattr(ve_hinh, "CSV_EVAL", csv_cu)
    with pytest.raises(SystemExit, match="loai_cau_hoi"):
        ve_hinh._doc_eval()


def test_so_thap_phan_dung_dau_phay_tieng_viet(ve_hinh):
    assert ve_hinh._so(0.9091, 4) == "0,9091"
    assert ve_hinh._so(4.0649, 2) == "4,06"


def test_so_trong_chuong_4_khop_voi_tep_ket_qua(ve_hinh):
    """Mỗi độ đo giám khảo (Correct/Faithful/Relevancy, gộp có trọng số theo
    LOẠI) in trong Chương 4 phải bằng số tính lại từ `eval_report.csv`.

    D-190 (2026-09-05): CSV nay ở trục LOẠI câu hỏi cố định (`van_ban`/`hinh`/
    `ngoai_pham_vi`, D-182), không còn 9 cột IR/xếp hạng theo quyển của cấu trúc
    cũ (đã xoá vĩnh viễn ở D-181/D-182, không quay lại) — nên không còn lý do
    để SKIP: cột `judge_correctness`/`judge_faithfulness`/`judge_relevancy` luôn
    có mặt trong schema hiện hành.
    """
    import pandas as pd
    d = pd.read_csv(CSV_EVAL)
    tex = io.open(TEX_CH4, encoding="utf-8").read()

    can_kiem = {
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


def test_tong_so_cau_la_240(ve_hinh):
    """240 = 158 văn bản + 52 hình + 30 ngoài phạm vi, bộ câu D-182/D-187
    (lấy mẫu ngẫu nhiên toàn corpus, thay cấu trúc cố định-theo-quyển của
    D-172 đã bị D-182 huỷ hoàn toàn).

    KHÔNG cấm '231'/'238'/'270' xuất hiện trong Chương 4 — chương này CHỦ Ý
    nhắc lại các số cũ như mốc lịch sử khi so sánh với các lượt đo trước, nên
    cấm tuyệt đối sẽ chặn nhầm nội dung hợp lệ.
    """
    import pandas as pd
    d = pd.read_csv(CSV_EVAL)
    tong = int(d["num_questions"].sum())
    assert tong == 240, f"Tổng số câu = {tong}, kỳ vọng 240"
    tex = io.open(TEX_CH4, encoding="utf-8").read()
    assert "240" in tex
    assert "240 câu" in tex or "$240$ câu" in tex


def test_lint_tex_sach(lint):
    """Bộ lint `.tex` phải sạch — máy này không có trình biên dịch LaTeX."""
    loi = lint.kiem_tra()
    assert loi == [], "\n".join(loi)
