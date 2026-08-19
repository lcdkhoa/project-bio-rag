import src.rag.image_vectorstore as M
from src.rag.image_vectorstore import ImageVectorDB


def _bare_db():
    return ImageVectorDB.__new__(ImageVectorDB)   # no CLIP / no chroma


def test_fold_accents_folds_d_stroke():
    # callers pre-lowercase via normalize_accented_text; case is preserved
    # (mirrors citations._fold), so lowercase đ -> d and uppercase Đ -> D.
    assert M._fold_accents("được") == "duoc"
    assert M._fold_accents("đom đóm") == "dom dom"
    assert M._fold_accents("Đá vôi") == "Da voi"


def test_dstroke_stopword_is_dropped_from_tokens():
    db = _bare_db()
    # "được" is meant to be a stopword ("duoc" is in _STOPWORDS) but strip_accents
    # leaves "đ" so it used to leak in as a content token; folding fixes it.
    toks = db._tokenize("được con trâu")
    bare = [M._fold_accents(t) for t in toks]
    assert "duoc" not in bare


def test_dstroke_filler_dropped_from_phrases():
    db = _bare_db()
    phrases, match_tokens = db._query_content_phrases("cho tôi hình được con trâu")
    joined = " ".join(phrases)
    assert "được" not in joined            # filler folded out
    assert any("trâu" in p for p in phrases)   # real object preserved (accents kept)
