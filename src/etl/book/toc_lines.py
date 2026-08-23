"""Đọc MỤC LỤC theo DÒNG — cho CTST và Cánh Diều (M1).

## Vì sao cần bộ đọc thứ hai (đo được, 2026-08-23)

`toc.py` đọc MỤC LỤC như một **bảng một cột logic**: tìm cột số trang bằng CV rồi
OCR từng ô. Nó đọc đúng 195/195 Bài của 4 quyển KNTT. Trên CTST/CD nó **ra số SAI
MÀ TRÔNG HỢP LÝ** — đo trên 7_CTST: `Bài 1 -> trang 144` (thật là trang 6), rồi
ràng buộc đơn điệu giết 31 Bài còn lại (D-65). Nguyên nhân: hai nhà xuất bản này
xếp MỤC LỤC kiểu tạp chí, nên "cột số trang phải nhất" là số của **cột bên phải**
trong khi tiêu đề lấy được là của **cột bên trái**.

## Bốn phép đo đã bác bỏ bốn thiết kế "hiển nhiên"

1. **Tách trang thành hai cột bằng hình học rồi OCR từng cột.** Đo khe dọc trong
   dải 30–70% bề rộng trên cả 16 trang MỤC LỤC của CD+CTST: CTST rất sạch (khe
   99–123 px, tâm x = 0,493–0,507 ở **8/8** trang), nhưng CD **không đồng nhất** —
   6_CD/7_CD có khe gần tâm (0,475–0,534) còn **8_CD và 9_CD không có khe giữa
   nào** (chỗ rộng nhất là 27 px ở x=0,614 và 108–150 px ở x=0,667–0,676, tức lề
   phải chứ không phải khe cột): **MỤC LỤC của 8_CD/9_CD là MỘT cột chạy hết bề
   rộng.** Một luật "CD luôn hai cột" sai với nửa số quyển CD.
2. **OCR cả trang `--psm 6` rồi khớp regex từng dòng.** Trên bố cục hai cột,
   Tesseract **dán hai cột vào cùng một dòng text**: `1. Nguyên tử 10 7, Tốc độ
   của chuyển động 47` (7_CD tr.170) — một dòng, hai mục, hai số trang. Regex "số
   ở cuối dòng" gán cho mục bên trái số trang của mục bên phải.
3. **Ràng buộc đơn điệu theo thứ tự đọc** (luật của `toc.py`). Sai theo cấu trúc ở
   bố cục hai cột: thứ tự đọc của Tesseract là 1, 7, 2, 8… nên số trang đi 10, 47,
   15, 50 — không đơn điệu, và ràng buộc đó giết mọi mục cột phải.
4. **"Số trang = token số đầu tiên sau tiêu đề", tìm mãi cho tới khi thấy.** Bản
   đầu của file này làm thế và đo được **12–26 cờ `out_of_order` mỗi quyển**: khi
   số của chính mục đó bị OCR đọc thành rác (`Ố`, `Z4`, `ĐỐ`, `nl Ðộ`), phép tìm
   đi tiếp và **lấy số của mục KHÁC** — 9_CTST ra `Bài 1 -> trang 62` (thật là ~6).
   Nên phép tìm phải **dừng ở mục kế tiếp**: thà không có số còn hơn có số của
   người khác (nguyên tắc 1).

## Nên: token + KHE NGANG, dừng ở mục kế, và đọc lại ô số bằng whitelist

`image_to_data` trả bbox từng từ, nên khe ngang giữa hai từ liền nhau là **dữ liệu
sẵn có**, không phải suy đoán. Đo phân bố khe trên trang MỤC LỤC: p50 = 12–15 px,
p75 = 24–72 px, còn khe cột / khe dot-leader ở **p90 = 267–906 px**. Ngưỡng
`SEG_GAP_FRAC = 3%` bề rộng (68 px ở 2280 px) nằm gọn giữa hai nhóm.

Luật, mỗi luật vì một ca đo được:

1. Cắt mỗi dòng thành **segment** ở khe > 3% bề rộng.
2. Một mục phải khớp ở **đầu segment** — nếu không thì `Chủ đề4:Tốc độ` sinh ra
   mục ma số 4 (chữ số dính ngay sau chữ "đề").
3. Cho phép **đúng một token số đứng trước** ở đầu segment: đó là số trang của mục
   cột bên trái bị dán vào (`10 7, Tốc độ …`). Không cho thì mất mọi mục cột phải
   của 6_CD/7_CD.
4. Số trang của một mục = token số đầu tiên sau tiêu đề của **chính nó**, và phép
   tìm **dừng khi gặp segment là một mục/chương khác** (luật này sinh ra từ phép
   đo ở §4 trên).
5. Không tìm thấy thì **đọc lại vùng đuôi bằng digit whitelist**, hợp qua
   `scale × psm` — đúng thủ pháp đã hiệu quả ở số trang góc (D-33) và ô số của
   `toc.py`. Vùng đuôi lấy từ **bbox thật của các token**, không phải toạ độ đoán.
6. **Không** ràng buộc đơn điệu theo thứ tự đọc. Tự kiểm bằng thứ khó bịa hơn: sắp
   theo `bai_so` rồi số trang phải **không giảm**; chỗ phạm thì **bỏ mục + gắn
   cờ**, không đoán (CẤM #4, #5).
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, Sequence

import cv2
import pytesseract

from ...config import TESSERACT_CMD
from .toc import MAX_PRINTED_PAGE, TocChuong, TocEntry, TocResult, _ocr

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

# Khe ngang (theo bề rộng trang) để cắt một dòng OCR thành segment. Đo được: khe
# giữa các từ cùng cụm p50 = 12–15 px / p75 = 24–72 px, còn khe cột và khe
# dot-leader p90 = 267–906 px, trên trang rộng 2280 px.
SEG_GAP_FRAC = 0.03
MIN_ENTRY_ROWS = 3
# Tách cột: khe dọc gần TÂM trang. Ngưỡng lấy từ phép đo 16 trang MỤC LỤC — khe
# thật của CTST 99–123 px @ x=0,493–0,507 và của 6_CD/7_CD 57–72 px @ 0,475–0,534;
# còn 8_CD/9_CD (MỤC LỤC một cột) chỉ có 27 px @ 0,614 và 108–150 px @ 0,667–0,676,
# tức LỀ PHẢI. Nên phải chặn cả bề rộng VÀ vị trí tâm, chặn một cái là nhận sai.
COL_GUTTER_MIN_FRAC = 0.015
COL_CENTER_RANGE = (0.42, 0.58)
COL_BAND = (0.30, 0.70)        # chỉ tìm khe trong dải này
COL_BODY_BAND = (0.10, 0.90)   # bỏ đầu trang/chân trang khi đo mực
COL_EMPTY_FRAC = 0.004         # cột "không mực" = dưới 0,4% chiều cao có mực
# Đọc lại ô số: hợp qua scale × psm. Cùng lý do như `toc.read_number_cell` —
# không scale/psm nào tốt nhất ở mọi ô.
RESCUE_SCALES = (2, 3)
RESCUE_PSMS = (7, 8, 13)
RESCUE_PAD_Y_FRAC = 0.004      # nới dọc theo chiều cao trang (~13 px ở 3201)

_BAI_ENTRY = re.compile(
    r"^(?:(?P<carry>\d{1,3})\s+)?[Bb][ÀÁÂàáâAa][ÌÍIiìí]\s*(?P<so>\d{1,2})\s*[.,:]?\s+"
    r"(?P<title>\S.*)$")
_SO_ENTRY = re.compile(
    r"^(?:(?P<carry>\d{1,3})\s+)?(?P<so>\d{1,2})\s*[.,:]\s*(?P<title>\D\S*.*)$")
_CHUONG = re.compile(
    r"^(?:\d{1,3}\s+)?(?:CH[ƯU][ƠO]NG|Ch[ủuúù]\s*đ[ềêe]|Ph[ầâa]n)\s*"
    r"(?P<label>[0-9IVXL]{1,4})\s*[.:,]?\s*(?P<title>.*)$", re.IGNORECASE)
_NUMBER = re.compile(r"^(\d{1,3})\D{0,2}$")
# "Bài tập (Chủ đề 4)" KHÔNG phải một Bài — nếu nhận thì `bai_so` trùng số chủ đề
# và phá phép tự kiểm 1..max.
_BAI_TAP = re.compile(r"b[àa]i\s*t[ậa]p", re.IGNORECASE)


@dataclass(frozen=True)
class Segment:
    text: str
    x0: int
    x1: int
    tokens: tuple              # tuple[(x0, x1, text)]


@dataclass(frozen=True)
class TocLine:
    page_index: int
    segments: tuple
    y0: int
    y1: int


def _fold(text: str) -> str:
    nfd = unicodedata.normalize("NFD", text or "")
    out = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return " ".join(out.replace("đ", "d").replace("Đ", "D").lower().split())


def split_columns(image) -> list:
    """`[(x0, x1), ...]` — hai cột nếu đo được khe dọc gần tâm, ngược lại một cột.

    Vì sao phải tách trước khi OCR: Tesseract `psm 6` **dán hai cột vào cùng một
    dòng**, và với CTST thì tiêu đề còn tràn sang dòng dưới, nên số trang của mục
    cột trái nằm ở dòng kế của CHÍNH cột đó — không thể tìm được nếu hai cột còn
    dán. Đo trên 8/8 trang CTST: khe 99–123 px, tâm x = 0,493–0,507.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    height, width = gray.shape
    body = (gray < 128)[int(COL_BODY_BAND[0] * height):
                        int(COL_BODY_BAND[1] * height), :]
    if body.size == 0:
        return [(0, width - 1)]
    empty = body.sum(axis=0) <= max(1, int(COL_EMPTY_FRAC * body.shape[0]))
    lo, hi = int(COL_BAND[0] * width), int(COL_BAND[1] * width)
    runs, start = [], None
    for x in range(lo, hi):
        if empty[x]:
            start = x if start is None else start
        elif start is not None:
            runs.append((start, x - 1))
            start = None
    if start is not None:
        runs.append((start, hi - 1))
    if not runs:
        return [(0, width - 1)]
    best = max(runs, key=lambda r: r[1] - r[0])
    centre = (best[0] + best[1]) / 2.0 / width
    if (best[1] - best[0] + 1 < COL_GUTTER_MIN_FRAC * width
            or not COL_CENTER_RANGE[0] <= centre <= COL_CENTER_RANGE[1]):
        return [(0, width - 1)]
    return [(0, best[0]), (best[1], width - 1)]


