# -*- coding: utf-8 -*-
"""Chia bộ test đã duyệt (`draft.csv`) thành N batch cho Colab Free (D-183).

Không còn Colab Pro -> phiên Free ngắn hơn và không đảm bảo GPU liên tục, và
`run_eval.py` (D-182) KHÔNG resume được giữa chừng (finding I-4, PARK) -> chia
240 câu thành N batch (mặc định 3, ~80 câu/batch, chạy trên 3 file notebook
riêng `document/colab_runtime_eval_batch{1,2,3}.ipynb`) để mỗi phiên ngắn hơn
và một lần rớt phiên chỉ mất tối đa MỘT batch, không mất cả bộ.

Chia ROUND-ROBIN theo `loai` (van_ban/hinh/ngoai_pham_vi): trong từng nhóm, rải
theo thứ tự có sẵn trong draft.csv vào batch (vị trí trong nhóm % n_batches) ->
mỗi batch có tỉ lệ loại câu hỏi gần giống bộ gốc. Đây là một PHÂN VÙNG thật: mỗi
câu thuộc đúng 1 batch, hợp cả N batch lại đúng bằng draft.csv gốc — không câu
nào bị trùng hay mất (có assert kiểm lại tổng số trước khi ghi file).

Cần `draft.csv`/`meta.json` đã `--mark-reviewed` (xem `build_testset.py`) —
script này CHIA bộ đã duyệt, không tự sinh/duyệt gì thêm.

Chạy:
    python -m src.test.split_testset                  # mặc định 3 batch
    python -m src.test.split_testset --n-batches 2
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd

from src.test.testset_common import DRAFT_CSV, meta_path_for, require_human_reviewed

BATCHES_DIRNAME = "batches"


def split(draft_csv: Path, n_batches: int) -> None:
    meta_path = meta_path_for(draft_csv)
    require_human_reviewed(meta_path)  # KHONG --allow-draft: chia batch la buoc
    # chinh thuc truoc khi upload Colab, khong phai tu kiem code.

    df = pd.read_csv(draft_csv)
    if df.empty:
        raise SystemExit(f"{draft_csv} rong - khong co gi de chia.")
    if "loai" not in df.columns:
        raise SystemExit(f"{draft_csv} thieu cot 'loai' - dung dinh dang build_testset.py sinh ra chua?")

    # Round-robin THEO TUNG NHOM loai (khong phai theo toan bo draft.csv) de
    # moi batch giu duoc ti le van_ban/hinh/ngoai_pham_vi gan giong bo goc —
    # build_testset.py ghi lien tiep theo khoi (het van_ban roi moi toi hinh
    # roi ngoai_pham_vi), nen chia tho theo thu tu dong se don het mot loai
    # vao mot batch.
    buckets = {i: [] for i in range(n_batches)}
    for _, nhom in df.groupby("loai", sort=False):
        for vi_tri_trong_nhom, (_, row) in enumerate(nhom.iterrows()):
            buckets[vi_tri_trong_nhom % n_batches].append(row)

    out_dir = draft_csv.parent / BATCHES_DIRNAME
    out_dir.mkdir(parents=True, exist_ok=True)

    tong = 0
    breakdown = {}
    for i in range(n_batches):
        batch_df = pd.DataFrame(buckets[i], columns=df.columns)
        out_path = out_dir / f"batch{i + 1}.csv"
        batch_df.to_csv(out_path, index=False, encoding="utf-8-sig")
        tong += len(batch_df)
        counts = {str(k): int(v) for k, v in batch_df["loai"].value_counts().items()}
        breakdown[f"batch{i + 1}"] = {"n": len(batch_df), **counts}
        print(f"[split_testset] {out_path.name}: {len(batch_df)} cau -> {counts}")

    # Kiem tra la mot PHAN VUNG that: tong phai khop tuyet doi, khong duoc
    # lech du chi 1 cau (mot cau bi ghi 2 lan hoac bi rot mat se lam gia tri
    # cua toan bo phep chia nay bang khong).
    if tong != len(df):
        raise RuntimeError(
            f"BUG: tong {n_batches} batch ({tong}) khac so cau goc trong "
            f"{draft_csv} ({len(df)}) - KHONG duoc ghi ra, kiem tra lai logic chia.")

    meta_goc = json.loads(meta_path.read_text(encoding="utf-8"))
    meta_goc["n_batches"] = n_batches
    meta_goc["batch_breakdown"] = breakdown
    meta_goc["split_from"] = str(draft_csv)
    meta_goc["split_at"] = datetime.now(timezone(timedelta(hours=7))).isoformat()
    (out_dir / "meta.json").write_text(
        json.dumps(meta_goc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[split_testset] tong {tong} cau, khop {draft_csv} ({len(df)} cau) - OK, khong mat/trung cau nao")
    print(f"[split_testset] da ghi {n_batches} file batch*.csv + meta.json vao {out_dir}/")
    print("[split_testset] upload TOAN BO thu muc chua draft.csv nay (bao gom "
          f"'{BATCHES_DIRNAME}/') len Drive truoc khi chay cac notebook batch.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-batches", type=int, default=3)
    ap.add_argument("--draft-csv", default=str(DRAFT_CSV))
    args = ap.parse_args()
    if args.n_batches < 2:
        raise SystemExit("--n-batches phai >= 2 (chia lam gi voi 1 batch).")
    split(Path(args.draft_csv), args.n_batches)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
