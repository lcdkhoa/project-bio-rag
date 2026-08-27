# -*- coding: utf-8 -*-
"""Ghep ket qua MinerU vao dong Tesseract bi gate nghi cong thuc (D-144, Buoc 3).

Hai ham thuan, khong can model that de test — thiet ke day du:
document/specs/2026-08-27-formula-ocr-hybrid-buoc23-design.md §3, §2.4.

`merge_formula_line`: ghep TOKEN vao MOT DONG, giu nguyen phan tieng Viet con
lai cua Tesseract (MinerU thang cong thuc nhung thua dau tieng Viet, D-108).

`apply_line_merge_to_region`: dan dong da sua tro lai vao text CUA CA REGION.
Hai OCR pass (`image_to_string` cho region, `image_to_data` cho dong) khong
chung offset ky tu, nen ghep bang cach tim DONG NGUYEN VEN lam chuoi con, chi
thay khi khop DUNG 1 LAN.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from .formula_signals import CO_DAU_BANG, CONG_THUC_HONG, TOKEN_HOA, TOKEN_LY


@dataclass
class MergeOutcome:
    text: str
    status: str  # "applied" | "unmatched_count" | "not_suspect"
    n_holes: int
    n_applied: int


def _chem_tokens(text: str) -> List[str]:
    """Token hoa trong `text`, LOAI token da nam trong mot phuong trinh ly.

    Tach rieng khoi `formula_tokens` (dung de CHAM, D-108 da khoa so) vi o day
    can biet CHINH XAC vi tri (span), khong phai chi mot list token.
    """
    ly_spans = [m.span() for m in TOKEN_LY.finditer(text)]
    out = []
    for m in TOKEN_HOA.finditer(text):
        if any(a <= m.start() and m.end() <= b for a, b in ly_spans):
            continue
        tok = m.group(0)
        if any(c.isalpha() for c in tok):
            out.append(tok)
    return out


def merge_formula_line(tesseract_line: str, mineru_text: str) -> MergeOutcome:
    hoa_holes = list(CONG_THUC_HONG.finditer(tesseract_line))
    ly_holes = list(CO_DAU_BANG.finditer(tesseract_line))
    if not hoa_holes and not ly_holes:
        return MergeOutcome(tesseract_line, "not_suspect", 0, 0)

    mineru_text = str(mineru_text or "")
    ly_tokens = [m.group(0) for m in TOKEN_LY.finditer(mineru_text)]
    hoa_tokens = _chem_tokens(mineru_text)

    replacements: List[Tuple[int, int, str]] = []
    n_applied = 0
    if hoa_holes and len(hoa_holes) == len(hoa_tokens):
        for hole, tok in zip(hoa_holes, hoa_tokens):
            replacements.append((hole.start(), hole.end(), tok))
        n_applied += len(hoa_holes)
    if ly_holes and len(ly_holes) == len(ly_tokens):
        for hole, tok in zip(ly_holes, ly_tokens):
            replacements.append((hole.start(), hole.end(), tok))
        n_applied += len(ly_holes)

    n_holes = len(hoa_holes) + len(ly_holes)
    if not replacements:
        return MergeOutcome(tesseract_line, "unmatched_count", n_holes, 0)

    # Ap tu CUOI dong len DAU de offset cac vi tri chua xu ly khong bi lech.
    replacements.sort(key=lambda r: r[0], reverse=True)
    out = tesseract_line
    for start, end, tok in replacements:
        out = out[:start] + tok + out[end:]
    status = "applied" if n_applied == n_holes else "unmatched_count"
    return MergeOutcome(out, status, n_holes, n_applied)


def apply_line_merge_to_region(region_text: str, original_line: str,
                                merged_line: str) -> Tuple[str, str]:
    count = region_text.count(original_line)
    if count == 0:
        return region_text, "line_not_located_in_region_text"
    if count >= 2:
        return region_text, "line_ambiguous_in_region_text"
    idx = region_text.index(original_line)
    new_text = (region_text[:idx] + merged_line +
                region_text[idx + len(original_line):])
    return new_text, "applied"
