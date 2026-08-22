"""Phép so của cổng G3 — bỏ dấu, độ phủ có trọng số IDF, luật đáp án NGẮN.

Test nhanh, không cần index và không cần LLM: IDF được truyền vào tường minh nên
mọi phép so đều xác định.

Chỗ dễ sai âm thầm mà các test này khoá lại:
- "đ" không tách được bằng NFD, phải fold riêng;
- **không được dùng danh sách stopword trên dạng đã bỏ dấu** — nó xoá đúng những
  từ nội dung của sách KHTN ("khí"->"khi", "đo"/"độ"->"do", "lá"->"la", "tai",
  "đá"->"da", "cân"->"can");
- chữ số một kí tự ("6 giai đoạn") không được bị cắt vì ngắn;
- đáp án chỉ còn <= 3 token đặc trưng thì trúng một phần KHÔNG phải bằng chứng.
"""
from __future__ import annotations

import math

import pytest

from src.test.qa_citation_page import (
    SHORT_ANSWER_TOKENS,
    UNINFORMATIVE_IDF,
    build_idf,
    coverage,
    fold,
    informative_tokens,
    page_supports_answer,
    tokens_of,
)

# Ngưỡng CỐ ĐỊNH của riêng test, CỐ Ý không import từ `qa_citation_page`: các test
# dưới đây khoá HÀNH VI của `page_supports_answer` (ba nhánh: không token đặc
# trưng / đáp án ngắn / phủ >= ngưỡng), chứ không khoá giá trị cấu hình. Nên nó
# không đổi theo lần hiệu chỉnh nào. Giá trị production hiện là 0,50 (D-57) và
# việc hai số này khác nhau là bình thường — đừng "sửa" cho khớp.
COVERAGE_MIN = 0.60

# Ba "trang" tí hon đủ để IDF có nghĩa: từ có ở cả ba -> trọng số ~0.
PAGES = [
    "Dụng cụ đo nhiệt độ được gọi là nhiệt kế. Nhiệt kế y tế thuỷ ngân.",
    "Nước tồn tại ở thể rắn, thể lỏng và thể khí. Sự nóng chảy và sự đông đặc.",
    "Quá trình gồm giai đoạn đầu và giai đoạn cuối của sự bay hơi.",
]


@pytest.fixture(scope="module")
def idf():
    return build_idf(PAGES)


def test_fold_handles_d_stroke():
    assert fold("Đường được đo") == "duong duoc do"
    assert fold("Nhiệt độ nóng chảy") == "nhiet do nong chay"


def test_single_digit_survives_tokenising():
    """"6 giai đoạn": chữ "6" là token phân biệt duy nhất, không được cắt."""
    assert "6" in tokens_of("6 giai đoạn")
    assert "o" not in tokens_of("ở trong")   # chữ cái đơn vẫn bị cắt


def test_content_words_are_not_stripped_as_stopwords(idf):
    """"khí", "đo", "lá", "tai", "đá", "cân" phải còn lại sau khi bỏ dấu."""
    for word, folded in [("khí", "khi"), ("đo", "do"), ("lá", "la"),
                         ("tai", "tai"), ("đá", "da"), ("cân", "can")]:
        assert folded in tokens_of(f"cái {word} ở đây")


def test_idf_downweights_words_present_on_every_page(idf):
    """Từ có ở cả 3 trang -> idf dưới ngưỡng "không mang thông tin"."""
    assert idf["su"] < UNINFORMATIVE_IDF          # "sự" có ở trang 2 và 3
    assert idf["nhiet"] >= UNINFORMATIVE_IDF      # chỉ trang 1


def test_coverage_is_set_based_not_frequency(idf):
    cov_once, _ = coverage("nhiệt kế thuỷ ngân", "có nhiệt kế thuỷ ngân", idf)
    cov_many, _ = coverage("nhiệt kế thuỷ ngân",
                           "nhiệt kế " * 10 + "thuỷ ngân", idf)
    assert cov_once == pytest.approx(cov_many)


def test_long_answer_needs_only_partial_coverage(idf):
    gt = "Nước tồn tại ở thể rắn, thể lỏng và thể khí trên Trái Đất."
    ok, cov, n = page_supports_answer(gt, PAGES[1], COVERAGE_MIN, idf)
    assert ok and cov >= COVERAGE_MIN and n > SHORT_ANSWER_TOKENS


def test_long_answer_rejected_when_page_is_unrelated(idf):
    gt = "Nước tồn tại ở thể rắn, thể lỏng và thể khí trên Trái Đất."
    ok, cov, _ = page_supports_answer(gt, PAGES[0], COVERAGE_MIN, idf)
    assert not ok and cov < COVERAGE_MIN


