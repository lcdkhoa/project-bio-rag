import json

import pytest

from src.test.testset_common import duong_dan_output, require_human_reviewed


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
