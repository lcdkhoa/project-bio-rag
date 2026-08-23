"""M0 §2.1 + §2.2 — ĐO trang MỤC LỤC và hình học bảng mục lục của từng quyển.

## Vì sao không hardcode — và lần này còn nặng hơn tưởng

Hằng số cũ `TOC_PAGE_NUMBERS = (5, 6)` **âm thầm làm mất Bài 40–55 của KNTT lớp
6** vì quyển đó có BA trang MỤC LỤC. Bản dò đầu tiên của file này sửa được lỗi ấy
nhưng vẫn mang một giả định KNTT khác: *MỤC LỤC nằm ở đầu sách và mỗi mục bắt đầu
bằng chữ "Bài"*. **Đo trên corpus thật ngày 2026-08-23 cho thấy cả hai đều sai:**

| bộ | trang MỤC LỤC | mẫu mục | bố cục | đọc số trang |
|---|---|---|---|---|
| KNTT | **đầu** (tr. 4–6) | `Bài N` + cột số riêng | 1 cột, có kẻ / dải màu | cell OCR chạy tốt |
| CD | **CUỐI SÁCH** (6_CD tr. 178–179 / 179; 9_CD tr. 214–215 / 215) | `N. Tiêu đề <số>` — **không có chữ "Bài"** | hai nhóm cột | số nằm cuối dòng, `psm 6` đọc được |
| CTST | **đầu** (tr. 4–5) | `BÀI N: Tiêu đề ....... <số>` (dot leader) | hai cột | `psm 6` đọc **SAI nhiều số** (`6`→`Ổ`, `71`→`Z Ì`, `62`→`Õ 2`) |

Chữ "MỤC LỤC" chỉ đọc được ở **1 trong 4 quyển** đã mở ra xem (9_CD), nên nó
KHÔNG thể là cổng nhận — chỉ là một bằng chứng phụ.

## Cổng nhận là HỢP của hai bộ đọc, không phải một

Bản trước của file này dùng **một** cổng: đếm dòng dạng mục lục trên OCR cả trang
(`psm 6`). Nó tìm được CD/CTST và **mất sạch 4 quyển KNTT** — đúng bằng lý do
`toc.py` từng được viết ra: trên trang MỤC LỤC có kẻ khung của KNTT, `psm 6` cả
trang chỉ ra **~49 từ** vì nét kẻ dính vào chữ số, nên phép đếm dòng ra 0. Đổi một
nhà xuất bản lấy một nhà xuất bản khác thì không phải là sửa.

Nên cổng nhận là **HOẶC** của hai bộ đọc độc lập, chạy theo thứ tự rẻ trước:

* **A — đếm dòng** trên OCR cả trang (`ROW_PATTERNS`). Bắt được bố cục tạp chí
  hai cột của CD/CTST. Không đòi đọc được số trang: 9_CTST ra
  `Bài 2. Cơ năng ....... TŨ`, số trang là rác, nên mẫu nào bắt buộc có chữ số ở
  cuối dòng sẽ bỏ sót cả quyển CTST.
* **B — bộ đọc cell** `toc.read_toc_rows` (dựng hình học bằng CV rồi OCR từng ô).
  Bắt được bảng có kẻ khung của KNTT, nơi A luôn ra 0. Chỉ chạy khi A trượt, nên
  CD/CTST không phải trả giá.

Hai bằng chứng phụ, ghi ra chứ không dùng làm cổng:

* **Chữ "MỤC LỤC"** trên bản đã bỏ dấu — chỉ đọc được ở 1/4 quyển đã mở ra xem.
* **Hình học bảng** (CV thuần) — số nhóm cột, để thấy ngay quyển nào là bảng một
  cột (KNTT) và quyển nào là hai cột kiểu tạp chí (CD/CTST).

Cửa sổ quét là **đầu sách VÀ cuối sách**: quét chỉ một đầu là lặp lại đúng loại
sai của `TOC_PAGE_NUMBERS`. Tập trang nhận được phải **liền mạch**; không liền
mạch thì **gắn cờ**, không tự lấp (nguyên tắc 5 + CẤM #4).

## Bộ đọc spine của KNTT KHÔNG được chạy cho style khác

`toc.read_toc_rows` khớp `Bài N` để tìm hàng. Với CD (mục là `N. Tiêu đề`) nó trả
0 hàng — chạy nó rồi báo "0 Bài" là một con số vô nghĩa đội lốt phép đo. Nên nó
chỉ chạy khi `entry_style == "bai"`, còn lại ghi rõ **vì sao không chạy**. Đó là
việc của M1, và phải nhìn thấy được ở đây thay vì lặng lẽ ra 0.

## Ngưỡng px không được mượn giữa các nhà xuất bản

`toc.py` đo mọi ngưỡng px trên KNTT ở 1094 px. CD/CTST rộng 2280–2480 px nên
`toc.geom_for_width(w)` nhân chúng theo `w / 1094`, và bộ số thực dùng được GHI
vào JSON — để một kết quả "0 hàng" phân biệt được *quyển này không có bảng* với
*ta đo bằng ngưỡng của quyển khác*.
"""

