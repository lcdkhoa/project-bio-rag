# -*- coding: utf-8 -*-
"""Chỉ mục thưa phải TỰ TỐ khi nó cũ hơn index dày.

Đây là test của một cách hỏng **im lặng**, cùng lớp với D-52 (image doc mồ côi)
và với "rerank tắt âm thầm dưới HF_HUB_OFFLINE=1". Cả hai lần trước đều lọt qua
test suite, nên lần này viết test cho đúng cái đó.
"""

import pytest

from src.rag import sparse_store
from src.rag.bm25 import BM25Index, SparseIndexStale, live_fingerprint


class FakeCollection:
    name = "biology_text"

    def __init__(self, rows):
        self.rows = rows

    def get(self, include=None, limit=None):
        out = {"ids": [r[0] for r in self.rows]}
        if include and "documents" in include:
            out["documents"] = [r[1] for r in self.rows]
        return out


ROWS = [("S#h_p1_c0", "quang hợp ở lá cây"), ("S#h_p2_c0", "định luật Ohm")]


@pytest.fixture(autouse=True)
def _reset():
    sparse_store.reset_cache()
    yield
    sparse_store.reset_cache()


def test_dung_roi_nap_lai_thi_khop(tmp_path, monkeypatch):
    col = FakeCollection(ROWS)
    monkeypatch.setattr(sparse_store, "open_text_collection", lambda *a, **k: col)
    sparse_store.build_sparse_index(index_dir=tmp_path)
    sparse_store.reset_cache()
    idx = sparse_store.get_sparse_index(index_dir=tmp_path, collection=col)
    assert idx.ids == [r[0] for r in ROWS]


def test_index_THEM_chunk_thi_chi_muc_thua_RAISE(tmp_path, monkeypatch):
    col = FakeCollection(ROWS)
    monkeypatch.setattr(sparse_store, "open_text_collection", lambda *a, **k: col)
    sparse_store.build_sparse_index(index_dir=tmp_path)
    sparse_store.reset_cache()

    moi = FakeCollection(ROWS + [("S#h_p3_c0", "nam châm điện")])
    with pytest.raises(SparseIndexStale, match="n_chunks"):
        sparse_store.get_sparse_index(index_dir=tmp_path, collection=moi)


def test_index_DOI_NOI_DUNG_ma_GIU_nguyen_so_chunk_van_bi_bat(tmp_path, monkeypatch):
    """Đếm số chunk là KHÔNG đủ — đây chính là lý do dấu vân phải có digest."""
    col = FakeCollection(ROWS)
    monkeypatch.setattr(sparse_store, "open_text_collection", lambda *a, **k: col)
    sparse_store.build_sparse_index(index_dir=tmp_path)
    sparse_store.reset_cache()

    doi = FakeCollection([("S#KHAC_p1_c0", ROWS[0][1]), ROWS[1]])
    with pytest.raises(SparseIndexStale, match="ids_digest"):
        sparse_store.get_sparse_index(index_dir=tmp_path, collection=doi)


def test_doi_TEXT_EXTRACTION_VERSION_thi_RAISE(tmp_path, monkeypatch):
    col = FakeCollection(ROWS)
    monkeypatch.setattr(sparse_store, "open_text_collection", lambda *a, **k: col)
    sparse_store.build_sparse_index(index_dir=tmp_path)
    sparse_store.reset_cache()

    monkeypatch.setattr(sparse_store, "TEXT_EXTRACTION_VERSION", "v99_sau_khi_OCR_lai")
    with pytest.raises(SparseIndexStale, match="text_extraction_version"):
        sparse_store.get_sparse_index(index_dir=tmp_path, collection=col)


def test_index_RONG_thi_raise_chu_khong_dung_chi_muc_rong(tmp_path, monkeypatch):
    col = FakeCollection([])
    monkeypatch.setattr(sparse_store, "open_text_collection", lambda *a, **k: col)
    with pytest.raises(RuntimeError, match="--text-only"):
        sparse_store.build_sparse_index(index_dir=tmp_path)


def test_live_fingerprint_chi_doc_id_khong_doc_van_ban():
    """Đọc dấu vân phải RẺ — nó chạy mỗi lần nạp chỉ mục thưa."""
    class OnlyIds(FakeCollection):
        def get(self, include=None, limit=None):
            assert not include, f"live_fingerprint không được yêu cầu {include}"
            return {"ids": [r[0] for r in self.rows]}

    fp = live_fingerprint(OnlyIds(ROWS), tokenizer="plain",
                          text_extraction_version="v2")
    assert fp.n_chunks == 2 and fp.tokenizer == "plain"
