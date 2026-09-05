# -*- coding: utf-8 -*-
"""Sinh hình Chương 4 từ SỐ ĐO THẬT, không vẽ tay.

D-181 (2026-09-03, chỉ đạo CBHD): `evaluation_report_240.csv` đổi trục tổng hợp
từ "theo TỪNG QUYỂN" (12 hàng, 9 cột IR + điểm tổng hợp) sang "theo LOẠI câu hỏi"
(văn bản / hình / ngoài-phạm-vi). 9 cột IR/xếp hạng theo quyển
(precision/recall/mrr page & book, retrieval_score, answer_score, overall_score)
đã bị xoá khỏi báo cáo — số liệu Precision/Recall/F1@K theo 4 phương pháp truy
vấn (keyword/dense/truyền thống/đề xuất) nay sống trong `ablation.py`, không còn
ở đây. Hai hình cũ dựa trên trục "theo quyển" (leaderboard, recall_per_book) và
hai hình dựa trên các cột IR đã xoá (retrieval_vs_answer, recall_at_k) KHÔNG còn
vẽ được — bộ hình mới chỉ còn phản ánh những gì evaluator.py THẬT SỰ đo:
thành phần bộ câu hỏi theo loại, và điểm giám khảo (Correct/Faithful/Relevancy)
theo loại. Không hằng số nào được gõ tay:

    python report/ve_hinh_chuong4.py

Bảng màu lấy từ bảng màu tham chiếu đã qua bộ kiểm CVD (ba ô đầu của bảng phân
loại: xanh dương / cam / xanh ngọc, đạt mọi ngưỡng ở chế độ all-pairs). Vì báo
cáo đem đi IN, mỗi màu còn mang một kiểu gạch chéo riêng để phân biệt được cả
khi in đen trắng — màu không bao giờ là kênh thông tin duy nhất.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

GOC = Path(__file__).resolve().parent.parent
CSV_EVAL = GOC / "src" / "test" / "eval_results" / "eval_report.csv"
THU_MUC_HINH = GOC / "report" / "tex_source" / "src" / "images" / "chapter4"

# --- bảng màu (xem docstring) -------------------------------------------------
XANH = "#2a78d6"     # văn bản
CAM = "#eb6834"       # hình
NGOC = "#1baf7a"      # ngoài phạm vi
XAM = "#9a988f"       # không rõ loại (dữ liệu cũ trước D-181)

MUC_CHINH = "#0b0b0b"
MUC_PHU = "#52514e"
MUC_MO = "#898781"
LUOI = "#e1e0d9"
NEN = "#fcfcfb"

GACH_LOAI = {"van_ban": "", "hinh": "/", "ngoai_pham_vi": "\\", "khong_ro": "x"}
MAU_LOAI = {"van_ban": XANH, "ngoai_pham_vi": NGOC, "hinh": CAM, "khong_ro": XAM}
TEN_LOAI = {
    "van_ban": "Văn bản",
    "hinh": "Hình",
    "ngoai_pham_vi": "Ngoài phạm vi",
    "khong_ro": "Không rõ loại",
}
THU_TU_LOAI = ["van_ban", "hinh", "ngoai_pham_vi", "khong_ro"]


def _dat_kieu() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",   # phông duy nhất chắc chắn đủ dấu tiếng Việt
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.labelsize": 10,
        "axes.edgecolor": MUC_MO,
        "axes.labelcolor": MUC_PHU,
        "axes.facecolor": NEN,
        "figure.facecolor": NEN,
        "text.color": MUC_CHINH,
        "xtick.color": MUC_PHU,
        "ytick.color": MUC_PHU,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "grid.color": LUOI,
        "grid.linewidth": 0.6,
        "legend.frameon": False,
        "legend.fontsize": 9,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
    })


def _don_khung(ax, truc_luoi: str = "x") -> None:
    """Bỏ khung, chỉ giữ lưới mảnh — trục và lưới phải lùi sau dữ liệu."""
    for canh in ("top", "right", "left" if truc_luoi == "x" else "bottom"):
        ax.spines[canh].set_visible(False)
    ax.spines["bottom" if truc_luoi == "x" else "left"].set_color("#c3c2b7")
    ax.grid(axis=truc_luoi, linestyle="-", alpha=0.9)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def _so(x: float, n: int = 3) -> str:
    """Số theo quy ước tiếng Việt: dấu phẩy thập phân."""
    return f"{x:.{n}f}".replace(".", ",")


def _sap_xep(d: pd.DataFrame) -> pd.DataFrame:
    """Sắp theo thứ tự cố định văn_bản/hình/ngoài_phạm_vi/không_rõ, bỏ loại vắng mặt."""
    thu_tu = {loai: i for i, loai in enumerate(THU_TU_LOAI)}
    d = d[d["loai_cau_hoi"].isin(thu_tu)].copy()
    d["_thu_tu"] = d["loai_cau_hoi"].map(thu_tu)
    return d.sort_values("_thu_tu").drop(columns="_thu_tu").reset_index(drop=True)


def _doc_eval() -> pd.DataFrame:
    if not CSV_EVAL.exists():
        raise SystemExit(f"Không thấy {CSV_EVAL} — chưa chạy evaluator?")
    d = pd.read_csv(CSV_EVAL)
    thieu = [c for c in ("loai_cau_hoi", "num_questions") if c not in d.columns]
    if thieu:
        raise SystemExit(
            f"{CSV_EVAL} thiếu cột {thieu} — đây có phải bản CŨ trước D-181 "
            "(trục 'theo quyển') không? Chạy lại `python -m src.test.run_eval` "
            "để tái sinh đúng cấu trúc mới (theo LOẠI câu hỏi) trước khi vẽ."
        )
    return _sap_xep(d)


def _gop(d: pd.DataFrame, cot: str) -> float:
    """Gộp CÓ TRỌNG SỐ theo `num_questions` — trung bình của các nhóm KHÁC trung
    bình đơn giản khi cỡ nhóm lệch nhau (vd văn bản 192 câu vs ngoài-phạm-vi 30
    câu). Đây là chỗ DUY NHẤT định nghĩa cách gộp, dùng chung cho mọi hình + cho
    `tests/test_bao_cao_so_lieu.py`.
    """
    n = d["num_questions"]
    return float((d[cot] * n).sum() / n.sum())


# --- Hình 1: thành phần bộ câu hỏi theo loại -----------------------------------
def ve_phan_bo_loai(d: pd.DataFrame) -> Path:
    tong = int(d["num_questions"].sum())
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    y = list(range(len(d)))
    for i, (_, r) in enumerate(d.iterrows()):
        loai = r["loai_cau_hoi"]
        ty_le = r["num_questions"] / tong
        ax.barh(i, r["num_questions"], height=0.55, color=MAU_LOAI[loai],
                hatch=GACH_LOAI[loai], edgecolor=NEN, linewidth=0.8)
        ax.text(r["num_questions"] + tong * 0.01, i,
                f"{int(r['num_questions'])} câu ({_so(ty_le * 100, 1)}%)",
                va="center", ha="left", fontsize=9, color=MUC_PHU)
    ax.set_yticks(y)
    ax.set_yticklabels([TEN_LOAI.get(l, l) for l in d["loai_cau_hoi"]])
    ax.set_xlim(0, tong * 1.28)
    ax.set_xlabel("Số câu hỏi")
    ax.set_title(f"Thành phần bộ câu hỏi theo loại — {tong} câu",
                 loc="left", color=MUC_CHINH, pad=14)
    _don_khung(ax, "x")
    return _luu(fig, "phan_bo_loai_cau_hoi.png")


# --- Hình 2: điểm giám khảo theo loại câu hỏi ----------------------------------
def ve_judge_scores(d: pd.DataFrame) -> Path:
    tieu_chi = [("judge_correctness", "Tính đúng"),
                ("judge_faithfulness", "Độ trung thực"),
                ("judge_relevancy", "Độ liên quan")]
    n_loai = len(d)
    cao = 0.8 / max(n_loai, 1)
    fig, ax = plt.subplots(figsize=(7.8, 3.6))
    for j, (_, r) in enumerate(d.iterrows()):
        loai = r["loai_cau_hoi"]
        for i, (cot, _ten) in enumerate(tieu_chi):
            lech = (j - (n_loai - 1) / 2) * cao
            gia_tri = r[cot]
            ax.barh(i + lech, gia_tri, height=cao * 0.92, color=MAU_LOAI[loai],
                    hatch=GACH_LOAI[loai], edgecolor=NEN, linewidth=0.6)
            if pd.notna(gia_tri):
                ax.text(gia_tri + 0.05, i + lech, _so(gia_tri, 2), va="center",
                        ha="left", fontsize=8, color=MUC_PHU)
    ax.set_yticks(range(len(tieu_chi)))
    ax.set_yticklabels([t[1] for t in tieu_chi])
    ax.set_xlim(0, 5.6)
    ax.set_xticks([0, 1, 2, 3, 4, 5])
    ax.set_xlabel("Điểm giám khảo (thang 1–5)")
    ax.set_title("Chất lượng câu trả lời theo LOẠI câu hỏi (giám khảo LLM độc lập)",
                 loc="left", color=MUC_CHINH, pad=30)
    _don_khung(ax, "x")
    tay = [plt.Rectangle((0, 0), 1, 1, facecolor=MAU_LOAI[l], hatch=GACH_LOAI[l],
                         edgecolor=NEN) for l in d["loai_cau_hoi"]]
    ax.legend(tay, [TEN_LOAI.get(l, l) for l in d["loai_cau_hoi"]],
              loc="lower left", bbox_to_anchor=(0, 1.0), ncol=len(d))
    return _luu(fig, "judge_scores_theo_loai.png")


def _luu(fig, ten: str) -> Path:
    THU_MUC_HINH.mkdir(parents=True, exist_ok=True)
    duong = THU_MUC_HINH / ten
    fig.savefig(duong)
    plt.close(fig)
    return duong


def main() -> int:
    _dat_kieu()
    d = _doc_eval()
    tong_cau = int(d["num_questions"].sum())
    for ham in (ve_phan_bo_loai, ve_judge_scores):
        duong = ham(d)
        print("  đã ghi", duong.relative_to(GOC))
    print(f"\n2 hình sinh từ {CSV_EVAL.name} — {tong_cau} câu / {len(d)} loại.")
    print("Số gộp có trọng số theo loại (dùng trong Chương 4):")
    for cot, ten in [("judge_correctness", "Tính đúng /5"),
                     ("judge_faithfulness", "Độ trung thực /5"),
                     ("judge_relevancy", "Độ liên quan /5")]:
        print(f"  {ten:26s} {_so(_gop(d, cot), 4)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
