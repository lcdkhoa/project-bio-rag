# -*- coding: utf-8 -*-
"""Test đường truy xuất thưa+dày. Fake toàn bộ — không chạm index thật.

Test then chốt: `test_hybrid_tat_kenh_thua_ra_DUNG_dense_thuan`. §3.3 gọi nó là
tự kiểm bắt buộc: nếu "hybrid" bỏ kênh thưa mà không cho ra **đúng** kết quả của
dense thuần thì đường ống có nhánh ẩn.
"""

from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

from src.rag.hybrid_text_retriever import ChunkLookup, HybridTextRetriever


# --- Đồ giả ---------------------------------------------------------------

CHUNKS = [
    ("S#h_p10_c0", "Quang hợp diễn ra chủ yếu ở lá cây", "S", 10, 0),
    ("S#h_p10_c1", "Diệp lục hấp thụ ánh sáng mặt trời", "S", 10, 1),
    ("S#h_p11_c0", "Hô hấp tế bào giải phóng năng lượng", "S", 11, 0),
    ("S#h_p12_c0", "Nam châm có hai cực bắc và nam", "S", 12, 0),
]


class FakeCollection:
    def __init__(self, chunks=CHUNKS):
        self._chunks = chunks

    def get(self, include=None, limit=None):
        return {
            "ids": [c[0] for c in self._chunks],
            "documents": [c[1] for c in self._chunks],
            "metadatas": [
                {"source": c[2], "page_index": c[3], "chunk_index": c[4],
                 "page": c[3], "region_type": "body"}
                for c in self._chunks
            ],
        }


class FakeVectorStore:
    """Trả (Document, khoảng cách) — nhỏ hơn là gần hơn."""

    def __init__(self, ranked):
        self.ranked = ranked

    def similarity_search_with_score(self, query, k):
        out = []
        for cid, dist in self.ranked[:k]:
            row = next(c for c in CHUNKS if c[0] == cid)
            out.append((Document(page_content=row[1],
                                 metadata={"source": row[2],
                                           "page_index": row[3],
                                           "chunk_index": row[4],
                                           "page": row[3]}), dist))
        return out


class FakeSparse:
    def __init__(self, ranked):
        self.ranked = ranked

    def search(self, query, k, k1, b, fold_accents=True, formula=True):
        return self.ranked[:k]


DENSE = [("S#h_p10_c0", 0.10), ("S#h_p11_c0", 0.20), ("S#h_p12_c0", 0.90)]
SPARSE = [("S#h_p10_c1", 9.0), ("S#h_p10_c0", 4.0)]


def make(mode, **kw):
    kw.setdefault("gate_enabled", False)
    kw.setdefault("rerank_enabled", False)
    return HybridTextRetriever(
        vectorstore=FakeVectorStore(DENSE),
        lookup=ChunkLookup(FakeCollection()),
        sparse=FakeSparse(SPARSE),
        mode=mode,
        max_k=10,
        **kw,
    )


def ids(docs):
    return [d.page_content for d in docs]


# --- Tự kiểm bắt buộc -----------------------------------------------------

def test_hybrid_tat_kenh_thua_ra_DUNG_dense_thuan():
    """Hybrid với kênh thưa RỖNG phải trùng từng phần tử với dense thuần."""
    r_dense = make("dense")
    r_hybrid = make("hybrid")
    r_hybrid.sparse = FakeSparse([])
    assert ids(r_hybrid.invoke("quang hợp")) == ids(r_dense.invoke("quang hợp"))


def test_dense_thuan_KHONG_goi_kenh_thua():
    class Exploding:
        def search(self, *a, **k):
            raise AssertionError("dense thuần không được chạm kênh thưa")

    r = make("dense")
    r.sparse = Exploding()
    assert r.invoke("quang hợp")


def test_bm25_thuan_KHONG_goi_kenh_day():
    class Exploding:
        def similarity_search_with_score(self, *a, **k):
            raise AssertionError("BM25 thuần không được chạm kênh dày")

    r = make("bm25")
    r.vectorstore = Exploding()
    assert ids(r.invoke("quang hợp")) == [
        "Diệp lục hấp thụ ánh sáng mặt trời", "Quang hợp diễn ra chủ yếu ở lá cây"]


def test_thieu_chi_muc_thua_thi_RAISE_chu_khong_am_tham_thanh_dense():
    r = make("hybrid")
    r.sparse = None
    with pytest.raises(RuntimeError, match="--build-bm25"):
        r.invoke("quang hợp")


# --- Hợp nhất thật sự có tác dụng ----------------------------------------

def test_hybrid_keo_len_ket_qua_CHI_kenh_thua_tim_duoc():
    """`p10_c1` không có trong top dày — hybrid phải đưa nó vào."""
    dense_only = ids(make("dense").invoke("q"))
    hybrid = ids(make("hybrid").invoke("q"))
    assert "Diệp lục hấp thụ ánh sáng mặt trời" not in dense_only
    assert "Diệp lục hấp thụ ánh sáng mặt trời" in hybrid


def test_metadata_ghi_ro_ung_vien_den_tu_kenh_nao():
    docs = make("hybrid").invoke("q")
    kenh = {d.page_content: d.metadata["retrieval_channels"] for d in docs}
    assert kenh["Quang hợp diễn ra chủ yếu ở lá cây"] == "dense+sparse"
    assert kenh["Diệp lục hấp thụ ánh sáng mặt trời"] == "sparse"
    assert kenh["Hô hấp tế bào giải phóng năng lượng"] == "dense"


# --- Rerank: KHÔNG được tắt âm thầm --------------------------------------

def test_reranker_hong_thi_RAISE_chu_khong_xep_theo_diem_hop_nhat():
    r = make("hybrid", rerank_enabled=True)
    r.reranker = SimpleNamespace(score=lambda q, texts: [])
    with pytest.raises(RuntimeError, match="rerank KHÔNG chạy"):
        r.invoke("q")


def test_rerank_doi_thu_tu_va_san_diem_cat_duoi_nguong():
    r = make("hybrid", rerank_enabled=True, rerank_score_min=0.5)
    order = {"Nam châm có hai cực bắc và nam": 0.9,
             "Quang hợp diễn ra chủ yếu ở lá cây": 0.8}
    r.reranker = SimpleNamespace(
        score=lambda q, texts: [order.get(t, 0.1) for t in texts])
    got = ids(r.invoke("q"))
    assert got == ["Nam châm có hai cực bắc và nam",
                   "Quang hợp diễn ra chủ yếu ở lá cây"]


# --- ChunkLookup là song ánh ---------------------------------------------

def test_lookup_phat_hien_khoa_trung_thay_vi_im_lang():
    trung = CHUNKS + [("S#khac_p10_c0", "văn bản khác", "S", 10, 0)]
    with pytest.raises(RuntimeError, match="song ánh"):
        ChunkLookup(FakeCollection(trung))


def test_lookup_khong_khop_duoc_thi_raise():
    lookup = ChunkLookup(FakeCollection())
    lac = Document(page_content="?", metadata={"source": "X", "page_index": 1,
                                               "chunk_index": 0})
    with pytest.raises(RuntimeError, match="chunk_id"):
        lookup.id_of(lac)
