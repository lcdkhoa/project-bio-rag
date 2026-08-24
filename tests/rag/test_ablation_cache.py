# -*- coding: utf-8 -*-
"""Bộ nhớ đệm của bảng ablation: đắt, nên không được huỷ nhầm và phải resume.

Lý do có file này là một lỗi đã cắn thật trong lượt xây nó: `--build-cache` bắt
đầu từ RỖNG mà `_save` lại ghi đè CÙNG một file sau mỗi 10 câu — nên một lượt bị
giết giữa chừng **thay đệm 100 câu bằng đệm 20 câu**, mất 51 phút CPU.
"""

import json

import pytest

from src.test import ablation
from src.test.ablation import Cache, load_cache


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
    monkeypatch.setattr(ablation, "chunk_ids_digest", lambda ids: "moi")
    with pytest.raises(RuntimeError, match="digest"):
        load_cache(p, FakeCollection())


def test_doi_tham_so_kenh_thua_thi_raise_TRU_KHI_sap_topup(tmp_path, monkeypatch):
    p = tmp_path / "ab.json"
    p.write_text(json.dumps(_cache(params="k1=1.2 b=0.75 tok=folded n=50").to_json(),
                            ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(ablation, "chunk_ids_digest", lambda ids: "dig")
    monkeypatch.setattr(ablation, "TEXT_EXTRACTION_VERSION", "vTEST")

    with pytest.raises(RuntimeError, match="tham số thưa"):
        load_cache(p, FakeCollection())
    # `--topup-cache` phải nạp được để còn chấm bù — đó là cả mục đích của nó.
    got = load_cache(p, FakeCollection(), check_sparse_params=False)
    assert len(got.dense) == 3


def test_thieu_dem_thi_raise_chu_khong_cham_tren_phan_da_co(tmp_path):
    """Đệm dựng dở mà vẫn chấm = recall thấp đi ÂM THẦM."""
    cache = _cache(n=2)
    cfg = ablation.Config(mode="dense", rerank=False, gate=False)
    with pytest.raises(RuntimeError, match="thiếu câu hỏi"):
        ablation.rank_for(cfg, "câu 99", cache, sparse=None, top_n=5)


def test_bm25_thuan_KHONG_can_dem_day(tmp_path):
    """Chế độ bm25 không đụng phần dày, nên đệm thiếu cũng không sao."""
    class FakeSparse:
        def search(self, query, k, k1, b, fold_accents=True, formula=True):
            return [("c1", 5.0), ("c2", 3.0)]

    cfg = ablation.Config(mode="bm25", rerank=False, gate=False)
    got = ablation.rank_for(cfg, "câu chưa từng đệm", _cache(n=0), FakeSparse(), 5)
    assert got == ["c1", "c2"]
