import json

import pandas as pd
import pytest

from src.test.split_testset import split


def _viet_draft(tmp_path, rows):
    draft = tmp_path / "draft.csv"
    pd.DataFrame(rows, columns=["question", "loai", "source_book", "source_page",
                                 "figure_label", "ground_truth"]).to_csv(
        draft, index=False, encoding="utf-8-sig")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"human_reviewed": True, "n_total": len(rows)}),
                     encoding="utf-8")
    return draft


def _bo_cau_9():
    rows = []
    for i in range(5):
        rows.append({"question": f"vb{i}", "loai": "van_ban", "source_book": "S",
                      "source_page": 1, "figure_label": "", "ground_truth": "gt"})
    for i in range(3):
        rows.append({"question": f"hinh{i}", "loai": "hinh", "source_book": "S",
                      "source_page": 2, "figure_label": "Hinh 1", "ground_truth": "gt"})
    rows.append({"question": "npv0", "loai": "ngoai_pham_vi", "source_book": "",
                 "source_page": "", "figure_label": "", "ground_truth": "gt"})
    return rows


def test_split_la_mot_phan_vung_khong_trung_khong_mat(tmp_path):
    draft = _viet_draft(tmp_path, _bo_cau_9())
    split(draft, n_batches=3)

    batches_dir = tmp_path / "batches"
    cau_theo_batch = []
    tong = 0
    for i in (1, 2, 3):
        df = pd.read_csv(batches_dir / f"batch{i}.csv")
        cau_theo_batch.extend(df["question"].tolist())
        tong += len(df)

    assert tong == 9
    assert len(set(cau_theo_batch)) == 9  # khong cau nao trung giua cac batch
    assert set(cau_theo_batch) == {f"vb{i}" for i in range(5)} | \
        {f"hinh{i}" for i in range(3)} | {"npv0"}


def test_split_giu_ti_le_loai_gan_deu_giua_cac_batch(tmp_path):
    draft = _viet_draft(tmp_path, _bo_cau_9())
    split(draft, n_batches=3)

    batches_dir = tmp_path / "batches"
    so_van_ban_moi_batch = []
    for i in (1, 2, 3):
        df = pd.read_csv(batches_dir / f"batch{i}.csv")
        so_van_ban_moi_batch.append(int((df["loai"] == "van_ban").sum()))

    # 5 cau van_ban chia 3 batch round-robin -> [2, 2, 1] (khong batch nao 0 hoac 5)
    assert sorted(so_van_ban_moi_batch, reverse=True) == [2, 2, 1]


def test_split_raise_khi_chua_duyet(tmp_path):
    draft = _viet_draft(tmp_path, _bo_cau_9())
    (tmp_path / "meta.json").write_text(
        json.dumps({"human_reviewed": False}), encoding="utf-8")
    with pytest.raises(SystemExit, match="chưa được duyệt tay"):
        split(draft, n_batches=3)
    assert not (tmp_path / "batches").exists()  # khong ghi gi khi chua qua cong duyet


def test_split_ghi_meta_batches_giu_human_reviewed_va_them_thong_tin_batch(tmp_path):
    draft = _viet_draft(tmp_path, _bo_cau_9())
    split(draft, n_batches=3)

    meta_batches = json.loads((tmp_path / "batches" / "meta.json").read_text(encoding="utf-8"))
    assert meta_batches["human_reviewed"] is True
    assert meta_batches["n_batches"] == 3
    assert "batch_breakdown" in meta_batches
    assert meta_batches["batch_breakdown"]["batch1"]["n"] > 0
