# -*- coding: utf-8 -*-
"""Bake-off OCR: chọn model đọc chữ BẰNG PHÉP ĐO, không bằng danh tiếng.

Thiết kế đầy đủ: `document/specs/2026-08-25-ocr-model-bakeoff-design.md`.

## Vì sao cần bước này

Bốn ứng viên (`PaddleOCR-VL-1.6`, `dots.ocr`, `MinerU2.5-Pro`, `Nanonets-OCR2-3B`)
đều quảng cáo công thức + bảng — đúng hai bệnh của corpus này (281 công thức hỏng
: 4 đúng, D-56; bảng mất quan hệ hàng/cột, D-63) — nhưng **không model nào nhắc
tới tiếng Việt trong model card**. Chọn theo danh tiếng ở đây là lặp lại D-47:
Vintern-1B nghe rất hợp lý, chạy thật thì bịa 4/12 crop.

## Phiếu duyệt được thiết kế để KHÔNG TICK ĐƯỢC

D-90 vừa dạy bằng tiền thật: một phiếu 50 câu có thể tick đã bị điền **50/50 một
nhãn trong 38 giây**, và con số đó đã được công bố. Nên ở đây:

1. Người duyệt **GÕ chữ**, không chọn đúng/sai, và ô trả lời **không mồi sẵn chữ
   của máy**.
2. Đơn vị công việc là **một DÒNG đã crop**, không phải cả trang 2 000 ký tự —
   D-55 đo được 23/24 file gold cũ trùng *từng chữ* với output của máy, vì việc
   sửa cả trang là việc không ai làm nổi.
3. Ô loại `cong_thuc` vào phiếu **vì máy đã đọc sai**. Gõ lại y nguyên chữ của máy
   nghĩa là không mở ảnh ra xem → `score_answers` đếm nó là `nghi_dong_dau` và
   **từ chối công bố**, chứ không in số kèm chú thích.
"""

from __future__ import annotations

import argparse
import base64
import csv
import html
import io
import json
import os
import re
import sys
import time
import unicodedata
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PAGES_FILE = Path(__file__).with_name("ocr_bakeoff_pages.json")


class ItemKind(str, Enum):
    """Loại ô trong phiếu. Giá trị là chuỗi để ghi thẳng ra JSON."""

    CONG_THUC = "cong_thuc"
    SO = "so"
    BANG = "bang"
    DOI_CHUNG = "doi_chung"


# --- 1. Gom word box thành DÒNG ------------------------------------------

def group_lines(words: Sequence[dict]) -> List[dict]:
    """Gom output `image_to_data` của Tesseract thành dòng, giữ bbox hợp.

    Khoá gom là `(block_num, par_num, line_num)`, **không phải `line_num` một
    mình**: Tesseract đánh `line_num` lại từ 0 trong mỗi block, nên gom theo nó
    sẽ dán hai cột của bố cục hai cột (CTST/CD) vào cùng một dòng.
    """
    theo_dong: Dict[Tuple[int, int, int], List[dict]] = {}
    thu_tu: List[Tuple[int, int, int]] = []
    for w in words:
        text = str(w.get("text", "")).strip()
        if not text:
            continue
        key = (int(w.get("block_num", 0)), int(w.get("par_num", 0)),
               int(w.get("line_num", 0)))
        if key not in theo_dong:
            theo_dong[key] = []
            thu_tu.append(key)
        theo_dong[key].append(w)

    out: List[dict] = []
    for key in thu_tu:
        ws = theo_dong[key]
        x0 = min(int(w["left"]) for w in ws)
        y0 = min(int(w["top"]) for w in ws)
        x1 = max(int(w["left"]) + int(w["width"]) for w in ws)
        y1 = max(int(w["top"]) + int(w["height"]) for w in ws)
        confs = [float(w.get("conf", -1)) for w in ws
                 if str(w.get("conf", "-1")) not in ("-1", "")]
        out.append({
            "text": " ".join(str(w["text"]).strip() for w in ws),
            "bbox": (x0, y0, x1, y1),
            "conf": round(sum(confs) / len(confs), 1) if confs else None,
        })
    return out


# --- 2. Chỉ chọn dòng CÓ BỆNH -------------------------------------------

# Chỉ số dưới bị phá thành dấu phẩy. Mẫu lấy từ chính phép đo D-56/D-73, không
# phải từ trí tưởng tượng: `CO,` 88 lần, `CH,` 60, `SO,` 43, `H,O` 31, `H,SO,` 21.
_CONG_THUC_HONG = re.compile(
    r"(?:\b(?:CO|CH|SO|NO|N|O|H|Cl|Fe|Ca|Na|Mg|Cu|Zn|Al|K|S|P)\s?,"
    r"|\bH\s?,\s?O\b|\bH\s?,\s?SO\s?,|\(\s?0\s?,|\b0\s?,(?:\s|$))")
# Chuỗi 3 chữ số dính nhau: nghi mất dấu phẩy thập phân (`26,2` -> `262`, sai 10×).
# 4 chữ số là NĂM, gặp khắp nơi — cờ nó thì phiếu toàn nhiễu.
_SO_DAI = re.compile(r"(?<!\d)\d{3}(?!\d)")
# Dòng CHỈ có số (và dấu câu) là SỐ TRANG IN, không phải số liệu bị hỏng. Phiếu
# đầu tiên đã có một ô nội dung đúng là `'155'` — tìm ra bằng cách MỞ PHIẾU ra
# đối chiếu, không bằng test.
_CHI_CO_SO = re.compile(r"^[\d\s.,:;|]+$")
# Công thức VẬT LÍ hầu như luôn có `=`, và nó KHÔNG có dấu phẩy-chỉ-số-dưới nên
# bộ lọc công thức Hoá bỏ sót nó hoàn toàn: `1 J = 1 Ñm` (D-63, RAG trả lời RỖNG).
_CO_DAU_BANG = re.compile(r"[A-Za-zÀ-ỹ0-9)\]]\s*=\s*[A-Za-zÀ-ỹ0-9(]")
# Tiêu đề bảng phải BẮT ĐẦU bằng "Bảng N.M". Câu văn `(xem Bảng 12.1).` chỉ TRỎ
# tới bảng; đưa nó vào phiếu thì người duyệt gõ lại một câu văn và ta không đo
# được gì về quan hệ hàng/cột — đúng thứ đang bị mất (D-63).
_BANG = re.compile(r"^\s*B[ảa]ng\s+\d+\.\d+", re.IGNORECASE)
# Dải ảnh của một bảng: từ dòng tiêu đề xuống 50% chiều cao trang. Sách KHTN đặt
# "Bảng N.M …" NGAY TRÊN bảng, nên mở xuống là đúng chiều.
TABLE_BAND_FRACTION = 0.5


