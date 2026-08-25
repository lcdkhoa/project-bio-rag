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


def test_phieu_html_co_du_o_va_anh_tuong_doi(khu):
    """Phiếu HTML là thứ NGƯỜI thực sự dùng — hỏng nó là mất cả buổi duyệt.

    Chốt ba tính chất: đủ số ô, ảnh trỏ đường dẫn TƯƠNG ĐỐI (trang mở từ đĩa,
    đường dẫn tuyệt đối của máy tôi sẽ hỏng trên máy khác), và nháp được điền sẵn.
    """
    out, _ = khu
    items = json.loads((out / "items.json").read_text(encoding="utf-8"))
    for it in items:
        it["anh"] = f"/duong/dan/tuyet/doi/{it['id']}.png"
    (out / "items.json").write_text(json.dumps(items, ensure_ascii=False),
                                    encoding="utf-8")
    (out / "nhap_llm.json").write_text(json.dumps({
        items[0]["id"]: {"cau_hoi": "NHAP Q", "dap_an": "NHAP A",
                         "chac_chan": False}}, ensure_ascii=False), encoding="utf-8")

    p = B.lam_phieu_html(items, out)
    html = p.read_text(encoding="utf-8")
    # neo vào `data-id` chứ không vào tên class: class đổi theo giao diện
    # (đã đổi thành "o chua-xem" ở lượt 2), còn data-id là hợp đồng dữ liệu.
    assert html.count('data-id=') == len(items)
    assert '<img src="crops/' in html
    assert "/duong/dan/tuyet/doi/" not in html
    assert "NHAP Q" in html and "NHAP A" in html
    assert "KHÔNG chắc" in html          # cờ model tự khai


def test_phieu_html_giu_lai_viec_nguoi_da_dien(khu):
    """Mở lại trang giữa chừng không được xoá việc đã làm."""
    out, _ = khu
    items = json.loads((out / "items.json").read_text(encoding="utf-8"))
    _phieu(out, {items[0]["id"]: {"cau_hoi": "NGUOI VIET", "dap_an": "DA",
                                  "bo": False, "ly_do_bo": ""}})
    html = B.lam_phieu_html(items, out).read_text(encoding="utf-8")
    assert "NGUOI VIET" in html


def test_phieu_html_thoat_ky_tu_dac_biet(khu):
    """Chú thích OCR có thể chứa `<`, `&`, `\"` — không được phá vỡ HTML."""
    out, _ = khu
    items = json.loads((out / "items.json").read_text(encoding="utf-8"))
    items[0]["figure_caption"] = 'a < b & c "d" <script>x</script>'
    (out / "items.json").write_text(json.dumps(items, ensure_ascii=False),
                                    encoding="utf-8")
    html = B.lam_phieu_html(items, out).read_text(encoding="utf-8")
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


def test_bu_dem_dung_so_o_con_lai_va_tranh_trang_da_dung(khu):
    """`--bu` phải đếm ô CÒN DÙNG ĐƯỢC, và không lấy lại trang đã xuất hiện.

    Lấy lại đúng trang mà khung cắt đã hỏng thì nhiều khả năng ra khung hỏng
    tương tự, và người phải bỏ lần thứ hai — phí công duyệt.
    """
    out, _ = khu
    items = json.loads((out / "items.json").read_text(encoding="utf-8"))
    _phieu(out, {
        items[0]["id"]: {"cau_hoi": "q", "dap_an": "a", "bo": True,
                         "ly_do_bo": "cắt lấn"},
        items[1]["id"]: {"cau_hoi": "q2", "dap_an": "a2", "bo": False},
    })
    con_lai, tranh = B._da_dung(out)
    assert con_lai == {"SGK_KHTN_6_KNTT": 1}, "ô bị bỏ không được tính là còn"
    # CẢ HAI trang đều bị tránh, kể cả trang của ô đã bỏ
    assert tranh == {("SGK_KHTN_6_KNTT", 10), ("SGK_KHTN_6_KNTT", 20)}


def test_bu_khong_ghi_de_o_nguoi_da_duyet(khu, monkeypatch, capsys):
    """items.json phải được GHI NỐI, không ghi đè — mất ô cũ là mất công duyệt."""
    import sys
    out, _ = khu
    truoc = json.loads((out / "items.json").read_text(encoding="utf-8"))
    _phieu(out, {truoc[0]["id"]: {"cau_hoi": "", "dap_an": "", "bo": True}})

    # giả lập `chon` trả về một ô mới
    monkeypatch.setattr(B, "chon", lambda *a, **k: [{
        "id": "SGK_KHTN_6_KNTT_p99_01", "quyen": "SGK_KHTN_6_KNTT",
        "trang": 99, "trang_nguon": 99, "nhan_hinh": "Hình 9.9",
        "anh": "crops/x.png", "figure_caption": "", "crop_text": "",
        "chu_tren_trang": ""}])
    monkeypatch.setattr(sys, "argv", ["b", "--bu", "--out-dir", str(out)])
    assert B.main() == 0

    sau = json.loads((out / "items.json").read_text(encoding="utf-8"))
    ids = {x["id"] for x in sau}
    assert {x["id"] for x in truoc} <= ids, "ô cũ phải còn nguyên"
    assert "SGK_KHTN_6_KNTT_p99_01" in ids, "ô mới phải được thêm"


def test_bu_khong_them_o_trung_id(khu, monkeypatch):
    """Chạy --bu hai lần không được nhân đôi ô."""
    import sys
    out, _ = khu
    items = json.loads((out / "items.json").read_text(encoding="utf-8"))
    _phieu(out, {items[0]["id"]: {"cau_hoi": "", "dap_an": "", "bo": True}})
    moi = {"id": "SGK_KHTN_6_KNTT_p99_01", "quyen": "SGK_KHTN_6_KNTT",
           "trang": 99, "trang_nguon": 99, "nhan_hinh": "Hình 9.9",
           "anh": "crops/x.png", "figure_caption": "", "crop_text": "",
           "chu_tren_trang": ""}
    monkeypatch.setattr(B, "chon", lambda *a, **k: [moi])
    monkeypatch.setattr(sys, "argv", ["b", "--bu", "--out-dir", str(out)])
    B.main()
    B.main()
    sau = json.loads((out / "items.json").read_text(encoding="utf-8"))
    assert sum(1 for x in sau if x["id"] == moi["id"]) == 1
