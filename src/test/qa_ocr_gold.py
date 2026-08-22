"""Cổng G2 — CER / WER / tỉ lệ lỗi DẤU của OCR, trên gold set 24 trang DO NGƯỜI xác nhận.

Thiết kế gốc (`2026-08-20-kntt-only-etl-rebuild-design.md` §G2): 24 trang
(4 lớp × 6 archetype) người xác nhận, đo CER/WER/lỗi dấu cho **từng engine +
consensus**, ngưỡng diacritic-ER <= 2%.

**Phạm vi THẬT của file này, nói rõ để không ai đọc quá:** chỉ đo **một engine**
(Tesseract `vie`, đúng cấu hình production). Phần "consensus 2 engine tốt hơn cả
hai engine đơn" KHÔNG đo được vì engine thứ hai (PaddleOCR VN) chưa từng được
cài — dual-engine đã bị hoãn. Báo cáo phải nói G2 đạt **một nửa**, không được
viết "G2 PASS".

Hai quyết định thiết kế, mỗi cái chặn một cách tự lừa mình:

1. **Gold theo TỪNG VÙNG, không theo cả trang.** Chunk trong index chồng nhau
   120 ký tự (`CHUNK_SIZE=400/overlap=120`), nối chunk lại là nhân đôi chữ. Và
   CER trên một transcript phẳng sẽ bị thổi lên bởi *thứ tự đọc* giữa các vùng
   chứ không phải bởi lỗi ký tự. Nên gold bám vào `extract_text_units` — đúng
   cái OCR sinh ra trước khi chunk: không chồng lấn, không nhập nhằng thứ tự.
2. **`--score` KHÔNG tính một trang chưa có dấu người duyệt.** File `gold.txt`
   được mồi sẵn bằng chính output OCR (không mồi thì phải gõ tay 24 trang sách).
   Một file mồi mà chưa ai sửa sẽ cho CER 0,0% và trông như PASS — đó là kiểu im
   lặng tệ nhất (nguyên tắc 5). Nên mỗi trang phải có dòng `#REVIEWED-BY: <tên>`
   do người thêm vào; thiếu dòng đó thì trang bị đếm vào "chưa duyệt" và nằm
   NGOÀI mọi con số.

**Sai lệch đã biết, phải ghi vào báo cáo:** gold mồi bằng OCR nên nó *thiên vị
OCR* — người sửa dễ bỏ qua lỗi mà mắt tự động đọc đúng. Vì vậy CER đo được là
**cận dưới** của CER thật. Cách duy nhất khử sai lệch này là gõ lại từ ảnh, đắt
gấp nhiều lần; muốn con số không thiên vị thì phải trả giá đó.

Dùng:
    python -m src.test.qa_ocr_gold --export        # dựng 24 trang để người sửa
    python -m src.test.qa_ocr_gold --score         # đo sau khi đã sửa
    python -m src.test.qa_ocr_gold --score --per-page
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import DATA_DIR, PERSIST_DIR  # noqa: E402
from src.etl.layout.segmenter import segment_page  # noqa: E402
from src.etl.layout.text_extract import extract_text_units  # noqa: E402
from src.etl.page_source import discover_page_sources  # noqa: E402

GOLD_DIR = Path(__file__).resolve().parent / "gold_ocr"
BLOCK_RE = re.compile(r"^=== \[(\d+)\]\s+(\S+)\s*===\s*$")
REVIEW_RE = re.compile(r"^#REVIEWED-BY:[ \t]*(.*)$", re.MULTILINE)
DIACRITIC_ER_MAX = 0.02

# 6 archetype/quyển. `most_flagged` là lựa chọn ĐỐI KHÁNG có chủ đích: lấy đúng
# trang mà hệ thống tự cắm cờ nhiều nhất, tức trang nó tự nghi mình sai
# (nguyên tắc 4 — đi tìm trang làm mình sai, đừng chỉ lấy trang dễ).
ARCHETYPES = ("body_only", "with_sidebar", "with_info_box",
              "figure_heavy", "text_dense", "most_flagged")


# ---------------------------------------------------------------- chọn trang

def _page_facts() -> dict:
    """Số liệu mỗi trang, lấy từ chính index đã dựng (không đoán)."""
    import chromadb
    client = chromadb.PersistentClient(path=str(PERSIST_DIR))
    text = client.get_collection("biology_text").get(
        include=["metadatas", "documents"], limit=1_000_000)
    facts: dict = defaultdict(lambda: {
        "chars": 0, "regions": Counter(), "flags": 0, "figures": 0})
    for meta, doc in zip(text["metadatas"], text["documents"]):
        key = (meta["source"], meta["page_index"])
        f = facts[key]
        f["chars"] += len(doc or "")
        f["regions"][meta.get("region_type")] += 1
        f["flags"] += len((meta.get("review_tokens") or "")
                          .replace(",", " ").split())
    img_meta = client.get_collection("biology_images").get(
        include=["metadatas"], limit=1_000_000)["metadatas"]
    hit = miss = 0
    for meta in img_meta:
        key = (meta.get("pdf_filename"), meta.get("page_number"))
        if key in facts:
            facts[key]["figures"] += 1
            hit += 1
        else:
            miss += 1
    # Doc anh dung `pdf_filename`/`page_number`, chunk text dung
    # `source`/`page_index`. Neu hai khoa lech he quy chieu thi moi trang se co
    # 0 hinh va archetype `figure_heavy` bien mat KHONG MOT TIENG NAO — nen
    # phai on len (nguyen tac 5). KHONG bao boc trong try/except: mot canh bao
    # bi nuot o day chinh la kieu loi ma nguyen tac 7 cam.
    if img_meta and hit == 0:
        raise RuntimeError(
            f"0/{len(img_meta)} doc anh khop khoa (pdf_filename, page_number) "
            "voi (source, page_index) cua chunk text. Hai ben dang o hai he "
            "quy chieu khac nhau — dung lai, dung do tiep.")
    if miss:
        print(f"[canh bao] {miss}/{hit + miss} doc anh khong khop trang nao "
              "trong index text (trang chi co hinh, khong co chu?)")
    return dict(facts)


def select_pages(facts: dict) -> list:
    """24 trang = 4 quyển × 6 archetype. Tất định: tie-break theo page_index."""
    by_book: dict = defaultdict(list)
    for (book, page), f in facts.items():
        by_book[book].append((page, f))

    chosen: list = []
    for book in sorted(by_book):
        pages = sorted(by_book[book])
        taken: set = set()

        def pick(name, candidates, key):
            pool = [(p, f) for p, f in candidates if p not in taken]
            if not pool:
                print(f"[canh bao] {book}: khong con trang nao cho '{name}'")
                return
            page, f = max(pool, key=lambda pf: (key(pf[1]), -pf[0]))
            taken.add(page)
            chosen.append({"book": book, "page_index": page,
                           "archetype": name, "chars": f["chars"],
                           "figures": f["figures"], "flags": f["flags"],
                           "regions": dict(f["regions"])})

        pick("body_only",
             [(p, f) for p, f in pages if set(f["regions"]) == {"body"}],
             lambda f: f["chars"])
        pick("with_sidebar",
             [(p, f) for p, f in pages if f["regions"].get("sidebar")],
             lambda f: f["chars"])
        pick("with_info_box",
             [(p, f) for p, f in pages if f["regions"].get("info_box")],
             lambda f: f["chars"])
        pick("figure_heavy",
             [(p, f) for p, f in pages if f["figures"] >= 2],
             lambda f: f["figures"])
        pick("text_dense", pages, lambda f: f["chars"])
        pick("most_flagged", pages, lambda f: f["flags"])
    return chosen


# ---------------------------------------------------------------- export

def _blocks_to_text(units) -> str:
    out = []
    for i, u in enumerate(units, 1):
        rt = getattr(u.region_type, "value", str(u.region_type))
        out.append(f"=== [{i}] {rt} ===")
        out.append(u.text.strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"


GOLD_HEADER = (
    "#REVIEWED-BY:\n"
    "# ^ Dien TEN cua ban vao dong tren SAU KHI da doi chieu xong voi page.png.\n"
    "# Chua co ten -> trang nay bi tinh la CHUA DUYET, nam NGOAI moi con so.\n"
    "# Sua chu trong tung block cho dung NHU TRONG ANH.\n"
    "# GIU NGUYEN cac dong '=== [k] ... ==='.\n"
    "# Neu mot block la rac hoan toan (khong phai chu that): xoa het chu ben\n"
    "# duoi nhung GIU dong tieu de -> se duoc dem rieng la 'vung rac'.\n"
)


def do_export(overwrite: bool) -> int:
    facts = _page_facts()
    if not facts:
        print("Index rong — chua co chunk nao. Dung index truoc.")
        return 1
    chosen = select_pages(facts)
    sources = {s.name: s for s in discover_page_sources(DATA_DIR)}

    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for item in chosen:
        book, page = item["book"], item["page_index"]
        source = sources.get(book)
        if source is None:
            print(f"[bo qua] khong tim thay nguon cho {book}")
            continue
        outdir = GOLD_DIR / book / f"page_{page:03d}"
        gold_path = outdir / "gold.txt"
        if gold_path.exists() and not overwrite:
            print(f"  giu nguyen (da co): {book}/page_{page:03d}")
            continue
        outdir.mkdir(parents=True, exist_ok=True)

        image = source.load(page)
        regions = segment_page(image, "kntt")
        units = extract_text_units(image, regions, "kntt")
        body = _blocks_to_text(units)

        cv2.imwrite(str(outdir / "page.png"), image)
        (outdir / "ocr.txt").write_text(
            "# OUTPUT CUA MAY — KHONG SUA FILE NAY\n" + body, encoding="utf-8")
        gold_path.write_text(GOLD_HEADER + body, encoding="utf-8")
        item["n_blocks"] = len(units)
        item["n_chars_ocr"] = sum(len(u.text) for u in units)
        print(f"  {book} page_{page:03d} [{item['archetype']}] "
              f"{len(units)} vung, {item['n_chars_ocr']} ky tu")
        written += 1

    (GOLD_DIR / "_selection.json").write_text(json.dumps({
        "n_pages": len(chosen),
        "archetypes": list(ARCHETYPES),
        "human_reviewed": False,
        "scope_note": ("Chi do MOT engine (Tesseract vie). Phan consensus 2 "
                       "engine cua G2 goc KHONG do duoc — PaddleOCR chua cai."),
        "bias_note": ("gold.txt duoc moi bang chinh output OCR, nen CER do "
                      "duoc la CAN DUOI cua CER that."),
        "pages": chosen,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nDa dung {written} trang moi (tong {len(chosen)}) tai {GOLD_DIR}")
    print("Buoc cua BAN: mo page.png, sua gold.txt, dien #REVIEWED-BY.")
    print("Xong thi chay: python -m src.test.qa_ocr_gold --score --per-page")
    return 0


# ---------------------------------------------------------------- đo

def _strip_marks(ch: str) -> str:
    """Bỏ dấu, GIỮ hoa/thường.

    Không hạ chữ thường ở đây là có chủ đích: nếu fold cả hoa/thường thì một lỗi
    'A' -> 'a' sẽ bị đếm thành lỗi DẤU và thổi phồng đúng con số đang có ngưỡng
    (diacritic-ER <= 2%). Lỗi hoa/thường được đếm riêng.
    """
    d = unicodedata.normalize("NFD", ch)
    return "".join(c for c in d if unicodedata.category(c) != "Mn")


def _is_letter(ch: str) -> bool:
    return unicodedata.category(ch).startswith("L")


def _levenshtein(a, b):
    """Ma trận DP đầy đủ (cần cho backtrace)."""
    n, m = len(a), len(b)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        d[i][0] = i
    for j in range(1, m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        ai = a[i - 1]
        row, prev = d[i], d[i - 1]
        for j in range(1, m + 1):
            cost = 0 if ai == b[j - 1] else 1
            row[j] = min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + cost)
    return d


def _align_chars(gold: str, ocr: str):
    """Trả (dist, sub_dau, sub_hoa, sub_khac, ins, del).

    Ba loại thay thế được tách riêng vì chúng nói ba điều khác nhau:
      sub_dau  — cùng chữ gốc, khác DẤU  ('ế' -> 'é'): lỗi tiếng Việt đặc thù.
      sub_hoa  — chỉ khác hoa/thường     ('A' -> 'a'): gần như vô hại về nghĩa.
      sub_khac — khác hẳn chữ            ('m' -> 'n'): lỗi nhận dạng thật.
    """
    d = _levenshtein(gold, ocr)
    i, j = len(gold), len(ocr)
    sub_dau = sub_hoa = sub_khac = ins = dele = 0
    while i > 0 or j > 0:
        if (i > 0 and j > 0 and gold[i - 1] == ocr[j - 1]
                and d[i][j] == d[i - 1][j - 1]):
            i, j = i - 1, j - 1
        elif i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + 1:
            g, o = gold[i - 1], ocr[j - 1]
            if _strip_marks(g) == _strip_marks(o):
                sub_dau += 1
            elif g.lower() == o.lower():
                sub_hoa += 1
            else:
                sub_khac += 1
            i, j = i - 1, j - 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            dele += 1          # gold có, OCR thiếu
            i -= 1
        else:
            ins += 1           # OCR thêm chữ không có trong gold
            j -= 1
    return d[len(gold)][len(ocr)], sub_dau, sub_hoa, sub_khac, ins, dele


def _word_distance(gw, ow) -> int:
    return _levenshtein(gw, ow)[len(gw)][len(ow)]


def _parse_blocks(text: str) -> dict:
    blocks: dict = {}
    cur = None
    buf: list = []
    for line in text.splitlines():
        mm = BLOCK_RE.match(line)
        if mm:
            if cur is not None:
                blocks[cur] = "\n".join(buf).strip()
            cur, buf = int(mm.group(1)), []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        blocks[cur] = "\n".join(buf).strip()
    return blocks


def _norm_ws(s: str) -> str:
    return " ".join(s.split())


def do_score(per_page: bool) -> int:
    sel_path = GOLD_DIR / "_selection.json"
    if not sel_path.exists():
        print(f"Chua co {sel_path}. Chay --export truoc.")
        return 1
    sel = json.loads(sel_path.read_text(encoding="utf-8"))

    reviewed, unreviewed, rows = [], [], []
    tot = Counter()
    empties = 0

    for item in sel["pages"]:
        outdir = GOLD_DIR / item["book"] / f"page_{item['page_index']:03d}"
        gold_path, ocr_path = outdir / "gold.txt", outdir / "ocr.txt"
        if not gold_path.exists() or not ocr_path.exists():
            unreviewed.append((item, "thieu file"))
            continue
        gtext = gold_path.read_text(encoding="utf-8")
        mm = REVIEW_RE.search(gtext)
        who = (mm.group(1).strip() if mm else "")
        if not who or who.startswith("#"):
            unreviewed.append((item, "chua dien #REVIEWED-BY"))
            continue

        gblocks = _parse_blocks(gtext)
        oblocks = _parse_blocks(ocr_path.read_text(encoding="utf-8"))
        p = Counter()
        for k in sorted(set(gblocks) | set(oblocks)):
            g = _norm_ws(gblocks.get(k, ""))
            o = _norm_ws(oblocks.get(k, ""))
            if not g and o:
                empties += 1        # người chấm: block này là rác, không phải chữ
                p["vung_rac"] += 1
                continue
            if not g and not o:
                continue
            dist, sd, sh, sk, ins, dele = _align_chars(g, o)
            p["dist"] += dist
            p["sub_dau"] += sd
            p["sub_hoa"] += sh
            p["sub_khac"] += sk
            p["ins"] += ins
            p["del"] += dele
            p["gold_chars"] += len(g)
            p["gold_letters"] += sum(1 for c in g if _is_letter(c))
            gw, ow = g.split(), o.split()
            p["werr"] += _word_distance(gw, ow)
            p["gold_words"] += len(gw)
        # Chu ky KHONG chung minh la da doi chieu ky. Nen dem thang: nguoi da
        # sua bao nhieu cho so voi ocr.txt, va lan doc thu hai (neu co) khong
        # dong y voi ocr.txt bao nhieu cho. Neu nguoi sua RAT IT ma lan doc thu
        # hai lai khac RAT NHIEU thi trang do gan nhu chac chan CHUA duoc doc
        # ky — phai in ra, khong duoc de con so CER im lang di qua.
        import difflib as _dl

        def _ndiff(a_blocks, b_blocks):
            n = 0
            for kk in sorted(set(a_blocks) | set(b_blocks)):
                aa = _norm_ws(a_blocks.get(kk, "")).split()
                bb = _norm_ws(b_blocks.get(kk, "")).split()
                for tag, i1, i2, j1, j2 in _dl.SequenceMatcher(
                        a=aa, b=bb, autojunk=False).get_opcodes():
                    if tag != "equal":
                        n += 1
            return n

        p["sua_tay"] = _ndiff(oblocks, gblocks)
        r2 = outdir / READ2_NAME
        p["may2"] = (_ndiff(oblocks, _parse_blocks(
            r2.read_text(encoding="utf-8"))) if r2.exists() else -1)
        reviewed.append(item)
        rows.append((item, who, p))
        tot.update(p)

    print("=" * 72)
    print("CONG G2 — CER/WER/loi DAU tren gold set NGUOI xac nhan")
    print("=" * 72)
    print(f"Trang da duyet: {len(reviewed)}/{len(sel['pages'])}")
    if unreviewed:
        print(f"Trang CHUA duyet (nam NGOAI moi con so): {len(unreviewed)}")
        for item, why in unreviewed[:30]:
            print(f"   - {item['book']} page_{item['page_index']:03d} "
                  f"[{item['archetype']}] : {why}")
    if not reviewed:
        print("\nChua co trang nao duoc duyet -> KHONG co con so nao de bao cao.")
        print("Day la ket qua THAT, khong phai loi. Sua gold.txt roi chay lai.")
        return 1

    gc = tot["gold_chars"] or 1
    gl = tot["gold_letters"] or 1
    gw = tot["gold_words"] or 1
    cer, wer, der = tot["dist"] / gc, tot["werr"] / gw, tot["sub_dau"] / gl
    print(f"\nKy tu gold: {tot['gold_chars']} | tu gold: {tot['gold_words']}")
    print(f"CER          = {cer:.4f}  ({cer * 100:.2f}%)")
    print(f"WER          = {wer:.4f}  ({wer * 100:.2f}%)")
    print(f"diacritic-ER = {der:.4f}  ({der * 100:.2f}%)  nguong "
          f"<= {DIACRITIC_ER_MAX * 100:.0f}%")
    print(f"   thay the vi DAU     : {tot['sub_dau']}")
    print(f"   thay the hoa/thuong : {tot['sub_hoa']}")
    print(f"   thay the khac chu   : {tot['sub_khac']}")
    print(f"   OCR thieu chu     : {tot['del']}")
    print(f"   OCR them chu      : {tot['ins']}")
    if empties:
        print(f"   vung nguoi cham la RAC (khong phai chu): {empties}")

    if per_page:
        print("\n{:<8} {:>5} {:<14} {:>8} {:>8} {:>8} {:>7} {:>6}".format(
            "quyen", "trang", "archetype", "CER", "WER", "dia-ER",
            "nguoi", "may2"))
        for item, _who, p in rows:
            c = p["dist"] / (p["gold_chars"] or 1)
            w = p["werr"] / (p["gold_words"] or 1)
            dd = p["sub_dau"] / (p["gold_letters"] or 1)
            print("{:<8} {:>5} {:<14} {:>7.2f}% {:>7.2f}% {:>7.2f}% {:>7} {:>6}"
                  .format(
                      item["book"].replace("SGK_KHTN_", "").replace("_KNTT", ""),
                      item["page_index"], item["archetype"],
                      c * 100, w * 100, dd * 100,
                      p["sua_tay"], p["may2"] if p["may2"] >= 0 else "-"))
        print("  'nguoi' = so cho NGUOI sua so voi ocr.txt | "
              "'may2' = so cho lan doc thu hai khac ocr.txt")

    # Canh bao trang co chu ky nhung gan nhu khong sua gi, trong khi lan doc
    # thu hai lai khac rat nhieu -> con so CER cua trang do khong dang tin.
    dubious = [(i, p) for i, _w, p in rows
               if p["may2"] > 0 and p["sua_tay"] * 3 < p["may2"]]
    if dubious:
        print(f"\nCANH BAO — {len(dubious)} trang CO chu ky nhung gan nhu chua "
              "duoc doi chieu (nguoi sua rat it so voi cho bat dong that):")
        for item, p in dubious:
            print(f"   - {item['book']} page_{item['page_index']:03d}: nguoi sua "
                  f"{p['sua_tay']} cho, nhung lan doc thu hai khac {p['may2']} cho")
        print("   CER/WER cua nhung trang nay KHONG dang tin. Doc lai roi ky lai.")

    print("\nPHAM VI: chi MOT engine (Tesseract vie). Phan 'consensus 2 engine "
          "tot hon ca hai' cua G2 goc KHONG do duoc — PaddleOCR chua cai.")
    print("SAI LECH: gold moi bang output OCR -> CER do duoc la CAN DUOI.")
    if len(reviewed) < len(sel["pages"]):
        print(f"KHONG DU BO: chi {len(reviewed)}/{len(sel['pages'])} trang duyet.")
    ok = der <= DIACRITIC_ER_MAX
    print(f"\ndiacritic-ER {'DAT' if ok else 'KHONG DAT'} nguong "
          f"{DIACRITIC_ER_MAX * 100:.0f}%.")
    return 0 if ok else 1


# ------------------------------------------------- doi chieu lan doc thu hai

READ2_NAME = "read_claude.txt"


def _iter_pages(sel):
    for item in sel["pages"]:
        yield item, GOLD_DIR / item["book"] / f"page_{item['page_index']:03d}"


def do_diff() -> int:
    """In CHO BAT DONG giua ocr.txt va lan doc thu hai, theo tung tu.

    Muc dich: bien 50 000 ky tu phai doi chieu thanh vai tram cho phai phan xu.
    Lan doc thu hai KHONG phai gold — no chi chi cho NGUOI biet nen nhin vao dau.
    """
    import difflib
    sel_path = GOLD_DIR / "_selection.json"
    if not sel_path.exists():
        print(f"Chua co {sel_path}. Chay --export truoc.")
        return 1
    sel = json.loads(sel_path.read_text(encoding="utf-8"))

    n_done = 0
    tot_words = tot_diff = 0
    rows = []
    for item, outdir in _iter_pages(sel):
        r2 = outdir / READ2_NAME
        ocr = outdir / "ocr.txt"
        if not r2.exists() or not ocr.exists():
            continue
        n_done += 1
        ob = _parse_blocks(ocr.read_text(encoding="utf-8"))
        cb = _parse_blocks(r2.read_text(encoding="utf-8"))
        pw = pd = 0
        chunks = []
        for k in sorted(set(ob) | set(cb)):
            o = _norm_ws(ob.get(k, "")).split()
            c = _norm_ws(cb.get(k, "")).split()
            pw += len(c)
            sm = difflib.SequenceMatcher(a=o, b=c, autojunk=False)
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == "equal":
                    continue
                pd += max(i2 - i1, j2 - j1)
                chunks.append((k, tag, " ".join(o[i1:i2]), " ".join(c[j1:j2])))
        tot_words += pw
        tot_diff += pd
        rows.append((item, pw, pd, chunks))

    if not n_done:
        print(f"Chua co file {READ2_NAME} nao. Khong co gi de doi chieu.")
        return 1

    print("=" * 72)
    print(f"DOI CHIEU ocr.txt  <->  {READ2_NAME} (lan doc thu hai bang may)")
    print("=" * 72)
    print(f"Trang co lan doc thu hai: {n_done}/{len(sel['pages'])}\n")
    print("{:<8} {:>5} {:<14} {:>7} {:>8} {:>9}".format(
        "quyen", "trang", "archetype", "tu", "bat dong", "ti le"))
    for item, pw, pd, _c in rows:
        print("{:<8} {:>5} {:<14} {:>7} {:>8} {:>8.1%}".format(
            item["book"].replace("SGK_KHTN_", "").replace("_KNTT", ""),
            item["page_index"], item["archetype"], pw, pd, pd / max(pw, 1)))
    print(f"\nTONG: {tot_diff} cho bat dong / {tot_words} tu "
          f"= {tot_diff/max(tot_words,1):.1%}")
    print("\nDay la CAN TREN cua so cho NGUOI phai xem: hai may cung doc sai "
          "giong nhau thi khong hien ra o day.")
    print(f"\nChi tiet: python -m src.test.qa_ocr_gold --diff --show <trang>")
    return 0


def do_diff_show(page: int) -> int:
    import difflib
    sel = json.loads((GOLD_DIR / "_selection.json").read_text(encoding="utf-8"))
    hit = False
    for item, outdir in _iter_pages(sel):
        if item["page_index"] != page:
            continue
        r2, ocr = outdir / READ2_NAME, outdir / "ocr.txt"
        if not r2.exists():
            continue
        hit = True
        print("=" * 72)
        print(f"{item['book']} page_{page:03d} [{item['archetype']}]")
        print("=" * 72)
        ob = _parse_blocks(ocr.read_text(encoding="utf-8"))
        cb = _parse_blocks(r2.read_text(encoding="utf-8"))
        for k in sorted(set(ob) | set(cb)):
            o = _norm_ws(ob.get(k, "")).split()
            c = _norm_ws(cb.get(k, "")).split()
            sm = difflib.SequenceMatcher(a=o, b=c, autojunk=False)
            first = True
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == "equal":
                    continue
                if first:
                    print(f"\n--- block [{k}] ---")
                    first = False
                lhs = " ".join(o[i1:i2]) or "(khong co)"
                rhs = " ".join(c[j1:j2]) or "(xoa)"
                print(f"  may1: {lhs}")
                print(f"  may2: {rhs}")
    if not hit:
        print(f"Khong tim thay trang {page} co {READ2_NAME}.")
        return 1
    return 0


def do_promote(force: bool) -> int:
    """Do noi dung lan doc thu hai vao gold.txt, GIU dong #REVIEWED-BY TRONG.

    Muc dich: nguoi khong phai go lai tu dau. Quy trinh con lai cua nguoi la
    (1) doc `--diff` de xem may1 vs may2 khac nhau o dau, (2) sua lai nhung cho
    minh khong dong y, (3) dien ten vao #REVIEWED-BY.

    KHONG tu dien ten: gold set nay se duoc bao cao la "NGUOI xac nhan", nen chi
    con nguoi moi duoc ky. May tu ky vao la lam sai xuat xu cua so do.
    """
    sel_path = GOLD_DIR / "_selection.json"
    if not sel_path.exists():
        print(f"Chua co {sel_path}. Chay --export truoc.")
        return 1
    sel = json.loads(sel_path.read_text(encoding="utf-8"))
    done = skipped = 0
    for item, outdir in _iter_pages(sel):
        r2, gold = outdir / READ2_NAME, outdir / "gold.txt"
        if not r2.exists():
            continue
        if gold.exists():
            mm = REVIEW_RE.search(gold.read_text(encoding="utf-8"))
            who = (mm.group(1).strip() if mm else "")
            if who and not who.startswith("#") and not force:
                print(f"  BO QUA (da co nguoi duyet: {who}): "
                      f"{item['book']} page_{item['page_index']:03d}")
                skipped += 1
                continue
        blocks = _parse_blocks(r2.read_text(encoding="utf-8"))
        body = []
        for k in sorted(blocks):
            body.append(f"=== [{k}] {_region_of(r2, k)} ===")
            body.append(blocks[k])
            body.append("")
        gold.write_text(GOLD_HEADER + "\n".join(body).rstrip() + "\n",
                        encoding="utf-8")
        done += 1
    print(f"\nDa do lan doc thu hai vao {done} gold.txt "
          f"(bo qua {skipped} trang da co nguoi duyet).")
    print("Dong #REVIEWED-BY vẫn TRONG — chi BAN moi duoc dien ten vao do.")
    print("Buoc tiep: python -m src.test.qa_ocr_gold --diff --show <trang>")
    return 0


def _region_of(path, k: int) -> str:
    """Lay lai nhan region_type cua block k tu file goc (giu nguyen tieu de)."""
    for line in path.read_text(encoding="utf-8").splitlines():
        mm = BLOCK_RE.match(line)
        if mm and int(mm.group(1)) == k:
            return mm.group(2)
    return "body"


def main() -> int:
    ap = argparse.ArgumentParser(description="Cong G2 — CER/WER/loi dau OCR")
    ap.add_argument("--export", action="store_true",
                    help="dung 24 trang de nguoi sua")
    ap.add_argument("--score", action="store_true", help="do sau khi da sua")
    ap.add_argument("--diff", action="store_true",
                    help=f"doi chieu ocr.txt voi {READ2_NAME} (lan doc thu hai)")
    ap.add_argument("--promote", action="store_true",
                    help=f"do {READ2_NAME} vao gold.txt, GIU #REVIEWED-BY trong")
    ap.add_argument("--show", type=int, default=0,
                    help="dung voi --diff: in chi tiet mot so trang")
    ap.add_argument("--per-page", action="store_true", help="in bang tung trang")
    ap.add_argument("--overwrite", action="store_true",
                    help="ghi de gold.txt da co (MAT phan da sua tay!)")
    args = ap.parse_args()
    chon = (args.export, args.score, args.diff, args.promote)
    if sum(bool(x) for x in chon) != 1:
        ap.error("chon dung mot trong --export / --score / --diff / --promote")
    if args.diff:
        return do_diff_show(args.show) if args.show else do_diff()
    if args.promote:
        return do_promote(args.overwrite)
    return do_export(args.overwrite) if args.export else do_score(args.per_page)


if __name__ == "__main__":
    raise SystemExit(main())
