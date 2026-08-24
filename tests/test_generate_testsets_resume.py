"""Test đường sinh bộ test: resume, ghi ngay, backoff 429, dừng sạch (D-75).

Không gọi LLM thật, không OCR: `llm` là một đối tượng giả đếm số lượt gọi. Mỗi test
neo vào một cách hỏng CỤ THỂ mà bản trước có thật, ghi ở docstring.
"""
import csv
import json

import pytest

BOM = bytes([0xEF, 0xBB, 0xBF])   # BOM cua UTF-8

from src.test import generate_testsets as G


class FakeLLM:
    """Trả JSON hợp lệ; đếm lượt gọi; raise được lỗi hạn mức theo kịch bản."""

    def __init__(self, script=None, n=3):
        self.calls = 0
        self.script = list(script or [])
        self.n = n

    def invoke(self, prompt):
        self.calls += 1
        if self.script:
            action = self.script.pop(0)
            if isinstance(action, Exception):
                raise action
        qs = [{"question": f"Câu {self.calls}.{i}?",
               "ground_truth": f"Đáp {self.calls}.{i}",
               "do_kho": "truc_tiep" if i else "suy_luan"}
              for i in range(self.n)]
        return json.dumps({"answerable": True, "phan_mon": "sinh",
                           "questions": qs}, ensure_ascii=False)


def payload(page_index=20, printed=20):
    return {"text": "x" * 900, "source_book": "SGK_KHTN_6_KNTT",
            "source_page": printed, "source_page_index": page_index,
            "bai_so": 3, "n_chunks": 4, "text_chars": 900}


# --------------------------------------------------------------- nhãn quyển

def test_book_labels_from_the_name():
    assert G.book_labels("SGK_KHTN_9_CD") == {"khoi": "9", "bo_sach": "CD"}
    assert G.book_labels("SGK_KHTN_6_CTST") == {"khoi": "6", "bo_sach": "CTST"}


def test_book_labels_unknown_name_stays_empty():
    """Không nhận ra thì để RỖNG, không đoán một nhà xuất bản — đúng bài học D-71."""
    assert G.book_labels("quyen_la") == {"khoi": "", "bo_sach": ""}


# ------------------------------------------------------------ parse_questions

def test_parse_questions_keeps_labels_and_levels():
    data = {"answerable": True, "phan_mon": "hoa", "questions": [
        {"question": "Q1", "ground_truth": "A1", "do_kho": "truc_tiep"},
        {"question": "Q2", "ground_truth": "A2", "do_kho": "suy_luan"}]}
    rows = G.parse_questions(data, payload(), {"khoi": "8", "bo_sach": "CD"})
    assert [r["do_kho"] for r in rows] == ["truc_tiep", "suy_luan"]
    assert all(r["phan_mon"] == "hoa" and r["khoi"] == "8" for r in rows)


def test_parse_questions_drops_incomplete_items_instead_of_filling():
    data = {"answerable": True, "phan_mon": "sinh", "questions": [
        {"question": "Q1", "ground_truth": "A1", "do_kho": "truc_tiep"},
        {"question": "", "ground_truth": "A2"},          # thiếu câu hỏi
        {"question": "Q3", "ground_truth": ""},          # thiếu đáp án
        "khong phai dict"]}
    rows = G.parse_questions(data, payload(), {})
    assert len(rows) == 1


def test_parse_questions_blanks_a_value_outside_the_closed_set():
    """`phan_mon`/`do_kho` ngoài tập đóng thì để RỖNG — nhãn sai tệ hơn nhãn thiếu."""
    data = {"answerable": True, "phan_mon": "vat ly ung dung", "questions": [
        {"question": "Q", "ground_truth": "A", "do_kho": "sieu_kho"}]}
    rows = G.parse_questions(data, payload(), {})
    assert rows[0]["phan_mon"] == "" and rows[0]["do_kho"] == ""


def test_parse_questions_respects_answerable_false():
    assert G.parse_questions({"answerable": False, "questions": [
        {"question": "Q", "ground_truth": "A"}]}, payload(), {}) == []


# ------------------------------------------------------------- 429 / backoff

def test_ask_llm_retries_then_succeeds():
    exc = RuntimeError("Error code: 429 - rate limit exceeded")
    llm = FakeLLM(script=[exc])
    slept = []
    out = G._ask_llm(llm, "p", sleeper=slept.append)
    assert llm.calls == 2 and slept == [G.RATE_LIMIT_BACKOFF_SECONDS[0]]
    assert "questions" in out