def page_lines(image, page_index: int, *, gap_frac: float = SEG_GAP_FRAC,
               psm: int = 6, x_offset: int = 0) -> list:
    """Dòng của một ảnh (một cột hoặc cả trang), cắt segment ở khe ngang lớn.

    `x_offset` được cộng vào mọi toạ độ x để bbox vẫn nằm trong hệ toạ độ của
    TRANG — nếu không thì `rescue_number` sẽ crop sai chỗ khi đọc theo cột.
    """
    threshold = max(1, int(gap_frac * image.shape[1]))
    data = pytesseract.image_to_data(image, lang="vie", config=f"--psm {psm}",
                                     output_type=pytesseract.Output.DICT)
    grouped: dict = defaultdict(list)
    for index, raw in enumerate(data["text"]):
        token = (raw or "").strip()
        if not token:
            continue
        key = (data["block_num"][index], data["par_num"][index],
               data["line_num"][index])
        grouped[key].append((data["left"][index] + x_offset,
                             data["left"][index] + data["width"][index] + x_offset,
                             data["top"][index],
                             data["top"][index] + data["height"][index], token))

    def build(words: list) -> Segment:
        return Segment(text=" ".join(w[4] for w in words),
                       x0=min(w[0] for w in words), x1=max(w[1] for w in words),
                       tokens=tuple((w[0], w[1], w[4]) for w in words))

    lines: list = []
    for key in sorted(grouped):
        words = sorted(grouped[key])
        groups: list = [[words[0]]]
        for previous, word in zip(words, words[1:]):
            if word[0] - previous[1] > threshold:
                groups.append([word])
            else:
                groups[-1].append(word)
        lines.append(TocLine(page_index=page_index,
                             segments=tuple(build(g) for g in groups),
                             y0=min(w[2] for w in words),
                             y1=max(w[3] for w in words)))
    return lines


