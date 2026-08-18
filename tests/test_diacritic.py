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
