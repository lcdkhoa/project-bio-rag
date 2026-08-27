# -*- coding: utf-8 -*-
"""Bước 1 của kế hoạch hybrid Tesseract + MinerU (D-56, D-144): đo precision/
recall của gate `formula_gate.is_formula_suspect` trên gold set 97 ô người đã
duyệt tay (`document/review/ocr_gold/`), thay vì đoán ngưỡng.

Thiết kế: `document/specs/2026-08-27-formula-ocr-hybrid-prompt.md` §3 Bước 1.

## Nhãn "đúng" (ground truth) lấy từ đâu

KHÔNG dùng `kind` của item (`cong_thuc`/`so`/`bang`/`doi_chung`): nhãn đó do
CHÍNH `classify_line` gán khi dựng phiếu — dùng nó làm nhãn đúng để đo lại
chính cái gate suy ra từ đó là đo vòng tròn. Nhãn đúng ở đây lấy từ CÂU TRẢ LỜI
CỦA NGƯỜI: `bool(formula_tokens(gold))` — dòng đó có thật sự chứa một token
công thức hay không, theo NGƯỜI đã xác nhận, độc lập với việc Tesseract đọc
đúng hay sai. Ô loại `bang` bị loại khỏi phép đo này: bảng là bệnh khác (D-63,
mất quan hệ hàng/cột), không phải công thức bị vỡ chỉ số dưới.

## Vì sao quét ngưỡng thay vì chỉ in một con số

D-57 quét `COVERAGE_MIN` bằng cách đo agreement ở nhiều ngưỡng rồi mới chọn.
Ở đây tương tự: điểm gợi ý là mật độ tín hiệu-hỏng / số từ trong dòng, quét từ
0,00 đến 1,04 bước 0,02. Kết quả (xem D-144) là recall đạt tối đa NGAY ở biên
"có ít nhất một khớp", và tăng ngưỡng chỉ làm recall rơi mà không đổi precision
đáng kể — nghĩa là điểm liên tục không mua được gì, gate cuối cùng là quy tắc
nhị phân `is_formula_suspect` (D-56 hai tín hiệu OR nhau), không phải một tham
số cần chỉnh. In cả bảng quét ra để "đã đo, không đoán" có bằng chứng tái lập
được, không chỉ có kết luận.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.etl.layout.formula_gate import is_formula_suspect
from src.etl.layout.formula_signals import CO_DAU_BANG, CONG_THUC_HONG
from src.test.ocr_bakeoff import KHONG_DOC_DUOC, formula_tokens

GOLD_DIR = Path("document/review/ocr_gold")


def _suspect_score(text: str) -> float:
    """Mật độ tín hiệu-hỏng / số từ — dùng để QUÉT, không phải để chốt gate.

    Gate chốt (`is_formula_suspect`) là nhị phân; hàm này chỉ tồn tại để in
    bảng quét minh hoạ vì sao ngưỡng liên tục không mua được gì (xem docstring
    module).
    """
    t = str(text or "")
    n = len(CONG_THUC_HONG.findall(t)) + len(CO_DAU_BANG.findall(t))
    words = max(1, len(t.split()))
    return n / words


def load_labeled_items():
    """Nạp 97 ô + đáp án người, gắn nhãn đúng, loại ô `bang`/`???`/rỗng.

    Trả về list `(item, label, may_doc)`. `may_doc` là chữ Tesseract đọc được
    — đúng tín hiệu gate thấy được lúc ETL chạy thật, KHÔNG phải đáp án người.
    """
    items = json.loads((GOLD_DIR / "items.json").read_text(encoding="utf-8"))
    raw = json.loads((GOLD_DIR / "phieu_nguoi.json").read_text(encoding="utf-8"))
    gold = raw.get("traloi", raw)

    out = []
    for it in items:
        if it.get("kind") == "bang":
            continue  # bảng là bệnh khác (D-63), không phải công thức vỡ
        g = str(gold.get(it["id"], "") or "").strip()
        if not g or g == KHONG_DOC_DUOC:
            continue  # không có đáp án người -> không có nhãn đúng để so
        label = bool(formula_tokens(g))
        out.append((it, label, it.get("may_doc", "") or ""))
    return out


def sweep(rows) -> None:
    thresholds = [i / 100 for i in range(0, 105, 2)]
    head = f"{'nguong':>7} {'TP':>3} {'FP':>3} {'FN':>3} {'TN':>3} {'prec':>6} {'rec':>6} {'f1':>6}"
    print(head)
    print("-" * len(head))
    for t in thresholds:
        tp = fp = fn = tn = 0
        for _it, label, text in rows:
            pred = _suspect_score(text) > t
            if pred and label:
                tp += 1
            elif pred and not label:
                fp += 1
            elif not pred and label:
                fn += 1
            else:
                tn += 1
        prec = tp / (tp + fp) if (tp + fp) else 1.0
        rec = tp / (tp + fn) if (tp + fn) else 1.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        print(f"{t:7.2f} {tp:3d} {fp:3d} {fn:3d} {tn:3d} {prec:6.3f} {rec:6.3f} {f1:6.3f}")


def score_gate(rows):
    tp = fp = fn = tn = 0
    fps = []
    for it, label, text in rows:
        pred = is_formula_suspect(text)
        if pred and label:
            tp += 1
        elif pred and not label:
            fp += 1
            fps.append(it)
        elif not pred and label:
            fn += 1
        else:
            tn += 1
    prec = tp / (tp + fp) if (tp + fp) else 1.0
    rec = tp / (tp + fn) if (tp + fn) else 1.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "prec": prec, "rec": rec,
            "fps": fps}


def per_publisher(rows):
    stats = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
    for it, label, text in rows:
        nxb = it.get("quyen", "").split("_")[-1]
        pred = is_formula_suspect(text)
        key = "tp" if (pred and label) else "fp" if (pred and not label) \
            else "fn" if (not pred and label) else "tn"
        stats[nxb][key] += 1
    return stats


def main() -> int:
    rows = load_labeled_items()
    n_nxb = len({it.get("quyen", "") for it, _l, _t in rows})
    print(f"{len(rows)} ô có nhãn (loại ô `bang`/`???`/rỗng), "
          f"{sum(1 for _i, l, _t in rows if l)} nhãn công thức=True, "
          f"{n_nxb} quyển khác nhau")
    print()
    sweep(rows)

    print("\n== Gate chốt (is_formula_suspect, nhị phân) ==")
    st = score_gate(rows)
    print(f"TP={st['tp']} FP={st['fp']} FN={st['fn']} TN={st['tn']}  "
          f"precision={st['prec']:.4f}  recall={st['rec']:.4f}")

    print("\n== Theo NXB ==")
    for nxb, s in sorted(per_publisher(rows).items()):
        p = s["tp"] / (s["tp"] + s["fp"]) if (s["tp"] + s["fp"]) else 1.0
        r = s["tp"] / (s["tp"] + s["fn"]) if (s["tp"] + s["fn"]) else 1.0
        print(f"  {nxb:6s} tp={s['tp']} fp={s['fp']} fn={s['fn']} tn={s['tn']}"
              f"  precision={p:.3f} recall={r:.3f}")

    if st["fps"]:
        print(f"\n== {len(st['fps'])} ô false-positive — MỞ RA XEM (CẤM #11), "
              "không kết luận từ bảng ==")
        for it in st["fps"]:
            print(f"  {it['id']}: {it.get('may_doc', '')!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