def _is_entry_like(segment: Segment, pattern) -> bool:
    return bool(pattern.match(segment.text) or _CHUONG.match(segment.text))


def _number_in(text: str) -> Optional[int]:
    for token in (text or "").split():
        match = _NUMBER.match(token)
        if match:
            value = int(match.group(1))
            if 0 < value <= MAX_PRINTED_PAGE:
                return value
    return None


def rescue_number(image, line: TocLine, x0: int, x1: int) -> set:
    """Đọc lại vùng `[x0, x1]` của một dòng bằng digit whitelist (luật 5)."""
    pad = max(2, int(RESCUE_PAD_Y_FRAC * image.shape[0]))
    y0, y1 = max(0, line.y0 - pad), min(image.shape[0], line.y1 + pad)
    x0, x1 = max(0, x0), min(image.shape[1], x1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return set()
    crop = image[y0:y1, x0:x1]
    found: set = set()
    for scale in RESCUE_SCALES:
        scaled = cv2.resize(crop, None, fx=scale, fy=scale,
                            interpolation=cv2.INTER_CUBIC)
        for psm in RESCUE_PSMS:
            digits = "".join(c for c in _ocr(scaled, psm, "0123456789")
                             if c.isdigit())
            if digits and len(digits) <= 3:
                value = int(digits)
                if 0 < value <= MAX_PRINTED_PAGE:
                    found.add(value)
    return found


def parse_page(image, lines, style: str, result: TocResult,
               seen: dict) -> None:
    """Gom mục của MỘT cột (hoặc cả trang) vào `seen` + cờ.

    `lines` phải theo thứ tự đọc của MỘT cột: luật 4 đi sang dòng sau để tìm số
    trang của tiêu đề tràn dòng, nên trộn hai cột vào đây là gán số sai.
    """
    lines = list(lines)
    pattern = _BAI_ENTRY if style == "bai" else _SO_ENTRY
    for line in lines:
        segments = line.segments
        for index, segment in enumerate(segments):
            if _CHUONG.match(segment.text):
                chuong = _CHUONG.match(segment.text)
                result.chuongs.append(TocChuong(
                    label=chuong.group("label").upper(),
                    title=chuong.group("title").strip(" .:-–—").strip(),
                    after_bai=None))
                continue
            if _BAI_TAP.search(_fold(segment.text)):
                continue
            entry = pattern.match(segment.text)
            if not entry:
                continue
            bai_so = int(entry.group("so"))
            if not 0 < bai_so <= 99:
                continue

            # Tiêu đề dừng ở token số đầu tiên (đó là số trang, không phải tên).
            title_tokens, tail_tokens = [], []
            for token in entry.group("title").split():
                if tail_tokens or _NUMBER.match(token):
                    tail_tokens.append(token)
                else:
                    title_tokens.append(token)
            title = " ".join(title_tokens).strip(" .:-–—…").strip()

            # Luật 4: nhìn tới trước mục kế tiếp, không đi xa hơn — trong
            # phần còn lại của dòng này, RỒI các dòng sau của cùng cột (tiêu đề
            # CTST tràn dòng nên số trang nằm ở dòng kế của chính nó).
            page = _number_in(" ".join(tail_tokens))
            limit = segment.x1
            scan_line = line
            if page is None:
                for following in segments[index + 1:]:
                    if _is_entry_like(following, pattern):
                        break
                    limit = following.x1
                    page = _number_in(following.text)
                    if page is not None:
                        break
            if page is None and index == len(segments) - 1:
                for nxt in lines[lines.index(line) + 1:]:
                    if any(_is_entry_like(seg, pattern) for seg in nxt.segments):
                        break
                    hit = None
                    for seg in nxt.segments:
                        hit = _number_in(seg.text)
                        if hit is not None:
                            limit, scan_line = seg.x1, nxt
                            break
                    if hit is not None:
                        page = hit
                        break
                    if nxt.segments:
                        limit, scan_line = nxt.segments[-1].x1, nxt

            if page is None:
                # Luật 5: đọc lại vùng đuôi bằng whitelist. Vùng đuôi = từ mép
                # phải của token tiêu đề cuối tới `limit` (mép phải segment cuối
                # còn được phép nhìn).
                after_title = (segment.tokens[len(title_tokens)][0]
                               if len(title_tokens) < len(segment.tokens)
                               else segment.x1)
                candidates = rescue_number(image, scan_line, after_title, limit)
                if len(candidates) == 1:
                    page = candidates.pop()
                elif candidates:
                    result.flags.append({
                        "kind": "toc_page_ambiguous",
                        "detail": f"Bài {bai_so} (trang nguồn {line.page_index}): "
                                  f"đọc lại ra nhiều ứng viên {sorted(candidates)} "
                                  f"-> bỏ mục, không chọn bừa"})
                    continue

            if page is None:
                result.flags.append({
                    "kind": "toc_page_unreadable",
                    "detail": f"Bài {bai_so} (trang nguồn {line.page_index}): "
                              f"không đọc được số trang sau tiêu đề "
                              f"{title[:40]!r} -> bỏ mục, không đoán"})
                continue

            previous = seen.get(bai_so)
            if previous is None:
                seen[bai_so] = (page, title)
            elif previous[0] != page:
                result.flags.append({
                    "kind": "toc_entry_duplicated",
                    "detail": f"Bài {bai_so} xuất hiện hai lần với số trang khác "
                              f"nhau ({previous[0]} và {page}) -> giữ "
                              f"{previous[0]}"})


def _longest_non_decreasing(pairs: list) -> set:
    """Chỉ số của dãy con KHÔNG GIẢM dài nhất theo `page` (pairs đã sắp theo bai).

    Vì sao không dùng phép quét tham lam từ trái sang: một mục SAI ở đầu dãy
    (9_CTST đo được `Bài 3 -> trang 62`) sẽ đẩy con trỏ lên và **giết toàn bộ**
    phần còn lại — đo được **40 cờ `out_of_order` và chỉ còn 3 mục**. Dãy con dài
    nhất bỏ đúng phần thiểu số xung đột, và vẫn là phép **drop-only**: không mục
    nào bị sửa số, chỉ bị bỏ (CẤM #5).
    """
    if not pairs:
        return set()
    best = [1] * len(pairs)
    prev = [-1] * len(pairs)
    for i in range(len(pairs)):
        for j in range(i):
            if pairs[j][1] <= pairs[i][1] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    end = max(range(len(pairs)), key=lambda i: best[i])
    keep = set()
    while end != -1:
        keep.add(end)
        end = prev[end]
    return keep


def finalise(result: TocResult, seen: dict) -> TocResult:
    """Tự kiểm (luật 6): sắp theo `bai_so`, số trang phải KHÔNG GIẢM."""
    pairs = [(bai_so, seen[bai_so][0]) for bai_so in sorted(seen)]
    keep = _longest_non_decreasing(pairs)
    entries: list = []
    for position, (bai_so, page) in enumerate(pairs):
        if position not in keep:
            result.flags.append({
                "kind": "toc_page_out_of_order",
                "detail": f"Bài {bai_so}: trang {page} phá thứ tự không giảm của "
                          f"dãy dài nhất -> bỏ mục, không đoán"})
            continue
        entries.append(TocEntry(bai_so=bai_so, title=seen[bai_so][1],
                                start_page=page))
    result.entries = entries
    return result


def read_toc_lines(source, pages: Sequence, style: str) -> TocResult:
    """Đọc MỤC LỤC của một quyển từ danh sách trang đã ĐO được (fingerprint M0).

    Chạy **hai** bộ đọc rồi hợp kết quả, vì phép đo cho thấy không bộ nào thắng ở
    mọi quyển: đọc THEO CỘT nâng CTST từ 3–9 mục lên 19–24 (tiêu đề tràn dòng nên
    số trang nằm ở dòng kế của chính cột đó), nhưng lại làm 6_CD/7_CD **tụt**
    32->29 và 25->22. Hai bộ cùng cho một `bai_so` mà **khác số trang** thì bỏ mục
    đó và gắn cờ — hai nguồn không khớp thì không chọn bừa (nguyên tắc 6).
    """
    result = TocResult()
    votes: dict = {}           # bai_so -> {page: [tên bộ đọc]}
    titles: dict = {}
    for page_index in pages:
        image = source.load(page_index)
        columns = split_columns(image)
        readers = [("toan_trang", [(0, image.shape[1] - 1)])]
        if len(columns) > 1:
            readers.append(("theo_cot", columns))
        for name, boxes in readers:
            seen: dict = {}
            for x0, x1 in boxes:
                crop = image[:, x0:x1 + 1]
                parse_page(image, page_lines(crop, page_index, x_offset=x0),
                           style, result, seen)
            for bai_so, (page, title) in seen.items():
                votes.setdefault(bai_so, {}).setdefault(page, []).append(name)
                titles.setdefault(bai_so, {}).setdefault(page, title)
        del image

    merged: dict = {}
    for bai_so, by_page in votes.items():
        if len(by_page) == 1:
            page = next(iter(by_page))
            merged[bai_so] = (page, titles[bai_so][page])
            continue
        # Hai bộ đọc không khớp. Nếu đúng một số trang được CẢ HAI bộ nêu thì lấy
        # nó (đồng thuận); còn lại thì bỏ, không chọn bừa.
        agreed = [page for page, who in by_page.items() if len(set(who)) > 1]
        if len(agreed) == 1:
            merged[bai_so] = (agreed[0], titles[bai_so][agreed[0]])
            result.flags.append({
                "kind": "toc_page_reader_disagreement",
                "detail": f"Bài {bai_so}: hai bộ đọc ra {sorted(by_page)} -> lấy "
                          f"{agreed[0]} (số duy nhất cả hai bộ cùng nêu)"})
        else:
            result.flags.append({
                "kind": "toc_page_reader_conflict",
                "detail": f"Bài {bai_so}: hai bộ đọc ra {sorted(by_page)} và không "
                          f"số nào được cả hai nêu -> bỏ mục, không đoán"})

    finalise(result, merged)
    result.page_indices = list(pages)
    if len(result.entries) < MIN_ENTRY_ROWS:
        result.flags.append({
            "kind": "toc_too_few_entries",
            "detail": f"{source.name}: chỉ đọc ra {len(result.entries)} mục từ "
                      f"trang {list(pages)} (style {style})"})
    return result
