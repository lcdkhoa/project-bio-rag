# -*- coding: utf-8 -*-
"""Trích bộ câu hỏi HÌNH từ bộ test 240 câu đã duyệt, phục vụ ablation M2C
(MT4 vế ii, `goal.docx`): multi-modal context (`MULTIMODAL_CONTEXT_ENABLED`)
có cải thiện câu trả lời so với text-only hay không.

Vì sao trích lại thay vì sinh bộ mới: `ground_truth` của nhóm `hinh` trong
`build_testset.py` (D-182) được LLM soạn TRỰC TIẾP từ `figure_caption`/
`crop_text` của chính hình đó — đúng loại thông tin mà multi-modal context sẽ
bơm vào prompt. Bộ D-87 cũ (100 câu/4 quyển KNTT) có `ground_truth` sinh từ
văn bản TRANG chứ không từ hình, nên trần đo được chỉ 0,104 và không kết luận
được gì. Bộ 52 câu này không có trần đó.

Không cần chạy lại retrieval — multi-modal context chỉ đổi PROMPT đưa vào LLM,
không đổi kết quả truy xuất. Baseline text-only cho đúng 52 câu này đã có sẵn
trong `src/test/eval_results/eval_result.csv` (lượt `--n 240` D-187, chạy với
`MULTIMODAL_CONTEXT_ENABLED=false` — giá trị mặc định, `.env` không ghi đè) —
script này trích luôn baseline đó ra để so sánh có ghép cặp (paired) sau khi
có kết quả multi-modal-on.

Chạy (cục bộ, không cần GPU):
    python -m src.test.build_m2c_subset
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from src.test.testset_common import meta_path_for, require_human_reviewed

REPO_ROOT = Path(__file__).resolve().parents[2]
NGUON_DIR = REPO_ROOT / "src" / "test" / "eval_results"
RA_DIR = REPO_ROOT / "src" / "test" / "testset_m2c"


def build(nguon_dir: Path = NGUON_DIR, ra_dir: Path = RA_DIR) -> None:
    draft_path = nguon_dir / "draft.csv"
    result_path = nguon_dir / "eval_result.csv"
    if not draft_path.exists():
        raise SystemExit(f"Không thấy {draft_path} — cần bộ test 240 câu đã "
                          "chạy end-to-end (run_eval.py) trước.")
    require_human_reviewed(meta_path_for(draft_path))

    draft = pd.read_csv(draft_path)
    hinh = draft[draft["loai"] == "hinh"].reset_index(drop=True)
    if hinh.empty:
        raise SystemExit(f"{draft_path} không có câu nào loai=='hinh'.")

    ra_dir.mkdir(parents=True, exist_ok=True)
    out_draft = ra_dir / "draft.csv"
    hinh.to_csv(out_draft, index=False, encoding="utf-8-sig")

    meta = {
        "nguon": "src/test/build_m2c_subset.py — trích từ eval_results/draft.csv",
        "loc_theo": "loai == 'hinh'",
        "n_total": len(hinh),
        "tao_luc": datetime.now(timezone(timedelta(hours=7))).isoformat(),
        # Đã là tập con của bộ 240 câu đã người duyệt — không cần duyệt lại,
        # nhưng vẫn khai human_reviewed=true tường minh để
        # `require_human_reviewed()` (run_eval.py trên Colab) không chặn.
        "human_reviewed": True,
        "reviewed_at": None,
    }
    (ra_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Đã ghi {len(hinh)} câu 'hinh' -> {out_draft}")

    if result_path.exists():
        result = pd.read_csv(result_path)
        baseline = result[result["loai"] == "hinh"][
            ["question", "retrieved", "rag_answer", "ground_truth",
             "judge_correctness", "judge_faithfulness", "judge_relevancy"]
        ].reset_index(drop=True)
        out_baseline = ra_dir / "baseline_text_only.csv"
        baseline.to_csv(out_baseline, index=False, encoding="utf-8-sig")
        print(f"Đã ghi baseline text-only ({len(baseline)} câu) -> {out_baseline}")
        print("  Trung bình text-only: "
              f"Correct={baseline['judge_correctness'].mean():.3f} "
              f"Faithful={baseline['judge_faithfulness'].mean():.3f} "
              f"Relevancy={baseline['judge_relevancy'].mean():.3f}")
    else:
        print(f"CẢNH BÁO: không thấy {result_path} — chưa trích được baseline "
              "text-only, chỉ có bộ câu hỏi. Chạy lại sau khi có eval_result.csv.")

    print(f"\nBước tiếp theo: upload thư mục {ra_dir} lên Drive, chạy phần "
          "'Ablation multimodal M2C' trong document/colab_runtime_eval.ipynb.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nguon-dir", default=str(NGUON_DIR))
    ap.add_argument("--ra-dir", default=str(RA_DIR))
    args = ap.parse_args()
    build(Path(args.nguon_dir), Path(args.ra_dir))
