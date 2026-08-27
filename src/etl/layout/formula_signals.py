# -*- coding: utf-8 -*-
"""Tín hiệu công thức Hoá/Lý dùng chung giữa bake-off (`src/test/ocr_bakeoff.py`)
và gate phát hiện vùng nghi công thức (`formula_gate.py`).

Các mẫu regex ở đây được ĐO trên chính D-56/D-73 (281 công thức hỏng : 4 đúng
trên toàn kho), không phải đoán. Chuyển vào một module dùng chung (thay vì để
mỗi nơi định nghĩa lại) vì `formula_tokens`/`normalize_formula` là số liệu ĐÃ
KHOÁ ở D-108 (bake-off) — hai bản định nghĩa trôi nhau sẽ âm thầm đổi số đã
công bố (nguyên tắc 6, một nguồn sự thật duy nhất).

KHÔNG sửa các regex này để "bắt thêm ca" mà không đo lại: `formula_tokens` là
đơn vị chấm CT trong `ocr_bakeoff.score_engine`, và số CT 0,441/0,048 của D-108
đã bị khoá bằng đúng các mẫu này.
"""
from __future__ import annotations

import re
from typing import List

# --- Token hoá công thức (dùng để CHẤM, D-108 đã khoá số theo đúng mẫu này) --

_SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
# Chỉ số dưới đứng SAU một chữ cái hoá học và trước một chữ cái/ngoặc/kết thúc.
# Ràng buộc đó giữ `2 H₂O` (hệ số 2 đứng trước) và `tr.154` không bị đổi.
_CHI_SO_ASCII = re.compile(r"(?<=[A-Za-z\)\]])(\d+)")


def normalize_formula(text: str) -> str:
    """Chuẩn hoá CÁCH GÕ công thức, không chuẩn hoá nội dung.

    `O2` và `O₂` là cùng một câu trả lời đúng. Nhưng `O,` **không** được chuẩn
    hoá thành `O₂`: đoán lại một chỉ số đã mất là bịa (nguyên tắc 1).
    """
    s = " ".join(str(text or "").split())
    return _CHI_SO_ASCII.sub(lambda m: m.group(1).translate(_SUB), s)


# Công thức HOÁ: chữ cái hoa mở đầu, có ít nhất một chỉ số (Unicode hoặc ASCII).
# `(NH₄)₂SO₄` cũng khớp nhờ nhóm ngoặc.
_TOKEN_HOA = re.compile(
    r"\(?[A-Z][A-Za-z]{0,2}\)?(?:[₀-₉]|\d)"
    r"(?:\(?[A-Z][A-Za-z]{0,2}\)?(?:[₀-₉]|\d)?)*")
# Công thức LÝ: một phương trình có `=`, ví dụ `A = Fs`, `1 J = 1 N·m`. Hai bên
# `=` chỉ nhận ký hiệu KHÔNG DẤU (chữ Latin trần, số, đơn vị) — nếu cho phép
# chữ có dấu thì "công thức A = Fs với F" nuốt luôn cả câu văn tiếng Việt quanh
# phương trình.
_KY_HIEU = r"(?<![A-Za-zÀ-ỹ])[A-Za-z0-9][A-Za-z0-9₀-₉·./^]*(?![A-Za-zÀ-ỹ])"
_TOKEN_LY = re.compile(
    rf"{_KY_HIEU}(?:\s{_KY_HIEU})?\s*=\s*{_KY_HIEU}(?:\s{_KY_HIEU})?")


def formula_tokens(text: str) -> List[str]:
    """Các token CÔNG THỨC trong một dòng — đơn vị chấm của chỉ số CT (D-108).

    **Có khoảng mù đã biết, đo được khi soát tay gate D-144**: không bắt token
    có ngoặc bao quanh biến (`KLPT(NₓOᵧ)`) và không bắt phương trình dùng ký
    hiệu Unicode ngoài ASCII/subscript (`⇒`, `≈`). Không sửa ở đây vì số CT của
    D-108 đã khoá theo đúng hành vi hiện tại — sửa regex này là sửa NGẦM một số
    đã công bố.
    """
    s = " ".join(str(text or "").split())
    out = [m.group(0).strip() for m in _TOKEN_LY.finditer(s)]
    da_co = " ".join(out)
    for m in _TOKEN_HOA.finditer(s):
        tok = m.group(0).strip()
        # Bỏ token chỉ là số (`2016`) hoặc đã nằm trong một phương trình đã bắt.
        if not any(c.isalpha() for c in tok) or tok in da_co:
            continue
        out.append(tok)
    return out


# --- Tín hiệu OCR-HỎNG (D-56/D-73): dùng để GATE, không dùng để chấm --------

# Chỉ số dưới bị phá thành dấu phẩy. Mẫu lấy từ chính phép đo D-56/D-73:
# `CO,` 88 lần, `CH,` 60, `SO,` 43, `H,O` 31, `H,SO,` 21.
CONG_THUC_HONG = re.compile(
    r"(?:\b(?:CO|CH|SO|NO|N|O|H|Cl|Fe|Ca|Na|Mg|Cu|Zn|Al|K|S|P)\s?,"
    r"|\bH\s?,\s?O\b|\bH\s?,\s?SO\s?,|\(\s?0\s?,|\b0\s?,(?:\s|$))")
# Công thức VẬT LÍ hầu như luôn có `=`, và nó KHÔNG có dấu phẩy-chỉ-số-dưới nên
# bộ lọc công thức Hoá bỏ sót nó hoàn toàn: `1 J = 1 Ñm` (D-63, RAG trả lời RỖNG).
CO_DAU_BANG = re.compile(r"[A-Za-zÀ-ỹ0-9)\]]\s*=\s*[A-Za-zÀ-ỹ0-9(]")
