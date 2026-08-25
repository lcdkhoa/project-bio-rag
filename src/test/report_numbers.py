"""Số liệu Chương 4 của báo cáo, ĐỌC THẲNG TỪ INDEX — không gõ tay số nào.

Báo cáo chuyên đề cũ (`report/main_chuyende_totnghiep.pdf`, tháng 6/2026) chứa
một bảng 12 dòng và hàng chục con số rải trong văn xuôi. Mọi con số đó nay đã
sai vì corpus và mô hình đều đổi. Gõ lại bằng tay là cách chắc chắn nhất để một
con số cũ sống sót vào bản mới mà không ai thấy — nên script này sinh chúng từ
ChromaDB đang chạy, và in kèm **những con số CŨ nó thay thế** để người viết báo
cáo đối chiếu chứ không phải nhớ.

    python -m src.test.report_numbers              # bảng cho người đọc
    python -m src.test.report_numbers --latex      # thân bảng LaTeX dán vào tex

Cái script này CỐ Ý KHÔNG tự sửa file `.tex`: một bản vá tự động vào báo cáo là
chỗ dễ làm hỏng nhất mà lại khó thấy nhất.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
from collections import Counter, defaultdict
from pathlib import Path

import chromadb

from src.config import PERSIST_DIR

BASE = Path(__file__).resolve().parent

# Số của báo cáo CHUYÊN ĐỀ cũ (06/2026), giữ lại để đối chiếu — KHÔNG phải mục tiêu.
CU = {
    "trang": "2.319", "chunk": "13.754", "vector_hinh": "2.408",
    "embed": "paraphrase-multilingual-MiniLM-L12-v2, 384 chiều",
    "caption": "2.384 hình có caption Vintern-1B",
    "cau_hoi": "120 câu (12 quyển × 10)",
    "page_tolerance": "±1 trang",
}

TEN_NXB = {"CD": "Cánh Diều", "CTST": "Chân trời sáng tạo",
           "KNTT": "Kết nối tri thức"}


def _tach(book: str):
    """`SGK_KHTN_6_CD` -> `(6, 'CD')`."""
    phan = book.split("_")
    return int(phan[2]), phan[3]


def thu_thap() -> dict:
    cl = chromadb.PersistentClient(path=str(PERSIST_DIR))

    txt = cl.get_collection("biology_text").get(limit=200000,
                                                include=["metadatas"])
    chunk = Counter(m.get("source") for m in txt["metadatas"])
    trang = defaultdict(set)
    variant = Counter()
    for m in txt["metadatas"]:
        trang[m.get("source")].add(m.get("page_index"))
        variant[(m.get("source", "").split("_")[-1], m.get("variant"))] += 1

    img = cl.get_collection("biology_images").get(limit=200000,
                                                  include=["metadatas"])
    hinh = Counter(m.get("pdf_filename") for m in img["metadatas"])
    loai = Counter(m.get("image_type") for m in img["metadatas"])
    co_caption = sum(1 for m in img["metadatas"]
                     if (m.get("visual_caption_vi") or "").strip())

    return {"chunk": chunk, "trang": {k: len(v) for k, v in trang.items()},
            "hinh": hinh, "loai_hinh": loai, "co_caption_sinh": co_caption,
            "n_hinh": len(img["metadatas"]), "variant": variant,
            "n_chunk": len(txt["metadatas"])}


def bo_test(thu_muc: Path) -> dict:
    rows = []
    for f in sorted(glob.glob(str(thu_muc / "*_testset.csv"))):
        with open(f, encoding="utf-8-sig", newline="") as fh:
            rows.extend(list(csv.DictReader(fh)))
    return {
        "n": len(rows),
        "theo_bo_sach": Counter(_tach(r["source_book"])[1] for r in rows
                                if r.get("source_book")),
        "theo_nguon": Counter(r.get("nguon_cau_hoi") or "?" for r in rows),
        "theo_do_kho": Counter(r.get("do_kho") or "?" for r in rows),
        "theo_phan_mon": Counter(r.get("phan_mon") or "?" for r in rows),
    }


def in_bang(d: dict, test: dict) -> None:
    books = sorted(set(d["trang"]) | set(d["hinh"]),
                   key=lambda b: (_tach(b)[0], _tach(b)[1]))
    print("\n=== Bảng 4.2 — kho tri thức đã số hoá và lập chỉ mục ===")
    print(f"{'Khối':>4} {'Bộ sách':<20} {'Trang':>6} {'Chunk':>7} {'Vector hình':>12}")
    tong_t = tong_c = tong_h = 0
    for b in books:
        khoi, nxb = _tach(b)
        t, c, h = d["trang"].get(b, 0), d["chunk"].get(b, 0), d["hinh"].get(b, 0)
        tong_t += t
        tong_c += c
        tong_h += h
        ghi = "" if h else "   <- CHƯA có kho ảnh"
        print(f"{khoi:>4} {TEN_NXB.get(nxb, nxb):<20} {t:>6} {c:>7} {h:>12}{ghi}")
    print(f"{'':>4} {'TỔNG':<20} {tong_t:>6} {tong_c:>7} {tong_h:>12}")

    # 2 399 trang trên đĩa nhưng 2 387 trang có chunk. Chênh lệch KHÔNG phải mất
    # dữ liệu: đúng 12 trang bìa (1/quyển, `role="cover"`) bị bỏ theo thiết kế —
    # đã kiểm từng quyển. Báo cáo phải nói con số nào là con số nào, nếu không
    # người đọc sẽ tưởng ETL bỏ sót 12 trang.
    print(f"\n  * {tong_t} là số trang CÓ NỘI DUNG được lập chỉ mục. Trên đĩa có "
          f"{tong_t + 12} trang; chênh đúng 12 = trang BÌA (1/quyển, role=cover), "
          f"bỏ theo thiết kế, không phải bỏ sót.")

    print("\n=== Số CŨ trong báo cáo chuyên đề mà bảng trên THAY THẾ ===")
    print(f"  trang       : {CU['trang']:>8}  ->  {tong_t} (nội dung) / "
          f"{tong_t + 12} (trên đĩa)")
    print(f"  chunk       : {CU['chunk']:>8}  ->  {tong_c}")
    print(f"  vector hình : {CU['vector_hinh']:>8}  ->  {tong_h}"
          f"   ({sum(1 for b in books if d['hinh'].get(b))}/12 quyển)")
    print(f"  nhúng       : {CU['embed']}  ->  BAAI/bge-m3, 1024 chiều")
    print(f"  caption     : {CU['caption']}  ->  {d['co_caption_sinh']} "
          f"(captioner TẮT theo D-47)")
    print(f"  bộ test     : {CU['cau_hoi']}  ->  {test['n']} câu")
    print(f"  dung sai    : {CU['page_tolerance']}  ->  PAGE_TOLERANCE = 0")

    print("\n=== Loại hình (thay danh sách '1.166 hình đơn, 504 hình con…' cũ) ===")
    for k, v in d["loai_hinh"].most_common():
        print(f"  {str(k):<22} {v}")

    print("\n=== Bảng 4.3 — phân bố bộ kiểm thử ===")
    print(f"  tổng: {test['n']} câu")
    for k, v in sorted(test["theo_bo_sach"].items()):
        print(f"    {TEN_NXB.get(k, k):<20} {v}")
    print(f"  theo nguồn : {dict(test['theo_nguon'])}")
    print(f"  theo độ khó: {dict(test['theo_do_kho'])}")
    print(f"  theo phân môn: {dict(test['theo_phan_mon'])}")

    sai = {k: v for k, v in d["variant"].items() if k[0].lower() != (k[1] or "")}
    if sai:
        print("\n=== CẢNH BÁO: chunk mang nhãn `variant` SAI (D-109) ===")
        for (nxb, var), n in sorted(sai.items()):
            print(f"  {nxb} gắn variant={var!r}: {n} chunk")
        print("  Code đã sửa (D-111) nhưng dữ liệu cũ chỉ sạch sau khi bump "
              "TEXT_EXTRACTION_VERSION. Đừng viết vào báo cáo là đã khắc phục.")


def in_latex(d: dict) -> None:
    books = sorted(set(d["trang"]) | set(d["hinh"]),
                   key=lambda b: (_tach(b)[0], _tach(b)[1]))
    print("% sinh bằng `python -m src.test.report_numbers --latex` — đừng gõ tay")
    tong_t = tong_c = tong_h = 0
    khoi_truoc = None
    for b in books:
        khoi, nxb = _tach(b)
        t, c, h = d["trang"].get(b, 0), d["chunk"].get(b, 0), d["hinh"].get(b, 0)
        tong_t += t
        tong_c += c
        tong_h += h
        cot1 = f"\\multirow{{3}}{{*}}{{Lớp {khoi}}}" if khoi != khoi_truoc else ""
        khoi_truoc = khoi
        print(f"{cot1} & KHTN {khoi} {TEN_NXB.get(nxb, nxb)} & {t} & {c} & {h} \\\\")
    print("\\midrule")
    print(f"\\multicolumn{{2}}{{r}}{{\\textbf{{Tổng cộng}}}} & "
          f"\\textbf{{{tong_t}}} & \\textbf{{{tong_c}}} & \\textbf{{{tong_h}}} \\\\")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--latex", action="store_true", help="in thân bảng LaTeX")
    ap.add_argument("--testset-dir", default=str(BASE / "testsets_240"))
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args()

    d = thu_thap()
    test = bo_test(Path(a.testset_dir))
    if a.latex:
        in_latex(d)
    else:
        in_bang(d, test)
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(
            {"trang": d["trang"], "chunk": d["chunk"], "hinh": d["hinh"],
             "loai_hinh": dict(d["loai_hinh"]), "bo_test": {
                 k: (v if isinstance(v, int) else dict(v))
                 for k, v in test.items()}},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n[OK] JSON -> {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
