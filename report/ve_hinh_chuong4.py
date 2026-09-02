# -*- coding: utf-8 -*-
"""Sinh lại 5 hình của Chương 4 từ SỐ ĐO THẬT, không vẽ tay.

Trước script này, `report/tex_source/src/images/chapter4/*.png` là năm tệp PNG
dựng từ bộ 120 câu của báo cáo chuyên đề cũ, và repo **không có** mã nguồn nào
sinh ra chúng (`grep -rl matplotlib src/ report/ scripts/` = 0). Một hình không
tái lập được là một con số không kiểm được: người đọc không có cách nào đối
chiếu nó với dữ liệu, và người viết không có cách nào cập nhật nó khi dữ liệu
đổi. Nên mọi giá trị dưới đây đọc thẳng từ hai tệp kết quả:

  - `src/test/evaluation_report_240.csv`  (12 quyển, 240 câu, D-173/D-174)
  - `src/test/ablation_report_240.csv`    (30 hàng đối chiếu cấu hình, D-173/D-174)

Không hằng số nào được gõ tay. Đổi dữ liệu -> chạy lại -> hình đổi theo.

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
CSV_EVAL = GOC / "src" / "test" / "evaluation_report_240.csv"
CSV_ABLATION = GOC / "src" / "test" / "ablation_report_240.csv"
THU_MUC_HINH = GOC / "report" / "tex_source" / "src" / "images" / "chapter4"

# --- bảng màu (xem docstring) -------------------------------------------------
XANH = "#2a78d6"     # ô phân loại 1
CAM = "#eb6834"      # ô phân loại 2
NGOC = "#1baf7a"     # ô phân loại 3
# thang thứ bậc một sắc (xanh dương, nhạt -> đậm), đã qua bộ kiểm --ordinal
THANG = ["#86b6ef", "#2a78d6", "#184f95"]

MUC_CHINH = "#0b0b0b"
MUC_PHU = "#52514e"
MUC_MO = "#898781"
LUOI = "#e1e0d9"
NEN = "#fcfcfb"

# Gạch chéo đi kèm màu, để bản in đen trắng vẫn đọc được. Chỉ dùng 45° và ảnh
# gương 135° của nó — hai góc này phân biệt tốt mà không làm rối mặt cột.
GACH = {"CD": "", "CTST": "/", "KNTT": "\\"}
MAU_NXB = {"CD": XANH, "CTST": CAM, "KNTT": NGOC}
TEN_NXB = {"CD": "Cánh Diều", "CTST": "Chân trời sáng tạo",
           "KNTT": "Kết nối tri thức"}


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


def _nxb(book: str) -> str:
    return book.rsplit("_", 1)[-1]


def _nhan_sach(book: str) -> str:
    # SGK_KHTN_8_KNTT -> "KHTN 8 · Kết nối tri thức"
    phan = book.split("_")
    return f"KHTN {phan[2]} · {TEN_NXB[phan[3]]}"


def _doc_eval() -> pd.DataFrame:
    if not CSV_EVAL.exists():
        raise SystemExit(f"Không thấy {CSV_EVAL} — chưa chạy evaluator?")
    d = pd.read_csv(CSV_EVAL)
    d["nxb"] = d["book"].map(_nxb)
    d["nhan"] = d["book"].map(_nhan_sach)
    return d


def _gop(d: pd.DataFrame, cot: str) -> float:
    """Gộp theo CÂU, không phải trung bình theo quyển.

    Số câu mỗi quyển không bằng nhau (17--20 vì 9/48 khung cắt bị người duyệt
    loại), nên trung bình của 12 trung bình KHÁC trung bình của 231 câu. Báo cáo
    dùng số gộp; hàm này là chỗ duy nhất định nghĩa nó.
    """
    n = d["num_questions"]
    return float((d[cot] * n).sum() / n.sum())


# --- Hình 1: xếp hạng tổng thể ------------------------------------------------
def ve_leaderboard(d: pd.DataFrame, tong_cau: int) -> Path:
    d = d.sort_values("overall_score")
    fig, ax = plt.subplots(figsize=(8.2, 5.0))
    y = range(len(d))
    for i, (_, r) in enumerate(d.iterrows()):
        ax.barh(i, r["overall_score"], height=0.68,
                color=MAU_NXB[r["nxb"]], hatch=GACH[r["nxb"]],
                edgecolor=NEN, linewidth=0.8)
        ax.text(r["overall_score"] + 0.008, i, _so(r["overall_score"]),
                va="center", ha="left", fontsize=9, color=MUC_PHU)
    ax.set_yticks(list(y))
    ax.set_yticklabels(d["nhan"])
    ax.set_xlim(0, 1.0)
    ax.set_xlabel("Điểm tổng thể (overall)")
    ax.set_title(f"Xếp hạng 12 cuốn sách theo điểm tổng thể — {tong_cau} câu hỏi",
                 loc="left", color=MUC_CHINH, pad=30)
    _don_khung(ax, "x")
    tay = [plt.Rectangle((0, 0), 1, 1, facecolor=MAU_NXB[k], hatch=GACH[k],
                         edgecolor=NEN) for k in ("CD", "CTST", "KNTT")]
    ax.legend(tay, [TEN_NXB[k] for k in ("CD", "CTST", "KNTT")],
              loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3)
    return _luu(fig, "leaderboard.png")


# --- Hình 2: truy xuất so với câu trả lời -------------------------------------
def ve_retrieval_vs_answer(d: pd.DataFrame) -> Path:
    d = d.sort_values("overall_score")
    fig, ax = plt.subplots(figsize=(8.2, 5.4))
    cao = 0.38
    vi_tri = list(range(len(d)))
    ax.barh([v + cao / 2 for v in vi_tri], d["retrieval_score"], height=cao,
            color=XANH, edgecolor=NEN, linewidth=0.8, label="Điểm truy xuất")
    ax.barh([v - cao / 2 for v in vi_tri], d["answer_score"], height=cao,
            color=CAM, hatch="/", edgecolor=NEN, linewidth=0.8,
            label="Điểm câu trả lời")

    tb_r = _gop(d, "retrieval_score")
    tb_a = _gop(d, "answer_score")
    ax.axvline(tb_r, color=XANH, linestyle="--", linewidth=1.2, alpha=0.8)
    ax.axvline(tb_a, color=CAM, linestyle="--", linewidth=1.2, alpha=0.8)
    # Nhãn đường trung bình đặt dưới đáy trục để không đè lên cột nào; chính
    # đường đứt cùng màu đã mang danh tính, nên chữ giữ mực trung tính.
    ax.text(tb_r, -0.95, f"TB truy xuất {_so(tb_r)}", color=MUC_PHU,
            fontsize=8.5, ha="right", va="top")
    ax.text(tb_a, -0.95, f"TB trả lời {_so(tb_a)}", color=MUC_PHU,
            fontsize=8.5, ha="left", va="top")

    ax.set_yticks(vi_tri)
    ax.set_yticklabels(d["nhan"])
    ax.set_xlim(0, 1.0)
    ax.set_ylim(-1.6, len(d) - 0.3)
    ax.set_xlabel("Điểm thành phần (0–1)")
    ax.set_title("Hai thành phần của điểm tổng thể theo từng cuốn",
                 loc="left", color=MUC_CHINH, pad=30)
    _don_khung(ax, "x")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2)
    return _luu(fig, "retrieval_vs_answer.png")


# --- Hình 3: Recall@k thô so với production ------------------------------------
def ve_recall_at_k(d: pd.DataFrame, tong_cau: int) -> Path:
    ks = [3, 5, 10]
    tho = [_gop(d, f"recall@{k}_raw") for k in ks]
    prod = _gop(d, "recall_page")

    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    x = list(range(len(ks)))
    for i, (k, v) in enumerate(zip(ks, tho)):
        ax.bar(i, v, width=0.55, color=THANG[i], edgecolor=NEN, linewidth=0.8)
        ax.text(i, v + 0.012, _so(v), ha="center", va="bottom", fontsize=9,
                color=MUC_PHU)
    ax.bar(len(ks), prod, width=0.55, color=CAM, hatch="/", edgecolor=NEN,
           linewidth=0.8)
    ax.text(len(ks), prod + 0.012, _so(prod), ha="center", va="bottom",
            fontsize=9, color=MUC_CHINH, fontweight="bold")

    # Đường đứt = trần đo được của RIÊNG kênh ngữ nghĩa. Nhãn đặt ngay trên
    # đường, phía trên đỉnh cột cao nhất, để không đè lên nhãn giá trị nào.
    ax.axhline(tho[-1], color=THANG[2], linestyle="--", linewidth=1.1,
               alpha=0.9)
    ax.text(-0.42, tho[-1] + 0.055,
            "trần của RIÊNG kênh ngữ nghĩa (top-10 thô, chưa hợp nhất, "
            "chưa xếp hạng lại)",
            fontsize=8.5, color=MUC_PHU, ha="left", va="bottom")

    ax.set_xticks(x + [len(ks)])
    ax.set_xticklabels([f"top-{k} thô\n(ngữ nghĩa)" for k in ks]
                       + ["cấu hình thật\n(lai + xếp hạng lại)"])
    ax.set_ylim(0, 1.14)
    ax.set_yticks([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_ylabel("Recall ở mức trang")
    ax.set_title(f"Cấu hình thật VƯỢT trần của kênh ngữ nghĩa — {tong_cau} câu hỏi",
                 loc="left", color=MUC_CHINH)
    _don_khung(ax, "y")
    return _luu(fig, "recall_at_k.png")


# --- Hình 4: Recall@k theo từng cuốn -------------------------------------------
def ve_recall_per_book(d: pd.DataFrame) -> Path:
    d = d.sort_values("recall_page")
    ks = [3, 5, 10]
    fig, ax = plt.subplots(figsize=(8.6, 5.4))
    cao = 0.24
    vi_tri = list(range(len(d)))
    for i, k in enumerate(ks):
        lech = (i - 1) * cao
        ax.barh([v + lech for v in vi_tri], d[f"recall@{k}_raw"], height=cao,
                color=THANG[i], edgecolor=NEN, linewidth=0.6,
                label=f"top-{k} thô (ngữ nghĩa)")
    ax.scatter(d["recall_page"], vi_tri, marker="D", s=34, color=CAM,
               edgecolor=NEN, linewidth=0.8, zorder=5,
               label="cấu hình thật (lai + xếp hạng lại)")

    ax.set_yticks(vi_tri)
    ax.set_yticklabels(d["nhan"])
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("Recall ở mức trang")
    ax.set_title("Recall theo từng cuốn: cấu hình thật so với top-k thô",
                 loc="left", color=MUC_CHINH, pad=30)
    _don_khung(ax, "x")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=4,
              columnspacing=1.0, handletextpad=0.5)
    return _luu(fig, "recall_per_book.png")


# --- Hình 5: điểm giám khảo ----------------------------------------------------
def ve_judge_scores(d: pd.DataFrame) -> Path:
    tieu_chi = [("judge_correctness", "Tính đúng", XANH, ""),
                ("judge_faithfulness", "Độ trung thực", CAM, "/"),
                ("judge_relevancy", "Độ liên quan", NGOC, "\\")]
    fig, ax = plt.subplots(figsize=(7.8, 3.2))
    for i, (cot, ten, mau, gach) in enumerate(tieu_chi):
        tb = _gop(d, cot)
        ax.barh(i, tb, height=0.46, color=mau, hatch=gach, edgecolor=NEN,
                linewidth=0.8)
        # Mỗi chấm = một cuốn, đặt NGAY TRÊN cột để không đè lên mặt cột;
        # viền trắng để hai cuốn sát điểm nhau vẫn tách ra được.
        ax.scatter(d[cot], [i + 0.36] * len(d), s=22, color=MUC_PHU,
                   alpha=0.75, zorder=5, linewidth=0.6, edgecolor=NEN)
        # Nhãn giá trị dồn hết về lề phải, thẳng cột, nên không bao giờ va
        # vào chấm dù trung bình của tiêu chí nào rơi vào đâu.
        ax.text(5.45, i, _so(tb, 2), va="center", ha="right", fontsize=10.5,
                color=MUC_CHINH, fontweight="bold")
    ax.set_yticks(range(len(tieu_chi)))
    ax.set_yticklabels([t[1] for t in tieu_chi])
    ax.set_xlim(0, 5.5)
    ax.set_ylim(-0.5, len(tieu_chi) - 0.35)
    ax.set_xticks([0, 1, 2, 3, 4, 5])
    ax.set_xlabel("Điểm giám khảo (thang 1–5); mỗi chấm là một cuốn")
    ax.set_title("Chất lượng câu trả lời do mô hình giám khảo độc lập chấm",
                 loc="left", color=MUC_CHINH)
    _don_khung(ax, "x")
    return _luu(fig, "judge_scores.png")


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
    # Không hardcode tổng số câu: nó đã đổi 231->238->240 trong quá trình làm
    # đồ án (xem D-169..D-174). Tiêu đề hình lấy thẳng giá trị đo được; số
    # trong .tex phải được rà lại theo đúng tong_cau in ra dưới đây.
    for ham, can_tong_cau in ((ve_leaderboard, True), (ve_retrieval_vs_answer, False),
                              (ve_recall_at_k, True), (ve_recall_per_book, False),
                              (ve_judge_scores, False)):
        duong = ham(d, tong_cau) if can_tong_cau else ham(d)
        print("  đã ghi", duong.relative_to(GOC))
    print(f"\n5 hình sinh từ {CSV_EVAL.name} — {tong_cau} câu / {len(d)} cuốn.")
    print("Số gộp theo CÂU (dùng trong Chương 4):")
    for cot, ten in [("recall_page", "Recall (cấu hình thật)"),
                     ("mrr_page", "MRR"),
                     ("precision_page", "Precision"),
                     ("recall@3_raw", "Recall@3 thô"),
                     ("recall@5_raw", "Recall@5 thô"),
                     ("recall@10_raw", "Recall@10 thô"),
                     ("judge_correctness", "Tính đúng /5"),
                     ("judge_faithfulness", "Độ trung thực /5"),
                     ("judge_relevancy", "Độ liên quan /5")]:
        print(f"  {ten:26s} {_so(_gop(d, cot), 4)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
