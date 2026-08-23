"""M0 §2.4 — ĐO cách từng quyển ghi NHÃN HÌNH (`pill_pattern`).

## Câu hỏi phép đo này trả lời

KNTT ghi nhãn `Hình N.M` bằng **pill: chữ trắng trên nền màu đặc**, đọc được chỉ
nhờ `layout/pill.py` (khoanh pill -> đảo màu -> OCR). CD/CTST **chưa biết dùng
kiểu gì**: pill, hay caption chữ đen dưới hình, hay cả hai. Câu trả lời quyết
định phía crop hình có anchor hay không — mất anchor là mất cả G4.

Nên đo HAI kênh độc lập trên cùng một trang, rồi đối chiếu:

* **kênh pill** — `pill.find_pill_boxes` + OCR bản đảo màu, tự kiểm bằng regex
  `Hình N.M`. Ngưỡng kích thước pill phải theo TỈ LỆ trang
  (`pill.bounds_for_width`): `MAX_W = 460 px` đo trên KNTT 1094 px sẽ **loại sạch
  mọi pill của CD/CTST** vì ở 2280–2480 px chúng rộng gấp hơn hai lần. Bộ ngưỡng
  thực dùng được ghi ra, để một kết quả 0 pill không bị đọc thành "quyển này
  không dùng pill".
* **kênh OCR thường** — `image_to_data --psm 6` cả trang, rồi khớp các mẫu chú
  thích trên chuỗi từ. Ghi cả **vị trí y đã chuẩn hoá** của mỗi nhãn: nhãn dưới
  hình và nhãn trong pill nằm ở phân bố y khác nhau, và đây là bằng chứng phân
  biệt "caption dưới hình" với "nhãn nằm trong hình".

## Không kết luận thay người

`ket_luan` chỉ là nhãn dán suy từ hai con số đếm được, và cả hai con số đều nằm
trong JSON để kiểm lại. Không có nhánh nào tự "sửa" một nhãn đọc sai: pill đọc ra
rác thì bị regex loại (CẤM #5).
"""

from __future__ import annotations

import re
import time

from ..layout import pill as P

# Các mẫu chú thích hình/bảng có thể gặp. Đo bằng cách ĐẾM mẫu nào khớp, không
# chọn trước một mẫu rồi coi nó là chuẩn.
CAPTION_PATTERNS = {
    "hinh_n_m":  re.compile(r"H[ìiíỉĩị]nh\s*(\d{1,2})\s*[.,]\s*(\d{1,2})"),
    "hinh_n":    re.compile(r"H[ìiíỉĩị]nh\s*(\d{1,3})(?!\s*[.,]\s*\d)"),
    "h_dot_n_m": re.compile(r"\bH\s*\.\s*(\d{1,2})\s*[.,]\s*(\d{1,2})"),
    "bang_n_m":  re.compile(r"B[ảaá]ng\s*(\d{1,2})\s*[.,]\s*(\d{1,2})"),
}

def _page_words(image) -> list:
    """`[{text, cx, cy, conf}]` — mọi từ OCR được trên trang, toạ độ chuẩn hoá.

    `--psm 6` vì đó là psm đã đo tốt nhất cho thân bài trên nguồn này (psm 3 mất
    3,8% token). KHÔNG upscale: CẤM #1 — nhãn hình là chữ thường, không phải crop
    số trang.
    """
    import pytesseract
    height, width = image.shape[:2]
    data = pytesseract.image_to_data(image, lang="vie", config="--psm 6",
                                     output_type=pytesseract.Output.DICT)
    out = []
    for txt, conf, left, top, w, h in zip(
            data["text"], data["conf"], data["left"], data["top"],
            data["width"], data["height"]):
        txt = (txt or "").strip()
        if not txt:
            continue
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = -1.0
        out.append({"text": txt, "conf": conf,
                    "cx": round((left + w / 2) / width, 4),
                    "cy": round((top + h / 2) / height, 4)})
    return out


def caption_hits(words: list) -> list:
    """Nhãn khớp mẫu chú thích, kèm vị trí. Ghép tối đa 3 từ liền nhau.

    Phải ghép: Tesseract tách `Hình 1.2` thành hai token (`Hình`, `1.2`), và ở
    trang xấu thành ba (`Hình`, `1`, `.2`). Vị trí lấy theo từ ĐẦU của cụm.
    """
    hits = []
    for index, word in enumerate(words):
        window = " ".join(w["text"] for w in words[index:index + 3])
        for name, pattern in CAPTION_PATTERNS.items():
            match = pattern.match(window)
            if not match:
                continue
            hits.append({"pattern": name, "text": match.group(0),
                         "cx": word["cx"], "cy": word["cy"],
                         "conf": word["conf"]})
            break
    return hits


