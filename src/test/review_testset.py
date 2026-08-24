# -*- coding: utf-8 -*-
"""Phiếu để NGƯỜI duyệt tay bộ test, và bộ chấm đọc lại phiếu đó.

## Vì sao cần

Bộ test do LLM sinh, `_generation_meta.json` ghi `human_reviewed: false`. Nên mọi
bảng số dùng nó đều phải kèm câu "chưa có người duyệt" — một câu **định tính**,
đúng chỗ hội đồng sẽ hỏi. Duyệt một mẫu ~50 câu biến câu đó thành **một tỉ lệ
sai đo được**, kèm khoảng tin cậy. Đây là quyết định #6 của người dùng (D-74).

## Mẫu được chọn thế nào (và vì sao không lấy 50 câu đầu)

Phân tầng theo (quyển × độ khó) với hạt giống cố định: 50 câu đầu của file là 50
câu của **hai quyển đầu**, nên tỉ lệ sai đo trên đó không nói gì về 10 quyển kia.
Phân tầng + hạt giống làm mẫu vừa đại diện vừa **lặp lại được**.

## Người duyệt điền vào đâu

Đúng **một cột**: `ket_luan`, nhận `dung` / `sai` / `khong_chac`. Phiếu đã kèm
sẵn **văn bản đã index của trang vàng**, nên không phải mở file PNG ra tra.

    python -m src.test.review_testset --export      # tạo phiếu
    python -m src.test.review_testset --score       # chấm sau khi điền xong
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_OUT = Path("document/review/testset_review_50.csv")
SEED = 42
HOP_LE = ("dung", "sai", "khong_chac")

# Cột người duyệt điền đứng ĐẦU: mở bằng Excel là thấy ngay, không phải kéo
# ngang qua một ô văn bản dài 2 000 ký tự mới tới chỗ cần gõ.
COLS = [
    "stt", "ket_luan", "ghi_chu",
    "cau_hoi", "dap_an_LLM_sinh",
    "quyen", "trang", "phan_mon", "do_kho",
    "van_ban_da_index_cua_trang_vang",
]


def load_rows(directory: Path) -> List[dict]:
    import glob

    rows: List[dict] = []
    for path in sorted(glob.glob(str(directory / "*_testset.csv"))):
        with io.open(path, encoding="utf-8-sig", newline="") as fh:
            rows.extend(csv.DictReader(fh))
    return rows


def stratified_sample(rows: List[dict], n: int, seed: int = SEED) -> List[dict]:
    """Rải đều theo (quyển × độ khó), thiếu chỗ nào thì bù ngẫu nhiên."""
    rng = random.Random(seed)
    groups: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for r in rows:
        groups[(r.get("source_book", "?"), r.get("do_kho", "?"))].append(r)
    for g in groups.values():
        rng.shuffle(g)

    keys = sorted(groups)
    picked: List[dict] = []
    i = 0
    while len(picked) < n and any(groups[k] for k in keys):
        k = keys[i % len(keys)]
        if groups[k]:
            picked.append(groups[k].pop())
        i += 1
    return picked[:n]


def page_text_lookup():
    """Văn bản đã index của từng trang. Đọc thẳng Chroma, KHÔNG nạp model nào."""
    import chromadb

    from src.config import PERSIST_DIR, TEXT_COLLECTION_NAME

    col = chromadb.PersistentClient(path=str(PERSIST_DIR)).get_collection(
        TEXT_COLLECTION_NAME)
    got = col.get(include=["documents", "metadatas"], limit=1_000_000)
    pages: Dict[Tuple[str, int], List[str]] = defaultdict(list)
    for doc, meta in zip(got["documents"], got["metadatas"]):
        pages[(str(meta["source"]), int(meta["page"]))].append(doc or "")
    return {k: "\n".join(v) for k, v in pages.items()}


def do_export(testset_dir: Path, out: Path, n: int) -> int:
    rows = load_rows(testset_dir)
    if not rows:
        print(f"Không có *_testset.csv trong {testset_dir}")
        return 2
    if out.exists():
        # KHÔNG ghi đè: file này có thể đã có công của người duyệt trong đó.
        print(f"{out} ĐÃ TỒN TẠI — không ghi đè (có thể đang có công người "
              f"duyệt). Đổi tên nó rồi chạy lại nếu muốn phiếu mới.")
        return 1

    pages = page_text_lookup()
    mau = stratified_sample(rows, n)
    out.parent.mkdir(parents=True, exist_ok=True)
    with io.open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        for i, r in enumerate(mau, 1):
            key = (r["source_book"], int(r["source_page"]))
            w.writerow({
                "stt": i,
                "ket_luan": "",
                "ghi_chu": "",
                "cau_hoi": r["question"],
                "dap_an_LLM_sinh": r["ground_truth"],
                "quyen": r["source_book"],
                "trang": r["source_page"],
                "phan_mon": r.get("phan_mon", ""),
                "do_kho": r.get("do_kho", ""),
                "van_ban_da_index_cua_trang_vang": pages.get(key, "(TRANG NÀY "
                                                             "KHÔNG CÓ CHUNK)"),
            })
    thieu = sum(1 for r in mau
                if (r["source_book"], int(r["source_page"])) not in pages)
    print(f"Đã tạo phiếu: {out}")
    print(f"  {len(mau)} câu, rải đều theo (quyển × độ khó), hạt giống {SEED}")
    print(f"  {len(set((r['source_book'], r['source_page']) for r in mau))} trang vàng riêng biệt")
    if thieu:
        print(f"  CẢNH BÁO: {thieu} câu trỏ vào trang KHÔNG có chunk")
    print()
    print("NGƯỜI DUYỆT ĐIỀN VÀO ĐÚNG MỘT CỘT: `ket_luan`")
    print("  dung       = đáp án đúng VÀ nằm ở đúng trang vàng ghi trong phiếu")
    print("  sai        = đáp án sai, hoặc nó không nằm ở trang đó")
    print("  khong_chac = không quyết được (sẽ tính riêng, không gộp vào tỉ lệ)")
    print("Cột `ghi_chu` tuỳ ý. ĐỪNG sửa các cột khác — bộ chấm đối chiếu theo `stt`.")
    return 0


def wilson(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Khoảng tin cậy 95% cho tỉ lệ. Với n = 50 thì khoảng này RỘNG, và nói ra
    khoảng đó thành thật hơn là chỉ đưa một con số điểm."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return ((c - r) / d, (c + r) / d)


def do_score(path: Path) -> int:
    if not path.exists():
        print(f"Chưa có phiếu ở {path}. Tạo bằng: --export")
        return 2
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    dem = Counter((r.get("ket_luan") or "").strip().lower() for r in rows)
    la = {k: v for k, v in dem.items() if k and k not in HOP_LE}
    if la:
        print(f"Giá trị không hợp lệ trong cột `ket_luan`: {la}")
        print(f"Chỉ nhận: {', '.join(HOP_LE)}")
        return 1

    chua = dem.get("", 0)
    if chua:
        print(f"CHƯA CHẤM: {chua}/{len(rows)} dòng còn trống cột `ket_luan`.")
        print("Không tính tỉ lệ trên phần đã điền — một tỉ lệ trên mẫu dở dang là "
              "một con số sai mà trông hợp lý.")
        return 1

    dung, sai, khong_chac = dem.get("dung", 0), dem.get("sai", 0), dem.get("khong_chac", 0)
    quyet = dung + sai
    lo, hi = wilson(sai, quyet)
    print(f"Phiếu: {path}  ·  {len(rows)} câu")
    print(f"  đúng       {dung:3d}")
    print(f"  SAI        {sai:3d}")
    print(f"  không chắc {khong_chac:3d}  (để NGOÀI tỉ lệ, không gộp vào đâu cả)")
    print()
    if quyet:
        print(f"  Tỉ lệ gold key SAI = {sai}/{quyet} = **{sai / quyet:.1%}**")
        print(f"  Khoảng tin cậy 95% (Wilson): {lo:.1%} – {hi:.1%}")
    print()
    print("Câu để dán vào báo cáo, cạnh MỌI bảng số:")
    print(f'  "Bộ test do LLM sinh. Một mẫu {len(rows)} câu rải đều theo quyển và')
    print(f'   độ khó đã được người duyệt tay: tỉ lệ gold key sai {sai}/{quyet}')
    print(f'   = {sai / quyet:.1%} (KTC 95%: {lo:.1%}–{hi:.1%}), {khong_chac} câu không')
    print('   quyết được."')
    sai_theo_quyen = Counter(r["quyen"] for r in rows
                             if (r.get("ket_luan") or "").strip().lower() == "sai")
    if sai_theo_quyen:
        print("\nCâu sai tập trung ở đâu (đọc để biết có nên duyệt thêm quyển nào):")
        for k, v in sai_theo_quyen.most_common():
            print(f"  {k:22s} {v}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--testset-dir", default="src/test/testsets")
    ap.add_argument("--file", default=str(DEFAULT_OUT))
    ap.add_argument("-n", type=int, default=50)
    args = ap.parse_args()
    if args.export:
        return do_export(Path(args.testset_dir), Path(args.file), args.n)
    if args.score:
        return do_score(Path(args.file))
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
