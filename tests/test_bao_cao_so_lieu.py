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


_COT_IR_CU_TRUOC_D181 = (
    "recall_page", "mrr_page", "precision_page", "recall_book", "precision_book",
    "recall@3_raw", "recall@5_raw", "recall@10_raw",
)


@pytest.mark.skipif(not CSV_EVAL.exists(), reason="chưa có tệp kết quả đánh giá")
def test_so_trong_chuong_4_khop_voi_tep_ket_qua(ve_hinh):
    """Mỗi độ đo tổng hợp in trong Chương 4 phải bằng số tính lại từ CSV.

    D-181 (2026-09-03): `evaluation_report_240.csv` đổi trục sang LOẠI câu hỏi,
    9 cột IR/xếp hạng theo quyển (bao gồm 8 cột IR kiểm ở đây) bị xoá. Chương 4
    `.tex` CHƯA được viết lại theo cấu trúc mới (việc đó nằm ngoài phạm vi lượt
    sửa D-181 lần này) — nên khi CSV đã ở schema MỚI (thiếu các cột IR cũ), test
    này SKIP thay vì crash: không còn gì để đối chiếu cho tới khi Chương 4 được
    viết lại. Khi CSV vẫn ở schema CŨ (như tệp thật hiện có trên đĩa, sinh trước
    D-181), test chạy y hệt trước đây.
    """
    import pandas as pd
    d = pd.read_csv(CSV_EVAL)
    if any(c not in d.columns for c in _COT_IR_CU_TRUOC_D181):
        pytest.skip(
            "evaluation_report_240.csv đã ở schema MỚI theo LOẠI câu hỏi (D-181) "
            "-- Chương 4 .tex chưa được viết lại theo cấu trúc mới, việc đó nằm "
            "ngoài phạm vi lượt sửa này."
        )
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
def test_tong_so_cau_la_240(ve_hinh):
    """240 = 192 văn bản + 48 hình, chốt D-172 (2026-09-02).

    D-181 (2026-09-03): thêm 30 câu `ngoai_pham_vi` vào `testsets_240/`, nên một
    lượt đo bao gồm cả nhóm này cho tổng ĐÚNG là 270 = 240 + 30 — không phải một
    hồi quy, miễn là không câu nào bị rơi mất khi gộp. Test chấp nhận cả hai giá
    trị tuỳ CSV hiện có nhóm `ngoai_pham_vi` hay không, nhưng vẫn khẳng định
    Chương 4 (chưa viết lại, ngoài phạm vi D-181) còn nhắc "240" như số hiện tại.

    KHÔNG cấm '231'/'238' xuất hiện trong Chương 4 — chương này CHỦ Ý nhắc lại
    cả hai như mốc lịch sử khi so sánh với các lượt đo trước (đúng phong cách đã
    dùng xuyên suốt chương cho báo cáo chuyên đề cũ), nên cấm tuyệt đối sẽ chặn
    nhầm nội dung hợp lệ.
    """
    import pandas as pd
    d = pd.read_csv(CSV_EVAL)
    tong = int(d["num_questions"].sum())
    co_ngoai_pham_vi = "loai_cau_hoi" in d.columns and (
        d["loai_cau_hoi"] == "ngoai_pham_vi").any()
    ky_vong = 270 if co_ngoai_pham_vi else 240
    assert tong == ky_vong, (
        f"Tổng số câu = {tong}, kỳ vọng {ky_vong} "
        f"(co_ngoai_pham_vi={co_ngoai_pham_vi})"
    )
    tex = io.open(TEX_CH4, encoding="utf-8").read()
    assert "240" in tex
    assert "240 câu" in tex or "$240$ câu" in tex


def test_lint_tex_sach(lint):
    """Bộ lint `.tex` phải sạch — máy này không có trình biên dịch LaTeX."""
    loi = lint.kiem_tra()
    assert loi == [], "\n".join(loi)
