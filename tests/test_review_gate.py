import json

import pytest

from src.test.testset_common import (DRAFT_CSV, META_JSON, duong_dan_output,
                                      meta_path_for, require_human_reviewed)


def test_raise_khi_chua_duyet(tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"human_reviewed": False}), encoding="utf-8")
    with pytest.raises(SystemExit, match="chưa được duyệt tay"):
        require_human_reviewed(meta)


def test_khong_raise_khi_da_duyet(tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"human_reviewed": True}), encoding="utf-8")
    require_human_reviewed(meta)  # không raise


def test_allow_draft_bo_qua_nhung_in_canh_bao(tmp_path, capsys):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"human_reviewed": False}), encoding="utf-8")
    require_human_reviewed(meta, allow_draft=True)  # không raise
    captured = capsys.readouterr()  # đọc ĐÚNG MỘT LẦN — gọi lại sẽ luôn rỗng
    out = captured.out + captured.err
    assert "NHÁP" in out or "nháp" in out or "draft" in out.lower()


def test_duong_dan_output_them_hau_to_khi_draft():
    p = duong_dan_output("eval_result.csv", allow_draft=True)
    assert p.name == "eval_result_NHAP_CHUA_DUYET.csv"


def test_duong_dan_output_khong_doi_khi_khong_draft():
    p = duong_dan_output("eval_result.csv", allow_draft=False)
    assert p.name == "eval_result.csv"


# I-3 (phản biện Opus 5, 2026-09-04): `meta_path_for()` phải trỏ ĐÚNG thư mục
# chứa `--testset-csv` người dùng truyền, không phải luôn luôn hằng số mặc
# định `META_JSON` — bug cũ: chạy `--testset-csv` trỏ sang một CSV KHÁC
# (chưa duyệt) trong khi `meta.json` mặc định vẫn `human_reviewed: true` (từ
# lượt trước) sẽ lọt cổng nhầm.

def test_meta_path_for_mac_dinh_tra_ve_meta_json():
    """Không truyền cờ (hành vi mặc định) phải giữ nguyên y hệt trước khi sửa."""
    assert meta_path_for(DRAFT_CSV) == META_JSON


def test_meta_path_for_theo_dung_thu_muc_cua_testset_csv_khac(tmp_path):
    """`--testset-csv` trỏ sang thư mục KHÁC OUT_DIR mặc định."""
    khac_dir = tmp_path / "mot_thu_muc_khac"
    khac_dir.mkdir()
    testset_csv_khac = khac_dir / "draft.csv"
    assert meta_path_for(testset_csv_khac) == khac_dir / "meta.json"


def test_cong_duyet_raise_dung_cho_thu_muc_thieu_du_lieu_du_out_dir_the_nao(tmp_path):
    """Dựng 2 thư mục tạm: một có meta.json human_reviewed=true, một KHÔNG có
    gì. Cổng duyệt phải raise cho thư mục thiếu — bất kể OUT_DIR mặc định (nếu
    tồn tại trong môi trường test) có nội dung gì đi nữa, vì `meta_path_for`
    không bao giờ đọc nhầm sang OUT_DIR mặc định.
    """
    da_duyet_dir = tmp_path / "da_duyet"
    da_duyet_dir.mkdir()
    (da_duyet_dir / "meta.json").write_text(
        json.dumps({"human_reviewed": True}), encoding="utf-8")
    testset_da_duyet = da_duyet_dir / "draft.csv"
    require_human_reviewed(meta_path_for(testset_da_duyet))  # không raise

    thieu_dir = tmp_path / "thieu_meta"
    thieu_dir.mkdir()
    testset_thieu = thieu_dir / "draft.csv"
    with pytest.raises(FileNotFoundError):
        # meta.json không tồn tại trong thư mục này -> đọc file lỗi (không
        # phải lỗi human_reviewed=false) — vẫn CHẶN, không lọt cổng nhầm.
        require_human_reviewed(meta_path_for(testset_thieu))
