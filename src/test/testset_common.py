# -*- coding: utf-8 -*-
"""Tiện ích dùng chung cho `run_eval.py` và `retrieval_benchmark.py` (D-182).

CHỈ chứa cổng người duyệt tay + helper đặt tên file nháp — KHÔNG chứa logic
sinh câu hỏi (đó là việc riêng của `build_testset.py`, cố ý không import module
này để hai script không phụ thuộc chéo nhau).
"""
from __future__ import annotations

import json
from pathlib import Path

# CỐ Ý định nghĩa lại (không import từ build_testset.py) — cả hai file cùng
# neo theo Path(__file__).resolve().parent nên luôn trỏ đúng cùng một
# src/test/testset/, và giữ Task 2/Task 3 không phụ thuộc chéo nhau (ranh giới
# song song hóa đã chốt ở đầu plan). Đây là trade-off DRY-vs-độc-lập có chủ ý,
# không phải trùng lặp bỏ sót.
OUT_DIR = Path(__file__).resolve().parent / "testset"
DRAFT_CSV = OUT_DIR / "draft.csv"
META_JSON = OUT_DIR / "meta.json"


def require_human_reviewed(meta_path: Path, allow_draft: bool = False) -> None:
    """Chặn dùng một bộ test CHƯA được người duyệt tay, trừ khi `--allow-draft`.

    `--allow-draft` chỉ để tự kiểm code của chính người chạy — KHÔNG dùng số ra
    từ đó cho báo cáo (xem cảnh báo in ra + hậu tố `_NHAP_CHUA_DUYET` mà
    `duong_dan_output` thêm vào MỌI file output khi cờ này bật).
    """
    meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    if not meta.get("human_reviewed") and not allow_draft:
        raise SystemExit(
            f"{meta_path} chưa được duyệt tay (human_reviewed=false).\n"
            f"Đọc lại {DRAFT_CSV}, sửa câu/ground_truth sai, rồi chạy:\n"
            f"  python -m src.test.build_testset --mark-reviewed\n"
            f"(Chỉ dùng --allow-draft để tự kiểm code của CHÍNH BẠN, không dùng "
            f"số ra từ --allow-draft cho báo cáo.)")
    if allow_draft and not meta.get("human_reviewed"):
        print("!! CẢNH BÁO: đang chạy trên bộ test NHÁP, CHƯA người duyệt tay. "
              "Mọi file output sẽ mang hậu tố _NHAP_CHUA_DUYET — KHÔNG dùng số "
              "này cho báo cáo tốt nghiệp.")


def duong_dan_output(ten_file: str, allow_draft: bool) -> Path:
    """Thêm hậu tố `_NHAP_CHUA_DUYET` vào tên file khi `allow_draft=True`.

    Cảnh báo console không đủ (D-182, phản biện lần 4 của spec): nếu output bị
    redirect vào log hoặc file được mở lại nhiều ngày sau, phải phân biệt được
    nháp với chính thức chỉ bằng NHÌN TÊN FILE.
    """
    p = OUT_DIR / ten_file
    if not allow_draft:
        return p
    return p.with_name(f"{p.stem}_NHAP_CHUA_DUYET{p.suffix}")
