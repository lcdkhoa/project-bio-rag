from src.etl.diacritic import fix_diacritics

def test_fixes_known_confusions():
    assert fix_diacritics("nước đá vẫn được tạo thành") == "nước đá vẫn được tạo thành"
    assert fix_diacritics("phát triên của sinh vật") == "phát triển của sinh vật"
    assert fix_diacritics("Trái Đât") == "Trái Đất"

def test_preserves_science_and_english_terms():
    assert fix_diacritics("Sulfuric acid H2SO4") == "Sulfuric acid H2SO4"
    assert fix_diacritics("oxygen CO2") == "oxygen CO2"

def test_idempotent():
    once = fix_diacritics("phát triên")
    assert fix_diacritics(once) == once

def test_context_guard_fires_adjacent():
    once = fix_diacritics("sự tổn tại")
    assert once == "sự tồn tại"
    assert fix_diacritics(once) == once

def test_context_guard_fires_across_punctuation():
    once = fix_diacritics("sự, tổn tại")
    assert once == "sự, tồn tại"
    assert fix_diacritics(once) == once

def test_context_guard_fires_at_two_token_distance():
    once = fix_diacritics("sản xuất giây")
    assert once == "sản xuất giấy"
    assert fix_diacritics(once) == once

def test_context_guard_does_not_fire_without_trigger():
    once = fix_diacritics("một giây trôi qua")
    assert once == "một giây trôi qua"
    assert fix_diacritics(once) == once
