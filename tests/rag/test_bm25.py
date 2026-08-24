# -*- coding: utf-8 -*-
"""Test cho kênh thưa. Nhỏ, nhanh, không chạm index thật.

Ba điều nghiệm thu của M2.1 (§3.2 prompt M2), mỗi cái một test:
  (a) khoá của chỉ mục thưa TRÙNG `chunk_id` của `biology_text`;
  (b) chỉ mục thưa cũ hơn index thì **raise**, không âm thầm dùng bản cũ;
  (c) hàm chuẩn hoá chỉ số dưới **không** đổi chữ đã lưu.

Cộng thêm một test quan trọng hơn cả ba: **công thức BM25 có đúng là BM25 không**
— đối chiếu với số tính tay, vì "test pass" trên đầu ra của chính mình chứng minh
được rất ít (nguyên tắc 4).
"""

import math

import numpy as np
import pytest

from src.rag.bm25 import (
    BM25Index,
    SparseFingerprint,
    SparseIndexMissing,
    SparseIndexStale,
    chunk_ids_digest,
)
from src.rag.text_normalize import NORMALIZER_VERSION, formula_tokens, tokenize


def _fp(n=3, digest="abc", version="vTEST"):
    return SparseFingerprint(
        collection="biology_text",
        n_chunks=n,
        ids_digest=digest,
        text_extraction_version=version,
        tokenizer="folded",
        normalizer_version=NORMALIZER_VERSION,
    )


# --- (0) Công thức có đúng là Okapi BM25 không --------------------------

def test_bm25_score_khop_so_tinh_tay():
    """Đối chiếu với BM25 tính tay, không phải với đầu ra của chính mình."""
    ids = ["d0", "d1", "d2"]
    # Token thuần chữ thường, không dấu -> tokenize trả về đúng như viết.
    texts = ["alpha beta beta", "alpha gamma", "delta"]
    idx = BM25Index.build(ids, texts, _fp(), fold_accents=True)

    k1, b = 1.2, 0.75
    got = idx.scores("beta", k1=k1, b=b)

    n = 3.0
    df = 1.0                       # "beta" chỉ có ở d0
    idf = math.log(1.0 + (n - df + 0.5) / (df + 0.5))
    doc_len = [3.0, 2.0, 1.0]
    avg = sum(doc_len) / 3.0
    f = 2.0                        # "beta" xuất hiện 2 lần ở d0
    expect_d0 = idf * (f * (k1 + 1.0)) / (
        f + k1 * (1.0 - b + b * doc_len[0] / avg))

    assert got[0] == pytest.approx(expect_d0, rel=1e-9)
    assert got[1] == 0.0 and got[2] == 0.0


def test_b_cang_lon_cang_phat_tai_lieu_dai():
    """`b` là hệ số chuẩn hoá độ dài — b=0 phải bỏ qua độ dài hoàn toàn."""
    idx = BM25Index.build(
        ["ngan", "dai"],
        ["nam cham", "nam cham " + " ".join(f"tu{i}" for i in range(50))],
        _fp(n=2),
    )
    s_b0 = idx.scores("cham", k1=1.2, b=0.0)
    s_b1 = idx.scores("cham", k1=1.2, b=1.0)
    assert s_b0[0] == pytest.approx(s_b0[1]), "b=0 thì độ dài không được ảnh hưởng"
    assert s_b1[0] > s_b1[1], "b=1 thì tài liệu dài phải bị phạt"


# --- (a) Khoá trùng chunk_id -------------------------------------------

def test_khoa_tra_ve_dung_chunk_id_cua_index():
    ids = [
        "SGK_KHTN_6_CD#3ff40bb8dab9b77009928854db751257_p2_c0",
        "SGK_KHTN_9_KNTT#deadbeefdeadbeefdeadbeefdeadbeef_p155_c3",
    ]
    idx = BM25Index.build(ids, ["quang hop o la cay", "dinh luat ohm"], _fp(n=2))
    top = idx.search("quang hop", k=1, k1=1.2, b=0.75)
    assert top and top[0][0] == ids[0]
    assert set(idx.ids) == set(ids), "không được sinh id riêng"


def test_search_bo_han_tai_lieu_diem_0():
    idx = BM25Index.build(["a", "b"], ["nam cham", "te bao"], _fp(n=2))
    assert idx.search("nam cham", k=10, k1=1.2, b=0.75) == [
        r for r in idx.search("nam cham", k=10, k1=1.2, b=0.75) if r[1] > 0
    ]
    assert len(idx.search("nam cham", k=10, k1=1.2, b=0.75)) == 1
    assert idx.search("khong he co tu nao", k=10, k1=1.2, b=0.75) == []


# --- (b) Chỉ mục cũ hơn index -> RAISE ----------------------------------

@pytest.mark.parametrize("field,value", [
    ("n_chunks", 4),
    ("ids_digest", "digest-khac"),
    ("text_extraction_version", "v3_something_else"),
    ("tokenizer", "plain"),
    ("normalizer_version", "v0_cu"),
])
def test_chi_muc_cu_hon_index_thi_raise(field, value):
    idx = BM25Index.build(["a"], ["x y"], _fp(n=1))
    live = _fp(n=1)
    live = SparseFingerprint(**{**live.__dict__, field: value})
    with pytest.raises(SparseIndexStale) as e:
        idx.verify(live)
    assert field in str(e.value)
    assert "--build-bm25" in str(e.value), "phải nói cách sửa"


def test_khop_hoan_toan_thi_khong_raise():
    idx = BM25Index.build(["a"], ["x y"], _fp(n=1))
    idx.verify(_fp(n=1))


def test_thieu_chi_muc_thi_raise_chu_khong_tra_rong(tmp_path):
    with pytest.raises(SparseIndexMissing):
        BM25Index.load(tmp_path / "khong-ton-tai")


