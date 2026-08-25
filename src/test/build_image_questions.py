"""48 câu hỏi sinh từ HÌNH — máy chọn crop, NGƯỜI nhìn ảnh và viết câu.

**Vì sao không tự động hoàn toàn (D-113, đo trên 938 crop của 4 quyển KNTT).**
Ba trường đọc lại từ pixel đều không đủ để sinh câu:

- `figure_caption` trùng chữ đã index của CHÍNH trang đó ở mức **trung vị 0,958**
  (73,3% có độ phủ >= 0,8) — câu sinh từ nó là câu VĂN BẢN đội lốt, và sẽ tái tạo
  đúng cái trần 0,104 của D-87. Lý do cấu trúc: caption trên KNTT phần lớn là câu
  lệnh bài tập quanh hình, không phải mô tả nội dung hình.
- `crop_text` độc lập với chữ trang thì **vỡ**: "H Mũi g là eì để Khi quản ụ Phối".
- `visual_caption_vi` là **0/938** — captioner tắt theo D-47 (nó bịa 4/12 và tự
  khai số hiệu hình SAI 4/4 lần).

Nên: máy chọn crop và bày ra mọi thứ nó đọc được, người **mở ảnh ra nhìn** rồi
viết câu hỏi + đáp án, hoặc gạch bỏ. Câu cuối cùng là của người. Đây cũng là lần
đầu bộ test của dự án có nhãn "người duyệt" thật cho phần mình sinh ra — pool 300
câu mới chỉ được duyệt trên MẪU 50 câu (D-90).

Hai bước, chạy rời nhau:

    python -m src.test.build_image_questions --chon      # máy chọn + chép crop + lập phiếu
    python -m src.test.build_image_questions --ap-dung   # trộn câu ĐÃ DUYỆT vào bộ 240

Phiếu theo đúng khuôn `document/review/ocr_gold/` mà người dùng đã quen:
`items.json` (máy xuất) + `phieu_nguoi.json` (`{_bat_dau, _ket_thuc, traloi}`).
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import chromadb

from src.config import PERSIST_DIR

BASE = Path(__file__).resolve().parent
OUT_DIR = Path("document/review/image_questions")
TESTSET_DIR = BASE / "testsets_240"

PER_BOOK = 4

# Chỉ lấy HÌNH thật, không lấy hộp chữ. `activity_box` / `textbook_info_box` là
# khung bài tập — chúng chính là thứ làm `figure_caption` trùng chữ trang.
FIGURE_TYPES = {"single_figure", "composite_figure", "sub_figure"}


def _client():
    return chromadb.PersistentClient(path=str(PERSIST_DIR))


def _page_texts() -> Dict[tuple, str]:
    col = _client().get_collection("biology_text")
    got = col.get(limit=100000, include=["metadatas", "documents"])
    pages: Dict[tuple, List[str]] = defaultdict(list)
    for m, d in zip(got["metadatas"], got["documents"]):
        pages[(m.get("source"), m.get("page"))].append(d or "")
    return {k: "\n".join(v) for k, v in pages.items()}


def chon(per_book: int, out_dir: Path) -> List[Dict]:
    """Chọn `per_book` hình MỖI QUYỂN, trải theo trang, chép crop ra để người xem.

    Tiêu chí chọn cố ý ĐƠN GIẢN và giải thích được: hình thật (không phải hộp
    chữ), có `figure_label` (để trích dẫn kiểm được), và mỗi trang tối đa một
    hình (trải rộng). KHÔNG lọc theo độ phủ `crop_text` — người mới là nguồn ngữ
    nghĩa ở đây, nên chất lượng OCR của crop không phải tiêu chí chọn (D-113).
    """
    col = _client().get_collection("biology_image_metadata")
    got = col.get(limit=100000, include=["metadatas"])
    page_text = _page_texts()
    crop_dir = out_dir / "crops"

    by_book: Dict[str, List[Dict]] = defaultdict(list)
    for m in got["metadatas"]:
        if (m.get("image_type") or "") not in FIGURE_TYPES:
            continue
        if not (m.get("figure_label") or "").strip():
            continue
        if not Path(m.get("image_path") or "").exists():
            continue
        by_book[m.get("pdf_filename") or "?"].append(m)

    out_dir.mkdir(parents=True, exist_ok=True)
    crop_dir.mkdir(parents=True, exist_ok=True)
    items: List[Dict] = []

    for book in sorted(by_book):
        seen_pages = set()
        picked = []
        # sắp xếp xác định: theo trang rồi theo nhãn hình
        for m in sorted(by_book[book],
                        key=lambda x: (int(x.get("page_number") or 0),
                                       str(x.get("figure_label")))):
            page = int(m.get("page_number") or 0)
            if page in seen_pages:
                continue
            seen_pages.add(page)
            picked.append(m)
            if len(picked) >= per_book:
                break

        for i, m in enumerate(picked, 1):
            page = int(m.get("page_number") or 0)
            item_id = f"{book}_p{page}_{i:02d}"
            dest = crop_dir / f"{item_id}.png"
            shutil.copyfile(m["image_path"], dest)
            items.append({
                "id": item_id,
                "quyen": book,
                "trang": page,
                "nhan_hinh": (m.get("figure_label") or "").strip(),
                "anh": dest.as_posix(),
                # ba trường đọc lại từ PIXEL — đưa nguyên trạng, kể cả khi vỡ,
                # để người thấy máy có gì mà tự đánh giá độ tin
                "figure_caption": (m.get("figure_caption") or "").strip(),
                "crop_text": (m.get("crop_text") or "").strip(),
                "chu_tren_trang": (page_text.get((book, page)) or "")[:1500],
            })

    (out_dir / "items.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return items


NHAP_PROMPT = """Bạn đang giúp soạn NHÁP cho một bộ kiểm thử sách giáo khoa KHTN.

