"""Kiểm tra âm tiết = CHỈ GẮN CỜ. Không hàm nào ở đây được phép đổi ký tự.

Bản cũ (`fix_diacritics`) tự ghi lại chữ: sửa được 3/6500 token trên corpus thật
trong khi có toàn quyền thay ký tự trong sách giáo khoa. Test đầu tiên dưới đây
là cái chốt cửa: module này không còn export hàm sửa chữ nào nữa.
"""
import src.etl.diacritic as D
from src.etl.diacritic import diacritic_review_flags, is_valid_syllable


def test_the_rewriting_api_is_gone():
    assert not hasattr(D, "fix_diacritics")


def test_flags_a_token_mixing_letters_and_digits():
    # `kh6ng`, `1a`: dấu hiệu OCR hỏng đã đo được (0,10–0,15% token).
    assert diacritic_review_flags("vật kh6ng thể") == ["kh6ng"]
    assert diacritic_review_flags("có 1a trong đó") == ["1a"]


def test_flags_a_closed_syllable_that_lost_its_tone_mark():
    # Luật chính tả thật: âm tiết đóng bởi p/t/c/ch chỉ nhận sắc hoặc nặng, nên
    # "mat" (mất dấu của "mát"/"mạt") là không hợp lệ và bị gắn cờ.
    assert diacritic_review_flags("trời mat quá") == ["mat"]
    assert diacritic_review_flags("trời mát quá") == []


def test_flags_impossible_onsets_and_double_tones():
    assert diacritic_review_flags("nggười ta") == ["nggười"]
    assert is_valid_syllable("chế") and is_valid_syllable("ché")


def test_does_not_flag_ordinary_vietnamese_text():
    text = ("Quang hợp là quá trình tổng hợp chất hữu cơ, trong đó nguyên liệu "
            "gồm nước và khí carbon dioxide; sản phẩm là tinh bột và khí oxygen. "
            "Nghiên cứu Hình 1.2 rồi trả lời câu hỏi ở khung bên phải.")
    assert diacritic_review_flags(text) == []


def test_does_not_flag_units_abbreviations_and_formulas():
    assert diacritic_review_flags("dài 5 km, nặng 2 kg, H2SO4, CO2, ADN") == []


def test_does_not_flag_long_transliterated_loanwords():
    # "cacbon", "amoniac", "hidroxit": viết liền nhiều âm tiết, không dấu — luật
    # âm tiết không áp dụng được, và flag chúng thì người xem sẽ ngập nhiễu.
    assert diacritic_review_flags("cacbon amoniac hidroxit protein") == []


def test_flag_list_is_capped_and_deduplicated():
    flags = diacritic_review_flags("kh6ng " * 5 + " ".join(f"m{i}t" for i in range(30)))
    assert flags[0] == "kh6ng"
    assert len(flags) == D.MAX_FLAGS_PER_UNIT
    assert len(set(flags)) == len(flags)
