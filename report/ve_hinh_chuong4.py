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


# --- Hình 3: so sánh hiệu năng 4 phương pháp truy xuất --------------------------
def ve_so_sanh_truy_xuat() -> Path:
    phuong_phap = [
        "BM25 thuần",
        "Ngữ nghĩa véc-tơ đặc",
        "Truy xuất lai (tắt rerank)",
        "Đề xuất (Lai + Tái xếp hạng)",
    ]
    mau_pp = ["#9a988f", "#eb6834", "#2a78d6", "#1baf7a"]
    gach_pp = ["..", "//", "", "\\\\"]
    chi_so = ["MRR", "R@1", "R@3", "R@5", "R@10"]

    du_lieu = {
        "BM25 thuần": [0.6636, 0.0905, 0.1475, 0.1796, 0.2303],
        "Ngữ nghĩa véc-tơ đặc": [0.5664, 0.0647, 0.1338, 0.1778, 0.2302],
        "Truy xuất lai (tắt rerank)": [0.6947, 0.0914, 0.1609, 0.2031, 0.2643],
        "Đề xuất (Lai + Tái xếp hạng)": [0.7789, 0.1041, 0.1804, 0.2085, 0.2458],
    }

    n_pp = len(phuong_phap)
    n_cs = len(chi_so)
    x = range(n_cs)
    be_rong = 0.19

    fig, ax = plt.subplots(figsize=(9.2, 4.3))
    for i, pp in enumerate(phuong_phap):
        toa_do = [xi + (i - (n_pp - 1) / 2) * be_rong for xi in x]
        gia_tri = du_lieu[pp]
        cot = ax.bar(
            toa_do, gia_tri, width=be_rong * 0.92,
            label=pp, color=mau_pp[i], hatch=gach_pp[i],
            edgecolor=NEN, linewidth=0.6
        )
        for thanh, v in zip(cot, gia_tri):
            ax.text(
                thanh.get_x() + thanh.get_width() / 2, v + 0.015,
                _so(v, 2), ha="center", va="bottom",
                fontsize=8, color=MUC_PHU
            )

    ax.set_xticks(list(x))
    ax.set_xticklabels(chi_so, fontsize=10, fontweight="bold")
    ax.set_ylabel("Giá trị chỉ số", fontsize=10)
    ax.set_ylim(0, 0.92)
    ax.set_title("So sánh định lượng hiệu năng truy xuất giữa bốn phương pháp (210 câu hỏi có nhãn)",
                 loc="left", color=MUC_CHINH, pad=26)
    _don_khung(ax, "y")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=n_pp, fontsize=8.2)
    return _luu(fig, "so_sanh_truy_xuat.png")


# --- Hình 4: đối chiếu chất lượng câu trả lời đa phương thức (Bảng 4.9) -------
def ve_so_sanh_da_phuong_thuc() -> Path:
    import numpy as np
    tieu_chi = ["Tính đúng", "Độ trung thực", "Độ liên quan"]
    thuan_vb = [3.077, 3.654, 3.904]
    da_pt = [3.000, 3.615, 3.865]
    chenh_lech = [-0.077, -0.038, -0.038]

    x = np.arange(len(tieu_chi))
    width = 0.28

    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    rects1 = ax.bar(x - width/2, thuan_vb, width, label="Cấu hình thuần văn bản",
                    color=XANH, edgecolor=NEN, linewidth=0.8)
    rects2 = ax.bar(x + width/2, da_pt, width, label="Cấu hình đa phương thức",
                    color=CAM, hatch="//", edgecolor=NEN, linewidth=0.8)

    for rect in rects1:
        h = rect.get_height()
        ax.annotate(f"{h:.3f}".replace(".", ","),
                    xy=(rect.get_x() + rect.get_width() / 2, h),
                    xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8.5, color=MUC_CHINH)

    for rect, delta in zip(rects2, chenh_lech):
        h = rect.get_height()
        delta_str = f"{delta:.3f}".replace(".", ",")
        ax.annotate(f"{h:.3f}".replace(".", ",") + f"\n({delta_str})",
                    xy=(rect.get_x() + rect.get_width() / 2, h),
                    xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8.5, color="#c2410c")

    ax.set_ylabel("Điểm giám khảo (thang 1–5)", fontsize=9.5, color=MUC_PHU)
    ax.set_title("Đối chiếu chất lượng câu trả lời trên 52 câu hỏi hình ảnh (Cấu hình M2C)",
                 loc="left", pad=22, fontsize=10.5, color=MUC_CHINH)
    ax.set_xticks(x)
    ax.set_xticklabels(tieu_chi, fontsize=9.5, fontweight="bold")
    ax.set_ylim(0, 4.6)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False, fontsize=9)
    _don_khung(ax, "y")
    return _luu(fig, "so_sanh_da_phuong_thuc.png")


