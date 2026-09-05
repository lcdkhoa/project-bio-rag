import numpy as np
import pandas as pd
import pytest

from src.test.run_eval import _RongTron, aggregate_by_loai


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


def test_rong_tron_dung_khi_ti_le_that_bai_vuot_nguong():
    """D-184: 240/240 câu rỗng lặng lẽ (except Exception rộng ở
    HybridRetriever.search() nuốt lỗi) từng làm mất trắng một lượt eval nhiều
    giờ mà script không hề dừng — cửa sổ trượt này phải dừng SỚM."""
    tron = _RongTron(window=20, max_rate=0.30)
    with pytest.raises(SystemExit):
        for _ in range(20):
            tron.ghi_nhan(False)  # thất bại toàn bộ, giống đúng sự cố D-184


def test_rong_tron_khong_dung_khi_ti_le_that_bai_binh_thuong():
    tron = _RongTron(window=20, max_rate=0.30)
    for i in range(20):
        tron.ghi_nhan(i % 10 != 0)  # 2/20 = 10% thất bại, dưới ngưỡng 30%
