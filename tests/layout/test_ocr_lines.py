# -*- coding: utf-8 -*-
from src.etl.layout.ocr_lines import group_lines


def _word(text, line=0, left=0, top=0, w=20, h=18, block=1, par=1, conf=90):
    return {"text": text, "block_num": block, "par_num": par, "line_num": line,
            "left": left, "top": top, "width": w, "height": h, "conf": conf}


def test_words_of_one_line_become_one_line_with_union_bbox():
    words = [_word("hấp", left=10, top=100, w=40),
             _word("thụ", left=60, top=100, w=40),
             _word("khí", left=110, top=98, w=40, h=22)]

    lines = group_lines(words)

    assert len(lines) == 1
    assert lines[0]["text"] == "hấp thụ khí"
    assert lines[0]["bbox"] == (10, 98, 150, 120)


def test_two_columns_stay_separate_by_block_num():
    left_col = [_word("cột", block=1, line=0, left=0, top=0),
                _word("trái", block=1, line=0, left=40, top=0)]
    right_col = [_word("cột", block=2, line=0, left=500, top=0),
                 _word("phải", block=2, line=0, left=540, top=0)]

    lines = group_lines(left_col + right_col)

    assert len(lines) == 2
    assert {l["text"] for l in lines} == {"cột trái", "cột phải"}


def test_empty_word_text_is_skipped():
    words = [_word("thật", left=0), _word("  ", left=30), _word("sự", left=60)]

    lines = group_lines(words)

    assert lines[0]["text"] == "thật sự"