def table_band_bbox(caption_bbox, page_w: int, page_h: int):
    """Dải chứa cả bảng, tính từ bbox của dòng tiêu đề.

    Lấy TRỌN chiều rộng trang: trên bố cục hai cột (CTST/CD) một bảng thường
    chiếm cả trang, và thà cho người duyệt thấy thừa hơn là cắt mất một cột —
    cột bị cắt là chính thứ ta đang đo.
    """
    _, y0, _, _ = caption_bbox
    y1 = min(int(page_h), int(y0) + int(page_h * TABLE_BAND_FRACTION))
    return (0, int(y0), int(page_w), y1)


def classify_line(text: str) -> Optional[ItemKind]:
    """Dòng này có đáng đưa vào phiếu không, và vì bệnh gì.

    Thứ tự ưu tiên là thứ tự mức độ bệnh: công thức (bệnh chính, 281:4) > bảng >
    số. Một dòng chỉ vào phiếu MỘT lần — 15 trang phải còn ~90 ô, không phải 900.
    """
    t = str(text or "")
    if not t.strip():
        return None
    if _CHI_CO_SO.match(t):
        return None
    if _CONG_THUC_HONG.search(t) or _CO_DAU_BANG.search(t):
        return ItemKind.CONG_THUC
    if _BANG.search(t):
        return ItemKind.BANG
    if _SO_DAI.search(t):
        return ItemKind.SO
    return None


# --- 3. Chấm phiếu, và TỪ CHỐI công bố khi phiếu đáng nghi ---------------

def _fold(text: str) -> str:
    s = str(text or "").replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


# --- 3b. Ba chỉ số chấm engine ------------------------------------------

_SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
# Chỉ số dưới đứng SAU một chữ cái hoá học và trước một chữ cái/ngoặc/kết thúc.
# Ràng buộc đó giữ `2 H₂O` (hệ số 2 đứng trước) và `tr.154` không bị đổi.
_CHI_SO_ASCII = re.compile(r"(?<=[A-Za-z\)\]])(\d+)")


def normalize_formula(text: str) -> str:
    """Chuẩn hoá CÁCH GÕ công thức, không chuẩn hoá nội dung.

    `O2` và `O₂` là cùng một câu trả lời đúng — người duyệt không nên bị phạt vì
    cách gõ. Nhưng `O,` **không** được chuẩn hoá thành `O₂`: đoán lại một chỉ số
    đã mất là bịa (nguyên tắc 1), và chính `O,` là thứ ta đang đo.
    """
    s = " ".join(str(text or "").split())
    return _CHI_SO_ASCII.sub(lambda m: m.group(1).translate(_SUB), s)


# Công thức HOÁ: chữ cái hoa mở đầu, có ít nhất một chỉ số (Unicode hoặc ASCII).
# `(NH₄)₂SO₄` cũng khớp nhờ nhóm ngoặc.
_TOKEN_HOA = re.compile(
    r"\(?[A-Z][A-Za-z]{0,2}\)?(?:[₀-₉]|\d)"
    r"(?:\(?[A-Z][A-Za-z]{0,2}\)?(?:[₀-₉]|\d)?)*")
# Công thức LÝ: một phương trình có `=`, ví dụ `A = Fs`, `1 J = 1 N·m`.
# Hai bên `=` chỉ nhận ký hiệu KHÔNG DẤU (chữ Latin trần, số, đơn vị) — nếu cho
# phép chữ có dấu thì `công thức A = Fs với F` nuốt luôn cả câu văn tiếng Việt
# quanh phương trình, và chỉ số CT sẽ đo văn xuôi thay vì đo công thức.
# Ranh giới `(?<![A-Za-zÀ-ỹ])` là bắt buộc: không có nó thì `công thức A = Fs
# với` khớp thành `c A = Fs v` — chữ `c` cuối "thức" và `v` đầu "với" đều là
# chữ Latin trần.
_KY_HIEU = r"(?<![A-Za-zÀ-ỹ])[A-Za-z0-9][A-Za-z0-9₀-₉·./^]*(?![A-Za-zÀ-ỹ])"
_TOKEN_LY = re.compile(
    rf"{_KY_HIEU}(?:\s{_KY_HIEU})?\s*=\s*{_KY_HIEU}(?:\s{_KY_HIEU})?")


