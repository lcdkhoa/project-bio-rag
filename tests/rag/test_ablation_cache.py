# -*- coding: utf-8 -*-
"""Bộ nhớ đệm của bảng đối chiếu: đắt, nên không được huỷ nhầm và phải resume."""

import json

import pytest

from src.test import retrieval_benchmark
from src.test.retrieval_benchmark import Cache, load_cache


def _cache(n=3, digest="dig", version="vTEST", params="k1=0.7 b=0.75 tok=plain n=50"):
    return Cache(
        index_digest=digest,
        text_version=version,
        sparse_params=params,
        dense={f"câu {i}": [(f"c{i}", 0.1 * i)] for i in range(n)},
        rerank={f"câu {i}": {f"c{i}": 0.9} for i in range(n)},
    )


class FakeCollection:
    def get(self, include=None, limit=None):
        return {"ids": ["a", "b"]}


def test_json_di_ve_khong_mat_gi(tmp_path):
    c = _cache()
    p = tmp_path / "ab.json"
    p.write_text(json.dumps(c.to_json(), ensure_ascii=False), encoding="utf-8")
    back = Cache.from_json(json.loads(p.read_text(encoding="utf-8")))
    assert back.dense == c.dense and back.rerank == c.rerank
    assert back.sparse_params == c.sparse_params


def test_dem_thuoc_index_KHAC_thi_raise(tmp_path, monkeypatch):
    p = tmp_path / "ab.json"
    p.write_text(json.dumps(_cache(digest="cu").to_json(), ensure_ascii=False),
                 encoding="utf-8")
    monkeypatch.setattr(retrieval_benchmark, "chunk_ids_digest", lambda ids: "moi")
    with pytest.raises(RuntimeError, match="digest"):
        load_cache(p, FakeCollection())


def test_doi_tham_so_kenh_thua_thi_raise_TRU_KHI_sap_topup(tmp_path, monkeypatch):
    p = tmp_path / "ab.json"
    p.write_text(json.dumps(_cache(params="k1=1.2 b=0.75 tok=folded n=50").to_json(),
                            ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(retrieval_benchmark, "chunk_ids_digest", lambda ids: "dig")
    monkeypatch.setattr(retrieval_benchmark, "TEXT_EXTRACTION_VERSION", "vTEST")

    with pytest.raises(RuntimeError, match="tham số thưa"):
        load_cache(p, FakeCollection())
    got = load_cache(p, FakeCollection(), check_sparse_params=False)
    assert len(got.dense) == 3


def test_thieu_dem_thi_raise_chu_khong_cham_tren_phan_da_co(tmp_path):
    cache = _cache(n=2)
    cfg = retrieval_benchmark.Config(mode="dense", rerank=False, gate=False)
    with pytest.raises(RuntimeError, match="thiếu câu hỏi"):
        retrieval_benchmark.rank_for(cfg, "câu 99", cache, sparse=None, top_n=5)