# --- Hình 5: sơ đồ quy trình thực nghiệm đánh giá tự động hai pha ------------
def ve_quy_trinh_danh_gia_hai_pha() -> Path:
    import matplotlib.patches as patches

    fig, ax = plt.subplots(figsize=(17.5, 9.6), dpi=220)
    ax.set_xlim(0, 17.5)
    ax.set_ylim(0, 9.6)
    ax.axis("off")
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")

    def draw_node(x, y, w, h, title, subtitle, items, is_rounded=False):
        boxstyle = "round,pad=0.25,rounding_size=0.25" if is_rounded else "square,pad=0.2"
        card = patches.FancyBboxPatch((x, y), w, h, boxstyle=boxstyle,
                                      facecolor="#ffffff", edgecolor="#000000", linewidth=1.3, zorder=3)
        ax.add_patch(card)

        ax.text(x + w / 2, y + h - 0.35, title, ha="center", va="center",
                fontsize=10.5, fontweight="bold", color="#000000", zorder=4, family="DejaVu Sans")

        if subtitle:
            ax.text(x + w / 2, y + h - 0.70, subtitle, ha="center", va="center",
                    fontsize=8.5, fontstyle="normal", color="#475569", zorder=4, family="DejaVu Sans")
            start_y = y + h - 1.02
        else:
            start_y = y + h - 0.75

        ax.plot([x + 0.2, x + w - 0.2], [start_y + 0.15, start_y + 0.15],
                color="#cbd5e1", linewidth=0.8, zorder=4)

        n = len(items)
        spacing = (start_y - y - 0.25) / max(n, 1)
        for i, it in enumerate(items):
            cur_y = start_y - 0.15 - i * spacing
            bold = it.startswith("•") or it.startswith("★")
            indent = 0.32 if it.startswith("  -") else 0.15
            color = "#000000" if bold else "#334155"
            weight = "bold" if bold else "normal"
            ax.text(x + indent, cur_y, it, ha="left", va="center", fontsize=8.2,
                    color=color, fontweight=weight, zorder=4, family="DejaVu Sans")

    def draw_badge(cx, cy, text):
        ax.text(cx, cy, text, ha="center", va="center", fontsize=8.2, fontweight="bold",
                color="#000000", zorder=6, family="DejaVu Sans",
                bbox=dict(boxstyle="square,pad=0.25", facecolor="#ffffff", edgecolor="#000000", lw=0.9))

    # Khung PHA 1 (Dashed rectangle)
    p1_group = patches.FancyBboxPatch((4.4, 4.8), 12.5, 4.4, boxstyle="square,pad=0.1",
                                      facecolor="#ffffff", edgecolor="#475569", linewidth=1.1, linestyle="--", zorder=1)
    ax.add_patch(p1_group)
    ax.text(4.7, 8.85, "PHA 1: ĐÁNH GIÁ NĂNG LỰC TRUY XUẤT TRI THỨC (RETRIEVAL BENCHMARK)",
            fontsize=10.5, fontweight="bold", color="#000000", family="DejaVu Sans", zorder=2)

    # Khung PHA 2 (Dashed rectangle)
    p2_group = patches.FancyBboxPatch((4.4, 0.4), 12.5, 4.4, boxstyle="square,pad=0.1",
                                      facecolor="#ffffff", edgecolor="#475569", linewidth=1.1, linestyle="--", zorder=1)
    ax.add_patch(p2_group)
    ax.text(8.5, 4.45, "PHA 2: ĐÁNH GIÁ CHẤT LƯỢNG SINH NGÔN NGỮ (GENERATION BENCHMARK)",
            fontsize=10.5, fontweight="bold", color="#000000", family="DejaVu Sans", zorder=2)

    # Node đầu vào: Bộ dữ liệu kiểm thử
    draw_node(0.4, 1.2, 2.6, 7.2, "Bộ dữ liệu kiểm thử", "Quy mô 240 câu hỏi KHTN",
              ["• 158 câu văn bản (65,8%)",
               "• 52 câu hình ảnh (21,7%)",
               "• 30 câu ngoài phạm vi (12,5%)",
               "• Nhãn nguồn (B*, p*):",
               "  - Sách và số trang in gốc",
               "• Đáp án chuẩn đối sánh:",
               "  - Ground Truth chuyên gia",
               "  - human-reviewed: true",
               "• Lấy mẫu phân tầng:",
               "  - Cố định seed = 42"],
              is_rounded=True)

    # Các Node Pha 1
    draw_node(4.7, 5.1, 3.3, 3.3, "Truy xuất lai & Tái xếp hạng", "Hybrid Retrieval & Cross-Encoder",
              ["• Kênh từ khóa Okapi BM25",
               "  - Tham số: k1 = 0,7, b = 0,75",
               "• Kênh ngữ nghĩa BAAI/bge-m3",
               "  - Véc-tơ không gian 1024 chiều",
               "• Hợp nhất ứng viên Top-40 (RRF)",
               "• Tái xếp hạng bge-reranker-v2-m3",
               "  - Phân tích tương tác chéo câu hỏi",
               "• Lọc tin cậy: score >= 0,59"],
              is_rounded=False)

    draw_node(9.3, 5.1, 3.3, 3.3, "Đối sánh nhãn nguồn chuẩn", "Ground Truth Verification",
              ["• Tập ứng viên sau rerank: R_k",
               "  - k = 1, 3, 5, 10 đoạn văn bản",
               "• Tập phân đoạn chuẩn: G",
               "  - Toàn bộ đoạn thuộc (B*, p*)",
               "• Tiêu chí so khớp nghiêm ngặt:",
               "  - Khớp tuyệt đối số trang in gốc",
               "• Giới hạn trần tranP@k lý thuyết",
               "• F1@k Macro tuân thủ Jensen"],
              is_rounded=False)

    draw_node(13.9, 5.1, 2.7, 3.3, "Chỉ số IR đạt được", "Retrieval Performance",
              ["★ MRR = 0,7789 (Hạng 1)",
               "• Recall@1 = 0,1041",
               "• Recall@3 = 0,1804",
               "• Recall@5 = 0,2085",
               "• Recall@10 = 0,2458",
               "• Precision@5 = 0,2810",
               "  - Trần lý thuyết: 0,9867",
               "• Macro F1@k trung thực"],
              is_rounded=True)

    # Các Node Pha 2
    draw_node(4.7, 0.7, 3.3, 3.3, "Ghép Prompt & Sinh lời giải", "Prompt Augmentation & Local LLM",
              ["• Ghép Top-3 đoạn làm ngữ cảnh",
               "• Chỉ thị sư phạm chống ảo giác:",
               "  - Ràng buộc tuyệt đối vào SGK",
               "  - Không tự suy diễn ngoài sách",
               "• Mô hình: Qwen2.5-3B-Instruct",
               "  - Nhiệt độ thấp: temp = 0.1",
               "• Xuất câu trả lời hoàn chỉnh",
               "  - Kèm trích dẫn số trang SGK"],
              is_rounded=False)

    draw_node(9.3, 0.7, 3.3, 3.3, "Hội đồng Giám khảo độc lập", "Independent LLM Judge (Groq)",
              ["• 4 mô hình luân phiên:",
               "  - qwen/qwen3.8-27b",
               "  - qwen/qwen3.6-27b",
               "  - openai/gpt-oss-120b",
               "  - openai/gpt-oss-20b",
               "• Phương pháp thử lại (Retry):",
               "  - Tối đa 3 lần cho lỗi 429",
               "  - Thời gian chờ lũy tiến",
               "  - Luân chuyển mô hình dự phòng"],
              is_rounded=False)

    draw_node(13.9, 0.7, 2.7, 3.3, "Điểm chất lượng sinh", "Generation Scores (1 - 5)",
              ["★ Tính đúng: 4,033 / 5",
               "  - Chuẩn xác kiến thức KHTN",
               "★ Độ trung thực: 4,417 / 5",
               "  - Bám sát ngữ cảnh SGK",
               "★ Độ liên quan: 4,492 / 5",
               "  - Trực diện vào trọng tâm",
               "• Từ chối ngoài phạm vi:",
               "  - 96,67% (29/30 câu chuẩn xác)"],
              is_rounded=True)

    # Mũi tên liên kết Flowchart
    arrow_kw = dict(arrowstyle="-|>", color="#000000", lw=1.3, mutation_scale=12)

    # Bộ dữ liệu -> Pha 1
    ax.annotate("", xy=(4.7, 6.75), xytext=(3.0, 6.75), arrowprops=arrow_kw, zorder=5)
    draw_badge(3.85, 6.75, "210 câu có nhãn")

    # Bộ dữ liệu -> Pha 2
    ax.annotate("", xy=(4.7, 2.35), xytext=(3.0, 2.35), arrowprops=arrow_kw, zorder=5)
    draw_badge(3.85, 2.35, "240 câu kiểm thử")

    # Pha 1: 1.1 -> 1.2
    ax.annotate("", xy=(9.3, 6.75), xytext=(8.0, 6.75), arrowprops=arrow_kw, zorder=5)
    draw_badge(8.65, 6.75, "Top-k đoạn")

    # Pha 1: 1.2 -> 1.3
    ax.annotate("", xy=(13.9, 6.75), xytext=(12.6, 6.75), arrowprops=arrow_kw, zorder=5)
    draw_badge(13.25, 6.75, "Đối sánh IR")

    # Liên kết giữa hai pha: Top-3 ngữ cảnh từ Truy xuất xuống Ghép Prompt
    ax.annotate("", xy=(6.35, 4.0), xytext=(6.35, 5.1),
                arrowprops=dict(arrowstyle="-|>", color="#000000", lw=1.3, linestyle="-", mutation_scale=12),
                zorder=5)
    draw_badge(6.35, 4.55, "Top-3 ngữ cảnh")

    # Pha 2: 2.1 -> 2.2
    ax.annotate("", xy=(9.3, 2.35), xytext=(8.0, 2.35), arrowprops=arrow_kw, zorder=5)
    draw_badge(8.65, 2.35, "(q, gt, ctx, ans)")

    # Pha 2: 2.2 -> 2.3
    ax.annotate("", xy=(13.9, 2.35), xytext=(12.6, 2.35), arrowprops=arrow_kw, zorder=5)
    draw_badge(13.25, 2.35, "Chấm điểm")

    return _luu(fig, "quy_trinh_danh_gia_hai_pha.png")


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
    duong_ss = ve_so_sanh_truy_xuat()
    print("  đã ghi", duong_ss.relative_to(GOC))
    duong_m2c = ve_so_sanh_da_phuong_thuc()
    print("  đã ghi", duong_m2c.relative_to(GOC))
    duong_pipe = ve_quy_trinh_danh_gia_hai_pha()
    print("  đã ghi", duong_pipe.relative_to(GOC))
    print(f"\n5 hình sinh cho Chương 4 — {tong_cau} câu / {len(d)} loại.")
    print("Số gộp có trọng số theo loại (dùng trong Chương 4):")
    for cot, ten in [("judge_correctness", "Tính đúng /5"),
                     ("judge_faithfulness", "Độ trung thực /5"),
                     ("judge_relevancy", "Độ liên quan /5")]:
        print(f"  {ten:26s} {_so(_gop(d, cot), 4)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