def formula_tokens(text: str) -> List[str]:
    """Các token CÔNG THỨC trong một dòng — đơn vị chấm của chỉ số CT.

    Thiết kế §3.2 đòi đo **token công thức**, không phải cả dòng. So cả dòng thì
    một dòng 15 từ chỉ sai một dấu ở chữ thường cũng bị tính là hỏng công thức,
    và con số ra từ đó không trả lời được câu hỏi thật: *engine có đọc được `O₂`
    không?*

    Chấp nhận cả `O₂` lẫn `O2` vì người duyệt được phép gõ ASCII (§3.5 luật 3);
    `normalize_formula` gộp hai cách gõ lại khi so.
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


def diacritic_error_rate(gold: str, hyp: str) -> float:
    """Tỉ lệ từ sai **chỉ ở dấu** — cổng loại của bake-off.

    Đếm riêng khỏi lỗi CHỮ: `chế`→`ché` là lỗi dấu (bỏ dấu thì hai từ trùng),
    còn `quang`→`quaug` là lỗi chữ. Gộp hai loại vào một con số thì không biết
    model hỏng ở đâu — mà chỗ model nước ngoài dễ chết nhất chính là dấu.
    """
    g = str(gold or "").split()
    h = str(hyp or "").split()
    if not g:
        return 0.0
    loi = 0
    for i, tu in enumerate(g):
        khac = h[i] if i < len(h) else ""
        if tu != khac and _fold(tu) == _fold(khac):
            loi += 1
    return loi / len(g)


def table_cells(row: str) -> List[str]:
    """Tách một hàng bảng do người/engine gõ, phân cách bằng `|`."""
    return [c.strip() for c in str(row or "").split("|") if c.strip()]


KHONG_DOC_DUOC = "???"


def score_engine(items: Sequence[dict], gold: Dict[str, str],
                 hyp: Dict[str, str]) -> dict:
    """Ba chỉ số của MỘT engine trên gold set người duyệt.

    Hai luật khiến con số này trung thực:

    1. **Ô engine không trả lời được tính là SAI, không phải bỏ qua.** Bỏ qua sẽ
       thưởng cho engine im lặng — đúng loại "số cao mà sai" repo này sợ nhất
       (D-83: một bước thất bại mà lớp gọi vẫn báo thành công).
    2. **Ô người để trống, hoặc người ghi `???`, bị loại khỏi MỌI trục.** Không
       có bản người thì không có chuẩn để so; chấm bừa là bịa (nguyên tắc 1).
       `???` là câu trả lời hợp lệ và có giá trị: nó nói rằng chỗ đó không ai
       đọc được, kể cả người.
    3. **Ô THIẾU KEY và ô RỖNG được đếm RIÊNG.** Thiếu key = engine chưa chạy ô
       đó (lượt `--limit`, phiên Colab đứt); rỗng = engine đã chạy và không đọc
       được. Cả hai đều chấm là SAI, nhưng chúng là hai chuyện khác nhau và
       `--compare` phải nói ra chuyện nào: một engine mới chạy 3/97 ô có `DẤU`
       **0,000** — điểm hoàn hảo ở đúng cột quyết định thắng/thua — chỉ vì một
       từ mất hẳn không phải "lỗi dấu" (`_fold("Quang") != _fold("")`).
    """
    n_ct = n_dc = n_bang = 0
    dung_ct = 0.0
    tong_dau = 0.0
    dung_bang = 0.0
    khong_doc_duoc = 0
    o_cham = o_thieu = o_rong = 0

    for it in items:
        chuan = gold.get(it["id"])
        if chuan is None or not str(chuan).strip():
            continue
        if str(chuan).strip() == KHONG_DOC_DUOC:
            khong_doc_duoc += 1
            continue
        doc = str(hyp.get(it["id"], ""))          # thiếu -> "" -> sai, không bỏ
        o_cham += 1
        if it["id"] not in hyp:
            o_thieu += 1                          # engine CHƯA chạy ô này
        elif not doc.strip():
            o_rong += 1                           # engine chạy, không đọc được
        kind = it.get("kind")
        if kind == ItemKind.BANG.value:
            n_bang += 1
            dung_bang += table_cell_accuracy(chuan, doc)
        elif kind == ItemKind.DOI_CHUNG.value:
            n_dc += 1
            tong_dau += diacritic_error_rate(chuan, doc)
        else:                                     # cong_thuc, so
            # Đo TOKEN công thức, không phải cả dòng (§3.2). Ô mà bản người
            # KHÔNG có token công thức nào (ví dụ ô `so` chỉ mất dấu phẩy thập
            # phân) bị loại khỏi CT: tính nó vào mẫu số sẽ pha loãng chỉ số bằng
            # thứ nó không đo. Lỗi DẤU của ô đó thì vẫn được tính.
            tok_chuan = formula_tokens(chuan)
            if tok_chuan:
                n_ct += 1
                tok_doc = {normalize_formula(t) for t in formula_tokens(doc)}
                dung_ct += sum(
                    1 for t in tok_chuan
                    if normalize_formula(t) in tok_doc) / len(tok_chuan)
            tong_dau += diacritic_error_rate(chuan, doc)

    n_dau = n_ct + n_dc
    return {
        "cong_thuc": round(dung_ct / n_ct, 4) if n_ct else None,
        "loi_dau": round(tong_dau / n_dau, 4) if n_dau else None,
        "bang": round(dung_bang / n_bang, 4) if n_bang else None,
        "n_cong_thuc": n_ct,
        "n_doi_chung": n_dc,
        "n_bang": n_bang,
        "n_khong_doc_duoc": khong_doc_duoc,
        # Số ô THỰC SỰ được chấm — không phải `n_ct + n_dc + n_bang`: ô `so`
        # không có token công thức nào bị loại khỏi trục CT nhưng vẫn được chấm
        # ở trục DẤU, nên cộng ba trục lại cho mẫu số NHỎ HƠN thực tế (đo được:
        # 77 thay vì 97, khiến bảng in ra "thiếu 94/77 ô" và "trả lời -17 ô").
        "n_o_cham": o_cham,
        "n_o_thieu": o_thieu,
        "n_o_rong": o_rong,
    }


def table_cell_accuracy(gold_row: str, hyp_row: str) -> float:
    """Tỉ lệ ô đúng **cả nội dung và VỊ TRÍ cột**.

    Vị trí là bắt buộc: `Bảng 12.1` hỏng vì **trộn cột** (cột *công dụng* chảy
    vào cột *tính chất* — D-63), nên một phép đo bỏ qua vị trí sẽ không thấy
    được đúng cái bệnh mình đi tìm.
    """
    g = table_cells(gold_row)
    h = table_cells(hyp_row)
    if not g:
        return 0.0
    dung = sum(1 for i, o in enumerate(g)
               if i < len(h) and normalize_formula(o) == normalize_formula(h[i]))
    return dung / len(g)


def _giong_nhau(a: str, b: str) -> bool:
    """So sau khi chuẩn hoá khoảng trắng — khác dấu vẫn tính là KHÁC."""
    return " ".join(str(a or "").split()) == " ".join(str(b or "").split())


def score_answers(items: Sequence[dict], answers: Dict[str, str]) -> dict:
    """Đếm ô đã điền và ô ĐÁNG NGHI, rồi quyết có công bố được không.

    `cong_thuc` / `so` / `bang` vào phiếu **vì máy đã đọc sai**, nên câu trả lời
    trùng y nguyên chữ của máy là dấu hiệu không mở ảnh ra xem. `doi_chung` thì
    ngược lại: trùng là bình thường, và đó chính là điều cần đo.
    """
    # BẢNG cố ý KHÔNG nằm trong tập này: `may_doc` của ô bảng là dòng TIÊU ĐỀ,
    # còn câu trả lời là một hàng của bảng — hai thứ không so được, nên đối chiếu
    # chúng sẽ luôn cho "khác nhau" và biến phép kiểm thành vô nghĩa.
    can_doc_lai = {ItemKind.CONG_THUC.value, ItemKind.SO.value}
    tong = len(items)
    da_dien = 0
    nghi = 0
    for it in items:
        ans = answers.get(it["id"])
        if ans is None or not str(ans).strip():
            continue
        da_dien += 1
        if it.get("kind") in can_doc_lai and _giong_nhau(ans, it.get("may_doc", "")):
            nghi += 1

    ly_do = ""
    if da_dien < tong:
        ly_do = f"còn {tong - da_dien}/{tong} ô chưa điền"
    elif nghi and nghi / max(1, da_dien) >= 0.5:
        ly_do = (f"{nghi}/{da_dien} ô được gõ lại Y NGUYÊN chữ của máy trên ô đã "
                 "biết là máy đọc SAI — dấu hiệu đóng dấu cho qua")
    elif nghi:
        ly_do = (f"{nghi}/{da_dien} ô trùng y nguyên chữ của máy — xem lại đúng "
                 "những ô đó (danh sách ở dưới)")
    return {
        "tong_o": tong,
        "da_dien": da_dien,
        "nghi_dong_dau": nghi,
        "cong_bo_duoc": bool(da_dien == tong and nghi / max(1, da_dien) < 0.5),
        "ly_do": ly_do,
    }


# --- 4. Xuất phiếu ------------------------------------------------------

def load_pages() -> List[dict]:
    if not PAGES_FILE.exists():
        raise FileNotFoundError(
            f"Thiếu {PAGES_FILE}. Danh sách 15 trang phải được COMMIT để lượt "
            "sau chấm trên đúng 15 trang đó, không chọn lại.")
    return json.loads(PAGES_FILE.read_text(encoding="utf-8"))["trang"]


def _ocr_words(image_bgr) -> List[dict]:
    """Word box của Tesseract trên CẢ TRANG, `--psm 6` như đường production."""
    import pytesseract
    from src.config import TESSERACT_CMD

    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    data = pytesseract.image_to_data(
        image_bgr, lang="vie", config="--psm 6",
        output_type=pytesseract.Output.DICT)
    n = len(data["text"])
    return [{k: data[k][i] for k in
             ("text", "block_num", "par_num", "line_num", "left", "top",
              "width", "height", "conf")} for i in range(n)]


def _crop_png_b64(image_bgr, bbox, pad: int = 8, max_w: int = 1400) -> str:
    import cv2

    h, w = image_bgr.shape[:2]
    x0, y0, x1, y1 = bbox
    x0 = max(0, x0 - pad); y0 = max(0, y0 - pad)
    x1 = min(w, x1 + pad); y1 = min(h, y1 + pad)
    crop = image_bgr[y0:y1, x0:x1]
    if crop.size == 0:
        return ""
    if crop.shape[1] > max_w:
        scale = max_w / crop.shape[1]
        crop = cv2.resize(crop, (max_w, max(1, int(crop.shape[0] * scale))))
    ok, buf = cv2.imencode(".png", crop)
    return base64.b64encode(buf.tobytes()).decode("ascii") if ok else ""


_CAU_HOI = {
    ItemKind.CONG_THUC: "Gõ lại NGUYÊN DÒNG này. Chỉ số dưới gõ chỉ số dưới thật "
                        "(O₂, H₂SO₄) — đừng gõ O,",
    ItemKind.SO: "Gõ lại NGUYÊN DÒNG này, chú ý dấu phẩy thập phân (26,2 chứ "
                 "không phải 262)",
    ItemKind.DOI_CHUNG: "Gõ lại NGUYÊN DÒNG này, đúng dấu tiếng Việt",
}


def question_for(kind: ItemKind) -> str:
    """Câu hỏi hiện cho người duyệt. Không có nó thì mỗi ô được hiểu một kiểu và
    gold set không so được với nhau."""
    return _CAU_HOI.get(kind, "Gõ lại nguyên dòng này")


def table_questions() -> List[str]:
    """Hai câu cho MỘT bảng — hai bệnh khác nhau đã ghi ở D-63.

    `Bảng 35.1` mất **hàng header**; `Bảng 12.1` **trộn cột**. Một khung nhập
    duy nhất cho bảng 2 cột × 7 hàng thì không ai gõ, và cũng không tách được
    hai bệnh đó ra.
    """
    return [
        "HÀNG ĐẦU (header) của bảng: gõ các ô của hàng đó, cách nhau bằng | "
        "— ví dụ: Vật liệu | Tính chất",
        "HÀNG DỮ LIỆU ĐẦU TIÊN (ngay dưới header): gõ các ô của hàng đó, cách "
        "nhau bằng | — thứ tự cột phải đúng như trên trang",
    ]


def build_items(image_bgr, page_meta: dict, max_per_page: int = 8) -> List[dict]:
    """Các ô cần người duyệt cho MỘT trang.

    Trang `doi_chung` cố ý lấy các dòng **dài nhất** (không lọc theo bệnh): chỗ đó
    đo xem model có tệ hơn Tesseract trên **chữ thường** hay không — 93% corpus là
    chữ thường, nên một model thắng công thức mà thua chữ thường là model TỆ HƠN.
    """
    lines = group_lines(_ocr_words(image_bgr))
    la_doi_chung = page_meta.get("loai") == "doi_chung"
    chon: List[Tuple[ItemKind, dict]] = []
    if la_doi_chung:
        dai = sorted(lines, key=lambda l: -len(l["text"]))
        chon = [(ItemKind.DOI_CHUNG, l) for l in dai[:max_per_page]]
    else:
        for l in lines:
            kind = classify_line(l["text"])
            if kind is not None:
                chon.append((kind, l))
        # Ưu tiên công thức, rồi bảng, rồi số — cắt còn `max_per_page`.
        uu_tien = {ItemKind.CONG_THUC: 0, ItemKind.BANG: 1, ItemKind.SO: 2}
        chon.sort(key=lambda p: (uu_tien.get(p[0], 9), -len(p[1]["text"])))
        chon = chon[:max_per_page]

    page_h, page_w = image_bgr.shape[:2]
    out: List[dict] = []
    for i, (kind, line) in enumerate(chon, 1):
        # Ô loại BẢNG phải là một DẢI chứa cả bảng, không phải dòng tiêu đề: gõ
        # lại một dòng tiêu đề không đo được gì về quan hệ hàng/cột (D-63). Và
        # một dải sinh HAI ô, vì header-mất và cột-bị-trộn là hai bệnh khác nhau.
        vung_text = None
        if kind is ItemKind.BANG:
            bbox = table_band_bbox(line["bbox"], page_w, page_h)
            cau_hoi_list = table_questions()
            # OCR CẢ DẢI bảng — đây mới là baseline Tesseract cho ô bảng. Dùng
            # dòng tiêu đề làm baseline sẽ cho BẢNG = 0 giả (xem
            # `baseline_reading`).
            x0, y0, x1, y1 = bbox
            vung = image_bgr[y0:y1, x0:x1]
            vung_text = " ".join(
                l["text"] for l in group_lines(_ocr_words(vung))) if vung.size                 else ""
        else:
            bbox = line["bbox"]
            cau_hoi_list = [question_for(kind)]
        anh = _crop_png_b64(image_bgr, bbox, max_w=1000)
        for j, cau_hoi in enumerate(cau_hoi_list, 1):
            hau_to = f"_{j}" if len(cau_hoi_list) > 1 else ""
            out.append({
                "id": f"{page_meta['quyen']}_p{page_meta['trang']}_{i:02d}{hau_to}",
                "quyen": page_meta["quyen"],
                "trang": page_meta["trang"],
                "kind": kind.value,
                "cau_hoi": cau_hoi,
                # `may_doc` của ô bảng là dòng TIÊU ĐỀ, không phải nội dung bảng —
                # nên phép kiểm "gõ lại y nguyên chữ máy" không áp cho ô bảng.
                "may_doc": line["text"],
                "conf": line["conf"],
                "bbox": list(bbox),
                "anh_b64": anh,
                **({"may_doc_vung": vung_text} if vung_text is not None else {}),
            })
    return out


HUONG_DAN = """
<h2>Bạn cần làm gì — đọc 60 giây rồi bắt đầu</h2>
<ol>
<li><b>Mỗi ô là MỘT DÒNG được cắt ra từ trang sách thật.</b> Nhìn ảnh, rồi gõ lại
    <b>đúng những gì bạn THẤY</b> vào khung bên dưới nó.</li>
