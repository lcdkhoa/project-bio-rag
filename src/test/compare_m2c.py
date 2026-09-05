# -*- coding: utf-8 -*-
"""So sánh multi-modal-on vs text-only trên đúng 52 câu 'hinh' — kết luận cho
MT4 vế (ii) (`goal.docx`). Chạy CỤC BỘ, không cần GPU — chỉ đọc hai CSV đã có.

Đầu vào:
    - `src/test/testset_m2c/baseline_text_only.csv` (sinh bởi
      `build_m2c_subset.py`, đo với `MULTIMODAL_CONTEXT_ENABLED=false`)
    - `src/test/testset_m2c/eval_result_multimodal_on.csv` (tải về từ Drive
      sau khi chạy phần "Ablation multimodal M2C" trong
      `document/colab_runtime_eval.ipynb`, đo với
      `MULTIMODAL_CONTEXT_ENABLED=true` — đổi tên `eval_result.csv` thành tên
      này khi tải về, xem hướng dẫn cuối notebook)

Ghép theo cột `question` (bộ 52 câu không trùng câu hỏi nào — đã kiểm khi
sinh). Câu nào không ghép được (lệch bộ, ví dụ chạy nhầm draft.csv) sẽ bị loại
và CẢNH BÁO rõ, không lặng lẽ bỏ qua.

Chạy:
    python -m src.test.compare_m2c
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
M2C_DIR = REPO_ROOT / "src" / "test" / "testset_m2c"

COT_JUDGE = ["judge_correctness", "judge_faithfulness", "judge_relevancy"]


def compare(baseline_csv: Path, on_csv: Path, out_md: Path) -> None:
    base = pd.read_csv(baseline_csv)
    on = pd.read_csv(on_csv)

    merged = base.merge(on, on="question", how="outer", suffixes=("_off", "_on"),
                         indicator=True)
    khong_ghep = merged[merged["_merge"] != "both"]
    if not khong_ghep.empty:
        print(f"CẢNH BÁO: {len(khong_ghep)}/{len(merged)} câu KHÔNG ghép được "
              "giữa hai file (khác bộ câu hỏi?) — loại khỏi so sánh:")
        for q in khong_ghep["question"]:
            print("  -", str(q)[:80])
    merged = merged[merged["_merge"] == "both"].copy()
    if merged.empty:
        raise SystemExit("Không có câu nào ghép được — kiểm tra lại hai file đầu vào.")

    dong = []
    for c in COT_JUDGE:
        off_mean = merged[f"{c}_off"].mean()
        on_mean = merged[f"{c}_on"].mean()
        dong.append({
            "do_do": c, "text_only": round(off_mean, 3),
            "multi_modal_on": round(on_mean, 3),
            "delta": round(on_mean - off_mean, 3),
        })
    bang = pd.DataFrame(dong)

    n = len(merged)
    # KHÔNG dùng DataFrame.to_markdown() — cần gói `tabulate` chưa nằm trong
    # requirements.txt; tự dựng bảng Markdown để không thêm phụ thuộc mới.
    header = "| " + " | ".join(bang.columns) + " |"
    sep = "|" + "|".join(["---"] * len(bang.columns)) + "|"
    rows = ["| " + " | ".join(str(v) for v in row) + " |"
            for row in bang.itertuples(index=False)]
    bang_md = "\n".join([header, sep, *rows])

    lines = [
        "# So sánh multi-modal-on vs text-only (M2C, MT4 vế ii)",
        "",
        f"Số câu ghép được: {n}",
        "",
        bang_md,
        "",
        "Ghép cặp theo từng câu (paired) — mỗi câu có đúng 2 lượt chạy, chỉ "
        "khác `MULTIMODAL_CONTEXT_ENABLED`. Xem `so_sanh_chi_tiet.csv` cạnh "
        "file này để đối chiếu từng câu (câu nào tệ đi khi bật multi-modal).",
    ]
    out_md.write_text("\n".join(lines), encoding="utf-8")

    chi_tiet_cols = ["question"] + [f"{c}_off" for c in COT_JUDGE] + \
        [f"{c}_on" for c in COT_JUDGE]
    merged[chi_tiet_cols].to_csv(out_md.with_name("so_sanh_chi_tiet.csv"),
                                  index=False, encoding="utf-8-sig")

    print(bang.to_string(index=False))
    print(f"\nĐã ghi {out_md} + {out_md.with_name('so_sanh_chi_tiet.csv')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline-csv", default=str(M2C_DIR / "baseline_text_only.csv"))
    ap.add_argument("--on-csv", default=str(M2C_DIR / "eval_result_multimodal_on.csv"))
    ap.add_argument("--out-md", default=str(M2C_DIR / "m2c_ket_qua.md"))
    args = ap.parse_args()

    b, o = Path(args.baseline_csv), Path(args.on_csv)
    if not b.exists():
        raise SystemExit(f"Không thấy {b} — chạy `build_m2c_subset.py` trước.")
    if not o.exists():
        raise SystemExit(f"Không thấy {o} — tải kết quả multi-modal-on từ Drive về "
                          f"đúng đường dẫn này trước (xem docstring đầu file).")
    compare(b, o, Path(args.out_md))
