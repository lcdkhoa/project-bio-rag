"""Regression tests for the "cho tôi hình con cá" false-positive bug.

Measured on the real index (biology_image_metadata, 3,881 docs, 2026-08-27):
129 docs match standalone token "cá"; a 15-doc sample was only ~3 genuine
fish, the rest mostly "cá heo" (dolphin), "cá sấu" (crocodile), "cá thể"
(individual, a population-biology term). Live repro before the fix: query
"cho tôi hình con cá có trong bài học" gave phrase "con cá" an identical
phrase_score=1.0 against both a real fish doc and a dolphin doc.
"""

from langchain_core.documents import Document

import src.rag.image_vectorstore as M
from src.rag.image_vectorstore import ImageVectorDB


def _bare_db():
    return ImageVectorDB.__new__(ImageVectorDB)   # bypass heavy __init__ (no CLIP)


def _doc(**metadata):
    return Document(page_content="", metadata=metadata)


QUERY = "cho tôi hình con cá có trong bài học"


def test_phrase_match_does_not_swallow_dolphin():
    db = _bare_db()
    dolphin = _doc(crop_text="Con cá heo Con trâu Con dơi Con khỉ Hình 23.11")
    assert db._phrase_match_score(QUERY, dolphin) == 0.0


def test_phrase_match_does_not_swallow_crocodile():
    db = _bare_db()
    croc = _doc(crop_text="Hình 38.11 Cá sấu Lớp Chim là nhóm động vật")
    assert db._phrase_match_score(QUERY, croc) == 0.0


def test_phrase_match_still_finds_real_fish():
    db = _bare_db()
    fish = _doc(crop_text="Hình 25.5 Con cá rô phi Con thỏ Con chim bồ câu")
    assert db._phrase_match_score(QUERY, fish) == 1.0


def test_tokenize_drops_individual_bare_ca_from_ca_the():
    db = _bare_db()
    toks = db._tokenize("một nhóm cá thể là quần thể sinh vật")
    assert "cá" not in toks


def test_tokenize_keeps_bare_ca_for_real_fish_text():
    db = _bare_db()
    toks = db._tokenize("con cá rô phi con thỏ")
    assert "cá" in toks


def test_direct_evidence_score_ignores_dolphin_and_crocodile():
    db = _bare_db()
    dolphin = _doc(lesson_title="Con cá heo Con trâu Con dơi Con khỉ")
    assert db._direct_evidence_score(QUERY, dolphin) == 0.0


def test_clip_hint_expansion_is_word_bounded():
    db = _bare_db()
    # "các"/"cách"/"cao" all contain "ca" as a raw substring but must NOT
    # trigger the "ca" -> "fish" hint any more.
    assert db._expand_query_for_clip("cách chăm sóc cây thế nào") == "cách chăm sóc cây thế nào"
    assert db._expand_query_for_clip("chiều cao của cây") == "chiều cao của cây"


def test_clip_hint_expansion_still_fires_on_real_token():
    db = _bare_db()
    expanded = db._expand_query_for_clip("cho tôi hình con cá")
    assert "fish" in expanded
