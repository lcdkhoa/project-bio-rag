import pandas as pd
import pytest

from src.test.merge_eval_batches import merge


def _ghi_batch(tmp_path, ten, rows):
    p = tmp_path / ten
    pd.DataFrame(rows).to_csv(p, index=False, encoding="utf-8-sig")
    return p


def _dong(question, loai="van_ban", source_book="S", source_page=1, correctness=5.0):
    return {"question": question, "loai": loai, "source_book": source_book,
            "source_page": source_page, "retrieved": "S:p1", "rag_answer": "a",
            "ground_truth": "gt", "judge_correctness": correctness,
            "judge_faithfulness": correctness, "judge_relevancy": correctness}


def test_merge_gop_dung_khong_trung_va_tinh_lai_bao_cao(tmp_path):
    b1 = _ghi_batch(tmp_path, "b1.csv", [_dong("q1"), _dong("q2")])
    b2 = _ghi_batch(tmp_path, "b2.csv", [_dong("q3"), _dong("q4")])

    out_dir = tmp_path / "out"
    report = merge([b1, b2], draft_csv=tmp_path / "khong_ton_tai.csv", out_dir=out_dir)

    merged = pd.read_csv(out_dir / "eval_result.csv")
    assert len(merged) == 4
    assert set(merged["question"]) == {"q1", "q2", "q3", "q4"}
    assert (out_dir / "eval_report.csv").exists()
    assert (out_dir / "eval_report.md").exists()
    assert int(report.loc[report["loai_cau_hoi"] == "van_ban", "num_questions"].iloc[0]) == 4


def test_merge_phat_hien_cau_trung_giua_2_batch(tmp_path):
    # cung (question, source_book, source_page) xuat hien o ca 2 batch -> loi
    # phan vung that (mot batch bi chay/tai nham 2 lan).
    b1 = _ghi_batch(tmp_path, "b1.csv", [_dong("q1"), _dong("q2")])
    b2 = _ghi_batch(tmp_path, "b2.csv", [_dong("q1"), _dong("q3")])

    with pytest.raises(SystemExit, match="TRUNG"):
        merge([b1, b2], draft_csv=tmp_path / "khong_ton_tai.csv", out_dir=tmp_path / "out")


def test_merge_lech_so_cau_so_voi_draft_csv_goc(tmp_path):
    b1 = _ghi_batch(tmp_path, "b1.csv", [_dong("q1"), _dong("q2")])
    b2 = _ghi_batch(tmp_path, "b2.csv", [_dong("q3")])

    draft = tmp_path / "draft.csv"
    pd.DataFrame([_dong("q1"), _dong("q2"), _dong("q3"), _dong("q4")]).to_csv(
        draft, index=False, encoding="utf-8-sig")

    with pytest.raises(SystemExit, match="LECH SO CAU"):
        merge([b1, b2], draft_csv=draft, out_dir=tmp_path / "out")


def test_merge_bao_dong_khi_thieu_diem_judge(tmp_path, capsys):
    # I-3 cua run_eval.py (D-173): mot cau lo judge (NaN) van phai duoc dem
    # vao num_questions nhung lo ra qua so_cau_co_diem_judge thap hon, va
    # merge_eval_batches.py phai in canh bao ngay, khong duoc im lang.
    b1 = _ghi_batch(tmp_path, "b1.csv",
                    [_dong("q1"), _dong("q2", correctness=float("nan"))])
    b2 = _ghi_batch(tmp_path, "b2.csv", [_dong("q3")])

    report = merge([b1, b2], draft_csv=tmp_path / "khong_ton_tai.csv",
                    out_dir=tmp_path / "out")

    row = report.loc[report["loai_cau_hoi"] == "van_ban"].iloc[0]
    assert int(row["num_questions"]) == 3
    assert int(row["so_cau_co_diem_judge"]) == 2

    out = capsys.readouterr().out
    assert "KHONG co diem giam khao" in out
