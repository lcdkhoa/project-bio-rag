# -*- coding: utf-8 -*-
"""Độ phủ nhãn hình: bao nhiêu `Hình A.B` trên trang thực sự có khung cắt.

## Vì sao phép đo này đáng có, và vì sao nó KHÔNG cần người dán nhãn

Cổng G4 (`qa_figures.py`) kiểm "B liên tục 1..max" trong phạm vi vài Bài được
chọn. Nó mạnh nhưng **hẹp**: một quyển bỏ sót hình có hệ thống trên những Bài
không được lấy mẫu thì G4 không thấy.

Phép đo ở đây rộng và rẻ: chữ trên trang đã được lập chỉ mục sẵn, và mỗi nhãn
`Hình A.B` xuất hiện trong đó là **bằng chứng do chính cuốn sách đưa ra** rằng có
một hình mang số hiệu đó. So tập nhãn ấy với tập nhãn của các khung cắt thu được
cho ta một tỉ lệ phủ trên **toàn bộ quyển**, không tốn một giây OCR nào.

Chính phép đo này đã lộ ra lỗi ▲ của Chân trời sáng tạo (D-121): CD đạt 92--97%,
KNTT 95--96%, còn CTST chỉ **51--65%** --- và nguyên nhân là một ký tự.

## Giới hạn phải nói rõ khi trích số

Nhãn trong chữ có thể là **tham chiếu thân bài** ("Quan sát Hình 2.1...") chứ
không phải chú thích, và trang chứa tham chiếu có thể khác trang chứa hình. Vì
vậy đây là một **cận dưới có nhiễu**, không phải tỉ lệ tuyệt đối: dùng nó để so
sánh giữa các quyển và để phát hiện tụt hạng, đừng công bố nó như "độ chính xác".
Đếm theo nhãn KHÁC NHAU (không đếm số lần xuất hiện) nên tham chiếu lặp lại nhiều
lần không thổi phồng con số.

    python -m src.test.qa_figure_coverage
    python -m src.test.qa_figure_coverage --nxb CTST --json bao_cao.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import chromadb  # noqa: E402

from src.config import PERSIST_DIR  # noqa: E402

# Chữ "H" cố ý VIẾT HOA, không dùng IGNORECASE. Chú thích hình thật luôn in hoa
# ("Hình 2.1. ..."), còn dạng viết thường gần như luôn là tham chiếu thân bài
# ("xem hình 5.2"). Đo cả hai cách trên corpus thật:
#
#     quyển        HOA (chữ/crop/phủ)      IGNORECASE (chữ/crop/phủ)
#     6_CD         215 / 203 / 94%         218 / 207 / 95%
#     9_CD         189 / 184 / 97%         230 / 193 / 84%
#     6_KNTT       245 / 233 / 95%         245 / 234 / 96%
#
# IGNORECASE kéo `9_CD` từ 97% xuống 84% vì nó thêm **41 tham chiếu** vào mẫu số
# mà chỉ thêm 9 nhãn vào tử số -- tức thêm nhiễu nhiều hơn thêm tín hiệu.
#
# Cái giá của lựa chọn này, đo được và phải nói ra: **128/2126 = 6%** khung cắt có
# `figure_label` viết thường (OCR đọc sai hoa/thường) nên không vào tử số. Vì vậy
# con số phủ ở đây là **cận dưới**, và nó bị hụt ĐỀU trên mọi quyển nên vẫn so
# sánh được giữa các quyển -- đúng mục đích của phép đo này.
FIG = re.compile(r"H[iìíỉĩị]nh\s*(\d{1,2})\s*[.,]\s*(\d{1,2})")

# Dưới mức này thì coi là bất thường, cần mở trang ra xem. Ngưỡng lấy từ phép đo
# thật: CD 92-97%, KNTT 95-96% (D-121). Không phải một con số gõ ra.
NGUONG_CANH_BAO = 0.80


def thu_thap(persist_dir: str | Path = PERSIST_DIR) -> dict:
    cl = chromadb.PersistentClient(path=str(persist_dir))
    txt = cl.get_collection("biology_text").get(
        limit=1_000_000, include=["metadatas", "documents"])
    img = cl.get_collection("biology_image_metadata").get(
        limit=1_000_000, include=["metadatas"])

    nhan_chu: dict[str, set] = defaultdict(set)
    trang_chu: dict[str, set] = defaultdict(set)
    for m, d in zip(txt["metadatas"], txt["documents"]):
        b = m.get("source")
        if not b:
            continue
        trang_chu[b].add(m.get("page"))
        nhan_chu[b].update(FIG.findall(d or ""))

    nhan_crop: dict[str, set] = defaultdict(set)
    n_doc: dict[str, int] = defaultdict(int)
    n_co_nhan: dict[str, int] = defaultdict(int)
    trang_co_hinh: dict[str, set] = defaultdict(set)
    for m in img["metadatas"]:
        b = m.get("pdf_filename")
        if not b:
            continue
        n_doc[b] += 1
        trang_co_hinh[b].add(m.get("page_number"))
        lab = (m.get("figure_label") or "").strip()
        if lab:
            n_co_nhan[b] += 1
        g = FIG.search(lab)
        if g:
            nhan_crop[b].add(g.groups())

    ra = {}
    for b in sorted(set(nhan_chu) | set(n_doc)):
        nc, ncr = len(nhan_chu[b]), len(nhan_crop[b])
        ra[b] = {
            "nhan_tren_chu": nc,
            "nhan_tu_crop": ncr,
            "phu": round(ncr / nc, 4) if nc else None,
            "n_doc": n_doc[b],
            "n_co_figure_label": n_co_nhan[b],
            "trang_co_chu": len(trang_chu[b]),
            "trang_co_hinh": len(trang_co_hinh[b]),
        }
    return ra


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nxb", default="", help="lọc theo hậu tố: KNTT / CTST / CD")
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args()

    d = thu_thap()
    if a.nxb:
        d = {k: v for k, v in d.items() if k.upper().endswith("_" + a.nxb.upper())}

    print(f"{'quyển':22s} {'nhãn/chữ':>9} {'nhãn/crop':>10} {'PHỦ':>7} "
          f"{'doc':>6} {'có nhãn':>8} {'trang có hình':>14}")
    canh_bao = []
    for b, r in d.items():
        phu = "-" if r["phu"] is None else f"{r['phu']:.0%}"
        cb = ""
        if r["phu"] is not None and r["phu"] < NGUONG_CANH_BAO:
            cb = "  <-- THẤP"
            canh_bao.append((b, r["phu"]))
        tr = f"{r['trang_co_hinh']}/{r['trang_co_chu']}"
        print(f"{b:22s} {r['nhan_tren_chu']:9d} {r['nhan_tu_crop']:10d} {phu:>7} "
              f"{r['n_doc']:6d} {r['n_co_figure_label']:8d} {tr:>14}{cb}")

    print(f"\nNgưỡng cảnh báo {NGUONG_CANH_BAO:.0%} lấy từ phép đo thật "
          f"(CD 92-97%, KNTT 95-96% — D-121), không phải số gõ tay.")
    print("Đây là CẬN DƯỚI CÓ NHIỄU: nhãn trong chữ có thể là tham chiếu thân bài, "
          "không phải chú thích. Dùng để SO SÁNH giữa các quyển, đừng công bố như "
          "độ chính xác tuyệt đối.")

    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(d, ensure_ascii=False, indent=1),
                          encoding="utf-8")
        print(f"[OK] JSON -> {a.json}")

    if canh_bao:
        print(f"\n{len(canh_bao)} quyển dưới ngưỡng: "
              f"{', '.join(f'{b} {p:.0%}' for b, p in canh_bao)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