<li><b>Tôi cố ý KHÔNG hiện chữ máy đọc được</b> ở khung trả lời. Nếu hiện thì
    ai cũng sẽ sửa vài chữ rồi bấm xong — chuyện đó đã xảy ra thật ở repo này
    (23/24 file gold cũ trùng <i>từng chữ</i> với output của máy).</li>
<li><b>Chỉ số dưới thì gõ chỉ số dưới thật:</b> <code>O₂</code>,
    <code>H₂SO₄</code>, <code>CO₂</code>, <code>Fe₂O₃</code>. Có nút chèn nhanh
    <code>₀₁₂₃₄₅₆₇₈₉</code> ở đầu trang. Gõ <code>O2</code> cũng được — tôi chuẩn
    hoá khi chấm — nhưng <b>đừng</b> gõ <code>O,</code>.</li>
<li><b>Dấu tiếng Việt phải đúng.</b> Đây là chỉ số quyết định: một model đọc giỏi
    công thức mà sai dấu thì bị loại.</li>
<li><b>Ô loại BẢNG:</b> gõ các ô trên cùng một hàng, phân cách bằng dấu
    <code>|</code>. Ví dụ: <code>Vật liệu | Tính chất | Công dụng</code>. Thứ tự
    cột phải đúng như trên trang — đó chính là thứ hiện đang bị mất.</li>
