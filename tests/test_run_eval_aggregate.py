import numpy as np
import pandas as pd

from src.test.run_eval import aggregate_by_loai


def test_aggregate_by_loai_doc_dung_cot_loai_khong_phai_nguon_cau_hoi():
    df = pd.DataFrame([
        {"question": "q1", "loai": "van_ban", "judge_correctness": 5.0,
         "judge_faithfulness": 5.0, "judge_relevancy": 5.0},
        {"question": "q2", "loai": "hinh", "judge_correctness": 3.0,
         "judge_faithfulness": 3.0, "judge_relevancy": 3.0},
    ])
    out = aggregate_by_loai(df)  # KHÔNG được raise KeyError('nguon_cau_hoi')
    assert set(out["loai_cau_hoi"]) == {"van_ban", "hinh"}
    assert int(out.loc[out["loai_cau_hoi"] == "van_ban", "num_questions"].iloc[0]) == 1


def test_aggregate_by_loai_dem_so_cau_co_diem_judge_bo_qua_nan():
    """I-3 (phản biện Task 4): một câu judge lỗi (NaN) không được lặng lẽ biến
    mất khỏi `num_questions` NHƯNG phải lộ ra qua `so_cau_co_diem_judge` thấp
    hơn `num_questions` — lặp lại đúng lớp lỗi D-173 (106/240 câu mất điểm)."""
    df = pd.DataFrame([
        {"question": "q1", "loai": "van_ban", "judge_correctness": 5.0,
         "judge_faithfulness": 5.0, "judge_relevancy": 5.0},
        {"question": "q2", "loai": "van_ban", "judge_correctness": np.nan,
         "judge_faithfulness": np.nan, "judge_relevancy": np.nan},
    ])
    out = aggregate_by_loai(df)
    row = out.loc[out["loai_cau_hoi"] == "van_ban"].iloc[0]
    assert int(row["num_questions"]) == 2
    assert int(row["so_cau_co_diem_judge"]) == 1
