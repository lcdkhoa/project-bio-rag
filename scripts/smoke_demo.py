# -*- coding: utf-8 -*-
"""Thử luồng thật đầu-cuối qua HTTP, không cần mở trình duyệt.

    python scripts/smoke_demo.py
    python scripts/smoke_demo.py --host http://localhost:5000 --cau-hoi "Quang hợp là gì?"

Kiểm đúng những thứ giao diện web phụ thuộc, và **kiểm bằng cách tải thật**:

1. `/api/health` trả 200 và kho không rỗng.
2. `/api/chat` trả đủ `answer_text` + `citations` + `images`.
3. Mỗi `image_url` trả về TẢI ĐƯỢC thật (mã 200, đúng kiểu ảnh) — đây là chỗ
   từng hỏng âm thầm: máy chủ trả đường dẫn tuyệt đối của máy chạy ETL, giao
   diện dựng ra `<img>` gãy, và không có gì báo lỗi.
4. `/api/chat/stream` phát được sự kiện và kết thúc bằng `done`.

Thoát khác 0 khi có mục nào hỏng, để dùng được trong một lệnh nối.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

MAC_DINH_HOST = "http://localhost:5000"
MAC_DINH_CAU_HOI = "Quang hợp là gì?"
CHO_TOI_DA = 300          # giây; trên CPU một câu mất ~90 s


def _get(url, timeout=30):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.headers, r.read()


def _post_json(url, payload, timeout=CHO_TOI_DA):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


class KetQua:
    def __init__(self):
        self.hong = []

    def kiem(self, dieu_kien, ten, chi_tiet=""):
        dau = "OK  " if dieu_kien else "HỎNG"
        print(f"  [{dau}] {ten}" + (f" — {chi_tiet}" if chi_tiet else ""))
        if not dieu_kien:
            self.hong.append(ten)
        return dieu_kien


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default=MAC_DINH_HOST)
    p.add_argument("--cau-hoi", default=MAC_DINH_CAU_HOI)
    args = p.parse_args()
    host = args.host.rstrip("/")
    kq = KetQua()

    # --- 1. health -----------------------------------------------------------
    print(f"\n1) {host}/api/health")
    try:
        _, _, body = _get(f"{host}/api/health", timeout=10)
        health = json.loads(body)
    except (urllib.error.URLError, OSError) as exc:
        print(f"  [HỎNG] không gọi được — máy chủ chưa chạy? ({exc})")
        return 1
    print(f"         {health}")
    kq.kiem(health.get("status") == "ok", "trạng thái ok")
    kq.kiem((health.get("text_chunks") or 0) > 0, "kho văn bản không rỗng",
            f"{health.get('text_chunks')} đoạn")
    kq.kiem((health.get("image_docs") or 0) > 0, "kho ảnh không rỗng",
            f"{health.get('image_docs')} hình")

    # --- 2. chat -------------------------------------------------------------
    print(f"\n2) {host}/api/chat — {args.cau_hoi!r} (có thể mất ~90 giây trên CPU)")
    try:
        _, body = _post_json(f"{host}/api/chat", {"question": args.cau_hoi})
        chat = json.loads(body)
    except (urllib.error.URLError, OSError) as exc:
        print(f"  [HỎNG] gọi thất bại: {exc}")
        return 1

    answer_text = chat.get("answer_text") or ""
    citations = chat.get("citations") or []
    images = chat.get("images") or []
    print(f"         câu trả lời: {answer_text[:120]!r}")

    kq.kiem(bool(answer_text), "có answer_text")
    kq.kiem("📚" not in answer_text, "answer_text KHÔNG lẫn khối nguồn dạng chữ")
    kq.kiem(bool(citations), "có citations", f"{len(citations)} nguồn")
    for c in citations:
        print(f"           - {c.get('display')}")
    kq.kiem(
        all(not str(c.get("book", "")).startswith("SGK_") for c in citations),
        "mọi nhãn sách đã dịch sang tên đọc được",
    )

    # --- 3. ảnh: TẢI THẬT, không chỉ nhìn chuỗi -------------------------------
    print(f"\n3) tải thật {len(images)} hình mà máy chủ trả về")
    if not images:
        print("         (không có hình cho câu hỏi này — bỏ qua)")
    for image in images[:5]:
        url = image.get("image_url") or image.get("image_path") or ""
        kq.kiem(url.startswith("/images/"), f"đường dẫn tương đối: {url[:60]}")
        if not url.startswith("/images/"):
            continue
        try:
            status, headers, blob = _get(f"{host}{url}", timeout=30)
        except (urllib.error.URLError, OSError) as exc:
            kq.kiem(False, f"tải {url}", str(exc))
            continue
        kq.kiem(
            status == 200 and headers.get("Content-Type", "").startswith("image/"),
            f"tải được {url.rsplit('/', 1)[-1]}",
            f"{status}, {len(blob)} byte, {headers.get('Content-Type')}",
        )

    # --- 4. stream -----------------------------------------------------------
    print(f"\n4) {host}/api/chat/stream — chỉ kiểm có phát sự kiện và kết thúc bằng `done`")
    try:
        data = json.dumps({"question": args.cau_hoi}, ensure_ascii=False).encode()
        req = urllib.request.Request(
            f"{host}/api/chat/stream", data=data,
            headers={"Content-Type": "application/json"})
        ten_su_kien = []
        with urllib.request.urlopen(req, timeout=CHO_TOI_DA) as r:
            for dong in r:
                dong = dong.decode("utf-8", "replace").strip()
                if dong.startswith("event:"):
                    ten_su_kien.append(dong.split(":", 1)[1].strip())
    except (urllib.error.URLError, OSError) as exc:
        kq.kiem(False, "luồng SSE", str(exc))
        ten_su_kien = []

    kq.kiem("status" in ten_su_kien, "có sự kiện status")
    kq.kiem("answer_delta" in ten_su_kien, "có sự kiện answer_delta",
            f"{ten_su_kien.count('answer_delta')} mẩu")
    kq.kiem(ten_su_kien[-1:] == ["done"], "kết thúc bằng done")

    print()
    if kq.hong:
        print(f"KẾT QUẢ: {len(kq.hong)} mục HỎNG — " + "; ".join(kq.hong))
        return 1
    print("KẾT QUẢ: tất cả các mục đều đạt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