def test_digest_khong_phu_thuoc_thu_tu():
    assert chunk_ids_digest(["b", "a"]) == chunk_ids_digest(["a", "b"])
    assert chunk_ids_digest(["a"]) != chunk_ids_digest(["a", "b"])


def test_luu_roi_nap_lai_giu_nguyen_diem(tmp_path):
    ids = ["d0", "d1"]
    texts = ["quang hop dien ra o la cay", "dinh luat bao toan nang luong"]
    idx = BM25Index.build(ids, texts, _fp(n=2))
    idx.save(tmp_path)
    back = BM25Index.load(tmp_path)
    assert back.ids == idx.ids
    np.testing.assert_allclose(
        back.scores("quang hop", k1=1.2, b=0.75),
        idx.scores("quang hop", k1=1.2, b=0.75),
    )
    back.verify(_fp(n=2))


# --- (c) Chuẩn hoá KHÔNG đổi chữ đã lưu ---------------------------------

def test_chuan_hoa_khong_dong_vao_chu_goc():
    """`tokenize` là hàm THUẦN: chuỗi vào không đổi, và nó chỉ TRẢ VỀ token."""
    goc = "hấp thụ khí CO, và thải ra khí O,"
    ban_sao = str(goc)
    toks = tokenize(goc)
    assert goc == ban_sao, "chuỗi gốc bị sửa tại chỗ"
    assert isinstance(toks, list) and goc not in toks


def test_build_khong_sua_van_ban_dau_vao():
    texts = ["khí CO, trong không khí", "H,SO, loãng"]
    ban_sao = list(texts)
    BM25Index.build(["a", "b"], texts, _fp(n=2))
    assert texts == ban_sao


# --- Chuẩn hoá công thức: cầu nối CO2 <-> CO, ---------------------------

@pytest.mark.parametrize("hong,dung", [
    ("CO,", "CO2"), ("O,", "O2"), ("H,O", "H2O"),
    ("H,SO,", "H2SO4"), ("CH,", "CH4"), ("Fe,O,", "Fe2O3"),
])
def test_dang_hong_va_dang_dung_gap_nhau_o_khung(hong, dung):
    khung_hong = formula_tokens(hong)
    khung_dung = formula_tokens(dung)
    assert khung_hong[0] == khung_dung[0], f"{hong} và {dung} phải chung khung"
    # Dạng đọc ĐÚNG sinh thêm token nguyên văn (`co2`) mà dạng hỏng không có ->
    # trang đọc đúng vẫn hơn điểm trang đọc hỏng.
    assert set(khung_hong) < set(khung_dung), (
        "token của dạng hỏng phải là TẬP CON THỰC SỰ của dạng đúng")
    assert any(any(c.isdigit() for c in t) for t in khung_dung)
    assert not any(any(c.isdigit() for c in t) for t in khung_hong)


def test_khung_KHONG_doan_chu_so():
    """SO₂ và SO₃ cùng khung — mất mát này là CỐ Ý, thà mất còn hơn bịa."""
    assert formula_tokens("SO2")[0] == formula_tokens("SO3")[0] == "so#"
    assert "so2" in formula_tokens("SO2") and "so3" in formula_tokens("SO3")
    # dạng chữ thuần cũng chung nhau — đó là cây cầu cho truy vấn không chỉ số
    assert "so" in formula_tokens("SO2") and "so" in formula_tokens("SO,")
    # và không token nào chứa một chữ số ĐƯỢC ĐOÁN từ dấu phẩy
    assert all(not any(c.isdigit() for c in t) for t in formula_tokens("SO,"))


def test_trang_doc_dung_van_thang_trang_doc_hong():
    """Giữ độ chính xác ở chỗ thông tin CÒN: 2 token trùng > 1 token trùng."""
    idx = BM25Index.build(
        ["dung", "hong"],
        ["khi CO2 trong khong khi", "khi CO, trong khong khi"],
        _fp(n=2),
    )
    s = idx.scores("CO2", k1=1.2, b=0.75)
    assert s[0] > s[1] > 0.0


@pytest.mark.parametrize("khong_phai_cong_thuc", [
    "KH0A", "H0C", "TRA0",       # "KHOA HỌC" bị OCR đọc Ọ/O -> 0
    "S0", "I0", "CaC0",          # chỉ số dưới 0 vô nghĩa trong hoá học
    "Bo,", "Tr,", "Ry,",         # nhóm hai chữ KHÔNG phải ký hiệu nguyên tố
    "XIII,", "II,", "IV,",       # số La Mã dài = nhãn mục, không phải công thức
    "khong", "Bài", "2026",
])
def test_luat_khong_bat_nham_chu_tieng_viet(khong_phai_cong_thuc):
    assert formula_tokens(khong_phai_cong_thuc) == []


def test_bo_dau_gop_dang_sai_dau_cua_ocr():
    assert tokenize("Quang hợp") == tokenize("Quang họp") == ["quang", "hop"]
    assert tokenize("Quang hợp", fold_accents=False) != ["quang", "hop"]


def test_don_chat_khong_chi_so_van_khop_dang_hong():
    """`CuO` (không chỉ số) phải khớp trang lưu `CuO,`.

    Không có dạng chữ thuần thì chính bước chuẩn hoá làm truy vấn này **tệ đi**
    so với khi không chuẩn hoá — đo được 6/10 -> 4/10 chunk đúng ở top-10.
    """
    idx = BM25Index.build(["a", "b"], ["oxide CuO, mau den", "nuoc bien"],
                          _fp(n=2))
    assert idx.search("CuO", k=5, k1=1.2, b=0.75)[0][0] == "a"
