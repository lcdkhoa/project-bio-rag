# -*- coding: utf-8 -*-
"""Buộc chạy lại luồng ẢNH cho MỘT SỐ quyển, không đụng tới các quyển khác.

## Vì sao cần công cụ này thay vì bump `IMAGE_EXTRACTION_VERSION`

Bump version là cách chuẩn để ép chạy lại — nhưng nó ép chạy lại **cả 12 quyển**.
Khi một bản vá chỉ ảnh hưởng một nhà xuất bản (D-121: chú thích hình của CTST mở
đầu bằng ▲ nên regex loại mất 49%), bump version sẽ đốt thêm nhiều giờ CPU để
dựng lại y nguyên những quyển vốn đã đúng.

## Nó làm đúng hai việc, theo đúng thứ tự

1. **Xoá doc ảnh** của các quyển đó trên cả hai collection, qua
   `ImageVectorDB.delete_page_documents`. Bỏ bước này thì doc cũ **sống sót thành
   mồ côi**: `image_id` là hash của chính khung cắt, nên khung cắt đổi là id đổi,
   doc cũ không bị ghi đè mà nằm lại (D-52).
2. **Hạ cờ `image_extracted`** trong `processing_status` cho đúng các trang đó,
   để lần chạy sau coi chúng là chưa xử lý.

Thứ tự này quan trọng: xoá doc trước, hạ cờ sau. Nếu hạ cờ trước rồi xoá doc thất
bại giữa chừng, ta còn một lượt chạy lại sạch; ngược lại thì có doc mồ côi mà
checkpoint lại nói "đã xong".

## Cách dùng

    python scripts/reset_image_books.py --book SGK_KHTN_6_CTST SGK_KHTN_7_CTST
    python scripts/reset_image_books.py --nxb CTST          # cả 4 quyển của một NXB
    python scripts/reset_image_books.py --nxb CTST --thu    # chỉ in, không xoá

Rồi chạy `python main.py --image-only` như bình thường.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import chromadb  # noqa: E402

from src.config import PERSIST_DIR  # noqa: E402


def _quyen_tren_dia() -> list[str]:
    from src.config import DATA_DIR
    from src.etl.page_source import discover_page_sources
    return sorted(s.name for s in discover_page_sources(DATA_DIR))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--book", nargs="*", default=[], help="tên quyển, cách nhau bởi dấu cách")
    ap.add_argument("--nxb", default="", help="hậu tố NXB: KNTT / CTST / CD")
    ap.add_argument("--thu", action="store_true", help="chỉ in, KHÔNG xoá gì")
    a = ap.parse_args()

    tren_dia = _quyen_tren_dia()
    chon = list(a.book)
    if a.nxb:
        chon += [b for b in tren_dia if b.upper().endswith("_" + a.nxb.upper())]
    chon = sorted(set(chon))

    if not chon:
        print("Chưa chọn quyển nào. Dùng --book hoặc --nxb.")
        print(f"Có trên đĩa: {', '.join(tren_dia)}")
        return 2

    la = [b for b in chon if b not in tren_dia]
    if la:
        # Thoát khác 0 thay vì bỏ qua: một lỗi chính tả trong tên quyển mà im lặng
        # sẽ khiến người dùng tưởng đã reset, rồi chạy lại và không thấy gì đổi.
        print(f"[LỖI] không có trên đĩa: {la}")
        print(f"Có: {', '.join(tren_dia)}")
        return 2

    client = chromadb.PersistentClient(path=str(PERSIST_DIR))
    st = client.get_collection("processing_status")
    # Trạng thái nằm trong `documents` (một chuỗi JSON), KHÔNG nằm trong
    # `metadatas` — metadata chỉ giữ `page_key` và `page` để tra cứu. Đọc nhầm
    # chỗ thì script này reset đúng 0 trang mà vẫn in ra "thành công": một lỗi
    # im lặng đắt hơn hẳn một lỗi ồn ào (nguyên tắc 5).
    got = st.get(limit=1_000_000, include=["documents"])

    theo_quyen: dict[str, list[tuple[str, dict]]] = {}
    for doc_id, raw in zip(got["ids"], got["documents"]):
        try:
            d = json.loads(raw or "{}")
        except Exception:
            continue
        if d.get("pdf_filename") in chon and d.get("image_extracted"):
            theo_quyen.setdefault(d["pdf_filename"], []).append((doc_id, d))

    img_col = client.get_collection("biology_images")
    n_img = Counter(m.get("pdf_filename")
                    for m in img_col.get(limit=1_000_000,
                                         include=["metadatas"])["metadatas"])

    print(f"{'quyển':22s} {'doc ảnh':>8} {'trang đã xong':>14}")
    for b in chon:
        print(f"{b:22s} {n_img.get(b, 0):8d} {len(theo_quyen.get(b, [])):14d}")
    tong_img = sum(n_img.get(b, 0) for b in chon)
    tong_tr = sum(len(v) for v in theo_quyen.values())
    print(f"{'TỔNG':22s} {tong_img:8d} {tong_tr:14d}")

    if a.thu:
        print("\n--thu: không xoá gì.")
        return 0

    # 1) Xoá doc ảnh TRƯỚC (xem docstring về thứ tự)
    from src.rag.image_vectorstore import ImageVectorDB
    vdb = ImageVectorDB()
    da_xoa = 0
    for b in chon:
        pages = sorted({int(m["page_number"]) for m in
                        img_col.get(where={"pdf_filename": {"$eq": b}},
                                    limit=1_000_000,
                                    include=["metadatas"])["metadatas"]
                        if m.get("page_number") is not None})
        if pages:
            da_xoa += vdb.delete_page_documents(b, pages)
    print(f"\nĐã xoá {da_xoa} doc ảnh.")

    # 2) Hạ cờ checkpoint SAU — ghi lại chính chuỗi JSON trong `documents`,
    #    giữ nguyên mọi trường khác (đặc biệt `text_indexed`: chỉ luồng ẢNH bị
    #    reset, chữ đã lập chỉ mục KHÔNG được đụng tới).
    cap = [(i, d) for v in theo_quyen.values() for i, d in v]
    for i in range(0, len(cap), 500):
        lo = cap[i:i + 500]
        st.update(
            ids=[i for i, _ in lo],
            documents=[json.dumps({**d, "image_extracted": False,
                                   "image_extraction_version": ""})
                       for _, d in lo],
        )
    print(f"Đã hạ cờ image_extracted cho {len(cap)} trang "
          f"(text_indexed giữ nguyên).")
    print("\nChạy lại: python main.py --image-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