@pytest.mark.parametrize("page_text,expected", [
    ("Dụng cụ đo nhiệt độ được gọi là nhiệt kế.", True),
    # chỉ có "nhiệt" mà không có "kế" -> trúng một phần, KHÔNG được tính
    ("Nhiệt độ là số đo độ nóng, lạnh của vật.", False),
])
def test_short_answer_requires_every_informative_token(idf, page_text, expected):
    ok, _, n = page_supports_answer("nhiệt kế", page_text, COVERAGE_MIN, idf)
    assert n <= SHORT_ANSWER_TOKENS
    assert ok is expected


def test_short_answer_partial_hit_is_not_evidence(idf):
    """Đáp án "6 giai đoạn": trang có "giai đoạn" nhưng KHÔNG có "6" -> loại.

    Đây chính là ca mà bản stopword cũ đã kết luận SAI: "sáu" bị bỏ dấu thành
    "sau" rồi bị coi là stopword, nên chỉ còn {giai, doan} và trang không liên
    quan vẫn "phủ 100%".
    """
    ok, cov, n = page_supports_answer("6 giai đoạn", PAGES[2], COVERAGE_MIN, idf)
    assert n <= SHORT_ANSWER_TOKENS
    assert cov > COVERAGE_MIN     # phủ vẫn cao...
    assert not ok                 # ...nhưng thiếu token phân biệt -> KHÔNG đạt


def test_answer_token_absent_from_whole_index_lowers_coverage(idf):
    """Token không có trong index nào phải mang trọng số CAO NHẤT.

    Nếu cho nó trọng số 0 thì một đáp án chứa thứ không có trong sách sẽ được
    "phủ 100%" — đúng kiểu bịa mà cổng này phải bắt.
    """
    weights_seen = idf["nhiet"]
    cov, _ = coverage("nhiệt kế mitochondria", PAGES[0], idf)
    assert cov < 1.0
    assert max(idf.values()) >= weights_seen


def test_empty_ground_truth_is_never_supported(idf):
    ok, cov, n = page_supports_answer("   ", PAGES[0], COVERAGE_MIN, idf)
    assert not ok and n == 0 and cov == 0.0


def test_no_idf_falls_back_to_uniform_weights():
    """Không có index thì mọi token nặng bằng nhau, vẫn phải chạy được."""
    ok, cov, n = page_supports_answer(
        "nước tồn tại ở thể rắn thể lỏng thể khí", PAGES[1], COVERAGE_MIN, None)
    assert n > 0 and cov > 0 and ok


def test_uninformative_threshold_is_derived_not_typed():
    assert UNINFORMATIVE_IDF == pytest.approx(math.log(2.0))


def test_contains_phrase_tolerates_ocr_tone_errors():
    """OCR ra "nhiệt ké" (mất dấu) vẫn phải khớp "nhiệt kế" vì cả hai đã bỏ dấu."""
    from src.test.qa_citation_page import contains_phrase

    assert contains_phrase("nhiệt kế", "Dụng cụ đo nhiệt độ gọi là nhiệt ké.")
    assert not contains_phrase("nhiệt kế", "Nhiệt độ là số đo độ nóng lạnh.")


def test_contains_phrase_needs_contiguity():
    """Hai từ có mặt nhưng KHÔNG liền nhau thì không phải cụm từ."""
    from src.test.qa_citation_page import contains_phrase

    assert not contains_phrase("nhiệt kế", "nhiệt độ và cái kế bên")


def test_zero_informative_answer_falls_back_to_phrase(idf):
    """Đáp án toàn từ phổ biến -> chỉ nhận nếu cụm từ có nguyên văn trên trang.

    Đây là ca thật gặp khi chạy thử trên index 16 trang: index toàn nói về nhiệt
    nên "nhiệt kế" không còn token nào đặc trưng, và luật cũ trả FALSE dù trang
    ghi rõ "gọi là nhiệt kế".
    """
    flat = build_idf(["nhiet ke o day", "nhiet ke o kia", "nhiet ke lan nua"])
    ok_phrase, _, n = page_supports_answer(
        "nhiệt kế", "dụng cụ gọi là nhiệt kế", COVERAGE_MIN, flat)
    ok_no_phrase, _, _ = page_supports_answer(
        "nhiệt kế", "nhiệt độ và cái kế bên", COVERAGE_MIN, flat)
    assert n == 0
    assert ok_phrase and not ok_no_phrase
