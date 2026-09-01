# -*- coding: utf-8 -*-
"""Buộc chạy lại luồng TEXT cho một số quyển (hoặc tất cả), không đụng ẢNH.

## Vì sao cần công cụ này thay vì chỉ bump `TEXT_EXTRACTION_VERSION`

Bump version một mình có một lỗ hổng đã cắn thật (D-157): nếu `database/` được
KHÔI PHỤC từ một checkpoint Drive cũ đã lỡ ghi `text_extraction_version` bằng
đúng giá trị MỚI (ví dụ do một lượt chạy trước dùng code có bug nhưng cùng
version), version-gate sẽ coi những trang đó là "đã xong" và KHÔNG OCR lại —
dù nội dung là sản phẩm của code cũ. Script này hạ cờ TRỰC TIẾP, không dựa vào
so sánh version, nên không thể bị qua mặt kiểu đó.

## Nó làm đúng MỘT việc

**Hạ cờ `text_indexed`/`text_extraction_version`** trong `processing_status` cho
đúng các trang được chọn, để lần chạy `--text-only` sau coi chúng là chưa xử lý.
KHÔNG cần xoá chunk `biology_text` thủ công ở đây: `_index_one_page()` trong
`main.py` đã tự xoá chunk cũ của ĐÚNG trang đó (`_delete_page_chunks`) ngay
trước khi ghi chunk mới, cho mọi trang nó xử lý — không phân biệt trang đó
"chưa từng chạy" hay "đã chạy nhưng bị hạ cờ ở đây". Nguyên tắc thứ tự giống
`reset_image_books.py` (D-122): hạ cờ xong mới an toàn, không cần bước xoá
riêng — nếu ETL sau đó chết giữa chừng ở một trang, trang đó vẫn `text_indexed=
False`, lần chạy kế tiếp sẽ làm lại, không có gì mồ côi.

`image_extracted`/`image_extraction_version` KHÔNG bị đụng — ảnh đã xong
12/12 quyển (D-121/D-124/D-131), dựng lại tốn 5-6 giờ, không có lý do để mất.

## Mặc định CHỈ hạ cờ trang chưa đạt đúng `TEXT_EXTRACTION_VERSION` hiện tại

Đọc kỹ trước khi dùng `--ignore-version`: mặc định script chỉ chọn trang có
`text_indexed=True` **và** `text_extraction_version != TEXT_EXTRACTION_VERSION`
(giá trị hiện tại của `src/config.py`, hoặc override qua `--version`). Đây KHÔNG
phải lặp lại lỗi D-157 (tin version một mình) — nó an toàn CHÍNH XÁC vì
`TEXT_EXTRACTION_VERSION` vừa được bump sang một chuỗi CHƯA từng có trang nào
đạt được trước khi có bản vá này, nên mọi trang cũ (bất kể version cũ đúng hay
sai) đều bị chọn. Lợi ích: script này RESUME-SAFE — nếu một phiên ETL dài bị
ngắt giữa chừng và người dùng chạy lại notebook từ đầu, những trang ĐÃ ĐƯỢC OCR
LẠI ĐÚNG bằng code mới (đã lên version mới) sẽ KHÔNG bị hạ cờ lần nữa, tránh lãng
phí công đã làm. Muốn hạ cờ TUYỆT ĐỐI mọi trang bất kể version (bản vá kế tiếp
KHÔNG kèm bump version, hoặc nghi ngờ chính so sánh version) thì thêm
`--ignore-version`.

## Cách dùng

    python scripts/reset_text_all_books.py --all
    python scripts/reset_text_all_books.py --book SGK_KHTN_6_CTST SGK_KHTN_7_CTST
    python scripts/reset_text_all_books.py --nxb CTST          # cả 4 quyển của một NXB
    python scripts/reset_text_all_books.py --all --thu         # chỉ in, không hạ cờ
    python scripts/reset_text_all_books.py --all --ignore-version  # bỏ qua so sánh version

Rồi chạy `python main.py --text-only` (hoặc lặp `--book` từng quyển) như bình
thường — mọi trang đã hạ cờ sẽ được OCR lại bằng code/model hiện tại.
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

from src.config import PERSIST_DIR, TEXT_EXTRACTION_VERSION  # noqa: E402


def _quyen_tren_dia() -> list[str]:
    from src.config import DATA_DIR
    from src.etl.page_source import discover_page_sources
    return sorted(s.name for s in discover_page_sources(DATA_DIR))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--book", nargs="*", default=[], help="tên quyển, cách nhau bởi dấu cách")
    ap.add_argument("--nxb", default="", help="hậu tố NXB: KNTT / CTST / CD")
    ap.add_argument("--all", action="store_true", help="chọn TẤT CẢ quyển có trên đĩa")
    ap.add_argument("--thu", action="store_true", help="chỉ in, KHÔNG hạ cờ gì")
    ap.add_argument("--ignore-version", action="store_true",
                    help="ha co MOI trang text_indexed=True, bo qua so sanh version "
                         "(mac dinh chi ha co trang CHUA dat dung version hien tai)")
    ap.add_argument("--version", default=TEXT_EXTRACTION_VERSION,
                    help="version coi la 'da xong' (mac dinh doc tu src/config.py)")
    a = ap.parse_args()

    tren_dia = _quyen_tren_dia()
    chon = list(a.book)
    if a.nxb:
        chon += [b for b in tren_dia if b.upper().endswith("_" + a.nxb.upper())]
    if a.all:
        chon += tren_dia
    chon = sorted(set(chon))

    if not chon:
        print("Chưa chọn quyển nào. Dùng --book, --nxb hoặc --all.")
        print(f"Có trên đĩa: {', '.join(tren_dia)}")
        return 2

    la = [b for b in chon if b not in tren_dia]
    if la:
        # Thoát khác 0 thay vì bỏ qua: một lỗi chính tả trong tên quyển mà im
        # lặng sẽ khiến người dùng tưởng đã reset, rồi ETL chạy lại và không
        # đụng tới đúng những trang cần sửa.
        print(f"[LỖI] không có trên đĩa: {la}")
        print(f"Có: {', '.join(tren_dia)}")
        return 2

    client = chromadb.PersistentClient(path=str(PERSIST_DIR))
    st = client.get_collection("processing_status")
    # Trạng thái nằm trong `documents` (một chuỗi JSON), KHÔNG nằm trong
    # `metadatas` — giống đúng bẫy đã cắn `reset_image_books.py` (D-52/121).
    got = st.get(limit=1_000_000, include=["documents"])

    theo_quyen: dict[str, list[dict]] = {}
    da_dat_version = 0
    for raw in got["documents"]:
        try:
            d = json.loads(raw or "{}")
        except Exception:
            continue
        if d.get("pdf_filename") not in chon or not d.get("text_indexed"):
            continue
        if not a.ignore_version and d.get("text_extraction_version") == a.version:
            da_dat_version += 1
            continue
        theo_quyen.setdefault(d["pdf_filename"], []).append(d)

    text_col = client.get_collection("biology_text")
    n_chunk = Counter(m.get("source")
                      for m in text_col.get(limit=1_000_000,
                                            include=["metadatas"])["metadatas"])

    print(f"{'quyển':22s} {'chunk text':>10} {'sẽ hạ cờ':>10}")
    for b in chon:
        print(f"{b:22s} {n_chunk.get(b, 0):10d} {len(theo_quyen.get(b, [])):10d}")
    tong_chunk = sum(n_chunk.get(b, 0) for b in chon)
    tong_tr = sum(len(v) for v in theo_quyen.values())
    print(f"{'TỔNG':22s} {tong_chunk:10d} {tong_tr:10d}")
    if not a.ignore_version:
        print(f"(đã bỏ qua {da_dat_version} trang đã đạt version {a.version!r} — "
              f"resume-safe; thêm --ignore-version để hạ cờ TUYỆT ĐỐI mọi trang)")

    if a.thu:
        print("\n--thu: không hạ cờ gì.")
        return 0

    from src.etl import ProcessingStatus
    ps = ProcessingStatus()
    cap = [d for v in theo_quyen.values() for d in v]
    for d in cap:
        ps.update_status(
            page_key=d["page_key"],
            page_number=int(d["page_number"]),
            text_indexed=False,
            text_extraction_version="",
            pdf_filename=d.get("pdf_filename"),
        )
    print(f"\nĐã hạ cờ text_indexed cho {len(cap)} trang "
          f"(image_extracted giữ nguyên).")
    print("Chạy lại: python main.py --text-only [--book <quyển>]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