from __future__ import annotations

import re
import time
import unicodedata

import cv2

from . import toc as T

# Cửa sổ quét: HAI ĐẦU sách. CD in MỤC LỤC ở hai trang cuối cùng, KNTT/CTST ở đầu.
FRONT_SCAN = 15
BACK_SCAN = 8
MARKER_BAND_FRAC = 0.40   # "MỤC LỤC" là tiêu đề -> nằm ở phần trên của trang
# Số dòng dạng mục lục tối thiểu để nhận một trang. Sàng lọc (trên dải trên) dùng
# ngưỡng thấp hơn vì dải chỉ thấy một phần trang.
MIN_TOC_ROWS = 4
MIN_SCREEN_ROWS = 2
# Cổng B: số hàng đọc ra "Bài N" bằng bộ đọc cell (dùng ngưỡng của chính `toc.py`).
MIN_BAI_CELLS = T.MIN_BAI_ROWS
# Chặn chi phí, áp RIÊNG cho từng đoạn quét (đầu sách / cuối sách) và chỉ khi
# đoạn đó chưa nhận được trang nào: sau ngần này ứng viên mà vẫn chưa thấy bảng
# thì dừng ĐOẠN ĐÓ và GẮN CỜ (CẤM #7).
#
# Vì sao phải chia đoạn: đo được là trang thân bài của CD/CTST cũng có cột mực
# bên phải nên lọt vào ứng viên. Áp một hạn mức chung cho cả cửa sổ thì 8 ứng
# viên ĐẦU sách dùng hết hạn mức và **không bao giờ tới được hai trang CUỐI** —
# đúng nơi CD in MỤC LỤC. Một hạn mức chung biến "chưa xem" thành "không có".
MAX_CANDIDATES = 8

_MUC_LUC_EXACT = re.compile(r"\bmuc\s*luc\b")
_MUC_LUC_FUZZY = re.compile(r"\bm[a-z0-9]{1,2}c\s*l[a-z0-9]{1,2}c\b")

# Hình dạng một DÒNG mục lục. Kiểm theo THỨ TỰ, dòng chỉ được đếm cho mẫu ĐẦU
# TIÊN khớp, để một dòng "Bài 3: ... 27" không bị đếm hai lần.
#
# `bai` KHÔNG đòi số trang ở cuối dòng: đo trên 9_CTST, `Bài 2. Cơ năng ..... TŨ`
# — số trang OCR ra rác. Đòi chữ số ở cuối là bỏ sót cả quyển.
# `so_thu_tu` THÌ đòi, vì `^N. chữ` một mình cũng khớp danh sách đánh số trong
# thân bài ("1. Quan sát hình..."); có số trang ở cuối mới phân biệt được.
ROW_PATTERNS = (
    ("bai", re.compile(r"^\s*B[ÀÁÂàáâAa][ÌIiI]\s*\d{1,2}\s*[.:,]", re.IGNORECASE)),
    ("chu_de", re.compile(r"^\s*Ch[ủuúù]\s*đ[ềêe]\s*\d{1,2}\s*[.:,]?",
                          re.IGNORECASE)),
    ("so_thu_tu", re.compile(r"^\s*\d{1,2}\s*[.,]\s+\D.*?\d{1,3}\s*$")),
)
_DOT_LEADER = re.compile(r"\.{4,}")