Dưới đây là những gì máy đọc được QUANH một hình trong sách. Máy KHÔNG nhìn thấy
hình — chữ dưới đây do OCR nên có thể vỡ. Một người sẽ mở hình ra nhìn và sửa lại
câu của bạn, nên nhiệm vụ của bạn là cho họ một điểm khởi đầu, KHÔNG phải khẳng
định điều gì về hình.

Nhãn hình: {nhan_hinh}   (sách {quyen}, trang {trang})
Chú thích hình máy đọc được: {figure_caption}
Chữ đọc được TRONG hình: {crop_text}
Trích chữ trên trang: {chu_tren_trang}

Viết MỘT câu hỏi mà học sinh chỉ trả lời được khi NHÌN VÀO HÌNH, kèm đáp án ngắn.
Quy tắc:
- Câu hỏi phải nhắc tới {nhan_hinh}.
- Nếu chữ đọc được quá vỡ để biết hình vẽ gì, hãy đặt "chac_chan": false và viết
  câu hỏi tổng quát nhất có thể — ĐỪNG đoán chi tiết mình không đọc được.
- Đáp án ngắn gọn, tiếng Việt có dấu đầy đủ.

Trả về DUY NHẤT một JSON: {{"cau_hoi": "...", "dap_an": "...", "chac_chan": true/false}}"""


def nhap_bang_llm(items: List[Dict], out_dir: Path) -> Dict:
    """LLM viết NHÁP cho từng ô. Đây là nháp, không phải dữ liệu.

    D-113 đo được vì sao đây chỉ có thể là nháp: `figure_caption` trùng chữ trang
    ở mức trung vị 0,958 và `crop_text` độc lập thì vỡ. Nên mọi ô đều đi kèm
    `chac_chan` do chính model tự khai, và `--ap-dung` chỉ nhận câu NGƯỜI đã điền
    — nháp không bao giờ tự vào bộ test.
    """
    from src.test import eval_llm
    from src.test.generate_testsets import _ask_llm, _parse_json

    if not eval_llm.is_configured():
        raise SystemExit(eval_llm.config_help())
    llm = eval_llm.get_eval_llm(temperature=0.3)

    p = out_dir / "nhap_llm.json"
    nhap = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    loi = 0
    for i, it in enumerate(items, 1):
        if it["id"] in nhap:                 # chạy lại thì không gọi lại
            continue
        try:
            raw = _ask_llm(llm, NHAP_PROMPT.format(**it))
            d = _parse_json(raw)
            nhap[it["id"]] = {
                "cau_hoi": str(d.get("cau_hoi") or "").strip(),
                "dap_an": str(d.get("dap_an") or "").strip(),
                "chac_chan": bool(d.get("chac_chan")),
            }
        except Exception as exc:             # nháp hỏng thì bỏ trống, không bịa
            loi += 1
            nhap[it["id"]] = {"cau_hoi": "", "dap_an": "", "chac_chan": False,
                              "loi": str(exc)[:200]}
        p.write_text(json.dumps(nhap, ensure_ascii=False, indent=1),
                     encoding="utf-8")
        print(f"  [{i}/{len(items)}] {it['id']} "
              f"{'OK' if nhap[it['id']]['cau_hoi'] else 'TRỐNG'}")
    return {"n": len(nhap), "loi": loi,
            "khong_chac": sum(1 for v in nhap.values() if not v.get("chac_chan")),
            "file": str(p)}


def lam_phieu(items: List[Dict], out_dir: Path) -> Path:
    """Phiếu để NGƯỜI điền. Không bao giờ ghi đè phiếu đã có.

    Nháp của LLM (nếu đã chạy `--nhap`) được điền sẵn vào `cau_hoi`/`dap_an` để
    người sửa thay vì gõ từ đầu, và `nhap_chac_chan` nói cho người biết model có
    tự tin hay không. Người vẫn phải MỞ ẢNH ra nhìn — nháp sinh từ chữ OCR vỡ.
    """
    p = out_dir / "phieu_nguoi.json"
    if p.exists():
        return p
    nhap_path = out_dir / "nhap_llm.json"
    nhap = json.loads(nhap_path.read_text(encoding="utf-8")) if nhap_path.exists() else {}
    phieu = {
        "_huong_dan": (
            "MỞ FILE ẢNH ở trường 'anh' của items.json ra NHÌN, rồi sửa 'cau_hoi' "
            "và 'dap_an' cho khớp với thứ NHÌN THẤY. Hai trường này có thể đã "
            "được LLM điền sẵn NHÁP — nháp sinh từ chữ OCR quanh hình, model "
            "KHÔNG nhìn thấy hình, nên phải kiểm chứ đừng tin. Câu phải trả lời "
            "được NHỜ hình, không phải nhờ chữ trên trang. Hình nào không dùng "
            "được thì đặt bo=true kèm lý do. Đừng sửa khoá 'id'."),
        "_bat_dau": int(time.time() * 1000),
        "_ket_thuc": 0,
        "traloi": {
            it["id"]: {
                "cau_hoi": (nhap.get(it["id"]) or {}).get("cau_hoi", ""),
                "dap_an": (nhap.get(it["id"]) or {}).get("dap_an", ""),
                "nhap_chac_chan": (nhap.get(it["id"]) or {}).get("chac_chan"),
                "bo": False, "ly_do_bo": "",
            }
            for it in items
        },
    }
    p.write_text(json.dumps(phieu, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def ap_dung(out_dir: Path, testset_dir: Path) -> Dict:
    """Trộn câu ĐÃ DUYỆT vào bộ 240. Ô chưa điền / đã bỏ thì KHÔNG vào.

    Chạy lại nhiều lần cho cùng kết quả: mỗi lượt xoá câu `nguon_cau_hoi=hinh`
    cũ rồi ghi lại, nên không có chuyện chạy hai lần thành 96 câu.
    """
    items = {it["id"]: it for it in
             json.loads((out_dir / "items.json").read_text(encoding="utf-8"))}
    phieu = json.loads((out_dir / "phieu_nguoi.json").read_text(encoding="utf-8"))

    by_book: Dict[str, List[Dict]] = defaultdict(list)
    bo, trong = 0, 0
    for item_id, ans in phieu["traloi"].items():
        it = items.get(item_id)
        if it is None:
            continue
        if ans.get("bo"):
            bo += 1
            continue
        q = (ans.get("cau_hoi") or "").strip()
        a = (ans.get("dap_an") or "").strip()
        if not q or not a:
            trong += 1
            continue
        by_book[it["quyen"]].append({
            "question": q, "ground_truth": a,
            "source_book": it["quyen"], "source_page": it["trang"],
            "source_page_index": it["trang"],
            "do_kho": "truc_tiep",
            "nguon_cau_hoi": "hinh", "figure_label": it["nhan_hinh"],
        })

    them = 0
    for book, rows in sorted(by_book.items()):
        csv_path = testset_dir / f"{book}_testset.csv"
        if not csv_path.exists():
            raise SystemExit(f"Không thấy {csv_path} — chạy build_testset_240 trước")
        with csv_path.open(encoding="utf-8-sig", newline="") as f:
            existing = list(csv.DictReader(f))
        fieldnames = list(existing[0].keys())
        existing = [r for r in existing if r.get("nguon_cau_hoi") != "hinh"]
        with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(existing)
            w.writerows([{k: r.get(k, "") for k in fieldnames} for r in rows])
        them += len(rows)

    return {"them": them, "bo": bo, "chua_dien": trong,
            "quyen": {b: len(r) for b, r in sorted(by_book.items())}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chon", action="store_true",
                    help="máy chọn crop + chép ảnh (chạy trước)")
    ap.add_argument("--nhap", action="store_true",
                    help="LLM viết NHÁP câu hỏi (cần EVAL_LLM_* trong .env)")
    ap.add_argument("--phieu", action="store_true",
                    help="lập phiếu cho người, điền sẵn nháp nếu có")
    ap.add_argument("--ap-dung", action="store_true",
                    help="trộn câu đã duyệt vào bộ 240")
    ap.add_argument("--per-book", type=int, default=PER_BOOK)
    ap.add_argument("--limit", type=int, default=0,
                    help="--nhap: chỉ viết nháp cho N ô đầu (thử đường chạy)")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    a = ap.parse_args()
    out_dir = Path(a.out_dir)

    if a.chon:
        items = chon(a.per_book, out_dir)
        per: Dict[str, int] = defaultdict(int)
        for it in items:
            per[it["quyen"]] += 1
        print(f"Chọn {len(items)} hình / {len(per)} quyển -> {out_dir}/items.json")
        for b, n in sorted(per.items()):
            mark = "" if n == a.per_book else f"   <-- THIẾU (cần {a.per_book})"
            print(f"  {b:18s} {n}{mark}")
        thieu = [b for b, n in per.items() if n < a.per_book]
        if thieu or len(per) < 12:
            print(f"CHƯA ĐỦ 12 quyển × {a.per_book} — ETL hình 12 quyển xong thì chạy lại.")
            return 1
        print("Bước tiếp: --nhap (LLM viết nháp) rồi --phieu (lập phiếu cho người).")
        return 0

    if a.nhap:
        items = json.loads((out_dir / "items.json").read_text(encoding="utf-8"))
        if a.limit:
            items = items[:a.limit]
        r = nhap_bang_llm(items, out_dir)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        print("Nháp KHÔNG tự vào bộ test — phải qua --phieu rồi người duyệt.")
        return 0

    if a.phieu:
        items = json.loads((out_dir / "items.json").read_text(encoding="utf-8"))
        p = lam_phieu(items, out_dir)
        print(f"Phiếu người: {p}")
        return 0

    if a.ap_dung:
        r = ap_dung(out_dir, TESTSET_DIR)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0 if r["them"] else 1

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