def test_ask_llm_raises_quota_stop_after_the_backoff_list():
    exc = RuntimeError("429 too many requests")
    llm = FakeLLM(script=[exc, exc, exc])
    with pytest.raises(G.QuotaStop):
        G._ask_llm(llm, "p", sleeper=lambda _s: None)
    assert llm.calls == len(G.RATE_LIMIT_BACKOFF_SECONDS) + 1


def test_ask_llm_does_not_swallow_a_non_quota_error():
    """Lỗi khác 429 phải nổi lên nguyên trạng, không bị coi là hết hạn mức."""
    llm = FakeLLM(script=[ValueError("json xấu")])
    with pytest.raises(ValueError):
        G._ask_llm(llm, "p", sleeper=lambda _s: None)


@pytest.mark.parametrize("text,expected", [
    ("Error code: 429", True),
    ("Rate limit reached for model", True),
    ("insufficient quota", True),
    ("connection reset by peer", False),
    ("Expecting value: line 1 column 1", False),
])
def test_rate_limit_detection(text, expected):
    assert G._is_rate_limited(RuntimeError(text)) is expected


# ----------------------------------------------------------- CSV: ghi & resume

def test_rows_in_csv_reads_back_what_was_appended(tmp_path):
    path = tmp_path / "t.csv"
    G._append_rows(path, [{**payload(21), "question": "Q", "ground_truth": "A"}])
    G._append_rows(path, [{**payload(22), "question": "Q2", "ground_truth": "A2"}])
    count, done = G._rows_in_csv(path)
    assert count == 2 and done == {21, 22}


def test_append_does_not_repeat_the_bom(tmp_path):
    """`utf-8-sig` mở ở chế độ APPEND có ghi lại BOM giữa file không?

    Cả thiết kế resume đứng trên câu trả lời này. ĐÃ ĐO: 3 tiến trình khác nhau
    lần lượt append vào cùng một file -> **đúng 1 BOM**, ở đầu file. Nếu Python
    đổi hành vi đó thì CSV sẽ có BOM giữa dòng và cột đầu của lô thứ hai bị hỏng,
    nên test này neo lại điều đã đo.
    """
    path = tmp_path / "t.csv"
    for page in (21, 22, 23):
        G._append_rows(path, [{**payload(page), "question": "Q",
                               "ground_truth": "A"}])
    assert path.read_bytes().count(BOM) == 1


def test_append_writes_the_header_once(tmp_path):
    path = tmp_path / "t.csv"
    for page in (21, 22):
        G._append_rows(path, [{**payload(page), "question": "Q",
                               "ground_truth": "A"}])
    with path.open(encoding="utf-8-sig") as f:
        assert sum(1 for line in f if line.startswith("question,")) == 1


def test_rows_in_csv_on_a_missing_file_is_empty(tmp_path):
    assert G._rows_in_csv(tmp_path / "chua_co.csv") == (0, set())


# ------------------------------------------------- meta ghi được cảnh báo tương quan

def test_meta_records_gold_page_count_and_the_correlation_warning(tmp_path):
    path = tmp_path / "SGK_KHTN_6_KNTT_testset.csv"
    rows = [{**payload(30, 30), "question": f"Q{i}", "ground_truth": "A",
             "do_kho": "truc_tiep", "phan_mon": "sinh"} for i in range(3)]
    rows += [{**payload(31, 31), "question": "Q4", "ground_truth": "A",
              "do_kho": "suy_luan", "phan_mon": "ly"}]
    G._append_rows(path, rows)

    class Args:
        per_book, seed = 25, 42
    meta_path = G._write_meta(tmp_path, [path], Args())
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    assert meta["human_reviewed"] is False
    assert meta["n_questions"] == 4 and meta["n_gold_pages"] == 2
    assert meta["by_do_kho"] == {"truc_tiep": 3, "suy_luan": 1}
    assert meta["missing_difficulty"] == G.MISSING_DIFFICULTY
    assert "tương quan" in meta["correlated_questions_warning"]


def test_meta_says_seed_only_fixes_page_order():
    """`seed` từng bị đọc thành "bộ test tái tạo được từng chữ" — nói rõ ra."""
    class Args:
        per_book, seed = 25, 42
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as d:
        meta = json.loads(G._write_meta(pathlib.Path(d), [], Args())
                          .read_text(encoding="utf-8"))
    assert "trang" in meta["seed_scope"] and "0.7" in meta["seed_scope"]