def fold(text: str) -> str:
    """Bỏ dấu + hạ chữ thường + gộp khoảng trắng. Dùng để so khớp, KHÔNG để lưu."""
    nfd = unicodedata.normalize("NFD", text or "")
    ascii_ish = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    ascii_ish = ascii_ish.replace("đ", "d").replace("Đ", "D")
    return " ".join(ascii_ish.lower().split())


def muc_luc_marker(text: str) -> str | None:
    """`"exact"` / `"fuzzy"` / `None` — mức khớp chữ "MỤC LỤC" trong `text`."""
    folded = fold(text)
    if _MUC_LUC_EXACT.search(folded):
        return "exact"
    if _MUC_LUC_FUZZY.search(folded):
        return "fuzzy"
    return None


def row_shape_counts(text: str) -> dict:
    """Đếm dòng theo từng mẫu mục lục + đặc trưng dot leader."""
    counts = {name: 0 for name, _ in ROW_PATTERNS}
    counts["dot_leader"] = 0
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if _DOT_LEADER.search(line):
            counts["dot_leader"] += 1
        for name, pattern in ROW_PATTERNS:
            if pattern.match(line):
                counts[name] += 1
                break
    counts["toc_rows"] = sum(counts[name] for name, _ in ROW_PATTERNS)
    return counts


def entry_style_of(counts: dict) -> str | None:
    """Mẫu mục trội của một quyển, hoặc None nếu không đếm được dòng nào."""
    ranked = sorted(((counts.get(name, 0), name) for name, _ in ROW_PATTERNS),
                    key=lambda kv: -kv[0])
    return ranked[0][1] if ranked[0][0] else None


def _ocr_band(image, frac: float) -> str:
    """OCR dải trên của trang (`psm 6`, tiếng Việt). `frac >= 1.0` = cả trang."""
    crop = image if frac >= 1.0 else image[:max(1, int(image.shape[0] * frac)), :]
    return T._ocr(crop, 6)


def cv_geometry(gray, geom: dict) -> dict:
    """Hình học bảng đo bằng CV thuần (không OCR) — rẻ, chạy cho mọi trang quét."""
    height, width = gray.shape
    column, how = T.number_column(gray, geom)
    body = (gray < T.INK_MAX)[int(T.TOP_CLIP * height):int(T.BOT_CLIP * height), :]
    col_groups = T._runs(body.sum(axis=0) > 2, 0, width, gutter=geom["col_gutter"])
    out = {"page_width": int(width), "page_height": int(height),
           "how": how, "col_px": None, "col_frac": None, "col_width_px": None,
           "n_rows": 0,
           # Số nhóm cột mực trên cả bề rộng: 1–2 = bảng một cột (KNTT), >=3 =
           # bố cục hai cột kiểu tạp chí (CD/CTST, mỗi cột một cặp tiêu đề+số).
           "n_col_groups": len([g for g in col_groups
                                if g[1] - g[0] + 1 >= geom["min_col_width"]])}
    if column is None:
        return out
    x0, x1 = column
    bands = T.row_bands(gray, x0, x1, geom)
    out.update({
        "col_px": [int(x0), int(x1)],
        "col_frac": [round(x0 / width, 4), round(x1 / width, 4)],
        "col_width_px": int(x1 - x0 + 1),
        "n_rows": len(bands),
    })
    return out


def _contiguous(pages: list) -> bool:
    return all(b - a == 1 for a, b in zip(pages, pages[1:]))


def scan_window(pages: list, front: int = FRONT_SCAN,
                back: int = BACK_SCAN) -> list:
    """Trang cần quét: `front` trang đầu + `back` trang cuối, không trùng lặp."""
    head = pages[:front]
    tail = [p for p in pages[-back:] if p not in set(head)] if back else []
    return head + tail


