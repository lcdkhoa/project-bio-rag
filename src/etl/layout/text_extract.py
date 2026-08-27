"""OCR từng vùng layout riêng, theo thứ tự đọc.

`--psm` phải chỉ định TƯỜNG MINH. Đo trên 14 trang thật (spec §1.2): psm mặc
định (3, "auto page segmentation") trên các crop nhỏ cho 6293 token, `--psm 6`
("uniform block of text") cho 6535 token — **+3,8% chữ, cùng thời gian**. psm 3
tự đi tìm layout *bên trong* một crop mà bản thân crop đã LÀ một vùng layout, và
khi đoán sai nó im lặng bỏ chữ. Crop cao dưới `SINGLE_LINE_MAX_H` px gần như
luôn là một dòng (caption, nhãn hộp) -> `--psm 7`.

Không upscale: đo được là CER thân bài không đổi ở 1×/2×/3×/4× trong khi `psm 6`
+ upscale 2× chỉ thêm 0,3% token với +70% thời gian (spec §1.2, CẤM #2).
"""
import unicodedata

import numpy as np
import pytesseract
from .formula_gate import is_formula_suspect
from .formula_merge import apply_line_merge_to_region, merge_formula_line
from .formula_ocr import get_formula_client
from .ocr_lines import image_to_lines
from .pill import bounds_for_width, read_pill_labels
from .regions import Region, RegionType, TextUnit
from ..cleaner import clean_vietnamese_text
from ..diacritic import diacritic_review_flags
from ...config import DIACRITIC_REVIEW_ENABLED, FORMULA_HYBRID_ENABLED, TESSERACT_CMD

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

# Chiều cao box chữ thân bài đo được là 19 px (p10 16, p90 20) -> 60 px là "một
# dòng cộng lề", đủ rộng để không nhận nhầm khối hai dòng thành dòng đơn.
SINGLE_LINE_MAX_H = 60


def _psm_for(crop: np.ndarray) -> int:
    return 7 if crop.shape[0] < SINGLE_LINE_MAX_H else 6


def _ocr(img: np.ndarray) -> str:
    raw = pytesseract.image_to_string(
        img, lang="vie", config=f"--psm {_psm_for(img)}")
    return clean_vietnamese_text(raw)

def _fold(text: str) -> str:
    """Bỏ dấu + hạ chữ thường, để so "đã có chưa" mà không bị lệch vì dấu OCR."""
    stripped = unicodedata.normalize("NFD", text.lower())
    return " ".join("".join(c for c in stripped
                            if unicodedata.category(c) != "Mn").split())


def _pill_text_missing_from(crop: np.ndarray, text: str,
                            bounds: dict | None = None) -> list[str]:
    """Chữ trên các pill trong `crop` mà `text` (OCR thường) chưa có.

    Nhãn chữ trắng trên nền màu ("Thông tin liên lạc", "Sản xuất") là loại chữ
    bị mất trọn vẹn — thêm lại thì hơn là để trống, nhưng chỉ thêm cái CHƯA có,
    để không nhân đôi những pill mà OCR thường tình cờ đọc được.

    `bounds` phải suy từ chiều rộng **TRANG**, không phải của `crop`: một pill có
    kích thước tỉ lệ với trang, còn crop thì hẹp hơn tuỳ vùng. Để mặc định thì
    `pill.bounds_for_width(crop_width)` sẽ tính ra ngưỡng của một trang nhỏ hơn
    thực tế và **loại oan pill rộng của CD/CTST** (`max_w` bị co lại).
    """
    seen = _fold(text)
    out = []
    for item in read_pill_labels(crop, bounds):
        pill_text = item["figure_label"] or item["text"]
        folded = _fold(pill_text)
        if folded and folded not in seen:
            out.append((item["bbox"][1], pill_text))
            seen += " " + folded
    return [text for _y, text in sorted(out)]


