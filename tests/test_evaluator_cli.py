"""Cờ `--book` / `--bo-qua-da-co` của evaluator, và cách tổng hợp lại kết quả cũ.

Lý do có file này: lượt đánh giá bộ 240 câu dừng giữa chừng ở quyển thứ 8, mà
`evaluator.py` không có cách nào chạy tiếp — nó glob toàn bộ `*_testset.csv` và
chạy lại từ đầu (~7 giờ + gọi lại LLM giám khảo cho 155 câu đã chấm). Cùng lớp
với D-84: một cờ bị bỏ qua im lặng đắt hơn nhiều một lỗi ồn ào.
"""

import pandas as pd
import pytest

from src.test.evaluator import book_of, chon_testsets, result_path_for, summarize_result


def _tao_bo_test(tmp_path, ten, co_ket_qua=False):
    p = tmp_path / f"{ten}_testset.csv"
    p.write_text("question,source_book,source_page\nq,b,1\n", encoding="utf-8")
    if co_ket_qua:
        (tmp_path / f"{ten}_result.csv").write_text("recall_page\n1.0\n", encoding="utf-8")
    return str(p)


def test_book_of_va_result_path_khop_nhau(tmp_path):
    p = _tao_bo_test(tmp_path, "SGK_KHTN_9_CD")
    assert book_of(p) == "SGK_KHTN_9_CD"
    assert result_path_for(p).endswith("SGK_KHTN_9_CD_result.csv")


def test_khong_co_co_thi_chay_het(tmp_path):
    files = [_tao_bo_test(tmp_path, t) for t in ("A", "B")]
    can_chay, bo_qua = chon_testsets(files)
    assert [book_of(p) for p in can_chay] == ["A", "B"]
    assert bo_qua == []


def test_loc_theo_book(tmp_path):
    files = [_tao_bo_test(tmp_path, t) for t in ("A", "B", "C")]
    can_chay, _ = chon_testsets(files, books=["B", "C"])
    assert [book_of(p) for p in can_chay] == ["B", "C"]


def test_ten_quyen_sai_thi_nem_kem_danh_sach_that(tmp_path):
    files = [_tao_bo_test(tmp_path, t) for t in ("A", "B")]
    with pytest.raises(ValueError) as exc:
        chon_testsets(files, books=["A", "KHONG_CO"])
    msg = str(exc.value)
    assert "KHONG_CO" in msg and "A" in msg and "B" in msg


def test_bo_qua_da_co_chi_bo_quyen_da_co_ket_qua(tmp_path):
    files = [
        _tao_bo_test(tmp_path, "A", co_ket_qua=True),
        _tao_bo_test(tmp_path, "B", co_ket_qua=False),
    ]
    can_chay, bo_qua = chon_testsets(files, bo_qua_da_co=True)
    assert [book_of(p) for p in can_chay] == ["B"]
    assert [book_of(p) for p in bo_qua] == ["A"]


def test_bo_qua_da_co_tat_thi_van_chay_lai(tmp_path):
    files = [_tao_bo_test(tmp_path, "A", co_ket_qua=True)]
    can_chay, bo_qua = chon_testsets(files, bo_qua_da_co=False)
    assert len(can_chay) == 1 and bo_qua == []


def test_summarize_result_danh_dau_luot_chay_va_chiu_thieu_cot():
    df = pd.DataFrame({"recall_page": [1.0, 0.0], "mrr_page": [1.0, 0.5]})
    s = summarize_result("A", df, luot_chay="da_co")
    assert s["book"] == "A"
    assert s["num_questions"] == 2
    assert s["luot_chay"] == "da_co"
    assert s["recall_page"] == 0.5
    # Cột vắng mặt phải ra NaN chứ không được ném — file kết quả cũ có thể thiếu cột.
    assert pd.isna(s["judge_correctness"])


class _LLMGia:
    """LLM giám khảo giả: ném lỗi `so_lan_loi` lần đầu rồi mới trả kết quả."""

    def __init__(self, so_lan_loi, loi):
        self.so_lan_loi = so_lan_loi
        self.loi = loi
        self.so_lan_goi = 0

    def invoke(self, _prompt):
        self.so_lan_goi += 1
        if self.so_lan_goi <= self.so_lan_loi:
            raise RuntimeError(self.loi)

        class _Resp:
            content = '{"correctness": 5, "faithfulness": 4, "relevancy": 4, "reasoning": "ok"}'

        return _Resp()


@pytest.fixture
def _khong_ngu(monkeypatch):
    import time
    monkeypatch.setattr(time, "sleep", lambda _s: None)


LOI_429 = ("Error code: 429 - {'error': {'message': 'Provider returned error', "
           "'code': 429, 'metadata': {'raw': 'stealth/ox-alpha is temporarily "
           "rate-limited upstream.'}}}")


def test_loi_429_duoc_coi_la_tam_thoi():
    from src.test.evaluator import _la_loi_tam_thoi
    assert _la_loi_tam_thoi(RuntimeError(LOI_429))
    assert _la_loi_tam_thoi(RuntimeError("Read timed out"))
    # Sai khoá thì thử lại vô ích — không được coi là tạm thời.
    assert not _la_loi_tam_thoi(RuntimeError("401 Invalid API Key"))


def test_judge_thu_lai_khi_429_roi_cham_duoc(_khong_ngu):
    from src.test.evaluator import judge_answer
    llm = _LLMGia(so_lan_loi=2, loi=LOI_429)
    kq = judge_answer(llm, "q", "gt", "ctx", "ans")
    assert llm.so_lan_goi == 3
    assert kq["judge_correctness"] == 5.0


def test_judge_khong_thu_lai_loi_khoa(_khong_ngu):
    from src.test.evaluator import judge_answer
    llm = _LLMGia(so_lan_loi=5, loi="401 Invalid API Key")
    kq = judge_answer(llm, "q", "gt", "ctx", "ans")
    assert llm.so_lan_goi == 1                      # thử lại vô ích thì đừng thử
    assert pd.isna(kq["judge_correctness"])
    assert "401" in kq["judge_reasoning"]


def test_judge_het_luot_thi_tra_nan_chu_khong_nem(_khong_ngu):
    from src.test.evaluator import JUDGE_RETRIES, judge_answer
    llm = _LLMGia(so_lan_loi=99, loi=LOI_429)
    kq = judge_answer(llm, "q", "gt", "ctx", "ans")
    assert llm.so_lan_goi == JUDGE_RETRIES
    assert pd.isna(kq["judge_correctness"])
