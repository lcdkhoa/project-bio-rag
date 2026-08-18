"""Regression test: filename-based checkpoint must not mask hash-based re-processing.

Bug: a replaced PDF that reuses an old filename but has new content (new hash)
was being skipped by main.run_etl_text_only because the skip decision was based
on `filename in processed_files.txt`. The truth source must be the hash-derived
`pages_needing_text` list from ProcessingStatus, not the filename log.
"""
from main import _should_skip_file


def test_same_name_new_hash_not_skipped():
    # a file already in the (advisory, no-longer-consulted) name list but whose pages
    # still need text must NOT be skipped
    assert _should_skip_file("SGK KHTN8 KNTT.pdf", pages_needing_text=[1, 2, 3]) is False


def test_fully_done_file_skipped():
    assert _should_skip_file("x.pdf", pages_needing_text=[]) is True