def probe_pill_pattern(source, pages: list, verbose: bool = False) -> dict:
    """`pill_pattern` + `figure_caption_regex` của một quyển, đo trên `pages`."""
    t0 = time.time()
    bounds = None
    pill_boxes = pill_read = 0
    pill_labels: list = []
    pill_texts: list = []
    caption_counts: dict = {k: 0 for k in CAPTION_PATTERNS}
    caption_examples: list = []
    caption_cys: list = []
    pages_with_pill_label = 0
    pages_with_caption_label = 0
    words_total = 0

    for pn in pages:
        image = source.load(pn)
        if bounds is None:
            bounds = P.bounds_for_width(image.shape[1])

        # --- kênh pill
        boxes = P.find_pill_boxes(image, bounds)
        pill_boxes += len(boxes)
        page_has_pill_label = False
        for bbox in boxes:
            variants = P.read_pill_variants(image, bbox)
            if not variants:
                continue
            pill_read += 1
            match = next((m for m in (P.FIGURE_LABEL.search(v) for v in variants)
                          if m), None)
            if match:
                page_has_pill_label = True
                pill_labels.append({
                    "page": pn, "bbox": list(bbox),
                    "label": f"Hình {int(match.group(1))}.{int(match.group(2))}",
                    "raw": variants[0]})
            elif len(pill_texts) < 12:
                pill_texts.append({"page": pn, "bbox": list(bbox),
                                   "text": variants[0]})
        pages_with_pill_label += 1 if page_has_pill_label else 0

        # --- kênh OCR thường
        words = _page_words(image)
        words_total += len(words)
        hits = caption_hits(words)
        page_has_caption = False
        for hit in hits:
            caption_counts[hit["pattern"]] += 1
            if hit["pattern"] in ("hinh_n_m", "h_dot_n_m"):
                page_has_caption = True
                caption_cys.append(hit["cy"])
            if len(caption_examples) < 15:
                caption_examples.append({"page": pn, **hit})
        pages_with_caption_label += 1 if page_has_caption else 0

    n_pages = len(pages) or 1
    n_pill_label = len(pill_labels)
    n_caption_label = caption_counts["hinh_n_m"] + caption_counts["h_dot_n_m"]

    # Nhãn dán, suy THUẦN từ hai con số đếm được ở trên (cả hai đều có trong JSON).
    if n_pill_label == 0 and n_caption_label == 0:
        ket_luan = "khong_doc_duoc_nhan_nao"
    elif n_pill_label and not n_caption_label:
        ket_luan = "pill"
    elif n_caption_label and not n_pill_label:
        ket_luan = "caption"
    else:
        ket_luan = "ca_hai"

    dominant = max(CAPTION_PATTERNS, key=lambda k: caption_counts[k])
    flags = []
    if ket_luan == "khong_doc_duoc_nhan_nao":
        flags.append("khong_doc_duoc_nhan_hinh_nao_o_ca_hai_kenh")
    if pill_boxes and pill_read == 0:
        flags.append(f"tim_thay_{pill_boxes}_pill_nhung_khong_doc_ra_chu_nao")

    out = {
        "pages_probed": pages,
        "bounds_used": bounds,
        "n_pill_boxes": pill_boxes,
        "n_pill_read": pill_read,
        "n_pill_figure_label": n_pill_label,
        "pages_with_pill_label": pages_with_pill_label,
        "pill_label_examples": pill_labels[:12],
        "pill_other_text_examples": pill_texts,
        "caption_counts": caption_counts,
        "caption_examples": caption_examples,
        "pages_with_caption_label": pages_with_caption_label,
        "caption_cy_median": (round(sorted(caption_cys)[len(caption_cys) // 2], 3)
                              if caption_cys else None),
        "words_per_page": round(words_total / n_pages, 1),
        "ket_luan": ket_luan,
        "figure_caption_regex": (CAPTION_PATTERNS[dominant].pattern
                                 if caption_counts[dominant] else None),
        "seconds": round(time.time() - t0, 1),
        "flags": flags,
    }
    if verbose:
        print(f"    [pill] pill={pill_boxes} doc={pill_read} nhan={n_pill_label} "
              f"| caption Hình N.M={caption_counts['hinh_n_m']} "
              f"-> {ket_luan} ({out['seconds']}s)")
    return out