<li><b>Ô loại ĐỐI CHỨNG</b> là chữ thường, máy có thể đã đọc đúng. Vẫn gõ lại
    bình thường; trùng với máy là chuyện tốt và tôi <b>không</b> tính đó là lỗi.</li>
<li><b>Không đọc được thật</b> (ảnh mờ, chữ bị hình che): gõ đúng ba dấu hỏi
    <code>???</code>. Đó là câu trả lời hợp lệ và có giá trị — nó nói rằng chỗ đó
    không ai đọc được, kể cả người.</li>
<li>Xong thì bấm <b>Tải phiếu JSON</b> ở cuối trang, lưu vào
    <code>database/review/ocr_gold/phieu_nguoi.json</code>.</li>
</ol>
<p class="canh-bao"><b>Một điều tôi nói trước cho công bằng:</b> những ô loại
CÔNG THỨC / SỐ / BẢNG có mặt ở đây <b>vì máy đã đọc sai chúng</b>. Nếu câu trả
lời gõ vào trùng y nguyên chữ máy đọc, phần chấm sẽ đếm đó là dấu hiệu
"không mở ảnh ra xem" và <b>từ chối công bố kết quả</b>. Tôi kiểm điều này
tự động, và nói ra trước vì cái cần kiểm là bạn có nhìn ảnh không — không phải
bẫy bạn.</p>
<p>Ước lượng: <b>35–50 phút</b> cho toàn bộ phiếu. Trang tự lưu nháp vào bộ nhớ
trình duyệt, đóng tab rồi mở lại vẫn còn.</p>
"""

_CSS = """
:root{--bg:#fff;--fg:#111;--line:#d0d0d0;--accent:#0b5fff;--warn:#8a3b00;
       --warn-bg:#fff4e5;--card:#fafafa}
@media (prefers-color-scheme:dark){:root{--bg:#131313;--fg:#eee;--line:#3a3a3a;
       --accent:#7aa2ff;--warn:#ffcf9e;--warn-bg:#33240f;--card:#1c1c1c}}
body{background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,sans-serif;
     margin:0 auto;max-width:1080px;padding:24px}
h1{font-size:26px;margin:0 0 4px} h2{font-size:19px;margin:28px 0 8px}
code{background:var(--card);padding:1px 5px;border-radius:4px;font-size:.92em}
.canh-bao{background:var(--warn-bg);color:var(--warn);border-left:4px solid
     currentColor;padding:10px 14px;border-radius:4px}
.item{border:1px solid var(--line);border-radius:8px;padding:12px;margin:14px 0;
     background:var(--card)}
.item img{max-width:100%;display:block;background:#fff;border:1px solid var(--line);
     border-radius:4px}
.meta{font-size:13px;opacity:.75;margin-bottom:6px}
.cau-hoi{font-size:14px;font-weight:600;margin-top:9px}
.kind{display:inline-block;font-size:12px;font-weight:700;padding:2px 8px;
     border-radius:99px;border:1px solid currentColor;margin-right:8px}
.k-cong_thuc{color:#b5006b} .k-bang{color:#0a6b3d} .k-so{color:#8a5a00}
.k-doi_chung{color:#4a4a8a}
input[type=text]{width:100%;font:15px/1.4 ui-monospace,monospace;padding:9px;
     margin-top:8px;border:1px solid var(--line);border-radius:6px;
     background:var(--bg);color:var(--fg)}
input[type=text]:focus{outline:2px solid var(--accent);border-color:var(--accent)}
.sub{position:sticky;bottom:0;background:var(--bg);border-top:1px solid var(--line);
     padding:12px 0;margin-top:24px}
button{font:15px system-ui;padding:9px 16px;border-radius:6px;cursor:pointer;
     border:1px solid var(--line);background:var(--card);color:var(--fg)}
button.chinh{background:var(--accent);color:#fff;border-color:var(--accent)}
.sub-b{display:inline-block;margin-right:6px}
#tiendo{font-weight:700}
"""

_JS = """
const KEY='ocr_gold_v1';
function o(){return document.querySelectorAll('input[data-id]')}
function luu(){const d={};o().forEach(i=>{if(i.value.trim())d[i.dataset.id]=i.value});
  try{localStorage.setItem(KEY,JSON.stringify(d))}catch(e){}
  const n=Object.keys(d).length;
  document.getElementById('tiendo').textContent=n+'/'+o().length;}
function nap(){try{const d=JSON.parse(localStorage.getItem(KEY)||'{}');
  o().forEach(i=>{if(d[i.dataset.id])i.value=d[i.dataset.id]});}catch(e){}luu();}
function tai(){const d={_bat_dau:window.__t0,_ket_thuc:Date.now(),traloi:{}};
  o().forEach(i=>{if(i.value.trim())d.traloi[i.dataset.id]=i.value});
  const b=new Blob([JSON.stringify(d,null,1)],{type:'application/json'});
  const a=document.createElement('a');a.href=URL.createObjectURL(b);
  a.download='phieu_nguoi.json';a.click();}
function chen(c){const e=document.activeElement;
  if(e&&e.tagName==='INPUT'){const s=e.selectionStart;
    e.value=e.value.slice(0,s)+c+e.value.slice(e.selectionEnd);
    e.selectionStart=e.selectionEnd=s+c.length;e.focus();luu();}}
window.addEventListener('DOMContentLoaded',()=>{window.__t0=Date.now();nap();
  document.addEventListener('input',e=>{if(e.target.dataset.id)luu()});});
"""


def export_html(items: Sequence[dict], out_dir: Path) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    sub = "".join(
        f'<button class="sub-b" onclick="chen(\'{c}\')">{c}</button>'
        for c in "₀₁₂₃₄₅₆₇₈₉")
    khoi = []
    for i, it in enumerate(items, 1):
        img = (f'<img alt="dòng cần đọc" src="data:image/png;base64,'
               f'{it["anh_b64"]}">' if it["anh_b64"] else
               "<i>(không cắt được ảnh)</i>")
        khoi.append(
            f'<div class="item"><div class="meta">'
            f'<span class="kind k-{it["kind"]}">{it["kind"]}</span>'
            f'#{i}/{len(items)} · {html.escape(it["quyen"])} · trang '
            f'{it["trang"]} · máy tự tin {it["conf"]}</div>{img}'
            f'<div class="cau-hoi">'
            f'{html.escape(it.get("cau_hoi", "Gõ lại nguyên dòng này"))}</div>'
            f'<input type="text" data-id="{html.escape(it["id"])}" '
            f'placeholder="Gõ lại đúng những gì bạn THẤY trên ảnh…" '
            f'autocomplete="off" spellcheck="false"></div>')
    doc = (f"<!doctype html><html lang=vi><head><meta charset=utf-8>"
           f"<meta name=viewport content='width=device-width,initial-scale=1'>"
           f"<title>Phiếu duyệt OCR — {len(items)} ô</title>"
           f"<style>{_CSS}</style><script>{_JS}</script></head><body>"
           f"<h1>Phiếu duyệt OCR — {len(items)} ô / 15 trang</h1>"
           f"{HUONG_DAN}"
           f"<h2>Chèn nhanh chỉ số dưới</h2><div>{sub}</div>"
           f"<h2>Các ô cần duyệt</h2>{''.join(khoi)}"
           f"<div class=sub>Đã điền <span id=tiendo>0/0</span> · "
           f"<button class=chinh onclick=tai()>Tải phiếu JSON</button></div>"
           f"</body></html>")
    p_html = out_dir / "phieu.html"
    p_html.write_text(doc, encoding="utf-8")
    p_items = out_dir / "items.json"
    p_items.write_text(json.dumps(
        [{k: v for k, v in it.items() if k != "anh_b64"} for it in items],
        ensure_ascii=False, indent=1), encoding="utf-8")
    return p_html, p_items


def cmd_export(out_dir: Path, max_per_page: int) -> int:
    from src.config import DATA_DIR
    from src.etl.page_source import find_page_source

    trang = load_pages()
    tat_ca: List[dict] = []
    t0 = time.time()
    for i, pm in enumerate(trang, 1):
        source = find_page_source(DATA_DIR, pm["quyen"])
        # `trang` trong danh sách là số trang IN. Trên corpus này offset = 0 ở
        # 12/12 quyển (D-65) nên nó cũng là số trong tên file; vẫn kiểm để không
        # âm thầm cắt sai trang.
        so_file = int(pm["trang"])
        if so_file not in set(source.page_numbers()):
            raise RuntimeError(
                f"{pm['quyen']} không có trang {so_file} trên đĩa — danh sách 15 "
                "trang và corpus không khớp, KHÔNG đoán trang khác.")
        img = source.load(so_file)
        items = build_items(img, pm, max_per_page=max_per_page)
        print(f"[{i:2d}/15] {pm['quyen']:18s} tr.{pm['trang']:>3} "
              f"{pm['loai']:10s} -> {len(items):2d} ô", flush=True)
        tat_ca.extend(items)
    p_html, p_items = export_html(tat_ca, out_dir)
    n_crop = dump_crops(tat_ca, out_dir / "crops")
    print(f"\n{len(tat_ca)} ô / {len(trang)} trang trong {time.time() - t0:.0f}s")
    print(f"Mở phiếu:       {p_html}")
    print(f"Danh sách ô:    {p_items}")
    print(f"Crop cho Colab: {out_dir / 'crops'} ({n_crop} PNG + crops.json) — "
          f"mang ĐÚNG thư mục này lên Drive, không cần chép corpus 4,1 GB")
    return 0


def cmd_score(out_dir: Path) -> int:
    p_items = out_dir / "items.json"
    p_ans = out_dir / "phieu_nguoi.json"
    if not p_items.exists():
        print(f"Chưa có {p_items} — chạy --export trước.")
        return 1
    if not p_ans.exists():
        print(f"Chưa có {p_ans}. Mở phieu.html, điền, bấm 'Tải phiếu JSON', "
              f"rồi lưu file vào đúng đường dẫn đó.")
        return 1
    items = json.loads(p_items.read_text(encoding="utf-8"))
    raw = json.loads(p_ans.read_text(encoding="utf-8"))
    answers = raw.get("traloi", raw)
    kq = score_answers(items, answers)

    giay = None
    if raw.get("_bat_dau") and raw.get("_ket_thuc"):
        giay = (int(raw["_ket_thuc"]) - int(raw["_bat_dau"])) / 1000.0

    print(f"Phiếu: {p_ans}")
    print(f"  ô đã điền     {kq['da_dien']}/{kq['tong_o']}")
    print(f"  ô đáng nghi   {kq['nghi_dong_dau']}  (gõ lại y nguyên chữ máy trên "
          f"ô đã biết máy đọc SAI)")
    if giay is not None:
        moi_o = giay / max(1, kq["da_dien"])
        print(f"  thời gian     {giay / 60:.1f} phút = {moi_o:.1f} s/ô")
        if moi_o < 5:
            print("  !! DƯỚI 5 s/ô — quá nhanh để đọc một dòng ảnh rồi gõ lại. "
                  "Bài học D-90: dấu hiệu này CHẶN việc công bố.")
            kq["cong_bo_duoc"] = False
            kq["ly_do"] = (kq["ly_do"] + "; " if kq["ly_do"] else "") + \
                f"{moi_o:.1f} s/ô là quá nhanh"
    else:
        print("  thời gian     không có dấu thời gian trong phiếu")

    if kq["nghi_dong_dau"]:
        print("\n  Những ô trùng y nguyên chữ máy (xem lại đúng các ô này):")
        for it in items:
            a = answers.get(it["id"])
            if (a and it["kind"] != ItemKind.DOI_CHUNG.value
                    and _giong_nhau(a, it.get("may_doc", ""))):
                print(f"    {it['id']}  {it['may_doc'][:70]!r}")

    if kq["cong_bo_duoc"]:
        dest = archive_human_sheet(p_ans)
        print("\n  => Phiếu DÙNG ĐƯỢC làm gold set.")
        print(f"  Đã chép vào {dest} (thư mục NẰM TRONG GIT) — "
              "`database/` bị gitignore nên phiếu chỉ sống ở đó là phiếu sẽ mất.")
        print("  HÃY COMMIT file đó: nó là công người, không dựng lại được.")
        print("  Bước tiếp: chạy các engine trên 97 crop rồi `--compare`.")
    else:
        print(f"\n  => CHƯA công bố được: {kq['ly_do']}")
    return 0 if kq["cong_bo_duoc"] else 2


ARCHIVE_DIR = Path("document/review/ocr_gold")


def archive_human_sheet(src: Path, kho: Path = ARCHIVE_DIR) -> Path:
    """Chép phiếu người duyệt vào thư mục NẰM TRONG GIT.

    `database/` bị `.gitignore` bỏ qua (D-68), nên một phiếu chỉ sống ở đó là
    một phiếu sẽ mất — mà đây là **công người, không dựng lại được** (ước lượng
    35–50 phút). Tiền lệ: `document/review/testset_review_50.csv` nằm trong git.

    **Không bao giờ ghi đè im lặng** một phiếu đã có: ghi đè là xoá công người
    mà không ai biết. Phiếu thứ hai được lưu thành tên khác, và hai phiếu độc
    lập chính là cách phân giải nghi ngờ ở D-90.
    """
    kho.mkdir(parents=True, exist_ok=True)
    dest = kho / "phieu_nguoi.json"
    if dest.exists():
        i = 2
        while (kho / f"phieu_nguoi_{i}.json").exists():
            i += 1
        dest = kho / f"phieu_nguoi_{i}.json"
    dest.write_bytes(Path(src).read_bytes())
    return dest


def baseline_reading(items: Sequence[dict]) -> Dict[str, str]:
    """Chữ Tesseract đọc được, dùng làm BASELINE — mốc để mọi engine so vào.

    Ô bảng phải lấy `may_doc_vung` (OCR **cả dải bảng**), không phải `may_doc`
    (dòng **tiêu đề**, vốn chỉ là anchor để tìm bảng). Lượt baseline đầu tiên đã
    dùng nhầm `may_doc` và cho ra `BẢNG = 0.000` — một con số trông như kết quả
    nhưng thật ra nói về cách dựng phiếu, không nói gì về Tesseract.

    Thiếu `may_doc_vung` thì **raise**: lặng lẽ lùi về dòng tiêu đề sẽ tái lập
    đúng con số 0 giả đó (nguyên tắc 5).
    """
    out: Dict[str, str] = {}
    for it in items:
        if it.get("kind") == ItemKind.BANG.value:
            if "may_doc_vung" not in it:
                raise RuntimeError(
                    f"Ô bảng {it['id']} thiếu `may_doc_vung` (OCR cả dải). Phiếu "
                    "này dựng trước bản vá — chạy lại `--export`. Dùng dòng tiêu "
                    "đề thay thế sẽ cho BẢNG = 0 GIẢ.")
            out[it["id"]] = it["may_doc_vung"]
        else:
            out[it["id"]] = it.get("may_doc", "")
    return out


def dump_crops(items: Sequence[dict], out_dir: Path) -> int:
    """Xuất crop PNG + `crops.json` để mang lên Colab.

    Engine chạy trên GPU Colab, mà PNG nguồn là **4,1 GB không nằm trong git**
    (D-68) — chép cả corpus lên Drive cho 15 trang là lãng phí. 97 crop chỉ vài
    MB, và **đó cũng chính là thứ người duyệt nhìn**, nên engine và người chấm
    trên cùng một mẩu pixel. Không có điều đó thì không so được: engine đọc cả
    trang rồi ta đi tìm dòng nào khớp nhất với đáp án người là **tự chọn kết quả
    tốt nhất cho engine**, một phép đo thiên vị.

    Ô loại BẢNG có crop là cả DẢI bảng, nên engine vẫn phải làm đúng việc khó
    (giữ quan hệ hàng/cột) chứ không được đọc từng dòng rời.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    man = []
    for it in items:
        b64 = it.get("anh_b64") or ""
        if not b64:
            raise RuntimeError(
                f"Ô {it['id']} không có ảnh — engine sẽ không có gì để đọc và ô "
                "đó sẽ bị chấm là SAI oan. Dựng lại phiếu bằng --export.")
        (out_dir / f"{it['id']}.png").write_bytes(base64.b64decode(b64))
        man.append({k: v for k, v in it.items() if k != "anh_b64"}
                   | {"file": f"{it['id']}.png"})
    (out_dir / "crops.json").write_text(
        json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(man)


def cmd_compare(out_dir: Path) -> int:
    """Bảng so các engine trên gold set người duyệt.

    Đọc `engine_*.json` — mỗi file là `{"<id ô>": "<chữ engine đọc được>"}` do
    lượt chạy trên Colab sinh ra.
    """
    p_items = out_dir / "items.json"
    p_gold = out_dir / "phieu_nguoi.json"
    if not (p_items.exists() and p_gold.exists()):
        print(f"Cần cả {p_items} và {p_gold}. Chạy --export rồi --score trước.")
        return 1
    items = json.loads(p_items.read_text(encoding="utf-8"))
    raw = json.loads(p_gold.read_text(encoding="utf-8"))
    gold = raw.get("traloi", raw)

    kq_phieu = score_answers(items, gold)
    if not kq_phieu["cong_bo_duoc"]:
        # Bài học D-90: phiếu đáng nghi phải CHẶN việc công bố, không phải đi
        # kèm nó dưới dạng chú thích.
        print(f"!! Phiếu người CHƯA dùng được làm gold set: {kq_phieu['ly_do']}")
        print("   Chạy `--score` để xem chi tiết. KHÔNG in bảng so engine.")
        return 2

    # Baseline Tesseract KHÔNG cần file engine nào: `may_doc` đã nằm trong
    # items.json. Đó là con số "hiện tại đang tệ đến mức nào", tức MỐC để mọi
    # engine so vào — bắt chạy 4 model trên Colab rồi mới biết mốc là ngược
    # thứ tự làm việc.
    files = sorted(out_dir.glob("engine_*.json"))
    if not files:
        print("(chưa có engine_*.json nào — in BASELINE Tesseract để có mốc)")

    print(f"Gold set: {kq_phieu['da_dien']}/{kq_phieu['tong_o']} ô người duyệt")
    tesseract = baseline_reading(items)
    bang = [("tesseract (hiện tại)", score_engine(items, gold, tesseract))]
    for f in files:
        ten = f.stem.replace("engine_", "")
        bang.append((ten, score_engine(items, gold,
                                       json.loads(f.read_text(encoding="utf-8")))))

    def o(v):
        return "  —  " if v is None else f"{v:5.3f}"

    # Engine chưa chạy đủ ô thì KHÔNG in số. Bài học D-90: một mẫu đáng nghi
    # phải CHẶN việc công bố, không phải đi kèm nó dưới dạng chú thích. Đo được
    # vì sao: với 94/97 ô thiếu, `score_engine` cho CT 0,000 / DẤU **0,000** /
    # BẢNG 0,000 — mà DẤU 0,000 là điểm HOÀN HẢO ở đúng cột quyết định
    # thắng/thua (một từ mất hẳn không phải "lỗi dấu"), nên bảng đó nói NGƯỢC
    # sự thật chứ không chỉ nói thiếu.
    def chua_du(st):
        return st["n_o_thieu"] > 0

    head = f"{'engine':28s} {'CT↑':>6s} {'DẤU↓':>6s} {'BẢNG↑':>6s}   n"
    print(f"\n{head}\n{'-' * len(head)}")
    for ten, st in bang:
        if chua_du(st):
            print(f"{ten:28s} {'  —  ':>5s} {'  —  ':>5s} {'  —  ':>5s}"
                  f"   CHƯA ĐỦ: thiếu {st['n_o_thieu']}/{st['n_o_cham']} ô")
            continue
        print(f"{ten:28s} {o(st['cong_thuc'])} {o(st['loi_dau'])} {o(st['bang'])}"
              f"   ct={st['n_cong_thuc']} dc={st['n_doi_chung']} b={st['n_bang']}"
              + (f"  ({st['n_o_rong']} ô rỗng)" if st["n_o_rong"] else ""))

    for ten, st in bang[1:]:
        if chua_du(st):
            print(f"\n!! {ten}: mới trả lời {st['n_o_cham'] - st['n_o_thieu']}"
                  f"/{st['n_o_cham']} ô -> CHƯA SO ĐƯỢC, không in số.")
            print("   Bỏ `--limit` (bỏ comment khối dưới trong cell notebook) "
                  "để chạy đủ; script tự nối tiếp phần đã chạy.")

    goc = bang[0][1]
    print("\nLuật chốt (thiết kế §3.2): một engine chỉ THẮNG khi nó **không tệ "
          "hơn**\nTesseract ở cột DẤU. Thắng công thức mà thua dấu là THUA — "
          "93% corpus\nlà chữ thường.")
    if goc["loi_dau"] is not None:
        for ten, st in bang[1:]:
            # Không áp luật chốt cho engine chưa chạy đủ: số của nó không tồn tại.
            if st["loi_dau"] is None or chua_du(st):
                continue
            if st["loi_dau"] > goc["loi_dau"]:
                print(f"  ✗ {ten}: lỗi dấu {st['loi_dau']:.3f} > tesseract "
                      f"{goc['loi_dau']:.3f} -> LOẠI")
    if goc["n_khong_doc_duoc"]:
        print(f"\n{goc['n_khong_doc_duoc']} ô người ghi `???` (không ai đọc "
              "được) -> loại khỏi mọi trục, không tính cho ai cả.")

    p_csv = out_dir / "bakeoff.csv"
    with io.open(p_csv, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["engine"] + list(bang[0][1].keys()))
        w.writeheader()
        for ten, st in bang:
            w.writerow({"engine": ten, **st})
    print(f"\nĐã lưu: {p_csv}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--export", action="store_true",
                    help="Dựng phiếu duyệt HTML từ 15 trang trong "
                         "ocr_bakeoff_pages.json")
    ap.add_argument("--score", action="store_true",
                    help="Đọc phiếu người đã điền, kiểm dấu hiệu đóng dấu cho qua")
    ap.add_argument("--compare", action="store_true",
                    help="Bảng so các engine (engine_*.json) trên gold set người "
                         "duyệt. Từ chối in bảng nếu phiếu chưa dùng được.")
    # Mặc định là thư mục NẰM TRONG GIT, không phải `database/` (bị gitignore).
    # Nhờ vậy Colab chỉ cần `git clone` là có đủ crop + phiếu người + baseline —
    # không phải upload gì lên Drive, không phải nhớ đường dẫn nào. Toàn bộ
    # bake-off gói gọn 8,2 MB, và nó đi cùng lịch sử của chính phép đo.
    ap.add_argument("--out-dir", default="document/review/ocr_gold")
    ap.add_argument("--max-per-page", type=int, default=8)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    if args.export:
        return cmd_export(out_dir, args.max_per_page)
    if args.score:
        return cmd_score(out_dir)
    if args.compare:
        return cmd_compare(out_dir)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
