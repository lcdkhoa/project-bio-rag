# -*- coding: utf-8 -*-
"""Gộp `eval_result.csv` của N batch (D-183) thành báo cáo cuối cùng.

Dùng SAU KHI cả N batch (mặc định 3, xem `split_testset.py` +
`document/colab_runtime_eval_batch{1,2,3}.ipynb`) đã chạy `run_eval.py` xong
trên Colab và tải `eval_result.csv` của mỗi batch về máy local — chạy CỤC BỘ,
không cần GPU/Groq gì thêm, chỉ nối CSV + kiểm tra tính toàn vẹn của phân vùng
(không câu nào trùng/thiếu) rồi tái dùng `aggregate_by_loai()` của
`run_eval.py` để tính lại bảng tổng hợp theo LOẠI câu hỏi trên toàn bộ.

Chạy:
    python -m src.test.merge_eval_batches \\
        --input path/to/batch1_eval_result.csv \\
        --input path/to/batch2_eval_result.csv \\
        --input path/to/batch3_eval_result.csv
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd

from src.test.run_eval import TEN_LOAI_HIEN_THI, aggregate_by_loai
from src.test.testset_common import DRAFT_CSV, OUT_DIR


def _cau_trung_lap(df: pd.DataFrame) -> List[tuple]:
    """Khoá đối chiếu (question, source_book, source_page) — chặt hơn chỉ
    `question` một mình, vì hai câu VĂN BẢN khác trang lý thuyết có thể trùng
    chữ (hiếm nhưng không loại trừ); dùng cả 3 trường để chắc chắn đây là
    CÙNG MỘT dòng bị lẫn vào 2 batch, không phải trùng ngẫu nhiên."""
    khoa = list(zip(df["question"], df.get("source_book"), df.get("source_page")))
    dem: dict = {}
    for k in khoa:
        dem[k] = dem.get(k, 0) + 1
    return [k for k, n in dem.items() if n > 1]


def merge(input_paths: List[Path], draft_csv: Path, out_dir: Path) -> pd.DataFrame:
    frames = []
    for p in input_paths:
        if not p.exists():
            raise SystemExit(f"Khong thay {p}.")
        frames.append(pd.read_csv(p))

    all_df = pd.concat(frames, ignore_index=True)

    trung = _cau_trung_lap(all_df)
    if trung:
        raise SystemExit(
            f"PHAT HIEN {len(trung)} cau TRUNG giua cac batch (vi du: {trung[0]!r}) "
            "- day KHONG con la mot phan vung dung. Kiem tra lai split_testset.py "
            "da chia dung chua, hoac mot batch da bi chay/tai nham 2 lan.")

    if draft_csv.exists():
        goc = pd.read_csv(draft_csv)
        if len(all_df) != len(goc):
            raise SystemExit(
                f"LECH SO CAU: gop duoc {len(all_df)} cau tu {len(input_paths)} file "
                f"nhung {draft_csv} co {len(goc)} cau - CHUA du batch (thieu file, "
                "hoac mot batch chay chua het), dung tin bang tong hop nay.")
        print(f"[merge_eval_batches] {len(all_df)} cau khop dung {draft_csv} "
              f"({len(goc)} cau) - du ca N batch, khong thieu/trung.")
    else:
        print(f"[merge_eval_batches] CANH BAO: khong thay {draft_csv} de doi chieu "
              "tong so cau - chi kiem tra duoc trung lap giua cac batch, KHONG kiem "
              "tra duoc co THIEU nguyen mot batch hay khong.")

    out_dir.mkdir(parents=True, exist_ok=True)
    result_csv = out_dir / "eval_result.csv"
    all_df.to_csv(result_csv, index=False, encoding="utf-8-sig")

    report = aggregate_by_loai(all_df)
    report_csv = out_dir / "eval_report.csv"
    report.to_csv(report_csv, index=False, encoding="utf-8-sig")

    # I-3 cua run_eval.py (D-182/D-173) lap lai o day: mot batch bi loi judge
    # giua chung (rate-limit/TPD) van cho ra du dong, chi trong cot judge_* -
    # phai lo ra ngay trong bang tong hop, khong doi ai do doi chieu tay.
    thieu = report[report["so_cau_co_diem_judge"] < report["num_questions"]]
    if not thieu.empty:
        print(f"\n!! {int((thieu['num_questions'] - thieu['so_cau_co_diem_judge']).sum())} "
              "cau KHONG co diem giam khao (loi judge/rate-limit o mot batch nao do) - "
              "so trung binh o cac dong duoi day KHONG tinh tren du num_questions:")
        print(thieu[["loai_cau_hoi", "num_questions", "so_cau_co_diem_judge"]].to_string(index=False))

    lines = ["# Bao cao danh gia RAG theo LOAI cau hoi (gop tu cac batch, D-183)\n",
             f"Tong so cau: {len(all_df)} | Gop tu {len(input_paths)} file batch\n",
             "## Tong hop theo loai cau hoi\n",
             "| Loai | So cau | Correct/5 | Faithful/5 | Relevancy/5 |",
             "|---|---|---|---|---|"]
    for _, r in report.iterrows():
        ten = TEN_LOAI_HIEN_THI.get(r["loai_cau_hoi"], r["loai_cau_hoi"])
        lines.append(
            f"| {ten} | {int(r['num_questions'])} | {r['judge_correctness']:.2f} | "
            f"{r['judge_faithfulness']:.2f} | {r['judge_relevancy']:.2f} |")
    report_md = out_dir / "eval_report.md"
    report_md.write_text("\n".join(lines), encoding="utf-8")

    print(f"\nDa luu: {result_csv}, {report_csv}, {report_md}")
    print("\n" + report.to_string(index=False))
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", action="append", required=True,
                     help="Duong dan mot eval_result.csv cua MOT batch (lap lai --input cho tung batch)")
    ap.add_argument("--draft-csv", default=str(DRAFT_CSV),
                     help="draft.csv day du (240 cau) de doi chieu tong so - bo qua neu khong co")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()
    if len(args.input) < 2:
        raise SystemExit("Can it nhat 2 --input (gop 1 file thi khong phai gop gi ca).")
    merge([Path(p) for p in args.input], Path(args.draft_csv), Path(args.out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