def probe_toc(source, scan: int = FRONT_SCAN, back: int = BACK_SCAN,
              verbose: bool = False) -> dict:
    """`toc_pages` + `toc_geometry` của một quyển, kèm bằng chứng từng trang."""
    all_pages = list(source.page_numbers())
    window = scan_window(all_pages, scan, back)
    t0 = time.time()

    # --- sàng lọc: OCR dải trên (rẻ hơn cả trang) + hình học CV
    #
    # KHÔNG giữ ảnh trong `screen`: cửa sổ quét là 23 trang, mỗi trang CD là
    # 2480x3480x3 = ~25 MB, tức ~575 MB cho một quyển. Ứng viên chỉ có 2-4 trang
    # nên nạp lại rẻ hơn nhiều so với giữ hết.
    screen: dict = {}
    for pn in window:
        image = source.load(pn)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        geom = T.geom_for_width(gray.shape[1])
        band = _ocr_band(image, MARKER_BAND_FRAC)
        screen[pn] = {"page": pn, "geom": geom,
                      "marker": muc_luc_marker(band),
                      "band_counts": row_shape_counts(band),
                      "cv": cv_geometry(gray, geom),
                      "page_counts": None}
        del image, gray

    # Ứng viên = HỢP của cả ba tín hiệu sàng lọc. Tín hiệu hình học CV là tín
    # hiệu DUY NHẤT bắt được trang MỤC LỤC thứ hai/thứ ba của KNTT: những trang đó
    # không in lại tiêu đề "MỤC LỤC" và OCR cả dải cũng không đếm ra dòng nào (nét
    # kẻ bảng dính chữ số). Bỏ nó đi là mất Bài 18–55 của KNTT lớp 6 — đúng lại
    # cái lỗi mà `TOC_PAGE_NUMBERS` từng gây ra.
    candidates = [pn for pn in window
                  if screen[pn]["marker"]
                  or screen[pn]["band_counts"]["toc_rows"] >= MIN_SCREEN_ROWS
                  or screen[pn]["cv"]["n_rows"] >= T.MIN_ROWS]

    # --- bằng chứng đầy đủ: OCR CẢ TRANG cho ứng viên
    flags: list = []
    head_set = set(all_pages[:scan])
    front = [pn for pn in candidates if pn in head_set]
    back = [pn for pn in candidates if pn not in head_set]
    blocks = []
    for label, segment in (("dau_sach", front), ("cuoi_sach", back)):
        block, seg_flags = _accept_in_segment(source, screen, segment)
        flags += [f"{label}:{f}" for f in seg_flags]
        if block:
            blocks.append((label, block))

    if len(blocks) > 1:
        # Hai khối ở hai đầu sách: một trong hai là bảng khác (bảng giải thích
        # thuật ngữ, bảng tra cứu tên riêng — CD in cả hai ngay trước MỤC LỤC).
        # Lấy khối DÀI hơn và gắn cờ, không lặng lẽ bỏ khối kia.
        blocks.sort(key=lambda kv: -len(kv[1]))
        flags.append(f"tim_thay_2_khoi_bang: giu {blocks[0][0]}{blocks[0][1]}, "
                     f"bo {blocks[1][0]}{blocks[1][1]}")
    accepted = blocks[0][1] if blocks else []
    segment_label = blocks[0][0] if blocks else None

    if not accepted:
        flags.append("khong_tim_thay_trang_muc_luc")
    elif not _contiguous(accepted):
        flags.append(f"trang_muc_luc_khong_lien_mach:{accepted}")

    total = {"dot_leader": 0, "toc_rows": 0}
    for name, _ in ROW_PATTERNS:
        total[name] = 0
    for pn in accepted:
        for key, value in (screen[pn]["page_counts"] or {}).items():
            total[key] = total.get(key, 0) + value
    style = entry_style_of(total)
    # Cổng B nhận được nghĩa là bảng có hàng "Bài N" đọc bằng cell OCR, dù OCR cả
    # trang không đếm ra dòng nào (KNTT). Đó vẫn là style `bai`.
    if style is None and any(screen[pn].get("n_bai_cells", 0) >= MIN_BAI_CELLS
                             for pn in accepted):
        style = "bai"

    where = segment_label

    hows = sorted({screen[pn]["cv"]["how"] for pn in accepted
                   if screen[pn]["cv"]["how"]})
    if len(hows) > 1:
        flags.append(f"cot_so_trang_khong_dong_nhat:{hows}")

    spine = _read_spine(source, accepted, screen, style)
    # Bộ đọc cell giả định bảng MỘT cột (một cặp tiêu đề + số trang). CD/CTST xếp
    # MỤC LỤC kiểu tạp chí hai cột, mỗi cột một cặp — chạy bộ đọc một cột lên đó
    # thì nó chỉ thấy cột số PHẢI NHẤT rồi ghép với tiêu đề của cột khác. Đo trên
    # 7_CTST: nó gán `Bài 1 -> trang 144` (thật là trang 6), rồi ràng buộc đơn
    # điệu giết 31 Bài sau vì số trang thật của chúng đều < 144. Tức nó ra một con
    # số SAI MÀ TRÔNG HỢP LÝ — tệ hơn ra 0.
    #
    # Phép phân biệt KHÔNG dùng `n_col_groups`: bảng MỤC LỤC của KNTT vốn có 3
    # nhóm cột (số Bài | tiêu đề | số trang) mà vẫn là một bảng một cột logic, nên
    # ngưỡng ">= 3 nhóm cột" báo động giả cho chính quyển nó đọc đúng. Dùng phép
    # TỰ KIỂM đã có sẵn: spine phải là 1..max không khuyết. `n_col_groups` vẫn
    # được ghi lại làm bằng chứng, chỉ không dùng làm cổng.
    if spine.get("reader") == "toc.read_toc_rows" and not spine.get("contiguous"):
        flags.append("spine_khong_lien_mach:ket_qua_spine_KHONG_dang_tin")
    flags += spine.pop("flags_geom", [])

    out = {
        "scan_window": [window[0], window[-1]] if window else [],
        "toc_pages": accepted,
        "where": where,
        "entry_style": style,
        "row_counts_total": total,
        "uses_dot_leader": bool(total.get("dot_leader")) if accepted else None,
        "marker_pages": [pn for pn in window if screen[pn]["marker"]],
        "how": hows[0] if len(hows) == 1 else None,
        "pad_allowed": (hows == ["gutter"]) if hows else None,
        "n_col_groups": [screen[pn]["cv"]["n_col_groups"] for pn in accepted],
        "geom_used": (screen[accepted[0]]["geom"] if accepted
                      else (screen[window[0]]["geom"] if window else None)),
        "per_page": [{k: v for k, v in screen[pn].items() if k != "geom"}
                     for pn in window
                     if screen[pn]["marker"] or screen[pn]["page_counts"]
                     or screen[pn]["band_counts"]["toc_rows"] >= MIN_SCREEN_ROWS],
        "spine": spine,
        "seconds": round(time.time() - t0, 1),
        "flags": flags,
    }
    if verbose:
        print(f"    [toc] trang={accepted} ({where}) style={style} "
              f"cot={out['n_col_groups']} bai={spine.get('n_entries')} "
              f"({out['seconds']}s)")
    return out


