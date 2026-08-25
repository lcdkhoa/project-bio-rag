"""Bộ 48 câu hỏi từ HÌNH — khoá lại cái ranh giới "nháp không được thành dữ liệu".

Không test phần chọn crop (cần ChromaDB thật) và không test phần gọi LLM (cần
mạng). Test đúng chỗ dễ hỏng mà lại im lặng: nháp lọt vào bộ test, hoặc chạy hai
lần thành 96 câu.
"""
import csv
import json
import time

import pytest

from src.test import build_image_questions as B


@pytest.fixture
def khu(tmp_path):
    """Một khu làm việc giả: items.json + một CSV bộ 240 có sẵn 2 câu văn bản."""
    out = tmp_path / "review"
    out.mkdir()
    items = [
        {"id": "SGK_KHTN_6_KNTT_p10_01", "quyen": "SGK_KHTN_6_KNTT", "trang": 10,
         "nhan_hinh": "Hình 2.1", "anh": "x.png", "figure_caption": "",
         "crop_text": "", "chu_tren_trang": ""},
        {"id": "SGK_KHTN_6_KNTT_p20_02", "quyen": "SGK_KHTN_6_KNTT", "trang": 20,
         "nhan_hinh": "Hình 4.1", "anh": "y.png", "figure_caption": "",
         "crop_text": "", "chu_tren_trang": ""},
    ]
    (out / "items.json").write_text(json.dumps(items, ensure_ascii=False),
                                    encoding="utf-8")

    ts = tmp_path / "testsets_240"
    ts.mkdir()
    cols = ["question", "ground_truth", "source_book", "source_page",
            "source_page_index", "do_kho", "nguon_cau_hoi", "figure_label"]
    with (ts / "SGK_KHTN_6_KNTT_testset.csv").open(
            "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for i in (1, 2):
            w.writerow({"question": f"q{i}", "ground_truth": f"a{i}",
                        "source_book": "SGK_KHTN_6_KNTT", "source_page": i,
                        "source_page_index": i, "do_kho": "truc_tiep",
                        "nguon_cau_hoi": "van_ban", "figure_label": ""})
    return out, ts


def _phieu(out, traloi):
    (out / "phieu_nguoi.json").write_text(
        json.dumps({"_bat_dau": 1, "_ket_thuc": 2, "traloi": traloi},
                   ensure_ascii=False), encoding="utf-8")


def _rows(ts):
    with (ts / "SGK_KHTN_6_KNTT_testset.csv").open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_o_chua_dien_khong_vao_bo_test(khu):
    """Ô người CHƯA điền là ô CHƯA duyệt — không được vào bộ test."""
    out, ts = khu
    _phieu(out, {
        "SGK_KHTN_6_KNTT_p10_01": {"cau_hoi": "", "dap_an": "", "bo": False},
        "SGK_KHTN_6_KNTT_p20_02": {"cau_hoi": "Hình 4.1 vẽ gì?",
                                   "dap_an": "Tế bào", "bo": False},
    })
    r = B.ap_dung(out, ts)
    assert r == {"them": 1, "bo": 0, "chua_dien": 1,
                 "quyen": {"SGK_KHTN_6_KNTT": 1}}
    assert [x["question"] for x in _rows(ts) if x["nguon_cau_hoi"] == "hinh"] \
        == ["Hình 4.1 vẽ gì?"]


def test_o_bi_gach_bo_khong_vao_bo_test(khu):
    out, ts = khu
    _phieu(out, {
        "SGK_KHTN_6_KNTT_p10_01": {"cau_hoi": "q", "dap_an": "a", "bo": True,
                                   "ly_do_bo": "crop cắt lấn"},
        "SGK_KHTN_6_KNTT_p20_02": {"cau_hoi": "q2", "dap_an": "a2", "bo": False},
    })
    r = B.ap_dung(out, ts)
    assert r["bo"] == 1 and r["them"] == 1


def test_chay_hai_lan_khong_nhan_doi_cau_hinh(khu):
    """`--ap-dung` phải bình phương bằng chính nó (idempotent).

    Không có tính chất này thì sửa một câu rồi chạy lại sẽ ra 8 câu hình/quyển
    thay vì 4, và bảng đo sai mà không ai thấy — bộ test không có ai canh.
    """
    out, ts = khu
    _phieu(out, {
        "SGK_KHTN_6_KNTT_p10_01": {"cau_hoi": "q1", "dap_an": "a1", "bo": False},
        "SGK_KHTN_6_KNTT_p20_02": {"cau_hoi": "q2", "dap_an": "a2", "bo": False},
    })
    B.ap_dung(out, ts)
    B.ap_dung(out, ts)
    rows = _rows(ts)
    assert sum(1 for r in rows if r["nguon_cau_hoi"] == "hinh") == 2
    assert sum(1 for r in rows if r["nguon_cau_hoi"] == "van_ban") == 2


def test_cau_hinh_giu_duoc_nhan_hinh_va_trang_nguon(khu):
    """`figure_label` + `source_page` là thứ làm câu hỏi này KIỂM ĐƯỢC."""
    out, ts = khu
    _phieu(out, {
        "SGK_KHTN_6_KNTT_p10_01": {"cau_hoi": "q1", "dap_an": "a1", "bo": False},
    })
    B.ap_dung(out, ts)
    row = [r for r in _rows(ts) if r["nguon_cau_hoi"] == "hinh"][0]
    assert row["figure_label"] == "Hình 2.1"
    assert row["source_page"] == "10"


def test_lam_phieu_khong_bao_gio_ghi_de_viec_nguoi_da_lam(khu, tmp_path):
    """Ghi đè phiếu là xoá công người — không được phép, kể cả khi chạy nhầm."""
    out, _ = khu
    items = json.loads((out / "items.json").read_text(encoding="utf-8"))
    _phieu(out, {"SGK_KHTN_6_KNTT_p10_01": {"cau_hoi": "NGUOI DA VIET",
                                            "dap_an": "x", "bo": False}})
    B.lam_phieu(items, out)
    d = json.loads((out / "phieu_nguoi.json").read_text(encoding="utf-8"))
    assert d["traloi"]["SGK_KHTN_6_KNTT_p10_01"]["cau_hoi"] == "NGUOI DA VIET"


def test_phieu_moi_dien_san_nhap_llm_va_co_cot_chac_chan(khu):
    """Nháp được điền sẵn để người SỬA, kèm cờ model tự khai có chắc không."""
    out, _ = khu
    items = json.loads((out / "items.json").read_text(encoding="utf-8"))
    (out / "nhap_llm.json").write_text(json.dumps({
        "SGK_KHTN_6_KNTT_p10_01": {"cau_hoi": "nhap q", "dap_an": "nhap a",
                                   "chac_chan": False}}, ensure_ascii=False),
        encoding="utf-8")
    B.lam_phieu(items, out)
    d = json.loads((out / "phieu_nguoi.json").read_text(encoding="utf-8"))
    o = d["traloi"]["SGK_KHTN_6_KNTT_p10_01"]
    assert o["cau_hoi"] == "nhap q" and o["nhap_chac_chan"] is False
    # ô không có nháp thì để TRỐNG, không mượn nháp của ô khác
    assert d["traloi"]["SGK_KHTN_6_KNTT_p20_02"]["cau_hoi"] == ""


def test_thieu_csv_bo_240_thi_dung_han_chu_khong_tao_moi(khu, tmp_path):
    """Tạo CSV mới ở đây sẽ đẻ ra một bộ test 4 câu trông như thật."""
    out, _ = khu
    _phieu(out, {"SGK_KHTN_6_KNTT_p10_01": {"cau_hoi": "q", "dap_an": "a",
                                            "bo": False}})
    with pytest.raises(SystemExit):
        B.ap_dung(out, tmp_path / "khong_ton_tai")


def test_trang_cua_cau_hoi_hinh_la_trang_IN_khong_phai_chi_so_nguon(khu):
    """Gold key của câu hình phải CÙNG HỆ với gold key của câu văn bản.

    `page_number` của image doc là CHỈ SỐ TRANG NGUỒN; gold key văn bản là SỐ
    TRANG IN. Hôm nay hai số bằng nhau (offset 0, D-65) nên lỗi này sẽ không lộ
    ra trên corpus hiện tại — đúng kiểu bug ngủ đông. Test dựng một quyển có
    offset khác 0 để bắt nó ngay bây giờ.
    """
    out, ts = khu
    items = json.loads((out / "items.json").read_text(encoding="utf-8"))
    items[0]["trang"] = 7           # trang IN
    items[0]["trang_nguon"] = 10    # chỉ số trang nguồn (offset -3)
    (out / "items.json").write_text(json.dumps(items, ensure_ascii=False),
                                    encoding="utf-8")
    _phieu(out, {items[0]["id"]: {"cau_hoi": "q", "dap_an": "a", "bo": False}})
    B.ap_dung(out, ts)
    row = [r for r in _rows(ts) if r["nguon_cau_hoi"] == "hinh"][0]
    assert row["source_page"] == "7", "source_page phải là trang IN"
    assert row["source_page_index"] == "10", "source_page_index là chỉ số nguồn"
