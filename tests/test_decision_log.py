# -*- coding: utf-8 -*-
"""`document/decision_log.html` phải PHÂN TÍCH ĐƯỢC, không chỉ phải tồn tại.

Sổ quyết định là nơi duy nhất ghi vì sao repo này làm như nó đang làm. Nó là một
mảng JavaScript nhúng trong HTML, nên **một lỗi cú pháp làm hỏng CẢ TRANG chứ
không chỉ một mục** — và hỏng hoàn toàn im lặng: tệp vẫn nằm đó, vẫn được commit,
vẫn mở được bằng trình soạn thảo.

Chuyện đó đã xảy ra thật: mục D-117 (thêm 2026-08-25) có trường `notes` bị xuống
dòng giữa chừng. Trong JavaScript, chuỗi trong dấu nháy kép **không được** chứa
ký tự xuống dòng thật, nên từ lúc đó tới khi phát hiện (2026-08-26) toàn bộ sổ
quyết định không render được một mục nào. Test này chặn đúng lớp lỗi đó.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

SO = Path(__file__).resolve().parent.parent / "document" / "decision_log.html"

BS = chr(92)   # dấu gạch chéo ngược, viết thế này để bản thân test không dính bẫy escape
NHAY = '"'


def _than_mang() -> list[str]:
    s = io.open(SO, encoding="utf-8").read()
    i = s.index("const DECISIONS")
    return s[i:].split("\n")


def _vi_tri_dong_chuoi(dong: str) -> int:
    """Vị trí dấu nháy đóng chuỗi, theo đúng luật JavaScript; -1 nếu chưa đóng."""
    j = dong.index(NHAY) + 1
    while j < len(dong):
        c = dong[j]
        if c == BS:          # ký tự sau dấu gạch chéo luôn bị nuốt
            j += 2
            continue
        if c == NHAY:
            return j
        j += 1
    return -1


@pytest.mark.skipif(not SO.exists(), reason="chưa có sổ quyết định")
def test_moi_truong_chuoi_deu_dong_tren_cung_mot_dong():
    hong = []
    for n, dong in enumerate(_than_mang(), 1):
        st = dong.strip()
        if not st.startswith(("decision:", "notes:")):
            continue
        if _vi_tri_dong_chuoi(dong) < 0:
            hong.append(f"dòng {n}: {st[:70]}…")
    assert not hong, (
        "Chuỗi JavaScript bị xuống dòng giữa chừng — cả trang sẽ không render:\n"
        + "\n".join(hong)
    )


@pytest.mark.skipif(not SO.exists(), reason="chưa có sổ quyết định")
def test_id_tang_dan_va_khong_trung():
    ids = re.findall(r'^\s*id: "D-(\d+)"', "\n".join(_than_mang()), re.M)
    so = [int(x) for x in ids]
    assert so, "không đọc được mục nào"
    assert len(so) == len(set(so)), "có id trùng nhau"
    assert so == sorted(so), "id không tăng dần"


@pytest.mark.skipif(not SO.exists(), reason="chưa có sổ quyết định")
def test_khong_co_ky_tu_dieu_khien():
    """Cùng lớp lỗi với phép kiểm `[ctrl]` của `report/kiem_tra_tex.py`."""
    s = io.open(SO, encoding="utf-8", newline="").read()
    xau = sorted({c for c in s if ord(c) < 32 and c not in "\n\r\t"})
    assert not xau, [hex(ord(c)) for c in xau]