def _accept_in_segment(source, screen: dict, segment: list) -> tuple:
    """Nhận trang MỤC LỤC trong MỘT đoạn quét (đầu sách hoặc cuối sách).

    Trả `(khoi_lien_mach, flags)`. Cổng nhận là HỢP của hai bộ đọc (xem docstring
    module): A đếm dòng trên OCR cả trang; B — chỉ chạy khi A trượt — là bộ đọc
    cell của `toc.py`, thứ duy nhất đọc được bảng có kẻ khung của KNTT.
    """
    accepted: list = []
    flags: list = []
    tested = 0
    for pn in segment:
        if accepted and pn > accepted[-1] + 1:
            break                          # khối liền mạch đã kết thúc
        if not accepted and tested >= MAX_CANDIDATES:
            flags.append(f"dung_sau_{MAX_CANDIDATES}_ung_vien_ma_chua_nhan_duoc_"
                         f"trang_nao, con_lai:{[p for p in segment if p > pn]}")
            break
        tested += 1
        image = source.load(pn)
        counts = row_shape_counts(_ocr_band(image, 1.0))
        screen[pn]["page_counts"] = counts
        ok = counts["toc_rows"] >= MIN_TOC_ROWS
        if not ok:
            # Cổng B đắt (OCR từng ô) nên chỉ chạy khi A trượt — CD/CTST không
            # cần tới. Nhưng với KNTT thì A LUÔN trượt, nên bỏ B là mất cả bộ.
            rows = T.read_toc_rows(source, pn, screen[pn]["geom"], image)
            n_cells = (0 if rows is None
                       else sum(1 for r in rows if T._BAI.search(r.text)))
            screen[pn]["n_bai_cells"] = n_cells
            ok = n_cells >= MIN_BAI_CELLS
        del image
        if ok:
            accepted.append(pn)
        elif accepted:
            break                          # trang ngay sau bảng không phải bảng
    return accepted, flags


