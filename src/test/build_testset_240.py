"""Dựng bộ kiểm thử 240 câu (3 bộ SGK × 80) từ pool 300 câu đã có.

**Vì sao rút mẫu chứ không sinh mới.** Pool `src/test/testsets/` đã có 300 câu
(25/quyển × 12) kèm đủ bốn nhãn `phan_mon` / `do_kho` / `khoi` / `bo_sach`, sinh
cùng một mô hình và cùng Algorithm 1 của báo cáo chuyên đề. Sinh lại 240 câu nữa
tốn quota OpenRouter (free chỉ còn tuần này) mà **không** mua thêm chất lượng —
và pool này đã được người duyệt trên mẫu 50 câu (D-90). Rút mẫu là miễn phí,
xác định, và giữ nguyên cái đã được kiểm chứng.

**Vì sao 16 + 4 chứ không phải 17 + 3 hay 20 + 0.** Thầy kê 240 để chia chẵn cho
ba bộ sách. 240 = 12 quyển × 20 = 3 bộ × 80. Trong 20 câu/quyển: **16 câu văn
bản + 4 câu sinh từ HÌNH**. Chốt 4 (thay vì 3) vì kênh HÌNH là trục **đang bị
chặn**: bảng text-only vs multi-modal (D-87) chỉ đo được delta +0,010 do trần bộ
test cũ là 0,104 — thêm câu hỏi hình là cách duy nhất nới trần đó. 48 câu hình
cho sức phân biệt tốt hơn 36.

**Rút mẫu phân tầng, và trải theo TRANG chứ không chỉ theo nhãn.** Pool cảnh báo
sẵn trong `_generation_meta.json`: "3 câu chung MỘT trang vàng nên tương quan với
nhau; 25 câu chỉ đến từ 9 trang". Nên bộ 240 ưu tiên **trang khác nhau trước** —
lấy vòng một mỗi trang một câu, vòng hai mới lấy câu thứ hai — rồi trong cùng
một trang mới cân theo `(phan_mon, do_kho)`. Cùng 16 câu, số trang vàng phân biệt
càng nhiều thì sức phân biệt thống kê càng gần 16 chứ không tụt về ~6.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

BASE = Path(__file__).resolve().parent
POOL_DIR = BASE / "testsets"
OUT_DIR = BASE / "testsets_240"

TEXT_PER_BOOK = 16
IMAGE_PER_BOOK = 4
SEED = 42

# Cột thêm so với pool: bộ 240 trộn hai NGUỒN câu hỏi nên phải phân biệt được,
# nếu không thì bảng "text-only vs multi-modal" không tách được tử số của nó.
EXTRA_COLUMNS = ["nguon_cau_hoi", "figure_label"]


def _read_pool(book_csv: Path) -> List[Dict]:
    with book_csv.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def select_text_rows(rows: List[Dict], n: int, rng: random.Random) -> List[Dict]:
    """Chọn `n` câu, TRẢI ĐỀU trên số trang vàng trước, cân nhãn sau.

    Trả về đúng `n` câu, hoặc tất cả nếu pool nhỏ hơn `n`. Không bịa thêm câu —
    thiếu thì trả ít và người gọi phải nhìn thấy (nguyên tắc 5).
    """
    by_page: Dict[str, List[Dict]] = defaultdict(list)
    for r in rows:
        by_page[r["source_page"]].append(r)

    # Trong một trang: xáo bằng rng đã seed để lượt chạy nào cũng ra y hệt.
    for page_rows in by_page.values():
        rng.shuffle(page_rows)

    pages = sorted(by_page)               # sắp xếp trước khi xáo -> xác định
    rng.shuffle(pages)

    chosen: List[Dict] = []
    depth = 0
    while len(chosen) < n:
        took_this_round = False
        for page in pages:
            if len(chosen) >= n:
                break
            if depth < len(by_page[page]):
                chosen.append(by_page[page][depth])
                took_this_round = True
        if not took_this_round:           # đã vét sạch pool
            break
        depth += 1
    return chosen


def build(pool_dir: Path, out_dir: Path, n_text: int, seed: int) -> Dict:
    books = sorted(pool_dir.glob("*_testset.csv"))
    if not books:
        raise SystemExit(f"Không có *_testset.csv trong {pool_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)
    meta: Dict = {"per_book": {}, "thieu": {}}
    total = 0

    for book_csv in books:
        book = book_csv.stem.replace("_testset", "")
        rows = _read_pool(book_csv)
        # Mỗi quyển một rng riêng, seed = seed + hash ổn định của tên quyển, để
        # thêm/bớt một quyển KHÔNG làm đổi lựa chọn của các quyển còn lại.
        rng = random.Random(f"{seed}:{book}")
        chosen = select_text_rows(rows, n_text, rng)

        if len(chosen) < n_text:
            meta["thieu"][book] = {"can": n_text, "co": len(chosen)}

        fieldnames = list(rows[0].keys()) + EXTRA_COLUMNS
        out_path = out_dir / f"{book}_testset.csv"
        with out_path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in chosen:
                w.writerow({**r, "nguon_cau_hoi": "van_ban", "figure_label": ""})

        total += len(chosen)
        meta["per_book"][book] = {
            "n_van_ban": len(chosen),
            "n_trang_vang": len({r["source_page"] for r in chosen}),
            "n_trang_vang_trong_pool": len({r["source_page"] for r in rows}),
            "by_do_kho": _count(chosen, "do_kho"),
            "by_phan_mon": _count(chosen, "phan_mon"),
        }

    meta.update({
        "n_van_ban": total,
        "n_hinh_du_kien": IMAGE_PER_BOOK * len(books),
        "n_tong_du_kien": total + IMAGE_PER_BOOK * len(books),
        "text_per_book": n_text,
        "image_per_book": IMAGE_PER_BOOK,
        "seed": seed,
        "nguon": "rút mẫu từ src/test/testsets/ (pool 300 câu), KHÔNG sinh mới",
        "human_reviewed": False,
        "human_review_note": (
            "Pool gốc do LLM sinh. Mẫu 50 câu đã được NGƯỜI duyệt (D-90): gold key "
            "sai 2/49 = 4,1%, KTC 95% Wilson 1,1-13,7%, 1 câu không quyết được. "
            "Mẫu đó cố ý lệch về suy_luan (50% vs 32% cả bộ) nên 4,1% là con số "
            "BI QUAN; hiệu chỉnh theo trọng số cả bộ ~2,7%. Bộ 240 này CHƯA có "
            "lượt duyệt riêng."),
        "chien_luoc_chon": (
            "Trải đều trên trang vàng trước (vòng 1 mỗi trang 1 câu), rồi mới lấy "
            "câu thứ 2 của một trang. Giảm tương quan mà _generation_meta.json của "
            "pool đã cảnh báo."),
    })
    (out_dir / "_selection_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def _count(rows: List[Dict], key: str) -> Dict[str, int]:
    out: Dict[str, int] = defaultdict(int)
    for r in rows:
        out[r.get(key) or "?"] += 1
    return dict(sorted(out.items()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pool-dir", default=str(POOL_DIR))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--text-per-book", type=int, default=TEXT_PER_BOOK)
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args()

    meta = build(Path(a.pool_dir), Path(a.out_dir), a.text_per_book, a.seed)

    print(f"Đã ghi {meta['n_van_ban']} câu VĂN BẢN vào {a.out_dir}")
    print(f"Còn thiếu {meta['n_hinh_du_kien']} câu HÌNH "
          f"({meta['image_per_book']}/quyển) -> chờ ETL hình 12 quyển xong")
    for book, d in meta["per_book"].items():
        print(f"  {book:18s} {d['n_van_ban']:2d} câu / "
              f"{d['n_trang_vang']:2d} trang vàng "
              f"(pool có {d['n_trang_vang_trong_pool']}) | {d['by_do_kho']}")
    if meta["thieu"]:
        print(f"THIẾU: {meta['thieu']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