def _mask_out(img: np.ndarray, boxes) -> np.ndarray:
    out = img.copy()
    for (x0, y0, x1, y1) in boxes:
        out[y0:y1, x0:x1] = 255
    return out


def _maybe_apply_formula_hybrid(crop, text, formula_client):
    """Neu `text` (da OCR xong bang duong chinh) bi gate nghi cong thuc: goi
    them `image_to_data` (side-computation, chi khi can) de tim DONG chua lo
    hong, crop rieng dong do, goi MinerU, ghep TOKEN vao dung vi tri.

    KHONG doi `text` neu khong co gi de ghep — tra ve nguyen ban + list trang
    thai rong. Xem thiet ke: document/specs/2026-08-27-formula-ocr-hybrid-buoc23-design.md §2.
    """
    if not is_formula_suspect(text):
        return text, []

    h, w = crop.shape[:2]
    psm = _psm_for(crop)
    lines = image_to_lines(crop, psm)

    statuses: list[str] = []
    new_text = text
    found_candidate_line = False
    for line in lines:
        line_text = line["text"]
        if not is_formula_suspect(line_text):
            continue
        found_candidate_line = True
        x0, y0, x1, y1 = line["bbox"]
        pad = 8
        cx0, cy0 = max(0, x0 - pad), max(0, y0 - pad)
        cx1, cy1 = min(w, x1 + pad), min(h, y1 + pad)
        line_crop = crop[cy0:cy1, cx0:cx1]
        if line_crop.size == 0:
            continue
        mineru_text = formula_client.read(line_crop, kind="text")
        outcome = merge_formula_line(line_text, mineru_text)
        if outcome.status == "not_suspect":
            continue
        statuses.append(outcome.status)
        if outcome.n_applied > 0:
            new_text, splice_status = apply_line_merge_to_region(
                new_text, line_text, outcome.text)
            statuses.append(splice_status)

    if not found_candidate_line:
        statuses.append("gate_hit_no_line_located")
    return new_text, statuses


def extract_text_units(image: np.ndarray, regions: list[Region], variant: str,
                        formula_client=None) -> list[TextUnit]:
    units: list[TextUnit] = []
    # Ngưỡng pill tính MỘT LẦN theo chiều rộng TRANG, rồi truyền xuống từng crop
    # (xem `_pill_text_missing_from`).
    pill_bounds = bounds_for_width(image.shape[1])
    client = formula_client
    if client is None and FORMULA_HYBRID_ENABLED:
        client = get_formula_client()
    for r in sorted(regions, key=lambda z: z.reading_order):
        if r.type in (RegionType.FIGURE, RegionType.PAGE_ARTIFACT):
            continue
        x0, y0, x1, y1 = r.bbox
        crop = image[y0:y1, x0:x1]
        if crop.size == 0:
            continue
        if r.type == RegionType.BODY:
            crop = _mask_out(crop, r.meta.get("excludes", []))
        text = _ocr(crop)
        pills = _pill_text_missing_from(crop, text, pill_bounds)
        if pills:
            # Nối vào cuối, theo thứ tự trên->dưới. Thứ tự đọc không hoàn hảo,
            # nhưng CÓ chữ thì hơn là MẤT chữ (nguyên tắc 5).
            text = (text + "\n" + "\n".join(pills)).strip()
        formula_statuses: list[str] = []
        if client is not None and text:
            text, formula_statuses = _maybe_apply_formula_hybrid(
                crop, text, client)
        if text and len(text) > 5:
            # Không sửa ký tự nào: chỉ ghi lại token đáng ngờ để người xem
            # (nguyên tắc 5 — bước sửa tự động phải là flag-for-review).
            flags = diacritic_review_flags(text) if DIACRITIC_REVIEW_ENABLED else []
            units.append(TextUnit(r.type, text, r.reading_order, r.bbox,
                                  review_flags=flags,
                                  formula_hybrid_status=formula_statuses))
    return units