def _read_spine(source, accepted: list, screen: dict, style: str | None) -> dict:
    """Chạy bộ đọc cell của KNTT — CHỈ khi mẫu mục là `Bài N`.

    Với style khác, "0 Bài" không phải phép đo mà là câu trả lời cho một câu hỏi
    khác. Ghi rõ lý do không chạy, và gắn cờ để M1 thấy đây là việc còn phải làm.
    """
    empty = {"n_entries": 0, "bai_min": None, "bai_max": None,
             "contiguous": False, "missing_bai": [], "toc_flags": [],
             "entries_head": [], "entries_tail": [], "reader": None,
             "flags_geom": []}
    if not accepted:
        return empty
    if style != "bai":
        empty["reader"] = f"khong_chay: bo_doc_cell_khop_'Bai N', style_do_duoc={style}"
        empty["flags_geom"] = [
            f"can_bo_doc_muc_luc_rieng_cho_style_{style}"]
        return empty

    rows, boxes = [], []
    for pn in accepted:
        geom = screen[pn]["geom"]
        image = source.load(pn)
        page_rows = T.read_toc_rows(source, pn, geom, image) or []
        geometry = T._table_geometry(source, pn, geom, image)
        bands = geometry[3] if geometry else [None] * len(page_rows)
        rows.extend(page_rows)
        boxes.extend((pn, band) for band in bands[:len(page_rows)])

    def rescue(position, _row):
        pn, band = boxes[position]
        if band is None:
            return set()
        geom = screen[pn]["geom"]
        geometry = T._table_geometry(source, pn, geom, source.load(pn))
        if geometry is None:
            return set()
        img, _gray, (nx0, nx1), _bands, _left, how = geometry
        return T.read_number_cell(img, (band[0], band[1], nx0, nx1),
                                  psms=T.NUMBER_PSMS_FULL,
                                  pads=T._pads(how, full=True, geom=geom),
                                  pad_y=geom["cell_pad_y"])

    result = T.parse_toc_rows(rows, rescue=rescue)
    bai = [e.bai_so for e in result.entries]
    missing = ([n for n in range(min(bai), max(bai) + 1) if n not in bai]
               if bai else [])
    flags_geom = []
    if bai and missing:
        flags_geom.append(f"spine_thieu_bai:{missing}")
    if not bai:
        flags_geom.append("khong_doc_ra_bai_nao_tu_muc_luc")
    return {
        "reader": "toc.read_toc_rows",
        "n_entries": len(result.entries),
        "bai_min": min(bai) if bai else None,
        "bai_max": max(bai) if bai else None,
        "contiguous": bool(bai) and not missing and min(bai) == 1,
        "missing_bai": missing,
        "toc_flags": result.flags[:20],
        "entries_head": [{"bai_so": e.bai_so, "start_page": e.start_page,
                          "title": e.title[:60]} for e in result.entries[:5]],
        "entries_tail": [{"bai_so": e.bai_so, "start_page": e.start_page,
                          "title": e.title[:60]} for e in result.entries[-3:]],
        "flags_geom": flags_geom,
    }
