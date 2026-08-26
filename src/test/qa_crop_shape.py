"""Đo HÌNH DẠNG khung cắt: bao nhiêu crop là dải dọc hẹp?

Vì sao cần phép đo này bên cạnh `qa_figure_coverage`: độ phủ nhãn chỉ trả lời
*"có khung cắt nào mang nhãn Hình A.B không"*, KHÔNG trả lời *"khung cắt có đúng
vùng hình không"*. Đo được (D-125): KNTT đạt **95--96% độ phủ nhãn** trong khi
**17,5% khung cắt là dải dọc hẹp** cắt ngang giữa hình ghép. Cổng độ phủ mù hoàn
toàn với lỗi đó, nên nó phải có cổng riêng.

Định nghĩa dải dọc hẹp (D-125): rộng < 20% chiều rộng trang **VÀ** cao > 1,5 lần
rộng. Chiều rộng trang đo từ chính trang PNG của quyển, không hằng số hoá.

    python -m src.test.qa_crop_shape
    python -m src.test.qa_crop_shape --nxb KNTT
    python -m src.test.qa_crop_shape --book SGK_KHTN_8_KNTT --json truoc.json
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import chromadb

from src.config import PERSIST_DIR
from src.etl.page_source import discover_page_sources
from src.config import DATA_DIR

HEP_TREN_TRANG = 0.20      # rộng < 20% chiều rộng trang
TY_LE_CAO_TREN_RONG = 1.5  # và cao > 1,5 lần rộng
NGUONG_CANH_BAO = 0.10     # >10% crop là dải hẹp -> thoát 1


def chieu_rong_trang() -> dict:
    """Chiều rộng trang thật của từng quyển, đo từ trang đầu tiên trên đĩa."""
    ra = {}
    for src in discover_page_sources(DATA_DIR):
        try:
            trang = src.page_numbers()[0]
            ra[src.name] = int(src.load(trang).shape[1])
        except Exception as exc:  # pragma: no cover - phụ thuộc dữ liệu trên đĩa
            print(f"  (bỏ qua {src.name}: {exc})")
    return ra


def do(books=None) -> dict:
    rong_trang = chieu_rong_trang()
    client = chromadb.PersistentClient(path=str(PERSIST_DIR))
    col = client.get_collection("biology_images")

    ket_qua = {}
    for ten in sorted(rong_trang):
        if books and ten not in books:
            continue
        got = col.get(where={"pdf_filename": ten}, include=["metadatas"])
        metas = got.get("metadatas") or []
        if not metas:
            continue
        W = rong_trang[ten]
        hep = []
        for m in metas:
            w = int(m.get("image_width") or 0)
            h = int(m.get("image_height") or 0)
            if w <= 0 or h <= 0:
                continue
            if w < W * HEP_TREN_TRANG and h > TY_LE_CAO_TREN_RONG * w:
                hep.append(m)
        ket_qua[ten] = {
            "chieu_rong_trang": W,
            "tong_crop": len(metas),
            "dai_hep": len(hep),
            "ty_le": round(len(hep) / len(metas), 4) if metas else 0.0,
        }
    return ket_qua


def main() -> int:
    ap = argparse.ArgumentParser(description="Đo tỉ lệ khung cắt là dải dọc hẹp")
    ap.add_argument("--book", nargs="*", default=None)
    ap.add_argument("--nxb", default=None, help="lọc theo hậu tố: KNTT / CTST / CD")
    ap.add_argument("--json", default=None, help="ghi kết quả ra file JSON để so trước/sau")
    a = ap.parse_args()

    books = set(a.book) if a.book else None
    kq = do(books)
    if a.nxb:
        kq = {k: v for k, v in kq.items() if k.endswith("_" + a.nxb.upper())}

    print(f"{'quyển':<20}{'crop':>7}{'dải hẹp':>10}{'tỉ lệ':>9}")
    tong, tong_hep = 0, 0
    for ten, v in kq.items():
        print(f"{ten:<20}{v['tong_crop']:>7}{v['dai_hep']:>10}{v['ty_le']*100:>8.1f}%")
        tong += v["tong_crop"]
        tong_hep += v["dai_hep"]
    ty_le = tong_hep / tong if tong else 0.0
    print(f"{'TỔNG':<20}{tong:>7}{tong_hep:>10}{ty_le*100:>8.1f}%")

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(kq, f, ensure_ascii=False, indent=2)
        print(f"Đã ghi {a.json}")

    # Thoát khác 0 khi vượt ngưỡng: một phép đo chỉ có ích khi nó CHẶN được.
    return 1 if ty_le > NGUONG_CANH_BAO else 0


if __name__ == "__main__":
    raise SystemExit(main())
